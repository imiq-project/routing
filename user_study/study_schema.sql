-- study_schema.sql
-- Simple Engine Phase 1 — Value-Based Routing Study
-- Phase 1 tests the 11-dimension value model against a GraphHopper baseline.
-- Schema is versioned (schema_version table) so future phases can migrate cleanly.

PRAGMA foreign_keys = ON;

-- ─────────────────────────────────────────────
--  Schema version (for future migrations)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    description TEXT,
    applied_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT OR IGNORE INTO schema_version (version, description) VALUES (1, 'Phase 1 — value model baseline study');

-- ─────────────────────────────────────────────
--  Participants
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS participants (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_code      TEXT UNIQUE NOT NULL,
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Study phase (allows reuse of schema across phases)
    study_phase           INTEGER NOT NULL DEFAULT 1,

    -- Profile selection (archetype chosen by participant)
    selected_profile      TEXT,               -- biospheric | altruistic | egoistic | hedonic

    -- Demographics
    age_group             TEXT,               -- e.g. '18-24', '25-34', ...
    gender                TEXT,
    occupation            TEXT,
    city_of_residence     TEXT,

    -- Mobility background
    mobility_frequency    TEXT,               -- daily | several_week | weekly | rarely
    has_driving_license   INTEGER,            -- 0/1
    owns_car              INTEGER,            -- 0/1
    owns_bike             INTEGER,            -- 0/1
    uses_public_transport INTEGER,            -- 0/1
    cycling_comfort       INTEGER,            -- 1-5: how comfortable cycling in traffic

    consent_given         INTEGER NOT NULL DEFAULT 0,

    -- Post-scenario needs importance ratings (JSON, collected once after all scenarios)
    needs_importance      TEXT
);

-- ─────────────────────────────────────────────
--  Scenarios (travel tasks)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scenarios (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_code   TEXT UNIQUE NOT NULL,
    title           TEXT NOT NULL,
    origin          TEXT NOT NULL,
    destination     TEXT NOT NULL,
    origin_lat      REAL,
    origin_lon      REAL,
    destination_lat REAL,
    destination_lon REAL,
    distance_band   TEXT,   -- short | medium | long  (for stratified analysis)
    context         TEXT NOT NULL,
    purpose         TEXT NOT NULL,
    day_type        TEXT,
    weather         TEXT
);

-- ─────────────────────────────────────────────
--  Engine rankings (one row per route per condition per participant)
--  condition: 'personalised' = value model active
--             'baseline'     = GraphHopper fastest (uniform weights)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS engine_rankings (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id         INTEGER NOT NULL,
    selected_profile       TEXT,
    scenario_id            INTEGER NOT NULL,
    condition              TEXT NOT NULL DEFAULT 'personalised', -- personalised | baseline

    route_rank             INTEGER NOT NULL,
    route_id               TEXT NOT NULL,
    route_summary          TEXT,

    transport_modes        TEXT,      -- e.g. "walk,tram,bike"
    is_intermodal          INTEGER DEFAULT 0,
    intermodal_type        TEXT,      -- e.g. "bike+pt"

    total_duration_minutes REAL,
    walking_minutes        REAL,
    cycling_minutes        REAL,
    pt_minutes             REAL,
    driving_minutes        REAL,
    transfer_count         INTEGER,

    -- Engine scores: one column per value dimension (aligns with VALUE_DIMENSIONS)
    score_pro_env          REAL,
    score_physical         REAL,
    score_privacy          REAL,
    score_autonomy         REAL,
    score_cost             REAL,
    score_speed            REAL,
    score_safety_accident  REAL,
    score_safety_crime     REAL,
    score_comfort          REAL,
    score_reliable         REAL,
    score_health_infection REAL,

    engine_total_score     REAL,
    raw_route_json         TEXT,      -- full route object for reanalysis

    FOREIGN KEY (participant_id) REFERENCES participants(id),
    FOREIGN KEY (scenario_id)   REFERENCES scenarios(id)
);

-- ─────────────────────────────────────────────
--  Scenario responses (one per participant per scenario)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scenario_responses (
    id                              INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id                  INTEGER NOT NULL,
    scenario_id                     INTEGER NOT NULL,

    -- Which route did the engine top-rank (personalised condition)?
    engine_top_route_id             TEXT,
    -- Which route did the participant ultimately choose?
    participant_selected_route_id   TEXT,
    -- Did participant pick the engine's top recommendation?
    accepted_engine_top_choice      INTEGER,  -- 0/1

    -- Overall ranking acceptance (1–5 Likert)
    ranking_acceptance_score        INTEGER,

    -- Participant's re-ordering of the personalised routes (JSON array of route_ids)
    participant_ranking_json        TEXT,
    -- Engine's original ranking (JSON array of route_ids)
    engine_ranking_json             TEXT,

    -- Kendall tau between engine ranking and participant ranking (-1 to +1)
    -- Computed server-side and stored for fast analysis
    kendall_tau                     REAL,

    -- Open text
    explanation                     TEXT,
    created_at                      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (participant_id) REFERENCES participants(id),
    FOREIGN KEY (scenario_id)   REFERENCES scenarios(id)
);

-- ─────────────────────────────────────────────
--  Route ratings  (one row per route shown to participant)
--  Perceived dimensions mapped 1:1 to VALUE_DIMENSIONS.
--  All perceived_* items: 1–5 Likert (1=strongly disagree, 5=strongly agree)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS route_ratings (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_response_id        INTEGER NOT NULL,
    condition                   TEXT NOT NULL,  -- personalised | baseline
    route_id                    TEXT NOT NULL,

    -- Overall
    participant_rating          INTEGER,  -- 1–5 star satisfaction
    would_use_route             INTEGER,  -- 0/1

    -- Per-dimension perceived scores (1–5, matching VALUE_DIMENSIONS order)
    -- These are used to compute Spearman ρ(engine_score_dim, perceived_dim)
    perceived_pro_env           INTEGER,
    perceived_physical          INTEGER,
    perceived_privacy           INTEGER,
    perceived_autonomy          INTEGER,
    perceived_cost              INTEGER,
    perceived_speed             INTEGER,
    perceived_safety_accident   INTEGER,
    perceived_safety_crime      INTEGER,
    perceived_comfort           INTEGER,
    perceived_reliable          INTEGER,
    perceived_health_infection  INTEGER,

    -- Intermodal-specific
    perceived_intermodal_quality INTEGER,  -- 1–5, only for intermodal routes

    route_comment               TEXT,

    FOREIGN KEY (scenario_response_id) REFERENCES scenario_responses(id)
);

-- ─────────────────────────────────────────────
--  Intermodal feedback (per scenario, not per route)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS intermodal_feedback (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_response_id        INTEGER NOT NULL,

    noticed_intermodal_option   INTEGER,   -- 0/1: did participant notice it?
    understood_intermodal_logic INTEGER,   -- 1–5
    intermodal_acceptance_score INTEGER,   -- 1–5
    intermodal_preference       TEXT,      -- prefer | neutral | avoid
    intermodal_comment          TEXT,

    FOREIGN KEY (scenario_response_id) REFERENCES scenario_responses(id)
);

-- ─────────────────────────────────────────────
--  Final feedback (one per participant)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS final_feedback (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id              INTEGER NOT NULL,

    -- Profile validity check
    value_profile_accuracy      INTEGER,   -- 1–5: "The selected profile accurately represents my values"
    profile_confidence          INTEGER,   -- 1–5: "I was confident choosing my profile"

    -- System evaluation
    system_usefulness           INTEGER,   -- 1–5 TAM
    trust_in_ranking            INTEGER,   -- 1–5
    comparison_with_google_maps INTEGER,   -- 1–5: much worse → much better
    willingness_to_use          INTEGER,   -- 1–5

    -- Phase 1 specific: did personalisation make a difference?
    noticed_personalisation     INTEGER,   -- 0/1: "I noticed the routes were adapted to my values"
    personalisation_quality     INTEGER,   -- 1–5: "The personalised routes matched my values well"

    -- Open text
    best_feature                TEXT,
    worst_feature               TEXT,
    improvement_suggestion      TEXT,

    created_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (participant_id) REFERENCES participants(id)
);