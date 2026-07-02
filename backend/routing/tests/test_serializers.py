from django.test import SimpleTestCase

from routing.client import Coordinates
from routing.serializers import RouteRequestSerializer


class RouteRequestSerializerTests(SimpleTestCase):
    def test_accepts_free_text_locations(self):
        serializer = RouteRequestSerializer(data={"start": "Chicago, IL", "end": "Dallas, TX"})

        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["start"], "Chicago, IL")
        self.assertEqual(serializer.validated_data["end"], "Dallas, TX")

    def test_accepts_coordinate_locations(self):
        serializer = RouteRequestSerializer(data={
            "start": {"lat": 41.8781, "lng": -87.6298},
            "end": {"lat": 32.7767, "lng": -96.7970},
        })

        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["start"], Coordinates(lat=41.8781, lng=-87.6298))

    def test_accepts_mixed_text_and_coordinates(self):
        serializer = RouteRequestSerializer(data={
            "start": "Chicago, IL",
            "end": {"lat": 32.7767, "lng": -96.7970},
        })

        self.assertTrue(serializer.is_valid())

    def test_rejects_missing_fields(self):
        serializer = RouteRequestSerializer(data={"start": "Chicago, IL"})

        self.assertFalse(serializer.is_valid())
        self.assertIn("end", serializer.errors)

    def test_rejects_empty_string_location(self):
        serializer = RouteRequestSerializer(data={"start": "  ", "end": "Dallas, TX"})

        self.assertFalse(serializer.is_valid())

    def test_rejects_coordinates_missing_lng(self):
        serializer = RouteRequestSerializer(data={"start": {"lat": 41.8781}, "end": "Dallas, TX"})

        self.assertFalse(serializer.is_valid())

    def test_rejects_out_of_range_latitude(self):
        serializer = RouteRequestSerializer(data={
            "start": {"lat": 95.0, "lng": -87.6298},
            "end": "Dallas, TX",
        })

        self.assertFalse(serializer.is_valid())

    def test_rejects_out_of_range_longitude(self):
        serializer = RouteRequestSerializer(data={
            "start": {"lat": 41.8781, "lng": 200.0},
            "end": "Dallas, TX",
        })

        self.assertFalse(serializer.is_valid())

    def test_rejects_non_numeric_coordinates(self):
        serializer = RouteRequestSerializer(data={
            "start": {"lat": "north", "lng": -87.6298},
            "end": "Dallas, TX",
        })

        self.assertFalse(serializer.is_valid())

    def test_rejects_wrong_type_location(self):
        serializer = RouteRequestSerializer(data={"start": 12345, "end": "Dallas, TX"})

        self.assertFalse(serializer.is_valid())
