param(
  [int]$WaitSeconds = 60,
  [string[]]$Url = @("http://localhost:8000/health"),
  [switch]$RequireHttp
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

Write-Host "Validating Docker Compose config..."
$ConfigArgs = $ComposeArgs + @("config", "--quiet")
& docker @ConfigArgs
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Docker Compose services:"
$PsArgs = $ComposeArgs + @("ps")
& docker @PsArgs

$PsqArgs = $ComposeArgs + @("ps", "-q")
$ContainerIds = @(& docker @PsqArgs | Where-Object { $_ -and $_.Trim().Length -gt 0 })

if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

if ($ContainerIds.Count -eq 0) {
  Write-Error "No containers found. Run .\scripts\start-local.ps1 first."
  exit 1
}

function Get-ContainerStatus {
  param(
    [string[]]$Ids
  )

  $Format = '{{.Name}}|{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}'
  $InspectArgs = @("inspect", "--format", $Format) + $Ids
  $Lines = @(& docker @InspectArgs)

  foreach ($Line in $Lines) {
    $Parts = $Line -split '\|'
    [pscustomobject]@{
      Name = $Parts[0].TrimStart("/")
      Status = $Parts[1]
      Health = $Parts[2]
    }
  }
}

$Deadline = (Get-Date).AddSeconds($WaitSeconds)

do {
  $Statuses = @(Get-ContainerStatus -Ids $ContainerIds)

  $NotReady = @(
    $Statuses | Where-Object {
      $_.Status -ne "running" -or $_.Health -eq "starting" -or $_.Health -eq "unhealthy"
    }
  )

  if ($NotReady.Count -eq 0) {
    break
  }

  if ((Get-Date) -ge $Deadline) {
    break
  }

  Write-Host ""
  Write-Host "Waiting for containers to become healthy/running..."
  $NotReady | Format-Table -AutoSize
  Start-Sleep -Seconds 2
} while ($true)

$Statuses = @(Get-ContainerStatus -Ids $ContainerIds)

Write-Host ""
Write-Host "Container health:"
$Statuses | Sort-Object Name | Format-Table -AutoSize

$Failed = @(
  $Statuses | Where-Object {
    $_.Status -ne "running" -or $_.Health -eq "starting" -or $_.Health -eq "unhealthy"
  }
)

if ($Failed.Count -gt 0) {
  Write-Error "One or more containers are not ready."
  exit 1
}

$HttpFailures = @()

foreach ($U in $Url) {
  $Ok = $false
  $LastError = $null

  while ((Get-Date) -lt $Deadline) {
    try {
      $Response = Invoke-WebRequest -Uri $U -UseBasicParsing -TimeoutSec 5

      if ($Response.StatusCode -ge 200 -and $Response.StatusCode -lt 400) {
        Write-Host "HTTP OK: $U -> $($Response.StatusCode)"
        $Ok = $true
        break
      }

      $LastError = "Unexpected HTTP status: $($Response.StatusCode)"
    } catch {
      $LastError = $_.Exception.Message
    }

    Start-Sleep -Seconds 2
  }

  if (-not $Ok) {
    Write-Warning "HTTP health check failed: $U -> $LastError"
    $HttpFailures += $U
  }
}

if ($RequireHttp -and $HttpFailures.Count -gt 0) {
  exit 1
}

Write-Host ""
Write-Host "Local stack health check completed."
exit 0
