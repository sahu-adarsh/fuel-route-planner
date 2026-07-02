import random

from django.test import SimpleTestCase

from optimization.exceptions import InfeasibleRouteError
from optimization.refueling import Stop, dp_min_cost, greedy_refuel, naive_min_cost

MAX_RANGE = 500.0
MPG = 10.0


class ZeroStopTests(SimpleTestCase):
    def test_trip_shorter_than_range_needs_no_stops(self):
        stops = [Stop(position_miles=100, price_per_gallon=3.00)]

        plan = greedy_refuel(stops, total_distance_miles=300, max_range_miles=MAX_RANGE, efficiency_mpg=MPG)

        self.assertEqual(plan.purchases, [])
        self.assertEqual(plan.total_cost, 0.0)

    def test_trip_of_exactly_the_max_range_needs_no_stops(self):
        plan = greedy_refuel([], total_distance_miles=MAX_RANGE, max_range_miles=MAX_RANGE, efficiency_mpg=MPG)

        self.assertEqual(plan.purchases, [])
        self.assertEqual(plan.total_cost, 0.0)


class SingleStopTests(SimpleTestCase):
    def test_trip_requiring_exactly_one_stop(self):
        stop = Stop(position_miles=400, price_per_gallon=3.00)

        plan = greedy_refuel([stop], total_distance_miles=700, max_range_miles=MAX_RANGE, efficiency_mpg=MPG)

        # Needs (700 - 400) - (500 - 400) = 200 extra miles of range = 20 gallons.
        self.assertEqual(len(plan.purchases), 1)
        self.assertAlmostEqual(plan.purchases[0].gallons, 20.0)
        self.assertAlmostEqual(plan.total_cost, 60.0)


class MultiStopTests(SimpleTestCase):
    def test_fills_up_completely_when_nothing_cheaper_is_ahead(self):
        """A > B in price order along the route, with B cheaper than
        anything reachable from it - greedy should skip straight past A
        (going to B is strictly better) then fill completely at B rather
        than topping up just enough to reach the next stop."""
        stops = [
            Stop(position_miles=200, price_per_gallon=3.00, payload="A"),
            Stop(position_miles=400, price_per_gallon=2.50, payload="B"),
            Stop(position_miles=700, price_per_gallon=4.00, payload="C"),
            Stop(position_miles=900, price_per_gallon=3.50, payload="D"),
        ]

        plan = greedy_refuel(stops, total_distance_miles=1000, max_range_miles=MAX_RANGE, efficiency_mpg=MPG)

        self.assertEqual([p.stop.payload for p in plan.purchases], ["B", "D"])
        self.assertAlmostEqual(plan.purchases[0].gallons, 40.0)  # topped up to a full tank at B
        self.assertAlmostEqual(plan.purchases[1].gallons, 10.0)  # just enough to finish from D
        self.assertAlmostEqual(plan.total_cost, 40 * 2.50 + 10 * 3.50)

    def test_greedy_dp_and_naive_agree_on_the_fill_up_scenario(self):
        stops = [
            Stop(position_miles=200, price_per_gallon=3.00),
            Stop(position_miles=400, price_per_gallon=2.50),
            Stop(position_miles=700, price_per_gallon=4.00),
            Stop(position_miles=900, price_per_gallon=3.50),
        ]

        greedy_cost = greedy_refuel(stops, 1000, MAX_RANGE, MPG).total_cost
        dp_cost = dp_min_cost(stops, 1000, MAX_RANGE, MPG)
        naive_cost = naive_min_cost(stops, 1000, MAX_RANGE, MPG)

        self.assertAlmostEqual(greedy_cost, dp_cost, places=6)
        self.assertAlmostEqual(greedy_cost, naive_cost, places=6)


class InfeasibleRouteTests(SimpleTestCase):
    def test_gap_larger_than_range_raises(self):
        stops = [
            Stop(position_miles=100, price_per_gallon=3.00),
            Stop(position_miles=700, price_per_gallon=3.00),  # 600 mile gap from the first stop
        ]

        with self.assertRaises(InfeasibleRouteError) as ctx:
            greedy_refuel(stops, total_distance_miles=800, max_range_miles=MAX_RANGE, efficiency_mpg=MPG)

        self.assertAlmostEqual(ctx.exception.gap_start_miles, 100.0)
        self.assertAlmostEqual(ctx.exception.gap_end_miles, 700.0)

    def test_dp_and_naive_agree_route_is_infeasible(self):
        stops = [
            Stop(position_miles=100, price_per_gallon=3.00),
            Stop(position_miles=700, price_per_gallon=3.00),
        ]

        self.assertIsNone(dp_min_cost(stops, 800, MAX_RANGE, MPG))
        self.assertIsNone(naive_min_cost(stops, 800, MAX_RANGE, MPG))

    def test_gap_from_origin_raises(self):
        stops = [Stop(position_miles=600, price_per_gallon=3.00)]

        with self.assertRaises(InfeasibleRouteError) as ctx:
            greedy_refuel(stops, total_distance_miles=700, max_range_miles=MAX_RANGE, efficiency_mpg=MPG)

        self.assertEqual(ctx.exception.gap_start_miles, 0.0)


class BoundaryTests(SimpleTestCase):
    def test_stop_exactly_at_max_range_is_reachable(self):
        stop = Stop(position_miles=MAX_RANGE, price_per_gallon=3.00)

        plan = greedy_refuel([stop], total_distance_miles=MAX_RANGE + 50, max_range_miles=MAX_RANGE, efficiency_mpg=MPG)

        self.assertEqual(len(plan.purchases), 1)

    def test_price_ties_break_toward_the_nearer_station(self):
        stops = [
            Stop(position_miles=300, price_per_gallon=3.00, payload="near"),
            Stop(position_miles=450, price_per_gallon=3.00, payload="far"),
        ]

        plan = greedy_refuel(stops, total_distance_miles=900, max_range_miles=MAX_RANGE, efficiency_mpg=MPG)

        # Both are reachable from the origin at the same price; the algorithm
        # should head for the nearer one deterministically rather than
        # relying on incidental list order, then top up there before moving on.
        self.assertEqual([p.stop.payload for p in plan.purchases], ["near", "far"])
        self.assertAlmostEqual(plan.total_cost, 120.0)


class RandomizedCrossCheckTests(SimpleTestCase):
    """The highest-value tests in this module: generate random small
    scenarios and cross-check the independently-implemented algorithms,
    per docs/testing.md."""

    def test_naive_and_greedy_agree_exactly_on_random_scenarios(self):
        """naive_min_cost is a genuine exhaustive search (see its
        docstring), so this is the strongest possible check on
        greedy_refuel - the algorithm this project actually ships."""
        rng = random.Random(1234)

        for _ in range(200):
            n = rng.randint(0, 8)
            total_distance = rng.uniform(50, 1500)
            positions = sorted(rng.uniform(1, total_distance - 1) for _ in range(n)) if total_distance > 2 else []
            stops = [Stop(position_miles=p, price_per_gallon=round(rng.uniform(2.0, 5.0), 3)) for p in positions]

            naive_cost = naive_min_cost(stops, total_distance, MAX_RANGE, MPG)

            if naive_cost is None:
                with self.assertRaises(InfeasibleRouteError):
                    greedy_refuel(stops, total_distance, MAX_RANGE, MPG)
            else:
                greedy_cost = greedy_refuel(stops, total_distance, MAX_RANGE, MPG).total_cost
                self.assertAlmostEqual(naive_cost, greedy_cost, places=4)

    def test_dp_never_undercuts_the_true_optimum(self):
        """dp_min_cost isn't guaranteed tight (see its docstring's scope
        limitation), but it always represents a real, achievable plan, so
        it can never claim a lower cost than the true optimum - and it
        must still agree with everyone on whether a route is feasible."""
        rng = random.Random(5678)

        for _ in range(200):
            n = rng.randint(0, 8)
            total_distance = rng.uniform(50, 1500)
            positions = sorted(rng.uniform(1, total_distance - 1) for _ in range(n)) if total_distance > 2 else []
            stops = [Stop(position_miles=p, price_per_gallon=round(rng.uniform(2.0, 5.0), 3)) for p in positions]

            naive_cost = naive_min_cost(stops, total_distance, MAX_RANGE, MPG)
            dp_cost = dp_min_cost(stops, total_distance, MAX_RANGE, MPG)

            if naive_cost is None:
                self.assertIsNone(dp_cost)
            else:
                self.assertIsNotNone(dp_cost)
                self.assertGreaterEqual(dp_cost, naive_cost - 1e-6)
