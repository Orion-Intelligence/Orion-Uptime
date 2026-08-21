import asyncio

from app.seeder.seed_admin import AdminSeeder
from app.seeder.seed_mongo_user import MongoUserSeeder
from app.service.mongo_db.mongo_controller import db_manager


async def seed() -> None:
    await db_manager.connect()

    try:
        await MongoUserSeeder().run()
        await AdminSeeder().run()
    finally:
        await db_manager.disconnect()

if __name__ == "__main__":
    asyncio.run(seed())
