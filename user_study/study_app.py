# study_app.py
# Simple Engine — Phase 1 User Study
#
# Two conditions per scenario (within-subject):
#   'personalised' — value-based router using the participant's chosen archetype
#   'baseline'     — GraphHopper fastest route, uniform value weights (1/11 each)
#
# Key endpoints:
#   POST /api/demographics          — save background + mobility data
#   POST /api/profile               — save chosen archetype
#   GET  /api/scenarios             — list 4 study scenarios
#   GET  /api/scenario/<id>/ranking — generate both conditions, return together
#   POST /api/scenario-response     — save rankings + per-route ratings
#   POST /api/final-feedback        — save post-session questionnaire
#   GET  /admin/dashboard           — researcher view

import json
import os
import sys
import uuid
import math
from pathlib import Path
from datetime import datetime, timezone

from flask import Flask, redirect, request, jsonify, render_template, session

from study_db_mysql import get_connection, init_database, seed_scenarios, create_database_if_not_exists

# ─────────────────────────────────────────────
#  Flask setup
# ─────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-this-in-production")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True

CURRENT_DIR  = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
SRC_PATH     = PROJECT_ROOT / "src"
AGENTS_PATH  = PROJECT_ROOT / "agents"

sys.path.insert(0, str(SRC_PATH))

# ─────────────────────────────────────────────
#  Engine imports
# ─────────────────────────────────────────────

from agent import Agent
from graphhopper_client import GraphHopperClient
from personalised_router import PersonalisedRouter
from value_model import VALUE_DIMENSIONS

AGENT_FILES = {
    "biospheric": AGENTS_PATH / "agent_biospheric.json",
    "altruistic":  AGENTS_PATH / "agent_altruistic.json",
    "egoistic":    AGENTS_PATH / "agent_egoistic.json",
    "hedonic":     AGENTS_PATH / "agent_hedonic.json",
}

def _generate_baseline_routes(scenario: dict, agent: Agent) -> list[dict]:
    """
    Baseline (Set B): pure GraphHopper fastest route per mode, no value
    scoring. Routes sorted by duration only — fastest first.

    Contrast with Set A (value-ranked):
      Set A top = best match to agent values
      Set B top = always the fastest available option

    For a biospheric agent: Set A tops bike/walk; Set B tops car/PT.
    That divergence is what participants evaluate.
    """
    gh = GraphHopperClient(base_url=os.getenv("GRAPHHOPPER_HOST", "http://localhost:8080"))

    from_lat = scenario["origin_lat"]
    from_lon = scenario["origin_lon"]
    to_lat   = scenario["destination_lat"]
    to_lon   = scenario["destination_lon"]

    # Set B always shows all 4 modes regardless of agent beliefs.
    # Beliefs (owns_car, owns_bike) control Set A (personalised) only —
    # there it determines which modes are scored and which are greyed out.
    # Set B represents what the city's transport network offers to anyone,
    # so all physically available modes are shown and ranked by speed.
    raw_routes = []

    foot = gh.route_foot(from_lat, from_lon, to_lat, to_lon)
    if foot:
        raw_routes.append(("foot", "🚶 Walk", foot[0]))

    bike = gh.route_bike(from_lat, from_lon, to_lat, to_lon)
    if bike:
        raw_routes.append(("bike", "🚴 Bike", bike[0]))

    car = gh.route_car(from_lat, from_lon, to_lat, to_lon)
    if car:
        r = car[0]
        r.duration_s += 8 * 60   # parking overhead (same as personalised condition)
        raw_routes.append(("car", "🚗 Car", r))

    pt = gh.route_pt(from_lat, from_lon, to_lat, to_lon,
                     departure_time=DEPARTURE,
                     max_walk_meters=1500,
                     limit_solutions=2)
    if pt:
        raw_routes.append(("pt", "🚌 Public Transport", pt[0]))

    # Sort by duration — this is the only ranking criterion for baseline
    raw_routes.sort(key=lambda x: x[2].duration_s)

    results = []
    for rank, (mode_key, label, r) in enumerate(raw_routes, 1):
        dur_min  = round(r.duration_s / 60, 1)
        dist_km  = round(r.distance_m / 1000, 2)
        results.append({
            "scenario_id":            scenario["id"],
            "route_condition":        "baseline",
            "route_rank":             rank,
            "route_id":               f"S{scenario['id']}_BASE_R{rank}_{mode_key}",
            "route_summary":          label,
            "transport_modes":        mode_key,
            "is_intermodal":          0,
            "intermodal_type":        mode_key,
            "total_duration_minutes": dur_min,
            "walking_minutes":        dur_min if mode_key == "foot" else 0,
            "cycling_minutes":        dur_min if mode_key == "bike" else 0,
            "pt_minutes":             dur_min if mode_key == "pt"   else 0,
            "driving_minutes":        dur_min if mode_key == "car"  else 0,
            "transfer_count":         getattr(r, "transfers", 0),
            "engine_total_score":     None,
            "raw_route_json":         json.dumps({
                "rank": rank, "mode_key": mode_key, "condition": "baseline",
                "duration_min": dur_min, "distance_km": dist_km,
            }),
        })
    return results
# ─────────────────────────────────────────────
#  Database bootstrap
# ─────────────────────────────────────────────

_db_initialised = False

@app.before_request
def ensure_database():
    global _db_initialised
    if not _db_initialised:
        create_database_if_not_exists()
        init_database()
        seed_scenarios()
        _db_initialised = True

# ─────────────────────────────────────────────
#  Participant helpers
# ─────────────────────────────────────────────

def create_participant() -> int:
    code = str(uuid.uuid4())[:8].upper()
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO participants (participant_code, consent_given, study_phase) VALUES (?, 1, 1)",
            (code,),
        )
        conn.commit()
        pid = cursor.lastrowid
    session["participant_id"]   = pid
    session["participant_code"] = code
    return pid


def get_or_create_participant_id() -> int:
    pid = session.get("participant_id")
    if pid:
        with get_connection() as conn:
            row = conn.execute("SELECT id FROM participants WHERE id = ?", (pid,)).fetchone()
        if row:
            return pid
    return create_participant()

# ─────────────────────────────────────────────
#  Agent loading
# ─────────────────────────────────────────────

def load_agent(profile_name: str) -> Agent:
    if profile_name not in AGENT_FILES:
        raise ValueError(f"Unknown profile: {profile_name}")
    path = AGENT_FILES[profile_name]
    if not path.exists():
        raise FileNotFoundError(f"Agent file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return Agent.from_dict(json.load(f))


def get_selected_profile(participant_id: int):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT selected_profile FROM participants WHERE id = ?", (participant_id,)
        ).fetchone()
    return row["selected_profile"] if row else None

# ─────────────────────────────────────────────
#  Route conversion helper
# ─────────────────────────────────────────────

def _safe(obj, attr, default=None):
    return obj.get(attr, default) if isinstance(obj, dict) else getattr(obj, attr, default)


def convert_route(result, scenario_id: int, condition: str) -> dict:
    """Convert one engine ScoredRoute into the db/frontend format."""
    route      = _safe(result, "route", result)
    rank       = _safe(result, "rank", None)
    mode_key   = _safe(result, "mode_key", f"route_{rank}")
    mode_label = _safe(result, "mode_label", mode_key)
    score      = _safe(result, "utility_score", _safe(result, "score", None))

    legs         = _safe(route, "legs", []) or []
    modes        = [_safe(l, "mode") for l in legs if _safe(l, "mode")]
    unique_modes = list(dict.fromkeys(modes)) or [mode_key]

    def leg_minutes(mode_name):
        return round(
            sum(_safe(l, "duration_s", 0) or 0 for l in legs if _safe(l, "mode") == mode_name) / 60,
            1,
        )

    duration_min = _safe(route, "duration_min",
                   _safe(route, "total_duration_minutes", None))
    distance_km  = _safe(route, "distance_km", None)
    transfers    = _safe(route, "transfers", _safe(route, "transfer_count", 0))

    # Per-dimension scores (from ScoredRoute.dimension_scores)
    dim_scores = {}
    dimension_scores_list = _safe(result, "dimension_scores", []) or []
    for ds in dimension_scores_list:
        dim  = _safe(ds, "dimension")
        cont = _safe(ds, "contribution")
        if dim and cont is not None:
            dim_scores[f"score_{dim}"] = round(float(cont), 4)

    raw_route = {
        "rank": rank, "mode_key": mode_key, "mode_label": mode_label,
        "condition": condition, "utility_score": score,
        "duration_min": duration_min, "distance_km": distance_km,
        "transfers": transfers,
        "strategy": _safe(route, "strategy", None),
        "geometry": _safe(route, "geometry", None),
        "legs": [
            {
                "mode":         _safe(l, "mode"),
                "description":  _safe(l, "description"),
                "distance_m":   _safe(l, "distance_m"),
                "duration_s":   _safe(l, "duration_s"),
                "from_name":    _safe(l, "from_name"),
                "to_name":      _safe(l, "to_name"),
                "from_stop":    _safe(l, "from_stop"),
                "to_stop":      _safe(l, "to_stop"),
                "num_stops":    _safe(l, "num_stops"),
                "route_id":     _safe(l, "route_id"),
                "trip_headsign":_safe(l, "trip_headsign"),
                "geometry":     _safe(l, "geometry"),
            }
            for l in legs
        ],
    }

    return {
        "scenario_id":             scenario_id,
        "route_condition":         condition,
        "route_rank":              rank,
        "route_id":                f"S{scenario_id}_{condition[:4].upper()}_R{rank}_{mode_key}",
        "route_summary":           mode_label,
        "transport_modes":         ", ".join(str(m) for m in unique_modes if m),
        "is_intermodal":           1 if len(unique_modes) > 1 else 0,
        "intermodal_type":         "+".join(str(m) for m in unique_modes if m),
        "total_duration_minutes":  duration_min,
        "walking_minutes":         leg_minutes("walk"),
        "cycling_minutes":         leg_minutes("bike"),
        "pt_minutes":              leg_minutes("pt"),
        "driving_minutes":         leg_minutes("car"),
        "transfer_count":          transfers,
        "engine_total_score":      score,
        "raw_route_json":          json.dumps(raw_route),
        **dim_scores,
    }

# ─────────────────────────────────────────────
#  Route generation (one condition)
# ─────────────────────────────────────────────

DEPARTURE = datetime(2025, 11, 15, 9, 0, tzinfo=timezone.utc)

def _generate_routes(scenario: dict, agent: Agent, condition: str) -> list[dict]:
    gh = GraphHopperClient(base_url=os.getenv("GRAPHHOPPER_HOST", "http://localhost:8080"))
    router = PersonalisedRouter(gh, pois=None)
    results = router.route(
        agent=agent,
        from_lat=scenario["origin_lat"],
        from_lon=scenario["origin_lon"],
        to_lat=scenario["destination_lat"],
        to_lon=scenario["destination_lon"],
        departure=DEPARTURE.isoformat(),
        max_walk_m=1500,
    )
    return [convert_route(r, scenario["id"], condition) for r in results]


def generate_both_conditions(scenario_id: int, selected_profile: str) -> dict:
    """Return personalised and baseline route sets for one scenario."""
    with get_connection() as conn:
        scenario = conn.execute(
            "SELECT * FROM scenarios WHERE id = ?", (scenario_id,)
        ).fetchone()
    if not scenario:
        raise ValueError(f"Scenario not found: {scenario_id}")
    scenario = dict(scenario)

    personalised_agent  = load_agent(selected_profile)
    personalised_routes = _generate_routes(scenario, personalised_agent, "personalised")
    baseline_routes     = _generate_baseline_routes(scenario, personalised_agent)

    return {
        "personalised": personalised_routes,
        "baseline":     baseline_routes,
    }


def save_engine_routes(participant_id: int, selected_profile: str,
                       routes: list[dict]) -> None:
    """Upsert engine rankings for one participant/scenario/condition batch."""
    if not routes:
        return
    scenario_id = routes[0]["scenario_id"]
    condition   = routes[0]["route_condition"]

    with get_connection() as conn:
        conn.execute(
            """DELETE FROM engine_rankings
               WHERE participant_id=? AND scenario_id=? AND route_condition=?""",
            (participant_id, scenario_id, condition),
        )
        for r in routes:
            conn.execute(
                """
                INSERT INTO engine_rankings (
                    participant_id, selected_profile, scenario_id, route_condition,
                    route_rank, route_id, route_summary,
                    transport_modes, is_intermodal, intermodal_type,
                    total_duration_minutes, walking_minutes, cycling_minutes,
                    pt_minutes, driving_minutes, transfer_count,
                    score_pro_env, score_physical, score_privacy, score_autonomy,
                    score_cost, score_speed, score_safety_accident, score_safety_crime,
                    score_comfort, score_reliable, score_health_infection,
                    engine_total_score, raw_route_json
                ) VALUES (
                    ?,?,?,?, ?,?,?,
                    ?,?,?,
                    ?,?,?,?,?,?,
                    ?,?,?,?,
                    ?,?,?,?,
                    ?,?,?,
                    ?,?
                )
                """,
                (
                    participant_id, selected_profile, scenario_id, condition,
                    r["route_rank"], r["route_id"], r["route_summary"],
                    r["transport_modes"], r["is_intermodal"], r["intermodal_type"],
                    r["total_duration_minutes"], r["walking_minutes"], r["cycling_minutes"],
                    r["pt_minutes"], r["driving_minutes"], r["transfer_count"],
                    r.get("score_pro_env"),   r.get("score_physical"),
                    r.get("score_privacy"),   r.get("score_autonomy"),
                    r.get("score_cost"),      r.get("score_speed"),
                    r.get("score_safety_accident"), r.get("score_safety_crime"),
                    r.get("score_comfort"),   r.get("score_reliable"),
                    r.get("score_health_infection"),
                    r["engine_total_score"],  r["raw_route_json"],
                ),
            )
        conn.commit()

# ─────────────────────────────────────────────
#  Kendall tau helper (server-side)
# ─────────────────────────────────────────────

def kendall_tau(engine_order: list, participant_order: list) -> float:
    """
    Compute Kendall tau-b between two ranked orderings of route IDs.
    Returns a value in [-1, +1].  +1 = perfect agreement.
    """
    # Map route IDs to their participant-assigned ranks
    p_rank = {rid: i for i, rid in enumerate(participant_order)}
    e_rank = {rid: i for i, rid in enumerate(engine_order)}
    common = [rid for rid in engine_order if rid in p_rank]
    n = len(common)
    if n < 2:
        return 0.0
    concordant = discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            e_diff = e_rank[common[i]] - e_rank[common[j]]
            p_diff = p_rank[common[i]] - p_rank[common[j]]
            if e_diff * p_diff > 0:
                concordant += 1
            elif e_diff * p_diff < 0:
                discordant += 1
    denom = n * (n - 1) / 2
    return round((concordant - discordant) / denom, 4) if denom else 0.0

# ─────────────────────────────────────────────
#  Page routes
# ─────────────────────────────────────────────

@app.route("/")
def index():
    if "participant_id" not in session:
        create_participant()
    return render_template("study.html")


@app.route("/new-participant")
def new_participant():
    session.clear()
    create_participant()
    return redirect("/")


@app.route("/api/participant", methods=["GET"])
def get_participant():
    return jsonify({
        "participant_id":   session.get("participant_id"),
        "participant_code": session.get("participant_code"),
    })

# ─────────────────────────────────────────────
#  Demographics
# ─────────────────────────────────────────────

@app.route("/api/demographics", methods=["POST"])
def save_demographics():
    pid  = get_or_create_participant_id()
    data = request.json or {}
    with get_connection() as conn:
        conn.execute(
            """UPDATE participants SET
                age_group=?, gender=?, occupation=?, city_of_residence=?,
                mobility_frequency=?, has_driving_license=?,
                owns_car=?, owns_bike=?, uses_public_transport=?, cycling_comfort=?
               WHERE id=?""",
            (
                data.get("age_group"),          data.get("gender"),
                data.get("occupation"),         data.get("city_of_residence"),
                data.get("mobility_frequency"), data.get("has_driving_license"),
                data.get("owns_car"),           data.get("owns_bike"),
                data.get("uses_public_transport"), data.get("cycling_comfort"),
                pid,
            ),
        )
        conn.commit()
    return jsonify({"status": "success"})

# ─────────────────────────────────────────────
#  Profile selection
# ─────────────────────────────────────────────

@app.route("/api/profile", methods=["POST"])
def save_profile():
    pid  = get_or_create_participant_id()
    data = request.json or {}
    profile = data.get("selected_profile")
    if profile not in AGENT_FILES:
        return jsonify({"status": "error", "message": "Invalid profile."}), 400
    with get_connection() as conn:
        conn.execute(
            "UPDATE participants SET selected_profile=? WHERE id=?", (profile, pid)
        )
        conn.commit()
    return jsonify({"status": "success", "selected_profile": profile})

# ─────────────────────────────────────────────
#  Scenarios
# ─────────────────────────────────────────────

@app.route("/api/scenarios", methods=["GET"])
def get_scenarios():
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM scenarios ORDER BY id").fetchall()
    return jsonify([dict(r) for r in rows])

# ─────────────────────────────────────────────
#  Route ranking — both conditions
# ─────────────────────────────────────────────

@app.route("/api/scenario/<int:scenario_id>/ranking", methods=["GET"])
def get_ranking(scenario_id):
    pid     = get_or_create_participant_id()
    profile = get_selected_profile(pid)
    if not profile:
        return jsonify({"status": "error", "message": "No profile selected."}), 400

    try:
        both = generate_both_conditions(scenario_id, profile)
        save_engine_routes(pid, profile, both["personalised"])
        save_engine_routes(pid, profile, both["baseline"])
        return jsonify({
            "status":       "success",
            "scenario_id":  scenario_id,
            "profile":      profile,
            "personalised": both["personalised"],
            "baseline":     both["baseline"],
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ─────────────────────────────────────────────
#  Scenario response
# ─────────────────────────────────────────────

@app.route("/api/scenario-response", methods=["POST"])
def save_scenario_response():
    pid  = get_or_create_participant_id()
    data = request.json or {}

    scenario_id         = data["scenario_id"]
    engine_ranking      = data.get("engine_ranking", [])
    participant_ranking = data.get("participant_ranking", [])
    route_ratings       = data.get("route_ratings", [])
    intermodal_fb       = data.get("intermodal_feedback", {})

    engine_top          = engine_ranking[0] if engine_ranking else None
    participant_top     = data.get("participant_selected_route_id")
    accepted            = 1 if participant_top == engine_top else 0
    tau                 = kendall_tau(engine_ranking, participant_ranking)

    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO scenario_responses (
                participant_id, scenario_id,
                engine_top_route_id, participant_selected_route_id,
                accepted_engine_top_choice, ranking_acceptance_score,
                participant_ranking_json, engine_ranking_json,
                kendall_tau, explanation
            ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                pid, scenario_id,
                engine_top, participant_top,
                accepted, data.get("ranking_acceptance_score"),
                json.dumps(participant_ranking), json.dumps(engine_ranking),
                tau, data.get("explanation"),
            ),
        )
        sr_id = cur.lastrowid

        for rating in route_ratings:
            conn.execute(
                """INSERT INTO route_ratings (
                    scenario_response_id, route_condition, route_id,
                    participant_rating, would_use_route,
                    perceived_pro_env, perceived_physical, perceived_privacy,
                    perceived_autonomy, perceived_cost, perceived_speed,
                    perceived_safety_accident, perceived_safety_crime,
                    perceived_comfort, perceived_reliable, perceived_health_infection,
                    perceived_intermodal_quality, route_comment
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    sr_id,
                    rating.get("route_condition", rating.get("condition", "personalised")),
                    rating.get("route_id"),
                    rating.get("participant_rating"),
                    rating.get("would_use_route"),
                    rating.get("perceived_pro_env"),
                    rating.get("perceived_physical"),
                    rating.get("perceived_privacy"),
                    rating.get("perceived_autonomy"),
                    rating.get("perceived_cost"),
                    rating.get("perceived_speed"),
                    rating.get("perceived_safety_accident"),
                    rating.get("perceived_safety_crime"),
                    rating.get("perceived_comfort"),
                    rating.get("perceived_reliable"),
                    rating.get("perceived_health_infection"),
                    rating.get("perceived_intermodal_quality"),
                    rating.get("route_comment"),
                ),
            )

        conn.execute(
            """INSERT INTO intermodal_feedback (
                scenario_response_id,
                noticed_intermodal_option, understood_intermodal_logic,
                intermodal_acceptance_score, intermodal_preference, intermodal_comment
            ) VALUES (?,?,?,?,?,?)""",
            (
                sr_id,
                intermodal_fb.get("noticed_intermodal_option"),
                intermodal_fb.get("understood_intermodal_logic"),
                intermodal_fb.get("intermodal_acceptance_score"),
                intermodal_fb.get("intermodal_preference"),
                intermodal_fb.get("intermodal_comment"),
            ),
        )
        conn.commit()

    return jsonify({"status": "success", "scenario_response_id": sr_id, "kendall_tau": tau})

# ─────────────────────────────────────────────
#  Final feedback
# ─────────────────────────────────────────────

@app.route("/api/needs-importance", methods=["POST"])
def save_needs_importance():
    """Save participant's post-scenario needs importance ratings.
    Stored as a JSON blob on the participant record (needs_importance column).
    """
    pid  = get_or_create_participant_id()
    data = request.json or {}
    with get_connection() as conn:
        conn.execute(
            "UPDATE participants SET needs_importance=? WHERE id=?",
            (json.dumps(data), pid),
        )
        conn.commit()
    return jsonify({"status": "success"})


@app.route("/api/final-feedback", methods=["POST"])
def save_final_feedback():
    pid  = get_or_create_participant_id()
    data = request.json or {}
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO final_feedback (
                participant_id,
                value_profile_accuracy, profile_confidence,
                system_usefulness, trust_in_ranking,
                comparison_with_google_maps, willingness_to_use,
                noticed_personalisation, personalisation_quality,
                best_feature, worst_feature, improvement_suggestion
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                pid,
                data.get("value_profile_accuracy"),
                data.get("profile_confidence"),
                data.get("system_usefulness"),
                data.get("trust_in_ranking"),
                data.get("comparison_with_google_maps"),
                data.get("willingness_to_use"),
                data.get("noticed_personalisation"),
                data.get("personalisation_quality"),
                data.get("best_feature"),
                data.get("worst_feature"),
                data.get("improvement_suggestion"),
            ),
        )
        conn.commit()
    return jsonify({"status": "success"})

# ─────────────────────────────────────────────
#  Admin
# ─────────────────────────────────────────────

@app.route("/admin/responses", methods=["GET"])
def view_responses():
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT sr.id, p.participant_code, p.selected_profile,
                      s.scenario_code, s.title, s.distance_band,
                      sr.engine_top_route_id, sr.participant_selected_route_id,
                      sr.accepted_engine_top_choice, sr.ranking_acceptance_score,
                      sr.kendall_tau, sr.explanation, sr.created_at
               FROM scenario_responses sr
               JOIN participants p ON sr.participant_id = p.id
               JOIN scenarios s    ON sr.scenario_id   = s.id
               ORDER BY sr.created_at DESC"""
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/admin/dashboard")
def admin_dashboard():
    with get_connection() as conn:
        participants = conn.execute("SELECT * FROM participants").fetchall()
        responses    = conn.execute(
            """SELECT sr.id, sr.participant_id, p.participant_code,
                      p.selected_profile, s.scenario_code, s.title, s.distance_band,
                      sr.engine_top_route_id, sr.participant_selected_route_id,
                      sr.accepted_engine_top_choice, sr.ranking_acceptance_score,
                      sr.kendall_tau, sr.explanation, sr.created_at
               FROM scenario_responses sr
               JOIN participants p ON sr.participant_id = p.id
               JOIN scenarios s    ON sr.scenario_id   = s.id
               ORDER BY sr.participant_id, sr.created_at"""
        ).fetchall()
    return render_template("admin_dashboard.html",
                           participants=participants, responses=responses)


# ─────────────────────────────────────────────
#  Run
# ─────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("FLASK_RUN_PORT", 5000))
    app.run(debug=False, port=port, host="0.0.0.0")