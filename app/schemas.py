"""Pydantic response/request schemas."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class HistoryItem(BaseModel):
    id: uuid.UUID
    object_type: str
    object_id: uuid.UUID
    status_before: str
    status_after: str
    reason: str
    lease_id: uuid.UUID | None = None
    operator_id: uuid.UUID
    occurred_at: datetime
    note: str | None = None

    model_config = {"from_attributes": True}


class HistoryPage(BaseModel):
    items: list[HistoryItem]
    total: int
    limit: int
    offset: int
