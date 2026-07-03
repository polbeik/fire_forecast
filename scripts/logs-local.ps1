param(
  [string[]]$Service = @(),
  [int]$Tail = 200,
  [switch]$NoFollow
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

$Cmd = @("logs", "--tail", $Tail.ToString())

if (-not $NoFollow) {
  $Cmd += "-f"
}

$Cmd += $Service

$AllArgs = $ComposeArgs + $Cmd
& docker @AllArgs
exit $LASTEXITCODE
