from django.test import SimpleTestCase

from stations.geocoding import lookup


class LookupTests(SimpleTestCase):
    def test_known_city_state_resolves(self):
        coords = lookup("Seymour", "IN")

        self.assertIsNotNone(coords)
        lat, lng = coords
        self.assertAlmostEqual(lat, 38.959, places=2)
        self.assertAlmostEqual(lng, -85.890, places=2)

    def test_lookup_is_case_and_whitespace_insensitive(self):
        self.assertEqual(lookup("Seymour", "IN"), lookup("  SEYMOUR  ", " in "))

    def test_unknown_city_state_returns_none(self):
        self.assertIsNone(lookup("Nonexistentville", "ZZ"))
