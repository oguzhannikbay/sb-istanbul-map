"""Regenerate IST PMTiles + labels (e.g. after MapGen flag changes)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from IST import download_osm_pbf, make_mapgen  # noqa: E402


def main() -> None:
    osmpbf = download_osm_pbf()
    obj = make_mapgen(osmpbf)
    print(
        "color_military_like_aerodrome =",
        obj.color_military_like_aerodrome,
        flush=True,
    )
    print("***** Regenerating PMTiles *****", flush=True)
    obj.generate_pmtiles()
    print("***** Re-adding labels *****", flush=True)
    obj.add_labels()
    print("Done regenerating tiles.", flush=True)


if __name__ == "__main__":
    main()
