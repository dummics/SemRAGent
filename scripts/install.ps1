param(
    [string]$InstallDir = "$env:USERPROFILE\.workspace-docs-mcp",
    [string]$RepoUrl = "https://github.com/dummics/workspace-docs-mcp.git",
    [switch]$WithCuda,
    [switch]$CpuOnly,
    [switch]$StartQdrant,
    [switch]$Dev
)

$ErrorActionPreference = "Stop"

function Step($Message) { Write-Host "`n==> $Message" -ForegroundColor Cyan }
function Ok($Message) { Write-Host "[OK] $Message" -ForegroundColor Green }
function Warn($Message) { Write-Host "[WARN] $Message" -ForegroundColor Yellow }
function Fail($Message) { Write-Host "[FAIL] $Message" -ForegroundColor Red; exit 1 }

if ($WithCuda -and $CpuOnly) {
    Fail "Choose only one of -WithCuda or -CpuOnly."
}

Step "Checking prerequisites"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Fail "Git is required." }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { Fail "Python 3.11+ is required." }
$pythonVersion = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ([version]$pythonVersion -lt [version]"3.11") { Fail "Python 3.11+ is required. Found $pythonVersion." }
Ok "Python $pythonVersion"

Step "Cloning or updating workspace-docs-mcp"
if (Test-Path -LiteralPath (Join-Path $InstallDir ".git")) {
    git -C $InstallDir pull --ff-only
} elseif (Test-Path -LiteralPath $InstallDir) {
    Fail "InstallDir exists but is not a git checkout: $InstallDir. Choose a different -InstallDir or move it manually."
} else {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $InstallDir) | Out-Null
    git clone $RepoUrl $InstallDir
}
Ok "Repository ready: $InstallDir"

Step "Creating virtual environment"
$Venv = Join-Path $InstallDir ".venv"
if (-not (Test-Path -LiteralPath $Venv)) {
    python -m venv $Venv
}
$Python = Join-Path $Venv "Scripts\python.exe"
$WorkspaceDocs = Join-Path $Venv "Scripts\workspace-docs.exe"
$WorkspaceDocsMcp = Join-Path $Venv "Scripts\workspace-docs-mcp.exe"
& $Python -m pip install --upgrade pip setuptools wheel

if ($WithCuda) {
    Step "Installing CUDA PyTorch"
    & $Python -m pip install --force-reinstall "torch==2.7.1" "torchvision==0.22.1" "torchaudio==2.7.1" --index-url "https://download.pytorch.org/whl/cu128"
} elseif ($CpuOnly) {
    Warn "CPU mode selected. First indexing and reranking can be slow."
} else {
    Warn "No GPU mode selected. If this machine has NVIDIA CUDA, rerun with -WithCuda for better performance."
}

Step "Installing package"
$Extra = if ($Dev) { ".[dev,all]" } else { ".[all]" }
& $Python -m pip install -e "$InstallDir$Extra"
Ok "Installed workspace-docs-mcp"

Step "Creating stable command wrappers"
$BinDir = Join-Path $InstallDir "bin"
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
$WorkspaceDocs = Join-Path $BinDir "workspace-docs.cmd"
$WorkspaceDocsMcp = Join-Path $BinDir "workspace-docs-mcp.cmd"
$CmdPython = $Python.Replace("%", "%%")
Set-Content -LiteralPath $WorkspaceDocs -Encoding ASCII -Value "@echo off`r`n`"$CmdPython`" -m workspace_docs_mcp.cli %*`r`n"
Set-Content -LiteralPath $WorkspaceDocsMcp -Encoding ASCII -Value "@echo off`r`n`"$CmdPython`" -c `"from workspace_docs_mcp.cli import mcp_main; raise SystemExit(mcp_main())`" %*`r`n"
Ok "Wrappers ready: $BinDir"

if ($StartQdrant) {
    & (Join-Path $InstallDir "scripts\start-qdrant.ps1") -StorageDir (Join-Path $InstallDir ".qdrant")
}

Step "Final commands"
Write-Host "workspace-docs:     $WorkspaceDocs"
Write-Host "workspace-docs-mcp: $WorkspaceDocsMcp"
Write-Host ""
Write-Host "Codex MCP example:"
Write-Host "[mcp_servers.workspaceDocs]"
Write-Host "command = `"$WorkspaceDocsMcp`""
Write-Host "args = [`"--root`", `"C:\\path\\to\\workspace`"]"
Write-Host "enabled = true"
Write-Host "startup_timeout_sec = 120"
Write-Host "tool_timeout_sec = 300"
Write-Host ""
Write-Host "Claude Desktop example:"
Write-Host "{"
Write-Host "  `"mcpServers`": {"
Write-Host "    `"workspace-docs`": {"
Write-Host "      `"command`": `"$WorkspaceDocsMcp`","
Write-Host "      `"args`": [`"--root`", `"C:\\path\\to\\workspace`"]"
Write-Host "    }"
Write-Host "  }"
Write-Host "}"
Write-Host ""
Write-Host "Next:"
Write-Host "  & `"$WorkspaceDocs`" --help"
Write-Host "  & `"$InstallDir\scripts\setup-workspace.ps1`" -Workspace `"C:\path\to\workspace`" -Preset generic -BuildIndex"
