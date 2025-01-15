import csv
import json
import statistics
import sys
from datetime import datetime, timezone

import fiona
import h3
import shapely
import shapely.geometry
from pyproj import Transformer

BOUNDS = shapely.box(
    -77.6118850708008, 37.43343148473675, -77.34203338623048, 37.63408177377815
)
RESOLUTION = 9

EXTENTS = [
    None,
    "Fully lost water",
    "Down to just a trickle",
    "Water pressure was reduced",
    "Not at all, flow was normal",
]
FIELDS = [
    "h3_cell",
    "CreationDate",
    "when_did_you_lose_water",
    "when_did_you_regain_water",
    "to_what_extent_did_you_lose_wat",
]

# Transform to NAD83 / UTM zone 17N -- https://epsg.io/26917-1736
transformer = Transformer.from_crs("EPSG:4326", "EPSG:26917")


# Collect features
feats = []
with fiona.open(sys.argv[1]) as src:
    for feat in src:
        if not shapely.geometry.shape(feat.geometry).within(BOUNDS):
            continue
        feats.append(feat)

# generate raw-h3 CSV
with open("docs/raw-h3.csv", "w", newline="") as file:
    writer = csv.writer(file)
    writer.writerow(FIELDS)

    for feat in feats:
        lng, lat = feat.geometry.coordinates
        cell = h3.latlng_to_cell(lat, lng, RESOLUTION)
        writer.writerow(
            [cell] + list([feat.properties[f] for f in FIELDS if f != "h3_cell"])
        )

# dedup features by converting coords to UTM and dividing by 10, effectively dedup to 10meters
feat_by_loc = {}
for feat in feats:
    utm_coords = transformer.transform(*feat.geometry.coordinates)
    if (
        feat.geometry.coordinates not in feat_by_loc
        or feat_by_loc[(round(utm_coords[0])/10, round(utm_coords[1])/10)].properties["CreationDate"]
        < feat.properties["CreationDate"]
    ):
        feat_by_loc[(round(utm_coords[0])/10, round(utm_coords[1])/10)] = feat
print(f"Removed {len(feats) - len(feat_by_loc)} feats by deduping")
feats = list(feat_by_loc.values())

# generate deduped-h3 CSV
with open("docs/deduped-h3.csv", "w", newline="") as file:
    writer = csv.writer(file)
    writer.writerow(FIELDS)

    for feat in feats:
        lng, lat = feat.geometry.coordinates
        cell = h3.latlng_to_cell(lat, lng, RESOLUTION)
        writer.writerow(
            [cell] + list([feat.properties[f] for f in FIELDS if f != "h3_cell"])
        )

# Compute basic metadata
count = 0
latest = None
for feat in feats:
    count += 1
    if latest is None or latest < feat.properties["CreationDate"]:
        latest = feat.properties["CreationDate"]
json.dump({"count": count, "latest": latest}, open("docs/meta.json", "w"))

# Compute max severities
max_severity = {}
for feat in feats:
    lng, lat = feat.geometry.coordinates
    cell = h3.latlng_to_cell(lat, lng, RESOLUTION)

    sev = EXTENTS.index(feat.properties["to_what_extent_did_you_lose_wat"])
    if cell not in max_severity or max_severity[cell] == 0:
        max_severity[cell] = sev
    elif max_severity[cell] > sev and sev != 0:
        max_severity[cell] = sev
json.dump(
    {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": h3.cells_to_geo([cell]),
                "properties": {
                    "sev": sev,
                },
            }
            for cell, sev in max_severity.items()
        ],
    },
    open("docs/max_severity.geojson", "w"),
)

# collect non-zero severities
severities_by_cell = {}
for feat in feats:
    lng, lat = feat.geometry.coordinates
    cell = h3.latlng_to_cell(lat, lng, RESOLUTION)

    sev = EXTENTS.index(feat.properties["to_what_extent_did_you_lose_wat"])
    if sev == 0:
        continue
    severities_by_cell.setdefault(cell, []).append(sev)

# dump mode of severity per cell
json.dump(
    {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": h3.cells_to_geo([cell]),
                "properties": {
                    "sev": statistics.mode(severities),
                    "sev1": len([s for s in severities if s == 1]),
                    "sev2": len([s for s in severities if s == 2]),
                    "sev3": len([s for s in severities if s == 3]),
                    "sev4": len([s for s in severities if s == 4]),
                },
            }
            for cell, severities in severities_by_cell.items()
        ],
    },
    open("docs/mode_severity.geojson", "w"),
)


def format_quote(raw_note: str) -> str:
    note = raw_note.strip('"').strip()
    return f'"{note}"'


# durations by severity
durations_by_sev = {
    1: {},
    2: {},
    3: {},
}
for feat in feats:
    lng, lat = feat.geometry.coordinates
    cell = h3.latlng_to_cell(lat, lng, RESOLUTION)
    cell_minus_1 = h3.latlng_to_cell(lat, lng, RESOLUTION - 1)

    sev = EXTENTS.index(feat.properties["to_what_extent_did_you_lose_wat"])
    if sev == 0 or sev == 4:
        continue
    if feat.properties["when_did_you_lose_water"]:
        start = datetime.fromisoformat(feat.properties["when_did_you_lose_water"])
        created = datetime.fromisoformat(feat.properties["CreationDate"])
        if start < datetime(2025, 1, 5, tzinfo=timezone.utc):
            print("WARN: invalid start date:", start)
            continue
        duration = created - start
        if feat.properties["when_did_you_regain_water"]:
            end = datetime.fromisoformat(feat.properties["when_did_you_regain_water"])
            if end < datetime(2025, 1, 5, tzinfo=timezone.utc):
                print("WARN: invalid end date:", end)
                continue
            if end < start:
                print("WARN: end date before start date:", start, end)
                continue
            if end < created:
                if end > datetime.now(timezone.utc):
                    print("WARN: invalid end date:", end)
                    continue
                duration = end - start
        duration = duration.total_seconds() / 60 / 60
        durations_by_sev[sev].setdefault(cell, []).append(duration)
        durations_by_sev[sev].setdefault(cell_minus_1, []).append(duration)
for sev, durations_by_cell in durations_by_sev.items():
    json.dump(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": h3.cells_to_geo([cell]),
                    "properties": {
                        "duration": round(statistics.median(durations)),
                        "count": len(durations),
                        "resolution": h3.get_resolution(cell),
                    },
                }
                for cell, durations in durations_by_cell.items()
            ],
        },
        open(f"docs/sev{sev}_median_duration.geojson", "w"),
    )
    json.dump(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": h3.cells_to_geo([cell]),
                    "properties": {
                        "duration": round(statistics.mean(durations)),
                        "count": len(durations),
                        "resolution": h3.get_resolution(cell),
                    },
                }
                for cell, durations in durations_by_cell.items()
            ],
        },
        open(f"docs/sev{sev}_mean_duration.geojson", "w"),
    )

# read rows from selected-notes.csv
with open("docs/selected-notes.csv", "r") as notes:
    reader = csv.reader(notes)
    json.dump(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": h3.cells_to_geo([row[0]]),
                    "properties": {
                        "note": format_quote(row[1]),
                    },
                }
                for row in reader
            ],
        },
        open("docs/selected_notes.geojson", "w"),
    )
