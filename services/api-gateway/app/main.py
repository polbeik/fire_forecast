from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query, Request

from fire_common.schemas import HealthResponse

SERVICE_NAME = "api-gateway"

CATALOG_URL = "http://catalog-service:8101"

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


async def _get_json(url: str, params: dict[str, Any] | None = None) -> Any:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, params=params)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


async def _post_json(url: str, payload: dict[str, Any]) -> Any:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


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


@app.get("/api/floga/inventory")
async def api_floga_inventory(
    max_files: int = Query(default=5000, ge=1, le=200000),
    recursive: bool = Query(default=False),
) -> Any:
    return await _get_json(
        f"{CATALOG_URL}/floga/inventory",
        params={
            "max_files": max_files,
            "recursive": recursive,
        },
    )


@app.post("/api/scenarios")
async def api_create_scenario(request: Request) -> Any:
    payload = await request.json()
    return await _post_json(f"{CATALOG_URL}/scenarios", payload)


@app.get("/api/scenarios")
async def api_list_scenarios(limit: int = Query(default=100, ge=1, le=10000)) -> Any:
    return await _get_json(f"{CATALOG_URL}/scenarios", params={"limit": limit})


@app.get("/api/scenarios/{scenario_id}")
async def api_get_scenario(scenario_id: str) -> Any:
    return await _get_json(f"{CATALOG_URL}/scenarios/{scenario_id}")


@app.post("/api/observations")
async def api_create_observation(request: Request) -> Any:
    payload = await request.json()
    return await _post_json(f"{CATALOG_URL}/observations", payload)


@app.get("/api/observations")
async def api_list_observations(limit: int = Query(default=100, ge=1, le=10000)) -> Any:
    return await _get_json(f"{CATALOG_URL}/observations", params={"limit": limit})
