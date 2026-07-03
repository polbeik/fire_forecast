param(
  [switch]$Volumes
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $RepoRoot

$EnvFile = ".env"
$ComposeFile = "infra/docker/docker-compose.yml"

if (-not (Test-Path $ComposeFile)) {
  throw "Compose file not found: $ComposeFile"
}

if (-not (Test-Path $EnvFile)) {
  throw "Missing .env. Refusing to run docker compose without explicit env file."
}

$ComposeArgs = @("--env-file", $EnvFile, "-f", $ComposeFile)

Write-Host "Validating Docker Compose config..."
docker compose @ComposeArgs config --quiet

$DownArgs = @("down")
if ($Volumes) {
  $DownArgs += "-v"
}

Write-Host "Stopping Fire Forecast stack with explicit .env..."
docker compose @ComposeArgs @DownArgs
