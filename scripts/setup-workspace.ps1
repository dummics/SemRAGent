param(
    [Parameter(Mandatory = $true)]
    [string]$Workspace,
    [ValidateSet("generic", "python", "node", "dotnet", "unity")]
    [string]$Preset = "generic",
    [string]$ToolDir = "$env:USERPROFILE\.semragent",
    [switch]$BuildIndex,
    [switch]$NoModelsDoctor,
    [switch]$StartQdrant
)

$ErrorActionPreference = "Stop"

function Step($Message) { Write-Host "`n==> $Message" -ForegroundColor Cyan }
function Ok($Message) { Write-Host "[OK] $Message" -ForegroundColor Green }
function Warn($Message) { Write-Host "[WARN] $Message" -ForegroundColor Yellow }
function Fail($Message) { Write-Host "[FAIL] $Message" -ForegroundColor Red; exit 1 }

$WorkspacePath = (Resolve-Path -LiteralPath $Workspace).Path
$Semragent = Join-Path $ToolDir "bin\semragent.cmd"
$WorkspaceDocs = Join-Path $ToolDir "bin\workspace-docs.cmd"
$WorkspaceDocsMcp = Join-Path $ToolDir "bin\workspace-docs-mcp.cmd"
if (-not (Test-Path -LiteralPath $Semragent)) {
    Fail "semragent wrapper not found at $Semragent. Run scripts\install.ps1 first."
}

if ($StartQdrant) {
    & (Join-Path $ToolDir "scripts\start-qdrant.ps1") -StorageDir (Join-Path $ToolDir "qdrant")
}

Step "Initializing workspace config"
& $Semragent --root $WorkspacePath init --preset $Preset
Ok "Workspace config ready"

Step "Ensuring .rag is ignored"
$GitIgnore = Join-Path $WorkspacePath ".gitignore"
if (Test-Path -LiteralPath $GitIgnore) {
    $content = Get-Content -LiteralPath $GitIgnore -Raw
    if ($content -notmatch "(?m)^\.rag/$") {
        Add-Content -LiteralPath $GitIgnore -Value "`n.rag/"
        Ok "Added .rag/ to .gitignore"
    } else {
        Ok ".rag/ already ignored"
    }
} else {
    Set-Content -LiteralPath $GitIgnore -Encoding ASCII -Value ".rag/`r`n"
    Ok "Created .gitignore with .rag/"
}

if (-not $NoModelsDoctor) {
    Step "Checking local models and Qdrant"
    & $Semragent --root $WorkspacePath models doctor
}

if ($BuildIndex) {
    Step "Building index"
    & $Semragent --root $WorkspacePath index build
}

Step "MCP config"
Write-Host "Codex:"
Write-Host "[mcp_servers.semragent]"
Write-Host "command = `"$Semragent`""
Write-Host "args = [`"--root`", `"$WorkspacePath`", `"mcp`"]"
Write-Host "enabled = true"
Write-Host "startup_timeout_sec = 120"
Write-Host "tool_timeout_sec = 300"
Write-Host ""
Write-Host "Claude Desktop:"
Write-Host "{"
Write-Host "  `"mcpServers`": {"
Write-Host "    `"semragent`": {"
Write-Host "      `"command`": `"$Semragent`","
Write-Host "      `"args`": [`"--root`", `"$WorkspacePath`", `"mcp`"]"
Write-Host "    }"
Write-Host "  }"
Write-Host "}"
Write-Host ""
Warn "Restart the agent after editing MCP config so it loads SemRAGent."
