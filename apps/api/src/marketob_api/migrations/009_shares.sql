CREATE TABLE shared_templates (
    share_id text PRIMARY KEY,
    user_id text NOT NULL REFERENCES users(user_id),
    page_id text NOT NULL REFERENCES personal_pages(page_id),
    code text NOT NULL UNIQUE,
    title text NOT NULL,
    layout jsonb NOT NULL,
    expires_at timestamptz,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    create_key_hash text NOT NULL,
    create_body_hash text NOT NULL,
    UNIQUE(user_id,create_key_hash)
);
CREATE INDEX shared_templates_page ON shared_templates(page_id,created_at);
