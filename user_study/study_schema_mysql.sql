-- study_schema_mysql.sql
-- Simple Engine Phase 1 — MySQL 8.0+ schema (version 2)
-- Updated to match Modou_Survey_final.html data collection.
--
-- Changes from v1:
--   participants  : +education, +commute_*, +exclusion_*, +profile_rating_*,
--                   +profile_selection_confidence, mobility_frequency now TINYINT (Likert)
--   scenario_responses : +ranking_acceptance_score_b, +participant_selected_route_b,
--                        +follow_top_route_a
--   final_feedback     : +overall_intermodal_use
--
-- Usage:
--   mysql -u root -p -e "DROP DATABASE IF EXISTS simple_engine_study; \
--                         CREATE DATABASE simple_engine_study CHARACTER SET utf8mb4 \
--                         COLLATE utf8mb4_unicode_ci;"
--   mysql -u root -p simple_engine_study < study_schema_mysql.sql

SET FOREIGN_KEY_CHECKS = 0;
SET NAMES utf8mb4;

-- ─────────────────────────────────────────────
--  Schema version
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS schema_version (
    version      INT          PRIMARY KEY,
    description  VARCHAR(255),
    applied_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO schema_version (version, description)
VALUES (3, 'Phase 1 v3 — between-subjects study condition, set order counterbalancing');

-- ─────────────────────────────────────────────
--  Participants
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS participants (
    id                    INT           NOT NULL AUTO_INCREMENT PRIMARY KEY,
    participant_code      VARCHAR(64)   NOT NULL UNIQUE,
    created_at            TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    study_phase           INT           NOT NULL DEFAULT 1,
    selected_profile      VARCHAR(32)   NULL,   -- biospheric | altruistic | egoistic | hedonic

    -- ── Demographics (Part A) ─────────────────
    age_group             VARCHAR(16)   NULL,   -- raw age stored as string e.g. "34"
    gender                VARCHAR(64)   NULL,
    education             VARCHAR(32)   NULL,   -- no_formal|secondary|abitur|vocational|bachelor|master|phd
    occupation            VARCHAR(64)   NULL,

    -- Commute geography
    commute_different_city  VARCHAR(8)  NULL,   -- yes | no
    commute_city            VARCHAR(64) NULL,   -- halle_saale | berlin | other_city etc
    commute_district        VARCHAR(64) NULL,   -- altstadt | sudenburg etc (Magdeburg districts)

    -- Accessibility / exclusion criteria
    exclusion_disability_yesno  TINYINT NULL,   -- 0=no 1=yes 9=prefer not to say
    exclusion_disability_modes  JSON    NULL,   -- ["walking","cycling"] etc

    -- ── Mobility habits (Part B) ──────────────
    mobility_frequency    TINYINT       NULL,   -- 1-5 Likert (1=never, 5=daily)
    has_driving_license   TINYINT(1)    NULL,
    owns_car              TINYINT(1)    NULL,
    owns_bike             TINYINT(1)    NULL,
    uses_public_transport TINYINT(1)    NULL,
    cycling_comfort       TINYINT       NULL,   -- 1-5 Likert

    -- ── Profile selection ─────────────────────
    -- Per-card soft ratings: "How much does this profile describe you?" 1-5
    profile_rating_biospheric    TINYINT NULL,
    profile_rating_altruistic    TINYINT NULL,
    profile_rating_egoistic      TINYINT NULL,
    profile_rating_hedonic       TINYINT NULL,
    -- Overall confidence in the chosen profile
    profile_selection_confidence TINYINT NULL,  -- 1-5 Likert

    consent_given         TINYINT(1)    NOT NULL DEFAULT 0,

    -- Pre-study needs ratings (drive personalised routing)
    needs_importance_pre  JSON          NULL,
    -- Post-scenario needs ratings (validation / test-retest reliability)
    needs_importance      JSON          NULL,

    -- ── Post-study profile self-identification ──────
    post_study_profile               VARCHAR(32) NULL,
    post_profile_rating_biospheric   TINYINT     NULL,
    post_profile_rating_altruistic   TINYINT     NULL,
    post_profile_rating_egoistic     TINYINT     NULL,
    post_profile_rating_hedonic      TINYINT     NULL,
    post_profile_selection_confidence TINYINT    NULL,

    -- ── Study assignment (between-subjects) ──────
    -- study_condition: 1 = no intermodal, 2 = with intermodal
    -- set_order: 'AB' = value-ranked first, 'BA' = time-ranked first
    study_condition       TINYINT       NOT NULL DEFAULT 1,
    set_order             VARCHAR(2)    NOT NULL DEFAULT 'AB'

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ─────────────────────────────────────────────
--  Scenarios
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scenarios (
    id              INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    scenario_code   VARCHAR(16)  NOT NULL UNIQUE,
    title           VARCHAR(128) NOT NULL,
    origin          VARCHAR(255) NOT NULL,
    destination     VARCHAR(255) NOT NULL,
    origin_lat      DOUBLE       NULL,
    origin_lon      DOUBLE       NULL,
    destination_lat DOUBLE       NULL,
    destination_lon DOUBLE       NULL,
    distance_band   VARCHAR(16)  NULL,    -- short | medium | long
    context         TEXT         NOT NULL,
    purpose         VARCHAR(64)  NOT NULL,
    day_type        VARCHAR(64)  NULL,
    weather         VARCHAR(32)  NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ─────────────────────────────────────────────
--  Engine rankings
--  One row per route per condition per scenario per participant.
--  route_condition: 'personalised' (Set A) | 'baseline' (Set B)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS engine_rankings (
    id                     INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    participant_id         INT          NOT NULL,
    selected_profile       VARCHAR(32)  NULL,
    scenario_id            INT          NOT NULL,
    route_condition        VARCHAR(16)  NOT NULL DEFAULT 'personalised',

    route_rank             INT          NOT NULL,
    route_id               VARCHAR(128) NOT NULL,
    route_summary          VARCHAR(255) NULL,

    transport_modes        VARCHAR(128) NULL,
    is_intermodal          TINYINT(1)   NOT NULL DEFAULT 0,
    intermodal_type        VARCHAR(64)  NULL,

    total_duration_minutes DOUBLE       NULL,
    walking_minutes        DOUBLE       NULL,
    cycling_minutes        DOUBLE       NULL,
    pt_minutes             DOUBLE       NULL,
    driving_minutes        DOUBLE       NULL,
    transfer_count         INT          NULL,

    -- Engine scores per value dimension (personalised condition only; NULL for baseline)
    score_pro_env          DOUBLE       NULL,
    score_physical         DOUBLE       NULL,
    score_privacy          DOUBLE       NULL,
    score_autonomy         DOUBLE       NULL,
    score_cost             DOUBLE       NULL,
    score_speed            DOUBLE       NULL,
    score_safety_accident  DOUBLE       NULL,
    score_safety_crime     DOUBLE       NULL,
    score_comfort          DOUBLE       NULL,
    score_reliable         DOUBLE       NULL,
    score_health_infection DOUBLE       NULL,

    engine_total_score     DOUBLE       NULL,
    raw_route_json         JSON         NULL,

    -- Which study condition was this participant in when this route was shown
    study_condition        TINYINT      NULL,
    intermodal_available   TINYINT(1)   NOT NULL DEFAULT 0,

    FOREIGN KEY (participant_id) REFERENCES participants(id),
    FOREIGN KEY (scenario_id)   REFERENCES scenarios(id),
    INDEX idx_er_participant (participant_id),
    INDEX idx_er_scenario    (scenario_id),
    INDEX idx_er_condition   (route_condition)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ─────────────────────────────────────────────
--  Scenario responses
--  One row per participant per scenario.
--  Stores both Set A and Set B responses together so
--  the A-vs-B comparison is a single-row operation.
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scenario_responses (
    id                              INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    participant_id                  INT          NOT NULL,
    scenario_id                     INT          NOT NULL,

    -- ── Set A (personalised) ──────────────────
    engine_top_route_id             VARCHAR(128) NULL,   -- top-ranked route from engine
    participant_selected_route_id   VARCHAR(128) NULL,   -- which route participant chose from Set A
    accepted_engine_top_choice      TINYINT(1)   NULL,   -- 1 if chosen == engine top
    follow_top_route_a              VARCHAR(8)   NULL,   -- yes | maybe | no
    ranking_acceptance_score        TINYINT      NULL,   -- 1-5: how well Set A ranking matched preference

    -- ── Set B (baseline) ─────────────────────
    participant_selected_route_b    VARCHAR(128) NULL,   -- which route participant chose from Set B
    ranking_acceptance_score_b      TINYINT      NULL,   -- 1-5: how well Set B ranking matched preference

    -- ── Ranking comparison ────────────────────
    -- Computed server-side: acceptance_A - acceptance_B
    -- Positive = engine better than baseline for this participant/scenario
    ranking_acceptance_delta        TINYINT      NULL,

    -- Participant's re-ordering of Set A routes (JSON array of route_ids)
    participant_ranking_json        JSON         NULL,
    engine_ranking_json             JSON         NULL,

    -- Kendall tau between engine ranking and participant chosen route preference
    -- Computed server-side and stored for fast analysis
    kendall_tau                     DOUBLE       NULL,
    kendall_tau_engine_participant   DOUBLE       NULL,
    kendall_tau_time_participant     DOUBLE       NULL,
    participant_ranking_b_json       JSON         NULL,

    explanation                     TEXT         NULL,
    created_at                      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Denormalised for easy analysis queries — mirrors participants.study_condition
    study_condition                 TINYINT      NULL,
    set_order                       VARCHAR(2)   NULL,

    FOREIGN KEY (participant_id) REFERENCES participants(id),
    FOREIGN KEY (scenario_id)   REFERENCES scenarios(id),
    INDEX idx_sr_participant (participant_id),
    INDEX idx_sr_scenario    (scenario_id),
    INDEX idx_sr_condition   (study_condition)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ─────────────────────────────────────────────
--  Route ratings
--  One row per route shown (both conditions).
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS route_ratings (
    id                           INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    scenario_response_id         INT          NOT NULL,
    route_condition              VARCHAR(16)  NOT NULL,   -- personalised | baseline
    route_id                     VARCHAR(128) NOT NULL,

    participant_rating           TINYINT      NULL,   -- overall satisfaction 1-5
    would_use_route              TINYINT(1)   NULL,

    perceived_pro_env            TINYINT      NULL,
    perceived_physical           TINYINT      NULL,
    perceived_privacy            TINYINT      NULL,
    perceived_autonomy           TINYINT      NULL,
    perceived_cost               TINYINT      NULL,
    perceived_speed              TINYINT      NULL,
    perceived_safety_accident    TINYINT      NULL,
    perceived_safety_crime       TINYINT      NULL,
    perceived_comfort            TINYINT      NULL,
    perceived_reliable           TINYINT      NULL,
    perceived_health_infection   TINYINT      NULL,
    perceived_intermodal_quality TINYINT      NULL,

    route_comment                TEXT         NULL,

    FOREIGN KEY (scenario_response_id) REFERENCES scenario_responses(id),
    INDEX idx_rr_response (scenario_response_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ─────────────────────────────────────────────
--  Intermodal feedback (per scenario)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS intermodal_feedback (
    id                          INT         NOT NULL AUTO_INCREMENT PRIMARY KEY,
    scenario_response_id        INT         NOT NULL,

    noticed_intermodal_option   TINYINT     NULL,   -- 0=no 1=yes 2=not sure
    understood_intermodal_logic TINYINT     NULL,   -- 1-5 Likert
    intermodal_acceptance_score TINYINT     NULL,   -- 1-5 Likert
    intermodal_preference       VARCHAR(16) NULL,   -- prefer | neutral | avoid
    intermodal_comment          TEXT        NULL,

    FOREIGN KEY (scenario_response_id) REFERENCES scenario_responses(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ─────────────────────────────────────────────
--  Final feedback (one row per participant)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS final_feedback (
    id                          INT        NOT NULL AUTO_INCREMENT PRIMARY KEY,
    participant_id              INT        NOT NULL,

    -- Profile validity
    value_profile_accuracy      TINYINT    NULL,   -- 1-5: profile represented my values
    profile_confidence          TINYINT    NULL,   -- 1-5: confident choosing profile

    -- System evaluation
    personalisation_quality     TINYINT    NULL,   -- 1-5: Set A matched my values well
    willingness_to_use          TINYINT    NULL,   -- 1-5: would use in daily life
    trust_in_ranking            TINYINT    NULL,   -- 1-5: trust the route rankings
    overall_intermodal_use      TINYINT    NULL,   -- 1-5: would consider intermodal routes overall
    comparison_with_google_maps TINYINT    NULL,   -- 1-5: much worse → much better vs standard nav
    noticed_personalisation     TINYINT(1) NULL,   -- 0/1: noticed routes adapted to profile

    -- Open text
    best_feature                TEXT       NULL,
    worst_feature               TEXT       NULL,
    improvement_suggestion      TEXT       NULL,

    created_at                  TIMESTAMP  NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (participant_id) REFERENCES participants(id),
    INDEX idx_ff_participant (participant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET FOREIGN_KEY_CHECKS = 1;