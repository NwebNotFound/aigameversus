-- One row per match that was started through the API: what was asked for and how it ended.
CREATE TABLE matches (
    id          uuid        PRIMARY KEY,
    game        text        NOT NULL,
    status      text        NOT NULL
                CHECK (status IN ('running', 'finished', 'failed', 'interrupted')),
    players     text[]      NOT NULL,
    seed        bigint      NOT NULL,
    settings    jsonb       NOT NULL,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,            -- set when the match stopped, however it ended
    placements  jsonb                   -- [{"player": ..., "rank": ...}], only when finished
);

CREATE INDEX matches_started_at ON matches (started_at DESC);
