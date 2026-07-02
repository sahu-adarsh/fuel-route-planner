class OptimizationError(Exception):
    """Base exception for the fuel-stop optimization domain."""


class InfeasibleRouteError(OptimizationError):
    """A fuel gap along the route exceeds the vehicle's range - no valid stop sequence exists."""

    def __init__(self, gap_start_miles: float, gap_end_miles: float):
        self.gap_start_miles = gap_start_miles
        self.gap_end_miles = gap_end_miles
        super().__init__(
            f"No feasible fuel stop sequence: a {gap_end_miles - gap_start_miles:.1f} mile gap "
            f"exists between mile {gap_start_miles:.1f} and mile {gap_end_miles:.1f}."
        )
