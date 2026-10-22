ALTER TABLE channel_content ADD COLUMN sequence bigint GENERATED ALWAYS AS IDENTITY;
ALTER TABLE channel_content ADD COLUMN draft_visibility text NOT NULL DEFAULT 'selected'
    CHECK (draft_visibility IN ('public','selected'));
ALTER TABLE channel_content ADD COLUMN published_version bigint;
UPDATE channel_content c SET draft_visibility=a.visibility FROM channel_access a
    WHERE c.channel_id=a.channel_id;
CREATE TABLE channel_versions (
    channel_id text NOT NULL REFERENCES channel_content(channel_id),
    template_version bigint NOT NULL CHECK (template_version > 0),
    definition jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    PRIMARY KEY(channel_id,template_version)
);
INSERT INTO channel_versions(channel_id,template_version,definition)
SELECT channel_id,(layout->>'template_version')::bigint,
    jsonb_build_object('title',title,'visibility',draft_visibility,'layout',layout,'actions',actions)
FROM channel_content;
ALTER TABLE channel_content ADD CONSTRAINT published_definition
    FOREIGN KEY(channel_id,published_version) REFERENCES channel_versions(channel_id,template_version);
ALTER TABLE source_records ADD COLUMN sequence bigint GENERATED ALWAYS AS IDENTITY;
CREATE INDEX sources_scan ON source_records(channel_id,sequence);
