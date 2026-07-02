import json
from pathlib import Path
from unittest.mock import MagicMock

import requests
from django.test import SimpleTestCase

from routing.client import Coordinates, OpenRouteServiceClient
from routing.exceptions import UnresolvableLocationError, UpstreamRoutingError

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text())


def _ok_response(json_data):
    response = MagicMock()
    response.json.return_value = json_data
    response.raise_for_status.return_value = None
    return response


def _http_error_response(error_body):
    """A response whose raise_for_status() raises an HTTPError carrying a
    real ORS-style error body, e.g. {"error": {"code": 2010, "message":
    "Could not find routable point..."}}."""
    error_response = MagicMock()
    error_response.json.return_value = error_body
    response = MagicMock()
    response.raise_for_status.side_effect = requests.HTTPError(response=error_response)
    return response


class ResolveLocationTests(SimpleTestCase):
    def setUp(self):
        self.session = MagicMock()
        self.client = OpenRouteServiceClient(api_key="test-key", session=self.session)

    def test_coordinates_pass_through_without_a_network_call(self):
        coords = Coordinates(lat=41.8781, lng=-87.6298)

        result = self.client.resolve_location(coords)

        self.assertIs(result, coords)
        self.session.get.assert_not_called()

    def test_free_text_is_geocoded(self):
        self.session.get.return_value = _ok_response(load_fixture("geocode_response.json"))

        result = self.client.resolve_location("Chicago, IL")

        self.assertAlmostEqual(result.lat, 41.87897, places=4)
        self.assertAlmostEqual(result.lng, -87.66063, places=4)
        self.session.get.assert_called_once()

    def test_no_geocode_match_raises_unresolvable(self):
        self.session.get.return_value = _ok_response({"features": []})

        with self.assertRaises(UnresolvableLocationError):
            self.client.resolve_location("asdlkjaslkdj not a real place")

    def test_geocode_outside_us_raises_unresolvable(self):
        fixture = load_fixture("geocode_response.json")
        fixture["features"][0]["properties"]["country_a"] = "CAN"
        self.session.get.return_value = _ok_response(fixture)

        with self.assertRaises(UnresolvableLocationError):
            self.client.resolve_location("Toronto, ON")

    def test_state_level_match_raises_unresolvable_with_a_clear_message(self):
        """A bare state/county/country name geocodes fine but its centroid
        is rarely near a routable road - reject it here, before the
        directions call fails later with an opaque 404 (the actual bug
        this guards against: 'iowa' -> Pelias region match -> ORS 404)."""
        fixture = load_fixture("geocode_response.json")
        fixture["features"][0]["properties"]["layer"] = "region"
        fixture["features"][0]["properties"]["name"] = "Iowa"
        self.session.get.return_value = _ok_response(fixture)

        with self.assertRaises(UnresolvableLocationError) as ctx:
            self.client.resolve_location("iowa")

        message = str(ctx.exception)
        self.assertIn("whole state", message)
        self.assertIn("iowa", message)

    def test_county_level_match_raises_unresolvable(self):
        fixture = load_fixture("geocode_response.json")
        fixture["features"][0]["properties"]["layer"] = "county"
        self.session.get.return_value = _ok_response(fixture)

        with self.assertRaises(UnresolvableLocationError) as ctx:
            self.client.resolve_location("cook county")

        self.assertIn("whole county", str(ctx.exception))

    def test_locality_layer_is_accepted(self):
        fixture = load_fixture("geocode_response.json")
        fixture["features"][0]["properties"]["layer"] = "locality"
        self.session.get.return_value = _ok_response(fixture)

        result = self.client.resolve_location("Chicago, IL")

        self.assertIsInstance(result, Coordinates)

    def test_geocode_network_failure_raises_upstream_error(self):
        self.session.get.side_effect = requests.ConnectionError("boom")

        with self.assertRaises(UpstreamRoutingError):
            self.client.resolve_location("Chicago, IL")

    def test_geocode_http_error_surfaces_ors_error_message(self):
        self.session.get.return_value = _http_error_response(
            {"error": {"code": 500, "message": "Rate limit exceeded"}}
        )

        with self.assertRaises(UpstreamRoutingError) as ctx:
            self.client.resolve_location("Chicago, IL")

        self.assertIn("Rate limit exceeded", str(ctx.exception))

    def test_missing_api_key_raises_upstream_error(self):
        client = OpenRouteServiceClient(api_key="", session=self.session)

        with self.assertRaises(UpstreamRoutingError):
            client.resolve_location("Chicago, IL")

        self.session.get.assert_not_called()


class GetRouteTests(SimpleTestCase):
    def setUp(self):
        self.session = MagicMock()
        self.client = OpenRouteServiceClient(api_key="test-key", session=self.session)
        self.start = Coordinates(lat=41.8781, lng=-87.6298)
        self.end = Coordinates(lat=32.7767, lng=-96.7970)

    def test_parses_distance_duration_and_geometry(self):
        self.session.post.return_value = _ok_response(load_fixture("directions_response.json"))

        result = self.client.get_route(self.start, self.end)

        self.assertAlmostEqual(result.distance_miles, 971.0, places=1)
        self.assertAlmostEqual(result.duration_hours, 21.58, places=1)
        self.assertEqual(result.geometry["type"], "LineString")
        self.assertGreaterEqual(len(result.geometry["coordinates"]), 2)

    def test_sends_coordinates_as_lng_lat_pairs(self):
        self.session.post.return_value = _ok_response(load_fixture("directions_response.json"))

        self.client.get_route(self.start, self.end)

        _, kwargs = self.session.post.call_args
        self.assertEqual(
            kwargs["json"]["coordinates"],
            [[self.start.lng, self.start.lat], [self.end.lng, self.end.lat]],
        )

    def test_uses_driving_hgv_profile_by_default(self):
        self.session.post.return_value = _ok_response(load_fixture("directions_response.json"))

        self.client.get_route(self.start, self.end)

        url = self.session.post.call_args[0][0]
        self.assertIn("/v2/directions/driving-hgv/geojson", url)

    def test_network_failure_raises_upstream_error(self):
        self.session.post.side_effect = requests.Timeout("boom")

        with self.assertRaises(UpstreamRoutingError):
            self.client.get_route(self.start, self.end)

    def test_unexpected_response_shape_raises_upstream_error(self):
        self.session.post.return_value = _ok_response({"features": []})

        with self.assertRaises(UpstreamRoutingError):
            self.client.get_route(self.start, self.end)

    def test_unroutable_point_surfaces_ors_error_message(self):
        """The actual failure behind the reported bug: a coordinate with
        no nearby road gets a 404 from ORS with a specific reason in the
        body - that reason should reach the user, not a raw exception
        dump (real body captured from a live call, see the commit this
        test was added in)."""
        self.session.post.return_value = _http_error_response({
            "error": {
                "code": 2010,
                "message": (
                    "Could not find routable point within a radius of "
                    "350.0 meters of specified coordinate 1: -93.5 42.04."
                ),
            }
        })

        with self.assertRaises(UpstreamRoutingError) as ctx:
            self.client.get_route(self.start, self.end)

        self.assertIn("Could not find routable point", str(ctx.exception))
