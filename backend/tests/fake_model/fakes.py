from __future__ import annotations

from types import SimpleNamespace

from bson import ObjectId

from orion.services.mongo_manager.shared_model.db_orion_login_model import AuthProfileModel


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


class FakeCursor:
    def __init__(self, documents):
        self.documents = documents
        self.iterator = iter(documents)

    def sort(self, *_args):
        return self

    def __aiter__(self):
        self.iterator = iter(self.documents)
        return self

    async def __anext__(self):
        try:
            return next(self.iterator)
        except StopIteration:
            raise StopAsyncIteration from None


class FakeCollection:
    def __init__(self):
        self.documents = []

    async def find_one(self, query, _projection=None):
        for document in self.documents:
            if "name_key" in query and document.get("name_key") == query["name_key"]:
                return document
            if "_id" in query and document.get("_id") == query["_id"]:
                return document
        return None

    async def insert_one(self, document):
        inserted = {**document, "_id": ObjectId()}
        self.documents.append(inserted)
        return SimpleNamespace(inserted_id=inserted["_id"])

    def find(self, query=None, _projection=None):
        query = query or {}
        monitor_id = query.get("monitor_ids")
        documents = self.documents if monitor_id is None else [document for document in self.documents if monitor_id in document.get("monitor_ids", [])]
        return FakeCursor([document.copy() for document in documents])


class FakeMonitorService:
    async def list_monitors(self):
        return []


class FakeHttpClient:
    pass


class FakeTokenManager:
    def __init__(self, profiles: list[AuthProfileModel], token: str = "token-1"):
        self.auth_profile_service = SimpleNamespace(list_profile_models=self._list_profiles, get_profile_model=self._get_profile)
        self._profiles = profiles
        self._token = token
        self.refreshes = 0
        self.token_profile_ids: list[str] = []

    async def _list_profiles(self):
        return self._profiles

    async def _get_profile(self, profile_id: str):
        return next((profile for profile in self._profiles if profile.id == profile_id), None)

    async def get_token(self, profile_id: str, *, force_refresh: bool = False) -> str:
        self.token_profile_ids.append(profile_id)
        if force_refresh:
            self.refreshes += 1
            self._token = "token-2"
        return self._token
