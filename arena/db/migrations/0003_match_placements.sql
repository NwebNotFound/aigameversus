-- Each rated player's result in a match, for win rates, placements and match history.
CREATE TABLE match_placements (
    match_id      uuid             NOT NULL REFERENCES rated_matches (match_id) ON DELETE CASCADE,
    profile_id    uuid             NOT NULL REFERENCES player_profiles (id) ON DELETE CASCADE,
    rank          integer          NOT NULL CHECK (rank >= 1),
    players       integer          NOT NULL CHECK (players >= 2),
    rating_before double precision NOT NULL,
    rating_after  double precision NOT NULL,
    PRIMARY KEY (match_id, profile_id)
);

CREATE INDEX match_placements_by_profile ON match_placements (profile_id);
