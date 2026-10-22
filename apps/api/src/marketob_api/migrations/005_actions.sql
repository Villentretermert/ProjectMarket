CREATE TABLE action_requests (
    sequence bigint GENERATED ALWAYS AS IDENTITY,
    action_request_id text PRIMARY KEY,
    event_id text NOT NULL UNIQUE,
    channel_id text NOT NULL REFERENCES channel_access(channel_id),
    bot_id text NOT NULL REFERENCES bots(bot_id),
    user_id text NOT NULL REFERENCES users(user_id),
    actor_ref text NOT NULL,
    resource_id text NOT NULL,
    action_id text NOT NULL,
    observed_source_revision bigint NOT NULL CHECK (observed_source_revision > 0),
    quantity integer NOT NULL CHECK (quantity = 1),
    idempotency_key text NOT NULL,
    body_hash text NOT NULL,
    state text NOT NULL DEFAULT 'queued'
        CHECK (state IN ('queued','processing','confirmed','failed','unknown','cancelled')),
    summary text NOT NULL DEFAULT 'Request queued. No payment has been taken.',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    acknowledged_at timestamptz,
    progress_at timestamptz,
    terminal_at timestamptz,
    result_revision bigint NOT NULL DEFAULT 0,
    UNIQUE(user_id,channel_id,idempotency_key),
    CHECK ((state IN ('confirmed','failed','cancelled')) = (terminal_at IS NOT NULL))
);
CREATE INDEX requests_bot_scan ON action_requests(bot_id,sequence);
CREATE INDEX requests_channel_actor ON action_requests(channel_id,user_id);
CREATE INDEX requests_expiry ON action_requests(terminal_at) WHERE terminal_at IS NOT NULL;
CREATE TABLE action_results (
    bot_id text NOT NULL REFERENCES bots(bot_id),
    result_id text NOT NULL,
    action_request_id text NOT NULL REFERENCES action_requests(action_request_id) ON DELETE CASCADE,
    body_hash text NOT NULL,
    external_reference text,
    received_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(bot_id,result_id)
);
ALTER TABLE change_outbox ADD COLUMN action_request_id text;
