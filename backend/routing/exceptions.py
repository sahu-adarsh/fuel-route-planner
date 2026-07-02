class RoutingError(Exception):
    """Base exception for the routing/geocoding provider integration."""


class UnresolvableLocationError(RoutingError):
    """A free-text location could not be geocoded, or resolved outside the US."""


class UpstreamRoutingError(RoutingError):
    """The routing/geocoding provider errored, timed out, or returned an unexpected shape."""
