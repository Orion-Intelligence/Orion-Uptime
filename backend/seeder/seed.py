import asyncio

from orion.services.mongo_manager.mongo_controller import db_manager
from seeder.seed_admin import AdminSeeder
from seeder.seed_mongo_user import MongoUserSeeder


async def seed() -> None:
    await db_manager.connect()

    try:
        await MongoUserSeeder().run()
        await AdminSeeder().run()
    finally:
        await db_manager.disconnect()


if __name__ == "__main__":
    asyncio.run(seed())
