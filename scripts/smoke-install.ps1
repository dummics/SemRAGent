param(
    [string]$Source = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path,
    [string]$WorkDir = (Join-Path $env:TEMP ("semragent-smoke-" + [guid]::NewGuid().ToString("N"))),
    [switch]$Keep
)

$ErrorActionPreference = "Stop"

function Step($Message) { Write-Host "`n==> $Message" -ForegroundColor Cyan }
function Ok($Message) { Write-Host "[OK] $Message" -ForegroundColor Green }

try {
    Step "Creating clean smoke workspace"
    New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
    $Checkout = Join-Path $WorkDir "repo"
    git clone $Source $Checkout | Out-Null

    Step "Creating virtual environment"
    $Venv = Join-Path $WorkDir ".venv"
    python -m venv $Venv
    $Python = Join-Path $Venv "Scripts\python.exe"
    & $Python -m pip install --upgrade pip setuptools wheel | Out-Null

    Step "Installing package without model extras"
    & $Python -m pip install -e "$Checkout[dev]" | Out-Null

    Step "Running CLI smoke"
    & $Python -m workspace_docs_mcp.cli --help | Out-Null
    & $Python -m workspace_docs_mcp.cli --root $Checkout init --preset generic --force | Out-Null
    & $Python -m workspace_docs_mcp.cli --root $Checkout qdrant status | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[WARN] Qdrant unavailable during smoke; this is allowed for install-only smoke." -ForegroundColor Yellow
    }
    & $Python -m workspace_docs_mcp.cli --root $Checkout lint-authority --json | Out-Null
    & $Python -m workspace_docs_mcp.cli --root $Checkout eval bootstrap | Out-Null

    Step "Running tests"
    Push-Location $Checkout
    try {
        & $Python -m unittest discover -s tests -v
    } finally {
        Pop-Location
    }

    Ok "Smoke install passed: $WorkDir"
} finally {
    if (-not $Keep -and (Test-Path -LiteralPath $WorkDir)) {
        Remove-Item -LiteralPath $WorkDir -Recurse -Force
    }
}
