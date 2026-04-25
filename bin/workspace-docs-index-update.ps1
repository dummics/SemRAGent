param(
    [string]$Root = (Get-Location).Path,
    [switch]$Build,
    [switch]$Doctor
)

$ErrorActionPreference = "Stop"

$toolRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$workspaceRoot = (Resolve-Path $Root).Path
Set-Location $workspaceRoot

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = $toolRoot

$python = (Get-Command python -ErrorAction Stop).Source
$command = if ($Build) { "build" } else { "update" }

if ($Doctor) {
    & $python -m workspace_docs_mcp.cli --root $workspaceRoot models doctor
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

& $python -m workspace_docs_mcp.cli --root $workspaceRoot index $command
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if ($Doctor) {
    & $python -m workspace_docs_mcp.cli --root $workspaceRoot doctor
    exit $LASTEXITCODE
}

exit 0
