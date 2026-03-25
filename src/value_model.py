"""
value_model.py
──────────────
Defines the VALUE ATTRIBUTE MATRIX — how well each transport mode/strategy
satisfies each human value dimension.

Scores are in the range [-1.0, +1.0]:
  +1.0  =  this mode strongly satisfies this value
   0.0  =  neutral
  -1.0  =  this mode strongly conflicts with this value

These are the default scores based on transport research literature.
You can tune any of them to better reflect your local context.

The nine value dimensions come from the psychological model output:
  pro_environment   — environmental concern
  physical_activity — desire for physical exercise
  privacy           — preference for personal space / no crowding
  autonomy          — preference for self-directed travel (own schedule)
  hedonism          — enjoyment / pleasure of the journey itself
  cost_saving       — sensitivity to monetary cost
  speed             — preference for fastest journey
  safety            — concern about personal safety
  comfort           — preference for comfortable, stress-free travel
"""

from dataclasses import dataclass, field
from typing import Optional


# ----------------------------------------------
#  Value dimensions 
# ----------------------------------------------

VALUE_DIMENSIONS = [
    "pro_environment",
    "physical_activity",
    "privacy",
    "autonomy",
    "hedonism",
    "cost_saving",
    "speed",
    "safety",
    "comfort",
]


# ----------------------------------------------
#  Mode attribute matrix 
# Each entry is a dict of {value_dimension: score}.
# Missing dimensions default to 0.0 (neutral).
# ----------------------------------------------S

MODE_ATTRIBUTES = {

    "foot": {
        "pro_environment":  1.0,   # zero emissions
        "physical_activity": 1.0,  # high physical effort
        "privacy":           0.8,  # full personal space
        "autonomy":          0.8,  # fully self-directed
        "hedonism":          0.4,  # can be enjoyable
        "cost_saving":       1.0,  # free
        "speed":            -1.0,  # slowest option
        "safety":            0.3,  # generally safe, some road risk
        "comfort":          -0.5,  # weather exposed, tiring
    },

    "bike": {
        "pro_environment":  1.0,   # zero emissions
        "physical_activity": 0.9,  # good physical effort
        "privacy":           0.8,  # personal space
        "autonomy":          0.9,  # fully self-directed
        "hedonism":          0.6,  # often enjoyable
        "cost_saving":       0.8,  # very low cost
        "speed":             0.2,  # faster than walking
        "safety":           -0.2,  # some road risk
        "comfort":          -0.2,  # weather exposed
    },

    "car": {
        "pro_environment": -1.0,   # high emissions
        "physical_activity":-1.0,  # sedentary
        "privacy":          1.0,   # fully private
        "autonomy":         1.0,   # fully self-directed
        "hedonism":         0.3,   # can be enjoyable
        "cost_saving":     -0.8,   # fuel, parking, depreciation
        "speed":            0.9,   # fast door-to-door
        "safety":           0.2,   # airbags etc but crash risk
        "comfort":          0.9,   # climate controlled, seated
    },

    "pt": {
        "pro_environment":  0.8,   # shared emissions
        "physical_activity": 0.1,  # some walking to stops
        "privacy":          -0.8,  # crowded, shared space
        "autonomy":         -0.8,  # fixed schedule, fixed route
        "hedonism":         -0.1,  # rarely enjoyable
        "cost_saving":       0.6,  # cheaper than car
        "speed":             0.3,  # depends on network
        "safety":            0.8,  # statistically very safe
        "comfort":           0.2,  # seated but crowded
    },

    # -----------------------------------------------
    #  Intermodal combinations 
    # -----------------------------------------------

    "bike_pt": {
        # Biking to the stop + PT: blend of bike and PT attributes
        "pro_environment":   0.9,
        "physical_activity": 0.6,  # bike leg provides activity
        "privacy":          -0.2,  # bike is private, PT is not
        "autonomy":          0.1,  # more flexible than pure PT
        "hedonism":          0.3,
        "cost_saving":       0.7,
        "speed":             0.5,  # faster than pure PT due to bike
        "safety":            0.2,
        "comfort":          -0.1,
    },

    "car_pt": {
        # Drive to a park-and-ride then take PT
        "pro_environment":  -0.2,  # still uses car for first leg
        "physical_activity":-0.5,
        "privacy":           0.2,  # car leg is private
        "autonomy":          0.3,  # flexible first leg
        "hedonism":          0.2,
        "cost_saving":      -0.1,  # car costs + PT ticket
        "speed":             0.8,  # often fastest for long trips
        "safety":            0.5,
        "comfort":           0.7,  # comfortable car + seated PT
    },
}

# ------------------------------------
# Human-readable labels for display
# ------------------------------------
MODE_LABELS = {
    "foot":    "🚶 Walk",
    "bike":    "🚴 Bike",
    "car":     "🚗 Car",
    "pt":      "🚌 Public Transport",
    "bike_pt": "🚴+🚌 Bike & PT",
    "car_pt":  "🚗+🚌 Car & PT (P&R)",
}

# -----------------------------------   
# Which belief must be True for this mode to be available
# ------------------------------------
MODE_BELIEF_REQUIREMENTS = {
    "foot":    [],                          
    "bike":    ["owns_bike"],
    "car":     ["owns_car"],
    "pt":      ["has_pt_access"],
    "bike_pt": ["owns_bike", "has_pt_access"],
    "car_pt":  ["owns_car",  "has_pt_access"],
}


# ------------------------------------
# Route metric scoring
# Beyond value attributes, actual route metrics also feed into value scores.
# These functions map a route metric to a value dimension contribution.
# ------------------------------------  


def speed_score_from_duration(duration_s: float,
                               reference_s: float = 1800) -> float:
    """
    Convert actual travel time into a speed score.
    reference_s = 30 min baseline.  Faster → higher score, slower → lower.
    Clamped to [-1, +1].
    """
    if reference_s <= 0:
        return 0.0
    ratio = duration_s / reference_s   # 1.0 = exactly at baseline
    score = 1.0 - ratio                # faster than baseline → positive
    return max(-1.0, min(1.0, score))


def cost_score_from_mode(mode: str, distance_m: float) -> float:
    """
    Estimate relative cost score from mode and distance.
    Returns a score in [-1, +1] where +1 = free, -1 = expensive.
    """
    distance_km = distance_m / 1000

    if mode in ("foot",):
        return 1.0
    elif mode == "bike":
        return 0.9
    elif mode == "pt":
        # Flat fare approximation
        return 0.5
    elif mode == "bike_pt":
        return 0.6
    elif mode == "car":
        cost_per_km = 0.30   # €/km approximation
        relative = min(1.0, distance_km * cost_per_km / 10)
        return -relative
    elif mode == "car_pt":
        cost_per_km = 0.15
        relative = min(1.0, distance_km * cost_per_km / 10)
        return -relative * 0.5
    return 0.0


def comfort_score_from_transfers(transfers: int) -> float:
    """More transfers = less comfortable."""
    if transfers <= 0:
        return 0.5
    elif transfers == 1:
        return 0.0
    else:
        return max(-1.0, -0.3 * transfers)


def walking_distance_penalty(distance_km: float, profile_type: str = "biospheric") -> float:
    """
    Penalty for walking long distances based on research.
    
    Research shows walking acceptability drops sharply after 1-2 km:
    - < 1 km: 80% willing
    - 1-2 km: 40% willing
    - > 2 km: < 15% willing (Saelens & Handy 2008)
    
    Parameters
    ----------
    distance_km : float
        Walking distance in kilometers
    profile_type : str
        Agent profile type for tolerance adjustment
    
    Returns
    -------
    penalty : float
        Negative value to subtract from speed/comfort scores (-10.0 to 0.0)
    """
    # Base penalty curve (biospheric baseline - most tolerant)
    if distance_km <= 1.0:
        penalty = 0.0
    elif distance_km <= 2.0:
        # Light penalty: -0.3 at 2km
        penalty = -0.3 * (distance_km - 1.0)
    elif distance_km <= 3.0:
        # Moderate penalty: -0.9 at 3km
        penalty = -0.3 - 0.6 * (distance_km - 2.0)
    elif distance_km <= 5.0:
        # Severe penalty: -2.1 at 5km
        penalty = -0.9 - 0.6 * (distance_km - 3.0)
    else:
        # Extreme penalty: very steep beyond 5km
        penalty = -2.1 - 2.0 * (distance_km - 5.0)
    
    # Clamp to minimum
    penalty = max(-10.0, penalty)
    
    # Profile-based tolerance adjustments
    multipliers = {
        "biospheric": 0.7,   # 30% more tolerant (health-conscious)
        "altruistic": 0.9,   # 10% more tolerant
        "egoistic": 1.5,     # 50% LESS tolerant (values speed)
        "hedonic": 1.8,      # 80% LESS tolerant (values comfort)
    }
    
    multiplier = multipliers.get(profile_type, 1.0)
    return penalty * multiplier


def cycling_distance_penalty(distance_km: float, profile_type: str = "biospheric") -> float:
    """
    Penalty for cycling long distances based on research.
    
    Research from Netherlands/Denmark (high-cycling countries):
    - Average commute: 3-5 km
    - 75th percentile: 7 km
    - 90th percentile: 12 km
    - Only 5% of trips exceed 10 km (Pucher & Buehler 2008)
    
    Parameters
    ----------
    distance_km : float
        Cycling distance in kilometers
    profile_type : str
        Agent profile type for tolerance adjustment
    
    Returns
    -------
    penalty : float
        Negative value to subtract from speed/comfort scores (-10.0 to 0.0)
    """
    # Base penalty curve (biospheric baseline - most tolerant)
    if distance_km <= 5.0:
        penalty = 0.0
    elif distance_km <= 8.0:
        # Light penalty: -0.3 at 8km
        penalty = -0.1 * (distance_km - 5.0)
    elif distance_km <= 12.0:
        # Moderate penalty: -1.5 at 12km
        penalty = -0.3 - 0.3 * (distance_km - 8.0)
    elif distance_km <= 15.0:
        # Severe penalty: -3.0 at 15km
        penalty = -1.5 - 0.5 * (distance_km - 12.0)
    elif distance_km <= 20.0:
        # Extreme penalty: -7.0 at 20km
        penalty = -3.0 - 0.8 * (distance_km - 15.0)
    else:
        # Prohibitive: continues declining
        penalty = -7.0 - 1.0 * (distance_km - 20.0)
    
    # Clamp to minimum
    penalty = max(-10.0, penalty)
    
    # Profile-based tolerance adjustments
    multipliers = {
        "biospheric": 0.6,   # 40% more tolerant (pro-environment + physical activity)
        "altruistic": 1.2,   # 20% LESS tolerant (safety concerns on long rides)
        "egoistic": 1.3,     # 30% LESS tolerant (too slow vs car)
        "hedonic": 1.6,      # 60% LESS tolerant (physical effort)
    }
    
    multiplier = multipliers.get(profile_type, 1.0)
    return penalty * multiplier