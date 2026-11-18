"""Engine/session factory: DATABASE_URL from env, never hardcoded secrets."""
from __future__ import annotations

import os

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://postgres:postgres@127.0.0.1:5433/space_history_test"
)

IMMUTABILITY_SQL = """
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
"""

_engine = None
_session_factory = None
_trigger_installed: set[str] = set()


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(database_url(), pool_pre_ping=True, future=True)
    return _engine


def install_immutability_trigger(engine) -> None:
    """Install the DB-level immutability trigger (idempotent).

    Called once per engine after create_all. In production the migration
    (migrations/001_...sql) applies this DDL; this helper lets tests and local
    runs reproduce the exact same guarantee without a separate psql step.
    """
    key = str(id(engine))
    if key in _trigger_installed:
        return
    with engine.begin() as conn:
        conn.execute(text(IMMUTABILITY_SQL))
    _trigger_installed.add(key)


def make_session():
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _session_factory()
