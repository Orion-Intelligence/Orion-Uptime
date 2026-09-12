from __future__ import annotations

from types import SimpleNamespace


class RecordingSlackClient:
    def __init__(self, *, error=None):
        self.calls = []
        self._error = error

    async def post(self, url, json):
        self.calls.append((url, json))
        if self._error is not None:
            raise self._error
        return SimpleNamespace(raise_for_status=lambda: None)
