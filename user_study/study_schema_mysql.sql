-- study_schema_mysql.sql
-- Simple Engine Phase 1 — MySQL 8.0+ schema
-- Converted from SQLite. Run once to initialise the database.
--
-- Usage:
--   mysql -u <user> -p simple_engine_study < study_schema_mysql.sql
--
-- Or from within MySQL:
--   CREATE DATABASE IF NOT EXISTS simple_engine_study CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
--   USE simple_engine_study;
--   SOURCE study_schema_mysql.sql;

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
VALUES (1, 'Phase 1 — value model baseline study');

-- ─────────────────────────────────────────────
--  Participants
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS participants (
    id                    INT           NOT NULL AUTO_INCREMENT PRIMARY KEY,
    participant_code      VARCHAR(64)   NOT NULL UNIQUE,
    created_at            TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    study_phase           INT           NOT NULL DEFAULT 1,
    selected_profile      VARCHAR(32)   NULL,       -- biospheric | altruistic | egoistic | hedonic

    -- Demographics
    age_group             VARCHAR(16)   NULL,
    gender                VARCHAR(64)   NULL,
    occupation            VARCHAR(64)   NULL,
    city_of_residence     VARCHAR(128)  NULL,

    -- Mobility background
    mobility_frequency    VARCHAR(32)   NULL,       -- daily | several_week | weekly | rarely
    has_driving_license   TINYINT(1)    NULL,
    owns_car              TINYINT(1)    NULL,
    owns_bike             TINYINT(1)    NULL,
    uses_public_transport TINYINT(1)    NULL,
    cycling_comfort       TINYINT       NULL,       -- 1-5

    consent_given         TINYINT(1)    NOT NULL DEFAULT 0,
    needs_importance      JSON          NULL        -- post-scenario needs ratings
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
    distance_band   VARCHAR(16)  NULL,              -- short | medium | long
    context         TEXT         NOT NULL,
    purpose         VARCHAR(64)  NOT NULL,
    day_type        VARCHAR(64)  NULL,
    weather         VARCHAR(32)  NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ─────────────────────────────────────────────
--  Engine rankings
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

    -- Engine scores per value dimension
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

    FOREIGN KEY (participant_id) REFERENCES participants(id),
    FOREIGN KEY (scenario_id)   REFERENCES scenarios(id),
    INDEX idx_er_participant (participant_id),
    INDEX idx_er_scenario    (scenario_id),
    INDEX idx_er_condition   (route_condition)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ─────────────────────────────────────────────
--  Scenario responses
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scenario_responses (
    id                              INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    participant_id                  INT          NOT NULL,
    scenario_id                     INT          NOT NULL,

    engine_top_route_id             VARCHAR(128) NULL,
    participant_selected_route_id   VARCHAR(128) NULL,
    accepted_engine_top_choice      TINYINT(1)   NULL,
    ranking_acceptance_score        INT          NULL,

    participant_ranking_json        JSON         NULL,
    engine_ranking_json             JSON         NULL,
    kendall_tau                     DOUBLE       NULL,

    explanation                     TEXT         NULL,
    created_at                      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (participant_id) REFERENCES participants(id),
    FOREIGN KEY (scenario_id)   REFERENCES scenarios(id),
    INDEX idx_sr_participant (participant_id),
    INDEX idx_sr_scenario    (scenario_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ─────────────────────────────────────────────
--  Route ratings
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS route_ratings (
    id                           INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    scenario_response_id         INT          NOT NULL,
    route_condition              VARCHAR(16)  NOT NULL,
    route_id                     VARCHAR(128) NOT NULL,

    participant_rating           TINYINT      NULL,
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
--  Intermodal feedback
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS intermodal_feedback (
    id                          INT         NOT NULL AUTO_INCREMENT PRIMARY KEY,
    scenario_response_id        INT         NOT NULL,

    noticed_intermodal_option   TINYINT(1)  NULL,
    understood_intermodal_logic TINYINT     NULL,
    intermodal_acceptance_score TINYINT     NULL,
    intermodal_preference       VARCHAR(16) NULL,   -- prefer | neutral | avoid
    intermodal_comment          TEXT        NULL,

    FOREIGN KEY (scenario_response_id) REFERENCES scenario_responses(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ─────────────────────────────────────────────
--  Final feedback
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS final_feedback (
    id                          INT        NOT NULL AUTO_INCREMENT PRIMARY KEY,
    participant_id              INT        NOT NULL,

    value_profile_accuracy      TINYINT    NULL,
    profile_confidence          TINYINT    NULL,
    system_usefulness           TINYINT    NULL,
    trust_in_ranking            TINYINT    NULL,
    comparison_with_google_maps TINYINT    NULL,
    willingness_to_use          TINYINT    NULL,
    noticed_personalisation     TINYINT(1) NULL,
    personalisation_quality     TINYINT    NULL,

    best_feature                TEXT       NULL,
    worst_feature               TEXT       NULL,
    improvement_suggestion      TEXT       NULL,

    created_at                  TIMESTAMP  NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (participant_id) REFERENCES participants(id),
    INDEX idx_ff_participant (participant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET FOREIGN_KEY_CHECKS = 1;