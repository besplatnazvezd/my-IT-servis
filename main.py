import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from handlers import router as handlers_router
from admin import router as admin_router
from games import router as games_router

logging.basicConfig(level=logging.INFO)

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(handlers_router)
    dp.include_router(admin_router)
    dp.include_router(games_router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
