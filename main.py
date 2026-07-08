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

# Внутреннее хранилище состояний ввода
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
            InlineKeyboardButton("⚽", callback_data="game_football"),
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
            InlineKeyboardButton("🕹️ Играть в WEB", web_app=WebAppInfo(url="https://google.com"))
        ],
        [
            InlineKeyboardButton("✍️ Изменить ставку", callback_data="change_bet")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Клавиатура выбора исхода в баскетболе
def get_basket_choice_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🏀 Попадание - x2.4", callback_data="basket_bet_hit")],
        [InlineKeyboardButton("🙈 Мимо - x1.6", callback_data="basket_bet_miss")],
        [InlineKeyboardButton("◀️ назад", callback_data="play_game")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Клавиатура после завершения игры в баскетбол
def get_basket_replay_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("⬇️ 5 💰", callback_data="basket_setbet_5"),
            InlineKeyboardButton("10 💰", callback_data="basket_setbet_10"),
            InlineKeyboardButton("⬆️ 20 💰", callback_data="basket_setbet_20")
        ],
        [
            InlineKeyboardButton("Повторить игру 🔄", callback_data="game_basket")
        ],
        [
            InlineKeyboardButton("◀️ Главное меню", callback_data="play_game")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Клавиатура выбора исхода в футболе
def get_football_choice_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("⚽ Гол - x1.6", callback_data="football_bet_hit")],
        [InlineKeyboardButton("🥅 Мимо - x2.4", callback_data="football_bet_miss")],
        [InlineKeyboardButton("◀️ назад", callback_data="play_game")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Клавиатура после завершения игры в футбол
def get_football_replay_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("⬇️ 5 💰", callback_data="football_setbet_5"),
            InlineKeyboardButton("10 💰", callback_data="football_setbet_10"),
            InlineKeyboardButton("⬆️ 20 💰", callback_data="football_setbet_20")
        ],
        [
            InlineKeyboardButton("Повторить игру 🔄", callback_data="game_football")
        ],
        [
            InlineKeyboardButton("◀️ Главное меню", callback_data="play_game")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


# === ОБРАБОТЧИКИ КОМАНД ===

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await db_get_or_create(user.id, user.username)
    bot_info = await context.bot.get_me()
    
    caption = f"""<b>Привет! 👋 Ты в Мины Бот — место, где время летит незаметно!</b>

🎮 20+ бесплатных игр без скачивания, прямо в Telegram.

Соревнуйся с друзьями и прокачивай свои каналы и чаты. 🏆"""
    
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
    username = query.from_user.username or query.from_user.first_name or "Игрок"
    user_data = await db_get_or_create(user_id, query.from_user.username)
    
    # Кнопка "Играть 🕹️"
    if query.data == "play_game":
        text = f"""<b>🎮 ДАВАЙ НАЧНЕМ ИГРАТЬ!</b>

💰 <b>Баланс:</b>
├ 💎 <code>{user_data['ncoin']} ncoin</code>
└ ⭐ <code>{user_data['nmp']} nmp</code>

💸 <b>Ставка:</b> <code>{user_data['current_bet']} ncoin</code>

👇 Выбери игру и начинай!"""
        
        await query.edit_message_text(
            text=text,
            reply_markup=get_game_keyboard(),
            parse_mode="HTML"
        )
        
    # Раздел "Баскетбол" (выбор исхода)
    elif query.data == "game_basket":
        text = f"""<b>{username}</b>
🏀 <b>Баскетбол · выбери исход!</b>
• • • • • • • • • • • • • • • • • • •
💸 <b>Ставка:</b> <code>{user_data['current_bet']} ncoin</code>"""
        
        await query.edit_message_text(
            text=text,
            reply_markup=get_basket_choice_keyboard(),
            parse_mode="HTML"
        )

    # Настройка быстрой ставки в меню баскетбола
    elif query.data.startswith("basket_setbet_"):
        new_bet = int(query.data.split("_")[2])
        await db_update(user_id, {"current_bet": new_bet})
        text = f"""<b>{username}</b>
🏀 <b>Баскетбол · выбери исход!</b>
• • • • • • • • • • • • • • • • • • •
💸 <b>Ставка:</b> <code>{new_bet} ncoin</code>"""
        
        await query.edit_message_text(
            text=text,
            reply_markup=get_basket_choice_keyboard(),
            parse_mode="HTML"
        )

    # Процесс игры в баскетбол
    elif query.data in ["basket_bet_hit", "basket_bet_miss"]:
        bet = user_data["current_bet"]
        balance = user_data["ncoin"]
        
        if balance < bet:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="❌ <b>У вас недостаточно ncoin для этой ставки!</b> Пожалуйста, уменьшите ставку.",
                parse_mode="HTML"
            )
            return
            
        balance -= bet
        await db_update(user_id, {"ncoin": balance})
        
        user_choice = "попадание" if query.data == "basket_bet_hit" else "мимо"
        
        dice_msg = await context.bot.send_dice(chat_id=query.message.chat_id, emoji="🏀")
        value = dice_msg.dice.value
        
        is_hit = value in [4, 5]
        outcome = "попадание" if is_hit else "мимо"
        
        win = False
        multiplier = 0.0
        if user_choice == "попадание" and is_hit:
            win = True
            multiplier = 2.4
        elif user_choice == "мимо" and not is_hit:
            win = True
            multiplier = 1.6
            
        if win:
            reward = int(bet * multiplier)
            balance += reward
            await db_update(user_id, {"ncoin": balance})
            result_header = f"🥳 Баскетбол · Выигрыш! 🎉"
            reward_text = f"💰 <b>Выигрыш:</b> <code>x{multiplier} / {reward} ncoin</code>"
        else:
            result_header = f"😢 Баскетбол · Проигрыш!"
            reward_text = f"💰 <b>Выигрыш:</b> <code>0 ncoin</code>"
            
        game_result_text = f"""<b>{username}</b>
🏀 <b>{result_header}</b>
• • • • • • • • • • • • • • • • • • •
💸 <b>Ставка:</b> <code>{bet} ncoin</code>
🎲 <b>Выбрано:</b> <code>{user_choice}</code>
{reward_text}
• • • • • • • • • • • • • • • • • • •
⚡️ <b>Итог:</b> <code>{outcome}</code>"""
        
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=game_result_text,
            reply_markup=get_basket_replay_keyboard(),
            parse_mode="HTML"
        )

    # Раздел "Футбол" (выбор исхода)
    elif query.data == "game_football":
        text = f"""<b>{username}</b>
⚽ <b>Футбол · выбери исход!</b>
• • • • • • • • • • • • • • • • • • •
💸 <b>Ставка:</b> <code>{user_data['current_bet']} ncoin</code>"""
        
        await query.edit_message_text(
            text=text,
            reply_markup=get_football_choice_keyboard(),
            parse_mode="HTML"
        )

    # Настройка быстрой ставки в меню футбола
    elif query.data.startswith("football_setbet_"):
        new_bet = int(query.data.split("_")[2])
        await db_update(user_id, {"current_bet": new_bet})
        text = f"""<b>{username}</b>
⚽ <b>Футбол · выбери исход!</b>
• • • • • • • • • • • • • • • • • • •
💸 <b>Ставка:</b> <code>{new_bet} ncoin</code>"""
        
        await query.edit_message_text(
            text=text,
            reply_markup=get_football_choice_keyboard(),
            parse_mode="HTML"
        )

    # Процесс игры в футбол
    elif query.data in ["football_bet_hit", "football_bet_miss"]:
        bet = user_data["current_bet"]
        balance = user_data["ncoin"]
        
        if balance < bet:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="❌ <b>У вас недостаточно ncoin для этой ставки!</b> Пожалуйста, уменьшите ставку.",
                parse_mode="HTML"
            )
            return
            
        balance -= bet
        await db_update(user_id, {"ncoin": balance})
        
        user_choice = "гол" if query.data == "football_bet_hit" else "мимо"
        
        dice_msg = await context.bot.send_dice(chat_id=query.message.chat_id, emoji="⚽")
        value = dice_msg.dice.value
        
        # Исходы футбола: 3, 4 и 5 — гол (попадание), 1 и 2 — промах (мимо)
        is_hit = value in [3, 4, 5]
        outcome = "гол" if is_hit else "мимо"
        
        win = False
        multiplier = 0.0
        if user_choice == "попадание" and is_hit:
            win = True
            multiplier = 2.4
        elif user_choice == "мимо" and not is_hit:
            win = True
            multiplier = 1.6
            
        if win:
            reward = int(bet * multiplier)
            balance += reward
            await db_update(user_id, {"ncoin": balance})
            status_text = "Выиграли! 🎉"
            reward_text = f"💰 <b>Выигрыш:</b> <code>x{multiplier} / {reward} ncoin</code>"
        else:
            status_text = "Проиграли!"
            reward_text = f"💰 <b>Выигрыш:</b> <code>0 ncoin</code>"
            
        game_result_text = f"""<b>{username}</b>
⚽ <b>Бот: Футбол · {status_text}</b>
• • • • • • • • • • • • • • • • • • •
💸 <b>Ставка:</b> <code>{bet} ncoin</code>
🎲 <b>Выбрано:</b> <code>{user_choice}</code>
{reward_text}
• • • • • • • • • • • • • • • • • • •
⚡️ <b>Итог:</b> <code>{outcome}</code>"""
        
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=game_result_text,
            reply_markup=get_football_replay_keyboard(),
            parse_mode="HTML"
        )

    # Кнопка "Изменить ставку"
    elif query.data == "change_bet":
        user_states[user_id] = "awaiting_bet"
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="✍️ <b>Пожалуйста, введите сумму вашей новой ставки числом:</b>",
            parse_mode="HTML"
        )

    # Заглушка для игр Dice и Slots
    elif query.data in ["game_dice", "game_slots"]:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="🎰 Данная мини-игра будет добавлена в ближайшем обновлении!",
            parse_mode="HTML"
        )

    elif call.data == "my_orders_stub":
        await context.bot.send_message(chat_id=call.message.chat.id, text="📋 У вас пока нет совершенных заказов.")


# === ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ ===

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    text = update.message.text
    
    # Обрабатываем изменение ставки
    if user_states.get(user_id) == "awaiting_bet":
        user_states[user_id] = None # Сбрасываем статус ожидания
        
        # Очищаем текст, оставляем только цифры
        clean_text = re.sub(r'[^\d]', '', text)
        if not clean_text:
            await update.message.reply_text("❌ Пожалуйста, отправьте корректное число!")
            return
            
        new_bet = int(clean_text)
        if new_bet <= 0:
            await update.message.reply_text("❌ Ставка должна быть больше нуля!")
            return
            
        await db_update(user_id, {"current_bet": new_bet})
        user_data = await db_get_or_create(user_id, update.effective_user.username)
        
        success_text = f"""✅ <b>Ставка успешно изменена!</b>

💵 <b>Текущая ставка:</b> <code>{user_data['current_bet']} ncoin</code>
💎 <b>Баланс:</b> <code>{user_data['ncoin']} ncoin</code>"""
        
        await update.message.reply_text(
            text=success_text,
            reply_markup=get_game_keyboard(),
            parse_mode="HTML"
        )


# === ЗАПУСК БОТА ===

def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    print("Бот успешно собран и запущен на Railway!")
    application.run_polling()

if __name__ == '__main__':
    main()
