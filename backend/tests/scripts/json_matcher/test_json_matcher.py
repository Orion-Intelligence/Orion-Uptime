from __future__ import annotations

import pytest

from orion.api.interactive.api_monitor_manager.json_matcher import json_matches


@pytest.mark.parametrize(
    "expected,actual,result",
    [
        ({"a": 1, "b": "x"}, {"a": 1, "b": "x", "c": 9}, True),
        ({"a": 1}, {"a": 2}, False),
        ({"a": {"b": 1}}, {"a": {"b": 1}}, True),
        ([1, 2], [1, 2, 3], True),
        ([1, 2, 3], [1, 2], False),
        (5, 5, True),
        ("x", "y", False),
        ({"missing": 1}, {"a": 1}, False),
        ({"a": 1}, "not-a-dict", False),
        ({"$unknown": 1}, {"anything": 1}, False),
        ({"value": {"$equals": 10}}, {"value": 10}, True),
        ({"value": {"$exact": 10}}, {"value": 11}, False),
        ({"value": {"$not_equals": 10}}, {"value": 11}, True),
        ({"value": {"$exists": True}}, {"value": None}, True),
        ({"value": {"$exists": True}}, {}, False),
        ({"maybe": {"$exists": False}}, {"other": 1}, True),
        ({"value": {"$type": "string"}}, {"value": "hi"}, True),
        ({"value": {"$type": "integer"}}, {"value": True}, False),
        ({"value": {"$type": "number"}}, {"value": 1.5}, True),
        ({"value": {"$type": "array"}}, {"value": [1]}, True),
        ({"value": {"$type": "null"}}, {"value": None}, True),
        ({"value": {"$type": "object"}}, {"value": {}}, True),
        ({"value": {"$type": "boolean"}}, {"value": False}, True),
        ({"value": {"$type": "bogus"}}, {"value": 1}, False),
        ({"value": {"$contains": "ell"}}, {"value": "hello"}, True),
        ({"value": {"$starts_with": "he"}}, {"value": "hello"}, True),
        ({"value": {"$ends_with": "lo"}}, {"value": "hello"}, True),
        ({"value": {"$gt": 5}}, {"value": 6}, True),
        ({"value": {"$gte": 5}}, {"value": 5}, True),
        ({"value": {"$lt": 5}}, {"value": 4}, True),
        ({"value": {"$lte": 5}}, {"value": 6}, False),
        ({"value": {"$gt": 5}}, {"value": "x"}, False),
        ({"value": {"$length": 3}}, {"value": [1, 2, 3]}, True),
        ({"value": {"$min_items": 2}}, {"value": [1, 2, 3]}, True),
        ({"value": {"$max_items": 2}}, {"value": [1, 2, 3]}, False),
        ({"value": {"$one_of": [1, 2, 3]}}, {"value": 2}, True),
        ({"value": {"$not_in": [1, 2]}}, {"value": 9}, True),
        ({"value": {"$and": [{"$gt": 1}, {"$lt": 10}]}}, {"value": 5}, True),
        ({"value": {"$or": [{"$gt": 100}, {"$lt": 10}]}}, {"value": 5}, True),
        ({"value": {"$not": {"$gt": 100}}}, {"value": 5}, True),
        ({"items": {"$any": {"$gt": 5}}}, {"items": [1, 2, 9]}, True),
        ({"items": {"$all": {"$gt": 0}}}, {"items": [1, 2, 3]}, True),
        ({"items": {"$none": {"$gt": 5}}}, {"items": [1, 2, 3]}, True),
        ({"items": {"$index": {"0": 1}}}, {"items": [1, 2]}, True),
        ({"items": {"$index": {"5": 1}}}, {"items": [1, 2]}, False),
        ({"value": {"$partial": {"a": 1}}}, {"value": {"a": 1, "b": 2}}, True),
    ],
)
def test_json_matches(expected, actual, result):
    assert json_matches(expected, actual) is result


def test_where_and_item_contains_with_match_counts():
    expected = {"items": {"$where": {"active": True}, "$min_matches": 2}}
    actual = {"items": [{"active": True}, {"active": True}, {"active": False}]}
    assert json_matches(expected, actual) is True

    too_few = {"items": {"$where": {"active": True}, "$min_matches": 3}}
    assert json_matches(too_few, actual) is False

    capped = {"items": {"$where": {"active": True}, "$max_matches": 1}}
    assert json_matches(capped, actual) is False


def test_item_contains_matches_nested_values():
    expected = {"items": {"$item_contains": "target"}}
    actual = {"items": [{"nested": {"deep": "target"}}]}
    assert json_matches(expected, actual) is True
