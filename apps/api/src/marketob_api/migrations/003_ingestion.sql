CREATE TABLE channel_content (
    channel_id text PRIMARY KEY REFERENCES channel_access(channel_id),
    slug text NOT NULL UNIQUE,
    title text NOT NULL,
    layout jsonb NOT NULL,
    actions jsonb NOT NULL DEFAULT '[]',
    data_revision bigint NOT NULL DEFAULT 0 CHECK (data_revision >= 0)
);
CREATE TABLE source_records (
    channel_id text NOT NULL REFERENCES channel_content(channel_id),
    resource_id text NOT NULL,
    source_revision bigint NOT NULL CHECK (source_revision > 0),
    data_revision bigint NOT NULL CHECK (data_revision > 0),
    content_type text CHECK (content_type IN ('news','product','chart')),
    content jsonb,
    deleted boolean NOT NULL,
    updated_at timestamptz NOT NULL,
    PRIMARY KEY (channel_id, resource_id),
    CHECK ((deleted AND content IS NULL) OR (NOT deleted AND content IS NOT NULL AND content_type IS NOT NULL))
);
CREATE TABLE message_receipts (
    bot_id text NOT NULL REFERENCES bots(bot_id),
    message_id text NOT NULL,
    body_hash text NOT NULL,
    receipt_id text NOT NULL UNIQUE,
    channel_id text NOT NULL REFERENCES channel_content(channel_id),
    data_revision bigint NOT NULL CHECK (data_revision > 0),
    received_at timestamptz NOT NULL,
    PRIMARY KEY (bot_id, message_id)
);
CREATE INDEX receipts_expiry ON message_receipts(received_at);
CREATE TABLE ingest_history (
    receipt_id text PRIMARY KEY,
    channel_id text NOT NULL REFERENCES channel_content(channel_id),
    bot_id text NOT NULL REFERENCES bots(bot_id),
    body jsonb NOT NULL,
    received_at timestamptz NOT NULL
);
CREATE INDEX history_expiry ON ingest_history(received_at);
ALTER TABLE change_outbox ADD COLUMN data_revision bigint;
ALTER TABLE change_outbox ADD COLUMN resource_id text;
ALTER TABLE change_outbox ADD COLUMN receipt_id text;
CREATE INDEX changes_channel_revision ON change_outbox(channel_id, data_revision);
CREATE TABLE rate_buckets (
    bucket text PRIMARY KEY,
    tokens double precision NOT NULL,
    updated_at timestamptz NOT NULL
);
