CREATE TABLE users (
    user_id text PRIMARY KEY,
    username text NOT NULL UNIQUE CHECK (username ~ '^[a-z0-9_-]{3,40}$'),
    display_name text NOT NULL,
    password_hash text,
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);
CREATE TABLE sessions (
    token_hash text PRIMARY KEY,
    user_id text NOT NULL REFERENCES users(user_id),
    origin text NOT NULL,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX sessions_user ON sessions(user_id);
CREATE INDEX sessions_expiry ON sessions(expires_at);
CREATE TABLE organizations (
    org_id text PRIMARY KEY,
    owner_user_id text NOT NULL UNIQUE REFERENCES users(user_id),
    name text NOT NULL,
    active boolean NOT NULL DEFAULT true
);
CREATE TABLE memberships (
    org_id text NOT NULL REFERENCES organizations(org_id),
    user_id text NOT NULL REFERENCES users(user_id),
    role text NOT NULL CHECK (role = 'owner'),
    PRIMARY KEY (org_id, user_id)
);
-- The access record is separate from channel content added in subsequent tasks.
CREATE TABLE channel_access (
    channel_id text PRIMARY KEY,
    org_id text NOT NULL REFERENCES organizations(org_id),
    visibility text NOT NULL CHECK (visibility IN ('public', 'selected')),
    published boolean NOT NULL DEFAULT false,
    deleted_at timestamptz
);
CREATE TABLE grants (
    sequence bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    channel_id text NOT NULL REFERENCES channel_access(channel_id),
    user_id text NOT NULL REFERENCES users(user_id),
    PRIMARY KEY (channel_id, user_id)
);
CREATE TABLE rate_windows (
    bucket text PRIMARY KEY,
    window_start timestamptz NOT NULL,
    hits integer NOT NULL CHECK (hits > 0)
);
CREATE TABLE change_outbox (
    sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    channel_id text NOT NULL REFERENCES channel_access(channel_id),
    user_id text REFERENCES users(user_id),
    kind text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE server_keys (
    purpose text PRIMARY KEY,
    secret bytea NOT NULL
);
