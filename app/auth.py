"""Request context: tenant-scoped caller identity.

Production connects this to the IAM ticket (S2-IAM). Until then the dependency
requires explicit org_id/site_id from trusted upstream headers, so the query
API can NEVER be called unscoped — closing the cross-tenant IDOR path.
"""
from __future__ import annotations

import uuid

from fastapi import Header, HTTPException


class CallerContext:
    def __init__(self, org_id: uuid.UUID, site_id: uuid.UUID):
        self.org_id = org_id
        self.site_id = site_id


def get_caller(
    x_org_id: str | None = Header(default=None, alias="X-Org-Id"),
    x_site_id: str | None = Header(default=None, alias="X-Site-Id"),
) -> CallerContext:
    """Require tenant headers from the trusted gateway.

    The gateway/IAM must strip client-supplied values; this service treats
    them as authoritative and scopes every history query by them.
    """
    if not x_org_id or not x_site_id:
        raise HTTPException(status_code=400, detail="X-Org-Id and X-Site-Id headers required")
    try:
        return CallerContext(org_id=uuid.UUID(x_org_id), site_id=uuid.UUID(x_site_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid tenant headers")
