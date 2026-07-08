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

# Клавиатура после завершения игры в баскетбол (как на скриншоте)
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
    username = query.from_user.username or query.from_user.first_name or "Игрок"
    user_data = await db_get_or_create(user_id, query.from_user.username)

        # Кнопка "Играть 🕹️"
    if query.data == "play_game":
        text = (
            "<b>🎮 ДАВАЙ НАЧНЕМ ИГРАТЬ!</b>\n\n"
            "💰 <b>Баланс:</b>\n"
            f"└ 💎 <code>{user_data['ncoin']} ncoin</code>\n"
            f"└ ⭐ <code>{user_data['nmp']} nmp</code>\n\n"
            f"💸 <b>Ставка:</b> <code>{user_data['current_bet']} ncoin</code>\n\n"
            "👇 Выбери игру и начинай!"
        )
        await query.edit_message_text(
            text=text,
            reply_markup=get_game_keyboard(),
            parse_mode="HTML"
        )
    # Раздел "Баскетбол" (выбор исхода)
    elif query.data == "game_basket":
        text = (
            f"<b>{username}</b>\n"
            "🏀 <b>Баскетбол · выбери исход!</b>\n"
            "• • • • • • • • • • • • • • • • • • •\n"
            f"💸 <b>Ставка:</b> <code>{user_data['current_bet']} ncoin</code>"
        )
        await query.edit_message_text(
            text=text,
            reply_markup=get_basket_choice_keyboard(),
            parse_mode="HTML"
        )

    # Настройка быстрой ставки в меню баскетбола
    elif query.data.startswith("basket_setbet_"):
        new_bet = int(query.data.split("_")[2])
        await db_update(user_id, {"current_bet": new_bet})
        # Возвращаем пользователя на экран выбора исхода баскетбола с новой ставкой
        text = (
            f"<b>{username}</b>\n"
            "🏀 <b>Баскетбол · выбери исход!</b>\n"
            "• • • • • • • • • • • • • • • • • • •\n"
            f"💸 <b>Ставка:</b> <code>{new_bet} ncoin</code>"
        )
        await query.edit_message_text(
            text=text,
            reply_markup=get_basket_choice_keyboard(),
            parse_mode="HTML"
        )

    # Процесс игры в баскетбол (Попадание или Мимо)
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
            
        # Списываем ставку
        balance -= bet
        await db_update(user_id, {"ncoin": balance})
        
        # Определяем выбор пользователя
        user_choice = "попадание" if query.data == "basket_bet_hit" else "мимо"
        
        # Запускаем анимацию баскетбольного кольца
        dice_msg = await context.bot.send_dice(chat_id=query.message.chat_id, emoji="🏀")
        value = dice_msg.dice.value
        
        # Определение исхода броска: 4 и 5 — залетел (попадание), 1, 2, 3 — промах (мимо)
        is_hit = value in [4, 5]
        outcome = "попадание" if is_hit else "мимо"
        
        # Проверка выигрыша
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
            status_text = "Выигрыш! 🎉"
            result_header = f"🥳 Баскетбол · {status_text}"
        else:
            status_text = "Проигрыш! 😢"
            result_header = f"😢 Баскетбол · {status_text}"
            
        # Текст итогов игры
        game_result_text = (
            f"<b>{username}</b>\n"
            f"🏀 <b>{result_header}</b>\n"
            "• • • • • • • • • • • • • • • • • • •\n"
            f"💸 <b>Ставка:</b> <code>{bet} ncoin</code>\n"
            f"🎲 <b>Выбрано:</b> <code>{user_choice}</code>\n"
            "• • • • • • • • • • • • • • • • • • •\n"
            f"⚡️ <b>Итог:</b> <code>{outcome}</code>"
        )
        
        # Отправляем результаты с панелью быстрого изменения ставки и повтора
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=game_result_text,
            reply_markup=get_basket_replay_keyboard(),
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
        
    # Слоты 🎰 и Кости 🎲
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
            
        balance -= bet
        await db_update(user_id, {"ncoin": balance})
        
        emoji = "🎰" if query.data == "game_slots" else "🎲"
        
        dice_msg = await context.bot.send_dice(chat_id=query.message.chat_id, emoji=emoji)
        value = dice_msg.dice.value
        
        win_multiplier = 0
        if query.data == "game_slots":
            if value in [1, 22, 43, 64]:
                win_multiplier = 10
            elif value in [16, 32, 48]:
                win_multiplier = 3
        else:
            if value >= 4:
                win_multiplier = 2
                
        if win_multiplier > 0:
            reward = bet * win_multiplier
            balance += reward
            await db_update(user_id, {"ncoin": balance})
            result_text = f"🎉 <b>Вы выиграли {reward} ncoin! (Множитель x{win_multiplier})</b>"
        else:
            result_text = "😔 <b>Ставка не сыграла. Попробуйте еще раз!</b>"
            
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=(
                f"{result_text}\n\n"
                f"💰 <b>Ваш новый баланс:</b> <code>{balance} ncoin</code>"
            ),
            parse_mode="HTML"
        )
        
    # Заглушки на другие кнопки
    elif query.data in ["btn_fast", "btn_modes", "game_ball", "game_darts", "game_bowling"]:
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
