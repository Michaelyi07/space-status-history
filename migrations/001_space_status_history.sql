-- 001_space_status_history.sql — Alembic-equivalent schema migration for PG16.
-- Can be applied with: psql -f migrations/001_space_status_history.sql
-- (Same DDL is created by Base.metadata.create_all for tests; this file is the
--  hand-off artifact for the core team's Alembic migration chain.)

CREATE TABLE IF NOT EXISTS space_status_history (
    id             uuid PRIMARY KEY,
    org_id         uuid NOT NULL,
    site_id        uuid NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now(),
    created_by     uuid NOT NULL,
    updated_at     timestamptz NOT NULL DEFAULT now(),
    deleted_at     timestamptz,
    object_type    varchar(32) NOT NULL,
    object_id      uuid NOT NULL,
    status_before  varchar(32) NOT NULL,
    status_after   varchar(32) NOT NULL,
    reason         varchar(32) NOT NULL,
    lease_id       uuid,
    operator_id    uuid NOT NULL,
    occurred_at    timestamptz NOT NULL,
    note           varchar(500)
);

-- Reverse-chronological query + tiebreak paging index.
CREATE INDEX IF NOT EXISTS ix_ssh_object_time
    ON space_status_history (object_id, occurred_at DESC, id DESC);

-- Immutability: reject any UPDATE or DELETE, including soft delete.
-- Corrections must be new compensating rows.
CREATE OR REPLACE FUNCTION space_status_history_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'space_status_history is append-only: % is not allowed', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_space_status_history_immutable ON space_status_history;
CREATE TRIGGER trg_space_status_history_immutable
    BEFORE UPDATE OR DELETE ON space_status_history
    FOR EACH ROW EXECUTE FUNCTION space_status_history_immutable();
