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

<!-- OPERATIONAL_EVALUATION_DATA_POLICY_START -->

## Operational evaluation data policy

Fire Forecast separates retrospective experimentation from operationally valid evaluation.

For any result described as operational, near-real-time, deployable, or decision-support evaluation, the weather input must have been available as archived forecast weather for the target event time. Historical actuals, reanalysis, corrected observations, and any fallback derived from post-event knowledge are not valid inputs for operational evaluation.

Current operational evaluation candidate set:

- Dataset: FLOGA 2021
- Candidate events: determined dynamically from the unique 2021 event IDs in `data_split.csv`
- Split membership fields: `year`, `event_id`, and `set`
- Operational weather eligibility: determined separately from an explicit per-event archived-forecast coverage manifest
- Required eligibility evidence: archived-forecast coverage confirmation, weather source type, provider, model, and forecast/model run reference time
- Current target weather source: Open-Meteo Historical Forecast API, model `gfs_global`
- Events without explicit eligibility evidence remain ineligible by default

Policy rules:

1. Operational evaluation requires `archived_forecast` weather.
2. Archived-forecast coverage must be explicitly confirmed for each event.
3. Weather provider, model, and forecast/model run reference time are mandatory.
4. `historical_actual`, reanalysis, observation-derived, and post-event fallback weather are forbidden for operational evaluation.
5. Data from those retrospective sources may be used only for diagnostic or retrospective experiments and must not be reported as operational evaluation.
6. Candidate-event counts and eligible-event counts must be calculated from the mounted data and eligibility manifest; they must not be hard-coded.

This policy is enforced by catalog-service validation and exposed through ingestion-service FLOGA 2021 inventory endpoints.

<!-- OPERATIONAL_EVALUATION_DATA_POLICY_END -->
