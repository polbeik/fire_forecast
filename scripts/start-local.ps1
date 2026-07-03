param(
  [switch]$NoBuild,
  [string[]]$Service = @()
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ComposeFile = Join-Path $RepoRoot "infra/docker/docker-compose.yml"
$EnvFile = Join-Path $RepoRoot ".env"
$EnvExample = Join-Path $RepoRoot ".env.example"

if (-not (Test-Path $ComposeFile)) {
  throw "Compose file not found: $ComposeFile"
}

if (-not (Test-Path $EnvFile) -and (Test-Path $EnvExample)) {
  Copy-Item $EnvExample $EnvFile
  Write-Host "Created .env from .env.example"
}

$ComposeArgs = @("compose", "--project-directory", $RepoRoot, "-f", $ComposeFile)

if (Test-Path $EnvFile) {
  $ComposeArgs += @("--env-file", $EnvFile)
} else {
  Write-Warning ".env not found. Docker Compose will use shell/default values."
}

Write-Host "Validating Docker Compose config..."
$ConfigArgs = $ComposeArgs + @("config", "--quiet")
& docker @ConfigArgs
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

$Cmd = @("up", "-d")

if (-not $NoBuild) {
  $Cmd += "--build"
}

$Cmd += $Service

Write-Host "Starting local Fire Forecast stack..."
$AllArgs = $ComposeArgs + $Cmd
& docker @AllArgs
exit $LASTEXITCODE
