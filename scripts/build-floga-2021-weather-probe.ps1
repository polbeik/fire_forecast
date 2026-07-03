@'
from pathlib import Path
import csv
import json
import re
import time
import urllib.parse
import urllib.request

import h5py
import mgrs

root = Path("/data/floga")
out_dir = Path("/data/processed")
out_dir.mkdir(parents=True, exist_ok=True)

manifest_path = out_dir / "floga_2021_event_manifest.csv"
probe_path = out_dir / "floga_2021_openmeteo_gfs_global_probe.csv"

files = {
    "10m": root / "S2 10m - MODIS 500m" / "FLOGA_dataset_2021_sen2_10_mod_500.h5",
    "20m": root / "S2 20m - MODIS 500m" / "FLOGA_dataset_2021_sen2_20_mod_500.h5",
    "60m": root / "S2 60m - MODIS 500m" / "FLOGA_dataset_2021_sen2_60_mod_500.h5",
}

split_path = root / "data splits" / "data_split.csv"
splits = {}

with split_path.open("r", encoding="utf-8", errors="replace", newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row.get("year") == "2021":
            splits[row["event_id"]] = row.get("set", "")

def extract_tile(s):
    if not s:
        return ""
    m = re.search(r"_T([0-9]{2}[A-Z]{3})_", s)
    return m.group(1) if m else ""

events_by_res = {}

for res, path in files.items():
    with h5py.File(path, "r") as f:
        events_by_res[res] = set(f["2021"].keys())

all_event_ids = sorted(set().union(*events_by_res.values()), key=lambda x: int(x))

manifest_rows = []

with h5py.File(files["60m"], "r") as f60:
    group = f60["2021"]

    for event_id in all_event_ids:
        attrs = dict(group[event_id].attrs)
        pre_sen2_file = attrs.get("pre_sen2_file", "")
        post_sen2_file = attrs.get("post_sen2_file", "")

        manifest_rows.append({
            "year": "2021",
            "event_id": event_id,
            "split": splits.get(event_id, ""),
            "pre_image_date": attrs.get("pre_image_date", ""),
            "post_image_date": attrs.get("post_image_date", ""),
            "pre_sen2_tile": extract_tile(pre_sen2_file),
            "post_sen2_tile": extract_tile(post_sen2_file),
            "pre_sen2_file": pre_sen2_file,
            "post_sen2_file": post_sen2_file,
            "pre_modis_file": attrs.get("pre_modis_file", ""),
            "post_modis_file": attrs.get("post_modis_file", ""),
            "has_10m": event_id in events_by_res["10m"],
            "has_20m": event_id in events_by_res["20m"],
            "has_60m": event_id in events_by_res["60m"],
        })

manifest_fields = [
    "year",
    "event_id",
    "split",
    "pre_image_date",
    "post_image_date",
    "pre_sen2_tile",
    "post_sen2_tile",
    "pre_sen2_file",
    "post_sen2_file",
    "pre_modis_file",
    "post_modis_file",
    "has_10m",
    "has_20m",
    "has_60m",
]

with manifest_path.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=manifest_fields)
    writer.writeheader()
    writer.writerows(manifest_rows)

print("manifest rows:", len(manifest_rows))
print("manifest path:", manifest_path)

required = [
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "precipitation",
    "cloud_cover",
]

hourly = ",".join(required)
base_url = "https://historical-forecast-api.open-meteo.com/v1/forecast"
model = "gfs_global"

converter = mgrs.MGRS()

def tile_to_centroid(tile):
    mgrs_center = tile + "5000050000"
    lat, lon = converter.toLatLon(mgrs_center)
    return float(lat), float(lon)

def non_null_ratio(hourly_data):
    total = 0
    non_null = 0

    for var in required:
        values = hourly_data.get(var)
        if values is None:
            continue

        for value in values:
            total += 1
            if value is not None:
                non_null += 1

    if total == 0:
        return 0.0

    return round(non_null / total, 4)

probe_rows = []

for idx, row in enumerate(manifest_rows, start=1):
    event_id = row["event_id"]
    split = row["split"]
    split_label = split if split else "NA"
    date = row["post_image_date"]
    tile = row["post_sen2_tile"]

    if not date or not tile:
        probe_rows.append({
            **row,
            "weather_model": model,
            "approx_lat": "",
            "approx_lon": "",
            "http_status": "missing_date_or_tile",
            "non_null_ratio": 0,
            "weather_available": False,
        })
        continue

    lat, lon = tile_to_centroid(tile)

    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": date,
        "end_date": date,
        "hourly": hourly,
        "timezone": "UTC",
        "models": model,
    }

    url = base_url + "?" + urllib.parse.urlencode(params)

    print("[{}/{}] event={} split={} date={} tile={} lat={:.4f} lon={:.4f}".format(
        idx,
        len(manifest_rows),
        event_id,
        split_label,
        date,
        tile,
        lat,
        lon,
    ))

    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            status = response.status
            payload = json.loads(response.read().decode("utf-8"))

        ratio = non_null_ratio(payload.get("hourly", {}))
        available = status == 200 and ratio >= 0.95

        probe_rows.append({
            **row,
            "weather_model": model,
            "approx_lat": round(lat, 6),
            "approx_lon": round(lon, 6),
            "http_status": status,
            "non_null_ratio": ratio,
            "weather_available": available,
        })
    except Exception as exc:
        probe_rows.append({
            **row,
            "weather_model": model,
            "approx_lat": round(lat, 6),
            "approx_lon": round(lon, 6),
            "http_status": "error",
            "non_null_ratio": 0,
            "weather_available": False,
        })
        print("  ERROR:", repr(exc))

    time.sleep(0.2)

probe_fields = manifest_fields + [
    "weather_model",
    "approx_lat",
    "approx_lon",
    "http_status",
    "non_null_ratio",
    "weather_available",
]

with probe_path.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=probe_fields)
    writer.writeheader()
    writer.writerows(probe_rows)

print()
print("probe path:", probe_path)
print("probe rows:", len(probe_rows))

counts = {}
for r in probe_rows:
    key = (r["split"] or "NO_SPLIT", str(r["weather_available"]))
    counts[key] = counts.get(key, 0) + 1

print()
print("weather availability by split:")
for key, count in sorted(counts.items()):
    print(" ", key, count)

eligible = [
    r for r in probe_rows
    if r["split"] in {"train", "val", "test"} and r["weather_available"] is True
]
print()
print("eligible train/val/test events:", len(eligible))

not_available = [
    r for r in probe_rows
    if r["split"] in {"train", "val", "test"} and r["weather_available"] is not True
]
print("non-eligible train/val/test events:", len(not_available))

if not_available:
    print()
    print("first non-eligible examples:")
    for r in not_available[:10]:
        print(
            r["event_id"],
            r["split"],
            r["post_image_date"],
            r["post_sen2_tile"],
            r["http_status"],
            r["non_null_ratio"],
        )
'@ | docker exec -i fire-forecast-ingestion-service python -