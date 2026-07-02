"""
Orchestrates a single /api/v1/route/ request: resolve locations, fetch
the route, filter candidate stations, run the refueling optimization,
and shape the result - see docs/api-design.md.
"""
from dataclasses import dataclass, field

from optimization.corridor import filter_corridor, haversine_miles
from optimization.refueling import Stop, greedy_refuel
from stations.data import load_stations

from .client import Coordinates, OpenRouteServiceClient
from .exceptions import IdenticalLocationsError, NoFuelDataInCorridorError

MAX_RANGE_MILES = 500.0
EFFICIENCY_MPG = 10.0
CORRIDOR_BUFFER_MILES = 10.0
IDENTICAL_LOCATION_THRESHOLD_MILES = 0.5


@dataclass
class RouteResult:
    distance_miles: float
    duration_hours: float
    geometry: dict
    stops_required: bool
    total_fuel_cost_usd: float
    external_calls_used: int
    fuel_stops: list = field(default_factory=list)


def plan_route(start_raw, end_raw) -> RouteResult:
    if _same_raw_location(start_raw, end_raw):
        raise IdenticalLocationsError()

    client = OpenRouteServiceClient()
    calls = 0

    start = client.resolve_location(start_raw)
    if isinstance(start_raw, str):
        calls += 1
    end = client.resolve_location(end_raw)
    if isinstance(end_raw, str):
        calls += 1

    if haversine_miles(start.lat, start.lng, end.lat, end.lng) < IDENTICAL_LOCATION_THRESHOLD_MILES:
        raise IdenticalLocationsError()

    route = client.get_route(start, end)
    calls += 1

    route_points = [(lat, lng) for lng, lat in route.geometry["coordinates"]]
    candidates = filter_corridor(route_points, load_stations(), buffer_miles=CORRIDOR_BUFFER_MILES)

    if route.distance_miles <= MAX_RANGE_MILES:
        return RouteResult(
            distance_miles=round(route.distance_miles, 1),
            duration_hours=round(route.duration_hours, 1),
            geometry=route.geometry,
            stops_required=False,
            fuel_stops=[],
            total_fuel_cost_usd=_reference_cost(route.distance_miles, candidates),
            external_calls_used=calls,
        )

    if not candidates:
        raise NoFuelDataInCorridorError()

    stops = [
        Stop(
            position_miles=cs.distance_along_route_miles,
            price_per_gallon=cs.station["price_per_gallon"],
            payload=cs.station,
        )
        for cs in candidates
    ]
    plan = greedy_refuel(stops, route.distance_miles, MAX_RANGE_MILES, EFFICIENCY_MPG)

    fuel_stops = [
        {
            "name": p.stop.payload["name"],
            "city": p.stop.payload["city"],
            "state": p.stop.payload["state"],
            "lat": p.stop.payload["latitude"],
            "lng": p.stop.payload["longitude"],
            "price_per_gallon": p.stop.price_per_gallon,
            "gallons_purchased": round(p.gallons, 2),
            "cumulative_distance_miles": round(p.stop.position_miles, 1),
        }
        for p in plan.purchases
    ]

    return RouteResult(
        distance_miles=round(route.distance_miles, 1),
        duration_hours=round(route.duration_hours, 1),
        geometry=route.geometry,
        stops_required=True,
        fuel_stops=fuel_stops,
        total_fuel_cost_usd=round(plan.total_cost, 2),
        external_calls_used=calls,
    )


def _same_raw_location(a, b) -> bool:
    """Cheap pre-geocoding check: catches identical input outright, saving
    the geocode calls the post-resolve haversine check can't avoid."""
    if isinstance(a, str) and isinstance(b, str):
        return a.strip().lower() == b.strip().lower()
    if isinstance(a, Coordinates) and isinstance(b, Coordinates):
        return a.lat == b.lat and a.lng == b.lng
    return False


def _reference_cost(distance_miles: float, candidates: list) -> float:
    """No stop is actually required for a trip this short, but the brief
    asks for a total cost unconditionally - report a reference figure
    using the cheapest in-corridor price, per docs/assumptions.md A5."""
    if not candidates:
        return 0.0
    cheapest_price = min(cs.station["price_per_gallon"] for cs in candidates)
    return round(distance_miles / EFFICIENCY_MPG * cheapest_price, 2)
