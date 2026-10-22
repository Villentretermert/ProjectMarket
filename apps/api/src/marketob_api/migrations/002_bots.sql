CREATE TABLE bots (
    sequence bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    bot_id text PRIMARY KEY,
    org_id text NOT NULL REFERENCES organizations(org_id),
    name text NOT NULL,
    state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','active','revoked')),
    last_seen timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX bots_org ON bots(org_id, sequence);
CREATE TABLE bot_registrations (
    token_hash text PRIMARY KEY,
    bot_id text NOT NULL UNIQUE REFERENCES bots(bot_id),
    expires_at timestamptz NOT NULL
);
CREATE TABLE bot_keys (
    sequence bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    key_id text PRIMARY KEY,
    bot_id text NOT NULL REFERENCES bots(bot_id),
    token_hash text NOT NULL UNIQUE,
    prefix text NOT NULL,
    scopes text[] NOT NULL,
    expires_at timestamptz NOT NULL,
    revoked boolean NOT NULL DEFAULT false
);
CREATE INDEX bot_keys_bot ON bot_keys(bot_id, sequence);
ALTER TABLE channel_access ADD COLUMN bot_id text REFERENCES bots(bot_id);
CREATE INDEX channels_bot ON channel_access(bot_id);
