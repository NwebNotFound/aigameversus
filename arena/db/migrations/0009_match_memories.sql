-- Long-term memory: one short summary of each remembered match per profile, from
-- that player's view, with the profiles it played against (arena/memory).
CREATE TABLE match_memories (
    profile_id uuid        NOT NULL REFERENCES player_profiles (id) ON DELETE CASCADE,
    match_id   uuid        NOT NULL,
    game_id    text        NOT NULL,
    opponents  uuid[]      NOT NULL,
    summary    text        NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (profile_id, match_id)
);

CREATE INDEX match_memories_newest ON match_memories (profile_id, created_at DESC);

-- A match played with memory off neither reads nor writes any memory (fair benchmarks).
ALTER TABLE matches ADD COLUMN memory boolean NOT NULL DEFAULT true;
