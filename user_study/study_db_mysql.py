import os
import mysql.connector
from mysql.connector import pooling
from pathlib import Path

BASE_DIR    = Path(__file__).resolve().parent
SCHEMA_PATH = BASE_DIR / "study_schema_mysql.sql"

# ─────────────────────────────────────────────
#  Connection config (from environment)
# ─────────────────────────────────────────────

DB_CONFIG = {
    "host":             os.getenv("MYSQL_HOST",     "localhost"),
    "port":             int(os.getenv("MYSQL_PORT", "3306")),
    "user":             os.getenv("MYSQL_USER",     "root"),
    "password":         os.getenv("MYSQL_PASSWORD", ""),
    "database":         os.getenv("MYSQL_DATABASE", "simple_engine_study"),
    "charset":          "utf8mb4",
    "collation":        "utf8mb4_unicode_ci",
    "use_unicode":      True,
    "autocommit":       False,
    "connection_timeout": 30,
}

# Connection pool — shared across requests (size 5 is fine for study load)
_pool = None

def _get_pool():
    global _pool
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(
            pool_name="study_pool",
            pool_size=5,
            **DB_CONFIG,
        )
    return _pool


# ─────────────────────────────────────────────
#  Public connection helper
#  Drop-in replacement for the SQLite version:
#    with get_connection() as conn:
#        conn.execute(...)  ← uses cursor internally
#        conn.commit()
# ─────────────────────────────────────────────

class _MySQLConnectionWrapper:
    """
    Wraps a mysql.connector connection to expose the same
    .execute() / .fetchone() / .fetchall() / .commit() API
    that the SQLite version used, so study_app.py needs
    minimal changes.

    Key differences from sqlite3:
      - Placeholders are %s not ?  (handled by wrapper)
      - row_factory → returns dict-like rows automatically
      - lastrowid available via cursor after execute()
    """

    def __init__(self, conn):
        self._conn   = conn
        self._cursor = conn.cursor(dictionary=True)
        self.lastrowid = None

    def execute(self, sql: str, params=None):
        # Convert SQLite ? placeholders to MySQL %s
        sql = sql.replace("?", "%s")
        self._cursor.execute(sql, params or ())
        self.lastrowid = self._cursor.lastrowid
        return self

    def executemany(self, sql: str, param_list):
        sql = sql.replace("?", "%s")
        self._cursor.executemany(sql, param_list)
        return self

    def fetchone(self):
        return self._cursor.fetchone()   # dict or None

    def fetchall(self):
        return self._cursor.fetchall()   # list of dicts

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._cursor.close()
        self._conn.close()

    # Context manager support: with get_connection() as conn:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()
        return False


def get_connection() -> _MySQLConnectionWrapper:
    raw = _get_pool().get_connection()
    return _MySQLConnectionWrapper(raw)


# ─────────────────────────────────────────────
#  Scenario seed data (4 scenarios, Phase 1)
# ─────────────────────────────────────────────

SCENARIOS = [
    {
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
            "before your first appointment. Parking near OVGU can be limited."
        ),
        "purpose":   "work_study",
        "day_type":  "weekday_morning",
        "weather":   "cool_sunny",
    },
    {
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
            "for a relaxed outing. There is no time pressure."
        ),
        "purpose":   "leisure",
        "day_type":  "weekday_afternoon",
        "weather":   "sunny",
    },
    {
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
            "Public transport connections are available between the two cities. "
            "Driving is also an option but requires navigating Sunday traffic."
        ),
        "purpose":   "family_visit",
        "day_type":  "sunday_afternoon",
        "weather":   "normal",
    },
]


# ─────────────────────────────────────────────
#  Init / seed
# ─────────────────────────────────────────────

def create_database_if_not_exists() -> None:
    """Create the MySQL database if it doesn't already exist."""
    cfg = {k: v for k, v in DB_CONFIG.items() if k != "database"}
    conn = mysql.connector.connect(**cfg)
    cur  = conn.cursor()
    db   = DB_CONFIG["database"]
    cur.execute(
        f"CREATE DATABASE IF NOT EXISTS `{db}` "
        f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
    conn.commit()
    cur.close()
    conn.close()
    print(f"Database '{db}' ready.")


def init_database() -> None:
    """
    Apply the MySQL schema file statement by statement.
    Skips comment lines before splitting, so semicolons inside
    comments never corrupt the statement stream.
    Idempotent: ignores table-exists, duplicate-column, duplicate-entry errors.
    """
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Schema file not found: {SCHEMA_PATH}")

    raw = SCHEMA_PATH.read_text(encoding="utf-8")
    cfg = dict(DB_CONFIG)
    conn = mysql.connector.connect(**cfg)
    cur  = conn.cursor()

    buf = []
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("--"):
            continue          # drop comments and blanks
        buf.append(s)
        if s.endswith(";"):   # end of statement
            stmt = " ".join(buf)[:-1].strip()   # strip trailing ;
            buf = []
            if not stmt:
                continue
            try:
                cur.execute(stmt)
                # consume any unread result sets (e.g. SET statements)
                try:
                    cur.fetchall()
                except Exception:
                    pass
            except mysql.connector.Error as e:
                if e.errno not in (1050, 1060, 1062):
                    raise

    conn.commit()

    # Verify at least one key table was created
    cur.execute("SHOW TABLES LIKE 'participants'")
    if not cur.fetchone():
        cur.close()
        conn.close()
        raise RuntimeError(
            "Schema application failed — 'participants' table not found. "
            "Apply schema manually: Get-Content study_schema_mysql.sql | "
            "docker exec -i simple-engine-mysql mysql -uroot -p<pwd> simple_engine_study"
        )

    cur.close()
    conn.close()
    print("Schema applied.")


def seed_scenarios() -> None:
    with get_connection() as conn:
        for s in SCENARIOS:
            conn.execute(
                """INSERT IGNORE INTO scenarios (
                    scenario_code, title, origin, destination,
                    origin_lat, origin_lon, destination_lat, destination_lon,
                    distance_band, context, purpose, day_type, weather
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    s["scenario_code"], s["title"],
                    s["origin"],        s["destination"],
                    s["origin_coords"][0],       s["origin_coords"][1],
                    s["destination_coords"][0],  s["destination_coords"][1],
                    s["distance_band"],
                    s["context"], s["purpose"], s["day_type"], s["weather"],
                ),
            )
    print(f"Seeded {len(SCENARIOS)} scenarios.")


def reset_database() -> None:
    create_database_if_not_exists()
    init_database()
    seed_scenarios()


def show_scenarios() -> None:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, scenario_code, title, origin, destination, distance_band "
            "FROM scenarios ORDER BY id"
        ).fetchall()
    for row in rows:
        print(f"  {row['id']}. [{row['scenario_code']}] {row['title']}  "
              f"({row['distance_band']})  {row['origin']} → {row['destination']}")


if __name__ == "__main__":
    reset_database()
    show_scenarios()