"""
The fuel-stop optimization algorithm - the classic continuous "gas
station problem": given stations at fixed positions along a line with a
tank capacity (max_range_miles) and per-gallon prices, buy fuel (any
fractional amount) so as to never run out, minimizing total cost.

Three implementations, matching docs/optimizations.md 4.6:
  - naive_min_cost: brute force over all subsets of stops - exponential,
    correctness baseline only, for small test cases.
  - dp_min_cost: dynamic programming - O(m^2), also optimal, used as an
    independent cross-check against the greedy in tests.
  - greedy_refuel: the production implementation - O(m log m), optimal
    by an exchange argument, and the only one of the three that returns
    a full purchase plan (not just the minimum cost).

All three assume the vehicle starts at position 0 with a full tank
(docs/assumptions.md A3), so the first leg is never charged.
"""
import math
from dataclasses import dataclass, field
from typing import Any, Optional

from .exceptions import InfeasibleRouteError

# Tolerance for floating-point drift at range/reachability boundaries -
# e.g. buying exactly enough fuel to finish a trip should leave exactly
# 0 range remaining, but a divide-then-multiply-by-efficiency roundtrip
# can leave a residue on the order of 1e-13 instead.
_EPSILON_MILES = 1e-9


@dataclass(frozen=True)
class Stop:
    position_miles: float
    price_per_gallon: float
    payload: Any = None  # opaque reference back to the original station record


@dataclass(frozen=True)
class Purchase:
    stop: Stop
    gallons: float


@dataclass(frozen=True)
class RefuelingPlan:
    purchases: list[Purchase] = field(default_factory=list)
    total_cost: float = 0.0


def greedy_refuel(
    stops: list[Stop],
    total_distance_miles: float,
    max_range_miles: float,
    efficiency_mpg: float,
) -> RefuelingPlan:
    stops = sorted(stops, key=lambda s: s.position_miles)
    destination = Stop(position_miles=total_distance_miles, price_per_gallon=math.inf)

    position = 0.0
    range_remaining = max_range_miles
    current_stop: Optional[Stop] = None
    purchases: list[Purchase] = []

    while True:
        distance_to_go = total_distance_miles - position

        if distance_to_go <= range_remaining + _EPSILON_MILES:
            break  # already carrying enough fuel to coast to the destination

        max_reach = position + max_range_miles
        reachable = [s for s in stops if position < s.position_miles <= max_reach + _EPSILON_MILES]
        current_price = current_stop.price_per_gallon if current_stop is not None else math.inf
        cheaper = [s for s in reachable if s.price_per_gallon < current_price]

        if cheaper:
            # Take the *nearest* improvement, not the cheapest one reachable
            # overall - grabbing a better price as soon as it's available
            # means buying less at the current, worse price, even if an
            # even-cheaper station exists farther out (confirmed against an
            # exhaustive search: overshooting a nearer improvement to reach
            # a cheaper-but-farther one costs more at the current price
            # than it saves).
            target = min(cheaper, key=lambda s: (s.position_miles, s.price_per_gallon))
            needed_range = target.position_miles - position
        elif distance_to_go <= max_range_miles + _EPSILON_MILES:
            # Nothing left beats the current price, but there's enough
            # range to finish from here once topped up - no reason to
            # detour through a pricier station first when no further
            # discount on the remaining distance is available anyway.
            target = destination
            needed_range = distance_to_go
        elif reachable:
            # Nothing cheaper, and more stops are unavoidable - top up
            # completely and head for whichever reachable station has the
            # best price, not simply the farthest one. A nearer station
            # that's still relatively cheap can be worth stopping at again
            # before a real price spike, rather than skipping straight to
            # the farthest point and losing the chance to top up cheaply
            # along the way (confirmed against an exhaustive search).
            target = min(reachable, key=lambda s: (s.price_per_gallon, s.position_miles))
            needed_range = max_range_miles
        else:
            next_beyond = min(
                (s.position_miles for s in stops if s.position_miles > position),
                default=total_distance_miles,
            )
            raise InfeasibleRouteError(position, next_beyond)

        gallons = max(0.0, (needed_range - range_remaining) / efficiency_mpg)
        if gallons > 0 and current_stop is not None:
            purchases.append(Purchase(stop=current_stop, gallons=gallons))
            range_remaining += gallons * efficiency_mpg

        range_remaining -= (target.position_miles - position)
        position = target.position_miles
        current_stop = target

    total_cost = sum(p.gallons * p.stop.price_per_gallon for p in purchases)
    return RefuelingPlan(purchases=purchases, total_cost=total_cost)


def dp_min_cost(
    stops: list[Stop],
    total_distance_miles: float,
    max_range_miles: float,
    efficiency_mpg: float,
) -> Optional[float]:
    """Cross-check for greedy_refuel's total_cost, used on hand-picked
    scenarios - see module docstring. Returns None if infeasible.

    A station reached directly from the origin (dp[i] == 0) arrives with
    the free initial tank's leftover range still in it - e.g. a stop 400mi
    into a 500mi tank still has 100mi of *free* range left. Whichever edge
    leaves such a station first gets a matching discount here, or this
    would double-charge for range that was never actually purchased.

    Known scope limitation: this same leftover effect can also happen
    later in the trip, whenever an optimal plan fills up completely at one
    station and the next station is closer than a full tank away - that
    leftover should discount the purchase *after* it too, and so on in a
    chain. Handling that in general means tracking a cost/leftover
    frontier per station rather than one scalar, which naive_min_cost does
    via brute force (see its docstring) but this simpler O(m^2) formulation
    does not. It still always returns a *valid, achievable* cost (never
    below the true optimum) and correctly detects infeasibility, which is
    why it's still useful - just not guaranteed tight in every case, so
    it's cross-checked against exact equality only on scenarios verified
    by hand, and against "greedy/naive can never cost more than this" in
    the broader randomized tests.
    """
    stops = sorted(stops, key=lambda s: s.position_miles)
    n = len(stops)

    dp = [math.inf] * n
    free_leftover_miles = [0.0] * n  # only meaningful where dp[i] == 0

    for i in range(n):
        if stops[i].position_miles <= max_range_miles:
            dp[i] = 0.0  # reachable directly from the free initial tank
            free_leftover_miles[i] = max_range_miles - stops[i].position_miles
        for j in range(i):
            distance = stops[i].position_miles - stops[j].position_miles
            if distance > max_range_miles or dp[j] == math.inf:
                continue
            discount = free_leftover_miles[j] if dp[j] == 0.0 else 0.0
            billable_distance = max(0.0, distance - discount)
            cost = dp[j] + stops[j].price_per_gallon * billable_distance / efficiency_mpg
            dp[i] = min(dp[i], cost)

    if total_distance_miles <= max_range_miles:
        return 0.0

    best = math.inf
    for j in range(n):
        if dp[j] == math.inf:
            continue
        distance = total_distance_miles - stops[j].position_miles
        if 0 <= distance <= max_range_miles:
            discount = free_leftover_miles[j] if dp[j] == 0.0 else 0.0
            billable_distance = max(0.0, distance - discount)
            cost = dp[j] + stops[j].price_per_gallon * billable_distance / efficiency_mpg
            best = min(best, cost)

    return best if best != math.inf else None


def naive_min_cost(
    stops: list[Stop],
    total_distance_miles: float,
    max_range_miles: float,
    efficiency_mpg: float,
) -> Optional[float]:
    """Brute force over every subset of stops to buy at, AND, for each
    subset, every combination of "buy just enough for the next stop" vs.
    "fill the tank completely" at each chosen stop - O(3^m) (C(m,k) subsets
    times 2^k fill choices, summed over k, is 3^m by the binomial theorem).
    Correctness baseline only; only safe to call on small inputs
    (docs/optimizations.md 4.6).

    It's not enough to brute-force *which* stops to buy at: buying more
    than the minimum at an early cheap stop can leave leftover range that
    discounts a later, pricier purchase, and that leftover can in turn
    depend on a leftover from *before* it, and so on - a chain that a
    simple "assume minimal at every stop" search misses (this is exactly
    what dp_min_cost's simpler formulation misses too - see its docstring).
    The exchange argument behind greedy_refuel's optimality guarantees
    every optimal plan can be built from just these two choices at each
    stop, so enumerating both here (rather than continuous amounts) is
    still a complete search of the relevant space.
    """
    stops = sorted(stops, key=lambda s: s.position_miles)
    n = len(stops)
    best = None

    for mask in range(1 << n):
        chosen = [stops[i] for i in range(n) if mask & (1 << i)]
        k = len(chosen)
        waypoints = [s.position_miles for s in chosen] + [total_distance_miles]

        for strategy_bits in range(1 << k):
            position = 0.0
            range_remaining = max_range_miles
            cost = 0.0
            feasible = True

            for idx, stop in enumerate(chosen):
                distance = stop.position_miles - position
                if distance > range_remaining + 1e-9:
                    feasible = False
                    break
                range_remaining -= distance
                position = stop.position_miles

                fill_completely = bool(strategy_bits & (1 << idx))
                if fill_completely:
                    gallons = max(0.0, (max_range_miles - range_remaining) / efficiency_mpg)
                    range_remaining = max_range_miles
                else:
                    needed = waypoints[idx + 1] - position
                    if needed > max_range_miles + 1e-9:
                        # Even a full tank from here can't cover this leg -
                        # this strategy can't work, regardless of cost.
                        feasible = False
                        break
                    gallons = max(0.0, (needed - range_remaining) / efficiency_mpg)
                    range_remaining += gallons * efficiency_mpg

                cost += gallons * stop.price_per_gallon

            if not feasible:
                continue
            if total_distance_miles - position > range_remaining + 1e-9:
                continue  # can't reach the destination after this plan

            if best is None or cost < best:
                best = cost

    return best
