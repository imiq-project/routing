"""
personalised_router.py
──────────────────────
The core scoring engine.

For each candidate route it computes a VALUE SCORE by:

  1. Start with the mode's base attribute scores (from value_model.py)
  2. Blend in route-metric adjustments (actual duration → speed score, etc.)
  3. Dot-product with the agent's normalised value weights
  4. Normalise to [0, 100] across all candidates for readability

The result is a ScoredRoute that carries:
  - the route itself
  - the final utility score
  - a per-dimension breakdown so the agent can see WHY it was recommended
"""

from dataclasses import dataclass, field
from typing import Optional

from agent import Agent
from value_model import (
    VALUE_DIMENSIONS, MODE_ATTRIBUTES, MODE_LABELS,
    speed_score_from_duration, cost_score_from_mode,
    comfort_score_from_transfers,
    walking_distance_penalty, cycling_distance_penalty,
)
from intermodal_router import IntermodalRouter, IntermodalRoute
from graphhopper_client import GraphHopperClient


# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class DimensionScore:
    """Score for one value dimension for one route."""
    dimension: str
    agent_weight: float       # how much this agent cares (0–1)
    mode_attribute: float     # how well this mode serves this value (-1 to +1)
    metric_adjustment: float  # real-route adjustment (-1 to +1)
    blended_attribute: float  # mode_attribute + adjustment (clamped -1 to +1)
    contribution: float       # agent_weight * blended_attribute (the actual score)


@dataclass
class ScoredRoute:
    """A route with full value-based scoring."""
    route: IntermodalRoute
    mode_key: str                          # e.g. "bike_pt"
    mode_label: str                        # e.g. "🚴+🚌 Bike & PT"
    utility_score: float                   # 0–100 final score
    raw_score: float                       # pre-normalised dot product
    dimension_scores: list[DimensionScore] # per-dimension breakdown
    rank: int = 0
    available: bool = True                 # can agent actually use this mode?
    poi_boost: float = 0.0                 # boost from passing through relevant POIs
    matched_pois: list = field(default_factory=list)  # POIs this route passed through

    @property
    def top_matching_values(self) -> list[DimensionScore]:
        """Value dimensions this route best satisfies for the agent."""
        positive = [d for d in self.dimension_scores if d.contribution > 0]
        return sorted(positive, key=lambda d: d.contribution, reverse=True)[:3]

    @property
    def top_conflicting_values(self) -> list[DimensionScore]:
        """Value dimensions this route conflicts with for the agent."""
        negative = [d for d in self.dimension_scores if d.contribution < 0]
        return sorted(negative, key=lambda d: d.contribution)[:2]


# ── Scorer ────────────────────────────────────────────────────────────────────

class PersonalisedRouter:
    """
    Given an Agent and two coordinates, returns a ranked list of
    ScoredRoutes with full value-dimension breakdowns.

    Usage
    -----
    client  = GraphHopperClient()
    router  = PersonalisedRouter(client)
    results = router.route(agent, from_lat, from_lon, to_lat, to_lon,
                           departure="2024-10-15T08:30:00+02:00")
    """

    # How much route metrics influence the score vs. pure mode attributes.
    # 0.0 = ignore real metrics entirely (pure value model)
    # 1.0 = metrics fully replace mode attribute for that dimension
    METRIC_BLEND = 0.4

    def __init__(self, client: GraphHopperClient, pois: Optional[list] = None, 
                 poi_proximity_m: float = 100):
        self.client = client
        self.pois = pois or []
        self.poi_proximity_m = poi_proximity_m

    # ── Main entry point ──────────────────────────────────────────────────────

    def route(self, agent: Agent,
              from_lat: float, from_lon: float,
              to_lat: float,   to_lon: float,
              departure: Optional[str] = None,
              max_walk_m: int = 500) -> list[ScoredRoute]:
        """
        Plan and score all available routes for this agent.
        Returns routes ranked by personalised utility score (highest first).
        """
        available_modes = agent.available_modes()

        # Get candidate routes from the intermodal router
        im_router = IntermodalRouter(
            client     = self.client,
            departure  = departure,
            max_walk_m = max_walk_m,
        )
        candidate_routes = im_router.plan(from_lat, from_lon, to_lat, to_lon)

        # Score each feasible route
        scored = []
        for route in candidate_routes:
            if not route.feasible:
                continue

            # Map the intermodal strategy to a mode key for attribute lookup
            mode_key = self._strategy_to_mode_key(route.strategy)

            if mode_key not in MODE_ATTRIBUTES:
                continue

            # Score all routes, but mark unavailable ones
            scored_route = self._score_route(agent, route, mode_key)
            
            # Check if agent can actually use this mode
            can_use = agent.can_use(mode_key.split("_")[0]) or mode_key in available_modes or mode_key == "foot"
            scored_route.available = can_use
            
            scored.append(scored_route)

        if not scored:
            return []

        # Normalise raw scores to 0–100
        raw_scores = [s.raw_score for s in scored]
        min_raw    = min(raw_scores)
        max_raw    = max(raw_scores)
        span       = max_raw - min_raw if max_raw != min_raw else 1.0

        for sr in scored:
            sr.utility_score = round(
                ((sr.raw_score - min_raw) / span) * 100, 1
            )

        # Rank by utility score descending
        scored.sort(key=lambda s: s.utility_score, reverse=True)
        for i, sr in enumerate(scored, 1):
            sr.rank = i

        return scored

    # ── Scoring logic ─────────────────────────────────────────────────────────

    def _score_route(self, agent: Agent,
                     route: IntermodalRoute,
                     mode_key: str) -> ScoredRoute:
        """Compute the full per-dimension score for one route."""
        base_attrs     = MODE_ATTRIBUTES[mode_key]
        metric_adjusts = self._metric_adjustments(route, mode_key, agent)
        dim_scores     = []
        raw_total      = 0.0

        for dim in VALUE_DIMENSIONS:
            agent_weight   = agent.value_weights.get(dim, 0.0)
            mode_attr      = base_attrs.get(dim, 0.0)
            metric_adj     = metric_adjusts.get(dim, 0.0)

            # Blend base attribute with metric adjustment
            blended = mode_attr * (1 - self.METRIC_BLEND) + \
                      metric_adj * self.METRIC_BLEND
            blended = max(-1.0, min(1.0, blended))

            contribution = agent_weight * blended
            raw_total   += contribution

            dim_scores.append(DimensionScore(
                dimension          = dim,
                agent_weight       = agent_weight,
                mode_attribute     = mode_attr,
                metric_adjustment  = metric_adj,
                blended_attribute  = blended,
                contribution       = contribution,
            ))
        
        # Add POI boost if POIs are configured
        poi_boost = 0.0
        matched_pois = []
        if self.pois:
            poi_boost, matched_pois = self.compute_poi_score(
                route, self.pois, agent, self.poi_proximity_m
            )
            raw_total += poi_boost

        return ScoredRoute(
            route            = route,
            mode_key         = mode_key,
            mode_label       = MODE_LABELS.get(mode_key, mode_key),
            utility_score    = 0.0,   # filled in after normalisation
            raw_score        = raw_total,
            dimension_scores = dim_scores,
            poi_boost        = poi_boost,
            matched_pois     = matched_pois,
        )

    def _metric_adjustments(self, route: IntermodalRoute,
                             mode_key: str, agent: Agent) -> dict:
        """
        Derive per-dimension metric adjustments from actual route data.
        Returns a dict of {dimension: score -1 to +1}.
        """
        adjustments = {}
        
        distance_km = route.total_distance_m / 1000
        profile_type = agent.infer_profile_type()

        # Speed: based on actual duration
        adjustments["speed"] = speed_score_from_duration(
            route.total_duration_s, reference_s=1800
        )
        
        # Apply distance penalties for active modes
        if mode_key == "foot":
            distance_penalty = walking_distance_penalty(distance_km, profile_type)
            # Reduce speed and comfort scores based on walking distance
            adjustments["speed"] += distance_penalty
            adjustments["comfort"] = adjustments.get("comfort", 0.0) + distance_penalty * 0.5
            
        elif mode_key == "bike":
            distance_penalty = cycling_distance_penalty(distance_km, profile_type)
            # Reduce speed and comfort scores based on cycling distance
            adjustments["speed"] += distance_penalty * 0.7
            adjustments["comfort"] = adjustments.get("comfort", 0.0) + distance_penalty * 0.3

        # Cost: based on mode and distance
        adjustments["cost_saving"] = cost_score_from_mode(
            mode_key, route.total_distance_m
        )

        # Comfort: penalise transfers
        if "comfort" not in adjustments:
            adjustments["comfort"] = 0.0
        adjustments["comfort"] += comfort_score_from_transfers(route.transfers)

        # Physical activity: based on distance walked/cycled
        active_distance = sum(
            leg.distance_m for leg in route.legs
            if leg.mode in ("walk", "bike")
        )
        # Normalise: 5km of active travel = +1.0
        adjustments["physical_activity"] = min(
            1.0, active_distance / 5000
        )

        return adjustments

    def compute_poi_score(self, route: IntermodalRoute, pois: list, 
                          agent: Agent, proximity_m: float = 100) -> tuple[float, list]:
        """
        Compute POI boost/penalty for a route.
        
        Parameters
        ----------
        route : IntermodalRoute
            The route to score
        pois : list of dict
            Each POI has: {lat, lon, type, value_alignment}
            value_alignment is a dict like {"pro_environment": +0.5, "hedonism": -0.3}
        agent : Agent
            The agent whose values we're matching
        proximity_m : float
            How close the route must pass to count as "through" the POI
        
        Returns
        -------
        total_boost : float
            Raw boost value to add to the route's raw_score
        matched_pois : list of dict
            POIs that the route passed through with their boost values
            
        Example POI
        -----------
        {
            "lat": 52.1320,
            "lon": 11.6234,
            "type": "park",
            "name": "City Park",
            "value_alignment": {
                "pro_environment": +0.8,   # Park aligns with environmental values
                "hedonism": +0.5,          # Pleasant place
                "physical_activity": +0.3   # Encourages activity
            }
        }
        """
        import math
        
        total_boost = 0.0
        matched_pois = []
        
        # Extract route geometry coordinates
        route_coords = self._extract_route_coordinates(route)
        
        if not route_coords:
            return 0.0, []
        
        for poi in pois:
            poi_lat = poi.get("lat")
            poi_lon = poi.get("lon")
            alignment = poi.get("value_alignment", {})
            
            if not poi_lat or not poi_lon or not alignment:
                continue
            
            # Check if route passes within proximity_m of this POI
            min_distance_m = float('inf')
            for coord_lat, coord_lon in route_coords:
                distance_m = self._haversine_distance(
                    poi_lat, poi_lon, coord_lat, coord_lon
                )
                min_distance_m = min(min_distance_m, distance_m)
            
            # If route passes close enough, compute boost
            if min_distance_m <= proximity_m:
                # Compute boost: dot product of POI alignment × agent weights
                poi_boost = sum(
                    agent.value_weights.get(dim, 0.0) * alignment.get(dim, 0.0)
                    for dim in alignment.keys()
                )
                total_boost += poi_boost
                
                matched_pois.append({
                    "name": poi.get("name", "Unknown POI"),
                    "type": poi.get("type", "unknown"),
                    "boost": poi_boost,
                    "distance_m": min_distance_m,
                })
        
        return total_boost, matched_pois
    
    def _extract_route_coordinates(self, route: IntermodalRoute) -> list[tuple[float, float]]:
        """
        Extract all lat/lon coordinates from a route's geometry.
        Returns list of (lat, lon) tuples.
        """
        coords = []
        
        # Get geometry from the route
        geometry = route.geometry
        
        if not geometry:
            # Fallback: extract from PT leg stops if available
            for leg in route.legs:
                if hasattr(leg, 'stops') and leg.stops:
                    for stop in leg.stops:
                        stop_geometry = stop.get("geometry", {})
                        if stop_geometry and "coordinates" in stop_geometry:
                            lon, lat = stop_geometry["coordinates"]
                            coords.append((lat, lon))
            return coords
        
        # Parse GeoJSON coordinates from the geometry dict
        if isinstance(geometry, dict) and "coordinates" in geometry:
            # GeoJSON format: coordinates are [lon, lat]
            for coord in geometry["coordinates"]:
                if isinstance(coord, (list, tuple)) and len(coord) >= 2:
                    lon, lat = coord[0], coord[1]
                    coords.append((lat, lon))
        
        return coords
    
    @staticmethod
    def _haversine_distance(lat1: float, lon1: float, 
                           lat2: float, lon2: float) -> float:
        """
        Calculate distance in meters between two lat/lon points.
        Uses Haversine formula.
        """
        import math
        
        R = 6371000  # Earth radius in meters
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        
        a = math.sin(dlat/2)**2 + \
            math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        return R * c

    @staticmethod
    def _strategy_to_mode_key(strategy: str) -> str:
        """Map intermodal strategy name to a MODE_ATTRIBUTES key."""
        mapping = {
            "pt_direct":   "pt",
            "car_direct":  "car",
            "bike_direct": "bike",
            "foot_direct": "foot",
            "bike_pt":     "bike_pt",
            "car_pt":      "car_pt",
        }
        return mapping.get(strategy, strategy)