-- Model qualification results (research/QUALIFY.md): one row per job. A job is not a match:
-- it has no match record, replay or batch; its id books its calls in the ledger (model_calls).
CREATE TABLE qualifications (
    id                 uuid        PRIMARY KEY,
    model_id           text        NOT NULL,   -- exact provider model id, suffix included
    game               text        NOT NULL,
    scope              text        NOT NULL,   -- "core"
    config_hash        text        NOT NULL,   -- sha256 of `configuration`, canonical JSON
    configuration      jsonb       NOT NULL,
    status             text        NOT NULL,   -- running, qualified, unqualified, unknown
    badge              text,                   -- "repaired (v1)", on a qualified v1 job
    reasons            jsonb       NOT NULL DEFAULT '[]',
    cases              jsonb       NOT NULL DEFAULT '[]',
    counts             jsonb       NOT NULL DEFAULT '{}',  -- clean, repaired, failed, unknown
    reserved_micro_eur bigint      NOT NULL,   -- the job's worst case, before it ran
    cap_micro_eur      bigint      NOT NULL,   -- the cap of this click
    parent_id          uuid        REFERENCES qualifications (id),  -- the failed job it retries
    started_at         timestamptz NOT NULL,
    finished_at        timestamptz,
    expires_at         timestamptz             -- after it, the result is no longer current
);
CREATE INDEX qualifications_model_game ON qualifications (model_id, game, started_at DESC);
