CREATE TABLE personal_pages (
    sequence bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    page_id text PRIMARY KEY,
    user_id text NOT NULL REFERENCES users(user_id),
    title text NOT NULL,
    layout jsonb NOT NULL,
    create_key_hash text NOT NULL,
    create_body_hash text NOT NULL,
    deleted_at timestamptz,
    UNIQUE(user_id,create_key_hash)
);
CREATE INDEX personal_pages_user ON personal_pages(user_id,sequence);
