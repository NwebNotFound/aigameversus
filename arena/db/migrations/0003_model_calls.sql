-- The spend ledger: one row per model call that was sent to a provider.
CREATE TABLE model_calls (
    id             bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    match_id       uuid        NOT NULL,
    player         text        NOT NULL,
    model          text        NOT NULL,  -- key in config/models.yaml
    called_at      timestamptz NOT NULL,
    input_tokens   integer,               -- NULL: no usage came back, the cost is the upper bound
    output_tokens  integer,
    cost_micro_eur bigint      NOT NULL   -- millionths of a euro
);

CREATE INDEX model_calls_match_id ON model_calls (match_id);
CREATE INDEX model_calls_called_at ON model_calls (called_at);
