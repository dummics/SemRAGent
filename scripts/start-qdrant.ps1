param(
    [string]$StorageDir = "$env:USERPROFILE\.workspace-docs-mcp\qdrant",
    [int]$Port = 6333,
    [string]$ContainerName = "workspace-docs-qdrant"
)

$ErrorActionPreference = "Stop"

function Step($Message) { Write-Host "`n==> $Message" -ForegroundColor Cyan }
function Ok($Message) { Write-Host "[OK] $Message" -ForegroundColor Green }
function Fail($Message) { Write-Host "[FAIL] $Message" -ForegroundColor Red; exit 1 }

Step "Checking Docker"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Fail "Docker CLI is required to auto-start Qdrant. Start Qdrant manually or install Docker Desktop."
}

New-Item -ItemType Directory -Force -Path $StorageDir | Out-Null

$existing = docker ps -a --filter "name=^/$ContainerName$" --format "{{.Names}}"
if ($existing -eq $ContainerName) {
    Step "Starting existing Qdrant container"
    docker start $ContainerName | Out-Null
} else {
    Step "Creating Qdrant container"
    docker run -d --name $ContainerName -p "${Port}:6333" -v "${StorageDir}:/qdrant/storage" qdrant/qdrant | Out-Null
}

Step "Waiting for Qdrant"
$deadline = (Get-Date).AddSeconds(30)
do {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:$Port/collections" -UseBasicParsing -TimeoutSec 3
        if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
            Ok "Qdrant reachable at http://localhost:$Port"
            exit 0
        }
    } catch {
        Start-Sleep -Seconds 1
    }
} while ((Get-Date) -lt $deadline)

Fail "Qdrant did not become reachable at http://localhost:$Port within 30 seconds."
