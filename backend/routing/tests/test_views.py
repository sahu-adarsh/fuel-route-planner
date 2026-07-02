from unittest.mock import patch

from rest_framework.test import APITestCase

from routing.client import Coordinates, DirectionsResult
from routing.exceptions import UnresolvableLocationError, UpstreamRoutingError

ROUTE_URL = "/api/v1/route/"

ROUTE_GEOMETRY = {
    "type": "LineString",
    "coordinates": [[round(i * 0.05, 4), 0.0] for i in range(175)],  # lng 0 -> 8.7
}

STATIONS = [
    {"opis_id": 1, "name": "Cheap Stop", "city": "Alpha", "state": "IL",
     "price_per_gallon": 3.00, "latitude": 0.0, "longitude": 4.0},
    {"opis_id": 2, "name": "Pricier Stop", "city": "Beta", "state": "TX",
     "price_per_gallon": 3.50, "latitude": 0.0, "longitude": 7.0},
]


def _client_returning(distance_miles, resolve_side_effect=None):
    from unittest.mock import MagicMock

    client = MagicMock()
    client.resolve_location.side_effect = resolve_side_effect or (
        lambda loc: loc if isinstance(loc, Coordinates) else Coordinates(lat=0.0, lng=float(len(loc)))
    )
    client.get_route.return_value = DirectionsResult(
        distance_miles=distance_miles, duration_hours=distance_miles / 60, geometry=ROUTE_GEOMETRY
    )
    return client


class SuccessResponseTests(APITestCase):
    def setUp(self):
        patcher = patch("routing.services.load_stations", return_value=STATIONS)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_short_trip_response_shape(self):
        client = _client_returning(distance_miles=300.0)
        with patch("routing.services.OpenRouteServiceClient", return_value=client):
            response = self.client.post(
                ROUTE_URL, {"start": {"lat": 0, "lng": 0}, "end": {"lat": 0, "lng": 1}}, format="json"
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        for key in ("distance_miles", "duration_hours", "route_geometry", "stops_required",
                    "fuel_stops", "total_fuel_cost_usd", "external_calls_used"):
            self.assertIn(key, body)
        self.assertFalse(body["stops_required"])
        self.assertEqual(body["fuel_stops"], [])
        self.assertEqual(body["external_calls_used"], 1)

    def test_long_trip_returns_populated_fuel_stops(self):
        client = _client_returning(distance_miles=600.0)
        with patch("routing.services.OpenRouteServiceClient", return_value=client):
            response = self.client.post(
                ROUTE_URL, {"start": {"lat": 0, "lng": 0}, "end": {"lat": 0, "lng": 8.7}}, format="json"
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["stops_required"])
        self.assertGreater(len(body["fuel_stops"]), 0)
        stop = body["fuel_stops"][0]
        for key in ("name", "city", "state", "lat", "lng", "price_per_gallon",
                    "gallons_purchased", "cumulative_distance_miles"):
            self.assertIn(key, stop)

    def test_free_text_input_costs_three_calls(self):
        client = _client_returning(distance_miles=300.0)
        with patch("routing.services.OpenRouteServiceClient", return_value=client):
            response = self.client.post(
                ROUTE_URL, {"start": "Chicago, IL", "end": "Dallas, TX"}, format="json"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["external_calls_used"], 3)


class ValidationErrorTests(APITestCase):
    def test_missing_field_returns_validation_error(self):
        response = self.client.post(ROUTE_URL, {"start": "Chicago, IL"}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "validation_error")

    def test_bad_coordinate_range_returns_validation_error(self):
        response = self.client.post(
            ROUTE_URL, {"start": {"lat": 999, "lng": 0}, "end": "Dallas, TX"}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "validation_error")


class IdenticalLocationsErrorTests(APITestCase):
    def test_identical_locations_returns_400(self):
        response = self.client.post(
            ROUTE_URL, {"start": "Chicago, IL", "end": "chicago, il"}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "identical_locations")


class UnresolvableLocationErrorTests(APITestCase):
    def test_unresolvable_location_returns_422(self):
        client = _client_returning(
            distance_miles=300.0,
            resolve_side_effect=UnresolvableLocationError("Could not resolve location"),
        )
        with patch("routing.services.OpenRouteServiceClient", return_value=client):
            response = self.client.post(
                ROUTE_URL, {"start": "Nowhereville", "end": "Dallas, TX"}, format="json"
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "unresolvable_location")


class NoFuelDataInCorridorErrorTests(APITestCase):
    def test_returns_422(self):
        client = _client_returning(distance_miles=600.0)
        with patch("routing.services.load_stations", return_value=[]):
            with patch("routing.services.OpenRouteServiceClient", return_value=client):
                response = self.client.post(
                    ROUTE_URL, {"start": {"lat": 0, "lng": 0}, "end": {"lat": 0, "lng": 8.7}}, format="json"
                )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "no_fuel_data_in_corridor")


class InfeasibleRouteErrorTests(APITestCase):
    def test_returns_422_with_gap_details(self):
        far_apart_stations = [
            {"opis_id": 1, "name": "A", "city": "A", "state": "IL",
             "price_per_gallon": 3.00, "latitude": 0.0, "longitude": 0.5},
            {"opis_id": 2, "name": "B", "city": "B", "state": "TX",
             "price_per_gallon": 3.00, "latitude": 0.0, "longitude": 8.2},
        ]
        client = _client_returning(distance_miles=900.0)
        with patch("routing.services.load_stations", return_value=far_apart_stations):
            with patch("routing.services.OpenRouteServiceClient", return_value=client):
                response = self.client.post(
                    ROUTE_URL, {"start": {"lat": 0, "lng": 0}, "end": {"lat": 0, "lng": 8.7}}, format="json"
                )

        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["error"]["code"], "infeasible_route")
        details = body["error"]["details"]
        for key in ("gap_start_mile", "gap_end_mile", "gap_miles"):
            self.assertIn(key, details)


class UpstreamRoutingErrorTests(APITestCase):
    def test_returns_502(self):
        client = _client_returning(distance_miles=300.0)
        client.get_route.side_effect = UpstreamRoutingError("ORS timed out")
        with patch("routing.services.OpenRouteServiceClient", return_value=client):
            response = self.client.post(
                ROUTE_URL, {"start": {"lat": 0, "lng": 0}, "end": {"lat": 0, "lng": 1}}, format="json"
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"]["code"], "upstream_routing_error")
