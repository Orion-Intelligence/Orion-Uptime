from __future__ import annotations

import asyncio
import re
from datetime import timedelta
from types import SimpleNamespace

from bson import ObjectId

from orion.management.jobs.monitoring_controller.monitor_results_manager.monitor_results_manager import MonitorResultManager
from orion.services.mongo_manager.shared_model.db_monitor_result_model import MonitorResultModel
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus, MonitorType
from orion.services.mongo_manager.shared_model.db_orion_script_monitor_model import OrionFeederStatus, feeder_result_id
from tests.scripts.monitor_results_manager.helpers import NOW, _async_return, _capture_insert_many, _document, _manager


def test_record_result_persists_and_returns_model():
    manager, collection = _manager()

    result = asyncio.run(manager.record_result("monitor-1", MonitorType.HTTP, MonitorStatus.UP, 200, 42, True))

    assert result.monitor_id == "monitor-1"
    assert result.status == MonitorStatus.UP
    assert result.status_code == 200
    assert result.response_time_ms == 42
    assert len(collection.documents) == 1
    assert result.id == str(collection.documents[0]["_id"])
    assert "id" not in collection.documents[0]
    assert collection.documents[0]["monitor_id"] == "monitor-1"


def test_seed_documents_builds_history_of_up_status():
    documents = MonitorResultManager._seed_documents("monitor-1", MonitorType.HTTP, NOW, days=3)

    assert len(documents) == 3
    assert all(doc["monitor_id"] == "monitor-1" for doc in documents)
    assert all(doc["status"] == MonitorStatus.UP for doc in documents)
    assert all(doc["success"] is True for doc in documents)
    assert all(doc["is_slow"] is False for doc in documents)
    assert "id" not in documents[0]


def test_seed_history_skips_when_already_seeded():
    manager, collection = _manager()
    collection.count_documents = _async_return(1)
    captured = _capture_insert_many(collection)

    asyncio.run(manager.seed_history("monitor-1", MonitorType.HTTP))

    assert captured == []


def test_seed_history_inserts_when_missing():
    manager, collection = _manager()
    collection.count_documents = _async_return(0)
    captured = _capture_insert_many(collection)

    asyncio.run(manager.seed_history("monitor-1", MonitorType.HTTP, days=5))

    assert len(captured) == 1
    assert len(captured[0]) == 5
    assert all(doc["monitor_id"] == "monitor-1" for doc in captured[0])


def test_record_feeder_results_ignores_disabled_and_unknown_feeders():
    manager, collection = _manager()
    feeders = [
        OrionFeederStatus(key="f1", name="Feeder 1", status=MonitorStatus.UNKNOWN, enabled=True),
        OrionFeederStatus(key="f2", name="Feeder 2", status=MonitorStatus.UP, enabled=False),
    ]

    asyncio.run(manager.record_feeder_results("monitor-1", feeders))

    assert collection.documents == []


def test_record_feeder_results_seeds_new_feeders_and_skips_existing():
    manager, collection = _manager()
    captured = _capture_insert_many(collection)
    feeders = [
        OrionFeederStatus(key="f1", name="Feeder 1", status=MonitorStatus.UP, enabled=True),
        OrionFeederStatus(key="f2", name="Feeder 2", status=MonitorStatus.DOWN, enabled=True),
    ]
    existing_id = feeder_result_id("monitor-1", "f2")
    collection.distinct = _async_return([existing_id])

    asyncio.run(manager.record_feeder_results("monitor-1", feeders))

    documents = captured[0]
    f1_id = feeder_result_id("monitor-1", "f1")
    f2_id = feeder_result_id("monitor-1", "f2")
    seeded_f1 = [doc for doc in documents if doc["monitor_id"] == f1_id]
    seeded_f2 = [doc for doc in documents if doc["monitor_id"] == f2_id]

    assert len(seeded_f1) == 46
    assert len(seeded_f2) == 1
    assert seeded_f2[0]["status"] == MonitorStatus.DOWN
    assert seeded_f2[0]["success"] is False


def test_average_response_time_rounds_result():
    manager, collection = _manager()
    collection.aggregate = lambda pipeline: SimpleNamespace(to_list=_async_return([{"avg": 123.456}]))

    result = asyncio.run(manager.average_response_time())

    assert result == 123.46


def test_average_response_time_defaults_to_zero():
    manager, collection = _manager()
    collection.aggregate = lambda pipeline: SimpleNamespace(to_list=_async_return([]))

    result = asyncio.run(manager.average_response_time())

    assert result == 0.0


def test_get_first_check_times_maps_monitor_to_earliest_checked_at():
    manager, collection = _manager()
    collection.aggregate = lambda pipeline: SimpleNamespace(to_list=_async_return([{"_id": "m1", "checked_at": NOW}, {"_id": "m2", "checked_at": NOW}]))

    result = asyncio.run(manager.get_first_check_times(["m1", "m2"]))

    assert result == {"m1": NOW, "m2": NOW}


def test_get_first_check_times_returns_empty_without_ids():
    manager, collection = _manager()

    result = asyncio.run(manager.get_first_check_times([]))

    assert result == {}


def test_get_latest_per_monitor_returns_models():
    manager, collection = _manager()
    documents = [
        {"_id": ObjectId(), "monitor_id": "m1", "monitor_type": MonitorType.HTTP, "status": MonitorStatus.UP, "status_code": 200, "response_time_ms": 50, "success": True, "is_slow": False, "checked_at": NOW},
        {"_id": ObjectId(), "monitor_id": "m2", "monitor_type": MonitorType.PING, "status": MonitorStatus.DOWN, "status_code": None, "response_time_ms": None, "success": False, "is_slow": False, "checked_at": NOW},
    ]
    collection.aggregate = lambda pipeline: SimpleNamespace(to_list=_async_return(documents))

    result = asyncio.run(manager.get_latest_per_monitor())

    assert [item.monitor_id for item in result] == ["m1", "m2"]
    assert all(isinstance(item, MonitorResultModel) for item in result)


def test_get_response_history_filters_by_monitor():
    manager, collection = _manager()
    collection.documents.append(_document("monitor-1", NOW - timedelta(days=2)))
    collection.documents.append(_document("monitor-1", NOW - timedelta(days=1)))
    collection.documents.append(_document("monitor-2", NOW - timedelta(days=1)))

    results = asyncio.run(manager.get_response_history("monitor-1"))

    assert len(results) == 2
    assert all(result.monitor_id == "monitor-1" for result in results)
    assert all(isinstance(result, MonitorResultModel) for result in results)


def test_get_status_history_delegates_to_response_history():
    manager, collection = _manager()
    collection.documents.append(_document("monitor-1", NOW - timedelta(days=1)))

    results = asyncio.run(manager.get_status_history("monitor-1"))

    assert len(results) == 1
    assert results[0].monitor_id == "monitor-1"


def test_get_statistics_returns_total_and_successful():
    manager, collection = _manager()
    collection.aggregate = lambda pipeline: SimpleNamespace(to_list=_async_return([{"total": 5, "successful": 3}]))

    result = asyncio.run(manager.get_statistics("monitor-1"))

    assert result == {"total": 5, "successful": 3}


def test_get_statistics_defaults_when_no_results():
    manager, collection = _manager()
    collection.aggregate = lambda pipeline: SimpleNamespace(to_list=_async_return([]))

    result = asyncio.run(manager.get_statistics("monitor-1"))

    assert result == {"total": 0, "successful": 0}


def test_get_public_uptime_breakdown_empty_monitor_ids_skips_aggregate():
    manager, collection = _manager()

    result = asyncio.run(manager.get_public_uptime_breakdown([], NOW))

    assert result == {"daily": [], "monitors_90": [], "overall_24": [], "overall_7": [], "overall_30": [], "overall_90": []}


def test_get_public_uptime_breakdown_returns_facet_result():
    manager, collection = _manager()
    canned = {"daily": [{"_id": {"monitor_id": "m1", "date": "2026-01-01"}, "total": 10, "successful": 9}], "monitors_90": [], "overall_24": [{"uptime_percentage": 100.0}], "overall_7": [], "overall_30": [], "overall_90": []}
    collection.aggregate = lambda pipeline: SimpleNamespace(to_list=_async_return([canned]))

    result = asyncio.run(manager.get_public_uptime_breakdown(["m1"], NOW))

    assert result == canned


def test_get_public_uptime_breakdown_no_results_returns_empty_dict():
    manager, collection = _manager()
    collection.aggregate = lambda pipeline: SimpleNamespace(to_list=_async_return([]))

    result = asyncio.run(manager.get_public_uptime_breakdown(["m1"], NOW))

    assert result == {}


def test_get_public_response_time_returns_points_and_metrics():
    manager, collection = _manager()
    canned = {"points": [{"_id": NOW, "response_time_ms": 120.0}], "metrics": [{"average_ms": 120.0, "maximum_ms": 130.0, "minimum_ms": 110.0}]}
    collection.aggregate = lambda pipeline: SimpleNamespace(to_list=_async_return([canned]))

    result = asyncio.run(manager.get_public_response_time("monitor-1", NOW))

    assert result == canned


def test_get_public_response_time_defaults_when_no_results():
    manager, collection = _manager()
    collection.aggregate = lambda pipeline: SimpleNamespace(to_list=_async_return([]))

    result = asyncio.run(manager.get_public_response_time("monitor-1", NOW))

    assert result == {"points": [], "metrics": []}


def test_count_slow_checks_counts_matching_documents():
    manager, collection = _manager()
    collection.documents.append(_document("monitor-1", NOW, is_slow=True))
    collection.documents.append(_document("monitor-1", NOW, is_slow=False))
    collection.documents.append(_document("monitor-2", NOW, is_slow=True))

    result = asyncio.run(manager.count_slow_checks("monitor-1"))

    assert result == 1


def test_delete_for_monitor_sends_or_query_for_monitor_and_feeder_results():
    manager, collection = _manager()
    captured = {}

    async def fake_delete_many(query):
        captured["query"] = query
        return SimpleNamespace(deleted_count=0)

    collection.delete_many = fake_delete_many

    asyncio.run(manager.delete_for_monitor("monitor-1"))

    assert captured["query"]["$or"][0] == {"monitor_id": "monitor-1"}
    assert captured["query"]["$or"][1] == {"monitor_id": {"$regex": f"^{re.escape(feeder_result_id('monitor-1', ''))}"}}
