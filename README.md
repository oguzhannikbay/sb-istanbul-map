# Subway Builder — Istanbul (IST)

Custom Istanbul map assets for [Subway Builder](https://store.steampowered.com/app/2417420/Subway_Builder/), generated with [`depot`](https://github.com/Subway-Builder-Modded/depot).

## Pipeline

| Step | What it does | Output |
|------|----------------|--------|
| Buildings | Overture Maps (or your GeoJSON) → filter by size | `buildings_index.json` |
| Roads / runways / taxiways | Extract from OSM | `roads.geojson`, `runways_taxiways.geojson` |
| PMTiles & labels | Optimized tiles + zoom-tier labels | `*.pmtiles` |

Script: [`IST.py`](IST.py) — city code `IST`, metro bbox around European + Asian sides.

## 1. Python environment (conda)

```bash
# From this repo root
conda env create -f vendor/depot/environment.yml
conda activate depot
pip install -e vendor/depot
pip install requests
```

## 2. CLI dependencies

Depot will not run until these are on your `PATH`:

| Tool | Install (macOS) |
|------|------------------|
| node | `brew install node` |
| mapshaper | `npm install -g mapshaper` |
| osmium | `brew install osmium-tool` |
| java | `brew install --cask temurin` |
| tippecanoe + tile-join | `brew install tippecanoe` |
| sqlite3 | usually preinstalled |
| jq | `brew install jq` |
| pmtiles | `brew install pmtiles` (or [releases](https://github.com/protomaps/go-pmtiles/releases)) |
| planetiler.jar | download into `tools/`, then put that dir on `PATH` (depot finds it via `which planetiler.jar`) — [releases](https://github.com/onthegomap/planetiler/releases) |

Check what’s missing:

```bash
chmod +x scripts/check_deps.sh
./scripts/check_deps.sh
```

## 3. Generate the map

```bash
source scripts/env.sh   # java + planetiler.jar + conda on PATH
conda activate depot
python IST.py
```

`scripts/env.sh` puts the portable JDK (`~/.local/bin`) and `tools/planetiler.jar` on your PATH.

This will:

1. Download `turkey-latest.osm.pbf` into `data/` (large file, first run only)
2. Run the full MapGen pipeline into `output/IST/`

### Iterate on labels / buildings

After the first extract, inspect place tags:

```python
obj.extract_base_data()
obj.check_labels()
```

Then edit `cities` / `suburbs` / `neighborhoods` in `IST.py`, or re-run individual steps (see comments in the script).

Useful knobs for a dense city like Istanbul:

- `building_index_filter_size` / `building_tile_filter_size` — raise to shrink files
- `ISTANBUL_BBOX` — tighten for a core map, widen for metro
- `label_name_language="prefer:tr"` — Turkish names with fallback
- `create_ocean_foundations=True` — important for Bosphorus / Marmara

## 4. Outputs

After a successful run, look under:

```
output/IST/
```

Typical Subway Builder map assets include the PMTiles file, `buildings_index.json`, road/aeroway GeoJSON, and related config pieces for Railyard submission.

## 4. Demand + Railyard config

```bash
source scripts/env.sh
python generate_demand.py   # demand_data.json + config.json + description.md
python package_railyard.py  # copy playable assets into package/IST/
```

Retune labels after inspecting place tags:

```bash
python IST.py --check-labels
python IST.py --labels-only
```

## Notes

- `vendor/depot` is a local clone of the upstream library (GPL-3.0).
- Base demand is synthetic (building footprint × floors + gravity model). Special demand covers airports, universities, and major venues.
