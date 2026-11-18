"""HTTP query API tests."""
from __future__ import annotations

from datetime import timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import writer
from app.api import router
from tests.conftest import BASE_TS, OPERATOR, make_workstation


def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_empty_history_returns_200_empty_list(db):
    ws = make_workstation(db)
    db.commit()
    r = client().get(f"/api/space/workstations/{ws.id}/history")
    assert r.status_code == 200
    assert r.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}


def test_history_query_newest_first_with_paging(db):
    ws = make_workstation(db)
    for i in range(5):
        writer.set_status(db, workstation=ws,
                          new_status="maintenance" if i % 2 == 0 else "available",
                          reason="manual_adjustment", operator_id=OPERATOR,
                          occurred_at=BASE_TS + timedelta(hours=i),
                          note=f"虚构{i}")
    db.commit()
    c = client()
    page1 = c.get(f"/api/space/workstations/{ws.id}/history", params={"limit": 2, "offset": 0}).json()
    page2 = c.get(f"/api/space/workstations/{ws.id}/history", params={"limit": 2, "offset": 2}).json()
    assert page1["total"] == 5
    assert [x["note"] for x in page1["items"]] == ["虚构4", "虚构3"]
    assert [x["note"] for x in page2["items"]] == ["虚构2", "虚构1"]


def test_history_scoped_to_one_workstation(db):
    a = make_workstation(db, "WS-A")
    b = make_workstation(db, "WS-B")
    writer.set_status(db, workstation=a, new_status="maintenance",
                      reason="maintenance", operator_id=OPERATOR)
    db.commit()
    r = client().get(f"/api/space/workstations/{b.id}/history")
    assert r.status_code == 200
    assert r.json()["total"] == 0
