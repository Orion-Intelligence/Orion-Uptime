from __future__ import annotations


class _FakeWriter:
    def close(self):
        return None

    async def wait_closed(self):
        return None


class _TimeoutProcess:
    returncode = None

    async def communicate(self):
        raise TimeoutError
