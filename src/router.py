"""
router.py
─────────
High-level routing interface.  This is the file your application code
should import and use.  It wraps graphhopper_client.py and adds:

  • A single route() function that accepts a mode string
  • Pretty-printing of results
  • Clear error messages

Example usage:
    from router import Router

    r = Router()
    routes = r.route("car",  51.5074, -0.1278, 51.5194, -0.0886)
    routes = r.route("pt",   51.5074, -0.1278, 51.5194, -0.0886,
                     departure="2025-06-16T08:30:00+01:00")
"""

from datetime import datetime
from dateutil import parser as dateparser

from graphhopper_client import GraphHopperClient, Route, WalkLeg, PtLeg

#-----------------------------------------
# Router
#-----------------------------------------

class Router:
    """
    Single entry point for all routing modes: car, bike, foot, pt.

    Parameters
    ----------
    host : str
        URL where GraphHopper is running.  Default is localhost:8080.
    """

    VALID_MODES = ("car", "bike", "foot", "pt")

    def __init__(self, host: str = "http://localhost:8080"):
        self.client = GraphHopperClient(base_url=host)
        self._check_server()

    # Health check 

    def _check_server(self):
        if not self.client.is_alive():
            print(
                "\n⚠️  WARNING: GraphHopper server is not reachable at "
                f"{self.client.base_url}\n"
                "   Start it first — see README.md for instructions.\n"
            )

    #------------------------------------------------   
    # Main routing method 
    #------------------------------------------------

    def route(
        self,
        mode: str,
        from_lat: float,
        from_lon: float,
        to_lat: float,
        to_lon: float,
        departure: str | None = None,
        arrive_by: bool = False,
        max_walk_meters: int = 500,
        limit_solutions: int = 3,
    ) -> list[Route]:
        """
        Route between two coordinates.

        Parameters
        ----------
        mode            : "car" | "bike" | "foot" | "pt"
        from_lat/lon    : origin coordinates
        to_lat/lon      : destination coordinates
        departure       : ISO-8601 string, e.g. "2025-06-16T08:30:00+01:00"
                          Only used when mode="pt". Defaults to now.
        arrive_by       : if True, treat departure as desired arrival time.
        max_walk_meters : max walk distance to/from PT stop (pt mode only).
        limit_solutions : number of PT alternatives to return (pt mode only).

        Returns
        -------
        List of Route objects (empty list if no route found).
        """
        mode = mode.lower()
        if mode not in self.VALID_MODES:
            raise ValueError(
                f"Invalid mode '{mode}'. Choose from: {self.VALID_MODES}"
            )

        if mode == "car":
            return self.client.route_car(from_lat, from_lon, to_lat, to_lon)

        if mode == "bike":
            return self.client.route_bike(from_lat, from_lon, to_lat, to_lon)

        if mode == "foot":
            return self.client.route_foot(from_lat, from_lon, to_lat, to_lon)

        if mode == "pt":
            dt = dateparser.parse(departure) if departure else None
            return self.client.route_pt(
                from_lat, from_lon,
                to_lat,   to_lon,
                departure_time  = dt,
                arrive_by       = arrive_by,
                max_walk_meters = max_walk_meters,
                limit_solutions = limit_solutions,
            )

    # -------------------------------------------   
    #  Pretty printing 
    # -------------------------------------------

    def print_routes(self, routes: list[Route], mode: str):
        """Print a human-readable summary of a list of routes."""
        print(f"\n{'='*55}")
        print(f"  Mode: {mode.upper()}   |   {len(routes)} route(s) found")
        print(f"{'='*55}")

        if not routes:
            print("  No routes found.")
            print("  For PT: check your departure time is within the GTFS")
            print("  calendar range, and that stops exist near your points.")
            return

        for i, route in enumerate(routes, 1):
            print(f"\n  Route {i}:")
            print(f"    Distance  : {route.distance_km} km")
            print(f"    Duration  : {route.duration_min} min")
            if mode == "pt":
                print(f"    Transfers : {route.transfers}")

            if route.legs:
                print(f"    Journey:")
                for leg in route.legs:
                    if isinstance(leg, WalkLeg):
                        print(f"      🚶 Walk  {leg.distance_m:.0f} m  "
                              f"({leg.duration_s/60:.0f} min)")
                    elif isinstance(leg, PtLeg):
                        print(f"      🚌 PT    route {leg.route_id}  "
                              f"→ {leg.trip_headsign}")
                        print(f"             from : {leg.from_stop}"
                              f"  at {leg.departure_time or '?'}")
                        print(f"             to   : {leg.to_stop}"
                              f"  at {leg.arrival_time or '?'}")

        print()