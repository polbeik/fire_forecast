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
  throw "Missing .env. Health validation must use the same explicit env file as start/stop."
}

$ComposeArgs = @("--env-file", $EnvFile, "-f", $ComposeFile)

Write-Host "Validating Docker Compose config..."
docker compose @ComposeArgs config --quiet

Write-Host ""
Write-Host "Docker Compose services:"
docker compose @ComposeArgs ps

Write-Host ""
Write-Host "Checking container states..."

$rawJson = docker compose @ComposeArgs ps --format json

if ([string]::IsNullOrWhiteSpace($rawJson)) {
  throw "docker compose ps returned no JSON output."
}

if ($rawJson.TrimStart().StartsWith("[")) {
  $containers = @($rawJson | ConvertFrom-Json)
} else {
  $containers = @($rawJson -split "`n" | Where-Object { $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json })
}

$badContainers = @()

foreach ($container in $containers) {
  $state = [string]$container.State
  $health = [string]$container.Health
  $name = [string]$container.Name
  $service = [string]$container.Service

  if ($state -ne "running") {
    $badContainers += "$service / $name is not running. State=$state"
    continue
  }

  if (-not [string]::IsNullOrWhiteSpace($health) -and $health -ne "healthy") {
    $badContainers += "$service / $name is not healthy. Health=$health"
  }
}

if ($badContainers.Count -gt 0) {
  Write-Host ""
  Write-Host "Unhealthy containers:"
  $badContainers | ForEach-Object { Write-Host " - $_" }
  exit 1
}

Write-Host "All running containers are healthy according to Docker Compose."

Write-Host ""
Write-Host "Checking HTTP health endpoints where applicable..."

$services = @(docker compose @ComposeArgs config --services)

$HealthEndpoints = @{
  "api-gateway"       = "http://localhost:8000/health"
  "catalog-service"  = "http://localhost:8101/health"
  "ingestion-service" = "http://localhost:8102/health"
  "minio"            = "http://localhost:9000/minio/health/live"
}

$endpointFailures = @()

foreach ($serviceName in $HealthEndpoints.Keys) {
  if ($services -contains $serviceName) {
    $url = $HealthEndpoints[$serviceName]
    try {
      $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 10
      if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 300) {
        $endpointFailures += "$serviceName returned HTTP $($response.StatusCode) at $url"
      } else {
        Write-Host "OK $serviceName -> $url"
      }
    } catch {
      $endpointFailures += "$serviceName failed at $url : $($_.Exception.Message)"
    }
  }
}

if ($endpointFailures.Count -gt 0) {
  Write-Host ""
  Write-Host "HTTP health failures:"
  $endpointFailures | ForEach-Object { Write-Host " - $_" }
  exit 1
}

Write-Host ""
Write-Host "Local Fire Forecast stack health validation passed."
