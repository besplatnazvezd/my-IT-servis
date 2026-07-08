import re
import logging
import httpx
import random
from datetime import datetime
from typing import Dict, Any
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
    BotCommand,
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
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd5and6aWZoZnhyb2p3amlvYXBwIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MzQxNDcxMywiZXhwIjoyMDk4OTkwNzEzfQ.xjicAYNFaI9iTA3PlHvM2L_10r38gJSIlwmopy_3O70"
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
# Состояния и Локальный Fallback
# -----------------------
user_states: Dict[int, str] = {}
LOCAL_DB: Dict[int, Dict[str, Any]] = {}

def format_number(val: int | float) -> str:
    val = int(val)
    if val >= 1000000:
        return f"{val / 1000000:.2f}kk"
    elif val >= 1000:
        return f"{val / 1000:.2f}k"
    return str(val)

# -----------------------
# Работа с БД (Supabase REST)
# -----------------------
async def db_get_or_create(tg_id: int, username: str | None) -> Dict[str, Any]:
    current_time = datetime.now().strftime("%d-%m-%Y %H:%M")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{SUPABASE_URL}users?tg_id=eq.{tg_id}", headers=HEADERS, timeout=6.0)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list) and data:
                return data[0]
            
            new_user = {
                "tg_id": tg_id,
                "username": username or "Игрок",
                "ncoin": 10000,
                "nmp": 0,
                "current_bet": 10,
                "games_played": 0,
                "won_duels": 0,
                "lost_ncoin": 0,
                "reg_date": current_time
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
                "lost_ncoin": 0,
                "reg_date": current_time
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
# Клавиатуры (В точности как на скриншотах)
# -----------------------

def get_start_keyboard(bot_username: str) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("Играть 🕹️", callback_data="play_game")],
        [InlineKeyboardButton("➕ Добавить бота в чат", url=f"https://t.me/{bot_username}?startgroup=true")],
    ]
    return InlineKeyboardMarkup(keyboard)

# Меню «Быстрые» (По умолчанию при "Играть")
def get_fast_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("🏀", callback_data="game_basket"),
            InlineKeyboardButton("⚽", callback_data="game_football"),
            InlineKeyboardButton("🎯", callback_data="info_darts"),
            InlineKeyboardButton("🎳", callback_data="info_bowling"),
            InlineKeyboardButton("🎲", callback_data="info_dice"),
            InlineKeyboardButton("🎰", callback_data="info_slots"),
        ],
        [InlineKeyboardButton("🔫 Рус. рулетка", callback_data="info_buckshot")],
        [
            InlineKeyboardButton("🚀 Краш", callback_data="game_crash_stub"),
            InlineKeyboardButton("Монета 🪙", callback_data="info_coin")
        ],
        [
            InlineKeyboardButton("🎲🎲 Кости", callback_data="info_dice"),
            InlineKeyboardButton("Рулетка 🎱", callback_data="info_roulette")
        ],
        [
            InlineKeyboardButton("🔮 Фортуна", callback_data="game_fortune_stub"),
            InlineKeyboardButton("Сундук 🧰", callback_data="game_chest_stub")
        ],
        [
            InlineKeyboardButton("🎈 Шар", callback_data="game_balloon_stub"),
            InlineKeyboardButton("Рыбалка 🎣", callback_data="game_fishing_stub")
        ],
        [InlineKeyboardButton("🎫 Скретч", callback_data="game_scratch_stub")],
        [InlineKeyboardButton("Режимы 💣", callback_data="btn_modes")],
        [
            InlineKeyboardButton("👤 Профиль", callback_data="open_profile"),
            InlineKeyboardButton("✍️ Изменить ставку", callback_data="change_bet")
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

# Меню «Режимы» (Второй скриншот)
def get_modes_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("💣 Мины", callback_data="game_mines_stub"),
            InlineKeyboardButton("Алмазы 💎", callback_data="game_diamonds_stub")
        ],
        [
            InlineKeyboardButton("🛕 Башня", callback_data="game_tower_stub"),
            InlineKeyboardButton("Золото ⚜️", callback_data="game_gold_stub")
        ],
        [
            InlineKeyboardButton("🐸 Квак", callback_data="game_frog_stub"),
            InlineKeyboardButton("HiLo ↕️", callback_data="game_hilo_stub")
        ],
        [
            InlineKeyboardButton("♣️ 21(Очко)", callback_data="game_21_stub"),
            InlineKeyboardButton("Пирамида 🔺", callback_data="game_pyramid_stub")
        ],
        [InlineKeyboardButton("🥊 Арена", callback_data="game_arena_stub")],
        [InlineKeyboardButton("🚀 Быстрые", callback_data="btn_fast")],
        [
            InlineKeyboardButton("👤 Профиль", callback_data="open_profile"),
            InlineKeyboardButton("✍️ Изменить ставку", callback_data="change_bet")
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ назад", callback_data="play_game")]])

def get_profile_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📦 Инвентарь", callback_data="open_inventory"),
         InlineKeyboardButton("⚙️ Настройки", callback_data="open_settings")],
        [InlineKeyboardButton("🏆 Титулы", callback_data="open_titles"),
         InlineKeyboardButton("🛍️ Витрина", callback_data="open_vitrina")],
        [InlineKeyboardButton("◀️ Назад", callback_data="play_game")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_game_action_keyboard(play_cb: str) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("Играть сейчас ⚡️", callback_data=play_cb)],
        [InlineKeyboardButton("◀️ назад", callback_data="play_game")]
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
# Команды бота
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

async def game_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_data = await db_get_or_create(user.id, user.username)
    text = (
        "<b>🎮 ДАВАЙ НАЧНЕМ ИГРАТЬ!</b>\n\n"
        "💰 <b>Баланс:</b>\n"
        f"├ 💎 <code>{user_data['ncoin']} ncoin</code>\n"
        f"└ ⭐ <code>{user_data['nmp']} nmp</code>\n\n"
        f"💸 <b>Ставка:</b> <code>{user_data['current_bet']} ncoin</code>\n\n"
        "👇 Выбери игру и начинай!"
    )
    await update.message.reply_text(text=text, reply_markup=get_fast_keyboard(), parse_mode="HTML")


# -----------------------
# Универсальный Обработчик Кнопок
# -----------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    logger.info("Callback received: %s from %s", query.data, query.from_user.id)
    await query.answer()
    
    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name or "Игрок"
    user_link = f'<a href="tg://user?id={user_id}">{username}</a>'
    user_data = await db_get_or_create(user_id, query.from_user.username)

    # --------------- Переключение между Быстрыми и Режимами ---------------
    if query.data in ["play_game", "btn_fast"]:
        text = (
            "<b>🎮 ДАВАЙ НАЧНЕМ ИГРАТЬ!</b>\n\n"
            "💰 <b>Баланс:</b>\n"
            f"├ 💎 <code>{user_data['ncoin']} ncoin</code>\n"
            f"└ ⭐ <code>{user_data['nmp']} nmp</code>\n\n"
            f"💸 <b>Ставка:</b> <code>{user_data['current_bet']} ncoin</code>\n\n"
            "👇 Выбери игру и начинай!"
        )
        try:
            await query.edit_message_text(text=text, reply_markup=get_fast_keyboard(), parse_mode="HTML")
        except Exception:
            await context.bot.send_message(chat_id=query.message.chat_id, text=text, reply_markup=get_fast_keyboard(), parse_mode="HTML")

    elif query.data == "btn_modes":
        text = (
            "<b>🎮 ДАВАЙ НАЧНЕМ ИГРАТЬ!</b>\n\n"
            "💰 <b>Баланс:</b>\n"
            f"├ 💎 <code>{user_data['ncoin']} ncoin</code>\n"
            f"└ ⭐ <code>{user_data['nmp']} nmp</code>\n\n"
            f"💸 <b>Ставка:</b> <code>{user_data['current_bet']} ncoin</code>\n\n"
            "👇 Выбери игру и начинай!"
        )
        try:
            await query.edit_message_text(text=text, reply_markup=get_modes_keyboard(), parse_mode="HTML")
        except Exception:
            await context.bot.send_message(chat_id=query.message.chat_id, text=text, reply_markup=get_modes_keyboard(), parse_mode="HTML")

    # --------------- Игры (Информационные экраны по скриншотам) ---------------
    elif query.data == "info_bowling":
        text = f"""<b>{username}</b>
<blockquote>🎳 <b>Боулинг</b> — это игра, в которой вам нужно сбить кегли, чтобы получить максимальный множитель.
📊 Лимиты: 10 - 1,000,000 ncoin</blockquote>
👥 {user_link}, чтобы начать игру, используй команду:

🎳 <code>/bowling [ставка]</code>

<b>Пример:</b> /bowling 100
<b>Пример:</b> боулинг 100"""
        await query.edit_message_text(text=text, reply_markup=get_game_action_keyboard("play_bowling_now"), parse_mode="HTML")

    elif query.data == "info_slots":
        text = f"""<b>{username}</b>
<blockquote>🎰 <b>Слоты</b> — это игра, где цель выбить три одинаковых символа на барабанах, запустив их вращение.
📊 Лимиты: 10 - 1,000,000 ncoin</blockquote>
👥 {user_link}, чтобы начать игру, используй команду:

🎰 <code>/slots [ставка]</code>

<b>Пример:</b> /slots 100
<b>Пример:</b> слоты 100"""
        await query.edit_message_text(text=text, reply_markup=get_game_action_keyboard("play_slots_now"), parse_mode="HTML")

    elif query.data == "info_dice":
        text = f"""<b>{username}</b>
<blockquote>🎲 <b>Кубик</b> — игра против дилера. Бросьте кубик и наберите больше очков, чтобы удвоить ставку!
📊 Лимиты: 10 - 1,000,000 ncoin</blockquote>
👥 {user_link}, чтобы начать игру, используй команду:

🎲 <code>/dice [ставка]</code>"""
        await query.edit_message_text(text=text, reply_markup=get_game_action_keyboard("play_dice_now"), parse_mode="HTML")

    elif query.data == "info_darts":
        text = f"""<b>{username}</b>
<blockquote>🎯 <b>Дартс</b> — игра на точность. Попадите ближе к центру мишени, чтобы сорвать огромный куш!
📊 Лимиты: 10 - 1,000,000 ncoin</blockquote>
👥 {user_link}, чтобы начать игру, используй команду:

🎯 <code>/darts [ставка]</code>"""
        await query.edit_message_text(text=text, reply_markup=get_game_action_keyboard("play_darts_now"), parse_mode="HTML")

    elif query.data == "info_buckshot":
        text = f"""<b>{username}</b>
<blockquote>🔫 <b>Русская рулетка</b> — это игра, в которой игрок использует револьвер с одним или пятью патронами, помещая его в барабан и вращая его.
📊 Лимиты: 10 - 1,000,000 ncoin</blockquote>
👥 {user_link}, чтобы начать игру, используй команду:

🔫 <code>/buckshot [ставка]</code>

<b>Пример:</b> /buckshot 100
<b>Пример:</b> рр 100"""
        await query.edit_message_text(text=text, reply_markup=get_game_action_keyboard("play_buckshot_now"), parse_mode="HTML")

    elif query.data == "info_coin":
        text = f"""<b>{username}</b>
<blockquote>🪙 <b>Орел и решка</b> — это простая игра, в которой используется монета. Игрок бросает монету, и в зависимости от того, какая сторона выпала, определяется результат игры.
📊 Лимиты: 10 - 1,000,000 ncoin</blockquote>
👥 {user_link}, чтобы начать игру, используй команду:

🪙 <code>/coin [ставка] [орел/решка]</code>"""
        await query.edit_message_text(text=text, reply_markup=get_game_action_keyboard("play_coin_now"), parse_mode="HTML")

    elif query.data == "info_roulette":
        text = f"""<b>{username}</b>
<blockquote>🎱 <b>Рулетка</b> — это игра с вращающимся колесом, состоящим из 36 красных и черных секторов. Игроки могут делать ставки на цвет, четное/нечетное или конкретное число.
📊 Лимиты: 10 - 1,000,000 ncoin</blockquote>
👥 {user_link}, чтобы начать игру, используй команду:

🎱 <code>/roulette [ставка] [к/ч/число]</code>"""
        await query.edit_message_text(text=text, reply_markup=get_game_action_keyboard("play_roulette_now"), parse_mode="HTML")


    # --------------- Прямой запуск игр с кнопок ---------------
    elif query.data in ["play_bowling_now", "play_slots_now", "play_dice_now", "play_darts_now", "play_buckshot_now", "play_coin_now", "play_roulette_now"]:
        bet = user_data["current_bet"]
        balance = user_data["ncoin"]
        
        if balance < bet:
            await context.bot.send_message(chat_id=query.message.chat_id, text="❌ <b>Недостаточно ncoin для игры!</b>", parse_mode="HTML")
            return
            
        await db_update(user_id, {"ncoin": balance - bet, "games_played": user_data.get("games_played", 0) + 1})
        
        # Запуск анимационных
        if query.data in ["play_bowling_now", "play_slots_now", "play_dice_now", "play_darts_now"]:
            emoji_map = {
                "play_bowling_now": "🎳",
                "play_slots_now": "🎰",
                "play_dice_now": "🎲",
                "play_darts_now": "🎯"
            }
            emoji = emoji_map[query.data]
            dice_msg = await context.bot.send_dice(chat_id=query.message.chat_id, emoji=emoji)
            val = dice_msg.dice.value
            
            multiplier = 0.0
            if emoji == "🎳":
                mults = {1: 0.0, 2: 0.5, 3: 1.0, 4: 1.5, 5: 2.0, 6: 3.5}
                multiplier = mults.get(val, 1.0)
            elif emoji == "🎰":
                if val in [1, 22, 43, 64]: multiplier = 15.0
                elif val in [16, 32, 48]: multiplier = 5.0
                elif val in [2, 3, 4, 10]: multiplier = 1.5
            elif emoji == "🎲":
                multiplier = 2.0 if val >= 4 else 0.0
            elif emoji == "🎯":
                mults = {1: 0.0, 2: 0.5, 3: 1.0, 4: 1.8, 5: 2.5, 6: 5.0}
                multiplier = mults.get(val, 0.0)
                
            win_sum = int(bet * multiplier)
            new_bal = balance - bet + win_sum
            lost_add = bet if win_sum == 0 else 0
            
        # Неанимационные игры (быстрый расчет)
        elif query.data == "play_buckshot_now":
            is_dead = random.choice([True, False, False, False, False, False])
            if is_dead:
                win_sum = 0
                lost_add = bet
                new_bal = balance - bet
                res_header = "💥 <b>БАБАХ! Вы застрелились.</b>"
            else:
                win_sum = int(bet * 1.2)
                lost_add = 0
                new_bal = balance - bet + win_sum
                res_header = "🔫 *Клик!* <b>Вы выжили!</b>"
            await context.bot.send_message(chat_id=query.message.chat_id, text=f"{res_header}\nРезультат: {win_sum} ncoin", parse_mode="HTML")
            await db_update(user_id, {"ncoin": new_bal, "lost_ncoin": user_data.get("lost_ncoin", 0) + lost_add})
            return

        elif query.data == "play_coin_now":
            outcome = random.choice(["орел", "решка"])
            win_sum = int(bet * 1.95)
            new_bal = balance - bet + win_sum
            lost_add = 0
            await context.bot.send_message(chat_id=query.message.chat_id, text=f"🌑 Выпала <b>{outcome}</b>! <b>Вы выиграли!</b>\nВыиграно: <code>{win_sum} ncoin</code>", parse_mode="HTML")
            await db_update(user_id, {"ncoin": new_bal})
            return

        elif query.data == "play_roulette_now":
            outcome = random.choice(["красный", "черный"])
            win_sum = int(bet * 2)
            new_bal = balance - bet + win_sum
            lost_add = 0
            await context.bot.send_message(chat_id=query.message.chat_id, text=f"🎱 Выпало: <b>{outcome}</b>! <b>Вы выиграли!</b>\nВыиграно: <code>{win_sum} ncoin</code>", parse_mode="HTML")
            await db_update(user_id, {"ncoin": new_bal})
            return

        await db_update(user_id, {"ncoin": new_bal, "lost_ncoin": user_data.get("lost_ncoin", 0) + lost_add})
        
        result_text = f"🎉 <b>Выиграли {win_sum} ncoin!</b>" if win_sum > 0 else "😔 <b>Ставка не сыграла.</b>"
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"{result_text}\n💰 <b>Баланс:</b> <code>{new_bal} ncoin</code>",
            reply_markup=get_back_keyboard(),
            parse_mode="HTML"
        )

    # --------------- БАСКЕТБОЛ ---------------
    elif query.data == "game_basket":
        text = (
            f"<b>{username}</b>\n"
            "🏀 <b>Баскетбол · выбери исход!</b>\n"
            "• • • • • • • • • • • • • • •\n"
            f"💸 <b>Ставка:</b> <code>{user_data['current_bet']} ncoin</code>"
        )
        await query.edit_message_text(text=text, reply_markup=get_basket_choice_keyboard(), parse_mode="HTML")

    elif query.data and query.data.startswith("basket_setbet_"):
        new_bet = int(query.data.split("_")[2])
        await db_update(user_id, {"current_bet": new_bet})
        text = (
            f"<b>{username}</b>\n"
            "🏀 <b>Баскетбол · выбери исход!</b>\n"
            "• • • • • • • • • • • • • • •\n"
            f"💸 <b>Ставка:</b> <code>{new_bet} ncoin</code>"
        )
        await query.edit_message_text(text=text, reply_markup=get_basket_choice_keyboard(), parse_mode="HTML")

    elif query.data in ("basket_bet_hit", "basket_bet_miss"):
        bet = int(user_data["current_bet"])
        balance = int(user_data["ncoin"])
        
        if balance < bet:
            await context.bot.send_message(chat_id=query.message.chat_id, text="❌ <b>Недостаточно ncoin</b>", parse_mode="HTML")
            return
            
        balance -= bet
        user_choice = "попадание" if query.data == "basket_bet_hit" else "мимо"
        dice_msg = await context.bot.send_dice(chat_id=query.message.chat_id, emoji="🏀")
        value = dice_msg.dice.value
        is_hit = value in [4, 5]
        outcome = "попадание" if is_hit else "мимо"

        win = (user_choice == "попадание" and is_hit) or (user_choice == "мимо" and not is_hit)
        multiplier = 2.4 if user_choice == "попадание" else 1.6
        
        if win:
            reward = int(bet * multiplier)
            balance += reward
            reward_text = f"💰 <b>Выиграли:</b> <code>x{multiplier} / {reward} ncoin</code>"
            header = "🏀 Победа! 🎉"
            lost_add = 0
        else:
            reward_text = "💰 <b>Выиграли:</b> <code>0 ncoin</code>"
            header = "🏀 Проигрыш!"
            lost_add = bet

        await db_update(user_id, {
            "ncoin": balance,
            "games_played": user_data.get("games_played", 0) + 1,
            "lost_ncoin": user_data.get("lost_ncoin", 0) + lost_add
        })

        game_result_text = (
            f"<b>{username}</b>\n"
            f"🏀 <b>{header}</b>\n"
            "• • • • • • • • •\n"
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
        await query.edit_message_text(text=text, reply_markup=get_football_choice_keyboard(), parse_mode="HTML")

    elif query.data and query.data.startswith("football_setbet_"):
        new_bet = int(query.data.split("_")[2])
        await db_update(user_id, {"current_bet": new_bet})
        text = (
            f"<b>{username}</b>\n"
            "⚽ <b>Футбол · выбери исход!</b>\n"
            "• • • • • • • • • •\n"
            f"💸 <b>Ставка:</b> <code>{new_bet} ncoin</code>"
        )
        await query.edit_message_text(text=text, reply_markup=get_football_choice_keyboard(), parse_mode="HTML")

    elif query.data in ("football_bet_hit", "football_bet_miss"):
        bet = int(user_data["current_bet"])
        balance = int(user_data["ncoin"])
        
        if balance < bet:
            await context.bot.send_message(chat_id=query.message.chat_id, text="❌ <b>Недостаточно ncoin</b>", parse_mode="HTML")
            return
            
        balance -= bet
        user_choice = "гол" if query.data == "football_bet_hit" else "мимо"
        dice_msg = await context.bot.send_dice(chat_id=query.message.chat_id, emoji="⚽")
        value = dice_msg.dice.value
        is_hit = value in [3, 4, 5]
        outcome = "гол" if is_hit else "мимо"

        win = (user_choice == "гол" and is_hit) or (user_choice == "мимо" and not is_hit)
        multiplier = 1.6 if user_choice == "гол" else 2.4

        if win:
            reward = int(bet * multiplier)
            balance += reward
            reward_text = f"💰 <b>Выиграли:</b> <code>x{multiplier} / {reward} ncoin</code>"
            header = "⚽ Победа! 🎉"
            lost_add = 0
        else:
            reward_text = "💰 <b>Выиграли:</b> <code>0 ncoin</code>"
            header = "⚽ Проиграли!"
            lost_add = bet

        await db_update(user_id, {
            "ncoin": balance,
            "games_played": user_data.get("games_played", 0) + 1,
            "lost_ncoin": user_data.get("lost_ncoin", 0) + lost_add
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

    # --------------- ПРОФИЛЬ ---------------
    elif query.data == "open_profile":
        ncoin_bal = user_data.get("ncoin", 10000)
        nmp_bal = user_data.get("nmp", 0)
        games_played = user_data.get("games_played", 0)
        won_duels = user_data.get("won_duels", 0)
        lost_ncoin = user_data.get("lost_ncoin", 0)
        reg_date = user_data.get("reg_date", "неизвестно")

        profile_text = f"""<b>{username}</b>
👤 Профиль

🆔 ID: <code>{user_id}</code>
👤 Юзернейм: <code>{username}</code>
• • • • • • • • • • • • • • • • • • •
💰 Баланс: <code>{ncoin_bal} nCoin</code>
💰 Баланс: <code>{nmp_bal} nMP</code>
• • • • • • • • • • • • • • • • • • •
💣 Сыграно игр: <code>{games_played}</code>
⚔️ Выиграно дуэлей: <code>{won_duels}</code>
🏆 Проиграно nCoin: <code>{format_number(lost_ncoin)} nCoin</code>
• • • • • • • • • • • • • • • • • • •
📅 Дата регистрации: <code>{reg_date}</code>"""
        
        await query.edit_message_text(text=profile_text, reply_markup=get_profile_keyboard(), parse_mode="HTML")

    elif query.data == "open_inventory":
        inventory_text = f"""<b>{username}</b>
📦 Инвентарь
• • • • • • • • • • • • • • • • • • •
Здесь отображаются все ваши предметы – как обычные, так и коллекционные из маркетплейса.

*пусто*"""
        await query.edit_message_text(text=inventory_text, reply_markup=get_profile_keyboard(), parse_mode="HTML")

    elif query.data == "open_settings":
        settings_text = f"""<b>{username}</b>
⚙️ Настройки профиля
• • • • • • • • • • • • • • • • • • •
В этом разделе вы можете управлять своим профилем: включать режим «инкогнито», менять никнейм, настраивать уведомления, доступ к RP-командам, а также выбирать язык."""
        await query.edit_message_text(text=settings_text, reply_markup=get_profile_keyboard(), parse_mode="HTML")

    elif query.data == "open_titles":
        titles_text = f"""<b>{username}</b>
🏆 МОИ ТИТУЛЫ • 0
• • • • • • • • • • • • • • • • • • •
*пусто*
• • • • • • • • • • • • • • • • • • •
Коллекция ваших титулов. Можно выбрать один для отображения в профиле."""
        await query.edit_message_text(text=titles_text, reply_markup=get_profile_keyboard(), parse_mode="HTML")

    elif query.data == "open_vitrina":
        vitrina_text = f"""<b>{username}</b>
🛍️ НАСТРОЙКИ ВИТРИНЫ
• • • • • • • • • • • • • • • • • • •
🎁 Вы можете настроить, кто видит вашу витрину подарков:
├ 🟢 подарок в витрине видно всем
└ 🔴 подарок в витрине скрыт от других

*пусто*"""
        await query.edit_message_text(text=vitrina_text, reply_markup=get_profile_keyboard(), parse_mode="HTML")

    # --------------- Изменение ставки ---------------
    elif query.data == "change_bet":
        user_states[user_id] = "awaiting_bet"
        await context.bot.send_message(chat_id=query.message.chat_id, text="✍️ <b>Введите новую ставку (числом):</b>", parse_mode="HTML")

    # --------------- Пустые заглушки для новых игр ---------------
    elif query.data.endswith("_stub"):
        await context.bot.send_message(chat_id=query.message.chat_id, text="🚧 Этот режим игры сейчас находится в активной разработке!", parse_mode="HTML")


# -----------------------
# Текстовые сообщения и Игры по командам
# -----------------------
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    raw_text = update.message.text or ""
    clean_text = raw_text.strip().lower()
    
    # 1. Запрос баланса / профиля по тексту ("баланс" / "б")
    if clean_text in ["баланс", "б", "balance", "b", "профиль", "profile"]:
        user_data = await db_get_or_create(user_id, user.username)
        ncoin_bal = user_data.get("ncoin", 10000)
        games_played = user_data.get("games_played", 0)
        lost_ncoin = user_data.get("lost_ncoin", 0)
        won_duels = user_data.get("won_duels", 0)
        
        profile_text = (
            f"<b>{user.first_name}</b>\n"
            f"{raw_text}\n\n"
            f"💰 <b>Баланс:</b> <code>{ncoin_bal} nCoin</code>\n"
            f"• • • • • • • • • • • • • • • • • • •\n"
            f"💣 <b>Сыграно игр:</b> <code>{games_played}</code>\n"
            f"⚔️ <b>Выиграно дуэлей:</b> <code>{won_duels}</code>\n"
            f"🏆 <b>Проиграно nCoin:</b> <code>{format_number(lost_ncoin)}</code>"
        )
        await update.message.reply_text(profile_text, parse_mode="HTML")
        return

    # 2. Игры через Текстовые Команды
    match = re.match(r'^/(bowling|slots|dice|darts|buckshot|pp|coin|roulette)\s*(\d+)?', clean_text)
    if not match:
        match = re.match(r'^(боулинг|слоты|кубик|дартс|рулетка|монета)\s+(\d+)', clean_text)

    if match:
        cmd = match.group(1)
        bet_str = match.group(2)
        
        user_data = await db_get_or_create(user_id, user.username)
        bet = int(bet_str) if bet_str else user_data["current_bet"]
        balance = user_data["ncoin"]
        
        if balance < bet:
            await update.message.reply_text("❌ <b>У вас недостаточно ncoin для этой ставки!</b>", parse_mode="HTML")
            return
            
        balance -= bet
        await db_update(user_id, {"ncoin": balance, "games_played": user_data.get("games_played", 0) + 1})

        # --- Игра: Русская Рулетка ---
        if cmd in ["buckshot", "pp", "рулетка"]:
            is_dead = random.choice([True, False, False, False, False, False])
            if is_dead:
                await db_update(user_id, {"lost_ncoin": user_data.get("lost_ncoin", 0) + bet})
                res = f"💥 <b>БАБАХ! Вы застрелились.</b> Проиграно: <code>{bet} ncoin</code>"
            else:
                win = int(bet * 1.2)
                await db_update(user_id, {"ncoin": balance + win})
                res = f"🔫 *Клик!* <b>Барабан пуст. Вы выжили!</b>\nВыигрыш: <code>{win} ncoin</code>"
            await update.message.reply_text(res, parse_mode="HTML")
            return

        # --- Игра: Орел и Решка (Coin) ---
        elif cmd in ["coin", "монета"]:
            choice = "орел" if "орел" in clean_text or "heads" in clean_text else "решка"
            outcome = random.choice(["орел", "решка"])
            if choice == outcome:
                win = int(bet * 1.95)
                await db_update(user_id, {"ncoin": balance + win})
                res = f"🌑 Выпала <b>{outcome}</b>! <b>Вы выиграли!</b>\nВыигрыш: <code>{win} ncoin</code>"
            else:
                await db_update(user_id, {"lost_ncoin": user_data.get("lost_ncoin", 0) + bet})
                res = f"🌑 Выпала <b>{outcome}</b>! Вы проиграли <code>{bet} ncoin</code>."
            await update.message.reply_text(res, parse_mode="HTML")
            return

        # --- Интерактивные Telegram-Dice Игры ---
        emoji = "🎲"
        if cmd in ["bowling", "боулинг"]: emoji = "🎳"
        elif cmd in ["slots", "слоты"]: emoji = "🎰"
        elif cmd in ["darts", "дартс"]: emoji = "🎯"
        
        dice_msg = await context.bot.send_dice(chat_id=update.message.chat_id, emoji=emoji)
        val = dice_msg.dice.value
        
        multiplier = 0.0
        if emoji == "🎳":
            mults = {1: 0.0, 2: 0.5, 3: 1.0, 4: 1.5, 5: 2.0, 6: 3.5}
            multiplier = mults.get(val, 1.0)
        elif emoji == "🎰":
            if val in [1, 22, 43, 64]: multiplier = 15.0
            elif val in [16, 32, 48]: multiplier = 5.0
            elif val in [2, 3, 4, 10]: multiplier = 1.5
        elif emoji == "🎯":
            mults = {1: 0.0, 2: 0.5, 3: 1.0, 4: 1.8, 5: 2.5, 6: 5.0}
            multiplier = mults.get(val, 0.0)
        else:
            multiplier = 2.0 if val >= 4 else 0.0

        win_sum = int(bet * multiplier)
        lost_add = bet if win_sum == 0 else 0
        
        await db_update(user_id, {"ncoin": balance + win_sum, "lost_ncoin": user_data.get("lost_ncoin", 0) + lost_add})
        
        res_text = f"🎉 <b>Выиграли {win_sum} ncoin!</b>" if win_sum > 0 else "😔 <b>Ставка не сыграла.</b>"
        await update.message.reply_text(f"{res_text}\n💰 <b>Баланс:</b> <code>{balance + win_sum} ncoin</code>", parse_mode="HTML")
        return

    # 3. Изменение ставки
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
# Запуск
# -----------------------
def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("game", game_command if 'game_command' in globals() else start_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    # --- Настройка меню команд в Telegram Меню ---
    # Бот автоматически зарегистрирует эти три команды в синей кнопке
    application.bot.set_my_commands([
        BotCommand("start", "🚀 Запустить бота"),
        BotCommand("game", "🎮 Открыть игровое меню"),
        BotCommand("profile", "👤 Мой профиль")
    ])

    logger.info("Бот успешно запущен на Railway!")
    application.run_polling()

if __name__ == "__main__":
    main()
