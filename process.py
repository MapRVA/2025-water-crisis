import json

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
    "Not at all, flow was normal",
    "Water pressure was reduced",
]

max_severity = {}
with fiona.open("survey.shp") as src:
    for feat in src:
        if not shapely.geometry.shape(feat.geometry).within(BOUNDS):
            continue
        lng, lat = feat.geometry.coordinates
        cell = h3.latlng_to_cell(lat, lng, RESOLUTION)
        sev = extents.index(feat.properties["to_what_ex"])
        if cell not in max_severity or max_severity[cell] > sev:
            max_severity[cell] = sev

json.dump(
    {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": h3.cells_to_geo([cell]),
                "properties": {
                    "to_what_ex": extents[sev],
                    "sev": sev,
                },
            }
            for cell, sev in max_severity.items()
        ],
    },
    open("docs/max_severity.geojson", "w"),
)
