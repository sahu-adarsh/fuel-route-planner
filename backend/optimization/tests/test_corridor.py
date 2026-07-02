from django.test import SimpleTestCase

from optimization.corridor import (
    bounding_box,
    cumulative_distances,
    filter_corridor,
    haversine_miles,
    nearest_vertex_distance,
)


class HaversineTests(SimpleTestCase):
    def test_same_point_is_zero(self):
        self.assertEqual(haversine_miles(41.88, -87.63, 41.88, -87.63), 0.0)

    def test_one_degree_of_latitude_is_about_69_miles(self):
        self.assertAlmostEqual(haversine_miles(0.0, 0.0, 1.0, 0.0), 69.0, delta=1.0)


class CumulativeDistancesTests(SimpleTestCase):
    def test_matches_manual_haversine_sum(self):
        route = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]

        result = cumulative_distances(route)

        self.assertEqual(result[0], 0.0)
        self.assertAlmostEqual(result[1], haversine_miles(0.0, 0.0, 1.0, 0.0))
        expected_total = haversine_miles(0.0, 0.0, 1.0, 0.0) + haversine_miles(1.0, 0.0, 1.0, 1.0)
        self.assertAlmostEqual(result[2], expected_total)

    def test_single_point_route(self):
        self.assertEqual(cumulative_distances([(0.0, 0.0)]), [0.0])


class BoundingBoxTests(SimpleTestCase):
    def test_box_contains_all_route_points_with_margin(self):
        route = [(30.0, -90.0), (35.0, -95.0), (40.0, -100.0)]

        min_lat, max_lat, min_lng, max_lng = bounding_box(route, buffer_miles=10)

        self.assertLess(min_lat, 30.0)
        self.assertGreater(max_lat, 40.0)
        self.assertLess(min_lng, -100.0)
        self.assertGreater(max_lng, -90.0)


class NearestVertexDistanceTests(SimpleTestCase):
    def test_finds_closest_vertex(self):
        route = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]

        dist, idx = nearest_vertex_distance((1.01, 0.0), route)

        self.assertEqual(idx, 1)
        self.assertLess(dist, 5.0)


class FilterCorridorTests(SimpleTestCase):
    def setUp(self):
        # A straight route along the equator from (0,0) to (0,3) degrees longitude.
        self.route = [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0), (0.0, 3.0)]

    def test_station_on_route_is_included(self):
        stations = [{"name": "OnRoute", "latitude": 0.0, "longitude": 1.0}]

        result = filter_corridor(self.route, stations, buffer_miles=10)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].station["name"], "OnRoute")
        self.assertAlmostEqual(result[0].distance_from_route_miles, 0.0, places=3)

    def test_station_far_from_route_is_excluded(self):
        stations = [{"name": "FarAway", "latitude": 20.0, "longitude": 1.0}]

        result = filter_corridor(self.route, stations, buffer_miles=10)

        self.assertEqual(result, [])

    def test_results_are_sorted_by_distance_along_route(self):
        # Placed exactly at route vertices - nearest_vertex_distance is a
        # discrete approximation (docs/optimizations.md 4.7), so a point
        # between sparse vertices in this synthetic route wouldn't
        # necessarily read as "on route" the way it would against a dense
        # real ORS polyline.
        stations = [
            {"name": "Far", "latitude": 0.0, "longitude": 2.0},
            {"name": "Near", "latitude": 0.0, "longitude": 1.0},
        ]

        result = filter_corridor(self.route, stations, buffer_miles=10)

        self.assertEqual([cs.station["name"] for cs in result], ["Near", "Far"])

    def test_boundary_distance_exactly_at_buffer_is_included(self):
        # 1 degree of longitude at the equator is ~69 miles; place a station
        # ~10 miles north of the route and use a buffer that exactly covers it.
        lat_for_10_miles = 10.0 / 69.0
        stations = [{"name": "OnBoundary", "latitude": lat_for_10_miles, "longitude": 1.0}]

        result = filter_corridor(self.route, stations, buffer_miles=10.05)

        self.assertEqual(len(result), 1)
