"""
The single integration point with OpenRouteService (routing + geocoding).

No other module in this codebase should make HTTP calls to a routing or
geocoding provider - see docs/decisions.md ADR-001. Keeping every call in
one place is what makes the per-request external call budget in
docs/api-design.md auditable.
"""
from dataclasses import dataclass
from typing import Union

import requests
from django.conf import settings

from .exceptions import UnresolvableLocationError, UpstreamRoutingError

ORS_BASE_URL = "https://api.openrouteservice.org"
METERS_PER_MILE = 1609.344
DEFAULT_PROFILE = "driving-hgv"

# Pelias layers coarser than a city - a match at this level (e.g. "iowa"
# resolving to the whole state) geocodes fine but its centroid is usually
# nowhere near a routable road, so the *directions* call fails later with
# an opaque 404. Catching it here, before that call is even made, is what
# lets us give a specific, actionable message instead.
_TOO_COARSE_LAYERS = frozenset({
    "continent", "empire", "dependency", "country", "macroregion",
    "region", "macrocounty", "county", "disputed", "ocean", "marinearea",
})
_LAYER_DISPLAY_NAMES = {
    "region": "state",
    "macroregion": "region",
    "macrocounty": "county",
    "dependency": "territory",
    "marinearea": "marine area",
    "disputed": "disputed territory",
}


@dataclass(frozen=True)
class Coordinates:
    lat: float
    lng: float


@dataclass(frozen=True)
class DirectionsResult:
    distance_miles: float
    duration_hours: float
    geometry: dict  # GeoJSON LineString, [lng, lat] pairs


Location = Union[str, Coordinates]


def _describe_http_error(exc: requests.RequestException) -> str:
    """Prefers ORS's own error.message from the response body (e.g. "Could
    not find routable point within a radius of 350.0 meters...") over the
    generic requests exception text, which is opaque to an end user."""
    response = getattr(exc, "response", None)
    if response is not None:
        try:
            message = response.json().get("error", {}).get("message")
            if message:
                return message
        except (ValueError, AttributeError):
            pass
    return str(exc)


class OpenRouteServiceClient:
    def __init__(self, api_key=None, session=None, timeout=10):
        self.api_key = api_key if api_key is not None else settings.ORS_API_KEY
        self.session = session or requests.Session()
        self.timeout = timeout

    def resolve_location(self, location: Location) -> Coordinates:
        """Returns Coordinates unchanged, or geocodes a free-text string.

        Only the free-text path spends an external call - see the call
        budget table in docs/api-design.md.
        """
        if isinstance(location, Coordinates):
            return location
        return self._geocode(location)

    def get_route(self, start: Coordinates, end: Coordinates, profile: str = DEFAULT_PROFILE) -> DirectionsResult:
        self._require_api_key()
        url = f"{ORS_BASE_URL}/v2/directions/{profile}/geojson"
        try:
            response = self.session.post(
                url,
                headers={"Authorization": self.api_key, "Content-Type": "application/json"},
                json={"coordinates": [[start.lng, start.lat], [end.lng, end.lat]]},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise UpstreamRoutingError(f"Could not compute a route: {_describe_http_error(exc)}") from exc

        try:
            feature = response.json()["features"][0]
            summary = feature["properties"]["summary"]
            return DirectionsResult(
                distance_miles=summary["distance"] / METERS_PER_MILE,
                duration_hours=summary["duration"] / 3600,
                geometry=feature["geometry"],
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise UpstreamRoutingError(f"Unexpected directions response shape: {exc}") from exc

    def _geocode(self, text: str) -> Coordinates:
        self._require_api_key()
        try:
            response = self.session.get(
                f"{ORS_BASE_URL}/geocode/search",
                params={
                    "api_key": self.api_key,
                    "text": text,
                    "size": 1,
                    "boundary.country": "US",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise UpstreamRoutingError(f"Could not resolve location: {_describe_http_error(exc)}") from exc

        try:
            features = response.json()["features"]
        except (KeyError, TypeError, ValueError) as exc:
            raise UpstreamRoutingError(f"Unexpected geocoding response shape: {exc}") from exc

        if not features:
            raise UnresolvableLocationError(f"Could not find a location matching {text!r}.")

        feature = features[0]
        properties = feature["properties"]

        if properties.get("country_a") != "USA":
            raise UnresolvableLocationError(f"{text!r} resolved outside the US.")

        layer = properties.get("layer")
        if layer in _TOO_COARSE_LAYERS:
            kind = _LAYER_DISPLAY_NAMES.get(layer, layer)
            raise UnresolvableLocationError(
                f"{text!r} resolved to a whole {kind}, not a specific place - "
                f"please include a city (e.g. 'Chicago, IL')."
            )

        lng, lat = feature["geometry"]["coordinates"]
        return Coordinates(lat=lat, lng=lng)

    def _require_api_key(self):
        if not self.api_key:
            raise UpstreamRoutingError(
                "ORS_API_KEY is not configured - see backend/.env.example"
            )
