"""
Loads the static, pre-geocoded fuel station dataset at runtime.

Per docs/decisions.md ADR-002, the deployed app never queries a live
database for this - it reads the JSON artifact produced once by the
load_fuel_stations management command, and keeps it in memory for the
life of the process (module-level cache, reused across requests and
across warm Lambda invocations).
"""
import json
from functools import lru_cache

from django.conf import settings

# Locally, data/ sits one level above backend/ (the repo-root convention
# used by the ingestion command). In the deployed Lambda package only
# backend/ itself is shipped, so deploy/package_backend.sh copies the
# artifact to backend/data/ first - check that location too.
_CANDIDATE_PATHS = (
    settings.BASE_DIR.parent / "data" / "fuel_stations.json",
    settings.BASE_DIR / "data" / "fuel_stations.json",
)


def _resolve_stations_path():
    for path in _CANDIDATE_PATHS:
        if path.exists():
            return path
    raise FileNotFoundError(
        f"fuel_stations.json not found in any of: {[str(p) for p in _CANDIDATE_PATHS]}"
    )


@lru_cache(maxsize=1)
def load_stations() -> list[dict]:
    with open(_resolve_stations_path(), encoding="utf-8") as f:
        return json.load(f)
