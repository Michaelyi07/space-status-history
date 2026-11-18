"""pytest fixtures: real PostgreSQL 16 (DATABASE_URL or local default)."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app import models
from app.db import install_immutability_trigger

ORG = uuid.UUID("00000000-0000-0000-0000-000000000010")
SITE = uuid.UUID("00000000-0000-0000-0000-000000000011")
OPERATOR = uuid.UUID("00000000-0000-0000-0000-000000000012")
BASE_TS = datetime(2026, 11, 18, 9, 0, 0, tzinfo=timezone.utc)


def database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@127.0.0.1:5433/space_history_test",
    )


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(database_url(), future=True)
    with eng.begin() as conn:
        models.Base.metadata.create_all(conn)
    install_immutability_trigger(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    # clean slate per test (DELETE on history is blocked by trigger -> truncate)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE space_status_history, space_lease, space_workstation RESTART IDENTITY CASCADE"))
    s = sessionmaker(bind=engine, expire_on_commit=False)()
    yield s
    s.close()


def make_workstation(db, code="WS-A"):
    ws = models.Workstation(
        id=uuid.uuid4(),
        org_id=ORG,
        site_id=SITE,
        created_by=OPERATOR,
        code=code,
        status=models.SpaceStatus.AVAILABLE.value,
    )
    db.add(ws)
    db.flush()
    return ws
