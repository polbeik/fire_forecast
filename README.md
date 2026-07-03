# Fire Forecast
Microservice platform for spatio-temporal wildfire segmentation, operational hindcasting, counterfactual fire scenarios, and fire-spread model comparison.

Core modes:
- Burned-area segmentation on FLOGA.
- Operational hindcast using archived forecast weather where available.
- Historical actual-weather replay.
- Counterfactual ignition scenarios.
- ML / PINN / Hybrid / physics-simulator comparison.

Local runtime:
- API Gateway: http://localhost:8000
- Catalog service: http://localhost:8101
- Ingestion service: http://localhost:8102
- Preprocessing service: http://localhost:8103
- Segmentation service: http://localhost:8104
- Forecasting service: http://localhost:8105
- PINN service: http://localhost:8106
- Simulation adapter service: http://localhost:8107
- Visualization service: http://localhost:8108
- Plugin adapter service: http://localhost:8109
- NATS monitor: http://localhost:8222
- MinIO console: http://localhost:9001
- Prefect server: http://localhost:4202

## Local Docker Workflow

The local Fire Forecast stack is managed through PowerShell helper scripts under scripts/.

### Start the stack

    .\scripts\start-local.ps1

For a faster restart without rebuilding images:

    .\scripts\start-local.ps1 -NoBuild

### Check stack health

    .\scripts\health-local.ps1 -RequireHttp

This validates the Compose configuration, checks container status, and verifies that the API Gateway responds at:

    http://localhost:8000/health

### Show running services

    .\scripts\ps-local.ps1

### View logs

Show recent logs without following:

    .\scripts\logs-local.ps1 -NoFollow

Follow logs:

    .\scripts\logs-local.ps1

Show logs for one service:

    .\scripts\logs-local.ps1 -Service api-gateway -NoFollow

### Validate Compose configuration

    .\scripts\compose-config.ps1 -Quiet

### Stop the stack

    .\scripts\stop-local.ps1

To stop the stack and remove volumes:

    .\scripts\stop-local.ps1 -Volumes

### Current checkpoint tags

    runtime-baseline-2026-07-03
    helper-scripts-2026-07-03

runtime-baseline-2026-07-03 marks the stable Docker runtime baseline before helper scripts.

helper-scripts-2026-07-03 marks the validated helper-script workflow.

<!-- LOCAL_DOCKER_WORKFLOW_START -->

## Local Docker workflow

The local Docker stack is designed to be started from the repository root.

### Recommended startup

Use the helper scripts:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\run-local.ps1
.\scripts\health-local.ps1
```

To stop the local stack:

```powershell
.\scripts\stop-local.ps1
```

### Equivalent explicit Docker Compose invocation

If the helper scripts are not used, Docker Compose must be called explicitly with the compose file path:

```powershell
docker compose --env-file .env -f infra/docker/docker-compose.yml up -d --build
docker compose --env-file .env -f infra/docker/docker-compose.yml ps
```

To stop the stack explicitly:

```powershell
docker compose --env-file .env -f infra/docker/docker-compose.yml down
```

### Important

Do not start the project with bare Docker Compose:

```powershell
docker compose up
```

Bare `docker compose up` depends on Compose discovering a compose file in the current directory. In this project, the local Compose file lives under `infra/docker/docker-compose.yml`, so the supported local workflow is either:

1. `.\scripts\run-local.ps1`, `.\scripts\health-local.ps1`, `.\scripts\stop-local.ps1`
2. Explicit Compose commands using `-f infra/docker/docker-compose.yml`

This avoids accidentally starting an incomplete or wrong local stack.

<!-- LOCAL_DOCKER_WORKFLOW_END -->

