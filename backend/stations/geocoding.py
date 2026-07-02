"""
Offline city+state -> coordinates lookup.

Backed by data/us_cities_gazetteer.csv (built once from a GeoNames
export - see scripts/build_gazetteer.py). No network calls happen here;
this is the whole point of ADR-003 in docs/decisions.md.
"""
import csv
from functools import lru_cache

from django.conf import settings

GAZETTEER_PATH = settings.BASE_DIR.parent / "data" / "us_cities_gazetteer.csv"


@lru_cache(maxsize=1)
def _gazetteer():
    table = {}
    with open(GAZETTEER_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (row["city"].strip().upper(), row["state"].strip().upper())
            table[key] = (float(row["latitude"]), float(row["longitude"]))
    return table


def lookup(city: str, state: str):
    """Returns (lat, lng) for a US city/state pair, or None if not found."""
    return _gazetteer().get((city.strip().upper(), state.strip().upper()))
