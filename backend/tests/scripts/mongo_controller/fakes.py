from __future__ import annotations

from pymongo.errors import OperationFailure

from orion.constants.constant import Collections


class FakeMotorClient:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeConnectedEngine:
    def __init__(self):
        self.client = FakeMotorClient()


class FakeIndexCollection:
    def __init__(self, fail_once_names=None):
        self.created = []
        self.dropped = []
        self._fail_once_names = set(fail_once_names or [])

    async def create_index(self, *args, **kwargs):
        name = kwargs.get("name")
        if name in self._fail_once_names:
            self._fail_once_names.discard(name)
            raise OperationFailure("index options conflict")
        self.created.append((args, kwargs))
        return name

    async def drop_index(self, name):
        self.dropped.append(name)


class FakeIndexDatabase:
    def __init__(self, fail_once_names=None):
        self._fail_once_names = fail_once_names or []
        self.collections: dict[str, FakeIndexCollection] = {}

    def __getitem__(self, name):
        if name not in self.collections:
            names = self._fail_once_names if name == Collections.MONITOR_RESULTS else None
            self.collections[name] = FakeIndexCollection(names)
        return self.collections[name]


class FakeIndexEngine:
    def __init__(self, fail_once_names=None):
        self.database = FakeIndexDatabase(fail_once_names)
