"""
Build demand_data.json + Railyard config/description for Istanbul.

Base demand is synthesized from Overture building footprints (area × floors),
then special demand (airports, universities, venues) is layered via depot.
Driving times use a road-detour haversine model (no Docker/OSRM required).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from depot.demand import DemandData
from IST import ISTANBUL_BBOX, OUTPUT

CITY_DIR = OUTPUT / "IST"
DEMAND_PATH = CITY_DIR / "demand_data.json"
BUILDINGS_PATH = CITY_DIR / "buildings.geojson"

# Target playable scale (not full census)
TARGET_WORKERS = 1_800_000
MAX_POP_SIZE = 200
GRID_M = 700  # demand point grid cell size
MAX_COMMUTE_KM = 45
MIN_COMMUTE_M = 1200  # discourage same-block work assignment
JOBS_PER_RESIDENT = 0.92
AVG_SPEED_KPH = 28.0
ROAD_DETOUR = 1.35
# Soft distance decay → longer, more metro-relevant trips
GRAVITY_EXP = 1.05
TOP_DESTINATIONS = 18

# Rough CBD: Taksim–Şişli–Levent–Maslak corridor (boost jobs)
CBD_BBOX = [28.95, 41.02, 29.05, 41.12]


def haversine_m(lon1, lat1, lon2, lat2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def haversine_matrix_m(lon, lat) -> np.ndarray:
    """Pairwise haversine distance matrix in meters. lon/lat shape (N,)."""
    lon = np.radians(lon.astype(float))
    lat = np.radians(lat.astype(float))
    dlon = lon[None, :] - lon[:, None]
    dlat = lat[None, :] - lat[:, None]
    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(lat)[:, None] * np.cos(lat)[None, :] * np.sin(dlon / 2) ** 2
    )
    return 6371000.0 * 2 * np.arcsin(np.minimum(1.0, np.sqrt(a)))


def estimate_floors(height: float) -> float:
    if height is None or (isinstance(height, float) and math.isnan(height)):
        return 3.0
    return max(1.0, min(40.0, float(height) / 3.2))


def build_base_demand() -> dict:
    print(f"Loading buildings from {BUILDINGS_PATH} ...", flush=True)
    gdf = gpd.read_file(BUILDINGS_PATH)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    gdf["height"] = pd.to_numeric(gdf.get("height"), errors="coerce")

    # Metric CRS for area / grid
    metric = gdf.to_crs(epsg=3857)
    metric["area_m2"] = metric.geometry.area
    metric["floors"] = gdf["height"].map(estimate_floors).to_numpy()
    metric["capacity"] = metric["area_m2"] * metric["floors"]
    metric = metric[metric["capacity"] > 40].copy()

    centroids = metric.geometry.centroid
    metric["gx"] = (centroids.x // GRID_M).astype(int)
    metric["gy"] = (centroids.y // GRID_M).astype(int)
    cents_wgs = gpd.GeoSeries(centroids, crs=metric.crs).to_crs(epsg=4326)
    metric["lon"] = cents_wgs.x.to_numpy()
    metric["lat"] = cents_wgs.y.to_numpy()

    agg = (
        metric.groupby(["gx", "gy"], as_index=False)
        .agg(
            capacity=("capacity", "sum"),
            lon=("lon", "mean"),
            lat=("lat", "mean"),
            n_buildings=("capacity", "count"),
        )
    )
    print(f"Aggregated {len(metric):,} buildings → {len(agg):,} grid cells", flush=True)

    # Job share: taller/denser cells + CBD bonus
    in_cbd = (
        (agg["lon"] >= CBD_BBOX[0])
        & (agg["lat"] >= CBD_BBOX[1])
        & (agg["lon"] <= CBD_BBOX[2])
        & (agg["lat"] <= CBD_BBOX[3])
    )
    job_weight = agg["capacity"] * (1.0 + 1.8 * in_cbd.astype(float))
    res_weight = agg["capacity"] * (1.0 + 0.15 * (~in_cbd).astype(float))

    job_weight = job_weight / job_weight.sum()
    res_weight = res_weight / res_weight.sum()

    jobs = (job_weight * TARGET_WORKERS).to_numpy()
    residents = (res_weight * (TARGET_WORKERS / JOBS_PER_RESIDENT)).to_numpy()

    # Drop tiny cells
    keep = (jobs + residents) >= 40
    agg = agg.loc[keep].reset_index(drop=True)
    jobs = jobs[keep]
    residents = residents[keep]

    points = []
    for i, row in agg.iterrows():
        points.append(
            {
                "id": f"dp_{i:05d}",
                "location": [float(row["lon"]), float(row["lat"])],
                "jobs": 0,
                "residents": 0,
                "popIds": [],
            }
        )

    # Gravity-model pops: each home cell distributes residents to nearby job cells
    pops = []
    pop_i = 0
    lon = agg["lon"].to_numpy()
    lat = agg["lat"].to_numpy()
    job_arr = np.maximum(jobs.copy(), 1.0)

    print("Building commute matrix (gravity model)...", flush=True)
    dist_mat = haversine_matrix_m(lon, lat)
    for hi in range(len(points)):
        home_res = residents[hi]
        if home_res < 5:
            continue
        dists = dist_mat[hi]
        attract = job_arr / np.maximum(dists, 800.0) ** GRAVITY_EXP
        attract[dists < MIN_COMMUTE_M] = 0
        attract[dists > MAX_COMMUTE_KM * 1000] = 0
        # Mild preference for mid-range urban trips (~5–20 km)
        mid = (dists >= 5000) & (dists <= 20000)
        attract[mid] *= 1.6
        if attract.sum() <= 0:
            continue
        attract /= attract.sum()

        top_k = min(TOP_DESTINATIONS, len(points))
        top_idx = np.argpartition(-attract, top_k - 1)[:top_k]
        top_idx = top_idx[attract[top_idx] > 0]
        weights = attract[top_idx]
        weights /= weights.sum()

        for ji, w in zip(top_idx, weights):
            size = int(round(home_res * w))
            if size < 3:
                continue
            dist_m = float(dists[int(ji)] * ROAD_DETOUR)
            seconds = dist_m / (AVG_SPEED_KPH * 1000 / 3600)
            pops.append(
                {
                    "id": f"pop_{pop_i}",
                    "size": size,
                    "residenceId": points[hi]["id"],
                    "jobId": points[int(ji)]["id"],
                    "drivingDistance": int(round(dist_m)),
                    "drivingSeconds": int(round(seconds)),
                }
            )
            pop_i += 1

    data = {"points": points, "pops": pops}
    data = DemandData.sanitize(data)
    print(
        f"Base demand: {len(data['points'])} points, {len(data['pops'])} pops, "
        f"total size={sum(p['size'] for p in data['pops']):,}",
        flush=True,
    )
    return data


SPECIAL_AIRPORTS = [
    {
        "type": "airport",
        "name": "İstanbul Havalimanı",
        "code": "IST_T1",
        "location": [28.7519, 41.2753],
        "total_capacity": 180000,
        "pop_size": 200,
        "merge_within": 500,
    },
    {
        "type": "airport",
        "name": "Sabiha Gökçen Havalimanı",
        "code": "SAW_T1",
        "location": [29.3092, 40.8986],
        "total_capacity": 90000,
        "pop_size": 200,
        "merge_within": 400,
    },
]

SPECIAL_UNIVERSITIES = [
    {
        "type": "university",
        "name": "İstanbul Üniversitesi",
        "code": "IU",
        "location": [28.9640, 41.0128],
        "students": 70000,
        "perc_oncampus": 0.05,
        "pop_size": 200,
        "merge_within": 350,
        "max_distance": 30000,
    },
    {
        "type": "university",
        "name": "İstanbul Teknik Üniversitesi",
        "code": "ITU",
        "location": [28.9860, 41.1045],
        "students": 37000,
        "perc_oncampus": 0.12,
        "pop_size": 200,
        "merge_within": 350,
        "max_distance": 30000,
    },
    {
        "type": "university",
        "name": "Boğaziçi Üniversitesi",
        "code": "BOUN",
        "location": [29.0507, 41.0840],
        "students": 16000,
        "perc_oncampus": 0.2,
        "pop_size": 150,
        "merge_within": 300,
        "max_distance": 30000,
    },
    {
        "type": "university",
        "name": "Marmara Üniversitesi",
        "code": "MU",
        "location": [29.0535, 40.9870],
        "students": 70000,
        "perc_oncampus": 0.05,
        "pop_size": 200,
        "merge_within": 350,
        "max_distance": 30000,
    },
    {
        "type": "university",
        "name": "Yıldız Teknik Üniversitesi",
        "code": "YTU",
        "location": [29.0185, 41.0530],
        "students": 30000,
        "perc_oncampus": 0.08,
        "pop_size": 150,
        "merge_within": 300,
        "max_distance": 30000,
    },
    {
        "type": "university",
        "name": "Koç Üniversitesi",
        "code": "KU",
        "location": [29.0630, 41.2050],
        "students": 8000,
        "perc_oncampus": 0.45,
        "pop_size": 100,
        "merge_within": 250,
        "max_distance": 35000,
    },
    {
        "type": "university",
        "name": "Sabancı Üniversitesi",
        "code": "SU",
        "location": [29.3610, 40.8900],
        "students": 5000,
        "perc_oncampus": 0.55,
        "pop_size": 100,
        "merge_within": 250,
        "max_distance": 40000,
    },
]

SPECIAL_ENTERTAINMENT = [
    {
        "type": "stadium",
        "name": "Rams Park",
        "code": "RAMS",
        "location": [28.9940, 41.1033],
        "total_capacity": 5200,
        "pop_size": 200,
        "merge_within": 250,
        "max_distance": 35000,
    },
    {
        "type": "stadium",
        "name": "Ülker Stadyumu",
        "code": "ULKER",
        "location": [29.0360, 40.9878],
        "total_capacity": 4200,
        "pop_size": 200,
        "merge_within": 250,
        "max_distance": 35000,
    },
    {
        "type": "stadium",
        "name": "Vodafone Park",
        "code": "VODAF",
        "location": [28.9947, 41.0395],
        "total_capacity": 3800,
        "pop_size": 200,
        "merge_within": 250,
        "max_distance": 35000,
    },
    {
        "type": "shopping_center",
        "name": "İstinyePark",
        "code": "ISTP",
        "location": [29.0345, 41.1105],
        "total_capacity": 28000,
        "pop_size": 200,
        "merge_within": 350,
        "max_distance": 30000,
    },
    {
        "type": "shopping_center",
        "name": "Zorlu Center",
        "code": "ZORLU",
        "location": [29.0160, 41.0665],
        "total_capacity": 18000,
        "pop_size": 200,
        "merge_within": 300,
        "max_distance": 30000,
    },
    {
        "type": "shopping_center",
        "name": "Forum İstanbul",
        "code": "FORUM",
        "location": [28.8970, 41.0475],
        "total_capacity": 22000,
        "pop_size": 200,
        "merge_within": 350,
        "max_distance": 30000,
    },
    {
        "type": "shopping_center",
        "name": "Capitol AVM",
        "code": "CAPIT",
        "location": [29.0620, 41.0205],
        "total_capacity": 14000,
        "pop_size": 150,
        "merge_within": 250,
        "max_distance": 25000,
    },
    {
        "type": "art_museum",
        "name": "İstanbul Modern",
        "code": "IMOD",
        "location": [28.9835, 41.0260],
        "total_capacity": 1200,
        "pop_size": 50,
        "merge_within": 150,
        "max_distance": 25000,
    },
]


def add_special_demand(dd: DemandData) -> None:
    univ_travel = (0.3, 0.9)  # on-campus / off-campus travel propensity

    for air in SPECIAL_AIRPORTS:
        dd.add_points(dict(air))

    for u in SPECIAL_UNIVERSITIES:
        on_c = u["students"] * u["perc_oncampus"] * univ_travel[0]
        off_c = u["students"] * (1 - u["perc_oncampus"]) * univ_travel[1]
        modeled = on_c + off_c
        poi = {
            "type": u["type"],
            "name": u["name"],
            "code": u["code"],
            "location": u["location"],
            "total_capacity": modeled,
            "pop_size": u["pop_size"],
            "merge_within": u["merge_within"],
            "residential_split": on_c / modeled if modeled else 0,
            "max_distance": u["max_distance"],
        }
        dd.add_points(poi)

    for e in SPECIAL_ENTERTAINMENT:
        poi = {
            "type": e["type"],
            "name": e["name"],
            "code": e["code"],
            "location": e["location"],
            "total_capacity": e["total_capacity"],
            "pop_size": e["pop_size"],
            "merge_within": e["merge_within"],
        }
        if e.get("max_distance") is not None:
            poi["max_distance"] = e["max_distance"]
        dd.add_points(poi)


def fill_missing_routes(dd: DemandData) -> None:
    """Ensure every pop has driving fields (special demand may lack them)."""
    points = {p["id"]: p for p in dd["points"]}
    for pop in dd["pops"]:
        if pop.get("drivingDistance") and pop.get("drivingSeconds"):
            continue
        a = points[pop["residenceId"]]["location"]
        b = points[pop["jobId"]]["location"]
        dist = haversine_m(a[0], a[1], b[0], b[1]) * ROAD_DETOUR
        pop["drivingDistance"] = int(round(dist))
        pop["drivingSeconds"] = int(round(dist / (AVG_SPEED_KPH * 1000 / 3600)))


def main() -> None:
    if not BUILDINGS_PATH.exists():
        raise SystemExit(f"Missing {BUILDINGS_PATH}. Run IST.py first.")

    CITY_DIR.mkdir(parents=True, exist_ok=True)
    base = build_base_demand()
    with open(DEMAND_PATH, "w", encoding="utf-8") as f:
        json.dump(base, f, separators=(",", ":"))

    dd = DemandData(
        str(DEMAND_PATH),
        map_code="IST",
        bbox=ISTANBUL_BBOX,
        outputdir=str(CITY_DIR),
        verb=True,
    )
    dd.enforce_max_pop_size(MAX_POP_SIZE)

    print("Adding special demand...", flush=True)
    add_special_demand(dd)
    fill_missing_routes(dd)
    dd.enforce_max_pop_size(MAX_POP_SIZE)
    dd.update(DemandData.sanitize(dd))

    dd.print_stats()
    dd.save(str(DEMAND_PATH))

    dd.create_config(
        name="İstanbul",
        bbox=ISTANBUL_BBOX,
        description="Boğaz'ın iki yakasında metro ağı kur — Avrupa ve Asya'yı bağla.",
        creator="oguzhan",
        version="0.1.0",
        country="TR",
        initial_view_state=[28.9784, 41.0082],  # Sultanahmet / historic peninsula
    )

    dd.create_description(
        mapID="istanbul-tr",
        methodology=[
            '<li><a href="https://github.com/Subway-Builder-Modded/depot">Depot</a> MapGen (OSM + Overture buildings → PMTiles / buildings_index)</li>',
            "<li>Synthetic demand: building footprint × estimated floors, gravity-model commuting, special demand for airports / universities / venues</li>",
        ],
        data_sources=[
            '<li><a href="https://download.geofabrik.de/europe/turkey.html">Geofabrik Turkey OSM PBF</a></li>',
            '<li><a href="https://overturemaps.org/">Overture Maps</a> buildings</li>',
            "<li>Special demand capacities estimated from public airport / university / venue figures</li>",
        ],
    )

    print(f"\nWrote:\n  {DEMAND_PATH}\n  {CITY_DIR / 'config.json'}\n  {CITY_DIR / 'description.md'}")


if __name__ == "__main__":
    main()
