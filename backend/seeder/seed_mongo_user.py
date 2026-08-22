import os

from dotenv import load_dotenv

from orion.services.mongo_manager.mongo_controller import db_manager


class MongoUserSeeder:
    async def run(self) -> None:
        load_dotenv()
        username = os.environ["MONGO_APP_USERNAME"]
        password = os.environ["MONGO_APP_PASSWORD"]
        database_name = os.environ["DATABASE_NAME"]
        database = db_manager.engine.client[database_name]
        roles = [{"role": "readWrite", "db": database_name}]
        info = await database.command("usersInfo", username)
        if info.get("users"):
            await database.command("updateUser", username, pwd=password, roles=roles)
        else:
            await database.command("createUser", username, pwd=password, roles=roles)
