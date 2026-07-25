# study_router.py
# Simple Engine — Study-specific route generator.
#
# Unlike PersonalisedRouter which filters routes by agent beliefs and
# feasibility, StudyRouter shows ALL modes to ALL participants so the
# full ranked set is always visible in both study conditions.
#
# Architecture (Option A — thin wrapper):
#   1. Call IntermodalRouter.plan() directly to get raw GraphHopper routes
#   2. Force all routes into the active pool (no belief/feasibility filtering)
#   3. Score each route with PersonalisedRouter._score_route() (value model)
#   4. Normalise 0-100 across ALL routes
#   5. Return two sets from the same raw routes:
#        Set A — sorted by value score (personalised)
#        Set B — sorted by duration (time baseline)

import math
import sys
import os
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional

# Ensure src is on path (called from study_app.py which already does this,
# but guard here for standalone use)
_HERE = Path(__file__).resolve().parent
_SRC  = _HERE.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from agent import Agent
from graphhopper_client import GraphHopperClient
from intermodal_router import IntermodalRouter, IntermodalRoute
from personalised_router import PersonalisedRouter, ScoredRoute
from value_model import mode_distance_feasibility


# ─────────────────────────────────────────────────────────────────────────────
#  StudyRouter
# ─────────────────────────────────────────────────────────────────────────────

class StudyRouter:
    """
    Generates route sets for study scenarios.

    Key differences from PersonalisedRouter:
    - All modes shown regardless of agent beliefs (owns_car, owns_bike, has_pt_access)
    - No feasibility filtering — a 6.7km walk appears in the set even if implausible
    - Feasibility multiplier still applied to SCORE so implausible routes rank low
    - Returns two sets from one GraphHopper call:
        personalised: sorted by value score
        baseline:     sorted by duration (same routes, different order)
    """

    # Intermodal strategies to exclude for study condition 1
    INTERMODAL_KEYS = {"bike_pt", "car_pt", "bike+pt", "car+pt"}

    def __init__(self, gh_client: GraphHopperClient):
        self._gh     = gh_client
        self._scorer = PersonalisedRouter(gh_client, pois=None)

    def generate_both(
        self,
        agent: Agent,
        scenario: dict,
        study_condition: int = 1,
        departure: Optional[datetime] = None,
        max_walk_m: int = 1500,
    ) -> dict:
        """
        Generate personalised (Set A) and baseline (Set B) route sets.

        Returns
        -------
        {
            "personalised": [ route_dict, ... ],   # value-ranked
            "baseline":     [ route_dict, ... ],   # duration-ranked
        }
        """
        if departure is None:
            departure = datetime(2025, 11, 15, 9, 0, tzinfo=timezone.utc)

        from_lat = scenario["origin_lat"]
        from_lon = scenario["origin_lon"]
        to_lat   = scenario["destination_lat"]
        to_lon   = scenario["destination_lon"]

        # ── Step 1: get all raw routes from IntermodalRouter ──────────────
        im_router = IntermodalRouter(
            client     = self._gh,
            departure  = departure.isoformat(),
            max_walk_m = max_walk_m,
        )
        raw_routes = im_router.plan(from_lat, from_lon, to_lat, to_lon)

        if not raw_routes:
            return {"personalised": [], "baseline": []}

        # ── Step 2: filter intermodal for condition 1 ─────────────────────
        if study_condition == 1:
            raw_routes = [
                r for r in raw_routes
                if getattr(r, "strategy", "").lower().replace(" ", "_")
                   not in self.INTERMODAL_KEYS
                and not getattr(r, "is_intermodal", False)
            ]

        if not raw_routes:
            return {"personalised": [], "baseline": []}

        # ── Step 2b: ensure all 4 core modes are present ─────────────────
        # IntermodalRouter may drop walk for long trips due to feasibility.
        # For the study we always want walk visible so participants can compare.
        present_strategies = {
            getattr(r, "strategy", "") for r in raw_routes
        }
        # Inject bike if IntermodalRouter dropped it due to distance cap.
        # StudyRouter always shows all modes for study comparison.
        if "bike_direct" not in present_strategies:
            bike_routes = self._gh.route_bike(from_lat, from_lon, to_lat, to_lon)
            if bike_routes:
                br = bike_routes[0]
                bike_route = type("BikeRoute", (), {
                    "strategy":        "bike_direct",
                    "total_duration_s": getattr(br, "duration_s", 0),
                    "total_distance_m": getattr(br, "distance_m", 0),
                    "transfer_count":   0,
                    "transfers":        0,
                    "is_intermodal":    False,
                    "feasible":         True,
                    "infeasible_reason": None,
                    "geometry":         getattr(br, "geometry", None),
                })()
                bike_leg = type("BikeLeg", (), {
                    "mode":       "bike",
                    "distance_m": getattr(br, "distance_m", 0),
                    "duration_s": getattr(br, "duration_s", 0),
                    "from_name":  None, "to_name": None,
                    "from_stop":  None, "to_stop": None,
                    "num_stops":  None, "route_id": None,
                    "trip_headsign": None, "description": "Bike",
                    "geometry":   None,
                })()
                bike_route.legs = [bike_leg] # type: ignore
                raw_routes.append(bike_route) # type: ignore

        # Inject walk if IntermodalRouter dropped it — always show walk
        # even for long distances so participants can see all options.
        # The feasibility-based normalisation ensures it ranks last.
        if "foot_direct" not in present_strategies:
            foot_routes = self._gh.route_foot(from_lat, from_lon, to_lat, to_lon)
            if foot_routes:
                fr = foot_routes[0]
                # Build a simple namespace object compatible with _score_route
                # Build a single walk leg
                walk_leg = type("WalkLeg", (), {
                    "mode":       "walk",
                    "distance_m": getattr(fr, "distance_m", 0),
                    "duration_s": getattr(fr, "duration_s", 0),
                    "from_name":  None,
                    "to_name":    None,
                    "from_stop":  None,
                    "to_stop":    None,
                    "num_stops":  None,
                    "route_id":   None,
                    "trip_headsign": None,
                    "description":   "Walk",
                    "geometry":   None,
                })()
                walk_route = type("WalkRoute", (), {
                    "strategy":        "foot_direct",
                    "total_duration_s": getattr(fr, "duration_s", 0),
                    "total_distance_m": getattr(fr, "distance_m", 0),
                    "transfer_count":   0,
                    "transfers":        0,
                    "is_intermodal":    False,
                    "feasible":         True,
                    "infeasible_reason": None,
                    "geometry":         getattr(fr, "geometry", None),
                    "legs":             [walk_leg],
                })()
                raw_routes.append(walk_route) # type: ignore

        # ── Step 3: crow-flies distance for feasibility multiplier ────────
        crow_km = _haversine(from_lat, from_lon, to_lat, to_lon)

        # ── Step 4: score every route (NO filtering by beliefs/feasibility) ──
        # Override agent beliefs so all modes are "available"
        agent.beliefs["owns_car"]      = True
        agent.beliefs["owns_bike"]     = True
        agent.beliefs["has_pt_access"] = True

        scored = []
        for route in raw_routes:
            mode_key = _get_mode_key(route)
            try:
                sr = self._scorer._score_route(agent, route, mode_key, crow_km)
                sr.rank = 0
                scored.append((mode_key, route, sr))
            except Exception as e:
                print(f"[StudyRouter] _score_route failed for {mode_key}: {e}")

        # ── Step 5: separate feasible vs implausible routes ─────────────────
        # Routes with feasibility < 0.01 (e.g. walk at 6.7km+) are kept visible
        # but always ranked below feasible routes, scored 0–10 within their group.
        FEASIBILITY_THRESHOLD = 0.01
        feasible_scored   = [(mk, r, sr) for mk, r, sr in scored if sr.feasibility_score >= FEASIBILITY_THRESHOLD]
        implausible_scored = [(mk, r, sr) for mk, r, sr in scored if sr.feasibility_score < FEASIBILITY_THRESHOLD]

        def normalise_group(group, score_min, score_max):
            if not group:
                return
            raws = [sr.raw_score for _, _, sr in group]
            lo   = min(min(0.0, min(raws)), 0.0)
            hi   = max(raws)
            span = hi - lo if hi != lo else 1.0
            for _, _, sr in group:
                clamped = max(lo, sr.raw_score)
                sr.utility_score = round(score_min + ((clamped - lo) / span) * (score_max - score_min), 1)

        # Feasible routes: score 15–100 (leave 0–14 for implausible)
        normalise_group(feasible_scored, 15.0, 100.0)
        # Implausible routes: score 0–10 (always shown last)
        normalise_group(implausible_scored, 0.0, 10.0)

        scored = feasible_scored + implausible_scored

        # ── Step 6: build Set A (value-ranked) ────────────────────────────
        set_a = sorted(scored, key=lambda x: x[2].utility_score, reverse=True)
        personalised = []
        for rank, (mode_key, route, sr) in enumerate(set_a, 1):
            sr.rank = rank
            personalised.append(
                _to_study_dict(sr, route, mode_key, scenario, "personalised", rank)
            )

        # ── Step 7: build Set B (duration-ranked, same routes) ────────────
        set_b = sorted(scored, key=lambda x: _get_duration(x[1]))
        baseline = []
        for rank, (mode_key, route, sr) in enumerate(set_b, 1):
            baseline.append(
                _to_study_dict(sr, route, mode_key, scenario, "baseline", rank)
            )

        return {"personalised": personalised, "baseline": baseline}


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * \
        math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


_STRATEGY_TO_MODE = {
    "pt_direct":   "pt",
    "car_direct":  "car",
    "bike_direct": "bike",
    "foot_direct": "foot",
    "bike_pt":     "bike_pt",
    "car_pt":      "car_pt",
}

def _get_mode_key(route) -> str:
    """Extract mode key from an IntermodalRoute, mapping strategy to mode key."""
    strategy = getattr(route, "strategy", None)
    if strategy:
        return _STRATEGY_TO_MODE.get(strategy, strategy.lower().replace(" ", "_")) or "unknown"
    if hasattr(route, "mode_key"):
        return route.mode_key
    legs = getattr(route, "legs", [])
    if legs:
        modes = list(dict.fromkeys(
            getattr(l, "mode", "") for l in legs if getattr(l, "mode", "")
        ))
        return "+".join(modes) if len(modes) > 1 else (modes[0] if modes else "unknown")
    return "unknown"


def _get_duration(route) -> float:
    """
    Get total duration in seconds from an IntermodalRoute.
    Uses total_duration_s which correctly includes waiting time at PT stops.
    """
    return getattr(route, "total_duration_s", 0) or 0


_MODE_EMOJI = {
    "foot":    "🚶",
    "walk":    "🚶",
    "bike":    "🚴",
    "car":     "🚗",
    "pt":      "🚌",
    "bike_pt": "🚴+🚌",
    "car_pt":  "🚗+🚌",
}

_MODE_LABEL = {
    "foot":    "Walk",
    "walk":    "Walk",
    "bike":    "Bike",
    "car":     "Car",
    "pt":      "Public Transport",
    "bike_pt": "Bike & PT",
    "car_pt":  "Car & PT (P&R)",
}


def _to_study_dict(
    sr: ScoredRoute,
    route,
    mode_key: str,
    scenario: dict,
    condition: str,
    rank: int,
) -> dict:
    """Convert a ScoredRoute to the dict format expected by study_app and the DB."""
    legs     = getattr(route, "legs", []) or []
    duration  = round(_get_duration(route) / 60, 1)
    distance  = round((getattr(route, "total_distance_m", 0) or 0) / 1000, 2)
    transfers = getattr(route, "transfer_count", 0) or 0

    unique_modes = list(dict.fromkeys(
        getattr(l, "mode", "") for l in legs if getattr(l, "mode", "")
    )) or [mode_key]

    # Only flag as intermodal if the strategy is explicitly bike+PT or car+PT.
    # PT routes with a short walking access leg are NOT intermodal in the
    # participant-facing sense — they are single-mode PT journeys.
    _TRUE_INTERMODAL = {"bike_pt", "car_pt"}
    is_intermodal = 1 if mode_key in _TRUE_INTERMODAL else 0

    def leg_min(mode_name):
        return round(
            sum(getattr(l, "duration_s", 0) or 0
                for l in legs
                if getattr(l, "mode", "") == mode_name
                or getattr(l, "mode", "") == mode_name.replace("walk", "foot")
                and getattr(l, "mode", "") != "wait") / 60, 1
        )

    emoji = _MODE_EMOJI.get(mode_key, "🔵")
    label = f"{emoji} {_MODE_LABEL.get(mode_key, mode_key.replace('_',' ').title())}"

    dim_scores = {}
    for ds in (sr.dimension_scores or []):
        dim  = getattr(ds, "dimension", None)
        cont = getattr(ds, "contribution", None)
        if dim and cont is not None:
            dim_scores[f"score_{dim}"] = round(float(cont), 4)

    raw_route_json = {
        "rank": rank, "mode_key": mode_key, "mode_label": label,
        "condition": condition, "utility_score": sr.utility_score,
        "duration_min": duration, "distance_km": distance,
        "transfers": transfers, "is_intermodal": is_intermodal,
        "strategy": getattr(route, "strategy", mode_key),
        "geometry": getattr(route, "geometry", None),
        "legs": [
            {
                "mode":          getattr(l, "mode", None),
                "description":   getattr(l, "description", None),
                "distance_m":    getattr(l, "distance_m", None),
                "duration_s":    getattr(l, "duration_s", None),
                "from_name":     getattr(l, "from_name", None),
                "to_name":       getattr(l, "to_name", None),
                "from_stop":     getattr(l, "from_stop", None),
                "to_stop":       getattr(l, "to_stop", None),
                "num_stops":     getattr(l, "num_stops", None),
                "route_id":      getattr(l, "route_id", None),
                "trip_headsign": getattr(l, "trip_headsign", None),
                "geometry":      getattr(l, "geometry", None),
            }
            for l in legs
        ],
    }

    # For display: single-mode routes show only their primary mode,
    # not the walking access leg that GraphHopper includes for PT stops.
    if is_intermodal:
        display_modes = ", ".join(str(m) for m in unique_modes if m)
        display_type  = "+".join(str(m) for m in unique_modes if m)
    else:
        # Use the canonical mode key for single-mode routes
        display_modes = mode_key
        display_type  = mode_key

    return {
        "scenario_id":            scenario["id"],
        "route_condition":        condition,
        "route_rank":             rank,
        "route_id":               f"S{scenario['id']}_{condition[:4].upper()}_R{rank}_{mode_key}",
        "route_summary":          label,
        "transport_modes":        display_modes,
        "is_intermodal":          is_intermodal,
        "intermodal_type":        display_type,
        "total_duration_minutes": duration,
        "walking_minutes":        leg_min("walk"),
        "cycling_minutes":        leg_min("bike"),
        "pt_minutes":             leg_min("pt"),
        "driving_minutes":        leg_min("car"),
        "transfer_count":         transfers,
        "engine_total_score":     sr.utility_score,
        "raw_route_json":         __import__("json").dumps(raw_route_json),
        **dim_scores,
    }