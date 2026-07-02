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

STATIONS_PATH = settings.BASE_DIR.parent / "data" / "fuel_stations.json"


@lru_cache(maxsize=1)
def load_stations() -> list[dict]:
    with open(STATIONS_PATH, encoding="utf-8") as f:
        return json.load(f)
