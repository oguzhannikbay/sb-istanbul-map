"""
Enrich Overture building heights using OSM building:levels / height tags,
then fill remaining gaps with Istanbul-aware estimates.

Writes:
  output/IST/buildings.pkl
  output/IST/buildings.geojson
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from IST import OUTPUT  # noqa: E402

CITY_DIR = OUTPUT / "IST"
PKL = CITY_DIR / "buildings.pkl"
GEOJSON = CITY_DIR / "buildings.geojson"
OSM_HEIGHTS = ROOT / "data" / "osm_building_heights.geojson"

LEVEL_M = 3.2  # meters per floor
DEFAULT_RESIDENTIAL_M = 15.0  # ~5 floors typical Istanbul apartment
MIN_HEIGHT_M = 3.0
MAX_HEIGHT_M = 400.0


def parse_height(val) -> float | None:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    if isinstance(val, (int, float)):
        h = float(val)
        return h if MIN_HEIGHT_M <= h <= MAX_HEIGHT_M else None
    s = str(val).strip().lower().replace(",", ".")
    m = re.search(r"([\d.]+)", s)
    if not m:
        return None
    h = float(m.group(1))
    if "ft" in s:
        h *= 0.3048
    return h if MIN_HEIGHT_M <= h <= MAX_HEIGHT_M else None


def parse_levels(val) -> float | None:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    try:
        levels = float(str(val).replace(",", ".").split(";")[0].strip())
    except ValueError:
        return None
    if levels < 1 or levels > 120:
        return None
    return levels


def levels_to_height(levels: float) -> float:
    return max(MIN_HEIGHT_M, min(MAX_HEIGHT_M, levels * LEVEL_M))


def estimate_height_from_area(area_m2: float) -> float:
    """Heuristic when no Overture/OSM height exists."""
    if area_m2 < 40:
        return 6.0
    if area_m2 < 120:
        return 12.0  # ~4 floors
    if area_m2 < 400:
        return DEFAULT_RESIDENTIAL_M  # ~5 floors
    if area_m2 < 1500:
        return 22.0  # mid-rise / large footprint block
    if area_m2 < 4000:
        return 30.0
    return 18.0  # very large footprint often low industrial/warehouse


def main() -> None:
    if not PKL.exists():
        raise SystemExit(f"Missing {PKL} — run IST.py process_buildings first")

    print(f"Loading {PKL} ...", flush=True)
    df = pd.read_pickle(PKL)
    gdf = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")
    n0 = len(gdf)
    overture_h = pd.to_numeric(gdf.get("height"), errors="coerce")
    has_overture = overture_h.notna() & (overture_h >= MIN_HEIGHT_M)
    print(
        f"Overture heights present: {int(has_overture.sum()):,} / {n0:,} "
        f"({100 * has_overture.mean():.1f}%)",
        flush=True,
    )

    height = overture_h.copy()
    source = np.where(has_overture, "overture", None)

    if OSM_HEIGHTS.exists():
        print(f"Loading OSM height/levels from {OSM_HEIGHTS} ...", flush=True)
        osm = gpd.read_file(OSM_HEIGHTS)
        osm = osm[osm.geometry.notna() & ~osm.geometry.is_empty].copy()
        osm_h = osm.get("height").map(parse_height)
        if "building:height" in osm.columns:
            osm_h = osm_h.fillna(osm["building:height"].map(parse_height))
        osm_l = None
        if "building:levels" in osm.columns:
            osm_l = osm["building:levels"].map(parse_levels)
        elif "levels" in osm.columns:
            osm_l = osm["levels"].map(parse_levels)
        osm["h_osm"] = osm_h
        if osm_l is not None:
            from_levels = osm_l.map(lambda x: levels_to_height(x) if x else np.nan)
            osm["h_osm"] = osm["h_osm"].fillna(from_levels)
        osm = osm[osm["h_osm"].notna()].copy()
        print(f"OSM features with usable height: {len(osm):,}", flush=True)

        # Point-in-polygon: building centroids → OSM polygons (prefer taller)
        cents = gdf.geometry.centroid
        pts = gpd.GeoDataFrame(
            {"idx": np.arange(len(gdf)), "geometry": cents},
            crs=gdf.crs,
        )
        joined = gpd.sjoin(
            pts,
            osm[["h_osm", "geometry"]],
            how="left",
            predicate="within",
        )
        # if multiple matches, keep max height
        best = joined.groupby("idx", as_index=True)["h_osm"].max()
        osm_fill = best.reindex(range(len(gdf)))
        need = ~has_overture & osm_fill.notna()
        height = height.where(~need, osm_fill)
        source = np.where(need, "osm", source)
        print(f"Filled from OSM: {int(need.sum()):,}", flush=True)
    else:
        print(f"WARNING: {OSM_HEIGHTS} missing — skipping OSM join", flush=True)

    # Area-based estimate for remaining nulls
    metric = gdf.to_crs(epsg=3857)
    area = metric.geometry.area.to_numpy()
    still_null = height.isna() | (height < MIN_HEIGHT_M)
    est = np.array([estimate_height_from_area(a) for a in area])
    height = height.where(~still_null, est)
    source = np.where(still_null, "estimate", source)

    # Cap / sanitize
    height = height.clip(lower=MIN_HEIGHT_M, upper=MAX_HEIGHT_M)

    gdf["height"] = height.astype(float)
    gdf["height_source"] = source

    print("\nHeight stats after enrichment:", flush=True)
    print(gdf["height"].describe(), flush=True)
    print("Sources:", pd.Series(source).value_counts().to_dict(), flush=True)
    print(
        f"height>20: {(gdf['height'] > 20).sum():,}  "
        f">50: {(gdf['height'] > 50).sum():,}  "
        f">100: {(gdf['height'] > 100).sum():,}",
        flush=True,
    )

    # Maslak/Levent/Şişli corridor sample
    cbd = (
        (gdf.geometry.centroid.x >= 28.98)
        & (gdf.geometry.centroid.x <= 29.05)
        & (gdf.geometry.centroid.y >= 41.06)
        & (gdf.geometry.centroid.y <= 41.12)
    )
    print(
        f"CBD corridor buildings: {int(cbd.sum()):,}  "
        f"mean height: {gdf.loc[cbd, 'height'].mean():.1f}m  "
        f"max: {gdf.loc[cbd, 'height'].max():.0f}m",
        flush=True,
    )

    out = gdf.drop(columns=["height_source"], errors="ignore")
    print(f"Saving {PKL} ...", flush=True)
    out.to_pickle(PKL)
    print(f"Saving {GEOJSON} ...", flush=True)
    out.to_file(GEOJSON, driver="GeoJSON")
    print("Done.", flush=True)


if __name__ == "__main__":
    main()
