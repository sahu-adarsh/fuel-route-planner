class RoutingError(Exception):
    """Base exception for the routing/geocoding provider integration."""


class UnresolvableLocationError(RoutingError):
    """A free-text location could not be geocoded, or resolved outside the US."""


class UpstreamRoutingError(RoutingError):
    """The routing/geocoding provider errored, timed out, or returned an unexpected shape."""


class IdenticalLocationsError(Exception):
    """Start and end are the same place - not a provider problem, so not a RoutingError."""


class NoFuelDataInCorridorError(Exception):
    """Stops are required for this trip, but no station data exists anywhere near the route."""
