"""
Cleans, dedups, geocodes, and loads the fuel price CSV into FuelStation,
then exports a static JSON artifact for the production Lambda to read
(see docs/decisions.md ADR-002 and docs/api-design.md ingestion strategy).

This is a build-time step, run locally, never in production and never
per-request.
"""
import csv
import html
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from stations.geocoding import lookup
from stations.models import FuelStation

DATA_DIR = settings.BASE_DIR.parent / "data"
DEFAULT_CSV_PATH = DATA_DIR / "Fuel Prices Assessment.csv"
DEFAULT_EXPORT_PATH = DATA_DIR / "fuel_stations.json"

# The 50 US states + DC - see docs/assumptions.md D2 (the source CSV also
# contains Canadian province codes, which are filtered out here).
US_STATE_CODES = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC",
})


class Command(BaseCommand):
    help = "Load, clean, and geocode the fuel price CSV into FuelStation, and export a static JSON artifact."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", nargs="?", default=str(DEFAULT_CSV_PATH))
        parser.add_argument(
            "--export", default=str(DEFAULT_EXPORT_PATH),
            help="Path to write the static JSON artifact bundled for deployment.",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["csv_path"])
        export_path = Path(options["export"])

        rows = self._read_and_clean(csv_path)
        stations_by_id = self._dedup(rows)
        geocoded, unresolved = self._geocode(stations_by_id)

        self._upsert(geocoded)
        self._export(geocoded, export_path)

        self.stdout.write(self.style.SUCCESS(
            f"Loaded {len(geocoded)} station(s) from {csv_path} -> {export_path}"
        ))
        if unresolved:
            self.stdout.write(self.style.WARNING(
                f"{len(unresolved)} station(s) could not be geocoded and were excluded:"
            ))
            for station in unresolved[:20]:
                self.stdout.write(
                    f"  - opis_id={station['opis_id']} {station['name']!r} "
                    f"({station['city']}, {station['state']})"
                )
            if len(unresolved) > 20:
                self.stdout.write(f"  ... and {len(unresolved) - 20} more")

    def _read_and_clean(self, csv_path):
        cleaned = []
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                state = row["State"].strip().upper()
                if state not in US_STATE_CODES:
                    continue
                cleaned.append({
                    "opis_id": int(row["OPIS Truckstop ID"]),
                    "name": html.unescape(row["Truckstop Name"]).strip(),
                    "address": html.unescape(row["Address"]).strip(),
                    "city": row["City"].strip(),
                    "state": state,
                    "rack_id": row["Rack ID"].strip(),
                    "price": float(row["Retail Price"]),
                })
        return cleaned

    def _dedup(self, rows):
        """Group by opis_id; keep the minimum price (and its rack_id), and
        the first-seen name/address - see docs/assumptions.md D3."""
        by_id = {}
        for row in rows:
            existing = by_id.get(row["opis_id"])
            if existing is None:
                by_id[row["opis_id"]] = row
            elif row["price"] < existing["price"]:
                existing["price"] = row["price"]
                existing["rack_id"] = row["rack_id"]
        return by_id

    def _geocode(self, stations_by_id):
        geocoded = []
        unresolved = []
        for station in stations_by_id.values():
            coords = lookup(station["city"], station["state"])
            if coords is None:
                unresolved.append(station)
                continue
            station["latitude"], station["longitude"] = coords
            geocoded.append(station)
        return geocoded, unresolved

    def _upsert(self, geocoded):
        for station in geocoded:
            FuelStation.objects.update_or_create(
                opis_id=station["opis_id"],
                defaults={
                    "name": station["name"],
                    "address": station["address"],
                    "city": station["city"],
                    "state": station["state"],
                    "rack_id": station["rack_id"],
                    "price_per_gallon": station["price"],
                    "latitude": station["latitude"],
                    "longitude": station["longitude"],
                },
            )

    def _export(self, geocoded, export_path):
        payload = [
            {
                "opis_id": station["opis_id"],
                "name": station["name"],
                "city": station["city"],
                "state": station["state"],
                "price_per_gallon": station["price"],
                "latitude": station["latitude"],
                "longitude": station["longitude"],
            }
            for station in geocoded
        ]
        export_path.parent.mkdir(parents=True, exist_ok=True)
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
