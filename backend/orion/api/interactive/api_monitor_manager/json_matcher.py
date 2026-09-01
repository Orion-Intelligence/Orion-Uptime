from __future__ import annotations

from collections.abc import Callable
from typing import Any

SUPPORTED_OPERATORS = {"$all", "$and", "$any", "$contains", "$each", "$ends_with", "$equals", "$exact", "$exists", "$gt", "$gte", "$index", "$item_contains", "$length", "$lt", "$lte", "$max_items", "$max_matches", "$min_items", "$min_matches", "$none", "$not", "$not_equals", "$not_in", "$one_of", "$or", "$partial", "$starts_with", "$type", "$where"}


def json_matches(expected: Any, actual: Any) -> bool:
    """Match literal JSON partially, with optional safe assertion operators."""
    if _contains_unknown_operator(expected):
        return False

    if isinstance(expected, dict):
        operators = {key: value for key, value in expected.items() if key.startswith("$")}
        fields = {key: value for key, value in expected.items() if not key.startswith("$")}

        if operators and not _operators_match(operators, actual):
            return False
        if not fields:
            return True
        if not isinstance(actual, dict):
            return False

        for key, expected_value in fields.items():
            if key not in actual:
                if _expects_absence(expected_value):
                    continue
                return False
            if not json_matches(expected_value, actual[key]):
                return False
        return True

    if isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) > len(actual):
            return False
        return all(json_matches(expected_item, actual_item) for expected_item, actual_item in zip(expected, actual, strict=False))

    return expected == actual


def _contains_unknown_operator(expected: Any) -> bool:
    if isinstance(expected, dict):
        return any((key.startswith("$") and key not in SUPPORTED_OPERATORS) or _contains_unknown_operator(value) for key, value in expected.items())
    if isinstance(expected, list):
        return any(_contains_unknown_operator(value) for value in expected)
    return False


def _operators_match(operators: dict[str, Any], actual: Any) -> bool:
    if any(operator not in SUPPORTED_OPERATORS for operator in operators):
        return False

    item_predicate = _item_predicate(operators)
    item_matches = _matching_item_count(actual, item_predicate) if item_predicate is not None else None

    checks: dict[str, Callable[[Any, Any], bool]] = {
        "$equals": lambda value, expected: value == expected,
        "$exact": lambda value, expected: value == expected,
        "$not_equals": lambda value, expected: value != expected,
        "$partial": lambda value, expected: json_matches(expected, value),
        "$type": _has_type,
        "$contains": _contains,
        "$starts_with": lambda value, expected: isinstance(value, str) and isinstance(expected, str) and value.startswith(expected),
        "$ends_with": lambda value, expected: isinstance(value, str) and isinstance(expected, str) and value.endswith(expected),
        "$gt": lambda value, expected: _number_comparison(value, expected, lambda left, right: left > right),
        "$gte": lambda value, expected: _number_comparison(value, expected, lambda left, right: left >= right),
        "$lt": lambda value, expected: _number_comparison(value, expected, lambda left, right: left < right),
        "$lte": lambda value, expected: _number_comparison(value, expected, lambda left, right: left <= right),
        "$length": _length_matches,
        "$min_items": lambda value, expected: _length_comparison(value, expected, lambda left, right: left >= right),
        "$max_items": lambda value, expected: _length_comparison(value, expected, lambda left, right: left <= right),
        "$one_of": lambda value, expected: isinstance(expected, list) and any(value == candidate for candidate in expected),
        "$not_in": lambda value, expected: isinstance(expected, list) and all(value != candidate for candidate in expected),
        "$and": lambda value, expected: isinstance(expected, list) and all(json_matches(assertion, value) for assertion in expected),
        "$or": lambda value, expected: isinstance(expected, list) and any(json_matches(assertion, value) for assertion in expected),
        "$not": lambda value, expected: not json_matches(expected, value),
        "$any": lambda value, expected: isinstance(value, list) and any(json_matches(expected, item) for item in value),
        "$all": lambda value, expected: isinstance(value, list) and all(json_matches(expected, item) for item in value),
        "$each": lambda value, expected: isinstance(value, list) and all(json_matches(expected, item) for item in value),
        "$none": lambda value, expected: isinstance(value, list) and all(not json_matches(expected, item) for item in value),
        "$index": _indices_match,
    }

    for operator, expected in operators.items():
        if operator == "$exists":
            if not isinstance(expected, bool) or not expected:
                return False
        elif operator in {"$where", "$item_contains"}:
            if item_matches is None:
                return False
            if "$min_matches" not in operators and "$max_matches" not in operators and item_matches < 1:
                return False
        elif operator == "$min_matches":
            if item_matches is None or not _valid_count(expected) or item_matches < expected:
                return False
        elif operator == "$max_matches":
            if item_matches is None or not _valid_count(expected) or item_matches > expected:
                return False
        elif operator in checks and not checks[operator](actual, expected):
            return False
    return True


def _expects_absence(expected: Any) -> bool:
    return isinstance(expected, dict) and expected.get("$exists") is False


def _has_type(actual: Any, expected: Any) -> bool:
    if not isinstance(expected, str):
        return False
    type_checks: dict[str, Callable[[Any], bool]] = {"array": lambda value: isinstance(value, list), "boolean": lambda value: isinstance(value, bool), "integer": lambda value: isinstance(value, int) and not isinstance(value, bool), "null": lambda value: value is None, "number": _is_number, "object": lambda value: isinstance(value, dict), "string": lambda value: isinstance(value, str)}
    checker = type_checks.get(expected.lower())
    return checker(actual) if checker is not None else False


def _contains(actual: Any, expected: Any) -> bool:
    if isinstance(actual, str) and isinstance(expected, str):
        return expected in actual
    if isinstance(actual, list):
        return any(_contains(item, expected) if isinstance(item, str | list | dict) else json_matches(expected, item) for item in actual)
    if isinstance(actual, dict):
        if isinstance(expected, str):
            return expected in actual
        if isinstance(expected, dict):
            return json_matches(expected, actual)
    return False


def _deep_contains(actual: Any, expected: Any) -> bool:
    if _contains(actual, expected):
        return True
    if isinstance(actual, dict):
        return any(_deep_contains(value, expected) for value in actual.values())
    if isinstance(actual, list):
        return any(_deep_contains(value, expected) for value in actual)
    return actual == expected


def _item_predicate(operators: dict[str, Any]) -> Callable[[Any], bool] | None:
    where = operators.get("$where")
    contains = operators.get("$item_contains")
    if "$where" in operators and "$item_contains" in operators:
        return lambda item: json_matches(where, item) and _deep_contains(item, contains)
    if "$where" in operators:
        return lambda item: json_matches(where, item)
    if "$item_contains" in operators:
        return lambda item: _deep_contains(item, contains)
    return None


def _matching_item_count(actual: Any, predicate: Callable[[Any], bool] | None) -> int | None:
    if not isinstance(actual, list) or predicate is None:
        return None
    return sum(1 for item in actual if predicate(item))


def _indices_match(actual: Any, expected: Any) -> bool:
    if not isinstance(actual, list) or not isinstance(expected, dict):
        return False
    for raw_index, assertion in expected.items():
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            return False
        if str(index) != str(raw_index) or not -len(actual) <= index < len(actual):
            return False
        if not json_matches(assertion, actual[index]):
            return False
    return True


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _number_comparison(actual: Any, expected: Any, comparison: Callable[[int | float, int | float], bool]) -> bool:
    return _is_number(actual) and _is_number(expected) and comparison(actual, expected)


def _length_matches(actual: Any, expected: Any) -> bool:
    if not isinstance(actual, str | list | dict):
        return False
    length = len(actual)
    if _valid_count(expected):
        return length == expected
    return isinstance(expected, dict) and json_matches(expected, length)


def _length_comparison(actual: Any, expected: Any, comparison: Callable[[int, int], bool]) -> bool:
    return isinstance(actual, str | list | dict) and _valid_count(expected) and comparison(len(actual), expected)


def _valid_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
