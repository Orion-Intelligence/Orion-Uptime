import os

from dotenv import load_dotenv

from orion.api.interactive.auth_manager.auth_manager import password_service
from orion.api.interactive.user_account_manager.user_account_manager import UserManager
from orion.services.mongo_manager.mongo_controller import db_manager


class AdminSeeder:
    async def run(self) -> None:
        load_dotenv()
        default_admin_username = os.environ["DEFAULT_ADMIN_USERNAME"]
        default_admin_password = os.environ["DEFAULT_ADMIN_PASSWORD"]
        service = UserManager(db_manager.get_engine(), password_service)
        await service.ensure_default_admin(default_admin_username, default_admin_password)
