#!/usr/bin/env bash
# Source before running map generation:
#   source scripts/env.sh
#   conda activate depot
#   python IST.py

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export PATH="$HOME/miniforge3/bin:$HOME/.local/bin:$ROOT/tools:/usr/local/bin:$PATH"

# Prefer portable Temurin JDK over macOS /usr/bin/java stub
if [[ -x "$HOME/.local/bin/java" ]]; then
  export JAVA_HOME="$(cd "$(dirname "$(readlink "$HOME/.local/bin/java")")/.." && pwd)"
fi

if [[ -f "$HOME/miniforge3/etc/profile.d/conda.sh" ]]; then
  # shellcheck disable=SC1091
  source "$HOME/miniforge3/etc/profile.d/conda.sh"
  conda activate depot
fi

# Prefer the depot env interpreter even if activate was skipped
if [[ -x "$HOME/miniforge3/envs/depot/bin/python" ]]; then
  export PATH="$HOME/miniforge3/envs/depot/bin:$PATH"
fi

echo "PATH ready"
echo "  python:         $(command -v python)"
echo "  java:           $(command -v java)"
echo "  planetiler.jar: $(command -v planetiler.jar || true)"
