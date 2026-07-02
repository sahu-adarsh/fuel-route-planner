from rest_framework.response import Response
from rest_framework.views import APIView

from optimization.exceptions import InfeasibleRouteError

from .exceptions import (
    IdenticalLocationsError,
    NoFuelDataInCorridorError,
    UnresolvableLocationError,
    UpstreamRoutingError,
)
from .serializers import RouteRequestSerializer
from .services import RouteResult, plan_route


def _error(code: str, message: str, details=None) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


def _serialize_result(result: RouteResult) -> dict:
    return {
        "distance_miles": result.distance_miles,
        "duration_hours": result.duration_hours,
        "route_geometry": result.geometry,
        "stops_required": result.stops_required,
        "fuel_stops": result.fuel_stops,
        "total_fuel_cost_usd": result.total_fuel_cost_usd,
        "external_calls_used": result.external_calls_used,
    }


class RouteView(APIView):
    def post(self, request):
        serializer = RouteRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                _error("validation_error", "Invalid request.", serializer.errors),
                status=400,
            )

        start = serializer.validated_data["start"]
        end = serializer.validated_data["end"]

        try:
            result = plan_route(start, end)
        except IdenticalLocationsError:
            return Response(
                _error("identical_locations", "Start and end resolve to the same location."),
                status=400,
            )
        except UnresolvableLocationError as exc:
            return Response(_error("unresolvable_location", str(exc)), status=422)
        except NoFuelDataInCorridorError:
            return Response(
                _error("no_fuel_data_in_corridor", "No fuel price data is available along this route."),
                status=422,
            )
        except InfeasibleRouteError as exc:
            gap_miles = exc.gap_end_miles - exc.gap_start_miles
            return Response(
                _error(
                    "infeasible_route",
                    str(exc),
                    {
                        "gap_start_mile": round(exc.gap_start_miles, 1),
                        "gap_end_mile": round(exc.gap_end_miles, 1),
                        "gap_miles": round(gap_miles, 1),
                    },
                ),
                status=422,
            )
        except UpstreamRoutingError as exc:
            return Response(_error("upstream_routing_error", str(exc)), status=502)

        return Response(_serialize_result(result), status=200)
