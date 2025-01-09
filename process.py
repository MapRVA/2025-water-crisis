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

extents = [
    None,
    "Fully lost water",
    "Down to just a trickle",
    "Water pressure was reduced",
    "Not at all, flow was normal",
]

count = 0
max_severity = {}
latest = None

with fiona.open(sys.argv[1]) as src:
    for feat in src:
        if not shapely.geometry.shape(feat.geometry).within(BOUNDS):
            continue

        count += 1
        if latest is None or latest < feat.properties["CreationDate"]:
            latest = feat.properties["CreationDate"]

        lng, lat = feat.geometry.coordinates
        cell = h3.latlng_to_cell(lat, lng, RESOLUTION)

        sev = extents.index(feat.properties["to_what_extent_did_you_lose_wat"])
        if cell not in max_severity or max_severity[cell] == 0:
            max_severity[cell] = sev
        elif max_severity[cell] > sev and sev != 0:
            max_severity[cell] = sev

json.dump({"count": count, "latest": latest}, open("docs/meta.json", "w"))

json.dump(
    {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": h3.cells_to_geo([cell]),
                "properties": {
                    "to_what_extent_did_you_lose_wat": extents[sev],
                    "sev": sev,
                },
            }
            for cell, sev in max_severity.items()
        ],
    },
    open("docs/max_severity.geojson", "w"),
)
