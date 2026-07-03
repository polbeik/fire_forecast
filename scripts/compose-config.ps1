param(
  [switch]$Quiet
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ComposeFile = Join-Path $RepoRoot "infra/docker/docker-compose.yml"
$EnvFile = Join-Path $RepoRoot ".env"

if (-not (Test-Path $ComposeFile)) {
  throw "Compose file not found: $ComposeFile"
}

$ComposeArgs = @("compose", "--project-directory", $RepoRoot, "-f", $ComposeFile)

if (Test-Path $EnvFile) {
  $ComposeArgs += @("--env-file", $EnvFile)
}

$Cmd = @("config")

if ($Quiet) {
  $Cmd += "--quiet"
}

$AllArgs = $ComposeArgs + $Cmd
& docker @AllArgs

if ($LASTEXITCODE -eq 0 -and $Quiet) {
  Write-Host "Docker Compose config OK."
}

exit $LASTEXITCODE
