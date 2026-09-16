from __future__ import annotations


def _factory(calls: list | None = None, sections: dict | None = None):
    async def factory(changed):
        if calls is not None:
            calls.append(changed)
        return dict(sections) if sections is not None else {"scope": "common"}

    return factory


def _changing_factory(values: list[dict]):
    remaining = list(values)

    async def factory(_changed):
        return remaining.pop(0) if remaining else dict(values[-1])

    return factory
