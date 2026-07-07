import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# --- Конфигурация ---
# Токен бота, полученный от BotFather.
# Рекомендуется хранить его в переменной окружения (например, на Railway).
# Для локального тестирования можно временно указать токен здесь,
# но при деплое убедитесь, что BOT_TOKEN установлен как переменная окружения.
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8894416195:AAHZ4i0sTodK5AYKhqZfNIlrFBnlRTOiVR8")

# ID администратора (пока не используется в этом базовом примере, но может понадобиться)
ADMIN_ID = -7727345054

# Юзернейм вашего бота (важно, чтобы он совпадал с реальным юзернеймом бота в Telegram)
BOT_USERNAME = "imperia_webot" # Убедитесь, что это ваш actual юзернейм!

# --- Ссылки на картинки ---
# "Нижняя картинка" (с котом) будет отправлена как фото с подписью.
LOWER_IMAGE_URL = "https://boss-drop.vercel.app/share/BOSS_DROP_aHR0cHM6Ly9pLmliYi5jby9qUEpqVERCdi8xMDAwMDkzMzE2LmpwZw.jpg"

# "Верхняя картинка" (с бомбочкой) в оригинальном скриншоте - это скорее аватарка бота
# или часть верхней панели, а не изображение, отправляемое в сообщении.
# Поэтому в коде мы отправляем только текст для первого сообщения.
# Если вы хотите отправить её как отдельное сообщение-фото, дайте знать.

# --- Тексты сообщений для бота ---

# Первое сообщение (описание функционала бота)
FIRST_MESSAGE_TEXT = f"""
Что умеет этот бот?

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

# Второе сообщение (текст под картинкой с котом)
SECOND_MESSAGE_TEXT = """
Привет! 👋 Ты в NMines Bot — место, где время летит незаметно!
🎮 20+ бесплатных игр без скачивания, прямо в Telegram.
🤝 Соревнуйся с друзьями и прокачивай свои каналы и чаты. 🏆
"""

# --- Обработчики команд ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команду /start, отправляя приветственные сообщения."""
    chat_id = update.effective_chat.id

    # 1. Отправляем первое текстовое сообщение (описание функций бота)
    await context.bot.send_message(
        chat_id=chat_id,
        text=FIRST_MESSAGE_TEXT,
        parse_mode="HTML" # Используем HTML, чтобы обеспечить корректное отображение эмодзи
    )

    # 2. Подготавливаем кнопки для второго сообщения
    keyboard = [
        # Кнопка "Играть" пока просто подтверждает нажатие и добавляет текст.
        # В будущем здесь может быть переход к игре или WebApp.
        [InlineKeyboardButton("Играть 🕹️", callback_data="play_game")],
        # Кнопка "Добавить бота в чат" открывает ссылку для добавления бота в группу.
        [InlineKeyboardButton("Добавить бота в чат 💬", url=f"https://t.me/{BOT_USERNAME}?startgroup=true")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # 3. Отправляем второе сообщение с картинкой и кнопками
    await context.bot.send_photo(
        chat_id=chat_id,
        photo=LOWER_IMAGE_URL,
        caption=SECOND_MESSAGE_TEXT,
        reply_markup=reply_markup,
        parse_mode="HTML" # Используем HTML для текста под картинкой
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает нажатия на inline-кнопки."""
    query = update.callback_query
    await query.answer() # Обязательно подтверждаем нажатие кнопки

    if query.data == "play_game":
        # Пример обработки: редактируем подпись сообщения, добавляя фразу о начале игры.
        # В реальной игре здесь будет запуск самой игры или меню выбора игр.
        await query.edit_message_caption(
            caption=query.message.caption + "\n\n*Начинаем играть!* (Эта функция будет разработана позже)",
            reply_markup=query.message.reply_markup,
            parse_mode="Markdown" # Используем Markdown для жирного текста
        )
    # Здесь можно добавить обработку других кнопок, если они появятся.

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
