#!/bin/bash
# Prepares backend/ for `sam build` and runs it. Run from the repo root.
#
# Two things SAM's Python builder doesn't handle on its own (.samignore
# isn't respected by PythonPipBuilder - confirmed empirically, not just
# undocumented):
#   1. backend/db.sqlite3 is local dev state (regeneratable, gitignored)
#      and must not ship in the Lambda package.
#   2. data/fuel_stations.json lives one level above backend/ (the
#      repo-root convention the ingestion command uses locally), but only
#      backend/ itself is packaged for Lambda - see stations/data.py's
#      fallback path.
set -euo pipefail
cd "$(dirname "$0")/.."

rm -f backend/db.sqlite3
mkdir -p backend/data
cp "data/fuel_stations.json" backend/data/fuel_stations.json

sam build
