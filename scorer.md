# HOW TRANSPORT MODE SCORING WORKS WITH AGENT VALUES
## A Complete Step-by-Step Explanation

---

## TABLE OF CONTENTS

1. Overview — The Big Picture
2. Stage 0: Agent Value Normalisation
3. Stage 1: Mode Attribute Matrix (Base Scores)
4. Stage 2: Metric Adjustments (Real Route Data)
5. Stage 3: Blending Attributes with Metrics
6. Stage 4: Computing Dimension Contributions
7. Stage 5: Computing Raw Total Score
8. Stage 6: Normalising to Utility Score 0-100
9. Complete Worked Example: Egoistic Agent Choosing Between Car and PT
10. Complete Worked Example: Biospheric Agent Choosing Between Bike and Car
11. Why Each Mode Scores the Way It Does
12. How to Calibrate the Scoring Model

---

## 1. OVERVIEW — THE BIG PICTURE

The scoring system answers this question: **"How well does this specific route serve this specific person's values?"**

The process:
1. Each agent has 9 value weights (0-1) representing what they care about
2. Each transport mode has 9 attribute scores (-1 to +1) representing how well it serves each value
3. Real route data (actual travel time, cost, etc.) adjusts 4 of these attributes
4. We compute: **contribution = agent_weight × mode_attribute** for each dimension
5. The raw score is the sum of all 9 contributions
6. We normalise all routes to 0-100 scale and rank them

**The mathematical formula:**

```
For each value dimension i (i = 1 to 9):
  blended_attr[i]  = (mode_attr[i] × 0.6) + (metric_adj[i] × 0.4)
  contribution[i]  = agent_weight[i] × blended_attr[i]

raw_score = sum(contribution[1] + contribution[2] + ... + contribution[9])

utility_score = ((raw_score - min_raw) / (max_raw - min_raw)) × 100
```

---

## 2. STAGE 0: AGENT VALUE NORMALISATION

**Input:** Raw psychological model scores (any range, e.g. -3.5 to +2.0)

**Output:** Normalised weights in [0, 1]

**Purpose:** Make the agent's values comparable within their own value vector

**Formula:**
```
For agent's raw value vector v = [v1, v2, ..., v9]:

  v_min = min(v1, v2, ..., v9)
  v_max = max(v1, v2, ..., v9)
  
  weight[i] = (v[i] - v_min) / (v_max - v_min)
```

**Example:**
```
Raw values from psychological model:
  pro_environment:   1.3691
  physical_activity: -3.5205   ← LOWEST (negative!)
  privacy:            0.6505
  autonomy:           1.5453
  hedonism:           0.0
  cost_saving:        1.3546
  speed:              1.6364
  safety:             2.0375   ← HIGHEST
  comfort:            1.2110

Step 1: Find min and max
  min = -3.5205
  max = 2.0375
  span = 2.0375 - (-3.5205) = 5.558

Step 2: Normalise each value
  pro_environment:   (1.3691 - (-3.5205)) / 5.558 = 0.887
  physical_activity: (-3.5205 - (-3.5205)) / 5.558 = 0.000  ← now LOWEST (0)
  privacy:           (0.6505 - (-3.5205)) / 5.558 = 0.750
  autonomy:          (1.5453 - (-3.5205)) / 5.558 = 0.912
  hedonism:          (0.0 - (-3.5205)) / 5.558 = 0.633
  cost_saving:       (1.3546 - (-3.5205)) / 5.558 = 0.877
  speed:             (1.6364 - (-3.5205)) / 5.558 = 0.929
  safety:            (2.0375 - (-3.5205)) / 5.558 = 1.000  ← now HIGHEST (1)
  comfort:           (1.2110 - (-3.5205)) / 5.558 = 0.851
```

**Key insight:** After normalisation, 1.0 means "this is what I care about MOST" and 0.0 means "this is what I care about LEAST" **within this agent's own value system**.

---

## 3. STAGE 1: MODE ATTRIBUTE MATRIX (BASE SCORES)

**Purpose:** Define how well each mode inherently serves each value, independent of the specific route

**Scale:** -1.0 (strongly conflicts) to +1.0 (strongly satisfies)

**Complete matrix:**

```
VALUE DIMENSION      | WALK  | BIKE  | CAR   | PT    | BIKE+PT | CAR+PT
─────────────────────|───────|───────|───────|───────|─────────|────────
pro_environment      | +1.0  | +1.0  | -1.0  | +0.8  | +0.9    | -0.2
physical_activity    | +1.0  | +0.9  | -1.0  | +0.1  | +0.6    | -0.5
privacy              | +0.8  | +0.8  | +1.0  | -0.8  | -0.2    | +0.2
autonomy             | +0.8  | +0.9  | +1.0  | -0.8  | +0.1    | +0.3
hedonism             | +0.4  | +0.6  | +0.3  | -0.1  | +0.3    | +0.2
cost_saving          | +1.0  | +0.8  | -0.8  | +0.6  | +0.7    | -0.1
speed                | -1.0  | +0.2  | +0.9  | +0.3  | +0.5    | +0.8
safety               | +0.3  | -0.2  | +0.2  | +0.8  | +0.2    | +0.5
comfort              | -0.5  | -0.2  | +0.9  | +0.2  | -0.1    | +0.7
```

**Reading the matrix:**

- **Walk + pro_environment = +1.0** — Walking has ZERO emissions, perfect for environment
- **Car + pro_environment = -1.0** — Car has HIGH emissions, terrible for environment
- **PT + privacy = -0.8** — Public transport is CROWDED, bad for privacy
- **Car + autonomy = +1.0** — Car gives you FULL control over schedule and route
- **Walk + speed = -1.0** — Walking is the SLOWEST mode

**Where do these numbers come from?**

These are derived from transport psychology research literature:
- Steg et al. (2014) — hedonic values in transport
- De Groot & Steg (2008) — environmental values and mode choice
- Schwartz value theory (1992) — value circumplex structure

You can tune any of these numbers in `value_model.py` to reflect your local context (e.g. if your city has excellent cycling infrastructure, you might raise bike safety from -0.2 to +0.4).

---

## 4. STAGE 2: METRIC ADJUSTMENTS (REAL ROUTE DATA)

**Purpose:** Adjust 4 dimensions based on the actual route GraphHopper computed

**Why?** The mode attributes are generic. A "car" route can be 5 minutes or 60 minutes. A "PT" route can have 0 transfers or 5 transfers. We need to account for this variation.

**The 4 adjusted dimensions:**

### 4.1 SPEED ADJUSTMENT

**Formula:**
```python
speed_score = 1.0 - (actual_duration_seconds / 1800)
speed_score = clamp(speed_score, -1.0, +1.0)
```

**Reference:** 1800 seconds = 30 minutes baseline

**Examples:**
```
Duration   | Score  | Interpretation
-----------|--------|------------------
0 min      | +1.0   | Instant (impossible but theoretical max)
10 min     | +0.67  | Very fast
30 min     | 0.0    | Exactly at baseline
45 min     | -0.5   | Slower than baseline
60 min     | -1.0   | Double the baseline time
90+ min    | -1.0   | Clamped at worst score
```

**This replaces the generic speed attribute from the matrix.**

---

### 4.2 COST_SAVING ADJUSTMENT

**Formula:**
```python
def cost_score_from_mode(mode, distance_m):
    distance_km = distance_m / 1000
    
    if mode == "foot":
        return +1.0    # Free
    
    elif mode == "bike":
        return +0.9    # Very cheap (minor maintenance)
    
    elif mode == "pt":
        return +0.5    # Flat fare assumption
    
    elif mode == "bike_pt":
        return +0.6    # PT fare only
    
    elif mode == "car":
        cost_per_km = 0.30  # €/km fuel + depreciation
        relative = min(1.0, distance_km * cost_per_km / 10)
        return -relative     # Negative because expensive
        
        # Examples:
        # 5 km  → -(5 × 0.30 / 10) = -0.15
        # 20 km → -(20 × 0.30 / 10) = -0.60
        # 50 km → -1.0 (clamped)
    
    elif mode == "car_pt":
        cost_per_km = 0.15  # Shorter car leg
        relative = min(1.0, distance_km * cost_per_km / 10)
        return -relative * 0.5
```

**This replaces the generic cost_saving attribute from the matrix.**

---

### 4.3 COMFORT ADJUSTMENT

**Formula:**
```python
def comfort_score_from_transfers(transfers):
    if transfers == 0:
        return +0.5   # Direct journey is more comfortable
    elif transfers == 1:
        return 0.0    # One transfer is neutral
    else:
        return max(-1.0, -0.3 * transfers)
        
        # Examples:
        # 2 transfers → -0.6
        # 3 transfers → -0.9
        # 4+ transfers → -1.0 (clamped)
```

**This replaces the generic comfort attribute from the matrix.**

---

### 4.4 PHYSICAL_ACTIVITY ADJUSTMENT

**Formula:**
```python
def physical_activity_from_route(route):
    # Sum up all walk and bike legs
    active_distance_m = sum(leg.distance_m 
                            for leg in route.legs 
                            if leg.mode in ("walk", "bike"))
    
    # Normalise: 5000m = full score
    score = min(1.0, active_distance_m / 5000)
    return score
    
    # Examples:
    # 500m walk   → 0.1
    # 1000m walk  → 0.2
    # 2500m bike  → 0.5
    # 5000m+ bike → 1.0
```

**This replaces the generic physical_activity attribute from the matrix.**

---

### Summary of what gets adjusted:

```
Dimension            | Adjusted? | Adjustment source
---------------------|-----------|--------------------------------
pro_environment      | NO        | Use mode attribute
physical_activity    | YES       | Sum of walk + bike distance
privacy              | NO        | Use mode attribute
autonomy             | NO        | Use mode attribute
hedonism             | NO        | Use mode attribute
cost_saving          | YES       | Mode + distance formula
speed                | YES       | Actual route duration
safety               | NO        | Use mode attribute
comfort              | YES       | Number of PT transfers
```

---

## 5. STAGE 3: BLENDING ATTRIBUTES WITH METRICS

**Purpose:** Combine the generic mode attribute with the route-specific metric adjustment

**Formula:**
```python
METRIC_BLEND = 0.4  # Configurable (0.0 to 1.0)

blended = (mode_attribute × 0.6) + (metric_adjustment × 0.4)
blended = clamp(blended, -1.0, +1.0)
```

**Interpretation:**
- `METRIC_BLEND = 0.0` → Pure value model, ignore actual route data
- `METRIC_BLEND = 0.4` → 60% generic mode / 40% actual route (default)
- `METRIC_BLEND = 1.0` → Actual route data fully overrides generic mode

**Example: Speed for an 8-minute car journey**

```
mode_attribute   = +0.9  (car is generically fast)
metric_adjustment = +0.86 (8 min → score = 1 - 480/1800 = +0.73, 
                           but let's say it computed to 0.86)

blended = (0.9 × 0.6) + (0.86 × 0.4)
        = 0.54 + 0.344
        = 0.884
```

**Example: Pro_environment for a car (no adjustment)**

```
mode_attribute    = -1.0  (car is terrible for environment)
metric_adjustment = 0.0   (no adjustment for this dimension)

blended = (-1.0 × 0.6) + (0.0 × 0.4)
        = -0.6 + 0.0
        = -0.6
```

---

## 6. STAGE 4: COMPUTING DIMENSION CONTRIBUTIONS

**Purpose:** Weight each blended attribute by how much the agent cares about that dimension

**Formula:**
```python
contribution[i] = agent_weight[i] × blended_attribute[i]
```

**Example: Egoistic agent (w_speed = 0.90) evaluating a fast car route**

```
agent_weight[speed] = 0.90       (speed is very important to this agent)
blended_attr[speed] = +0.884     (car is fast AND this route is 8 min)

contribution[speed] = 0.90 × 0.884 = +0.796
```

**Key insight:** Even if a mode scores perfectly on a dimension (+1.0), if the agent doesn't care about that dimension (weight = 0.0), the contribution is ZERO.

**Example: Same agent, pro_environment dimension**

```
agent_weight[pro_env] = 0.05     (environment is NOT important to this agent)
blended_attr[pro_env] = -0.6     (car is bad for environment)

contribution[pro_env] = 0.05 × (-0.6) = -0.03
```

Notice: Even though car is terrible for the environment (-0.6), the negative contribution is tiny (-0.03) because this agent simply doesn't weight environmental concerns highly.

---

## 7. STAGE 5: COMPUTING RAW TOTAL SCORE

**Purpose:** Add up all 9 dimension contributions to get one overall route score

**Formula:**
```python
raw_score = sum(contribution[1] + contribution[2] + ... + contribution[9])
```

**Example: Egoistic agent evaluating a car route**

```
Dimension            | agent_weight | blended_attr | contribution
---------------------|--------------|--------------|-------------
pro_environment      | 0.05         | -0.60        | -0.030
physical_activity    | 0.00         | -0.60        |  0.000
privacy              | 0.90         | +1.00        | +0.900
autonomy             | 0.95         | +1.00        | +0.950
hedonism             | 0.50         | +0.30        | +0.150
cost_saving          | 0.80         | -0.18        | -0.144
speed                | 0.90         | +0.88        | +0.792
safety               | 0.60         | +0.20        | +0.120
comfort              | 0.70         | +0.90        | +0.630
                                                   ──────────
                                        raw_score = +3.368
```

**Interpretation:** The raw score can be any value. Typically ranges from -3 to +3 depending on the match between agent and route.

---

## 8. STAGE 6: NORMALISING TO UTILITY SCORE 0-100

**Purpose:** Make scores easy to interpret. Best route = 100, worst route = 0.

**Formula:**
```python
# For all N candidate routes:
min_raw = min(raw_score[1], raw_score[2], ..., raw_score[N])
max_raw = max(raw_score[1], raw_score[2], ..., raw_score[N])

utility_score[k] = ((raw_score[k] - min_raw) / (max_raw - min_raw)) × 100
```

**Example: 5 routes for egoistic agent**

```
Route   | raw_score | Calculation                      | utility_score
--------|-----------|----------------------------------|---------------
Car     | +3.368    | ((3.368 - (-0.847)) / 4.215) × 100 | 100.0 ← BEST
Car+PT  | +2.105    | ((2.105 - (-0.847)) / 4.215) × 100 | 70.0
PT      | +0.432    | ((0.432 - (-0.847)) / 4.215) × 100 | 30.3
Bike    | +0.251    | ((0.251 - (-0.847)) / 4.215) × 100 | 26.0
Walk    | -0.847    | ((-0.847 - (-0.847)) / 4.215) × 100 | 0.0 ← WORST

Where: min_raw = -0.847, max_raw = +3.368, span = 4.215
```

**Key properties:**
- Best route always scores exactly 100
- Worst route always scores exactly 0
- All other routes are linearly interpolated
- Routes are then sorted by utility_score descending
- The top-ranked route is the engine's recommendation

---

## 9. COMPLETE WORKED EXAMPLE: EGOISTIC AGENT CHOOSING CAR VS PT

**Agent profile:**
```json
{
  "id": "agent_egoistic",
  "values": {
    "pro_environment":   0.05,
    "physical_activity": 0.10,
    "privacy":           0.90,
    "autonomy":          0.95,
    "hedonism":          0.50,
    "cost_saving":       0.80,
    "speed":             0.90,
    "safety":            0.60,
    "comfort":           0.70
  }
}
```

**Journey:** 6 km trip
- **Car:** 8 minutes, direct
- **PT:** 22 minutes, 1 transfer

---

### SCORING CAR ROUTE

**Step 1: Get base attributes from matrix**
```
pro_environment:  -1.0
physical_activity: -1.0
privacy:           +1.0
autonomy:          +1.0
hedonism:          +0.3
cost_saving:       -0.8
speed:             +0.9
safety:            +0.2
comfort:           +0.9
```

**Step 2: Compute metric adjustments**
```
speed:
  duration = 8 min = 480s
  score = 1 - (480 / 1800) = 1 - 0.267 = +0.733

cost_saving:
  distance = 6 km
  relative_cost = 6 × 0.30 / 10 = 0.18
  score = -0.18

comfort:
  transfers = 0
  score = +0.5

physical_activity:
  active_distance = 0 m
  score = 0.0

(Others: no adjustment, use 0.0)
```

**Step 3: Blend attributes with metrics (METRIC_BLEND = 0.4)**
```
pro_environment:  (-1.0 × 0.6) + (0.0 × 0.4) = -0.60
physical_activity: (-1.0 × 0.6) + (0.0 × 0.4) = -0.60
privacy:           (+1.0 × 0.6) + (0.0 × 0.4) = +0.60
autonomy:          (+1.0 × 0.6) + (0.0 × 0.4) = +0.60
hedonism:          (+0.3 × 0.6) + (0.0 × 0.4) = +0.18
cost_saving:       (-0.8 × 0.6) + (-0.18 × 0.4) = -0.55
speed:             (+0.9 × 0.6) + (+0.733 × 0.4) = +0.83
safety:            (+0.2 × 0.6) + (0.0 × 0.4) = +0.12
comfort:           (+0.9 × 0.6) + (+0.5 × 0.4) = +0.74
```

**Step 4: Multiply by agent weights**
```
Dimension          | weight | blended | contribution
-------------------|--------|---------|-------------
pro_environment    | 0.05   | -0.60   | -0.030
physical_activity  | 0.10   | -0.60   | -0.060
privacy            | 0.90   | +0.60   | +0.540
autonomy           | 0.95   | +0.60   | +0.570
hedonism           | 0.50   | +0.18   | +0.090
cost_saving        | 0.80   | -0.55   | -0.440
speed              | 0.90   | +0.83   | +0.747
safety             | 0.60   | +0.12   | +0.072
comfort            | 0.70   | +0.74   | +0.518
                                      ───────────
                           CAR raw_score = +2.007
```

---

### SCORING PT ROUTE

**Step 1: Get base attributes from matrix**
```
pro_environment:  +0.8
physical_activity: +0.1
privacy:           -0.8
autonomy:          -0.8
hedonism:          -0.1
cost_saving:       +0.6
speed:             +0.3
safety:            +0.8
comfort:           +0.2
```

**Step 2: Compute metric adjustments**
```
speed:
  duration = 22 min = 1320s
  score = 1 - (1320 / 1800) = 1 - 0.733 = +0.267

cost_saving:
  mode = "pt"
  score = +0.5

comfort:
  transfers = 1
  score = 0.0

physical_activity:
  active_distance = 320m + 180m = 500m (walk to/from stops)
  score = 500 / 5000 = 0.1
```

**Step 3: Blend attributes with metrics (METRIC_BLEND = 0.4)**
```
pro_environment:  (+0.8 × 0.6) + (0.0 × 0.4) = +0.48
physical_activity: (+0.1 × 0.6) + (+0.1 × 0.4) = +0.10
privacy:           (-0.8 × 0.6) + (0.0 × 0.4) = -0.48
autonomy:          (-0.8 × 0.6) + (0.0 × 0.4) = -0.48
hedonism:          (-0.1 × 0.6) + (0.0 × 0.4) = -0.06
cost_saving:       (+0.6 × 0.6) + (+0.5 × 0.4) = +0.56
speed:             (+0.3 × 0.6) + (+0.267 × 0.4) = +0.29
safety:            (+0.8 × 0.6) + (0.0 × 0.4) = +0.48
comfort:           (+0.2 × 0.6) + (0.0 × 0.4) = +0.12
```

**Step 4: Multiply by agent weights**
```
Dimension          | weight | blended | contribution
-------------------|--------|---------|-------------
pro_environment    | 0.05   | +0.48   | +0.024
physical_activity  | 0.10   | +0.10   | +0.010
privacy            | 0.90   | -0.48   | -0.432
autonomy           | 0.95   | -0.48   | -0.456
hedonism           | 0.50   | -0.06   | -0.030
cost_saving        | 0.80   | +0.56   | +0.448
speed              | 0.90   | +0.29   | +0.261
safety             | 0.60   | +0.48   | +0.288
comfort            | 0.70   | +0.12   | +0.084
                                      ───────────
                           PT raw_score = +0.197
```

---

### FINAL COMPARISON

```
Route | raw_score | utility_score
------|-----------|---------------
Car   | +2.007    | 100.0
PT    | +0.197    | 0.0

Calculation:
  min_raw = +0.197
  max_raw = +2.007
  span = 1.810
  
  Car utility = ((2.007 - 0.197) / 1.810) × 100 = 100.0
  PT utility  = ((0.197 - 0.197) / 1.810) × 100 = 0.0
```

**Recommendation: Car (100.0 points)**

**Why?**
- Car perfectly serves this agent's top values: autonomy (0.95), speed (0.90), privacy (0.90)
- PT conflicts heavily with autonomy (-0.456) and privacy (-0.432)
- The agent doesn't care about pro_environment (0.05), so car's terrible environmental score barely hurts it

---

## 10. COMPLETE WORKED EXAMPLE: BIOSPHERIC AGENT CHOOSING BIKE VS CAR

**Agent profile:**
```json
{
  "id": "agent_biospheric",
  "values": {
    "pro_environment":   0.98,
    "physical_activity": 0.75,
    "privacy":           0.20,
    "autonomy":          0.30,
    "hedonism":          0.10,
    "cost_saving":       0.35,
    "speed":             0.10,
    "safety":            0.60,
    "comfort":           0.15
  }
}
```

**Journey:** 6 km trip
- **Bike:** 24 minutes, direct
- **Car:** 8 minutes, direct

---

### SCORING BIKE ROUTE

**Step 1: Base attributes**
```
pro_environment:   +1.0
physical_activity: +0.9
privacy:           +0.8
autonomy:          +0.9
hedonism:          +0.6
cost_saving:       +0.8
speed:             +0.2
safety:            -0.2
comfort:           -0.2
```

**Step 2: Metric adjustments**
```
speed: 1 - (1440 / 1800) = +0.2
cost_saving: +0.9 (bike is cheap)
comfort: +0.5 (no transfers)
physical_activity: 6000 / 5000 = 1.0 (full score, clamped)
```

**Step 3: Blend (0.6 generic + 0.4 metric)**
```
pro_environment:   (+1.0 × 0.6) + (0.0 × 0.4) = +0.60
physical_activity: (+0.9 × 0.6) + (+1.0 × 0.4) = +0.94
privacy:           (+0.8 × 0.6) + (0.0 × 0.4) = +0.48
autonomy:          (+0.9 × 0.6) + (0.0 × 0.4) = +0.54
hedonism:          (+0.6 × 0.6) + (0.0 × 0.4) = +0.36
cost_saving:       (+0.8 × 0.6) + (+0.9 × 0.4) = +0.84
speed:             (+0.2 × 0.6) + (+0.2 × 0.4) = +0.20
safety:            (-0.2 × 0.6) + (0.0 × 0.4) = -0.12
comfort:           (-0.2 × 0.6) + (+0.5 × 0.4) = +0.08
```

**Step 4: Weight by agent**
```
Dimension          | weight | blended | contribution
-------------------|--------|---------|-------------
pro_environment    | 0.98   | +0.60   | +0.588
physical_activity  | 0.75   | +0.94   | +0.705
privacy            | 0.20   | +0.48   | +0.096
autonomy           | 0.30   | +0.54   | +0.162
hedonism           | 0.10   | +0.36   | +0.036
cost_saving        | 0.35   | +0.84   | +0.294
speed              | 0.10   | +0.20   | +0.020
safety             | 0.60   | -0.12   | -0.072
comfort            | 0.15   | +0.08   | +0.012
                                      ───────────
                          BIKE raw_score = +1.841
```

---

### SCORING CAR ROUTE (same as before)

```
Dimension          | weight | blended | contribution
-------------------|--------|---------|-------------
pro_environment    | 0.98   | -0.60   | -0.588
physical_activity  | 0.75   | -0.60   | -0.450
privacy            | 0.20   | +0.60   | +0.120
autonomy           | 0.30   | +0.60   | +0.180
hedonism           | 0.10   | +0.18   | +0.018
cost_saving        | 0.35   | -0.55   | -0.193
speed              | 0.10   | +0.83   | +0.083
safety             | 0.60   | +0.12   | +0.072
comfort            | 0.15   | +0.74   | +0.111
                                      ───────────
                           CAR raw_score = -0.647
```

---

### FINAL COMPARISON

```
Route | raw_score | utility_score
------|-----------|---------------
Bike  | +1.841    | 100.0
Car   | -0.647    | 0.0

Span: 1.841 - (-0.647) = 2.488
Bike utility: ((1.841 - (-0.647)) / 2.488) × 100 = 100.0
Car utility:  ((-0.647 - (-0.647)) / 2.488) × 100 = 0.0
```

**Recommendation: Bike (100.0 points)**

**Why?**
- Bike perfectly serves this agent's top values: pro_environment (0.98) and physical_activity (0.75)
- Car gets HEAVILY penalised on the agent's two most important dimensions
- Speed doesn't matter to this agent (0.10), so car's speed advantage is irrelevant

---

## 11. WHY EACH MODE SCORES THE WAY IT DOES

### 🚶 WALKING

**Strengths (+1.0 or high positive):**
- pro_environment: Zero emissions
- physical_activity: Maximum exercise
- cost_saving: Completely free

**Weaknesses (-1.0 or high negative):**
- speed: Slowest mode by far
- comfort: Weather exposed, gets tiring

**Best for:** Biospheric agents on short trips (<1km)

---

### 🚴 CYCLING

**Strengths:**
- pro_environment: Zero emissions
- physical_activity: Excellent exercise
- autonomy: Full route/schedule control
- cost_saving: Very cheap maintenance

**Weaknesses:**
- safety: Vulnerable to traffic
- comfort: Weather exposed

**Best for:** Biospheric agents on medium trips (1-15km)

---

### 🚗 CAR

**Strengths:**
- privacy: Fully private space
- autonomy: Complete control
- speed: Fast door-to-door
- comfort: Climate controlled, seated

**Weaknesses:**
- pro_environment: High emissions
- physical_activity: Zero exercise
- cost_saving: Expensive (fuel, parking, depreciation)

**Best for:** Egoistic and hedonic agents prioritising speed, comfort, autonomy

---

### 🚌 PUBLIC TRANSPORT (PT)

**Strengths:**
- pro_environment: Shared emissions (good)
- safety: Statistically very safe
- cost_saving: Cheaper than car

**Weaknesses:**
- privacy: Crowded, no personal space
- autonomy: Fixed schedule and routes
- hedonism: Rarely enjoyable experience

**Best for:** Altruistic agents (safety conscious, pro-social)

---

### 🚴+🚌 BIKE + PT

**Strengths:**
- pro_environment: Very good (bike leg + shared PT)
- physical_activity: Moderate (bike leg provides exercise)
- speed: Faster than pure PT due to bike leg
- cost_saving: Good (only PT fare)

**Weaknesses:**
- privacy: Negative (PT leg is crowded)
- comfort: Negative (requires bike handling + PT)

**Best for:** Biospheric agents on medium-long trips where cycling alone is too far

---

### 🚗+🚌 CAR + PT (Park & Ride)

**Strengths:**
- speed: Often fastest for long trips
- comfort: High (comfortable car + seated PT)
- safety: Moderate-high

**Weaknesses:**
- pro_environment: Still uses car
- physical_activity: Low (minimal walking)
- cost_saving: Negative (car costs + PT fare)

**Best for:** Egoistic agents on long trips where driving the whole way would be slower due to traffic/parking

---

## 12. HOW TO CALIBRATE THE SCORING MODEL

### 12.1 Adjusting Mode Attributes

**File:** `src/value_model.py` → `MODE_ATTRIBUTES` dictionary

**Example: Your city has excellent cycling infrastructure**
```python
"bike": {
    "safety": +0.4,  # Changed from -0.2
    # This makes cycling much more attractive to safety-conscious agents
}
```

**Example: Your PT network is unreliable**
```python
"pt": {
    "autonomy": -0.9,  # Changed from -0.8
    # This makes PT even less attractive to autonomy-seeking agents
}
```

---

### 12.2 Adjusting Metric Blend Ratio

**File:** `src/personalised_router.py` → `METRIC_BLEND`

**Current:** `METRIC_BLEND = 0.4` (60% generic mode, 40% actual route)

**Pure value model (ignore actual times/costs):**
```python
METRIC_BLEND = 0.0
# Now only the agent's values and mode attributes matter
# Useful for theoretical value analysis
```

**Reality-driven model (actual times/costs dominate):**
```python
METRIC_BLEND = 1.0
# Now the actual route performance fully overrides generic mode attributes
# Useful if you want more emphasis on real-world metrics
```

---

### 12.3 Adjusting Speed Reference Time

**File:** `src/value_model.py` → `speed_score_from_duration`

**Current:** `reference_s = 1800` (30 minutes)

**For a small city:**
```python
reference_s = 1200  # 20 minute baseline
# Journeys are generally shorter, so 30 min is now "slow"
```

**For a large city:**
```python
reference_s = 2700  # 45 minute baseline
# Journeys are generally longer, so 30 min is now "fast"
```

---

### 12.4 Adjusting Cost Rates

**File:** `src/value_model.py` → `cost_score_from_mode`

**Current:** `cost_per_km = 0.30` euros/km for car

**For high fuel prices:**
```python
cost_per_km = 0.50  # Expensive fuel
# Car becomes even less attractive to cost-conscious agents
```

**For electric cars:**
```python
if mode == "car_electric":
    cost_per_km = 0.10  # Much cheaper per km
```

---

### 12.5 Adjusting Physical Activity Threshold

**File:** `src/personalised_router.py` → `_metric_adjustments`

**Current:** `active_distance / 5000` (5km = full score)

**For less active users:**
```python
score = min(1.0, active_distance / 3000)  # 3km = full score
# Shorter active distances now count as "fully satisfying" physical activity
```

**For very active users:**
```python
score = min(1.0, active_distance / 10000)  # 10km = full score
# Requires much longer distances to fully satisfy physical activity need
```

---

### 12.6 Adjusting Distance Thresholds

**File:** `src/intermodal_router.py` → class constants

**Current thresholds:**
```python
BIKE_MAX_KM = 15.0    # Don't suggest biking beyond this
CAR_PT_MIN_KM = 5.0   # Only suggest park-and-ride above this
```

**For a hilly city (cycling is harder):**
```python
BIKE_MAX_KM = 8.0     # Suggest biking only up to 8km
```

**For a city with poor parking (park-and-ride more attractive):**
```python
CAR_PT_MIN_KM = 2.0   # Suggest park-and-ride even for short trips
```

---

## SUMMARY

The scoring algorithm is a **multi-criteria decision analysis** system that:

1. Normalises agent values to make them comparable (Stage 0)
2. Uses a mode attribute matrix to capture generic mode-value relationships (Stage 1)
3. Adjusts 4 dimensions using actual route data from GraphHopper (Stage 2)
4. Blends generic and actual attributes (Stage 3)
5. Weights each dimension by how much the agent cares (Stage 4)
6. Sums all contributions to get a raw score (Stage 5)
7. Normalises to 0-100 so the best route always scores 100 (Stage 6)

**The key insight:** A route's score depends on BOTH:
- How well the mode inherently serves each value (mode attributes)
- How much the agent cares about each value (agent weights)

This is why the **same route** gets completely different scores for different agents. An 8-minute car journey scores 100/100 for an egoistic agent but 0/100 for a biospheric agent, even though it's the exact same route.
