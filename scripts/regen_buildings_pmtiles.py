"""
After height enrichment: reprocess buildings index + regenerate PMTiles/labels.

Does NOT re-fetch Overture (uses enriched buildings.geojson).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from IST import download_osm_pbf, make_mapgen  # noqa: E402

CITY_GEOJSON = ROOT / "output" / "IST" / "buildings.geojson"


def main() -> None:
    if not CITY_GEOJSON.exists():
        raise SystemExit(f"Missing {CITY_GEOJSON} — run enrich_building_heights.py first")

    osmpbf = download_osm_pbf()
    obj = make_mapgen(osmpbf)
    # Use enriched geojson; skip Overture re-download
    obj.buildings_geojson = str(CITY_GEOJSON)
    obj.REFETCH_BUILDINGS = False
    print(
        "color_military_like_aerodrome =",
        obj.color_military_like_aerodrome,
        flush=True,
    )
    print("***** process_buildings (enriched heights) *****", flush=True)
    obj.process_buildings()
    print("***** generate_pmtiles *****", flush=True)
    obj.generate_pmtiles()
    print("***** add_labels *****", flush=True)
    obj.add_labels()
    print("Done buildings + tiles.", flush=True)


if __name__ == "__main__":
    main()
