param(
    [string]$Root = (Get-Location).Path,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PassthroughArgs
)

$ErrorActionPreference = "Stop"

$toolRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$workspaceRoot = (Resolve-Path $Root).Path
Set-Location $workspaceRoot

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = $toolRoot

$python = (Get-Command python -ErrorAction Stop).Source
$arguments = @("-m", "workspace_docs_mcp.cli", "--root", $workspaceRoot, "mcp")
if ($PassthroughArgs) {
    $arguments += $PassthroughArgs
}

& $python @arguments
exit $LASTEXITCODE
