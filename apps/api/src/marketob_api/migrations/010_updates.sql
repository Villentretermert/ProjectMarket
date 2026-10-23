-- Allocate delivery order after commit, not from the ingestion identity sequence.
ALTER TABLE change_outbox ADD COLUMN delivery_sequence bigint UNIQUE;
ALTER TABLE change_outbox ADD COLUMN delivered_at timestamptz;
ALTER TABLE change_outbox ADD COLUMN event_name text;
CREATE INDEX outbox_pending ON change_outbox(sequence) WHERE delivery_sequence IS NULL;
CREATE TABLE delivery_state (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    watermark bigint NOT NULL DEFAULT 0
);
INSERT INTO delivery_state DEFAULT VALUES;
CREATE TABLE event_preferences (
    sequence bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    user_id text NOT NULL REFERENCES users(user_id),
    channel_id text NOT NULL REFERENCES channel_access(channel_id),
    events jsonb NOT NULL,
    PRIMARY KEY(user_id,channel_id)
);
