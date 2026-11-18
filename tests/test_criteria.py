"""Acceptance criteria tests (each maps 1:1 to the ticket)."""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import models, writer
from tests.conftest import BASE_TS, OPERATOR, ORG, SITE, make_workstation


def rows_of(db, object_id):
    return (
        db.query(models.SpaceStatusHistory)
        .filter(models.SpaceStatusHistory.object_id == object_id)
        .all()
    )


# ---------------------------------------------------------------- criterion 1
def test_lease_creation_and_termination_both_recorded(db):
    ws = make_workstation(db)

    lease, h_create = writer.create_lease(db, workstation=ws, operator_id=OPERATOR, occurred_at=BASE_TS)
    db.commit()

    history = rows_of(db, ws.id)
    assert len(history) == 1
    row = history[0]
    assert row.status_before == "available"
    assert row.status_after == "occupied"
    assert row.reason == "lease_creation"
    assert row.lease_id == lease.id
    assert ws.status == "occupied"

    h_term = writer.terminate_lease(
        db, lease=lease, workstation=ws, operator_id=OPERATOR,
        occurred_at=BASE_TS + timedelta(hours=1)
    )
    db.commit()

    history = rows_of(db, ws.id)
    assert len(history) == 2
    term = [r for r in history if r.reason == "lease_termination"][0]
    assert term.status_before == "occupied"
    assert term.status_after == "available"
    assert term.lease_id == lease.id
    assert ws.status == "available"


def test_maintenance_and_manual_adjustment_recorded(db):
    ws = make_workstation(db)
    writer.set_status(db, workstation=ws, new_status="maintenance",
                      reason=models.ChangeReason.MAINTENANCE.value, operator_id=OPERATOR)
    writer.set_status(db, workstation=ws, new_status="available",
                      reason=models.ChangeReason.MANUAL_ADJUSTMENT.value,
                      operator_id=OPERATOR, note="虚构维护完成")
    db.commit()
    reasons = {r.reason for r in rows_of(db, ws.id)}
    assert reasons == {"maintenance", "manual_adjustment"}


def test_failed_transaction_rolls_back_state_and_history(db):
    """Same-transaction guarantee: if the caller raises after a write, neither
    the status flip nor the history row survives."""
    ws = make_workstation(db)
    db.commit()
    try:
        writer.create_lease(db, workstation=ws, operator_id=OPERATOR)
        raise RuntimeError("simulated downstream failure")
    except RuntimeError:
        db.rollback()
    db.expire_all()
    assert ws.status == "available"
    assert rows_of(db, ws.id) == []


# ---------------------------------------------------------------- criterion 2
def test_query_reverse_chronological(db):
    ws = make_workstation(db)
    for i in range(4):
        writer.set_status(
            db, workstation=ws,
            new_status="maintenance" if i % 2 == 0 else "available",
            reason=models.ChangeReason.MANUAL_ADJUSTMENT.value,
            operator_id=OPERATOR,
            occurred_at=BASE_TS + timedelta(hours=i),
            note=f"虚构变更{i}",
        )
    db.commit()

    ordered = (
        db.query(models.SpaceStatusHistory)
        .filter(models.SpaceStatusHistory.object_id == ws.id)
        .order_by(models.SpaceStatusHistory.occurred_at.desc(),
                  models.SpaceStatusHistory.id.desc())
        .all()
    )
    assert [r.note for r in ordered] == ["虚构变更3", "虚构变更2", "虚构变更1", "虚构变更0"]


def test_same_timestamp_tiebreak_is_deterministic(db):
    """Same timestamp -> id DESC tiebreak, identical order across repeated queries."""
    ws = make_workstation(db)
    for i in range(3):
        writer.set_status(db, workstation=ws, new_status="maintenance",
                          reason=models.ChangeReason.MANUAL_ADJUSTMENT.value,
                          operator_id=OPERATOR, occurred_at=BASE_TS)
    db.commit()
    q = lambda: [str(r.id) for r in (
        db.query(models.SpaceStatusHistory)
        .filter(models.SpaceStatusHistory.object_id == ws.id)
        .order_by(models.SpaceStatusHistory.occurred_at.desc(),
                  models.SpaceStatusHistory.id.desc()).all())]
    first = q()
    assert first == q()
    assert first == sorted(first, reverse=True)


# ---------------------------------------------------------------- criterion 3
def test_immutable_orm_update_rejected(db):
    ws = make_workstation(db)
    writer.set_status(db, workstation=ws, new_status="maintenance",
                      reason=models.ChangeReason.MAINTENANCE.value, operator_id=OPERATOR)
    db.commit()
    row = rows_of(db, ws.id)[0]
    row.note = "篡改尝试"
    with pytest.raises(Exception) as exc:
        db.commit()
    db.rollback()
    assert "append-only" in str(exc.value).lower() or "UPDATE" in str(exc.value)
    db.expire_all()
    assert rows_of(db, ws.id)[0].note is None


def test_immutable_raw_delete_rejected(db):
    ws = make_workstation(db)
    writer.set_status(db, workstation=ws, new_status="maintenance",
                      reason=models.ChangeReason.MAINTENANCE.value, operator_id=OPERATOR)
    db.commit()
    hist_id = rows_of(db, ws.id)[0].id
    with pytest.raises(SQLAlchemyError) as exc:
        db.execute(text("DELETE FROM space_status_history WHERE id = :i"), {"i": hist_id})
    db.rollback()
    assert "append-only" in str(exc.value).lower()
    assert len(rows_of(db, ws.id)) == 1


def test_compensating_row_is_the_correction_model(db):
    """Wrong entry is corrected by a NEW row, never by mutating the old one."""
    ws = make_workstation(db)
    writer.set_status(db, workstation=ws, new_status="maintenance",
                      reason=models.ChangeReason.MANUAL_ADJUSTMENT.value,
                      operator_id=OPERATOR, occurred_at=BASE_TS)
    first = rows_of(db, ws.id)[0].id
    writer.set_status(db, workstation=ws, new_status="available",
                      reason=models.ChangeReason.MANUAL_ADJUSTMENT.value,
                      operator_id=OPERATOR, occurred_at=BASE_TS + timedelta(seconds=1),
                      note="compensates previous entry")
    db.commit()
    all_rows = rows_of(db, ws.id)
    assert len(all_rows) == 2
    assert {r.id for r in all_rows} >= {first}
    assert any(r.note == "compensates previous entry" for r in all_rows)
