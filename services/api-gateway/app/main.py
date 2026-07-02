from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI
from fire_common.schemas import HealthResponse

SERVICE_NAME = "api-gateway"

SERVICES = {
    "catalog-service": "http://catalog-service:8101/health",
    "ingestion-service": "http://ingestion-service:8102/health",
    "preprocessing-service": "http://preprocessing-service:8103/health",
    "segmentation-service": "http://segmentation-service:8104/health",
    "forecasting-service": "http://forecasting-service:8105/health",
    "pinn-service": "http://pinn-service:8106/health",
    "simulation-adapter-service": "http://simulation-adapter-service:8107/health",
    "visualization-service": "http://visualization-service:8108/health",
    "plugin-adapter-service": "http://plugin-adapter-service:8109/health",
}

app = FastAPI(
    title="Fire Forecast API Gateway",
    version="0.1.0",
    description="Entry point for wildfire segmentation, hindcasting, forecasting, and scenario simulation.",
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(service=SERVICE_NAME, status="ok", version="0.1.0")


@app.get("/api/system/health")
async def system_health() -> dict[str, Any]:
    results: dict[str, Any] = {}

    async with httpx.AsyncClient(timeout=3.0) as client:
        for service_name, url in SERVICES.items():
            try:
                response = await client.get(url)
                results[service_name] = {
                    "status_code": response.status_code,
                    "body": response.json(),
                }
            except Exception as exc:
                results[service_name] = {
                    "status_code": None,
                    "error": str(exc),
                }

    overall = "ok" if all(item.get("status_code") == 200 for item in results.values()) else "degraded"

    return {
        "service": SERVICE_NAME,
        "overall": overall,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "services": results,
    }


@app.get("/api/modes")
def modes() -> dict[str, Any]:
    return {
        "scenario_modes": [
            "real_time_forecast",
            "historical_replay",
            "historical_forecast_replay",
            "counterfactual_ignition",
        ],
        "weather_modes": [
            "live_forecast",
            "archived_forecast",
            "historical_actual",
            "uploaded",
        ],
        "model_families": [
            "burned_area_segmentation",
            "operational_ml_forecast",
            "pinn_fire_spread",
            "hybrid_ml_pinn",
            "elmfire_benchmark",
            "gridfire_benchmark",
            "wrf_sfire_selected_benchmark",
            "farsite_flammap_selected_benchmark",
        ],
    }
