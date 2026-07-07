import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8894416195:AAHZ4i0sTodK5AYKhqZfNIlrFBnlRTOiVR8")

# ID администратора (пока не используется в этом базовом примере, но может понадобиться)
ADMIN_ID = -7727345054

BOT_USERNAME = "imperia_webot" 

BOTFATHER_PROFILE_PICTURE_URL = "https://i.ibb.co/qMQdGHqD/IMG-20260707-233514-557.jpg"

START_MESSAGE_IMAGE_URL = "https://i.ibb.co/jPJjTDBv/1000093316.jpg"

# --- Тексты сообщений для бота ---

# ЭТОТ ТЕКСТ ПРЕДНАЗНАЧЕН ДЛЯ УСТАНОВКИ В BotFather В РАЗДЕЛЕ "About" (ОПИСАНИЕ БОТА).
# Бот его сам не отправляет в чат.
BOTFATHER_ABOUT_TEXT = f"""
💥💣 Популярная игра Минёр в Telegram

✨ Список наших самых популярных игр:
💣 Мины
💰 Золото Запада
🐸 Frog Time
🎲 Башня
🎲 Кубик
🎲 Кости
🏀 Баскетбол
🎳 Боулинг
⚡️ И другие...

⚡️ Работает в личных сообщениях, группах и инлайн
@{BOT_USERNAME}

⬇️ Жми старт и начинай играть ⬇️
"""

# ЭТОТ ТЕКСТ БУДЕТ ОТПРАВЛЕН БОТОМ В ОТВЕТ НА КОМАНДУ /start (под картинкой с котом).
START_MESSAGE_CAPTION = """
Привет! 👋 Ты в NMines Bot — место, где время летит незаметно!
🎮 20+ бесплатных игр без скачивания, прямо в Telegram.
🤝 Соревнуйся с друзьями и прокачивай свои каналы и чаты. 🏆
"""
# Меню выбора игр
GAME_MENU_TEXT = """
🎮 ДАВАЙ НАЧНЕМ ИГРАТЬ!

💰 Баланс: 5 000 ncoin
💎 Ставка: 100 ncoin

👇 Выбери игру и начинай!
"""

# --- Обработчики команд ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команду /start.
    Отправляет сообщение с картинкой-котом и кнопками.
    """
    chat_id = update.effective_chat.id

    # Подготавливаем кнопки для сообщения
    keyboard = [
        [InlineKeyboardButton("Играть 🕹️", callback_data="play_game")],
        [InlineKeyboardButton("Добавить бота в чат 💬", url=f"https://t.me/{BOT_USERNAME}?startgroup=true")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Отправляем сообщение с картинкой-котом и кнопками
    await context.bot.send_photo(
        chat_id=chat_id,
        photo=START_MESSAGE_IMAGE_URL, # Используем картинку с котом
        caption=START_MESSAGE_CAPTION, # Используем текст для ответа на /start
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
          query = update.callback_query
    await query.answer()
if query.data == "play_game":
    # Создаем кнопки меню игр
    keyboard = [
        [
            InlineKeyboardButton("🏀", callback_data="game_basket"),
            InlineKeyboardButton("⚽", callback_data="game_ball"),
            InlineKeyboardButton("🎯", callback_data="game_darts"),
            InlineKeyboardButton("🎳", callback_data="game_bowling"),
            InlineKeyboardButton("🎲", callback_data="game_dice"),
            InlineKeyboardButton("🎰", callback_data="game_slots"),
        ],
        [
            InlineKeyboardButton("🚀 Быстрые", callback_data="fast"),
            InlineKeyboardButton("🕹 Режимы", callback_data="modes"),
        ],
        [
            InlineKeyboardButton("🕹 Играть в WEB", url="https://..."),
            InlineKeyboardButton("🛠 Изменить ставку", callback_data="change_bet"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
        # Отправляем сообщение с играми
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=GAME_MENU_TEXT,
            reply_markup=reply_markup,
            parse_mode="HTML"
             )
        # --- Основная функция для запуска бота ---
def main() -> None:
    """Запускает бота."""
    # Создаем объект Application и передаем токен бота.
    application = Application.builder().token(BOT_TOKEN).build()

    # Регистрируем обработчики команд и callback-запросов
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(button_handler))

    # Запускаем бота в режиме polling (постоянный опрос сервера Telegram на наличие обновлений)
    # allowed_updates=Update.ALL_TYPES - рекомендуется для Railway, чтобы избежать проблем с определением webhook'ов.
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
