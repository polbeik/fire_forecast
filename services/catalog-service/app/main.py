from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import FastAPI
from fire_common.schemas import HealthResponse

SERVICE_NAME = "catalog-service"
SERVICE_ROLE = "Stores AOIs, events, scenes, assets, scenarios, and metadata."
SERVICE_PORT = 8101

app = FastAPI(
    title=SERVICE_NAME,
    version="0.1.0",
    description=SERVICE_ROLE,
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(service=SERVICE_NAME, status="ok", version="0.1.0")


@app.get("/info")
def info() -> dict:
    return {
        "service": SERVICE_NAME,
        "role": SERVICE_ROLE,
        "port": SERVICE_PORT,
        "environment": os.getenv("ENVIRONMENT", "local"),
        "data_root": os.getenv("DATA_ROOT_DOCKER", "/data"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
