ALTER TABLE memberships DROP CONSTRAINT memberships_role_check;
ALTER TABLE memberships ADD CONSTRAINT memberships_role_check
    CHECK (role IN ('owner','admin','editor'));
ALTER TABLE memberships ADD COLUMN sequence bigint GENERATED ALWAYS AS IDENTITY UNIQUE;
CREATE INDEX memberships_user ON memberships(user_id);
-- The initial owner remains immutable in the pilot; no ownership transfer endpoint.
CREATE UNIQUE INDEX memberships_one_owner ON memberships(org_id) WHERE role='owner';
