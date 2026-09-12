from __future__ import annotations


def _factory(calls: list | None = None):
    async def factory(changed, include_admin):
        if calls is not None:
            calls.append((changed, include_admin))
        return {"scope": "common"}, ({"scope": "admin"} if include_admin else {})

    return factory
