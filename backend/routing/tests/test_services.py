from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from optimization.corridor import filter_corridor
from optimization.exceptions import InfeasibleRouteError
from optimization.refueling import Stop, greedy_refuel
from routing.client import Coordinates, DirectionsResult
from routing.exceptions import (
    IdenticalLocationsError,
    NoFuelDataInCorridorError,
    UnresolvableLocationError,
)
from routing.services import plan_route

# A simple straight route along the equator - real corridor-matching
# precision is already covered by optimization's own test suite; these
# tests only need *some* consistent geometry to check the orchestration
# wiring (right functions called with the right arguments, response
# shaped correctly). Densely sampled (~3.5mi between points) so stations
# "on" the route are actually near a vertex - nearest_vertex_distance is
# a discrete approximation (docs/optimizations.md 4.7), and a 2-point
# route would place a lot of empty space between its only two vertices.
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


def _mock_client(distance_miles, resolve_side_effect=None):
    client = MagicMock()
    if resolve_side_effect is not None:
        client.resolve_location.side_effect = resolve_side_effect
    else:
        # Coordinates pass through unchanged; text resolves to *some*
        # point that varies with the text, so two different location
        # strings don't collide and falsely trip the identical-locations
        # check.
        client.resolve_location.side_effect = lambda loc: (
            loc if isinstance(loc, Coordinates) else Coordinates(lat=0.0, lng=float(len(loc)))
        )
    client.get_route.return_value = DirectionsResult(
        distance_miles=distance_miles, duration_hours=distance_miles / 60, geometry=ROUTE_GEOMETRY
    )
    return client


class ExternalCallBudgetTests(SimpleTestCase):
    """docs/api-design.md: 1 call for coords+coords, 2 for one text, 3 for
    text+text."""

    def setUp(self):
        self.stations_patch = patch("routing.services.load_stations", return_value=STATIONS)
        self.stations_patch.start()
        self.addCleanup(self.stations_patch.stop)

    def _run(self, start, end, distance_miles=300.0):
        client = _mock_client(distance_miles)
        with patch("routing.services.OpenRouteServiceClient", return_value=client):
            result = plan_route(start, end)
        return result, client

    def test_both_coordinates_costs_one_call(self):
        result, client = self._run(Coordinates(lat=0, lng=0), Coordinates(lat=0, lng=1))
        self.assertEqual(result.external_calls_used, 1)
        client.get_route.assert_called_once()

    def test_one_text_one_coordinates_costs_two_calls(self):
        result, _ = self._run("Somewhere", Coordinates(lat=0, lng=1))
        self.assertEqual(result.external_calls_used, 2)

    def test_both_text_costs_three_calls(self):
        result, _ = self._run("Somewhere", "Somewhere Else")
        self.assertEqual(result.external_calls_used, 3)


class ShortTripTests(SimpleTestCase):
    def setUp(self):
        self.stations_patch = patch("routing.services.load_stations", return_value=STATIONS)
        self.stations_patch.start()
        self.addCleanup(self.stations_patch.stop)

    def test_trip_within_range_needs_no_stops(self):
        client = _mock_client(distance_miles=300.0)
        with patch("routing.services.OpenRouteServiceClient", return_value=client):
            result = plan_route(Coordinates(lat=0, lng=0), Coordinates(lat=0, lng=1))

        self.assertFalse(result.stops_required)
        self.assertEqual(result.fuel_stops, [])
        # Reference cost per docs/assumptions.md A5: cheapest in-corridor price.
        self.assertAlmostEqual(result.total_fuel_cost_usd, 300.0 / 10 * 3.00, places=2)


class LongTripTests(SimpleTestCase):
    def setUp(self):
        self.stations_patch = patch("routing.services.load_stations", return_value=STATIONS)
        self.stations_patch.start()
        self.addCleanup(self.stations_patch.stop)

    def test_matches_independently_computed_plan(self):
        distance_miles = 600.0
        client = _mock_client(distance_miles=distance_miles)
        with patch("routing.services.OpenRouteServiceClient", return_value=client):
            result = plan_route(Coordinates(lat=0, lng=0), Coordinates(lat=0, lng=8.7))

        route_points = [(lat, lng) for lng, lat in ROUTE_GEOMETRY["coordinates"]]
        candidates = filter_corridor(route_points, STATIONS, buffer_miles=10.0)
        stops = [
            Stop(position_miles=cs.distance_along_route_miles, price_per_gallon=cs.station["price_per_gallon"])
            for cs in candidates
        ]
        expected_plan = greedy_refuel(stops, distance_miles, max_range_miles=500.0, efficiency_mpg=10.0)

        self.assertTrue(result.stops_required)
        self.assertAlmostEqual(result.total_fuel_cost_usd, expected_plan.total_cost, places=2)
        self.assertEqual(len(result.fuel_stops), len(expected_plan.purchases))

    def test_fuel_stop_fields_are_shaped_per_api_contract(self):
        client = _mock_client(distance_miles=600.0)
        with patch("routing.services.OpenRouteServiceClient", return_value=client):
            result = plan_route(Coordinates(lat=0, lng=0), Coordinates(lat=0, lng=8.7))

        self.assertGreater(len(result.fuel_stops), 0)
        stop = result.fuel_stops[0]
        for key in ("name", "city", "state", "lat", "lng", "price_per_gallon",
                    "gallons_purchased", "cumulative_distance_miles"):
            self.assertIn(key, stop)


class NoFuelDataTests(SimpleTestCase):
    def test_long_trip_with_no_candidates_raises(self):
        with patch("routing.services.load_stations", return_value=[]):
            client = _mock_client(distance_miles=600.0)
            with patch("routing.services.OpenRouteServiceClient", return_value=client):
                with self.assertRaises(NoFuelDataInCorridorError):
                    plan_route(Coordinates(lat=0, lng=0), Coordinates(lat=0, lng=8.7))

    def test_short_trip_with_no_candidates_reports_zero_cost_not_an_error(self):
        with patch("routing.services.load_stations", return_value=[]):
            client = _mock_client(distance_miles=300.0)
            with patch("routing.services.OpenRouteServiceClient", return_value=client):
                result = plan_route(Coordinates(lat=0, lng=0), Coordinates(lat=0, lng=1))

        self.assertFalse(result.stops_required)
        self.assertEqual(result.total_fuel_cost_usd, 0.0)


class InfeasibleRouteTests(SimpleTestCase):
    def test_fuel_gap_larger_than_range_propagates(self):
        far_apart_stations = [
            {"opis_id": 1, "name": "A", "city": "A", "state": "IL",
             "price_per_gallon": 3.00, "latitude": 0.0, "longitude": 0.5},
            {"opis_id": 2, "name": "B", "city": "B", "state": "TX",
             "price_per_gallon": 3.00, "latitude": 0.0, "longitude": 8.2},
        ]
        # Gap between A and B is ~(8.2-0.5)*69 =~ 531mi, safely over the
        # 500mi range.
        with patch("routing.services.load_stations", return_value=far_apart_stations):
            client = _mock_client(distance_miles=900.0)
            with patch("routing.services.OpenRouteServiceClient", return_value=client):
                with self.assertRaises(InfeasibleRouteError):
                    plan_route(Coordinates(lat=0, lng=0), Coordinates(lat=0, lng=8.7))


class IdenticalLocationsTests(SimpleTestCase):
    def test_identical_text_raises_before_any_resolving(self):
        client = _mock_client(distance_miles=300.0)
        with patch("routing.services.OpenRouteServiceClient", return_value=client):
            with self.assertRaises(IdenticalLocationsError):
                plan_route("Chicago, IL", "chicago, il")

        client.resolve_location.assert_not_called()

    def test_identical_coordinates_raise(self):
        client = _mock_client(distance_miles=300.0)
        with patch("routing.services.OpenRouteServiceClient", return_value=client):
            with self.assertRaises(IdenticalLocationsError):
                plan_route(Coordinates(lat=41.0, lng=-87.0), Coordinates(lat=41.0, lng=-87.0))

    def test_different_text_resolving_to_the_same_place_raises(self):
        client = _mock_client(distance_miles=300.0)
        client.resolve_location.side_effect = lambda loc: Coordinates(lat=41.0, lng=-87.0)
        with patch("routing.services.OpenRouteServiceClient", return_value=client):
            with self.assertRaises(IdenticalLocationsError):
                plan_route("Chicago, IL", "Also Chicago Somehow")


class UnresolvableLocationTests(SimpleTestCase):
    def test_propagates_from_the_client(self):
        client = _mock_client(distance_miles=300.0)
        client.resolve_location.side_effect = UnresolvableLocationError("nope")
        with patch("routing.services.OpenRouteServiceClient", return_value=client):
            with self.assertRaises(UnresolvableLocationError):
                plan_route("Nowhereville", Coordinates(lat=0, lng=1))
