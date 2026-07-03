from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


ObservationType = Literal[
    "hotspot",
    "smoke",
    "flame",
    "perimeter",
    "manual_report",
    "sensor_alert",
]


ScenarioMode = Literal[
    "real_time_forecast",
    "historical_replay",
    "historical_forecast_replay",
    "counterfactual_ignition",
]


WeatherMode = Literal[
    "live_forecast",
    "archived_forecast",
    "historical_actual",
    "uploaded",
]


ScenarioStatus = Literal[
    "created",
    "queued",
    "running",
    "completed",
    "failed",
]


class HealthResponse(BaseModel):
    service: str
    status: Literal["ok", "degraded", "error"] = "ok"
    version: str = "0.1.0"


class FireObservation(BaseModel):
    source: str
    observed_at: datetime
    received_at: datetime
    geometry: dict[str, Any]
    observation_type: ObservationType
    confidence: float = Field(ge=0.0, le=1.0)
    spatial_uncertainty_m: float | None = None
    temporal_uncertainty_s: float | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class FireObservationCreateRequest(BaseModel):
    source: str
    observed_at: datetime
    received_at: datetime | None = None
    geometry: dict[str, Any]
    observation_type: ObservationType
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    spatial_uncertainty_m: float | None = None
    temporal_uncertainty_s: float | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class FireObservationRecord(FireObservation):
    id: str


class ScenarioCreateRequest(BaseModel):
    id: str | None = None
    mode: ScenarioMode
    ignition_geometry: dict[str, Any]
    start_time_t0: datetime
    horizon_hours: list[int] = Field(default_factory=lambda: [1, 3, 6, 12])
    weather_mode: WeatherMode
    allowed_data_cutoff_time: datetime | None = None
    models_to_run: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScenarioRun(BaseModel):
    id: str
    mode: ScenarioMode
    ignition_geometry: dict[str, Any]
    start_time_t0: datetime
    horizon_hours: list[int]
    weather_mode: WeatherMode
    allowed_data_cutoff_time: datetime
    models_to_run: list[str]
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: ScenarioStatus = "created"
    created_at: datetime


class FlogaInventoryResponse(BaseModel):
    root: str
    root_exists: bool
    recursive: bool
    max_files: int
    total_entries_scanned: int
    total_files_seen: int
    total_dirs_seen: int
    truncated: bool
    top_level_entries: list[str]
    extension_counts: dict[str, int]
    sample_files: list[str]
    h5_candidates: list[str]
    notes: list[str]
