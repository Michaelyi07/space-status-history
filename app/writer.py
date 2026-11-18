"""Status-change write logic — history writer shares the caller's transaction.

The lease and workstation interfaces call record_status_change() inside the
SAME transaction that mutates the business row, so state and history can never
divorce (no orphan history, no unlogged status flip). On failure the caller
rolls back both.

Dependencies are stubbed: lease creation/termination helpers here simulate the
sibling tickets' status-write path; integration point documented in README.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models


def _lock_workstation(db: Session, workstation_id: uuid.UUID) -> models.Workstation:
    """SELECT ... FOR UPDATE so concurrent status flips serialize and
    ``status_before`` always reflects the committed row, not a stale snapshot."""
    return db.scalar(
        select(models.Workstation)
        .where(models.Workstation.id == workstation_id)
        .execution_options(populate_existing=True)
        .with_for_update()
    )


def record_status_change(
    db: Session,
    *,
    object_type: str,
    object_id: uuid.UUID,
    status_before: str,
    status_after: str,
    reason: str,
    operator_id: uuid.UUID,
    org_id: uuid.UUID,
    site_id: uuid.UUID,
    lease_id: uuid.UUID | None = None,
    occurred_at: datetime | None = None,
    note: str | None = None,
) -> models.SpaceStatusHistory:
    """Append one immutable history row. NO commit here — caller owns the tx."""
    if reason not in {r.value for r in models.ChangeReason}:
        raise ValueError(f"unsupported reason: {reason}")
    if object_type not in {t.value for t in models.ObjectType}:
        raise ValueError(f"unsupported object_type: {object_type}")
    row = models.SpaceStatusHistory(
        id=uuid.uuid4(),
        org_id=org_id,
        site_id=site_id,
        created_by=operator_id,
        object_type=object_type,
        object_id=object_id,
        status_before=status_before,
        status_after=status_after,
        reason=reason,
        lease_id=lease_id,
        operator_id=operator_id,
        occurred_at=occurred_at or models.utcnow(),
        note=note,
    )
    db.add(row)
    db.flush()  # assign PK / surface constraint errors now, still inside tx
    return row


def create_lease(
    db: Session,
    *,
    workstation: models.Workstation,
    operator_id: uuid.UUID,
    occurred_at: datetime | None = None,
) -> tuple[models.Lease, models.SpaceStatusHistory]:
    """Lease creation: workstation available -> occupied, one history row."""
    locked = _lock_workstation(db, workstation.id)
    before = locked.status
    lease = models.Lease(
        id=uuid.uuid4(),
        org_id=workstation.org_id,
        site_id=workstation.site_id,
        created_by=operator_id,
        workstation_id=workstation.id,
        status="active",
    )
    workstation.status = models.SpaceStatus.OCCUPIED.value
    db.add(lease)
    history = record_status_change(
        db,
        object_type=models.ObjectType.WORKSTATION.value,
        object_id=workstation.id,
        status_before=before,
        status_after=workstation.status,
        reason=models.ChangeReason.LEASE_CREATION.value,
        operator_id=operator_id,
        org_id=workstation.org_id,
        site_id=workstation.site_id,
        lease_id=lease.id,
        occurred_at=occurred_at,
    )
    return lease, history


def terminate_lease(
    db: Session,
    *,
    lease: models.Lease,
    workstation: models.Workstation,
    operator_id: uuid.UUID,
    occurred_at: datetime | None = None,
) -> models.SpaceStatusHistory:
    """Lease termination: workstation occupied -> available, one history row."""
    locked = _lock_workstation(db, workstation.id)
    before = locked.status
    lease.status = "terminated"
    workstation.status = models.SpaceStatus.AVAILABLE.value
    return record_status_change(
        db,
        object_type=models.ObjectType.WORKSTATION.value,
        object_id=workstation.id,
        status_before=before,
        status_after=workstation.status,
        reason=models.ChangeReason.LEASE_TERMINATION.value,
        operator_id=operator_id,
        org_id=workstation.org_id,
        site_id=workstation.site_id,
        lease_id=lease.id,
        occurred_at=occurred_at,
    )


def set_status(
    db: Session,
    *,
    workstation: models.Workstation,
    new_status: str,
    reason: str,
    operator_id: uuid.UUID,
    note: str | None = None,
    occurred_at: datetime | None = None,
) -> models.SpaceStatusHistory:
    """Manual / maintenance adjustment — same append-only contract."""
    locked = _lock_workstation(db, workstation.id)
    before = locked.status
    workstation.status = new_status
    return record_status_change(
        db,
        object_type=models.ObjectType.WORKSTATION.value,
        object_id=workstation.id,
        status_before=before,
        status_after=new_status,
        reason=reason,
        operator_id=operator_id,
        org_id=workstation.org_id,
        site_id=workstation.site_id,
        occurred_at=occurred_at,
        note=note,
    )
