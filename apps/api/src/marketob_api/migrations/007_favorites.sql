-- Store references only; current access controls every metadata projection.
CREATE TABLE favorite_state (
    user_id text PRIMARY KEY REFERENCES users(user_id),
    revision bigint NOT NULL DEFAULT 0 CHECK (revision >= 0)
);
CREATE TABLE favorites (
    user_id text NOT NULL REFERENCES users(user_id),
    channel_id text NOT NULL REFERENCES channel_access(channel_id),
    position bigint NOT NULL,
    seen_data bigint NOT NULL DEFAULT 0,
    seen_template bigint NOT NULL DEFAULT 0,
    PRIMARY KEY(user_id, channel_id)
);
