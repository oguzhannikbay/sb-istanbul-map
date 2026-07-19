"""
Generate Subway Builder map assets for Istanbul (IST).

Pipeline (matches depot / Railyard docs):
  1. extract_base_data        — OSM extract for the bbox
  2. process_buildings        — Overture buildings → buildings_index.json
  3. process_roads_and_aeroways — roads / runways / taxiways GeoJSON
  4. generate_pmtiles         — optimized PMTiles (incl. buildings)
  5. add_labels               — city / suburb / neighborhood labels by zoom
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import requests
from depot.maps import MapGen

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUTPUT = ROOT / "output"

# Geofabrik extract covering Istanbul
OSM_URL = "https://download.geofabrik.de/europe/turkey-latest.osm.pbf"
OSM_PBF = DATA / "turkey-latest.osm.pbf"

# Metropolitan Istanbul — European + Asian sides, Bosphorus, Marmara coast.
# [min_lon, min_lat, max_lon, max_lat]
ISTANBUL_BBOX = [28.45, 40.85, 29.45, 41.35]

# Tuned from check_labels() on this bbox:
#   1 city, 36 town, 754 suburb, 63 village,
#   27 neighbourhood, 139 quarter, 223 locality
LABEL_CITIES = ["city", "town"]
LABEL_SUBURBS = ["suburb", "village"]
LABEL_NEIGHBORHOODS = ["neighbourhood", "quarter", "locality"]


def download_osm_pbf() -> Path:
    DATA.mkdir(parents=True, exist_ok=True)
    if OSM_PBF.exists():
        print(f"Using existing OSM file: {OSM_PBF}", flush=True)
        return OSM_PBF

    print(f"Downloading {OSM_URL}", flush=True)
    print("(Turkey extract is large — this may take a while.)", flush=True)
    with requests.get(OSM_URL, stream=True) as resp:
        resp.raise_for_status()
        tmp = OSM_PBF.with_suffix(".part")
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
        tmp.replace(OSM_PBF)
    print(f"Saved to {OSM_PBF}", flush=True)
    return OSM_PBF


def make_mapgen(osmpbf: Path) -> MapGen:
    ncores = os.cpu_count() or 4
    return MapGen(
        city="IST",
        bbox=ISTANBUL_BBOX,
        osmpbf=str(osmpbf),
        outputdir=str(OUTPUT),
        building_index_filter_size=40,
        building_tile_filter_size=40,
        building_index_simplification=1,
        building_tile_simplification=1,
        create_building_foundations=True,
        create_ocean_foundations=True,
        label_name_language="prefer:tr",
        road_name_preferred_language="tr",
        cities=LABEL_CITIES,
        suburbs=LABEL_SUBURBS,
        neighborhoods=LABEL_NEIGHBORHOODS,
        ncores=ncores,
        RAM=8,
        cleanup_files=True,
        verb=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate IST Subway Builder map")
    parser.add_argument(
        "--labels-only",
        action="store_true",
        help="Only re-run add_labels (requires prior generate_pmtiles)",
    )
    parser.add_argument(
        "--check-labels",
        action="store_true",
        help="Print place-tag counts and exit",
    )
    args = parser.parse_args()

    osmpbf = download_osm_pbf()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    obj = make_mapgen(osmpbf)

    if args.check_labels:
        obj.check_labels()
        return

    if args.labels_only:
        print("Re-running add_labels with tuned place tiers...", flush=True)
        obj.add_labels()
    else:
        obj.run_all()

    print(f"\nDone. Outputs under: {OUTPUT / 'IST'}", flush=True)


if __name__ == "__main__":
    main()
