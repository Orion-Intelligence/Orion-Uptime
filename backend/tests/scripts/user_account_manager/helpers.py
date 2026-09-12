from __future__ import annotations

import asyncio
from types import SimpleNamespace

from orion.api.interactive.auth_manager.auth_manager import PasswordManager
from orion.api.interactive.user_account_manager.user_account_manager import UserManager
from orion.constants.constant import Collections
from tests.model.fakes import FakeCollection

PASSWORD = "password123"


def _manager():
    collection = FakeCollection()
    engine = SimpleNamespace(database={Collections.USERS: collection})
    manager = UserManager(engine, PasswordManager())
    return manager, collection


def _create(manager, username="alice", password=PASSWORD):
    return asyncio.run(manager.create_user(username, password))
