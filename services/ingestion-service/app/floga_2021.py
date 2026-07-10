from __future__ import annotations

import csv
import os
from collections import Counter
from pathlib import Path
from typing import Any

from fastapi import APIRouter


router = APIRouter(tags=["floga-2021"])

POLICY_VERSION = "operational-evaluation-data-policy-2026-07-10"

VALID_SPLITS = {
    "train",
    "training",
    "val",
    "valid",
    "validation",
    "test",
}

COVERAGE_FIELDS = [
    "archived_forecast_coverage_valid",
    "weather_coverage_valid",
    "valid_weather_coverage",
    "coverage_valid",
    "weather_eligible",
    "operational_weather_eligible",
]

RUN_REFERENCE_FIELDS = [
    "forecast_issue_time_utc",
    "model_run_utc",
    "model_initialization_time_utc",
    "run_reference_time_utc",
    "forecast_reference_time_utc",
]


def _candidate_roots() -> list[Path]:
    roots: list[Path] = []

    for env_name in [
        "FLOGA_SPLIT_CSV",
        "FLOGA_WEATHER_ELIGIBILITY_CSV",
        "APP_FLOGA_ROOT",
        "FLOGA_DATA_ROOT",
        "FLOGA_ROOT",
        "APP_DATA_ROOT",
        "DATA_ROOT",
    ]:
        value = os.getenv(env_name)
        if value:
            roots.append(Path(value))

    here = Path(__file__).resolve()

    roots.extend(
        [
            Path.cwd(),
            here.parent,
            here.parent.parent,
            here.parent.parent.parent,
            Path("/data"),
            Path("/data/floga"),
            Path("/app/data"),
            Path("/app"),
        ]
    )

    unique: list[Path] = []
    seen: set[str] = set()

    for root in roots:
        key = str(root)
        if key not in seen:
            unique.append(root)
            seen.add(key)

    return unique


def _find_split_csv() -> Path | None:
    explicit = os.getenv("FLOGA_SPLIT_CSV")
    if explicit:
        path = Path(explicit)
        if path.exists() and path.is_file():
            return path

    for root in _candidate_roots():
        if root.is_file() and root.name.lower() == "data_split.csv":
            return root

        candidates = [
            root / "data_split.csv",
            root / "data splits" / "data_split.csv",
            root / "data_splits" / "data_split.csv",
            root / "splits" / "data_split.csv",
            root / "data" / "data_split.csv",
            root / "data" / "data splits" / "data_split.csv",
            root / "data" / "splits" / "data_split.csv",
        ]

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate

    return None


def _find_eligibility_csv() -> Path | None:
    explicit = os.getenv("FLOGA_WEATHER_ELIGIBILITY_CSV")
    if explicit:
        path = Path(explicit)
        if path.exists() and path.is_file():
            return path

    relative_candidates = [
        Path("floga_2021_weather_eligibility.csv"),
        Path("weather_eligibility_2021.csv"),
        Path("operational_weather_eligibility_2021.csv"),
        Path("manifests") / "floga_2021_weather_eligibility.csv",
        Path("metadata") / "floga_2021_weather_eligibility.csv",
    ]

    for root in _candidate_roots():
        if root.is_file() and "eligibility" in root.name.lower():
            return root

        for relative in relative_candidates:
            candidate = root / relative
            if candidate.exists() and candidate.is_file():
                return candidate

    return None


def _normalise_key(key: str) -> str:
    return key.strip().lower().replace(" ", "_").replace("-", "_")


def _first_existing(row: dict[str, Any], names: list[str]) -> Any:
    for name in names:
        value = row.get(name)
        if value not in {None, ""}:
            return value
    return None


def _read_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [
            {_normalise_key(key): value for key, value in raw.items() if key is not None}
            for raw in reader
        ]


def _event_id(row: dict[str, Any]) -> str | None:
    value = _first_existing(
        row,
        [
            "event_id",
            "event",
            "fire_event_id",
            "fire_id",
            "id",
            "fid",
            "floga_event_id",
        ],
    )
    return None if value is None else str(value).strip()


def _year(row: dict[str, Any]) -> str | None:
    value = _first_existing(
        row,
        ["year", "event_year", "fire_year", "reference_year", "dataset_year"],
    )
    return None if value is None else str(value).strip()


def _split(row: dict[str, Any]) -> str | None:
    value = _first_existing(
        row,
        ["split", "data_split", "set", "subset", "partition", "dataset_split"],
    )
    return None if value is None else str(value).strip()


def _truthy(value: Any) -> bool | None:
    if value is None:
        return None

    lowered = str(value).strip().lower()

    if lowered in {"1", "true", "yes", "y", "valid", "eligible", "covered", "confirmed"}:
        return True

    if lowered in {"0", "false", "no", "n", "invalid", "ineligible", "missing", "none"}:
        return False

    return None


def _normalise_source_type(value: Any) -> str:
    return "" if value is None else str(value).strip().lower()


def _manifest_record(row: dict[str, Any]) -> dict[str, Any] | None:
    event_id = _event_id(row)
    if not event_id:
        return None

    row_year = _year(row)
    if row_year and row_year != "2021":
        return None

    coverage = _truthy(_first_existing(row, COVERAGE_FIELDS))
    source_type = _normalise_source_type(
        _first_existing(
            row,
            ["weather_source_type", "source_type", "weather_source", "data_source"],
        )
    )
    provider = _first_existing(row, ["provider", "weather_provider", "source_provider"])
    model = _first_existing(row, ["model", "model_name", "weather_model"])
    run_reference = _first_existing(row, RUN_REFERENCE_FIELDS)

    provider_text = None if provider is None else str(provider).strip()
    model_text = None if model is None else str(model).strip()
    run_reference_text = None if run_reference is None else str(run_reference).strip()

    archived_source = source_type in {
        "archived_forecast",
        "historical_forecast",
        "forecast_archive",
    }

    exclusion_reasons: list[str] = []

    if coverage is None:
        exclusion_reasons.append(
            "archived_forecast_weather_coverage_not_explicitly_confirmed"
        )
    elif coverage is False:
        exclusion_reasons.append("archived_forecast_weather_coverage_not_valid")

    if not archived_source:
        exclusion_reasons.append("weather_source_is_not_archived_forecast")
    if not provider_text:
        exclusion_reasons.append("missing_weather_provider")
    if not model_text:
        exclusion_reasons.append("missing_weather_model")
    if not run_reference_text:
        exclusion_reasons.append("missing_forecast_run_reference_time")

    return {
        "event_id": event_id,
        "weather_source_type": source_type,
        "weather_provider": provider_text,
        "weather_model": model_text,
        "forecast_run_reference_time_utc": run_reference_text,
        "archived_forecast_coverage_valid": coverage is True,
        "weather_eligible": len(exclusion_reasons) == 0,
        "exclusion_reasons": exclusion_reasons,
    }


def _load_manifest(
    path: Path | None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    if path is None:
        return {}, [
            "No FLOGA 2021 weather eligibility manifest was found. "
            "Candidate events remain ineligible until archived-forecast coverage "
            "and required model metadata are explicitly recorded."
        ]

    records: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []

    for row in _read_rows(path):
        record = _manifest_record(row)
        if record is None:
            continue

        event_id = record["event_id"]
        if event_id in records:
            warnings.append(
                f"Duplicate weather eligibility manifest entry for event_id={event_id}; "
                "the last row was used."
            )
        records[event_id] = record

    return records, warnings


def _load_candidates(
    split_csv: Path,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    candidates: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []

    for row in _read_rows(split_csv):
        if _year(row) != "2021":
            continue

        event_id = _event_id(row)
        if not event_id:
            warnings.append("Ignored a FLOGA 2021 split row with a missing event_id.")
            continue

        split = _split(row)
        split_normalised = "" if split is None else split.strip().lower()
        split_valid = split_normalised in VALID_SPLITS

        if event_id in candidates:
            previous_split = candidates[event_id]["split"]
            warnings.append(
                f"Duplicate FLOGA 2021 split entry for event_id={event_id}; "
                f"kept split={previous_split!r} and ignored split={split!r}."
            )
            continue

        candidates[event_id] = {
            "event_id": event_id,
            "year": 2021,
            "split": split,
            "valid_split_membership": split_valid,
        }

    return candidates, warnings


def _load_events() -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    split_csv = _find_split_csv()
    eligibility_csv = _find_eligibility_csv()

    if split_csv is None:
        return [], {
            "split_csv": None,
            "split_csv_found": False,
            "weather_eligibility_csv": (
                None if eligibility_csv is None else str(eligibility_csv)
            ),
            "weather_eligibility_csv_found": eligibility_csv is not None,
        }, [
            "No local data_split.csv was found. Set FLOGA_SPLIT_CSV or expose "
            "the FLOGA data root through APP_FLOGA_ROOT/FLOGA_ROOT."
        ]

    candidates, candidate_warnings = _load_candidates(split_csv)
    manifest, manifest_warnings = _load_manifest(eligibility_csv)

    warnings = candidate_warnings + manifest_warnings
    events: list[dict[str, Any]] = []

    for event_id, candidate in candidates.items():
        split_valid = candidate["valid_split_membership"]
        manifest_record = manifest.get(event_id)

        if manifest_record is None:
            event = {
                **candidate,
                "weather_source_type": None,
                "weather_provider": None,
                "weather_model": None,
                "forecast_run_reference_time_utc": None,
                "archived_forecast_coverage_valid": False,
                "weather_eligible": False,
                "exclusion_reasons": (
                    ([] if split_valid else ["missing_or_invalid_split_membership"])
                    + ["weather_eligibility_manifest_entry_missing"]
                ),
            }
        else:
            exclusion_reasons = (
                [] if split_valid else ["missing_or_invalid_split_membership"]
            )
            exclusion_reasons.extend(manifest_record["exclusion_reasons"])

            event = {
                **candidate,
                **{
                    key: value
                    for key, value in manifest_record.items()
                    if key != "event_id"
                },
                "weather_eligible": (
                    split_valid and manifest_record["weather_eligible"]
                ),
                "exclusion_reasons": list(dict.fromkeys(exclusion_reasons)),
            }

        events.append(event)

    unmatched_manifest_ids = sorted(set(manifest) - set(candidates))
    if unmatched_manifest_ids:
        warnings.append(
            f"{len(unmatched_manifest_ids)} manifest event IDs were not found in the "
            "FLOGA 2021 candidate set."
        )

    events.sort(key=lambda item: item["event_id"])

    return events, {
        "split_csv": str(split_csv),
        "split_csv_found": True,
        "weather_eligibility_csv": (
            None if eligibility_csv is None else str(eligibility_csv)
        ),
        "weather_eligibility_csv_found": eligibility_csv is not None,
        "manifest_records_loaded": len(manifest),
        "manifest_records_matching_candidates": len(set(manifest) & set(candidates)),
    }, warnings


def _summary(
    events: list[dict[str, Any]],
    source_info: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    candidates = [
        event for event in events if event.get("valid_split_membership") is True
    ]
    eligible_events = [
        event for event in events if event.get("weather_eligible") is True
    ]

    split_distribution = Counter(
        str(event.get("split") or "missing") for event in candidates
    )

    return {
        "policy_version": POLICY_VERSION,
        "dataset": "FLOGA",
        "year": 2021,
        "candidate_count_mode": "dynamic_unique_event_ids",
        "actual_candidate_events_loaded": len(candidates),
        "confirmed_weather_eligible_events": len(eligible_events),
        "split_distribution": dict(sorted(split_distribution.items())),
        "eligibility_rule": (
            "Explicit archived-forecast coverage, weather source type, provider, "
            "model, and forecast/model run reference time are required."
        ),
        "source_info": source_info,
        "warnings": warnings,
    }


@router.get("/floga/2021/events")
def list_floga_2021_events() -> dict[str, Any]:
    events, source_info, warnings = _load_events()

    return {
        **_summary(events, source_info, warnings),
        "events": events,
    }


@router.get("/floga/2021/weather-eligible-events")
def list_floga_2021_weather_eligible_events() -> dict[str, Any]:
    events, source_info, warnings = _load_events()
    eligible_events = [
        event for event in events if event.get("weather_eligible") is True
    ]

    return {
        **_summary(events, source_info, warnings),
        "events": eligible_events,
    }


@router.get("/floga/2021/weather-eligibility-manifest-schema")
def get_weather_eligibility_manifest_schema() -> dict[str, Any]:
    return {
        "format": "CSV",
        "recommended_location": (
            "${APP_FLOGA_ROOT}/manifests/floga_2021_weather_eligibility.csv"
        ),
        "environment_override": "FLOGA_WEATHER_ELIGIBILITY_CSV",
        "required_columns": [
            "year",
            "event_id",
            "archived_forecast_coverage_valid",
            "weather_source_type",
            "provider",
            "model",
            "forecast_reference_time_utc",
        ],
        "optional_columns": [
            "coverage_checked_at_utc",
            "coverage_start_utc",
            "coverage_end_utc",
            "notes",
        ],
        "example": {
            "year": 2021,
            "event_id": "example-event-id",
            "archived_forecast_coverage_valid": True,
            "weather_source_type": "archived_forecast",
            "provider": "Open-Meteo Historical Forecast API",
            "model": "gfs_global",
            "forecast_reference_time_utc": "2021-08-01T00:00:00Z",
        },
    }
