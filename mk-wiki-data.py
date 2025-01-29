import json

def wikify(file):
    fc = json.load(open(f"docs/{file}"))

    colors = {
        0: "#bebebe",
        1: "#ff0000",
        2: "#ffa500",
        3: "#ffff00",
        4: "#008000",
    }

    for f in fc["features"]:
        f["properties"]["fill"] = colors[f["properties"]["sev"]]

    json.dump(fc, open(file.replace(".geojson", "-wiki.geojson"), "w"))

wikify("census_block_mode_severity.geojson")
wikify("mode_severity.geojson")
