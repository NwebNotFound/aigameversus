-- Player profiles and their Elo rating per game (D-031).
CREATE TABLE player_profiles (
    id             uuid        PRIMARY KEY,
    name           text        NOT NULL,
    model_id       text        NOT NULL,            -- id from config/models.yaml
    personality_id text,                            -- id from config/personalities/, or none
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ratings (
    profile_id   uuid             NOT NULL REFERENCES player_profiles (id) ON DELETE CASCADE,
    game_id      text             NOT NULL,
    rating       double precision NOT NULL DEFAULT 1000,
    games_played integer          NOT NULL DEFAULT 0 CHECK (games_played >= 0),
    updated_at   timestamptz      NOT NULL DEFAULT now(),
    PRIMARY KEY (profile_id, game_id)
);

-- One row per match whose result has been applied, so it is never counted twice.
CREATE TABLE rated_matches (
    match_id uuid        PRIMARY KEY,
    game_id  text        NOT NULL,
    rated_at timestamptz NOT NULL DEFAULT now()
);
