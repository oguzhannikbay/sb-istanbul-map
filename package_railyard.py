"""
Copy Railyard-ready map assets into package/IST/ and build IST.zip.

Zip layout matches community maps (e.g. ZRH.zip): files at archive root.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from IST import OUTPUT, ROOT

CITY_DIR = OUTPUT / "IST"
PKG = ROOT / "package" / "IST"
ZIP_PATH = ROOT / "package" / "IST.zip"
DESKTOP_ZIP = Path.home() / "Desktop" / "IST.zip"

FILES = [
    "config.json",
    "description.md",
    "demand_data.json",
    "IST.pmtiles",
    "IST_foundations.pmtiles",
    "buildings_index.bin.gz",
    "buildings_index.json.gz",
    "roads.geojson",
    "runways_taxiways.geojson",
    "ocean_depth_index.json.gz",
    "ocean_depth_index_contours.json.gz",
]

# Required / expected contents of the importable zip (ZRH-style)
ZIP_FILES = [
    "config.json",
    "IST.pmtiles",
    "IST_foundations.pmtiles",
    "buildings_index.bin.gz",
    "demand_data.json",
    "roads.geojson",
    "runways_taxiways.geojson",
    "ocean_depth_index.json.gz",
]


def main() -> None:
    PKG.mkdir(parents=True, exist_ok=True)
    copied = []
    missing = []
    for name in FILES:
        src = CITY_DIR / name
        if src.exists():
            shutil.copy2(src, PKG / name)
            copied.append(name)
        else:
            missing.append(name)

    schema_src = CITY_DIR / ".railyard_map"
    if schema_src.exists():
        dest = PKG / ".railyard_map"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(schema_src, dest)
        copied.append(".railyard_map/")

    # Build importable zip with files at root (no package/IST/ folder inside)
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in ZIP_FILES:
            path = PKG / name
            if not path.exists():
                raise FileNotFoundError(f"Missing zip member: {path}")
            zf.write(path, arcname=name)
        for schema in ("special_demand_points.json", "special_demand_types.json"):
            path = PKG / ".railyard_map" / schema
            if path.exists():
                zf.write(path, arcname=f".railyard_map/{schema}")

    shutil.copy2(ZIP_PATH, DESKTOP_ZIP)

    print("Packaged to", PKG)
    print("  copied:", ", ".join(copied))
    if missing:
        print("  missing:", ", ".join(missing))
    print(f"Zip: {ZIP_PATH} ({ZIP_PATH.stat().st_size / 1e6:.1f} MB)")
    print(f"Also copied to: {DESKTOP_ZIP}")


if __name__ == "__main__":
    main()
