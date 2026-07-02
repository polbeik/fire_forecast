$ErrorActionPreference = "Stop"

$PROJECT_ROOT = "C:\Users\hashedUserChain1user\Documents\fire_forecast"

cd $PROJECT_ROOT

Write-Host "Stopping Fire Forecast stack..." -ForegroundColor Cyan

docker compose --env-file .env -f infra/docker/docker-compose.yml down

Write-Host "Stack stopped." -ForegroundColor Green
