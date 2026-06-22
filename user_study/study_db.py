# study_db.py
# Simple Engine Phase 1 — database helpers and scenario seed data.
#
# Scenarios designed for MODAL TENSION — trips where value-based (Set A)
# and fastest-route (Set B) rankings meaningfully diverge across profiles.
#
# Design rule: crow-flies 4–9 km so bike, car, and PT are all viable
# with non-trivial time differences. Value weights then tip the ranking.
#
#   T1 — medium commute (Westerhüsen → OVGU, 6.7 km) — strong car/bike tension
#   S2 — medium leisure (Stadtfeld → Elbauenpark, 4.4 km) — bike/car near-tie
#   S3 — medium shopping (Klinikum Reform → City Center, 4.1 km) — bike/car near-tie
#   S6 — long cross-district (City Center → Schönebeck, 14.2 km) — PT/car tension

import sqlite3
from pathlib import Path

BASE_DIR    = Path(__file__).resolve().parent
DB_PATH     = BASE_DIR / "study_data.db"
SCHEMA_PATH = BASE_DIR / "study_schema.sql"


# ─────────────────────────────────────────────
#  Scenario seed data (4 scenarios, Phase 1)
# ─────────────────────────────────────────────

SCENARIOS = [
    {
        # 6.7 km crow-flies. Car ~29 min (incl. parking). Bike ~27 min. PT ~28 min.
        # Strong modal tension: car saves ~6 min over bike — tempting for egoistic/
        # hedonic, but biospheric/altruistic value the active/green option.
        # Expected: Set A tops bike for biospheric, car for egoistic. Set B tops car.
        "scenario_code":       "T1",
        "title":               "Westerhüsen to OVGU",
        "origin":              "Westerhüsen district",
        "destination":         "OVGU Campus",
        "origin_coords":       [52.0821, 11.6197],
        "destination_coords":  [52.1407, 11.6437],
        "distance_band":       "medium",
        "context":             (
            "It is a weekday morning. You are travelling from Westerhüsen "
            "to the OVGU campus for work or study. You have about 40 minutes "
            "before your first appointment. Parking near OVGU can be limited. "
            "Bike lanes connect the southern districts to campus."
        ),
        "purpose":   "work_study",
        "day_type":  "weekday_morning",
        "weather":   "cool_sunny",
    },
    {
        # 4.4 km crow-flies. Car ~25 min (incl. parking). Bike ~17 min. PT ~21 min.
        # Near-tie: bike is actually faster than car here. Value weights decide
        # whether comfort/autonomy (car) or pro-env/physical (bike) tips ranking.
        # Expected: all profiles prefer bike in Set A except hedonic (car comfort).
        "scenario_code":       "S2",
        "title":               "Stadtfeld to Elbauenpark",
        "origin":              "Home in Stadtfeld",
        "destination":         "Elbauenpark",
        "origin_coords":       [52.1276, 11.6046],
        "destination_coords":  [52.1381, 11.6661],
        "distance_band":       "medium",
        "context":             (
            "It is a sunny weekday afternoon and you have free time. "
            "You want to get from your home in Stadtfeld to Elbauenpark "
            "for a relaxed outing. There is no time pressure. "
            "The Elbe cycle path passes nearby."
        ),
        "purpose":   "leisure",
        "day_type":  "weekday_afternoon",
        "weather":   "sunny",
    },
    {
        # 4.1 km crow-flies. Car ~24 min (incl. parking). Bike ~16 min. PT ~20 min.
        # Bike is faster than car due to parking overhead.
        # Saturday context activates comfort dimension (carrying shopping bags).
        # Hedonic/egoistic may still prefer car despite slower door-to-door time.
        "scenario_code":       "S3",
        "title":               "Klinikum Reform to City Center",
        "origin":              "Klinikum Reform",
        "destination":         "Magdeburg City Center",
        "origin_coords":       [52.1012, 11.6053],
        "destination_coords":  [52.1317, 11.6392],
        "distance_band":       "medium",
        "context":             (
            "It is Saturday morning. You are heading from Klinikum Reform "
            "to the city centre for shopping. You may be carrying bags on the return trip. "
            "Parking in the city centre is expensive and limited on weekends."
        ),
        "purpose":   "shopping",
        "day_type":  "saturday_morning",
        "weather":   "normal",
    },
    {
        # 14.2 km crow-flies. Car ~44 min (incl. parking). PT ~51 min. Bike ~57 min.
        # Long trip: bike is at its feasibility limit. PT vs car is the main contest.
        # Altruistic values PT reliability. Egoistic/hedonic prefer car speed/comfort.
        # Pro-env biospheric may accept slower PT over car emissions.
        "scenario_code":       "S6",
        "title":               "City Center to Schönebeck",
        "origin":              "Magdeburg City Center",
        "destination":         "Schönebeck (Elbe)",
        "origin_coords":       [52.1317, 11.6392],
        "destination_coords":  [52.0207, 11.7422],
        "distance_band":       "long",
        "context":             (
            "It is Sunday afternoon. You are travelling from Magdeburg city centre "
            "to Schönebeck to visit family. The trip crosses district boundaries. "
            "A regional train connects the two cities. "
            "Driving is faster but requires navigating Sunday traffic."
        ),
        "purpose":   "family_visit",
        "day_type":  "sunday_afternoon",
        "weather":   "normal",
    },
]

# ─────────────────────────────────────────────
#  Connection
# ─────────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


# ─────────────────────────────────────────────
#  Init / seed
# ─────────────────────────────────────────────

def init_database() -> None:
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(
            f"Schema file not found: {SCHEMA_PATH}"
        )
    with get_connection() as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()
    print(f"Database initialised: {DB_PATH}")


def seed_scenarios() -> None:
    with get_connection() as conn:
        for s in SCENARIOS:
            conn.execute(
                """
                INSERT OR IGNORE INTO scenarios (
                    scenario_code, title, origin, destination,
                    origin_lat, origin_lon, destination_lat, destination_lon,
                    distance_band, context, purpose, day_type, weather
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    s["scenario_code"], s["title"],
                    s["origin"],        s["destination"],
                    s["origin_coords"][0],       s["origin_coords"][1],
                    s["destination_coords"][0],  s["destination_coords"][1],
                    s["distance_band"],
                    s["context"], s["purpose"], s["day_type"], s["weather"],
                ),
            )
        conn.commit()
    print(f"Seeded {len(SCENARIOS)} scenarios.")


def reset_database() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f"Deleted: {DB_PATH}")
    init_database()
    seed_scenarios()


def show_scenarios() -> None:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, scenario_code, title, origin, destination, distance_band, context "
            "FROM scenarios ORDER BY id"
        ).fetchall()
    for row in rows:
        print(f"  {row['id']}. [{row['scenario_code']}] {row['title']}  "
              f"({row['distance_band']})  {row['origin']} → {row['destination']}")
        print(f"     {row['context'][:80]}...")


if __name__ == "__main__":
    reset_database()
    show_scenarios()