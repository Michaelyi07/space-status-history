"""GET /api/space/workstations/{id}/history — reverse-chronological query.

Only a read route is exposed: no update/delete endpoints exist, and the DB
trigger rejects any write to history rows (see db.py / migrations).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import CallerContext, get_caller
from .db import make_session
from .models import SpaceStatusHistory
from .schemas import HistoryItem, HistoryPage

router = APIRouter(prefix="/api/space", tags=["space"])


def get_db() -> Session:
    db = make_session()
    try:
        yield db
    finally:
        db.close()


@router.get("/workstations/{workstation_id}/history", response_model=HistoryPage)
def get_workstation_history(
    workstation_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    caller: CallerContext = Depends(get_caller),
) -> HistoryPage:
    """Newest-first history for one workstation; [] (200) when none exists.

    Tenant isolation: the workstation must belong to the caller's org/site,
    and history rows are additionally scoped by org_id/site_id. A workstation
    in another tenant returns 404 (indistinguishable from missing) — no
    cross-tenant IDOR.
    """
    # 1) verify the target workstation belongs to the caller's tenant
    from sqlalchemy import select
    from .models import Workstation

    ws = db.scalar(
        select(Workstation).where(
            Workstation.id == workstation_id,
            Workstation.org_id == caller.org_id,
            Workstation.site_id == caller.site_id,
            Workstation.deleted_at.is_(None),
        )
    )
    if ws is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="workstation_not_found")

    # 2) scope history rows by tenant as well (defense in depth)
    base = select(SpaceStatusHistory).where(
        SpaceStatusHistory.object_type == "workstation",
        SpaceStatusHistory.object_id == workstation_id,
        SpaceStatusHistory.org_id == caller.org_id,
        SpaceStatusHistory.site_id == caller.site_id,
        SpaceStatusHistory.deleted_at.is_(None),
    )
    total = db.scalar(
        select(func.count()).select_from(base.order_by(None).subquery())
    ) or 0
    rows = db.scalars(
        base.order_by(
            SpaceStatusHistory.occurred_at.desc(), SpaceStatusHistory.id.desc()
        ).limit(limit).offset(offset)
    ).all()
    return HistoryPage(
        items=[HistoryItem.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
