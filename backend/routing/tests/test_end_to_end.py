"""
Full-chain check for docs/testing.md's edge-case checklist item:
"Duplicate/aliased station collapse verified end-to-end (ingestion ->
API response never shows both aliases)". The unit tests for _dedup()
(stations/tests/test_load_fuel_stations.py) and the API's own view/
service tests already exercise each layer separately; this test is the
one place that runs a CSV with a real duplicate through ingestion and
then through a simulated request, to confirm the guarantee holds across
the whole pipeline rather than just at each layer in isolation.
"""
import csv
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import TestCase

from routing.client import Coordinates, DirectionsResult

ROUTE_GEOMETRY = {
    "type": "LineString",
    "coordinates": [[round(i * 0.05, 4), 0.0] for i in range(175)],  # lng 0 -> 8.7
}

# Same physical stop, reported twice - once under each of its two brand
# names, at two different prices, exactly like the real "PILOT TRAVEL
# CENTER #1243" / "PILOT #1243" duplicate found in the source CSV
# (docs/assumptions.md D3).
DUPLICATE_ROWS = [
    ["99", "PILOT TRAVEL CENTER #500", "I-70, EXIT 1", "Argenta", "IL", "100", "3.500"],
    ["99", "PILOT #500", "I-70, EXIT 1", "Argenta", "IL", "200", "2.750"],
]


class DuplicateStationEndToEndTests(TestCase):
    def test_ingestion_then_api_response_never_shows_both_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "fuel.csv"
            export_path = Path(tmp) / "fuel_stations.json"

            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(
                    ["OPIS Truckstop ID", "Truckstop Name", "Address", "City", "State", "Rack ID", "Retail Price"]
                )
                writer.writerows(DUPLICATE_ROWS)

            # The two rows share a fictional city, so the geocoder result
            # is controlled directly rather than depending on whether
            # "Argenta, IL" happens to be in the real gazetteer.
            with patch(
                "stations.management.commands.load_fuel_stations.lookup",
                return_value=(0.0, 4.0),
            ):
                call_command("load_fuel_stations", str(csv_path), "--export", str(export_path))

            with open(export_path) as f:
                exported_stations = json.load(f)

        # Ingestion itself must have already collapsed the two rows.
        self.assertEqual(len(exported_stations), 1)
        self.assertEqual(exported_stations[0]["price_per_gallon"], 2.75)

        client = MagicMock()
        client.resolve_location.side_effect = lambda loc: loc
        client.get_route.return_value = DirectionsResult(
            distance_miles=600.0, duration_hours=10.0, geometry=ROUTE_GEOMETRY
        )

        with patch("routing.services.load_stations", return_value=exported_stations):
            with patch("routing.services.OpenRouteServiceClient", return_value=client):
                response = self.client.post(
                    "/api/v1/route/",
                    data=json.dumps({"start": {"lat": 0, "lng": 0}, "end": {"lat": 0, "lng": 8.7}}),
                    content_type="application/json",
                )

        self.assertEqual(response.status_code, 200)
        fuel_stops = response.json()["fuel_stops"]
        matches = [s for s in fuel_stops if s["price_per_gallon"] == 2.75]
        self.assertEqual(len(matches), 1)
        self.assertEqual(len(fuel_stops), 1)
