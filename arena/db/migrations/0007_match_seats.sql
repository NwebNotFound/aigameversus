-- Which profile played which seat of a rated match. A seat is the player id in the
-- match's event log, so the statistics of a profile can be read from the logs.
CREATE TABLE match_seats (
    match_id   uuid NOT NULL REFERENCES rated_matches (match_id) ON DELETE CASCADE,
    seat       text NOT NULL,
    profile_id uuid NOT NULL REFERENCES player_profiles (id) ON DELETE CASCADE,
    PRIMARY KEY (match_id, seat),
    UNIQUE (match_id, profile_id)
);

CREATE INDEX match_seats_by_profile ON match_seats (profile_id);
