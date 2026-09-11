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

    @staticmethod
    def _matches(document, query):
        for key, condition in query.items():
            value = document.get(key)
            if isinstance(condition, dict) and "$ne" in condition:
                if value == condition["$ne"]:
                    return False
            elif key == "monitor_ids":
                if condition not in (value or []):
                    return False
            elif value != condition:
                return False
        return True

    async def find_one(self, query, _projection=None):
        for document in self.documents:
            if self._matches(document, query):
                return document.copy()
        return None

    async def insert_one(self, document):
        inserted = {**document, "_id": ObjectId()}
        self.documents.append(inserted)
        return SimpleNamespace(inserted_id=inserted["_id"])

    async def update_one(self, query, update):
        for document in self.documents:
            if self._matches(document, query):
                document.update(update.get("$set", {}))
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def delete_one(self, query):
        for index, document in enumerate(self.documents):
            if self._matches(document, query):
                del self.documents[index]
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)

    def find(self, query=None, _projection=None):
        query = query or {}
        documents = [document for document in self.documents if self._matches(document, query)]
        return FakeCursor([document.copy() for document in documents])


class FakeMonitorService:
    def __init__(self, monitors: list | None = None):
        self._monitors = monitors or []

    async def list_monitors(self):
        return self._monitors


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
