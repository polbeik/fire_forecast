from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query

from fire_common.schemas import (
    FireObservationCreateRequest,
    FireObservationRecord,
    FlogaInventoryResponse,
    HealthResponse,
    ScenarioCreateRequest,
    ScenarioRun,
)

SERVICE_NAME = "catalog-service"
SERVICE_ROLE = "Stores AOIs, events, scenes, assets, scenarios, observations, and metadata."
SERVICE_PORT = 8101

APP_DATA_ROOT = Path(os.getenv("APP_DATA_ROOT", "/data"))
APP_FLOGA_ROOT = Path(os.getenv("APP_FLOGA_ROOT", str(APP_DATA_ROOT / "floga")))
APP_PROCESSED_ROOT = Path(os.getenv("APP_PROCESSED_DATA_ROOT", str(APP_DATA_ROOT / "processed")))

CATALOG_STORE_DIR = APP_PROCESSED_ROOT / "catalog_store"
SCENARIOS_PATH = CATALOG_STORE_DIR / "scenario_runs.jsonl"
OBSERVATIONS_PATH = CATALOG_STORE_DIR / "fire_observations.jsonl"

app = FastAPI(
    title=SERVICE_NAME,
    version="0.1.0",
    description=SERVICE_ROLE,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_store() -> None:
    CATALOG_STORE_DIR.mkdir(parents=True, exist_ok=True)


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    _ensure_store()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(service=SERVICE_NAME, status="ok", version="0.1.0")


@app.get("/info")
def info() -> dict[str, Any]:
    return {
        "service": SERVICE_NAME,
        "role": SERVICE_ROLE,
        "port": SERVICE_PORT,
        "environment": os.getenv("ENVIRONMENT", "local"),
        "app_data_root": str(APP_DATA_ROOT),
        "app_floga_root": str(APP_FLOGA_ROOT),
        "catalog_store_dir": str(CATALOG_STORE_DIR),
        "timestamp": _utc_now().isoformat(),
    }


@app.get("/floga/inventory", response_model=FlogaInventoryResponse)
def floga_inventory(
    max_files: int = Query(default=5000, ge=1, le=200000),
    recursive: bool = Query(default=False),
) -> FlogaInventoryResponse:
    notes: list[str] = [
        "This endpoint is read-only.",
        "It does not modify, delete, move, or preprocess FLOGA data.",
        "Use recursive=true only when a deeper scan is needed.",
    ]

    if not APP_FLOGA_ROOT.exists():
        return FlogaInventoryResponse(
            root=str(APP_FLOGA_ROOT),
            root_exists=False,
            recursive=recursive,
            max_files=max_files,
            total_entries_scanned=0,
            total_files_seen=0,
            total_dirs_seen=0,
            truncated=False,
            top_level_entries=[],
            extension_counts={},
            sample_files=[],
            h5_candidates=[],
            notes=notes + ["FLOGA root does not exist inside the container."],
        )

    top_level_entries: list[str] = []
    for item in list(APP_FLOGA_ROOT.iterdir())[:100]:
        top_level_entries.append(item.name)

    extension_counts: Counter[str] = Counter()
    sample_files: list[str] = []
    h5_candidates: list[str] = []

    total_entries_scanned = 0
    total_files_seen = 0
    total_dirs_seen = 0
    truncated = False

    iterator = APP_FLOGA_ROOT.rglob("*") if recursive else APP_FLOGA_ROOT.iterdir()

    for item in iterator:
        total_entries_scanned += 1

        if item.is_dir():
            total_dirs_seen += 1
        elif item.is_file():
            total_files_seen += 1
            ext = item.suffix.lower() or "<no_extension>"
            extension_counts[ext] += 1

            try:
                rel = str(item.relative_to(APP_FLOGA_ROOT))
            except ValueError:
                rel = str(item)

            if len(sample_files) < 50:
                sample_files.append(rel)

            if ext in {".h5", ".hdf5"} and len(h5_candidates) < 50:
                h5_candidates.append(rel)

        if total_entries_scanned >= max_files:
            truncated = True
            break

    if recursive and truncated:
        notes.append("Recursive scan was truncated by max_files.")
    elif not recursive:
        notes.append("Non-recursive scan only inspected top-level FLOGA entries.")

    return FlogaInventoryResponse(
        root=str(APP_FLOGA_ROOT),
        root_exists=True,
        recursive=recursive,
        max_files=max_files,
        total_entries_scanned=total_entries_scanned,
        total_files_seen=total_files_seen,
        total_dirs_seen=total_dirs_seen,
        truncated=truncated,
        top_level_entries=top_level_entries,
        extension_counts=dict(extension_counts),
        sample_files=sample_files,
        h5_candidates=h5_candidates,
        notes=notes,
    )


@app.post("/scenarios", response_model=ScenarioRun)
def create_scenario(request: ScenarioCreateRequest) -> ScenarioRun:
    scenario_id = request.id or f"scenario-{uuid4().hex[:12]}"
    allowed_cutoff = request.allowed_data_cutoff_time or request.start_time_t0

    scenario = ScenarioRun(
        id=scenario_id,
        mode=request.mode,
        ignition_geometry=request.ignition_geometry,
        start_time_t0=request.start_time_t0,
        horizon_hours=request.horizon_hours,
        weather_mode=request.weather_mode,
        allowed_data_cutoff_time=allowed_cutoff,
        models_to_run=request.models_to_run,
        metadata=request.metadata,
        status="created",
        created_at=_utc_now(),
    )

    _append_jsonl(SCENARIOS_PATH, scenario.model_dump(mode="json"))
    return scenario


@app.get("/scenarios")
def list_scenarios(limit: int = Query(default=100, ge=1, le=10000)) -> dict[str, Any]:
    records = _read_jsonl(SCENARIOS_PATH)
    return {
        "count": len(records),
        "items": records[-limit:],
    }


@app.get("/scenarios/{scenario_id}")
def get_scenario(scenario_id: str) -> dict[str, Any]:
    records = _read_jsonl(SCENARIOS_PATH)
    for record in reversed(records):
        if record.get("id") == scenario_id:
            return record

    raise HTTPException(status_code=404, detail=f"Scenario not found: {scenario_id}")


@app.post("/observations", response_model=FireObservationRecord)
def create_observation(request: FireObservationCreateRequest) -> FireObservationRecord:
    observation = FireObservationRecord(
        id=f"observation-{uuid4().hex[:12]}",
        source=request.source,
        observed_at=request.observed_at,
        received_at=request.received_at or _utc_now(),
        geometry=request.geometry,
        observation_type=request.observation_type,
        confidence=request.confidence,
        spatial_uncertainty_m=request.spatial_uncertainty_m,
        temporal_uncertainty_s=request.temporal_uncertainty_s,
        payload=request.payload,
    )

    _append_jsonl(OBSERVATIONS_PATH, observation.model_dump(mode="json"))
    return observation


@app.get("/observations")
def list_observations(limit: int = Query(default=100, ge=1, le=10000)) -> dict[str, Any]:
    records = _read_jsonl(OBSERVATIONS_PATH)
    return {
        "count": len(records),
        "items": records[-limit:],
    }

from app.operational_evaluation_policy import router as operational_evaluation_policy_router
app.include_router(operational_evaluation_policy_router)
