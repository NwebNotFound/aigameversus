-- What each profile thinks of every other profile it has played with: trust from
-- -100 to +100 and short notes, newest first (arena/memory).
CREATE TABLE relationships (
    profile_id uuid        NOT NULL REFERENCES player_profiles (id) ON DELETE CASCADE,
    other_id   uuid        NOT NULL REFERENCES player_profiles (id) ON DELETE CASCADE,
    trust      integer     NOT NULL DEFAULT 0 CHECK (trust BETWEEN -100 AND 100),
    notes      jsonb       NOT NULL DEFAULT '[]',
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (profile_id, other_id),
    CHECK (profile_id <> other_id)
);

-- Matches whose facts are in the relationships, so a match counts once.
CREATE TABLE remembered_matches (
    match_id    uuid        PRIMARY KEY,
    game_id     text        NOT NULL,
    remembered_at timestamptz NOT NULL DEFAULT now()
);
