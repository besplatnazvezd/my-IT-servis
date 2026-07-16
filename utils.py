import asyncio
from aiogram.types import Message
from aiogram import Bot

async def delete_message_later(bot: Bot, chat_id: int, message_id: int, delay: int = 10):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except:
        pass

async def delete_previous_bot_messages(bot: Bot, message: Message, keep_last: int = 1):
    # Удаляем сообщения бота, отправленные ранее в этом чате (можно хранить в БД, но упростим)
    # Этот функционал можно реализовать через хранение message_id в состоянии или БД.
    # Для простоты будем удалять только текущее сообщение через задержку.
    pass
