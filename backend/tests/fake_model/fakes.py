from __future__ import annotations


class FakePingProcess:
    def __init__(self, *, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self):
        return self._stdout, self._stderr


class FakePingSpawner:
    def __init__(self, process=None, calls: list | None = None):
        self._process = process or FakePingProcess()
        self._calls = calls if calls is not None else []

    async def __call__(self, *args, **_kwargs):
        self._calls.append(list(args))
        return self._process
