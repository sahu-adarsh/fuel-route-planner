from rest_framework import serializers

from .client import Coordinates


class LocationField(serializers.Field):
    """Accepts either a free-text location string or a {lat, lng} object,
    matching the request schema in docs/api-design.md. Returns a plain
    str or a Coordinates instance - both valid inputs to
    OpenRouteServiceClient.resolve_location.
    """

    def to_internal_value(self, data):
        if isinstance(data, str):
            text = data.strip()
            if not text:
                raise serializers.ValidationError("must not be empty")
            return text

        if isinstance(data, dict):
            if "lat" not in data or "lng" not in data:
                raise serializers.ValidationError("must include both lat and lng")
            try:
                lat = float(data["lat"])
                lng = float(data["lng"])
            except (TypeError, ValueError):
                raise serializers.ValidationError("lat and lng must be numbers")
            if not (-90 <= lat <= 90):
                raise serializers.ValidationError("lat must be between -90 and 90")
            if not (-180 <= lng <= 180):
                raise serializers.ValidationError("lng must be between -180 and 180")
            return Coordinates(lat=lat, lng=lng)

        raise serializers.ValidationError("must be a location string or a {lat, lng} object")

    def to_representation(self, value):
        if isinstance(value, Coordinates):
            return {"lat": value.lat, "lng": value.lng}
        return value


class RouteRequestSerializer(serializers.Serializer):
    start = LocationField()
    end = LocationField()
