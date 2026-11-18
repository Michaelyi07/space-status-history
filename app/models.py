"""Space status history — models.

All data is fictional test data; no real personal or enterprise information.
Unified conventions: id(UUID), org_id, site_id, created_at, created_by,
updated_at, deleted_at (soft delete); amounts (not used here) stored in cents.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class ObjectType(str, enum.Enum):
    SPACE_UNIT = "space_unit"
    WORKSTATION = "workstation"


class ChangeReason(str, enum.Enum):
    LEASE_CREATION = "lease_creation"
    LEASE_TERMINATION = "lease_termination"
    MAINTENANCE = "maintenance"
    MANUAL_ADJUSTMENT = "manual_adjustment"


class SpaceStatus(str, enum.Enum):
    AVAILABLE = "available"
    OCCUPIED = "occupied"
    MAINTENANCE = "maintenance"
    RESERVED = "reserved"


class ConventionMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SpaceStatusHistory(ConventionMixin, Base):
    """Append-only audit record of every space/workstations status change.

    DB-level immutability: a BEFORE UPDATE OR DELETE trigger raises an
    exception (see migrations/001...sql + app/db.py install helper). The API
    exposes no update/delete route. Corrections are recorded as compensating
    new rows, never by mutating existing ones.
    """

    __tablename__ = "space_status_history"

    object_type: Mapped[str] = mapped_column(String(32), nullable=False)
    object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status_before: Mapped[str] = mapped_column(String(32), nullable=False)
    status_after: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    lease_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    operator_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    note: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (
        # id tiebreak makes reverse-chronological paging stable even when two
        # changes carry the same timestamp.
        UniqueConstraint("id", name="uq_space_status_history_id"),
    )


class Workstation(ConventionMixin, Base):
    """Mock of the sibling workstation ticket (interface stub per brief)."""

    __tablename__ = "space_workstation"

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class Lease(ConventionMixin, Base):
    """Mock of the sibling lease ticket (interface stub per brief)."""

    __tablename__ = "space_lease"

    workstation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("space_workstation.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    amount_cents: Mapped[int | None] = mapped_column(nullable=True)
