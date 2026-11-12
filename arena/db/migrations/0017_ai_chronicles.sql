-- AI-written chronicles (D-140): a model's retelling of a finished match's template
-- chronicle, fact-checked per chapter, cached so the same request is paid once. The call is
-- in model_calls under `job_id` (its own id, capped at EUR 0.03 for the chronicle).
CREATE TABLE ai_chronicles (
    match_id    uuid        NOT NULL REFERENCES matches (id),
    style       text        NOT NULL,
    lang        text        NOT NULL,
    model       text        NOT NULL,
    job_id      uuid        NOT NULL,
    status      text        NOT NULL,   -- running, done, failed
    reason      text,                   -- why it failed, if it did
    body        jsonb,                  -- the AiChronicle when done
    created_at  timestamptz NOT NULL,
    PRIMARY KEY (match_id, style, lang, model)
);
