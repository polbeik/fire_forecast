from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Iterable

import hdf5plugin  # noqa: F401  # Must be imported before opening BZip2-compressed HDF5.
import h5py
import matplotlib.pyplot as plt
import numpy as np


SEN2_BANDS: dict[int, dict[str, int]] = {
    20: {
        "B02": 0,
        "B03": 1,
        "B04": 2,
        "B05": 3,
        "B06": 4,
        "B07": 5,
        "B11": 6,
        "B12": 7,
        "B8A": 8,
    },
    60: {
        "B01": 0,
        "B02": 1,
        "B03": 2,
        "B04": 3,
        "B05": 4,
        "B06": 5,
        "B07": 6,
        "B09": 7,
        "B11": 8,
        "B12": 9,
        "B8A": 10,
    },
}

DEFAULT_THRESHOLDS = (
    0.00,
    0.025,
    0.05,
    0.075,
    0.10,
    0.15,
    0.20,
    0.25,
    0.30,
    0.40,
    0.50,
    0.60,
)

DEFAULT_QUANTILES = (
    0.00,
    0.01,
    0.05,
    0.10,
    0.25,
    0.50,
    0.75,
    0.90,
    0.95,
    0.99,
    1.00,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a diagnostic dNBR burnt-area segmentation smoke test on one "
            "FLOGA event. The script validates array layout and band usage, "
            "reports class-conditional dNBR distributions, sweeps thresholds, "
            "and exports visual and tabular diagnostics."
        )
    )
    parser.add_argument(
        "--floga-root",
        type=Path,
        default=Path(r"F:\fire_forecast_data\floga"),
        help="Root directory containing FLOGA H5 files and data_split.csv.",
    )
    parser.add_argument("--year", type=int, default=2021)
    parser.add_argument(
        "--split",
        choices=("train", "val", "test"),
        default="test",
        help="Split from which to auto-select an event.",
    )
    parser.add_argument(
        "--event-id",
        type=str,
        default=None,
        help="Optional explicit event ID. Otherwise the first event in the split is used.",
    )
    parser.add_argument(
        "--sen-gsd",
        type=int,
        choices=(20, 60),
        default=60,
        help="Sentinel-2 ground sampling distance represented by the H5 file.",
    )
    parser.add_argument(
        "--mod-gsd",
        type=int,
        default=500,
        help="MODIS GSD encoded in the H5 filename.",
    )
    parser.add_argument(
        "--minimum-threshold",
        type=float,
        default=0.05,
        help="Lower bound applied to the global Otsu threshold for the baseline.",
    )
    parser.add_argument(
        "--thresholds",
        type=float,
        nargs="+",
        default=list(DEFAULT_THRESHOLDS),
        help=(
            "Diagnostic dNBR thresholds. The Otsu threshold and applied baseline "
            "threshold are added automatically."
        ),
    )
    parser.add_argument(
        "--histogram-bins",
        type=int,
        default=256,
        help="Number of bins used for Otsu and class-conditional histograms.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(r"F:\fire_forecast_data\outputs\floga_dnbr_diagnostics"),
        help="Directory receiving PNG, JSON, and CSV outputs.",
    )
    return parser.parse_args()


def find_split_csv(root: Path) -> Path:
    direct_candidates = [
        root / "data_split.csv",
        root / "data splits" / "data_split.csv",
        root / "data_splits" / "data_split.csv",
        root / "splits" / "data_split.csv",
    ]
    for candidate in direct_candidates:
        if candidate.is_file():
            return candidate

    matches = list(root.rglob("data_split.csv"))
    if not matches:
        raise FileNotFoundError(f"No data_split.csv found below {root}")
    return matches[0]


def read_split_events(
    split_csv: Path,
    *,
    year: int,
    split: str,
) -> list[str]:
    with split_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = csv.DictReader(handle)
        event_ids = [
            str(row["event_id"]).strip()
            for row in rows
            if str(row.get("year", "")).strip() == str(year)
            and str(row.get("set", "")).strip().lower() == split
            and str(row.get("event_id", "")).strip()
        ]

    unique_ids = list(dict.fromkeys(event_ids))
    if not unique_ids:
        raise ValueError(
            f"No events found for year={year}, split={split!r} in {split_csv}"
        )
    return unique_ids


def find_h5(root: Path, *, year: int, sen_gsd: int, mod_gsd: int) -> Path:
    expected_names = [
        f"FLOGA_dataset_{year}_sen2_{sen_gsd}_mod_{mod_gsd}.h5",
        f"FLOGA_dataset_{year}_sen2_{sen_gsd}_mod_{mod_gsd}.hdf5",
        f"FLOGA_dataset_{year}_sen2_{sen_gsd}_mod_{mod_gsd}.hdf",
    ]
    for name in expected_names:
        direct = root / name
        if direct.is_file():
            return direct

    patterns = [
        f"*{year}*sen2_{sen_gsd}*mod_{mod_gsd}*.h5",
        f"*{year}*sen2_{sen_gsd}*mod_{mod_gsd}*.hdf5",
        f"*{year}*sen2_{sen_gsd}*mod_{mod_gsd}*.hdf",
    ]
    for pattern in patterns:
        matches = sorted(root.rglob(pattern))
        if matches:
            return matches[0]

    raise FileNotFoundError(
        "Could not find a matching FLOGA HDF5 file. Expected a filename similar to "
        f"FLOGA_dataset_{year}_sen2_{sen_gsd}_mod_{mod_gsd}.h5 below {root}"
    )


def squeeze_spatial(array: np.ndarray) -> np.ndarray:
    result = np.asarray(array).squeeze()
    if result.ndim != 2:
        raise ValueError(f"Expected a 2-D spatial array after squeeze; got {result.shape}")
    return result


def ensure_chw(
    array: np.ndarray,
    *,
    expected_channels: int,
    dataset_name: str,
) -> tuple[np.ndarray, dict[str, Any]]:
    result = np.asarray(array)
    original_shape = tuple(int(value) for value in result.shape)

    if result.ndim != 3:
        raise ValueError(
            f"{dataset_name}: expected a 3-D Sentinel-2 array; got {original_shape}"
        )

    candidate_axes = [
        axis
        for axis, size in enumerate(result.shape)
        if int(size) == expected_channels
    ]

    if len(candidate_axes) != 1:
        raise ValueError(
            f"{dataset_name}: could not identify a unique channel axis. "
            f"Expected exactly one dimension equal to {expected_channels}; "
            f"shape={original_shape}, candidate_axes={candidate_axes}"
        )

    channel_axis = candidate_axes[0]
    if channel_axis == 0:
        chw = result
        conversion = "already_chw"
    elif channel_axis == 2:
        chw = np.moveaxis(result, 2, 0)
        conversion = "hwc_to_chw"
    else:
        chw = np.moveaxis(result, 1, 0)
        conversion = "hcw_to_chw"

    normalized_shape = tuple(int(value) for value in chw.shape)
    if normalized_shape[0] != expected_channels:
        raise AssertionError(
            f"{dataset_name}: normalized channel count is {normalized_shape[0]}, "
            f"expected {expected_channels}"
        )

    return chw, {
        "dataset": dataset_name,
        "original_shape": list(original_shape),
        "channel_axis": channel_axis,
        "conversion": conversion,
        "normalized_chw_shape": list(normalized_shape),
        "expected_channels": expected_channels,
    }


def validate_spatial_shapes(
    pre: np.ndarray,
    post: np.ndarray,
    label: np.ndarray,
    cloud_pre: np.ndarray | None,
    cloud_post: np.ndarray | None,
) -> None:
    expected = tuple(int(value) for value in pre.shape[1:])

    if tuple(post.shape[1:]) != expected:
        raise ValueError(
            f"Pre/post spatial shape mismatch: pre={pre.shape}, post={post.shape}"
        )
    if tuple(label.shape) != expected:
        raise ValueError(
            f"Label spatial shape mismatch: imagery={expected}, label={label.shape}"
        )
    if cloud_pre is not None and tuple(cloud_pre.shape) != expected:
        raise ValueError(
            f"Pre cloud-mask shape mismatch: imagery={expected}, mask={cloud_pre.shape}"
        )
    if cloud_post is not None and tuple(cloud_post.shape) != expected:
        raise ValueError(
            f"Post cloud-mask shape mismatch: imagery={expected}, mask={cloud_post.shape}"
        )


def robust_rgb(chw: np.ndarray, bands: dict[str, int]) -> np.ndarray:
    rgb = np.stack(
        [
            chw[bands["B04"]],
            chw[bands["B03"]],
            chw[bands["B02"]],
        ],
        axis=-1,
    ).astype(np.float32)

    result = np.zeros_like(rgb, dtype=np.float32)
    for channel in range(3):
        values = rgb[..., channel]
        valid = (
            np.isfinite(values)
            & (values > 0)
            & (values != 65535)
        )
        if not np.any(valid):
            continue

        low, high = np.percentile(values[valid], [2, 98])
        if not math.isfinite(low) or not math.isfinite(high) or high <= low:
            continue

        result[..., channel] = np.clip((values - low) / (high - low), 0, 1)

    return result


def array_summary(values: np.ndarray, valid: np.ndarray | None = None) -> dict[str, Any]:
    data = np.asarray(values)
    mask = np.isfinite(data)
    if valid is not None:
        mask &= valid

    selected = data[mask]
    if selected.size == 0:
        return {
            "count": 0,
            "minimum": None,
            "maximum": None,
            "mean": None,
            "median": None,
        }

    return {
        "count": int(selected.size),
        "minimum": float(np.min(selected)),
        "maximum": float(np.max(selected)),
        "mean": float(np.mean(selected, dtype=np.float64)),
        "median": float(np.median(selected)),
    }


def band_diagnostics(
    chw: np.ndarray,
    bands: dict[str, int],
    *,
    required_bands: Iterable[str],
) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for band_name in required_bands:
        index = bands[band_name]
        values = chw[index]
        finite = np.isfinite(values)
        nodata_65535 = finite & (values == 65535)
        positive = finite & (values > 0) & ~nodata_65535

        report[band_name] = {
            "channel_index": index,
            "shape": [int(value) for value in values.shape],
            "dtype": str(values.dtype),
            "finite_pixels": int(finite.sum()),
            "positive_pixels": int(positive.sum()),
            "zero_or_negative_pixels": int((finite & (values <= 0)).sum()),
            "nodata_65535_pixels": int(nodata_65535.sum()),
            "positive_value_summary": array_summary(values, positive),
        }
    return report


def compute_nbr(
    chw: np.ndarray,
    bands: dict[str, int],
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    nir = chw[bands["B8A"]].astype(np.float32)
    swir2 = chw[bands["B12"]].astype(np.float32)

    finite = np.isfinite(nir) & np.isfinite(swir2)
    nodata = (nir == 65535) | (swir2 == 65535)
    positive = (nir > 0) & (swir2 > 0)
    denominator = nir + swir2
    denominator_valid = np.abs(denominator) > 1e-6

    valid = finite & ~nodata & positive & denominator_valid

    nbr = np.full(nir.shape, np.nan, dtype=np.float32)
    np.divide(
        nir - swir2,
        denominator,
        out=nbr,
        where=valid,
    )

    diagnostics = {
        "total_pixels": int(nir.size),
        "finite_pair_pixels": int(finite.sum()),
        "nodata_65535_pair_pixels": int(nodata.sum()),
        "nonpositive_pair_pixels": int((finite & ~nodata & ~positive).sum()),
        "near_zero_denominator_pixels": int(
            (finite & ~nodata & positive & ~denominator_valid).sum()
        ),
        "valid_nbr_pixels": int(valid.sum()),
        "nir_summary": array_summary(nir, valid),
        "swir2_summary": array_summary(swir2, valid),
        "nbr_summary": array_summary(nbr, valid),
    }

    return nbr, valid, diagnostics


def otsu_threshold(values: np.ndarray, bins: int = 256) -> float:
    if bins < 8:
        raise ValueError("--histogram-bins must be at least 8")

    clean = values[np.isfinite(values)]
    if clean.size == 0:
        raise ValueError("No finite dNBR values were available for thresholding.")

    clean = np.clip(clean, -1.0, 1.0)
    histogram, edges = np.histogram(clean, bins=bins, range=(-1.0, 1.0))
    histogram = histogram.astype(np.float64)

    total = histogram.sum()
    if total <= 0:
        raise ValueError("The dNBR histogram is empty.")

    centers = (edges[:-1] + edges[1:]) / 2.0
    weight_background = np.cumsum(histogram)
    weight_foreground = total - weight_background

    mean_background_numerator = np.cumsum(histogram * centers)
    total_mean_numerator = mean_background_numerator[-1]
    mean_foreground_numerator = total_mean_numerator - mean_background_numerator

    valid = (weight_background > 0) & (weight_foreground > 0)
    between = np.full(histogram.shape, -np.inf, dtype=np.float64)

    mean_background = np.zeros_like(histogram)
    mean_foreground = np.zeros_like(histogram)
    mean_background[valid] = (
        mean_background_numerator[valid] / weight_background[valid]
    )
    mean_foreground[valid] = (
        mean_foreground_numerator[valid] / weight_foreground[valid]
    )

    between[valid] = (
        weight_background[valid]
        * weight_foreground[valid]
        * (mean_background[valid] - mean_foreground[valid]) ** 2
    )

    return float(centers[int(np.argmax(between))])


def binary_metrics(
    prediction: np.ndarray,
    truth: np.ndarray,
    valid: np.ndarray,
) -> dict[str, Any]:
    pred = prediction[valid].astype(bool)
    gt = truth[valid].astype(bool)

    tp = int(np.sum(pred & gt))
    fp = int(np.sum(pred & ~gt))
    fn = int(np.sum(~pred & gt))
    tn = int(np.sum(~pred & ~gt))

    def safe_div(numerator: float, denominator: float) -> float:
        return float(numerator / denominator) if denominator else 0.0

    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    specificity = safe_div(tn, tn + fp)
    f1 = safe_div(2 * precision * recall, precision + recall)
    iou = safe_div(tp, tp + fp + fn)
    accuracy = safe_div(tp + tn, tp + fp + fn + tn)
    balanced_accuracy = (recall + specificity) / 2.0
    predicted_fraction = safe_div(int(pred.sum()), int(valid.sum()))
    truth_fraction = safe_div(int(gt.sum()), int(valid.sum()))
    area_ratio = safe_div(int(pred.sum()), int(gt.sum()))

    return {
        "valid_pixels": int(valid.sum()),
        "ground_truth_burnt_pixels": int(gt.sum()),
        "predicted_burnt_pixels": int(pred.sum()),
        "ground_truth_burnt_fraction": truth_fraction,
        "predicted_burnt_fraction": predicted_fraction,
        "predicted_to_ground_truth_area_ratio": area_ratio,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "f1": f1,
        "iou": iou,
        "accuracy": accuracy,
        "balanced_accuracy": balanced_accuracy,
    }


def quantile_report(
    values: np.ndarray,
    mask: np.ndarray,
    quantiles: Iterable[float] = DEFAULT_QUANTILES,
) -> dict[str, Any]:
    selected = np.asarray(values)[mask]
    selected = selected[np.isfinite(selected)]

    if selected.size == 0:
        return {"count": 0, "quantiles": {}}

    quantile_values = np.quantile(selected, list(quantiles))
    return {
        "count": int(selected.size),
        "mean": float(np.mean(selected, dtype=np.float64)),
        "standard_deviation": float(np.std(selected, dtype=np.float64)),
        "quantiles": {
            f"{float(q):.3f}": float(value)
            for q, value in zip(quantiles, quantile_values)
        },
    }


def threshold_sweep(
    dnbr: np.ndarray,
    *,
    thresholds: Iterable[float],
    truth: np.ndarray,
    valid: np.ndarray,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for threshold in sorted({float(value) for value in thresholds}):
        prediction = valid & (dnbr >= threshold)
        row = {"threshold": threshold}
        row.update(binary_metrics(prediction, truth, valid))
        rows.append(row)
    return rows


def best_sweep_row(
    rows: list[dict[str, Any]],
    *,
    metric: str,
) -> dict[str, Any]:
    if not rows:
        raise ValueError("Threshold sweep is empty.")
    return max(
        rows,
        key=lambda row: (
            float(row[metric]),
            float(row["precision"]),
            -float(row["predicted_to_ground_truth_area_ratio"]),
            float(row["threshold"]),
        ),
    )


def write_sweep_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("Cannot write an empty threshold sweep.")

    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def normalized_histogram(
    values: np.ndarray,
    *,
    bins: int,
) -> tuple[np.ndarray, np.ndarray]:
    clean = np.asarray(values)
    clean = clean[np.isfinite(clean)]
    histogram, edges = np.histogram(
        np.clip(clean, -1.0, 1.0),
        bins=bins,
        range=(-1.0, 1.0),
        density=False,
    )
    histogram = histogram.astype(np.float64)
    total = histogram.sum()
    if total > 0:
        histogram /= total
    centers = (edges[:-1] + edges[1:]) / 2.0
    return centers, histogram


def make_error_map(
    prediction: np.ndarray,
    truth: np.ndarray,
    valid: np.ndarray,
) -> np.ndarray:
    result = np.full(valid.shape, np.nan, dtype=np.float32)
    result[valid & ~prediction & ~truth] = 0
    result[valid & prediction & ~truth] = 1
    result[valid & ~prediction & truth] = 2
    result[valid & prediction & truth] = 3
    return result


def read_optional_mask(group: h5py.Group, name: str) -> np.ndarray | None:
    if name not in group:
        return None
    return squeeze_spatial(group[name][:])


def json_safe_attributes(group: h5py.Group) -> dict[str, str]:
    return {
        str(key): (
            value.decode("utf-8", errors="replace")
            if isinstance(value, bytes)
            else str(value)
        )
        for key, value in group.attrs.items()
    }


def main() -> None:
    args = parse_args()
    root = args.floga_root.resolve()

    if not root.exists():
        raise FileNotFoundError(f"FLOGA root does not exist: {root}")

    split_csv = find_split_csv(root)
    split_events = read_split_events(
        split_csv,
        year=args.year,
        split=args.split,
    )
    event_id = args.event_id or split_events[0]

    if args.event_id is not None and event_id not in split_events:
        raise ValueError(
            f"event_id={event_id!r} is not in year={args.year}, split={args.split!r}"
        )

    h5_path = find_h5(
        root,
        year=args.year,
        sen_gsd=args.sen_gsd,
        mod_gsd=args.mod_gsd,
    )

    bands = SEN2_BANDS[args.sen_gsd]
    expected_channels = len(bands)
    dataset_prefix = f"sen2_{args.sen_gsd}"

    with h5py.File(h5_path, "r") as hdf:
        year_key = str(args.year)
        if year_key not in hdf:
            raise KeyError(f"Year group {year_key!r} is absent from {h5_path}")

        year_group = hdf[year_key]
        if event_id not in year_group:
            available = list(year_group.keys())
            raise KeyError(
                f"Event {event_id!r} is absent from {h5_path}. "
                f"First available IDs: {available[:10]}"
            )

        event_group = year_group[event_id]
        pre_name = f"{dataset_prefix}_pre"
        post_name = f"{dataset_prefix}_post"
        cloud_pre_name = f"{dataset_prefix}_cloud_pre"
        cloud_post_name = f"{dataset_prefix}_cloud_post"

        required = [pre_name, post_name, "label"]
        missing = [name for name in required if name not in event_group]
        if missing:
            raise KeyError(
                f"Event {event_id} is missing required datasets {missing}. "
                f"Available datasets: {list(event_group.keys())}"
            )

        pre_raw = event_group[pre_name][:]
        post_raw = event_group[post_name][:]

        pre, pre_layout = ensure_chw(
            pre_raw,
            expected_channels=expected_channels,
            dataset_name=pre_name,
        )
        post, post_layout = ensure_chw(
            post_raw,
            expected_channels=expected_channels,
            dataset_name=post_name,
        )
        label = squeeze_spatial(event_group["label"][:])

        cloud_pre = read_optional_mask(event_group, cloud_pre_name)
        cloud_post = read_optional_mask(event_group, cloud_post_name)
        attributes = json_safe_attributes(event_group)
        available_datasets = list(event_group.keys())

    validate_spatial_shapes(pre, post, label, cloud_pre, cloud_post)

    required_band_names = ("B02", "B03", "B04", "B8A", "B12")
    pre_band_report = band_diagnostics(
        pre,
        bands,
        required_bands=required_band_names,
    )
    post_band_report = band_diagnostics(
        post,
        bands,
        required_bands=required_band_names,
    )

    nbr_pre, valid_pre, nbr_pre_report = compute_nbr(pre, bands)
    nbr_post, valid_post, nbr_post_report = compute_nbr(post, bands)

    # Canonical differenced Normalized Burn Ratio:
    # positive burn signal is expected when NBR decreases after the fire.
    dnbr = nbr_pre - nbr_post
    reverse_dnbr = nbr_post - nbr_pre

    label_values, label_counts = np.unique(label, return_counts=True)
    label_distribution = {
        str(value.item() if hasattr(value, "item") else value): int(count)
        for value, count in zip(label_values, label_counts)
    }

    base_valid = valid_pre & valid_post & np.isfinite(dnbr)
    ignored_by_label = label == 2
    valid = base_valid & ~ignored_by_label

    cloud_pre_excluded = np.zeros(label.shape, dtype=bool)
    cloud_post_excluded = np.zeros(label.shape, dtype=bool)

    # The official FLOGA preprocessing treats Sentinel-2 cloud-mask value 9 as cloud.
    if cloud_pre is not None:
        cloud_pre_excluded = cloud_pre == 9
        valid &= ~cloud_pre_excluded
    if cloud_post is not None:
        cloud_post_excluded = cloud_post == 9
        valid &= ~cloud_post_excluded

    if not np.any(valid):
        raise ValueError("No valid pixels remain after nodata/cloud/label filtering.")

    truth = label == 1
    valid_truth = valid & truth
    valid_background = valid & ~truth

    if not np.any(valid_truth):
        raise ValueError(
            "The selected event has no ground-truth burnt pixels after filtering."
        )
    if not np.any(valid_background):
        raise ValueError(
            "The selected event has no valid background pixels after filtering."
        )

    raw_threshold = otsu_threshold(
        dnbr[valid],
        bins=args.histogram_bins,
    )
    applied_threshold = max(raw_threshold, float(args.minimum_threshold))

    sweep_thresholds = list(args.thresholds)
    sweep_thresholds.extend(
        [
            raw_threshold,
            applied_threshold,
        ]
    )
    sweep_rows = threshold_sweep(
        dnbr,
        thresholds=sweep_thresholds,
        truth=truth,
        valid=valid,
    )

    baseline_prediction = valid & (dnbr >= applied_threshold)
    baseline_metrics = binary_metrics(baseline_prediction, truth, valid)

    best_f1 = best_sweep_row(sweep_rows, metric="f1")
    best_iou = best_sweep_row(sweep_rows, metric="iou")
    best_iou_threshold = float(best_iou["threshold"])
    best_iou_prediction = valid & (dnbr >= best_iou_threshold)
    best_iou_error_map = make_error_map(best_iou_prediction, truth, valid)

    canonical_burnt_distribution = quantile_report(dnbr, valid_truth)
    canonical_background_distribution = quantile_report(dnbr, valid_background)
    reverse_burnt_distribution = quantile_report(reverse_dnbr, valid_truth)
    reverse_background_distribution = quantile_report(
        reverse_dnbr,
        valid_background,
    )

    canonical_median_separation = (
        canonical_burnt_distribution["quantiles"]["0.500"]
        - canonical_background_distribution["quantiles"]["0.500"]
    )
    reverse_median_separation = (
        reverse_burnt_distribution["quantiles"]["0.500"]
        - reverse_background_distribution["quantiles"]["0.500"]
    )

    if canonical_median_separation > 0:
        direction_assessment = "canonical_direction_supported"
    elif canonical_median_separation < 0 and reverse_median_separation > 0:
        direction_assessment = (
            "canonical_direction_not_supported_check_band_mapping_dates_and_sign"
        )
    else:
        direction_assessment = "weak_or_ambiguous_class_separation"

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    stem = (
        f"floga_{args.year}_{args.split}_event-{event_id}_"
        f"sen2-{args.sen_gsd}m_dnbr_diagnostics"
    )
    overview_png_path = output_dir / f"{stem}_overview.png"
    diagnostics_png_path = output_dir / f"{stem}_thresholds.png"
    json_path = output_dir / f"{stem}.json"
    csv_path = output_dir / f"{stem}_threshold_sweep.csv"

    write_sweep_csv(csv_path, sweep_rows)

    rgb_post = robust_rgb(post, bands)

    figure = plt.figure(figsize=(24, 8))

    axis = figure.add_subplot(2, 3, 1)
    axis.imshow(rgb_post)
    axis.set_title("Post-fire Sentinel-2 RGB")
    axis.axis("off")

    axis = figure.add_subplot(2, 3, 2)
    image = axis.imshow(
        np.where(valid, dnbr, np.nan),
        vmin=-0.5,
        vmax=0.8,
        cmap="RdYlGn_r",
    )
    axis.set_title(
        "Canonical dNBR = NBRpre - NBRpost\n"
        f"Otsu={raw_threshold:.4f}, baseline={applied_threshold:.4f}"
    )
    axis.axis("off")
    figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04)

    axis = figure.add_subplot(2, 3, 3)
    axis.imshow(
        np.where(valid, baseline_prediction, np.nan),
        vmin=0,
        vmax=1,
        cmap="gray",
    )
    axis.set_title(
        "Baseline prediction\n"
        f"IoU={baseline_metrics['iou']:.5f}, "
        f"F1={baseline_metrics['f1']:.5f}"
    )
    axis.axis("off")

    axis = figure.add_subplot(2, 3, 4)
    axis.imshow(
        np.where(valid, best_iou_prediction, np.nan),
        vmin=0,
        vmax=1,
        cmap="gray",
    )
    axis.set_title(
        "Best swept IoU prediction — diagnostic only\n"
        f"threshold={best_iou_threshold:.4f}, "
        f"IoU={best_iou['iou']:.5f}"
    )
    axis.axis("off")

    axis = figure.add_subplot(2, 3, 5)
    axis.imshow(
        np.where(valid, truth, np.nan),
        vmin=0,
        vmax=1,
        cmap="gray",
    )
    axis.set_title("FLOGA ground truth")
    axis.axis("off")

    axis = figure.add_subplot(2, 3, 6)
    error_image = axis.imshow(
        best_iou_error_map,
        vmin=0,
        vmax=3,
        cmap="viridis",
    )
    axis.set_title("Best-IoU error map: 0=TN, 1=FP, 2=FN, 3=TP")
    axis.axis("off")
    figure.colorbar(
        error_image,
        ax=axis,
        fraction=0.046,
        pad=0.04,
        ticks=[0, 1, 2, 3],
    )

    figure.suptitle(
        f"FLOGA {args.year} {args.split} event {event_id} — dNBR diagnostics"
    )
    figure.tight_layout()
    figure.savefig(overview_png_path, dpi=180, bbox_inches="tight")
    plt.close(figure)

    burnt_centers, burnt_histogram = normalized_histogram(
        dnbr[valid_truth],
        bins=args.histogram_bins,
    )
    background_centers, background_histogram = normalized_histogram(
        dnbr[valid_background],
        bins=args.histogram_bins,
    )

    thresholds = [float(row["threshold"]) for row in sweep_rows]
    precisions = [float(row["precision"]) for row in sweep_rows]
    recalls = [float(row["recall"]) for row in sweep_rows]
    f1_values = [float(row["f1"]) for row in sweep_rows]
    iou_values = [float(row["iou"]) for row in sweep_rows]
    area_ratios = [
        float(row["predicted_to_ground_truth_area_ratio"])
        for row in sweep_rows
    ]

    figure = plt.figure(figsize=(18, 10))

    axis = figure.add_subplot(2, 2, 1)
    axis.plot(background_centers, background_histogram, label="Background")
    axis.plot(burnt_centers, burnt_histogram, label="Ground-truth burnt")
    axis.axvline(raw_threshold, linestyle="--", label=f"Otsu {raw_threshold:.3f}")
    axis.axvline(
        applied_threshold,
        linestyle=":",
        label=f"Baseline {applied_threshold:.3f}",
    )
    axis.set_xlim(-1.0, 1.0)
    axis.set_yscale("log")
    axis.set_xlabel("Canonical dNBR")
    axis.set_ylabel("Normalized histogram mass (log scale)")
    axis.set_title("Class-conditional dNBR distributions")
    axis.legend()

    axis = figure.add_subplot(2, 2, 2)
    axis.plot(thresholds, precisions, marker="o", label="Precision")
    axis.plot(thresholds, recalls, marker="o", label="Recall")
    axis.plot(thresholds, f1_values, marker="o", label="F1")
    axis.plot(thresholds, iou_values, marker="o", label="IoU")
    axis.set_xlabel("dNBR threshold")
    axis.set_ylabel("Metric")
    axis.set_ylim(0.0, 1.0)
    axis.set_title("Threshold sweep metrics")
    axis.grid(True, alpha=0.3)
    axis.legend()

    axis = figure.add_subplot(2, 2, 3)
    axis.plot(thresholds, area_ratios, marker="o")
    axis.axhline(1.0, linestyle="--")
    axis.set_xlabel("dNBR threshold")
    axis.set_ylabel("Predicted / ground-truth burnt pixels")
    axis.set_yscale("log")
    axis.set_title("Predicted area inflation")
    axis.grid(True, alpha=0.3)

    axis = figure.add_subplot(2, 2, 4)
    axis.axis("off")
    summary_lines = [
        f"Band mapping: B8A index {bands['B8A']}, B12 index {bands['B12']}",
        f"Pre layout: {pre_layout['conversion']} {pre_layout['original_shape']}",
        f"Post layout: {post_layout['conversion']} {post_layout['original_shape']}",
        f"Valid pixels: {int(valid.sum()):,}",
        f"Valid burnt pixels: {int(valid_truth.sum()):,}",
        f"Burnt fraction: {valid_truth.sum() / valid.sum():.8f}",
        f"Canonical median separation: {canonical_median_separation:.6f}",
        f"Reverse median separation: {reverse_median_separation:.6f}",
        f"Direction assessment: {direction_assessment}",
        f"Best swept F1 threshold: {float(best_f1['threshold']):.4f}",
        f"Best swept F1: {float(best_f1['f1']):.6f}",
        f"Best swept IoU threshold: {best_iou_threshold:.4f}",
        f"Best swept IoU: {float(best_iou['iou']):.6f}",
        "",
        "Best swept thresholds use ground truth and are diagnostic only.",
        "They must not be reported as an independently evaluated model.",
    ]
    axis.text(
        0.0,
        1.0,
        "\n".join(summary_lines),
        va="top",
        ha="left",
        family="monospace",
        fontsize=10,
    )

    figure.suptitle(
        f"FLOGA {args.year} {args.split} event {event_id} — threshold and dNBR validation"
    )
    figure.tight_layout()
    figure.savefig(diagnostics_png_path, dpi=180, bbox_inches="tight")
    plt.close(figure)

    report = {
        "task": "retrospective_burnt_area_segmentation_diagnostics",
        "method": "canonical_dnbr_threshold_sweep",
        "is_future_fire_spread_forecast": False,
        "ground_truth_used_for_threshold_diagnostics": True,
        "diagnostic_warning": (
            "Best threshold metrics are oracle diagnostics computed on this event's "
            "ground truth. They are not valid independent evaluation results."
        ),
        "year": args.year,
        "split": args.split,
        "event_id": event_id,
        "sentinel2_gsd_m": args.sen_gsd,
        "modis_gsd_m": args.mod_gsd,
        "split_csv": str(split_csv),
        "h5_file": str(h5_path),
        "datasets": {
            "pre": pre_name,
            "post": post_name,
            "label": "label",
            "cloud_pre": cloud_pre_name if cloud_pre is not None else None,
            "cloud_post": cloud_post_name if cloud_post is not None else None,
            "available": available_datasets,
        },
        "array_layout_validation": {
            "pre": pre_layout,
            "post": post_layout,
            "label_shape": [int(value) for value in label.shape],
        },
        "band_mapping_validation": {
            "mapping": bands,
            "nbr_formula": "(B8A - B12) / (B8A + B12)",
            "dnbr_formula": "NBR_pre - NBR_post",
            "pre": pre_band_report,
            "post": post_band_report,
        },
        "nbr_validation": {
            "pre": nbr_pre_report,
            "post": nbr_post_report,
        },
        "masking": {
            "total_spatial_pixels": int(label.size),
            "valid_before_label_and_cloud_masks": int(base_valid.sum()),
            "label_value_distribution": label_distribution,
            "label_ignored_value": 2,
            "label_ignored_pixels": int(ignored_by_label.sum()),
            "cloud_mask_value": 9,
            "cloud_pre_present": cloud_pre is not None,
            "cloud_post_present": cloud_post is not None,
            "cloud_pre_excluded_pixels": int(cloud_pre_excluded.sum()),
            "cloud_post_excluded_pixels": int(cloud_post_excluded.sum()),
            "final_valid_pixels": int(valid.sum()),
            "final_valid_ground_truth_burnt_pixels": int(valid_truth.sum()),
            "final_valid_background_pixels": int(valid_background.sum()),
        },
        "dnbr_direction_validation": {
            "canonical": {
                "formula": "NBR_pre - NBR_post",
                "burnt_distribution": canonical_burnt_distribution,
                "background_distribution": canonical_background_distribution,
                "burnt_minus_background_median": canonical_median_separation,
            },
            "reverse": {
                "formula": "NBR_post - NBR_pre",
                "burnt_distribution": reverse_burnt_distribution,
                "background_distribution": reverse_background_distribution,
                "burnt_minus_background_median": reverse_median_separation,
            },
            "assessment": direction_assessment,
        },
        "thresholding": {
            "otsu_raw": raw_threshold,
            "minimum_threshold": float(args.minimum_threshold),
            "baseline_applied": applied_threshold,
            "histogram_bins": int(args.histogram_bins),
            "swept_thresholds": [
                float(row["threshold"])
                for row in sweep_rows
            ],
        },
        "baseline_metrics": baseline_metrics,
        "threshold_sweep": sweep_rows,
        "best_threshold_diagnostics": {
            "best_f1": best_f1,
            "best_iou": best_iou,
        },
        "event_attributes": attributes,
        "outputs": {
            "overview_visualization_png": str(overview_png_path),
            "threshold_diagnostics_png": str(diagnostics_png_path),
            "threshold_sweep_csv": str(csv_path),
            "report_json": str(json_path),
        },
    }

    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
