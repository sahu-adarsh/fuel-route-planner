"""
Live smoke tests against the real OpenRouteService API.

Not run by default - manage.py test skips these unless
RUN_LIVE_SMOKE_TESTS=1 is set, per docs/testing.md ("not run on every CI
build - run manually or on a schedule") and docs/risks.md R4 (respecting
ORS's free-tier rate limit). Their purpose is narrow: catch drift in the
provider's response shape, which is exactly what the mocked test suite
can't detect since it never talks to the real API.

Run explicitly with:
    RUN_LIVE_SMOKE_TESTS=1 python manage.py test routing.tests.test_smoke
"""
import os
import unittest

from django.test import SimpleTestCase

from routing.client import Coordinates, OpenRouteServiceClient

_SKIP_REASON = "live smoke test - set RUN_LIVE_SMOKE_TESTS=1 to run against the real ORS API"
_RUN_LIVE = bool(os.environ.get("RUN_LIVE_SMOKE_TESTS"))


@unittest.skipUnless(_RUN_LIVE, _SKIP_REASON)
class LiveGeocodeSmokeTest(SimpleTestCase):
    def test_resolves_a_known_us_city(self):
        client = OpenRouteServiceClient()

        coords = client.resolve_location("Chicago, IL")

        self.assertIsInstance(coords, Coordinates)
        self.assertAlmostEqual(coords.lat, 41.88, delta=0.5)
        self.assertAlmostEqual(coords.lng, -87.63, delta=0.5)


@unittest.skipUnless(_RUN_LIVE, _SKIP_REASON)
class LiveDirectionsSmokeTest(SimpleTestCase):
    def test_returns_a_sane_route_between_two_known_points(self):
        client = OpenRouteServiceClient()
        chicago = Coordinates(lat=41.8781, lng=-87.6298)
        dallas = Coordinates(lat=32.7767, lng=-96.7970)

        route = client.get_route(chicago, dallas)

        # Chicago-Dallas is ~920-1000 driving miles depending on route -
        # a wide but meaningful sanity band, not an exact match, since
        # ORS's chosen path can vary run to run.
        self.assertGreater(route.distance_miles, 800)
        self.assertLess(route.distance_miles, 1200)
        self.assertGreater(route.duration_hours, 0)
        self.assertEqual(route.geometry["type"], "LineString")
        self.assertGreater(len(route.geometry["coordinates"]), 1)
