$ErrorActionPreference = "Stop"

$PROJECT_ROOT = "C:\Users\hashedUserChain1user\Documents\fire_forecast"

Set-Location $PROJECT_ROOT

Write-Host ""
Write-Host "Checking Docker daemon..." -ForegroundColor Cyan

docker info *> $null

if ($LASTEXITCODE -ne 0) {
  Write-Host "Docker is not running or is not reachable." -ForegroundColor Red
  Write-Host "Open Docker Desktop, wait until the engine is running, then rerun this script." -ForegroundColor Yellow
  exit 1
}

Write-Host "Docker daemon is reachable." -ForegroundColor Green

Write-Host ""
Write-Host "Validating docker compose configuration..." -ForegroundColor Cyan

docker compose --env-file .env -f infra/docker/docker-compose.yml config *> $null

if ($LASTEXITCODE -ne 0) {
  Write-Host "Docker compose configuration is invalid." -ForegroundColor Red
  Write-Host "Printing compose config error details:" -ForegroundColor Yellow
  docker compose --env-file .env -f infra/docker/docker-compose.yml config
  exit 1
}

Write-Host "Docker compose configuration is valid." -ForegroundColor Green

Write-Host ""
Write-Host "Starting Fire Forecast stack..." -ForegroundColor Cyan

docker compose --env-file .env -f infra/docker/docker-compose.yml up --build -d

if ($LASTEXITCODE -ne 0) {
  Write-Host ""
  Write-Host "docker compose up failed. Stack was not started correctly." -ForegroundColor Red
  exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Docker compose status:" -ForegroundColor Cyan

docker compose --env-file .env -f infra/docker/docker-compose.yml ps

Write-Host ""
Write-Host "Stack started." -ForegroundColor Green
Write-Host "API Gateway:    http://localhost:8000" -ForegroundColor Green
Write-Host "System health:  http://localhost:8000/api/system/health" -ForegroundColor Green
Write-Host "NATS monitor:   http://localhost:8222" -ForegroundColor Green
Write-Host "MinIO console:  http://localhost:9001" -ForegroundColor Green
Write-Host "Prefect server: http://localhost:4202" -ForegroundColor Green
