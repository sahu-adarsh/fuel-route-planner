"""
Projects fuel stations onto a route and filters to a corridor buffer.

Pure functions, no framework/HTTP dependency - see docs/optimizations.md
4.4 and 4.7 for why a plain haversine loop is used here instead of
PostGIS or a spatial index (the candidate set is small enough that it
doesn't matter).
"""
import math
from dataclasses import dataclass
from typing import Any

EARTH_RADIUS_MILES = 3958.8
MILES_PER_DEGREE_LATITUDE = 69.0


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def cumulative_distances(route: list[tuple[float, float]]) -> list[float]:
    """route is a list of (lat, lng) polyline vertices in order.

    Returns a same-length list where result[i] is the distance in miles
    from route[0] to route[i] along the polyline.
    """
    distances = [0.0]
    for i in range(1, len(route)):
        lat1, lng1 = route[i - 1]
        lat2, lng2 = route[i]
        distances.append(distances[-1] + haversine_miles(lat1, lng1, lat2, lng2))
    return distances


def bounding_box(route: list[tuple[float, float]], buffer_miles: float) -> tuple[float, float, float, float]:
    """Returns (min_lat, max_lat, min_lng, max_lng) expanded by buffer_miles."""
    lats = [p[0] for p in route]
    lngs = [p[1] for p in route]
    avg_lat = sum(lats) / len(lats)

    lat_buffer = buffer_miles / MILES_PER_DEGREE_LATITUDE
    lng_buffer = buffer_miles / (MILES_PER_DEGREE_LATITUDE * max(math.cos(math.radians(avg_lat)), 0.01))

    return (min(lats) - lat_buffer, max(lats) + lat_buffer, min(lngs) - lng_buffer, max(lngs) + lng_buffer)


def nearest_vertex_distance(point: tuple[float, float], route: list[tuple[float, float]]) -> tuple[float, int]:
    """Returns (min_distance_miles, index_of_nearest_vertex) for point against route."""
    lat, lng = point
    best_dist = math.inf
    best_idx = 0
    for i, (vlat, vlng) in enumerate(route):
        dist = haversine_miles(lat, lng, vlat, vlng)
        if dist < best_dist:
            best_dist = dist
            best_idx = i
    return best_dist, best_idx


def _downsample_by_distance(
    route: list[tuple[float, float]],
    cum_dist: list[float],
    min_spacing_miles: float,
) -> list[int]:
    """Returns indices into route, kept at least min_spacing_miles apart.

    A real ORS polyline can pack thousands of vertices into a route (e.g.
    ~0.18mi apart on a 971mi trip - see docs/optimizations.md 4.7), which
    is far denser than a multi-mile corridor buffer needs. Scanning every
    vertex for every surviving station turns an O(n*v) check into a real
    bottleneck at that density; thinning to roughly one vertex every
    min_spacing_miles keeps the corridor-distance approximation well
    within the buffer's own margin of error while cutting v by 10x or
    more. Always keeps the first and last point so route endpoints are
    still covered.
    """
    if len(route) <= 2:
        return list(range(len(route)))

    kept = [0]
    last_kept_dist = cum_dist[0]
    for i in range(1, len(route) - 1):
        if cum_dist[i] - last_kept_dist >= min_spacing_miles:
            kept.append(i)
            last_kept_dist = cum_dist[i]
    kept.append(len(route) - 1)
    return kept


@dataclass(frozen=True)
class CorridorStation:
    station: Any  # the original station record (dict), untouched
    distance_along_route_miles: float
    distance_from_route_miles: float


def filter_corridor(
    route: list[tuple[float, float]],
    stations: list[dict],
    buffer_miles: float = 10.0,
) -> list[CorridorStation]:
    """Filters stations (dicts with "latitude"/"longitude") to those within
    buffer_miles of route, sorted by distance-along-route.

    Three passes, cheapest first (docs/optimizations.md 4.4): a
    bounding-box check eliminates most stations for O(1) each; the
    survivors get the more expensive nearest-vertex haversine check, but
    against a distance-thinned copy of the route rather than every raw
    polyline vertex (see _downsample_by_distance) - a dense real route
    otherwise turns this into the dominant cost of the whole request.
    """
    cum_dist = cumulative_distances(route)
    min_lat, max_lat, min_lng, max_lng = bounding_box(route, buffer_miles)

    sampled_indices = _downsample_by_distance(route, cum_dist, min_spacing_miles=2.0)
    sampled_route = [route[i] for i in sampled_indices]

    results = []
    for station in stations:
        lat, lng = station["latitude"], station["longitude"]
        if not (min_lat <= lat <= max_lat and min_lng <= lng <= max_lng):
            continue

        dist, sampled_idx = nearest_vertex_distance((lat, lng), sampled_route)
        if dist <= buffer_miles:
            original_idx = sampled_indices[sampled_idx]
            results.append(CorridorStation(
                station=station,
                distance_along_route_miles=cum_dist[original_idx],
                distance_from_route_miles=dist,
            ))

    results.sort(key=lambda cs: cs.distance_along_route_miles)
    return results
