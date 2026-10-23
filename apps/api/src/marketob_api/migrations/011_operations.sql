ALTER TABLE delivery_state ADD COLUMN retention_floor bigint NOT NULL DEFAULT 0;
CREATE INDEX outbox_expiry ON change_outbox(delivered_at,delivery_sequence);
CREATE INDEX requests_unresolved ON action_requests(bot_id) WHERE terminal_at IS NULL;
CREATE INDEX history_bot ON ingest_history(bot_id);
CREATE TABLE worker_state (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    succeeded_at timestamptz
);
INSERT INTO worker_state DEFAULT VALUES;

-- Account uncompressed JSON bytes, independent of TOAST compression or payload repetition.
CREATE TABLE history_usage (
    bot_id text PRIMARY KEY REFERENCES bots(bot_id),
    rows bigint NOT NULL DEFAULT 0 CHECK (rows>=0),
    bytes bigint NOT NULL DEFAULT 0 CHECK (bytes>=0)
);
INSERT INTO history_usage SELECT bot_id,count(*),sum(octet_length(body::text))
FROM ingest_history GROUP BY bot_id;
CREATE FUNCTION account_history() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='INSERT' THEN
        INSERT INTO history_usage(bot_id,rows,bytes)
        VALUES (NEW.bot_id,1,octet_length(NEW.body::text))
        ON CONFLICT(bot_id) DO UPDATE SET rows=history_usage.rows+1,
            bytes=history_usage.bytes+excluded.bytes;
        IF EXISTS (SELECT 1 FROM history_usage WHERE bot_id=NEW.bot_id
                   AND (rows>100000 OR bytes>268435456)) THEN
            RAISE check_violation USING CONSTRAINT='history_capacity';
        END IF;
    ELSIF TG_OP='DELETE' THEN
        UPDATE history_usage SET rows=rows-1,bytes=bytes-octet_length(OLD.body::text)
        WHERE bot_id=OLD.bot_id;
    END IF;
    RETURN NULL;
END;
$$;
CREATE TRIGGER history_account AFTER INSERT OR DELETE ON ingest_history
FOR EACH ROW EXECUTE FUNCTION account_history();

-- No shared counter lock: concurrent commits must retain independent delivery ordering.
-- The limit can overshoot by in-flight transactions; worker deletion restores capacity.
CREATE FUNCTION bound_outbox() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (SELECT count(*)>=250000 OR count(*) FILTER (WHERE delivery_sequence IS NULL)>=20000
        FROM change_outbox) THEN
        RAISE check_violation USING CONSTRAINT='outbox_capacity';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER outbox_admission BEFORE INSERT ON change_outbox
FOR EACH ROW EXECUTE FUNCTION bound_outbox();
