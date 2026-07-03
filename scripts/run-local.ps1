param(
  [switch]$Build,
  [switch]$Pull
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
  if (Test-Path ".env.example") {
    Copy-Item ".env.example" $EnvFile
    Write-Host "Created .env from .env.example"
  } else {
    throw "Missing .env and .env.example. Cannot start stack safely."
  }
}

$ComposeArgs = @("--env-file", $EnvFile, "-f", $ComposeFile)

Write-Host "Validating Docker Compose config..."
docker compose @ComposeArgs config --quiet

if ($Pull) {
  Write-Host "Pulling images..."
  docker compose @ComposeArgs pull
}

$UpArgs = @("up", "-d", "--wait")
if ($Build) {
  $UpArgs += "--build"
}

Write-Host "Starting Fire Forecast stack with explicit .env and health wait..."
docker compose @ComposeArgs @UpArgs

Write-Host ""
Write-Host "Docker Compose services:"
docker compose @ComposeArgs ps
