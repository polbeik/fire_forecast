from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException


router = APIRouter(tags=["operational-evaluation-policy"])

POLICY_VERSION = "operational-evaluation-data-policy-2026-07-10"

HISTORICAL_ACTUAL_SOURCES = {
    "historical_actual",
    "historical",
    "actual",
    "observed",
    "observation",
    "observations",
    "reanalysis",
    "era5",
    "era5_land",
}

ARCHIVED_FORECAST_SOURCES = {
    "archived_forecast",
    "historical_forecast",
    "forecast_archive",
}

OPERATIONAL_MODES = {
    "operational",
    "operational_evaluation",
    "decision_support",
    "near_real_time",
    "near-real-time",
}


def _lower(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _get_nested(payload: dict[str, Any], *path: str) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _first(payload: dict[str, Any], names: list[str]) -> Any:
    for name in names:
        if name in payload:
            return payload.get(name)
    return None


def _weather_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        payload.get("weather_model_metadata"),
        payload.get("weather_metadata"),
        payload.get("weather"),
        _get_nested(payload, "inputs", "weather"),
        _get_nested(payload, "evaluation_inputs", "weather"),
    ]

    for candidate in candidates:
        if isinstance(candidate, dict):
            return candidate

    return {}


def _is_operational(payload: dict[str, Any]) -> bool:
    if payload.get("is_operational_evaluation") is True:
        return True

    mode = _lower(
        _first(
            payload,
            [
                "evaluation_mode",
                "mode",
                "scenario_mode",
                "scenario_type",
                "run_mode",
            ],
        )
    )

    return mode in OPERATIONAL_MODES


def _weather_source(payload: dict[str, Any]) -> str:
    direct = _first(
        payload,
        [
            "weather_source_type",
            "weather_source",
            "weather_data_source",
            "weather_dataset_type",
        ],
    )
    if direct is not None:
        return _lower(direct)

    metadata = _weather_metadata(payload)

    nested = (
        metadata.get("source_type")
        or metadata.get("source")
        or metadata.get("data_source")
        or metadata.get("dataset_type")
    )

    return _lower(nested)


def _fallback_source(payload: dict[str, Any]) -> str:
    fallback = _first(
        payload,
        [
            "fallback_source",
            "fallback_weather_source",
            "weather_fallback",
            "fallback_strategy",
        ],
    )
    if fallback is not None:
        return _lower(fallback)

    metadata = _weather_metadata(payload)

    return _lower(
        metadata.get("fallback_source")
        or metadata.get("fallback")
        or metadata.get("fallback_strategy")
    )


def _coverage_valid(payload: dict[str, Any]) -> bool:
    candidates = [
        payload.get("weather_coverage_valid"),
        payload.get("valid_weather_coverage"),
        payload.get("archived_forecast_coverage_valid"),
        payload.get("coverage_valid"),
        _get_nested(payload, "weather", "coverage_valid"),
        _get_nested(payload, "weather", "coverage", "valid"),
        _get_nested(payload, "inputs", "weather", "coverage_valid"),
        _get_nested(payload, "evaluation_inputs", "weather", "coverage_valid"),
    ]

    for candidate in candidates:
        if candidate is True:
            return True

    status = _lower(
        payload.get("weather_coverage_status")
        or payload.get("coverage_status")
        or _get_nested(payload, "weather", "coverage_status")
        or _get_nested(payload, "weather", "coverage", "status")
    )

    return status in {"valid", "confirmed", "eligible", "covered"}


def _metadata_errors(metadata: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    provider = metadata.get("provider") or metadata.get("source_provider")
    model = metadata.get("model") or metadata.get("model_name") or metadata.get("weather_model")

    run_reference = (
        metadata.get("forecast_issue_time_utc")
        or metadata.get("model_run_utc")
        or metadata.get("model_initialization_time_utc")
        or metadata.get("run_reference_time_utc")
        or metadata.get("forecast_reference_time_utc")
    )

    if not provider:
        errors.append("Missing weather model metadata field: provider.")
    if not model:
        errors.append("Missing weather model metadata field: model/model_name.")
    if not run_reference:
        errors.append(
            "Missing weather model metadata field: forecast_issue_time_utc, "
            "model_run_utc, model_initialization_time_utc, run_reference_time_utc, "
            "or forecast_reference_time_utc."
        )

    return errors


def validate_operational_evaluation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    is_operational = _is_operational(payload)
    weather_source = _weather_source(payload)
    fallback_source = _fallback_source(payload)
    metadata = _weather_metadata(payload)

    if is_operational:
        if weather_source in HISTORICAL_ACTUAL_SOURCES:
            errors.append(
                "Operational evaluation cannot use historical_actual, observed, "
                "reanalysis, ERA5, or post-event weather sources."
            )

        if fallback_source in HISTORICAL_ACTUAL_SOURCES:
            errors.append(
                "Operational evaluation cannot use historical_actual fallback weather."
            )

        if fallback_source and fallback_source not in {"none", "disabled", "no_fallback"}:
            errors.append(
                f"Operational evaluation declares non-disabled fallback strategy "
                f"'{fallback_source}'."
            )

        if weather_source in ARCHIVED_FORECAST_SOURCES:
            if not _coverage_valid(payload):
                errors.append(
                    "Operational archived_forecast scenarios require explicitly valid "
                    "weather coverage before evaluation."
                )

            errors.extend(_metadata_errors(metadata))
        else:
            errors.append(
                "Operational evaluation requires weather_source_type='archived_forecast'."
            )

    return {
        "valid": len(errors) == 0,
        "policy_version": POLICY_VERSION,
        "is_operational_evaluation": is_operational,
        "weather_source_type": weather_source,
        "fallback_source": fallback_source,
        "errors": errors,
        "warnings": warnings,
    }


@router.get("/evaluation-policy/operational")
def get_operational_evaluation_policy() -> dict[str, Any]:
    return {
        "policy_version": POLICY_VERSION,
        "candidate_subset": {
            "dataset": "FLOGA",
            "year": 2021,
            "count_source": "unique 2021 event IDs in data_split.csv",
            "count_mode": "dynamic",
        },
        "weather_eligibility": {
            "mode": "explicit_per_event_manifest",
            "default_when_evidence_missing": "ineligible",
            "required_evidence": [
                "archived_forecast_coverage_valid",
                "weather_source_type",
                "provider",
                "model",
                "forecast_or_model_run_reference_time",
            ],
            "current_target": {
                "provider": "Open-Meteo Historical Forecast API",
                "model": "gfs_global",
            },
        },
        "rules": [
            "Operational evaluation requires archived_forecast weather.",
            "Operational archived_forecast weather requires confirmed valid coverage.",
            "Weather provider, model, and run-reference metadata are mandatory.",
            "historical_actual fallback is forbidden for operational evaluation.",
            "Candidate and eligible event counts must not be hard-coded.",
        ],
    }


@router.post("/evaluation-policy/operational/validate")
def validate_operational_evaluation_scenario(payload: dict[str, Any]) -> dict[str, Any]:
    result = validate_operational_evaluation_payload(payload)

    if not result["valid"]:
        raise HTTPException(status_code=422, detail=result)

    return result
