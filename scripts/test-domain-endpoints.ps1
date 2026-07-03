$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "Testing Fire domain endpoints..." -ForegroundColor Cyan
Write-Host ""

Write-Host "1. System health" -ForegroundColor Cyan
Invoke-RestMethod -Uri "http://localhost:8000/api/system/health" -Method GET | ConvertTo-Json -Depth 20

Write-Host ""
Write-Host "2. FLOGA inventory, safe non-recursive scan" -ForegroundColor Cyan
Invoke-RestMethod -Uri "http://localhost:8000/api/floga/inventory?max_files=1000&recursive=false" -Method GET | ConvertTo-Json -Depth 20

Write-Host ""
Write-Host "3. Create counterfactual ignition scenario" -ForegroundColor Cyan

$scenario = @{
  mode = "counterfactual_ignition"
  ignition_geometry = @{
    type = "Point"
    coordinates = @(23.7275, 38.2466)
  }
  start_time_t0 = "2021-08-03T14:00:00+00:00"
  horizon_hours = @(1, 3, 6, 12, 24)
  weather_mode = "archived_forecast"
  models_to_run = @(
    "operational_ml_forecast",
    "pinn_fire_spread",
    "hybrid_ml_pinn",
    "elmfire_benchmark"
  )
  metadata = @{
    title = "Smoke test counterfactual ignition scenario"
    country = "Greece"
    note = "Synthetic ignition point for API smoke testing. Not a scientific run yet."
    validation_policy = "allowed_data_cutoff_time must equal t0 for operational hindcast."
  }
}

$createdScenario = Invoke-RestMethod `
  -Uri "http://localhost:8000/api/scenarios" `
  -Method POST `
  -Body ($scenario | ConvertTo-Json -Depth 20) `
  -ContentType "application/json"

$createdScenario | ConvertTo-Json -Depth 20

Write-Host ""
Write-Host "4. List scenarios" -ForegroundColor Cyan
Invoke-RestMethod -Uri "http://localhost:8000/api/scenarios?limit=10" -Method GET | ConvertTo-Json -Depth 20

Write-Host ""
Write-Host "5. Create sample manual fire observation" -ForegroundColor Cyan

$observation = @{
  source = "manual_test"
  observed_at = "2021-08-03T14:10:00+00:00"
  geometry = @{
    type = "Point"
    coordinates = @(23.7290, 38.2470)
  }
  observation_type = "manual_report"
  confidence = 0.8
  spatial_uncertainty_m = 250
  temporal_uncertainty_s = 300
  payload = @{
    comment = "Synthetic manual report for smoke testing."
  }
}

Invoke-RestMethod `
  -Uri "http://localhost:8000/api/observations" `
  -Method POST `
  -Body ($observation | ConvertTo-Json -Depth 20) `
  -ContentType "application/json" | ConvertTo-Json -Depth 20

Write-Host ""
Write-Host "6. List observations" -ForegroundColor Cyan
Invoke-RestMethod -Uri "http://localhost:8000/api/observations?limit=10" -Method GET | ConvertTo-Json -Depth 20

Write-Host ""
Write-Host "Domain endpoint tests completed." -ForegroundColor Green
