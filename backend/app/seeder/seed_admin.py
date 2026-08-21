import os

from dotenv import load_dotenv

from app.modules.auth_manager.auth_manager import password_service
from app.modules.user_account_manager.user_account_manager import UserManager
from app.service.mongo_db.mongo_controller import db_manager


class AdminSeeder:
    async def run(self) -> None:
        load_dotenv()
        default_admin_username = os.environ["DEFAULT_ADMIN_USERNAME"]
        default_admin_password = os.environ["DEFAULT_ADMIN_PASSWORD"]
        service = UserManager(db_manager.get_engine(), password_service)
        await service.ensure_default_admin(
            default_admin_username,
            default_admin_password,
        )
