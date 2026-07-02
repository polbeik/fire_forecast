$ErrorActionPreference = "Stop"

$urls = @(
  "http://localhost:8000/health",
  "http://localhost:8000/api/system/health",
  "http://localhost:8101/health",
  "http://localhost:8102/health",
  "http://localhost:8103/health",
  "http://localhost:8104/health",
  "http://localhost:8105/health",
  "http://localhost:8106/health",
  "http://localhost:8107/health",
  "http://localhost:8108/health",
  "http://localhost:8109/health"
)

foreach ($url in $urls) {
  try {
    $response = Invoke-RestMethod -Uri $url -Method GET -TimeoutSec 5
    Write-Host "OK   $url" -ForegroundColor Green
    $response | ConvertTo-Json -Depth 8
  } catch {
    Write-Host "FAIL $url" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
  }

  Write-Host ""
}
