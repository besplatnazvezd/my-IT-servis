import re
import logging
import httpx
from typing import Dict, Any
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# -----------------------
# Настройки
# -----------------------
BOT_TOKEN = "8894416195:AAHZ4i0sTodK5AYKhqZfNIlrFBnlRTOiVR8"
ADMIN_ID = 7727345054
IMAGE_URL = "https://i.ibb.co/jPJjTDBv/1000093316.jpg"

SUPABASE_URL = "https://gyjwzifhfxrojwjioapp.supabase.co/rest/v1/"
SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd5and6aWZoZnhyb2p3amlvYXBwIiwicm9sZESIsImlhdCI6MTc4MzQxNDcxMywiZXhwIjoyMDk4OTkwNzEzfQ.xjicAYNFaI9iTA3PlHvM2L_10r38gJSIlwmopy_3O70"
)

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

# -----------------------
# Логирование
# -----------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# -----------------------
# Временная память (Fallback)
# -----------------------
user_states: Dict[int, str] = {}
LOCAL_DB: Dict[int, Dict[str, Any]] = {}

# Helper для красивого форматирования чисел (1000 -> 1k, 1000000 -> 1kk)
def format_number(val: int | float) -> str:
    val = int(val)
    if val >= 1000000:
        return f"{val / 1000000:.2f}kk"
    elif val >= 1000:
        return f"{val / 1000:.2f}k"
    return str(val)

# -----------------------
# Работа с БД (Supabase)
# -----------------------
async def db_get_or_create(tg_id: int, username: str | None) -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{SUPABASE_URL}users?tg_id=eq.{tg_id}", headers=HEADERS, timeout=6.0)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list) and data:
                return data[0]
            
            # Новый юзер с поддержкой игровой статистики
            new_user = {
                "tg_id": tg_id,
                "username": username or "Игрок",
                "ncoin": 10000,
                "nmp": 0,
                "current_bet": 10,
                "games_played": 0,
                "won_duels": 0,
                "lost_ncoin": 0
            }
            r2 = await client.post(f"{SUPABASE_URL}users", json=new_user, headers=HEADERS, timeout=6.0)
            r2.raise_for_status()
            created = r2.json()
            if isinstance(created, list) and created:
                return created[0]
            return new_user
    except Exception as e:
        logger.error("Supabase get_or_create error: %s", e)
        if tg_id not in LOCAL_DB:
            LOCAL_DB[tg_id] = {
                "tg_id": tg_id,
                "username": username or "Игрок",
                "ncoin": 10000,
                "nmp": 0,
                "current_bet": 10,
                "games_played": 0,
                "won_duels": 0,
                "lost_ncoin": 0
            }
        return LOCAL_DB[tg_id]


async def db_update(tg_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.patch(f"{SUPABASE_URL}users?tg_id=eq.{tg_id}", json=updates, headers=HEADERS, timeout=6.0)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list) and data:
                return data[0]
            return {}
    except Exception as e:
        logger.error("Supabase update error: %s", e)
        if tg_id in LOCAL_DB:
            LOCAL_DB[tg_id].update(updates)
            return LOCAL_DB[tg_id]
        return {}


# -----------------------
# Клавиатуры
# -----------------------
def get_start_keyboard(bot_username: str) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("Играть 🕹️", callback_data="play_game")],
        [InlineKeyboardButton("➕ Добавить бота в чат", url=f"https://t.me/{bot_username}?startgroup=true")],
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
            InlineKeyboardButton("🎰", callback_data="game_slots"),
        ],
        [InlineKeyboardButton("🚀 Быстрые", callback_data="btn_fast"), InlineKeyboardButton("Режимы 💣", callback_data="btn_modes")],
        [InlineKeyboardButton("🕹️ Играть в WEB", web_app=WebAppInfo(url="https://google.com"))],
        [InlineKeyboardButton("✍️ Изменить ставку", callback_data="change_bet")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_basket_choice_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🏀 Попадание - x2.4", callback_data="basket_bet_hit")],
        [InlineKeyboardButton("🙈 Мимо - x1.6", callback_data="basket_bet_miss")],
        [InlineKeyboardButton("◀️ назад", callback_data="play_game")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_basket_replay_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("⬇️ 5 💰", callback_data="basket_setbet_5"),
            InlineKeyboardButton("10 💰", callback_data="basket_setbet_10"),
            InlineKeyboardButton("⬆️ 20 💰", callback_data="basket_setbet_20"),
        ],
        [InlineKeyboardButton("Повторить игру 🔄", callback_data="game_basket")],
        [InlineKeyboardButton("◀️ Главное меню", callback_data="play_game")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_football_choice_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("⚽ Гол - x1.6", callback_data="football_bet_hit")],
        [InlineKeyboardButton("🥅 Мимо - x2.4", callback_data="football_bet_miss")],
        [InlineKeyboardButton("◀️ назад", callback_data="play_game")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_football_replay_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("⬇️ 5 💰", callback_data="football_setbet_5"),
            InlineKeyboardButton("10 💰", callback_data="football_setbet_10"),
            InlineKeyboardButton("⬆️ 20 💰", callback_data="football_setbet_20"),
        ],
        [InlineKeyboardButton("Повторить игру 🔄", callback_data="game_football")],
        [InlineKeyboardButton("◀️ Главное меню", callback_data="play_game")],
    ]
    return InlineKeyboardMarkup(keyboard)


# -----------------------
# Старт
# -----------------------
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
        parse_mode="HTML",
    )


# -----------------------
# Кнопки
# -----------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    logger.info("Callback received: %s from %s", query.data, query.from_user.id)
    await query.answer()
    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name or "Игрок"
    user_data = await db_get_or_create(user_id, query.from_user.username)

    # --------------- кнопка "Играть" ---------------
    if query.data == "play_game":
        text = (
            "<b>🎮 ДАВАЙ НАЧНЕМ ИГРАТЬ!</b>\n\n"
            "💰 <b>Баланс:</b>\n"
            f"├ 💎 <code>{user_data['ncoin']} ncoin</code>\n"
            f"└ ⭐ <code>{user_data['nmp']} nmp</code>\n\n"
            f"💸 <b>Ставка:</b> <code>{user_data['current_bet']} ncoin</code>\n\n"
            "👇 Выбери игру и начинай!"
        )
        try:
            await query.edit_message_text(text=text, reply_markup=get_game_keyboard(), parse_mode="HTML")
        except Exception:
            await context.bot.send_message(chat_id=query.message.chat_id, text=text, reply_markup=get_game_keyboard(), parse_mode="HTML")

    # --------------- БАСКЕТБОЛ ---------------
    elif query.data == "game_basket":
        text = (
            f"<b>{username}</b>\n"
            "🏀 <b>Баскетбол · выбери исход!</b>\n"
            "• • • • • • • • • • • • • • •\n"
            f"💸 <b>Ставка:</b> <code>{user_data['current_bet']} ncoin</code>"
        )
        try:
            await query.edit_message_text(text=text, reply_markup=get_basket_choice_keyboard(), parse_mode="HTML")
        except Exception:
            await context.bot.send_message(chat_id=query.message.chat_id, text=text, reply_markup=get_basket_choice_keyboard(), parse_mode="HTML")

    elif query.data and query.data.startswith("basket_setbet_"):
        new_bet = int(query.data.split("_")[2])
        await db_update(user_id, {"current_bet": new_bet})
        text = (
            f"<b>{username}</b>\n"
            "🏀 <b>Баскетбол · выбери исход!</b>\n"
            "• • • • • • • • • • • • • • •\n"
            f"💸 <b>Ставка:</b> <code>{new_bet} ncoin</code>"
        )
        try:
            await query.edit_message_text(text=text, reply_markup=get_basket_choice_keyboard(), parse_mode="HTML")
        except Exception:
            await context.bot.send_message(chat_id=query.message.chat_id, text=text, reply_markup=get_basket_choice_keyboard(), parse_mode="HTML")

    elif query.data in ("basket_bet_hit", "basket_bet_miss"):
        bet = int(user_data["current_bet"])
        balance = int(user_data["ncoin"])
        games_played = int(user_data.get("games_played", 0)) + 1
        lost_ncoin = int(user_data.get("lost_ncoin", 0))

        if balance < bet:
            await context.bot.send_message(chat_id=query.message.chat_id, text="❌ <b>Недостаточно ncoin</b>", parse_mode="HTML")
            return
        balance -= bet

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
            reward_text = f"💰 <b>Выигрыш:</b> <code>x{multiplier} / {reward} ncoin</code>"
            header = "🥳 Баскетбол · Выигрыш!"
        else:
            lost_ncoin += bet
            reward_text = "💰 <b>Выигрыш:</b> <code>0 ncoin</code>"
            header = "😢 Баскетбол · Проигрыш!"

        # Обновляем БД со статистикой
        await db_update(user_id, {
            "ncoin": balance,
            "games_played": games_played,
            "lost_ncoin": lost_ncoin
        })

        game_result_text = (
            f"<b>{username}</b>\n"
            f"🏀 <b>{header}</b>\n"
            "• • • • • • • • • •\n"
            f"💸 <b>Ставка:</b> <code>{bet} ncoin</code>\n"
            f"🎲 <b>Выбрано:</b> <code>{user_choice}</code>\n"
            f"{reward_text}\n"
            f"⚡️ <b>Итог:</b> <code>{outcome}</code>"
        )
        await context.bot.send_message(chat_id=query.message.chat_id, text=game_result_text, reply_markup=get_basket_replay_keyboard(), parse_mode="HTML")

    # --------------- ФУТБОЛ ---------------
    elif query.data == "game_football":
        text = (
            f"<b>{username}</b>\n"
            "⚽ <b>Футбол · выбери исход!</b>\n"
            "• • • • • • • • • •\n"
            f"💸 <b>Ставка:</b> <code>{user_data['current_bet']} ncoin</code>"
        )
        try:
            await query.edit_message_text(text=text, reply_markup=get_football_choice_keyboard(), parse_mode="HTML")
        except Exception:
            await context.bot.send_message(chat_id=query.message.chat_id, text=text, reply_markup=get_football_choice_keyboard(), parse_mode="HTML")

    elif query.data and query.data.startswith("football_setbet_"):
        new_bet = int(query.data.split("_")[2])
        await db_update(user_id, {"current_bet": new_bet})
        text = (
            f"<b>{username}</b>\n"
            "⚽ <b>Футбол · выбери исход!</b>\n"
            "• • • • • • • • • •\n"
            f"💸 <b>Ставка:</b> <code>{new_bet} ncoin</code>"
        )
        try:
            await query.edit_message_text(text=text, reply_markup=get_football_choice_keyboard(), parse_mode="HTML")
        except Exception:
            await context.bot.send_message(chat_id=query.message.chat_id, text=text, reply_markup=get_football_choice_keyboard(), parse_mode="HTML")

    elif query.data in ("football_bet_hit", "football_bet_miss"):
        bet = int(user_data["current_bet"])
        balance = int(user_data["ncoin"])
        games_played = int(user_data.get("games_played", 0)) + 1
        lost_ncoin = int(user_data.get("lost_ncoin", 0))

        if balance < bet:
            await context.bot.send_message(chat_id=query.message.chat_id, text="❌ <b>Недостаточно ncoin</b>", parse_mode="HTML")
            return
        balance -= bet

        user_choice = "гол" if query.data == "football_bet_hit" else "мимо"
        dice_msg = await context.bot.send_dice(chat_id=query.message.chat_id, emoji="⚽")
        value = dice_msg.dice.value
        is_hit = value in [3, 4, 5]
        outcome = "гол" if is_hit else "мимо"

        win = False
        multiplier = 0.0
        if user_choice == "гол" and is_hit:
            win = True
            multiplier = 1.6
        elif user_choice == "мимо" and not is_hit:
            win = True
            multiplier = 2.4

        if win:
            reward = int(bet * multiplier)
            balance += reward
            reward_text = f"💰 <b>Выигрыш:</b> <code>x{multiplier} / {reward} ncoin</code>"
            header = "⚽ Победа!"
        else:
            lost_ncoin += bet
            reward_text = "💰 <b>Выигрыш:</b> <code>0 ncoin</code>"
            header = "⚽ Проигрыш!"

        await db_update(user_id, {
            "ncoin": balance,
            "games_played": games_played,
            "lost_ncoin": lost_ncoin
        })

        game_result_text = (
            f"<b>{username}</b>\n"
            f"⚽ <b>{header}</b>\n"
            "• • • • • • • • •\n"
            f"💸 <b>Ставка:</b> <code>{bet} ncoin</code>\n"
            f"🎲 <b>Выбрано:</b> <code>{user_choice}</code>\n"
            f"{reward_text}\n"
            f"⚡️ <b>Итог:</b> <code>{outcome}</code>"
        )
        await context.bot.send_message(chat_id=query.message.chat_id, text=game_result_text, reply_markup=get_football_replay_keyboard(), parse_mode="HTML")

    # --------------- Изменение ставки ---------------
    elif query.data == "change_bet":
        user_states[user_id] = "awaiting_bet"
        await context.bot.send_message(chat_id=query.message.chat_id, text="✍️ <b>Введите новую ставку (числом):</b>", parse_mode="HTML")

    # --------------- Быстрые/режимы/пустышки ---------------
    elif query.data in ("btn_fast", "btn_modes", "game_darts", "game_bowling", "game_dice", "game_slots"):
        await context.bot.send_message(chat_id=query.message.chat_id, text="⚙️ Режим в разработке.", parse_mode="HTML")


# -----------------------
# Обработчик текста (баланс / ставка)
# -----------------------
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    raw_text = update.message.text or ""
    clean_text = raw_text.strip().lower()

    # Сначала проверяем команду «Баланс» или «Б» (а также на англ.)
    if clean_text in ["баланс", "б", "balance", "b"]:
        user_data = await db_get_or_create(user_id, user.username)
        
        # Получаем данные из БД (с подстраховкой на 0)
        ncoin_bal = user_data.get("ncoin", 10000)
        games_played = user_data.get("games_played", 0)
        lost_ncoin = user_data.get("lost_ncoin", 0)
        won_duels = user_data.get("won_duels", 0)
        
        # Красиво форматируем проигранные коины (например 8.01kk)
        formatted_lost = format_number(lost_ncoin)

        profile_text = (
            f"<b>{user.first_name}</b>\n"
            f"{raw_text}\n\n"
            f"💰 <b>Баланс:</b> <code>{ncoin_bal} nCoin</code>\n"
            f"• • • • • • • • • • • • • • • • • • •\n"
            f"💣 <b>Сыграно игр:</b> <code>{games_played}</code>\n"
            f"⚔️ <b>Выиграно дуэлей:</b> <code>{won_duels}</code>\n"
            f"🏆 <b>Проиграно nCoin:</b> <code>{formatted_lost}</code>"
        )
        await update.message.reply_text(profile_text, parse_mode="HTML")
        return

    # Если бот ожидал ввода новой ставки
    if user_states.get(user_id) == "awaiting_bet":
        user_states[user_id] = ""
        digits = re.sub(r"[^\d]", "", raw_text)
        if not digits:
            await update.message.reply_text("❌ Отправьте корректное число.")
            return
        new_bet = int(digits)
        if new_bet <= 0:
            await update.message.reply_text("❌ Ставка должна быть больше 0.")
            return
        await db_update(user_id, {"current_bet": new_bet})
        user_data = await db_get_or_create(user_id, user.username)
        await update.message.reply_text(
            text=f"✅ Ставка обновлена.\n💵 Текущая ставка: {user_data['current_bet']} ncoin\n💎 Баланс: {user_data['ncoin']} ncoin",
            reply_markup=get_game_keyboard(),
            parse_mode="HTML",
        )


# -----------------------
# Тестовая команда
# -----------------------
async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("TEST play_game", callback_data="play_game")]])
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Тестовая клавиатура:", reply_markup=kb)


# -----------------------
# Запуск бота
# -----------------------
def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("test", test_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    logger.info("Запуск бота...")
    application.run_polling()


if __name__ == "__main__":
    main()
