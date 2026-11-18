"""Alembic revision: space_status_history table + immutability trigger.

Revision ID: 20261118_ssh_001
Revises: (none)
Create Date: 2026-11-18
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261118_ssh_001"
down_revision = None
branch_labels = None
depends_on = None

def uuid_col(**kw):
    """Return a fresh UUID column type instance (Alembic reuses Across revisions)."""
    return postgresql.UUID(as_uuid=True, **kw)


def upgrade() -> None:
    op.create_table(
        "space_status_history",
        sa.Column("id", uuid_col(), primary_key=True),
        sa.Column("org_id", uuid_col(), nullable=False),
        sa.Column("site_id", uuid_col(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", uuid_col(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("object_type", sa.String(32), nullable=False),
        sa.Column("object_id", uuid_col(), nullable=False),
        sa.Column("status_before", sa.String(32), nullable=False),
        sa.Column("status_after", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("lease_id", uuid_col(), nullable=True),
        sa.Column("operator_id", uuid_col(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
    )
    op.create_index(
        "ix_ssh_object_time", "space_status_history",
        ["object_id", "occurred_at", "id"],
        postgresql_using="btree",
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION space_status_history_immutable() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'space_status_history is append-only: % is not allowed', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_space_status_history_immutable
            BEFORE UPDATE OR DELETE ON space_status_history
            FOR EACH ROW EXECUTE FUNCTION space_status_history_immutable();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_space_status_history_immutable ON space_status_history")
    op.execute("DROP FUNCTION IF EXISTS space_status_history_immutable()")
    op.drop_index("ix_ssh_object_time", table_name="space_status_history")
    op.drop_table("space_status_history")
