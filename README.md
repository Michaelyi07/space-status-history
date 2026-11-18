# space-status-history — Room Status Change History & Query (S2-SPACE-012)

`space_status_history` — append-only audit table + same-transaction write logic + reverse-chronological query API.

Python 3.11+ / FastAPI / SQLAlchemy 2 / Alembic-style migration / PostgreSQL 16. Fictional test data only; no real personal or enterprise data; no client name in deliverables; env-only config/secrets; no overseas SDKs.

## Deliverables

| File | Purpose |
|---|---|
| `app/models.py` | `space_status_history` (all unified convention columns), `space_workstation` / `space_lease` stubs |
| `app/writer.py` | `record_status_change`, `create_lease`, `terminate_lease`, `set_status` — all append in the caller's transaction |
| `app/auth.py` | Tenant-scoped caller context from trusted headers (no cross-tenant IDOR) |
| `app/api.py` | `GET /api/space/workstations/{id}/history` (read-only route, tenant-scoped) |
| `app/db.py` | engine/session factory (`DATABASE_URL` env), DB immutability-trigger installer |
| `app/schemas.py` | response models |
| `alembic.ini` + `migrations/alembic/` | Real Alembic revision `20261118_ssh_001` (upgrade/downgrade), env-only URL |
| `migrations/001_space_status_history.sql` | Equivalent plain-SQL DDL for teams applying by psql |
| `tests/test_criteria.py` | 3 acceptance criteria + edge cases |
| `tests/test_api.py` | HTTP query tests (empty list, paging, scoping) |

## Design decisions (mapping to the ticket)

1. **History table** — every status flip records object type/id, status before/after, reason (`lease_creation` / `lease_termination` / `maintenance` / `manual_adjustment`), associated lease, operator, timestamp. All unified columns present: `id(UUID)`, `org_id`, `site_id`, `created_at`, `created_by`, `updated_at`, `deleted_at` (soft delete).
2. **Write logic** — `record_status_change()` does NOT commit; the caller commits the business row and the history row together. A failed transaction rolls back both (test: `test_failed_transaction_rolls_back_state_and_history`).
3. **Query** — `ORDER BY occurred_at DESC, id DESC`: deterministic tiebreak makes paging stable for same-timestamp changes. No history → HTTP 200 with `{"items": [], "total": 0}` (not 404).
4. **Immutability** — two layers: no update/delete API route exists; a PG `BEFORE UPDATE OR DELETE` trigger raises on any write attempt. ORM updates and raw DELETE both rejected (tests). Corrections are new compensating rows, preserving the audit trail.
5. **Tenant isolation (security)** — the query endpoint requires `X-Org-Id` / `X-Site-Id` headers from the trusted gateway/IAM (S2-IAM integration point in `app/auth.py`) and scopes both the workstation lookup and history rows by tenant. Cross-tenant workstation → 404 (indistinguishable from missing); missing/invalid headers → 400. Closes the cross-tenant IDOR path. A wrong entry cannot be read across tenants.

## Integration points (dependency stubs)

Per the brief, dependencies are stubbed. `app/writer.py` is the integration point:

- **Lease ticket** → call `create_lease()` / `terminate_lease()` from the lease status-write path, passing the same `Session`.
- **Workstation ticket** → call `set_status()` for maintenance/manual adjustments.
- **IAM** → `operator_id` comes from the authenticated context (stubbed in tests).
- **Alembic** → apply the real revision `migrations/alembic/versions/001_space_status_history.py` (`20261118_ssh_001`) in the core team's chain via `alembic upgrade head`. A plain-SQL equivalent (`migrations/001_space_status_history.sql`) is provided for psql-based pipelines.

## Run & test

Requirements: Python 3.11+, PostgreSQL 16.

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt          # Windows: .venv\Scripts\pip
export DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5433/space_history_test
psql "$DATABASE_URL" -f migrations/001_space_status_history.sql   # or create_all in tests
pytest tests -v

# HTTP smoke
uvicorn app.api:router --app-dir . --port 8080
curl http://127.0.0.1:8080/api/space/workstations/<uuid>/history
```

Env vars:

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@127.0.0.1:5433/space_history_test` | SQLAlchemy URL |

## Verification record

Environment: Windows x64; Python 3.13.14; PostgreSQL **16.9** (Visual C++ build 1943, 64-bit) real instance at `127.0.0.1:5433`; SQLAlchemy 2.1.9; psycopg 3.3.9; FastAPI 0.163.2; pytest 9.2.0. Tests run against real PostgreSQL — no SQLite, no DB-layer mocks.

```
$ DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5433/space_history_test python -m pytest tests -v
tests/test_api.py::test_empty_history_returns_200_empty_list PASSED      [  7%]
tests/test_api.py::test_history_query_newest_first_with_paging PASSED    [ 15%]
tests/test_api.py::test_history_scoped_to_one_workstation PASSED         [ 23%]
tests/test_api.py::test_cross_tenant_query_rejected PASSED               [ 30%]
tests/test_api.py::test_missing_tenant_headers_rejected PASSED           [ 38%]
tests/test_criteria.py::test_lease_creation_and_termination_both_recorded PASSED [ 46%]
tests/test_criteria.py::test_maintenance_and_manual_adjustment_recorded PASSED [ 53%]
tests/test_criteria.py::test_failed_transaction_rolls_back_state_and_history PASSED [ 61%]
tests/test_criteria.py::test_query_reverse_chronological PASSED          [ 69%]
tests/test_criteria.py::test_same_timestamp_tiebreak_is_deterministic PASSED [ 76%]
tests/test_criteria.py::test_immutable_orm_update_rejected PASSED        [ 84%]
tests/test_criteria.py::test_immutable_raw_delete_rejected PASSED        [ 92%]
tests/test_criteria.py::test_compensating_row_is_the_correction_model PASSED [100%]

======================== 13 passed, 1 warning in 2.39s ========================
```

DB-level trigger verification (psql, same PG16 instance):

```
$ psql -h 127.0.0.1 -p 5433 -U postgres -d space_history_test -c "SELECT tgname FROM pg_trigger WHERE tgrelid='space_status_history'::regclass AND NOT tgisinternal;"
               tgname
------------------------------------
 trg_space_status_history_immutable
(1 row)
```

Alembic revision verification on a clean database (`alembic_verify`):

```
$ DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5433/alembic_verify python -m alembic upgrade head
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 20261118_ssh_001, Alembic revision: space_status_history table + immutability trigger.

$ psql -h 127.0.0.1 -p 5433 -U postgres -d alembic_verify -c "SELECT tgname FROM pg_trigger WHERE tgrelid='space_status_history'::regclass AND NOT tgisinternal;"
               tgname
------------------------------------
 trg_space_status_history_immutable
(1 row)
```
