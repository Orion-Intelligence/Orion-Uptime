from __future__ import annotations

import difflib
import json
from collections.abc import Callable
from typing import Any

from orion.shared_models.exceptions import ValidationError

SUPPORTED_OPERATORS = {"$all", "$and", "$any", "$contains", "$deep_contains", "$each", "$ends_with", "$after", "$before", "$equals", "$exact", "$exists", "$from_request", "$gt", "$gte", "$index", "$item_contains", "$length", "$lt", "$lte", "$max_items", "$max_matches", "$min_items", "$min_matches", "$none", "$not", "$not_equals", "$not_in", "$one_of", "$or", "$partial", "$starts_with", "$type", "$where"}

UNRESOLVED = object()


def resolve_request_refs(expected: Any, request_body: Any) -> Any:
    """Replace {"$from_request": "<path>"} placeholders with values taken from the request body."""
    if isinstance(expected, dict):
        if "$from_request" in expected and set(expected) <= {"$from_request", "$after", "$before"}:
            value = _request_value(request_body, expected["$from_request"])
            return _sliced(value, expected.get("$after"), expected.get("$before"))
        return {key: resolve_request_refs(value, request_body) for key, value in expected.items()}
    if isinstance(expected, list):
        return [resolve_request_refs(value, request_body) for value in expected]
    return expected


def _sliced(value: Any, after: Any, before: Any) -> Any:
    if value is UNRESOLVED or (after is None and before is None):
        return value
    if not isinstance(value, str):
        return UNRESOLVED
    if isinstance(after, str) and after:
        position = value.find(after)
        if position >= 0:
            value = value[position + len(after):]
    if isinstance(before, str) and before:
        position = value.find(before)
        if position >= 0:
            value = value[:position]
    return value


def _request_value(request_body: Any, path: Any) -> Any:
    if not isinstance(path, str) or not path:
        return UNRESOLVED
    current = request_body
    for segment in path.split("."):
        if isinstance(current, dict) and segment in current:
            current = current[segment]
            continue
        if isinstance(current, list) and segment.lstrip("-").isdigit():
            index = int(segment)
            if -len(current) <= index < len(current):
                current = current[index]
                continue
        return UNRESOLVED
    return current


def validate_expected_json(expected: Any, request_body: Any = None) -> None:
    """Raise ValidationError when the expected JSON uses an unknown operator or an unresolvable request path."""
    problem = _first_problem(expected, request_body, "$")
    if problem is not None:
        raise ValidationError(problem)


def _first_problem(expected: Any, request_body: Any, path: str) -> str | None:
    if isinstance(expected, dict):
        if "$from_request" in expected:
            problem = _request_reference_problem(expected, request_body, path)
            if problem is not None:
                return problem
        for key, value in expected.items():
            if key.startswith("$") and key not in SUPPORTED_OPERATORS:
                return f"Unknown operator '{key}' at {path}.{_suggestion(key)}"
            problem = _first_problem(value, request_body, f"{path}.{key}" if not key.startswith("$") else f"{path}[{key}]")
            if problem is not None:
                return problem
        return None
    if isinstance(expected, list):
        for index, value in enumerate(expected):
            problem = _first_problem(value, request_body, f"{path}[{index}]")
            if problem is not None:
                return problem
    return None


def _request_reference_problem(expected: dict, request_body: Any, path: str) -> str | None:
    unexpected = set(expected) - {"$from_request", "$after", "$before"}
    if unexpected:
        return f"$from_request at {path} cannot be combined with {', '.join(sorted(unexpected))}."
    reference = expected["$from_request"]
    if not isinstance(reference, str) or not reference:
        return f"$from_request at {path} needs a non-empty path into the request body."
    if request_body is None:
        return None
    if _request_value(request_body, reference) is UNRESOLVED:
        available = ", ".join(sorted(request_body)) if isinstance(request_body, dict) else "the request body"
        return f"$from_request path '{reference}' at {path} is not present in the request body. Available keys: {available}."
    return None


def _suggestion(operator: str) -> str:
    close = difflib.get_close_matches(operator, sorted(SUPPORTED_OPERATORS), n=1, cutoff=0.6)
    return f" Did you mean '{close[0]}'?" if close else ""


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


def explain_mismatch(expected: Any, actual: Any) -> str:
    """Describe the first place the response stopped matching the expected JSON."""
    if _contains_unknown_operator(expected):
        return "The expected JSON uses an operator this system does not recognise."
    return _explain(expected, actual, "response") or "The response JSON did not match the configured expected JSON."


def _explain(expected: Any, actual: Any, path: str) -> str | None:
    if json_matches(expected, actual):
        return None

    if isinstance(expected, dict):
        operators = {key: value for key, value in expected.items() if key.startswith("$")}
        fields = {key: value for key, value in expected.items() if not key.startswith("$")}

        if operators and not _operators_match(operators, actual):
            return _explain_operators(operators, actual, path)
        if fields and not isinstance(actual, dict):
            return f"{path}: configured an object, response had {_describe(actual)}."
        for key, value in fields.items():
            if key not in actual:
                if _expects_absence(value):
                    continue
                return f"{path}.{key}: key is missing from the response."
            nested = _explain(value, actual[key], f"{path}.{key}")
            if nested is not None:
                return nested
        return None

    if isinstance(expected, list):
        if not isinstance(actual, list):
            return f"{path}: configured an array, response had {_describe(actual)}."
        if len(expected) > len(actual):
            return f"{path}: configured at least {len(expected)} items, response had {len(actual)}."
        for index, (expected_item, actual_item) in enumerate(zip(expected, actual, strict=False)):
            nested = _explain(expected_item, actual_item, f"{path}[{index}]")
            if nested is not None:
                return nested
        return None

    return f"{path}: configured {_describe(expected)}, response had {_describe(actual)}."


def _explain_operators(operators: dict[str, Any], actual: Any, path: str) -> str:
    for operator, expected in operators.items():
        if _operators_match({operator: expected}, actual):
            continue
        if operator in {"$all", "$each"} and isinstance(actual, list):
            for index, item in enumerate(actual):
                nested = _explain(expected, item, f"{path}[{index}]")
                if nested is not None:
                    return nested
        if operator in {"$where", "$item_contains", "$any"} and isinstance(actual, list):
            return f"{path}: no item matched {operator} {_describe(expected)} ({len(actual)} items checked)."
        return f"{path}: configured {operator} {_describe(expected)}, response had {_describe(actual)}."
    return f"{path}: did not match the expected JSON."


def _describe(value: Any, limit: int = 120) -> str:
    if value is UNRESOLVED:
        return "an unresolved request reference"
    try:
        text = json.dumps(value, default=str)
    except (TypeError, ValueError):
        text = str(value)
    return text if len(text) <= limit else f"{text[:limit]}…"


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
        "$deep_contains": _deep_contains,
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
        if operator in {"$from_request", "$after", "$before"}:
            return False
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
    if expected is UNRESOLVED:
        return False
    if isinstance(expected, str):
        return _deep_contains_text(actual, expected.casefold())
    if _contains(actual, expected):
        return True
    if isinstance(actual, dict):
        return any(_deep_contains(value, expected) for value in actual.values())
    if isinstance(actual, list):
        return any(_deep_contains(value, expected) for value in actual)
    return actual == expected


def _deep_contains_text(actual: Any, needle: str) -> bool:
    if isinstance(actual, str):
        return needle in actual.casefold()
    if isinstance(actual, dict):
        return any(needle in key.casefold() for key in actual if isinstance(key, str)) or any(_deep_contains_text(value, needle) for value in actual.values())
    if isinstance(actual, list):
        return any(_deep_contains_text(value, needle) for value in actual)
    if isinstance(actual, bool) or actual is None:
        return False
    if isinstance(actual, int | float):
        return needle in str(actual).casefold()
    return False


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
