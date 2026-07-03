param(
  [double]$Latitude = 38.2466,
  [double]$Longitude = 23.7275,
  [string[]]$Dates = @(
    "2017-08-03",
    "2018-08-03",
    "2019-08-03",
    "2020-08-03",
    "2021-08-03"
  ),
  [string[]]$Models = @(
    "gfs_global",
    "ecmwf_ifs025"
  )
)

$ErrorActionPreference = "Stop"

$Hourly = "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,wind_gusts_10m,precipitation,cloud_cover"
$BaseUrl = "https://historical-forecast-api.open-meteo.com/v1/forecast"

function Get-NonNullRatio {
  param(
    [object]$HourlyData,
    [string[]]$RequiredVariables
  )

  $total = 0
  $nonNull = 0

  foreach ($var in $RequiredVariables) {
    $values = $HourlyData.$var
    if ($null -eq $values) {
      continue
    }

    foreach ($v in $values) {
      $total += 1
      if ($null -ne $v) {
        $nonNull += 1
      }
    }
  }

  if ($total -eq 0) {
    return 0
  }

  return [math]::Round($nonNull / $total, 4)
}

$Required = @(
  "temperature_2m",
  "relative_humidity_2m",
  "wind_speed_10m",
  "wind_direction_10m",
  "wind_gusts_10m",
  "precipitation",
  "cloud_cover"
)

$results = @()

foreach ($date in $Dates) {
  foreach ($model in $Models) {
    $url = "$BaseUrl" +
      "?latitude=$Latitude" +
      "&longitude=$Longitude" +
      "&start_date=$date" +
      "&end_date=$date" +
      "&hourly=$Hourly" +
      "&timezone=UTC" +
      "&models=$model"

    Write-Host "Checking $date / $model ..." -ForegroundColor Cyan

    try {
      $response = Invoke-RestMethod -Uri $url -Method GET
      $ratio = Get-NonNullRatio -HourlyData $response.hourly -RequiredVariables $Required
      $eligible = $ratio -ge 0.95

      $results += [pscustomobject]@{
        date = $date
        model = $model
        http_status = 200
        non_null_ratio = $ratio
        eligible = $eligible
        latitude_returned = $response.latitude
        longitude_returned = $response.longitude
        timezone = $response.timezone
      }
    }
    catch {
      $results += [pscustomobject]@{
        date = $date
        model = $model
        http_status = "error"
        non_null_ratio = 0
        eligible = $false
        latitude_returned = $null
        longitude_returned = $null
        timezone = $null
      }
    }
  }
}

$results | Format-Table -AutoSize

$outDir = "outputs\weather-availability"
New-Item -ItemType Directory -Path $outDir -Force | Out-Null

$outFile = Join-Path $outDir "openmeteo_historical_forecast_availability.csv"
$results | Export-Csv -Path $outFile -NoTypeInformation -Encoding UTF8

Write-Host "`nWrote $outFile" -ForegroundColor Green
