import csv
import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from stations.management.commands.load_fuel_stations import Command
from stations.models import FuelStation


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["OPIS Truckstop ID", "Truckstop Name", "Address", "City", "State", "Rack ID", "Retail Price"]
        )
        writer.writerows(rows)


class ReadAndCleanTests(TestCase):
    def test_filters_non_us_rows_and_cleans_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "fuel.csv"
            write_csv(csv_path, [
                ["1", "Test Stop", "I-90, EXIT 1 &amp; US-12", "Chicago", "IL", "100", "3.50"],
                ["2", "Canada Stop", "Hwy 1", "Toronto", "ON", "200", "1.20"],
                ["3", "Whitespace Stop", "Main St", "  Dallas  ", " TX ", "300", "3.10"],
            ])

            cleaned = Command()._read_and_clean(csv_path)

        self.assertEqual(len(cleaned), 2)  # the Canadian row is dropped
        self.assertEqual(cleaned[0]["address"], "I-90, EXIT 1 & US-12")  # HTML-unescaped
        self.assertEqual(cleaned[1]["city"], "Dallas")  # whitespace stripped
        self.assertEqual(cleaned[1]["state"], "TX")


class DedupTests(TestCase):
    def test_keeps_minimum_price_and_first_seen_name(self):
        rows = [
            {"opis_id": 1, "name": "Original Name", "address": "A", "city": "X",
             "state": "IL", "rack_id": "100", "price": 3.55},
            {"opis_id": 1, "name": "Alias Name", "address": "A", "city": "X",
             "state": "IL", "rack_id": "200", "price": 3.21},
            {"opis_id": 1, "name": "Another Alias", "address": "A", "city": "X",
             "state": "IL", "rack_id": "300", "price": 3.80},
        ]

        by_id = Command()._dedup(rows)

        self.assertEqual(len(by_id), 1)
        station = by_id[1]
        self.assertEqual(station["price"], 3.21)
        self.assertEqual(station["rack_id"], "200")  # rack_id follows the min-price row
        self.assertEqual(station["name"], "Original Name")  # first-seen name kept


class GeocodeTests(TestCase):
    def test_resolvable_and_unresolvable_are_separated(self):
        rows_by_id = {
            1: {"opis_id": 1, "name": "Real City Stop", "city": "Chicago", "state": "IL"},
            2: {"opis_id": 2, "name": "Nowhere Stop", "city": "Nonexistentville", "state": "IL"},
        }

        geocoded, unresolved = Command()._geocode(rows_by_id)

        self.assertEqual(len(geocoded), 1)
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["name"], "Nowhere Stop")
        self.assertIn("latitude", geocoded[0])
        self.assertIn("longitude", geocoded[0])


class LoadFuelStationsIntegrationTests(TestCase):
    def test_end_to_end_ingestion(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "fuel.csv"
            export_path = Path(tmp) / "fuel_stations.json"
            write_csv(csv_path, [
                ["10", "Chicago Stop", "Main St", "Chicago", "IL", "100", "3.550"],
                ["10", "Chicago Stop Alias", "Main St", "Chicago", "IL", "150", "3.210"],
                ["20", "Toronto Stop", "Hwy 1", "Toronto", "ON", "200", "1.200"],
                ["30", "Nowhere Stop", "Rural Rd", "Nonexistentville", "IL", "300", "3.990"],
            ])

            call_command("load_fuel_stations", str(csv_path), "--export", str(export_path))

            self.assertEqual(FuelStation.objects.count(), 1)  # only the Chicago stop survives
            station = FuelStation.objects.get(opis_id=10)
            self.assertAlmostEqual(float(station.price_per_gallon), 3.21, places=3)
            self.assertIsNotNone(station.latitude)

            with open(export_path) as f:
                exported = json.load(f)
            self.assertEqual(len(exported), 1)
            self.assertEqual(exported[0]["opis_id"], 10)
