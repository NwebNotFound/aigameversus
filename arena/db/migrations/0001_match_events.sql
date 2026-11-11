-- The event log: one row per event, ordered by seq within a match.
CREATE TABLE match_events (
    match_id    uuid        NOT NULL,
    seq         integer     NOT NULL,
    source      text        NOT NULL,  -- 'engine' or 'game'
    type        text        NOT NULL,
    data        jsonb       NOT NULL,
    visible_to  text[],                -- NULL: public; empty: spectators only; else these players
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (match_id, seq)
);
