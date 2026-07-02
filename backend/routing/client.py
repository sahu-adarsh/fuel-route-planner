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
            raise UpstreamRoutingError(f"Directions request failed: {exc}") from exc

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
            raise UpstreamRoutingError(f"Geocoding request failed: {exc}") from exc

        try:
            features = response.json()["features"]
        except (KeyError, TypeError, ValueError) as exc:
            raise UpstreamRoutingError(f"Unexpected geocoding response shape: {exc}") from exc

        if not features:
            raise UnresolvableLocationError(f"Could not resolve location: {text!r}")

        feature = features[0]
        if feature["properties"].get("country_a") != "USA":
            raise UnresolvableLocationError(f"Location resolved outside the US: {text!r}")

        lng, lat = feature["geometry"]["coordinates"]
        return Coordinates(lat=lat, lng=lng)

    def _require_api_key(self):
        if not self.api_key:
            raise UpstreamRoutingError(
                "ORS_API_KEY is not configured - see backend/.env.example"
            )
