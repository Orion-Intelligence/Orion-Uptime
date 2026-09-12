from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from bson import ObjectId

from orion.constants.constant import Collections, Intervals
from orion.management.jobs.monitoring_controller.monitoring_controller import MonitorManager
from orion.services.mongo_manager.shared_model.db_heartbeat_monitor_model import HeartbeatMonitorModel
from orion.services.mongo_manager.shared_model.db_incident_model import IncidentModel
from orion.services.mongo_manager.shared_model.db_monitor_state_model import MonitorTransition
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import HealthCheckResponse, MonitorStatus, MonitorType
from orion.services.mongo_manager.shared_model.db_orion_script_monitor_model import OrionFeederStatus, OrionScriptCheckResponse
from tests.model.fakes import FakeCollection
from tests.scripts.monitoring_controller.helpers import NOW, _async_return, _manager, _monitor, _state_result, _tracked


def test_get_monitor_service_dispatches_and_raises_for_unknown():
    http, api, ping, heartbeat = SimpleNamespace(), SimpleNamespace(), SimpleNamespace(), SimpleNamespace()
    manager = _manager(http=http, api=api, ping=ping, heartbeat=heartbeat)

    assert manager._get_monitor_service(MonitorType.HTTP) is http
    assert manager._get_monitor_service(MonitorType.API) is api
    assert manager._get_monitor_service(MonitorType.PING) is ping
    assert manager._get_monitor_service(MonitorType.HEARTBEAT) is heartbeat
    with pytest.raises(ValueError):
        manager._get_monitor_service(MonitorType.ORION_SCRIPT)


def test_get_monitor_service_returns_orion_script_when_configured():
    orion = SimpleNamespace()
    manager = _manager(orion_script=orion)
    assert manager._get_monitor_service(MonitorType.ORION_SCRIPT) is orion


@pytest.mark.parametrize(
    "monitor,result,expected",
    [
        (SimpleNamespace(monitor_type=MonitorType.HEARTBEAT), None, "Heartbeat was not received."),
        (SimpleNamespace(monitor_type=MonitorType.HTTP), None, "The monitor failed without producing a check result."),
        (SimpleNamespace(monitor_type=MonitorType.HTTP), SimpleNamespace(status_code=None, error="boom", timed_out=True), "boom"),
        (SimpleNamespace(monitor_type=MonitorType.HTTP), SimpleNamespace(status_code=None, error=None, timed_out=True), "The health check timed out before a response was received."),
        (SimpleNamespace(monitor_type=MonitorType.HTTP), SimpleNamespace(status_code=None, error="boom", timed_out=False), "boom"),
        (SimpleNamespace(monitor_type=MonitorType.HTTP, expected_status_code=200), SimpleNamespace(status_code=503, error=None, timed_out=False), "Expected HTTP 200 OK, but received HTTP 503 Service Unavailable — The server cannot process the request due to a high load."),
        (SimpleNamespace(monitor_type=MonitorType.HTTP), SimpleNamespace(status_code=200, error=None, timed_out=False), "Received HTTP 200 OK — Request fulfilled, document follows, but the configured response requirements were not satisfied."),
        (SimpleNamespace(monitor_type=MonitorType.HTTP), SimpleNamespace(status_code=None, error=None, timed_out=False), "The target could not be reached and returned no HTTP response."),
    ],
)
def test_build_incident_reason(monitor, result, expected):
    assert MonitorManager._build_incident_reason(monitor, result) == expected


def test_build_incident_reason_includes_status_details_with_error():
    monitor = SimpleNamespace(monitor_type=MonitorType.HTTP)
    result = SimpleNamespace(status_code=500, error="boom", timed_out=False)
    reason = MonitorManager._build_incident_reason(monitor, result)
    assert reason.startswith("Received HTTP 500 Internal Server Error")
    assert reason.endswith("boom")


def test_http_status_label_known_and_unknown():
    assert MonitorManager._http_status_label(404) == "404 Not Found"
    assert MonitorManager._http_status_label(999) == "999"


def test_http_status_details_known_and_unknown():
    assert MonitorManager._http_status_details(404) == "404 Not Found — Nothing matches the given URI"
    assert MonitorManager._http_status_details(999) == "999 — The target returned a non-standard HTTP status code"


@pytest.mark.parametrize(
    "timeout,expected",
    [
        (30, 100.0),
        (None, float(Intervals.CHECK_DEADLINE_GRACE_SECONDS)),
        (0, float(Intervals.CHECK_DEADLINE_GRACE_SECONDS)),
        (-5, float(Intervals.CHECK_DEADLINE_GRACE_SECONDS)),
        ("bad", float(Intervals.CHECK_DEADLINE_GRACE_SECONDS)),
    ],
)
def test_check_deadline_seconds(timeout, expected):
    monitor = SimpleNamespace(timeout=timeout)
    assert MonitorManager.check_deadline_seconds(monitor) == expected


def test_check_deadline_seconds_defaults_when_attribute_missing():
    monitor = SimpleNamespace()
    assert MonitorManager.check_deadline_seconds(monitor) == float(Intervals.CHECK_DEADLINE_GRACE_SECONDS)


def test_run_check_with_deadline_returns_checker_result():
    monitor = _monitor()
    response = HealthCheckResponse(url="http://x", status=MonitorStatus.UP, status_code=200, response_time_ms=5, success=True)
    checker = SimpleNamespace(check=_async_return(response))
    result = asyncio.run(MonitorManager.run_check_with_deadline(checker, monitor))
    assert result is response


def test_run_check_with_deadline_returns_timeout_response(monkeypatch):
    monkeypatch.setattr(Intervals, "CHECK_DEADLINE_GRACE_SECONDS", 0)
    monitor = _monitor(timeout=0.01)

    async def _slow_check(_monitor):
        await asyncio.sleep(0.2)

    checker = SimpleNamespace(check=_slow_check)
    response = asyncio.run(MonitorManager.run_check_with_deadline(checker, monitor))

    assert response.timed_out is True
    assert response.status == MonitorStatus.DOWN
    assert response.success is False
    assert response.url == "http://x"


def test_get_monitor_dispatches_by_type():
    http_monitor = SimpleNamespace(id="h1")
    manager = _manager(http=SimpleNamespace(get_monitor_model=_async_return(http_monitor)))
    result = asyncio.run(manager.get_monitor("h1", MonitorType.HTTP))
    assert result is http_monitor


def test_get_monitor_tries_all_when_type_is_none():
    api_monitor = SimpleNamespace(id="a1")
    manager = _manager(
        http=SimpleNamespace(get_monitor_model=_async_return(None)),
        api=SimpleNamespace(get_monitor_model=_async_return(api_monitor)),
        ping=SimpleNamespace(),
        heartbeat=SimpleNamespace(),
    )
    result = asyncio.run(manager.get_monitor("a1"))
    assert result is api_monitor


def test_get_monitor_returns_none_when_nothing_matches():
    manager = _manager(
        http=SimpleNamespace(get_monitor_model=_async_return(None)),
        api=SimpleNamespace(get_monitor_model=_async_return(None)),
        ping=SimpleNamespace(get_monitor_model=_async_return(None)),
        heartbeat=SimpleNamespace(get_monitor_model=_async_return(None)),
    )
    assert asyncio.run(manager.get_monitor("ghost")) is None


def test_list_monitors_combines_all_services():
    manager = _manager(
        http=SimpleNamespace(list_monitor_models=_async_return([SimpleNamespace(id="h1")])),
        api=SimpleNamespace(list_monitor_models=_async_return([SimpleNamespace(id="a1")])),
        ping=SimpleNamespace(list_monitor_models=_async_return([SimpleNamespace(id="p1")])),
        heartbeat=SimpleNamespace(list_monitor_models=_async_return([SimpleNamespace(id="hb1")])),
        orion_script=SimpleNamespace(list_monitor_models=_async_return([SimpleNamespace(id="os1")])),
    )
    monitors = asyncio.run(manager.list_monitors())
    assert [monitor.id for monitor in monitors] == ["h1", "a1", "p1", "hb1", "os1"]


def test_list_monitors_without_orion_script_service():
    manager = _manager(
        http=SimpleNamespace(list_monitor_models=_async_return([])),
        api=SimpleNamespace(list_monitor_models=_async_return([])),
        ping=SimpleNamespace(list_monitor_models=_async_return([])),
        heartbeat=SimpleNamespace(list_monitor_models=_async_return([])),
    )
    assert asyncio.run(manager.list_monitors()) == []


def test_get_monitors_with_lookup_builds_dict_by_persisted_id():
    monitor = SimpleNamespace(id="m1", persisted_id="m1")
    manager = _manager(
        http=SimpleNamespace(list_monitor_models=_async_return([monitor])),
        api=SimpleNamespace(list_monitor_models=_async_return([])),
        ping=SimpleNamespace(list_monitor_models=_async_return([])),
        heartbeat=SimpleNamespace(list_monitor_models=_async_return([])),
    )
    monitors, lookup = asyncio.run(manager.get_monitors_with_lookup())
    assert monitors == [monitor]
    assert lookup == {"m1": monitor}


def test_list_active_monitors_filters_inactive():
    active = SimpleNamespace(id="m1", is_active=True)
    inactive = SimpleNamespace(id="m2", is_active=False)
    manager = _manager(
        http=SimpleNamespace(list_monitor_models=_async_return([active, inactive])),
        api=SimpleNamespace(list_monitor_models=_async_return([])),
        ping=SimpleNamespace(list_monitor_models=_async_return([])),
        heartbeat=SimpleNamespace(list_monitor_models=_async_return([])),
    )
    result = asyncio.run(manager.list_active_monitors())
    assert result == [active]


def test_delete_monitor_history_cleans_up_related_data():
    calls = []
    status_pages = FakeCollection()
    status_pages.documents.append({"_id": ObjectId(), "monitor_ids": ["m1"], "updated_at": NOW})
    slack_integrations = FakeCollection()
    email_integrations = FakeCollection()
    database = {Collections.STATUS_PAGES: status_pages, Collections.SLACK_INTEGRATIONS: slack_integrations, Collections.EMAIL_INTEGRATIONS: email_integrations}
    results_service = SimpleNamespace(delete_for_monitor=_tracked(calls, "results"), collection=SimpleNamespace(database=database))
    incident_service = SimpleNamespace(delete_for_monitor=_tracked(calls, "incident"))
    state_service = SimpleNamespace(delete_for_monitor=_tracked(calls, "state"))
    manager = _manager(results=results_service, incident=incident_service, state=state_service)

    asyncio.run(manager.delete_monitor_history("m1"))

    names = [call[0] for call in calls]
    assert "results" in names
    assert "incident" in names
    assert "state" in names
    assert calls[names.index("results")][1][0] == "m1"


def test_delete_monitor_history_notifies_for_slack_and_email_matches():
    calls = []
    status_pages = FakeCollection()
    status_pages.documents.append({"_id": ObjectId(), "monitor_ids": ["other"], "updated_at": NOW})
    slack_integrations = FakeCollection()
    slack_integrations.documents.append({"_id": ObjectId(), "monitor_ids": ["m1"], "updated_at": NOW})
    email_integrations = FakeCollection()
    email_integrations.documents.append({"_id": ObjectId(), "monitor_ids": ["m1"], "updated_at": NOW})
    database = {Collections.STATUS_PAGES: status_pages, Collections.SLACK_INTEGRATIONS: slack_integrations, Collections.EMAIL_INTEGRATIONS: email_integrations}
    results_service = SimpleNamespace(delete_for_monitor=_tracked(calls, "results"), collection=SimpleNamespace(database=database))
    incident_service = SimpleNamespace(delete_for_monitor=_tracked(calls, "incident"))
    state_service = SimpleNamespace(delete_for_monitor=_tracked(calls, "state"))
    manager = _manager(results=results_service, incident=incident_service, state=state_service)

    asyncio.run(manager.delete_monitor_history("m1"))

    assert status_pages.documents[0]["monitor_ids"] == ["other"]
    assert slack_integrations.documents[0]["monitor_ids"] == ["m1"]
    assert email_integrations.documents[0]["monitor_ids"] == ["m1"]


def test_check_and_update_returns_when_monitor_missing():
    calls = []
    monitor = _monitor()
    manager = _manager(http=SimpleNamespace(get_monitor_model=_async_return(None)), results=SimpleNamespace(record_result=_tracked(calls, "record")))
    asyncio.run(manager.check_and_update(monitor))
    assert calls == []


def test_check_and_update_skips_heartbeat_without_last_heartbeat():
    calls = []
    heartbeat_model = HeartbeatMonitorModel(id="hb1", name="hb", expected_heartbeat_interval=60, heartbeat_token_hash="hash", created_at=NOW, updated_at=NOW, last_heartbeat_at=None)
    monitor = _monitor(persisted_id="hb1", monitor_type=MonitorType.HEARTBEAT)
    manager = _manager(heartbeat=SimpleNamespace(get_monitor_model=_async_return(heartbeat_model)), results=SimpleNamespace(record_result=_tracked(calls, "record")))
    asyncio.run(manager.check_and_update(monitor))
    assert calls == []


def test_check_and_update_swallows_exceptions():
    monitor = _monitor()

    async def _raise(_monitor_id):
        raise RuntimeError("boom")

    manager = _manager(http=SimpleNamespace(get_monitor_model=_raise))
    asyncio.run(manager.check_and_update(monitor))


def test_check_and_update_stores_feeder_results_for_orion_script():
    calls = []
    monitor = _monitor(persisted_id="os1", monitor_type=MonitorType.ORION_SCRIPT)
    feeder = OrionFeederStatus(key="f1", name="Feeder", status=MonitorStatus.UP)
    response = OrionScriptCheckResponse(url="http://x", status=MonitorStatus.UP, status_code=200, response_time_ms=10, success=True, feeders=[feeder])
    state_result = _state_result(MonitorStatus.UP, previous_status=MonitorStatus.UP, transition=MonitorTransition.NONE)
    orion_service = SimpleNamespace(get_monitor_model=_async_return(monitor), update_monitoring_result=_tracked(calls, "update"), store_feeders=_tracked(calls, "store_feeders"))
    manager = _manager(
        orion_script=orion_service,
        checker_factory=SimpleNamespace(get_checker=lambda _monitor_type: SimpleNamespace(check=_async_return(response))),
        state=SimpleNamespace(process_result=_async_return(state_result)),
        results=SimpleNamespace(record_result=_tracked(calls, "record"), record_feeder_results=_tracked(calls, "feeder_results")),
    )

    asyncio.run(manager.check_and_update(monitor))

    names = [call[0] for call in calls]
    assert "store_feeders" in names
    assert "feeder_results" in names


def test_check_and_update_records_success_and_resolves_incident():
    calls = []
    monitor = _monitor()
    response = HealthCheckResponse(url="http://x", status=MonitorStatus.UP, status_code=200, response_time_ms=12, success=True, is_slow=False)
    state_result = _state_result(MonitorStatus.UP, previous_status=MonitorStatus.DOWN, transition=MonitorTransition.UP)
    resolved_incident = IncidentModel(id="i1", monitor_id="m1", monitor_type=MonitorType.HTTP, started_at=NOW, reason="down", is_resolved=True, resolved_at=NOW)

    http_service = SimpleNamespace(get_monitor_model=_async_return(monitor), update_monitoring_result=_tracked(calls, "update"))
    incident_service = SimpleNamespace(resolve_incident=_tracked(calls, "resolve", resolved_incident))
    manager = _manager(
        http=http_service,
        checker_factory=SimpleNamespace(get_checker=lambda _monitor_type: SimpleNamespace(check=_async_return(response))),
        state=SimpleNamespace(process_result=_async_return(state_result)),
        results=SimpleNamespace(record_result=_tracked(calls, "record")),
        incident=incident_service,
    )
    notified = []
    manager.slack_integration_service = SimpleNamespace(notify_transition=_tracked(notified, "slack"))

    asyncio.run(manager.check_and_update(monitor))

    names = [call[0] for call in calls]
    assert names == ["record", "update", "resolve"]
    assert calls[0][2]["status"] == MonitorStatus.UP
    assert calls[0][2]["success"] is True
    assert calls[2][1] == ("m1", MonitorType.HTTP)
    assert len(notified) == 1


def test_check_and_update_records_failure_and_opens_incident():
    calls = []
    monitor = _monitor()
    response = HealthCheckResponse(url="http://x", status=MonitorStatus.DOWN, status_code=500, response_time_ms=None, success=False, is_slow=False, error="boom")
    state_result = _state_result(MonitorStatus.DOWN, previous_status=MonitorStatus.UP, transition=MonitorTransition.DOWN)
    opened_incident = IncidentModel(id="i2", monitor_id="m1", monitor_type=MonitorType.HTTP, started_at=NOW, reason="down")

    http_service = SimpleNamespace(get_monitor_model=_async_return(monitor), update_monitoring_result=_tracked(calls, "update"))
    incident_service = SimpleNamespace(get_active_incident=_async_return(None), open_incident=_tracked(calls, "open", opened_incident))
    manager = _manager(
        http=http_service,
        checker_factory=SimpleNamespace(get_checker=lambda _monitor_type: SimpleNamespace(check=_async_return(response))),
        state=SimpleNamespace(process_result=_async_return(state_result)),
        results=SimpleNamespace(record_result=_tracked(calls, "record")),
        incident=incident_service,
    )
    notified = []
    manager.email_integration_service = SimpleNamespace(notify_transition=_tracked(notified, "email"))

    asyncio.run(manager.check_and_update(monitor))

    open_call = next(call for call in calls if call[0] == "open")
    assert open_call[1][0] == "m1"
    assert open_call[1][1] == MonitorType.HTTP
    assert "boom" in open_call[1][2]
    assert open_call[1][3] == 500
    assert len(notified) == 1


def test_handle_incident_transition_opens_incident_on_down():
    calls = []
    monitor = _monitor()
    result = SimpleNamespace(status_code=500, error="boom", timed_out=False)
    state_result = _state_result(MonitorStatus.DOWN, transition=MonitorTransition.DOWN)
    opened = IncidentModel(id="i1", monitor_id="m1", monitor_type=MonitorType.HTTP, started_at=NOW, reason="down")
    incident_service = SimpleNamespace(get_active_incident=_async_return(None), open_incident=_tracked(calls, "open", opened))
    manager = _manager(incident=incident_service)

    incident = asyncio.run(manager._handle_incident_transition(monitor, result, state_result))
    assert incident is opened
    assert calls[0][0] == "open"


def test_handle_incident_transition_skips_open_when_already_active():
    monitor = _monitor()
    result = SimpleNamespace(status_code=500, error="boom", timed_out=False)
    state_result = _state_result(MonitorStatus.DOWN, transition=MonitorTransition.DOWN)
    active = IncidentModel(id="i0", monitor_id="m1", monitor_type=MonitorType.HTTP, started_at=NOW, reason="already open")
    incident_service = SimpleNamespace(get_active_incident=_async_return(active))
    manager = _manager(incident=incident_service)

    incident = asyncio.run(manager._handle_incident_transition(monitor, result, state_result))
    assert incident is active


def test_handle_incident_transition_resolves_on_up():
    calls = []
    monitor = _monitor()
    state_result = _state_result(MonitorStatus.UP, previous_status=MonitorStatus.DOWN, transition=MonitorTransition.UP)
    resolved = IncidentModel(id="i1", monitor_id="m1", monitor_type=MonitorType.HTTP, started_at=NOW, reason="down", is_resolved=True, resolved_at=NOW)
    incident_service = SimpleNamespace(resolve_incident=_tracked(calls, "resolve", resolved))
    manager = _manager(incident=incident_service)

    incident = asyncio.run(manager._handle_incident_transition(monitor, None, state_result))
    assert incident is resolved
    assert calls[0][1] == ("m1", MonitorType.HTTP)


def test_handle_incident_transition_none_when_no_transition():
    monitor = _monitor()
    state_result = _state_result(MonitorStatus.UP, previous_status=MonitorStatus.UP, transition=MonitorTransition.NONE)
    manager = _manager()
    incident = asyncio.run(manager._handle_incident_transition(monitor, None, state_result))
    assert incident is None


def test_process_heartbeat_records_and_transitions():
    calls = []
    monitor = SimpleNamespace(persisted_id="hb1", id="hb1", monitor_type=MonitorType.HEARTBEAT, name="hb")
    state_result = _state_result(MonitorStatus.UP, previous_status=MonitorStatus.UNKNOWN, transition=MonitorTransition.UP)
    resolved = IncidentModel(id="i1", monitor_id="hb1", monitor_type=MonitorType.HEARTBEAT, started_at=NOW, reason="x", is_resolved=True, resolved_at=NOW)
    heartbeat_service = SimpleNamespace(update_monitoring_result=_tracked(calls, "update"))
    incident_service = SimpleNamespace(resolve_incident=_tracked(calls, "resolve", resolved))
    manager = _manager(
        heartbeat=heartbeat_service,
        results=SimpleNamespace(record_result=_tracked(calls, "record")),
        state=SimpleNamespace(process_result=_async_return(state_result)),
        incident=incident_service,
    )

    asyncio.run(manager.process_heartbeat(monitor))

    names = [call[0] for call in calls]
    assert names == ["record", "update", "resolve"]
    assert calls[0][2]["monitor_id"] == "hb1"
    assert calls[1][2]["status"] == MonitorStatus.UP
