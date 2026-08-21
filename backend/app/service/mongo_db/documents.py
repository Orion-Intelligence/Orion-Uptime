from typing import Any


def with_string_id(document: dict[str, Any]) -> dict[str, Any]:
    document["id"] = str(document.pop("_id"))
    return document
