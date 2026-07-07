import re
import logging
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# Включаем логирование ошибок в консоль
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# === КОНСТАНТЫ ===
BOT_TOKEN = "8894416195:AAHZ4i0sTodK5AYKhqZfNIlrFBnlRTOiVR8"
ADMIN_ID = 7727345054
IMAGE_URL = "https://i.ibb.co/jPJjTDBv/1000093316.jpg"

# Данные Supabase
SUPABASE_URL = "https://gyjwzifhfxrojwjioapp.supabase.co/rest/v1/"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd5and6aWZoZnhyb2p3amlvYXBwIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MzQxNDcxMywiZXhwIjoyMDk4OTkwNzEzfQ.xjicAYNFaI9iTA3PlHvM2L_10r38gJSIlwmopy_3O70"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# Внутреннее хранилище состояний ввода (например, изменение ставки)
user_states = {}
# Локальная база данных на случай сбоя Supabase
LOCAL_DB = {}

# === ИНТЕГРАЦИЯ С БАЗОЙ ДАННЫХ ===

async def db_get_or_create(tg_id: int, username: str) -> dict:
    """Получает профиль игрока из Supabase или создает новый."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SUPABASE_URL}users?tg_id=eq.{tg_id}",
                headers=HEADERS,
                timeout=5.0
            )
            users = response.json()
            if users and len(users) > 0:
                return users[0]
            
            # Если пользователя нет — создаем его
            new_user = {
                "tg_id": tg_id,
                "username": username or "Игрок",
                "ncoin": 10000,
                "nmp": 0,
                "current_bet": 10
            }
            create_response = await client.post(
                f"{SUPABASE_URL}users",
                json=new_user,
                headers=HEADERS,
                timeout=5.0
            )
            created = create_response.json()
            if created and len(created) > 0:
                return created[0]
            return new_user
    except Exception as e:
        logging.error(f"Ошибка Supabase (get_or_create), переключаюсь на локальную память: {e}")
        if tg_id not in LOCAL_DB:
            LOCAL_DB[tg_id] = {
                "tg_id": tg_id,
                "username": username or "Игрок",
                "ncoin": 10000,
                "nmp": 0,
                "current_bet": 10
            }
        return LOCAL_DB[tg_id]

async def db_update(tg_id: int, updates: dict) -> dict:
    """Обновляет баланс или ставку пользователя."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{SUPABASE_URL}users?tg_id=eq.{tg_id}",
                json=updates,
                headers=HEADERS,
                timeout=5.0
            )
            users = response.json()
            if users and len(users) > 0:
                return users[0]
            return {}
    except Exception as e:
        logging.error(f"Ошибка Supabase (update), обновляю локально: {e}")
        if tg_id in LOCAL_DB:
            LOCAL_DB[tg_id].update(updates)
            return LOCAL_DB[tg_id]
        return {}


# === КЛАВИАТУРЫ ===

def get_start_keyboard(bot_username: str) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("Играть 🕹️", callback_data="play_game")],
        [InlineKeyboardButton("➕ Добавить бота в чат 💬", url=f"https://t.me/{bot_username}?startgroup=true")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_game_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("🏀", callback_data="game_basket"),
            InlineKeyboardButton("⚽", callback_data="game_ball"),
            InlineKeyboardButton("🎯", callback_data="game_darts"),
            InlineKeyboardButton("🎳", callback_data="game_bowling"),
            InlineKeyboardButton("🎲", callback_data="game_dice"),
            InlineKeyboardButton("🎰", callback_data="game_slots")
        ],
        [
            InlineKeyboardButton("🚀 Быстрые", callback_data="btn_fast"),
            InlineKeyboardButton("Режимы 💣", callback_data="btn_modes")
        ],
        [
            InlineKeyboardButton("🕹️ Играть в WEB", web_app=WebAppInfo(url="https://google.com")) # Замени на свой мини-сайт
        ],
        [
            InlineKeyboardButton("✍️ Изменить ставку", callback_data="change_bet")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


# === ОБРАБОТЧИКИ КОМАНД ===

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await db_get_or_create(user.id, user.username)
    
    bot_info = await context.bot.get_me()
    
    caption = (
        "<b>Привет! 👋 Ты в Мины Бот — место, где время летит незаметно!</b>\n\n"
        "🎮 20+ бесплатных игр без скачивания, прямо в Telegram.\n\n"
        "Соревнуйся с друзьями и прокачивай свои каналы и чаты. 🏆"
    )
    
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=IMAGE_URL,
        caption=caption,
        reply_markup=get_start_keyboard(bot_info.username),
        parse_mode="HTML"
    )

# === ОБРАБОТКА НАЖАТИЙ НА КНОПКИ ===

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_data = await db_get_or_create(user_id, query.from_user.username)
    
    # Кнопка "Играть 🕹️"
    if query.data == "play_game":
        text = (
            "<b>🎮 ДАВАЙ НАЧНЕМ ИГРАТЬ!</b>\n\n"
            "💰 <b>Баланс:</b>\n"
            f"└ 💎 <code>{user_data['ncoin']} ncoin</code>\n"
            f"└ ⭐ <code>{user_data['nmp']} nmp</code>\n\n"
            f"💵 <b>Ставка:</b> <code>{user_data['current_bet']} ncoin</code>\n\n"
            "👇 Выбери игру и начинай!"
        )
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=text,
            reply_markup=get_game_keyboard(),
            parse_mode="HTML"
        )
        
    # Кнопка "Изменить ставку"
    elif query.data == "change_bet":
        user_states[user_id] = "awaiting_bet"
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="✍️ <b>Введите новую сумму ставки в ncoin:</b>",
            parse_mode="HTML"
        )
        
    # Игры (Слоты 🎰 и Кости 🎲)
    elif query.data in ["game_slots", "game_dice"]:
        bet = user_data["current_bet"]
        balance = user_data["ncoin"]
        
        if balance < bet:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="❌ <b>У вас недостаточно ncoin для этой ставки!</b> Пожалуйста, уменьшите ставку.",
                parse_mode="HTML"
            )
            return
            
        # Списываем ставку
        balance -= bet
        await db_update(user_id, {"ncoin": balance})
        
        # Определяем эмодзи игры
        emoji = "🎰" if query.data == "game_slots" else "🎲"
        
        # Запускаем анимацию
        dice_msg = await context.bot.send_dice(chat_id=query.message.chat_id, emoji=emoji)
        value = dice_msg.dice.value
        
        # Рассчитываем выигрыш
        win_multiplier = 0
        if query.data == "game_slots":
            # Выигрышные комбинации на слотах (1 - джекпот, 22, 43, 64)
            if value in [1, 22, 43, 64]:
                win_multiplier = 10
            elif value in [16, 32, 48]:
                win_multiplier = 3
        else:
            # Выигрыш на костях (если выпало больше 4)
            if value >= 4:
                win_multiplier = 2
                
        if win_multiplier > 0:
            reward = bet * win_multiplier
            balance += reward
            await db_update(user_id, {"ncoin": balance})
            result_text = f"🎉 <b>Вы выиграли {reward} ncoin! (Множитель x{win_multiplier})</b>"
        else:
            result_text = "😔 <b>Ставка не сыграла. Попробуйте еще раз!</b>"
            
        # Отправляем результат с обновленным балансом
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=(
                f"{result_text}\n\n"
                f"💰 <b>Ваш новый баланс:</b> <code>{balance} ncoin</code>"
            ),
            parse_mode="HTML"
        )
        
    # Заглушки на другие кнопки
    elif query.data in ["btn_fast", "btn_modes", "game_basket", "game_ball", "game_darts", "game_bowling"]:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="⚙️ Этот режим игры сейчас находится в разработке.",
            parse_mode="HTML"
        )

# === ОБРАБОТКА ТЕКСТА (Ввод новой ставки) ===

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    state = user_states.get(user_id)
    
    if state == "awaiting_bet":
        user_states[user_id] = None # Сбрасываем статус
        
        clean_text = re.sub(r'[^\d]', '', update.message.text)
        if not clean_text:
            await update.message.reply_text("❌ Пожалуйста, введите корректное число!")
            return
            
        new_bet = int(clean_text)
        if new_bet <= 0:
            await update.message.reply_text("❌ Ставка должна быть больше 0!")
            return
            
        # Обновляем ставку в БД
        await db_update(user_id, {"current_bet": new_bet})
        
        # Получаем обновленного пользователя
        user_data = await db_get_or_create(user_id, update.effective_user.username)
        
        text = (
            "✅ <b>Ставка успешно изменена!</b>\n\n"
            f"💵 <b>Текущая ставка:</b> <code>{user_data['current_bet']} ncoin</code>\n"
            f"💎 <b>Баланс:</b> <code>{user_data['ncoin']} ncoin</code>"
        )
        await update.message.reply_text(text, reply_markup=get_game_keyboard(), parse_mode="HTML")

# === ЗАПУСК ===

def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    print("Бот успешно запущен на Railway!")
    application.run_polling()

if __name__ == '__main__':
    main()
