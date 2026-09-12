from __future__ import annotations

from tests.model.fakes import FakeCollection


class _DisappearingCollection(FakeCollection):
    async def update_one(self, query, update):
        result = await super().update_one(query, update)
        self.documents.clear()
        return result
