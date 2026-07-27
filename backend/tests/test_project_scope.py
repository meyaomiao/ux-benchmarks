"""Project-scope hardening tests.

These cover the cross-project access guards added to the M4 review service,
the L3 insight service and the L5 report service.  They are DB-free: the
guards only need ``Session.get``, so a tiny stub session is enough and the
tests stay deterministic without Postgres.

A wrong-project id must be reported as NOT_FOUND (404), never FORBIDDEN, so
the error cannot be used to probe which ids exist in other projects.
"""
import uuid

import pytest

from app.core.errors import AppError
from app.services.l3_insight import insight_service
from app.services.l5_report import report_service
from app.services.m4_annotation import review_service

PROJECT_A = uuid.uuid4()
PROJECT_B = uuid.uuid4()


class _Row:
    """Stand-in for an ORM row that only needs id + project_id."""

    def __init__(self, project_id):
        self.id = uuid.uuid4()
        self.project_id = project_id


class _StubSession:
    """Returns a preset row for any ``get`` call; records deletes/commits."""

    def __init__(self, row=None):
        self._row = row
        self.deleted = []
        self.commits = 0

    def get(self, _model, _pk):
        return self._row

    def delete(self, obj):
        self.deleted.append(obj)

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        pass


# --- M4 assets --------------------------------------------------------------

class TestLoadScopedAsset:
    def test_same_project_asset_is_returned(self):
        row = _Row(PROJECT_A)
        db = _StubSession(row)
        assert review_service._load_scoped_asset(db, row.id, PROJECT_A) is row

    def test_other_project_asset_raises_not_found(self):
        row = _Row(PROJECT_B)
        db = _StubSession(row)
        with pytest.raises(AppError) as exc:
            review_service._load_scoped_asset(db, row.id, PROJECT_A)
        assert exc.value.status_code == 404

    def test_missing_asset_raises_not_found(self):
        db = _StubSession(None)
        with pytest.raises(AppError) as exc:
            review_service._load_scoped_asset(db, uuid.uuid4(), PROJECT_A)
        assert exc.value.status_code == 404

    def test_none_project_id_stays_unscoped(self):
        row = _Row(PROJECT_B)
        db = _StubSession(row)
        assert review_service._load_scoped_asset(db, row.id, None) is row


# --- L3 insights ------------------------------------------------------------

class TestInsightScope:
    def test_get_insight_hides_other_project(self):
        row = _Row(PROJECT_B)
        db = _StubSession(row)
        assert insight_service.get_insight(db, row.id, PROJECT_A) is None
        assert insight_service.get_insight(db, row.id, PROJECT_B) is row

    def test_update_insight_other_project_raises_not_found(self):
        row = _Row(PROJECT_B)
        db = _StubSession(row)
        with pytest.raises(AppError) as exc:
            insight_service.update_insight(db, row.id, {"claim": "x"}, PROJECT_A)
        assert exc.value.status_code == 404
        assert db.commits == 0

    def test_delete_insight_other_project_raises_and_deletes_nothing(self):
        row = _Row(PROJECT_B)
        db = _StubSession(row)
        with pytest.raises(AppError) as exc:
            insight_service.delete_insight(db, row.id, PROJECT_A)
        assert exc.value.status_code == 404
        assert db.deleted == []


# --- L5 reports -------------------------------------------------------------

class TestReportScope:
    def test_get_report_hides_other_project(self):
        row = _Row(PROJECT_B)
        db = _StubSession(row)
        assert report_service.get_report(db, row.id, PROJECT_A) is None
        assert report_service.get_report(db, row.id, PROJECT_B) is row

    def test_delete_report_other_project_raises_and_deletes_nothing(self):
        row = _Row(PROJECT_B)
        db = _StubSession(row)
        with pytest.raises(AppError) as exc:
            report_service.delete_report(db, row.id, PROJECT_A)
        assert exc.value.status_code == 404
        assert db.deleted == []


# --- Route wiring -----------------------------------------------------------

# Paths that read or write project-owned data and therefore must resolve the
# active project through get_project_id.  Guards against a future endpoint
# being added without the dependency (the original #19 leak).
SCOPED_ROUTES = [
    ("GET", "/api/v1/m3/probe-runs"),
    ("GET", "/api/v1/m3/probe-runs/summary"),
    ("GET", "/api/v1/m4/shortlist/{cell_id}/{competitor_id}"),
    ("POST", "/api/v1/m4/shortlist/accept"),
    ("POST", "/api/v1/m4/shortlist/reject"),
    ("POST", "/api/v1/m4/shortlist/flag"),
    ("POST", "/api/v1/m4/insights/generate"),
    ("GET", "/api/v1/m4/insights/{insight_id}"),
    ("PATCH", "/api/v1/m4/insights/{insight_id}"),
    ("DELETE", "/api/v1/m4/insights/{insight_id}"),
    ("GET", "/api/v1/m5/coverage/{cell_id}/{competitor_id}"),
    ("POST", "/api/v1/m5/coverage/{cell_id}/{competitor_id}/recompute"),
    ("POST", "/api/v1/m5/reports/generate"),
    ("GET", "/api/v1/m5/reports/export.md"),
    ("GET", "/api/v1/reports/{report_id}"),
    ("DELETE", "/api/v1/reports/{report_id}"),
]


def _walk_routes(router, prefix=""):
    """Yield (full_path, route) pairs, expanding lazily-included sub-routers.

    FastAPI keeps included routers as placeholder entries whose children store
    paths relative to the include point, so the parent prefix has to be
    re-applied while walking.
    """
    for route in router.routes:
        original = getattr(route, "original_router", None)
        if original is not None:
            context = getattr(route, "include_context", None)
            yield from _walk_routes(original, getattr(context, "prefix", "") or "")
        else:
            yield prefix + getattr(route, "path", ""), route


def _dependency_names(route) -> set[str]:
    return {d.call.__name__ for d in route.dependant.dependencies if d.call}


@pytest.mark.parametrize(("method", "path"), SCOPED_ROUTES)
def test_route_requires_project_scope(method, path):
    from app.core.deps import get_project_id
    from app.main import app

    matches = [
        route for full_path, route in _walk_routes(app)
        if full_path == path and method in (getattr(route, "methods", None) or set())
    ]
    assert matches, f"route not found: {method} {path}"
    assert get_project_id.__name__ in _dependency_names(matches[0])
