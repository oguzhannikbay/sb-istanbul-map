#!/usr/bin/env bash
# Verify CLI tools required by depot MapGen.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MISSING=0

need() {
  local name="$1"
  local hint="${2:-}"
  if command -v "$name" >/dev/null 2>&1; then
    printf "  OK  %s (%s)\n" "$name" "$(command -v "$name")"
  else
    printf "  MISSING  %s%s\n" "$name" "${hint:+ — $hint}"
    MISSING=1
  fi
}

echo "Python / conda"
if command -v conda >/dev/null 2>&1; then
  printf "  OK  conda (%s)\n" "$(conda --version 2>/dev/null || true)"
else
  printf "  MISSING  conda — install Miniforge: https://github.com/conda-forge/miniforge\n"
  MISSING=1
fi

echo
echo "CLI tools required by depot"
need node "brew install node"
need mapshaper "npm install -g mapshaper"
need osmium "brew install osmium-tool"
need tippecanoe "brew install tippecanoe"
need tile-join "comes with tippecanoe"
need sqlite3
need jq "brew install jq"
need pmtiles "brew install pmtiles  OR download from https://github.com/protomaps/go-pmtiles/releases"

if command -v java >/dev/null 2>&1 && java -version >/dev/null 2>&1; then
  printf "  OK  java (%s)\n" "$(command -v java)"
else
  printf "  MISSING  java — brew install --cask temurin  (macOS stub does not count)\n"
  MISSING=1
fi

echo
PLANETILER="$ROOT/tools/planetiler.jar"
if [[ -f "$PLANETILER" ]]; then
  printf "  OK  planetiler.jar (%s)\n" "$PLANETILER"
else
  printf "  MISSING  planetiler.jar — download into tools/\n"
  printf "           https://github.com/onthegomap/planetiler/releases\n"
  MISSING=1
fi

echo
if [[ "$MISSING" -eq 0 ]]; then
  echo "All required tools look present."
  exit 0
else
  echo "Some tools are missing. See README.md for install steps."
  exit 1
fi
