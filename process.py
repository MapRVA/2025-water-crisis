import csv
import json
import sys

import fiona
import h3
import shapely
import shapely.geometry

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


# Collect features
feats = []
with fiona.open(sys.argv[1]) as src:
    for feat in src:
        if not shapely.geometry.shape(feat.geometry).within(BOUNDS):
            continue
        feats.append(feat)

# TODO: dedup features

# generate raw-h3 CSV
with open("docs/raw-h3.csv", "w", newline="") as file:
    writer = csv.writer(file)
    writer.writerow(FIELDS)

    for feat in feats:
        lng, lat = feat.geometry.coordinates
        cell = h3.latlng_to_cell(lat, lng, RESOLUTION)
        writer.writerow(
            [cell]
            + list([feat.properties[f] for f in FIELDS if f != "h3_cell"])
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
                    "to_what_extent_did_you_lose_wat": EXTENTS[sev],
                    "sev": sev,
                },
            }
            for cell, sev in max_severity.items()
        ],
    },
    open("docs/max_severity.geojson", "w"),
)


def format_quote(raw_note: str) -> str:
    note = raw_note.strip('"').strip()
    return f'"{note}"'


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
