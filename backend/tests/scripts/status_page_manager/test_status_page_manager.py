from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest
from bson import ObjectId

from orion.api.interactive.status_page_manager.status_page_manager import StatusPageManager
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus
from orion.services.mongo_manager.shared_model.db_status_page_model import UpdateStatusPageRequest
from orion.shared_models.exceptions import NotFoundError, ValidationError
from tests.scripts.status_page_manager.fixtures import clear_caches
from tests.scripts.status_page_manager.helpers import NOW, _create, _manager, _overview


def test_create_generates_unique_slug_and_response():
    manager, _ = _manager()
    first = _create(manager, name="Public Status")
    second = _create(manager, name="Public Status")

    assert first.slug == "public-status"
    assert second.slug == "public-status-2"
    assert first.public_path == "/status/public-status"
    assert first.monitor_count == 0


def test_create_validates_name_and_monitor_ids():
    manager, _ = _manager()
    with pytest.raises(ValidationError):
        _create(manager, name="   ")

    manager_missing, _ = _manager(monitors=[])
    with pytest.raises(ValidationError):
        _create(manager_missing, monitor_ids=["ghost"])

    manager_ok, _ = _manager(monitors=[SimpleNamespace(id="m1")])
    created = _create(manager_ok, monitor_ids=["m1"])
    assert created.monitor_ids == ["m1"]


def test_list_get_and_get_by_slug():
    manager, _ = _manager()
    created = _create(manager, name="Primary")

    listed = asyncio.run(manager.list_pages())
    fetched = asyncio.run(manager.get_page(created.id))
    by_slug = asyncio.run(manager.get_page_by_slug("primary"))

    assert [page.name for page in listed] == ["Primary"]
    assert fetched.id == created.id
    assert by_slug.slug == "primary"


def test_get_and_delete_missing_raise_not_found():
    manager, _ = _manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager.get_page(str(ObjectId())))
    with pytest.raises(NotFoundError):
        asyncio.run(manager.get_page("not-valid"))
    with pytest.raises(NotFoundError):
        asyncio.run(manager.get_page_by_slug("nope"))
    with pytest.raises(NotFoundError):
        asyncio.run(manager.delete_page("not-valid"))
    with pytest.raises(NotFoundError):
        asyncio.run(manager.delete_page(str(ObjectId())))


def test_update_page_changes_fields_and_rejects_nulls():
    manager, _ = _manager(monitors=[SimpleNamespace(id="m1")])
    created = _create(manager, name="Old")

    updated = asyncio.run(manager.update_page(created.id, UpdateStatusPageRequest(name="New", description="desc", monitor_ids=["m1"])))
    assert updated.name == "New"
    assert updated.description == "desc"
    assert updated.monitor_ids == ["m1"]

    with pytest.raises(ValidationError):
        asyncio.run(manager.update_page(created.id, UpdateStatusPageRequest(monitor_ids=None)))
    with pytest.raises(ValidationError):
        asyncio.run(manager.update_page(created.id, UpdateStatusPageRequest(description=None)))
    with pytest.raises(NotFoundError):
        asyncio.run(manager.update_page(str(ObjectId()), UpdateStatusPageRequest(name="x")))


def test_delete_page_removes_it():
    manager, collection = _manager()
    created = _create(manager)
    asyncio.run(manager.delete_page(created.id))
    assert collection.documents == []


@pytest.mark.parametrize(
    "statuses,expected",
    [
        ([MonitorStatus.UP, MonitorStatus.UP], "operational"),
        ([MonitorStatus.UP, MonitorStatus.DOWN], "outage"),
        ([MonitorStatus.UP, MonitorStatus.UNKNOWN], "degraded"),
    ],
)
def test_build_public_response_overall_status(statuses, expected):
    monitor_ids = [f"m{i}" for i in range(len(statuses))]
    overviews = [_overview(mid, status=status) for mid, status in zip(monitor_ids, statuses, strict=True)]
    manager, _ = _manager(monitors=[SimpleNamespace(id=mid) for mid in monitor_ids], overviews=overviews)
    created = _create(manager, monitor_ids=monitor_ids)

    page_model = asyncio.run(manager.get_page_by_slug(created.slug))
    public = asyncio.run(manager.build_public_response(page_model, overviews))

    assert public.overall_status == expected
    assert public.monitor_count == len(statuses)
    assert len(public.monitors) == len(statuses)


def test_build_public_response_unknown_when_all_paused():
    overviews = [_overview("m1", is_active=False)]
    manager, _ = _manager(monitors=[SimpleNamespace(id="m1")], overviews=overviews)
    created = _create(manager, monitor_ids=["m1"])
    page_model = asyncio.run(manager.get_page_by_slug(created.slug))

    public = asyncio.run(manager.build_public_response(page_model, overviews))
    assert public.overall_status == "unknown"
    assert public.monitors_paused == 1


def test_get_public_page_uses_dashboard_overviews():
    overviews = [_overview("m1", status=MonitorStatus.UP)]
    manager, _ = _manager(monitors=[SimpleNamespace(id="m1")], overviews=overviews)
    created = _create(manager, name="Ops", monitor_ids=["m1"])

    public = asyncio.run(manager.get_public_page(created.slug))
    assert public.slug == created.slug
    assert public.overall_status == "operational"


def test_get_public_monitor_detail_builds_events():
    incident = SimpleNamespace(id="i1", status_code=503, reason="Received HTTP 503.", started_at=NOW - timedelta(minutes=10), resolved_at=NOW, duration_seconds=600)
    overviews = [_overview("m1")]
    manager, _ = _manager(monitors=[SimpleNamespace(id="m1")], overviews=overviews, incidents={"m1": [incident]})
    created = _create(manager, monitor_ids=["m1"])

    detail = asyncio.run(manager.get_public_monitor_detail(created.slug, "m1"))
    assert detail.monitor.id == "m1"
    event_types = {event.event_type for event in detail.recent_events}
    assert {"down", "up", "created"} <= event_types


def test_get_public_monitor_detail_rejects_unknown_monitor():
    manager, _ = _manager(monitors=[SimpleNamespace(id="m1")], overviews=[_overview("m1")])
    created = _create(manager, monitor_ids=["m1"])
    with pytest.raises(NotFoundError):
        asyncio.run(manager.get_public_monitor_detail(created.slug, "not-on-page"))


def test_percentage_and_window_helpers():
    assert StatusPageManager._percentage({"successful": 9, "total": 10}) == 90.0
    assert StatusPageManager._percentage({"successful": 0, "total": 0}) is None
    assert StatusPageManager._percentage(None) is None
    assert StatusPageManager._window_percentage({"overall_7": [{"uptime_percentage": 99.987}]}, "overall_7") == 99.99
    assert StatusPageManager._window_percentage({}, "overall_7") is None
