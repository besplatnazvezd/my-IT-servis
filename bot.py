import re
import logging
import httpx
import random
from datetime import datetime
from typing import Dict, Any, List
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


# Helper для красивого форматирования чисел (1000 -> 1.00k, 1000000 -> 1.00kk)
def format_number(val: int | float) -> str:
    val = int(val)
    if val >= 1_000_000_000:
        return f"{val / 1_000_000_000:.2f}b"
    elif val >= 1_000_000:
        return f"{val / 1_000_000:.2f}kk"
    elif val >= 1000:
        return f"{val / 1000:.2f}k"
    return str(val)


# Helper для парсинга сокращенных чисел типа "1к", "2.5kk", "10m"
def parse_suffix_number(text: str) -> int | None:
    text = text.lower().strip().replace(" ", "")
    if not text:
        return None
    cleaned = re.sub(r'[^0-9.kmкм]', '', text)
    if not cleaned:
        return None
    
    multiplier = 1
    if "kk" in cleaned or "m" in cleaned or "м" in cleaned:
        multiplier = 1_000_000
        cleaned = cleaned.replace("kk", "").replace("m", "").replace("м", "")
    elif "k" in cleaned or "к" in cleaned:
        multiplier = 1000
        cleaned = cleaned.replace("k", "").replace("к", "")
    
    try:
        return int(float(cleaned) * multiplier)
    except ValueError:
        return None


# -----------------------
# Работа с БД (Supabase REST)
# -----------------------
async def db_get_or_create(tg_id: int, username: str | None, referrer_id: int | None = None) -> Dict[str, Any]:
    current_time = datetime.now().strftime("%d-%m-%Y %H:%M")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{SUPABASE_URL}users?tg_id=eq.{tg_id}", headers=HEADERS, timeout=6.0
            )
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
                "reg_date": current_time,
                "referrer": referrer_id,  # Кто пригласил
                "ref_reward_paid": False  # Выплачен ли бонус 100к пригласителю
            }
            r2 = await client.post(
                f"{SUPABASE_URL}users", json=new_user, headers=HEADERS, timeout=6.0
            )
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
                "reg_date": current_time,
                "referrer": referrer_id,
                "ref_reward_paid": False
            }
        return LOCAL_DB[tg_id]


async def db_update(tg_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.patch(
                f"{SUPABASE_URL}users?tg_id=eq.{tg_id}",
                json=updates,
                headers=HEADERS,
                timeout=6.0,
            )
            r.raise_for_status()
            data = r.json()
            
            # Логика выплаты реферального вознаграждения за активность друга
            user_data = data[0] if isinstance(data, list) and data else None
            if user_data:
                games = user_data.get("games_played", 0)
                referrer = user_data.get("referrer")
                paid = user_data.get("ref_reward_paid", False)
                
                if games >= 1 and referrer and not paid:
                    # Начисляем пригласителю 100 000 nCoin
                    await db_add_ref_reward(referrer, 100000)
                    # Помечаем в БД, что бонус за этого друга выплачен
                    await client.patch(
                        f"{SUPABASE_URL}users?tg_id=eq.{tg_id}",
                        json={"ref_reward_paid": True},
                        headers=HEADERS,
                        timeout=5.0
                    )
            
            if isinstance(data, list) and data:
                return data[0]
            return {}
    except Exception as e:
        logger.error("Supabase update error: %s", e)
        if tg_id in LOCAL_DB:
            LOCAL_DB[tg_id].update(updates)
            return LOCAL_DB[tg_id]
        return {}


async def db_add_ref_reward(referrer_tg_id: int, amount: int) -> None:
    """Увеличивает баланс пригласителя на сумму бонуса."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{SUPABASE_URL}users?tg_id=eq.{referrer_tg_id}", headers=HEADERS, timeout=5.0
            )
            data = r.json()
            if isinstance(data, list) and data:
                ref_user = data[0]
                new_bal = ref_user.get("ncoin", 0) + amount
                await client.patch(
                    f"{SUPABASE_URL}users?tg_id=eq.{referrer_tg_id}",
                    json={"ncoin": new_bal},
                    headers=HEADERS,
                    timeout=5.0
                )
                logger.info(f"Реферальный бонус {amount} начислен пользователю {referrer_tg_id}")
    except Exception as e:
        logger.error(f"Ошибка начисления реф-бонуса: {e}")


async def db_get_top_users(order_by: str, limit: int = 10) -> List[Dict[str, Any]]:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{SUPABASE_URL}users?select=tg_id,username,ncoin,nmp&order={order_by}.desc&limit={limit}",
                headers=HEADERS,
                timeout=6.0,
            )
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list):
                return data
            return []
    except Exception as e:
        logger.error("Supabase get_top_users error: %s", e)
        if LOCAL_DB:
            sorted_users = sorted(
                LOCAL_DB.values(), key=lambda x: x.get(order_by, 0), reverse=True
            )
            return sorted_users[:limit]
        return []


# -----------------------
# Клавиатуры
# -----------------------

def get_start_keyboard(bot_username: str) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("Играть 🕹️", callback_data="play_game")],
        [
            InlineKeyboardButton(
                "➕ Добавить бота в чат", url=f"https://t.me/{bot_username}?startgroup=true"
            )
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


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
            InlineKeyboardButton("🚀 Краш", callback_data="info_crash"),
            InlineKeyboardButton("Монета 🪙", callback_data="info_coin"),
        ],
        [
            InlineKeyboardButton("🎲🎲 Кости", callback_data="info_dice"),
            InlineKeyboardButton("Рулетка 🎱", callback_data="info_roulette"),
        ],
        [
            InlineKeyboardButton("🔮 Фортуна", callback_data="game_fortune_stub"),
            InlineKeyboardButton("Сундук 🧰", callback_data="game_chest_stub"),
        ],
        [
            InlineKeyboardButton("🎈 Шар", callback_data="game_balloon_stub"),
            InlineKeyboardButton("Рыбалка 🎣", callback_data="game_fishing_stub"),
        ],
        [InlineKeyboardButton("🎫 Скретч", callback_data="game_scratch_stub")],
        [InlineKeyboardButton("Режимы 💣", callback_data="btn_modes")],
        [
            InlineKeyboardButton("👤 Профиль", callback_data="open_profile"),
            InlineKeyboardButton("✍️ Изменить ставку", callback_data="change_bet"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_modes_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("💣 Мины", callback_data="game_mines_stub"),
            InlineKeyboardButton("Алмазы 💎", callback_data="game_diamonds_stub"),
        ],
        [
            InlineKeyboardButton("🛕 Башня", callback_data="game_tower_stub"),
            InlineKeyboardButton("Золото ⚜️", callback_data="game_gold_stub"),
        ],
        [
            InlineKeyboardButton("🐸 Квак", callback_data="game_frog_stub"),
            InlineKeyboardButton("HiLo ↕️", callback_data="game_hilo_stub"),
        ],
        [
            InlineKeyboardButton("♣️ 21(Очко)", callback_data="game_21_stub"),
            InlineKeyboardButton("Пирамида 🔺", callback_data="game_pyramid_stub"),
        ],
        [InlineKeyboardButton("🥊 Арена", callback_data="game_arena_stub")],
        [InlineKeyboardButton("🚀 Быстрые", callback_data="btn_fast")],
        [
            InlineKeyboardButton("👤 Профиль", callback_data="open_profile"),
            InlineKeyboardButton("✍️ Изменить ставку", callback_data="change_bet"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ назад", callback_data="play_game")]])


def get_profile_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("📦 Инвентарь", callback_data="open_inventory"),
            InlineKeyboardButton("⚙️ Настройки", callback_data="open_settings"),
        ],
        [
            InlineKeyboardButton("🏆 Титулы", callback_data="open_titles"),
            InlineKeyboardButton("🛍️ Витрина", callback_data="open_vitrina"),
        ],
        [InlineKeyboardButton("◀️ Назад", callback_data="play_game")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_game_action_keyboard(play_cb: str) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("Играть сейчас ⚡️", callback_data=play_cb)],
        [InlineKeyboardButton("◀️ назад", callback_data="play_game")],
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


def get_ref_keyboard(bot_username: str, user_id: int) -> InlineKeyboardMarkup:
    share_url = f"https://t.me/share/url?url=https://t.me/{bot_username}?start=ref_{user_id}&text=🎁 Присоединяйся к Мины Бот! Получи 10'000 nCoin на старт!"
    keyboard = [
        [InlineKeyboardButton("📋 Скопировать ссылку", callback_data="ref_copy_link_alert")],
        [
            InlineKeyboardButton("🏆 Топ рефералов", callback_data="ref_top_stub"),
            InlineKeyboardButton("Мои рефералы 🐣", callback_data="ref_list_stub")
        ],
        [InlineKeyboardButton("Поделиться ↩️", url=share_url)],
        [InlineKeyboardButton("◀️ назад", callback_data="play_game")]
    ]
    return InlineKeyboardMarkup(keyboard)


# -----------------------
# Отправка игрового меню (общая функция)
# -----------------------
async def _send_game_menu(
    user_id: int,
    username: str,
    user_data: Dict[str, Any],
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int | None = None,
    is_callback: bool = True,
    keyboard_type: str = "fast"
) -> None:
    text = (
        "<b>🎮 ДАВАЙ НАЧНЕМ ИГРАТЬ!</b>\n\n"
        "💰 <b>Баланс:</b>\n"
        f"├ 💎 <code>{user_data['ncoin']} ncoin</code>\n"
        f"└ ⭐ <code>{user_data['nmp']} nmp</code>\n\n"
        f"💸 <b>Ставка:</b> <code>{user_data['current_bet']} ncoin</code>\n\n"
        "👇 Выбери игру и начинай!"
    )
    
    keyboard = get_fast_keyboard() if keyboard_type == "fast" else get_modes_keyboard()

    if is_callback and message_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
        except Exception:
            await context.bot.send_message(
                chat_id=chat_id, text=text, reply_markup=keyboard, parse_mode="HTML"
            )
    else:
        await context.bot.send_message(
            chat_id=chat_id, text=text, reply_markup=keyboard, parse_mode="HTML"
        )


# -----------------------
# Обработчики команд бота
# -----------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    referrer_id = None
    if update.message and update.message.text:
        parts = update.message.text.split()
        if len(parts) > 1 and parts[1].startswith("ref_"):
            try:
                referrer_id = int(parts[1].split("_", 1)[1])
            except Exception:
                referrer_id = None

    user = update.effective_user
    await db_get_or_create(user.id, user.username, referrer_id)
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


async def game_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_data = await db_get_or_create(user.id, user.username)
    await _send_game_menu(
        user.id,
        user.username or user.first_name or "Игрок",
        user_data,
        context,
        update.effective_chat.id,
        is_callback=False,
        keyboard_type="fast"
    )


async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    top_ncoin = await db_get_top_users("ncoin", 10)
    top_nmp = await db_get_top_users("nmp", 10)

    ncoin_leaderboard = []
    for i, p in enumerate(top_ncoin):
        username = p.get("username") or "Игрок"
        ncoin_leaderboard.append(
            f"{i+1}. 🏆 <a href='tg://user?id={p['tg_id']}'>{username}</a> | <code>{format_number(p['ncoin'])} m¢</code>"
        )

    nmp_leaderboard = []
    for i, p in enumerate(top_nmp):
        username = p.get("username") or "Игрок"
        nmp_leaderboard.append(
            f"{i+1}. ⭐️ <a href='tg://user?id={p['tg_id']}'>{username}</a> | <code>{format_number(p['nmp'])} nMP</code>"
        )

    text = (
        "<b>🏆 МИРОВОЙ ТОП ИГРОКОВ • ЗА ВСЕ ВРЕМЯ</b>\n\n"
        "💎 <b>ТОП по mCoin (nCoin):</b>\n"
        + "\n".join(ncoin_leaderboard)
        + "\n\n"
        "⭐ <b>ТОП по nMP:</b>\n"
        + "\n".join(nmp_leaderboard)
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def ref_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    bot_info = await context.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{user.id}"

    # Считаем рефералов в БД
    invited_count = 0
    earned = 0
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{SUPABASE_URL}users?referrer=eq.{user.id}", headers=HEADERS, timeout=5.0)
            data = res.json()
            if isinstance(data, list):
                invited_count = len(data)
                for p in data:
                    # Начисляем рефералу 2% от lost_ncoin друга
                    lost = p.get("lost_ncoin", 0) or 0
                    earned += int(lost * 0.02)
                    # Если другу выплатили 100k, добавляем в "заработано"
                    if p.get("ref_reward_paid", False):
                        earned += 100000
    except Exception as e:
        logger.error(f"Ошибка получения реф-данных: {e}")

    text = f"""<b>👥 ПРИГЛАСИТЬ ДРУЗЕЙ</b>
• • • • • • • • • • • • • • • • • • •
🎁 Приглашайте друзей по своей ссылке и получайте бонусы:
• 100'000 mCoin за каждого друга
• 2% от проигранных коинов друзей
• 1 вращение Spin (в разработке)

🔗 <b>Твоя ссылка:</b>
<code>{link}</code>

💵 <b>Уже заработано:</b>
└ <code>{format_number(earned)} mCoin</code>
👥 <b>Приглашено друзей:</b>
└ <code>{invited_count} чел.</code>

<blockquote>ℹ️ Чтобы друг был зачислен, он должен сыграть хотя бы одну игру в боте!</blockquote>"""

    await update.message.reply_text(text, reply_markup=get_ref_keyboard(bot_info.username, user.id), parse_mode="HTML")


# -----------------------
# Универсальный Обработчик Кнопок (CallbackQuery)
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

    if query.data == "ref_copy_link_alert":
        bot_info = await context.bot.get_me()
        link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
        await query.answer(f"Ссылка скопирована: {link}", show_alert=True)
        return

    # --------------- Навигация ---------------
    elif query.data in ["play_game", "btn_fast"]:
        await _send_game_menu(
            user_id, username, user_data, context, query.message.chat_id, query.message.message_id, is_callback=True, keyboard_type="fast"
        )

    elif query.data == "btn_modes":
        await _send_game_menu(
            user_id, username, user_data, context, query.message.chat_id, query.message.message_id, is_callback=True, keyboard_type="modes"
        )

    # --------------- Игры (Информационные экраны) ---------------
    elif query.data == "info_bowling":
        text = f"""<b>{username}</b>
<blockquote>🎳 <b>Боулинг</b> — это игра, в которой вам нужно сбить кегли, чтобы получить максимальный множитель.
📊 Лимиты: 10 - 1,000,000 ncoin</blockquote>
👥 {user_link}, чтобы начать игру, используй команду:

🎳 <code>/bowling [ставка]</code>"""
        await query.edit_message_text(text=text, reply_markup=get_game_action_keyboard("play_bowling_now"), parse_mode="HTML")

    elif query.data == "info_slots":
        text = f"""<b>{username}</b>
<blockquote>🎰 <b>Слоты</b> — это игра, где цель выбить три одинаковых символа на барабанах, запустив их вращение.
📊 Лимиты: 10 - 1,000,000 ncoin</blockquote>
👥 {user_link}, чтобы начать игру, используй команду:

🎰 <code>/slots [ставка]</code>"""
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

🔫 <code>/buckshot [ставка]</code>"""
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

    elif query.data == "info_crash":
        text = f"""<b>{username}</b>
<blockquote>✈️ <b>Краш (Crash)</b> — игра, в которой самолетик взлетает и увеличивает множитель ставки в реальном времени. Успейте нажать авто-кэшаут до того, как самолет упадет!
📊 Лимиты: 10 - 1,000,000 ncoin</blockquote>
👥 {user_link}, чтобы начать игру, отправь в чат сообщение формата:

✈️ <code>краш [ставка] [множитель]</code>

<b>Пример:</b> <code>краш 1000 1.5</code>
<b>Пример:</b> <code>crash 1к 2.00</code>"""
        await query.edit_message_text(text=text, reply_markup=get_back_keyboard(), parse_mode="HTML")

    # --------------- Прямой запуск игр с кнопок (для анимационных) ---------------
    elif query.data in [
        "play_bowling_now",
        "play_slots_now",
        "play_dice_now",
        "play_darts_now",
    ]:
        bet = user_data["current_bet"]
        balance = user_data["ncoin"]

        if balance < bet:
            await context.bot.send_message(
                chat_id=query.message.chat_id, text="❌ <b>Недостаточно ncoin для игры!</b>", parse_mode="HTML"
            )
            return

        await db_update(
            user_id,
            {"ncoin": balance - bet, "games_played": user_data.get("games_played", 0) + 1},
        )

        emoji_map = {
            "play_bowling_now": "🎳",
            "play_slots_now": "🎰",
            "play_dice_now": "🎲",
            "play_darts_now": "🎯",
        }
        emoji = emoji_map[query.data]

        dice_msg = await context.bot.send_dice(chat_id=query.message.chat_id, emoji=emoji)
        val = dice_msg.dice.value

        multiplier = 0.0
        if emoji == "🎳":
            mults = {1: 0.0, 2: 0.5, 3: 1.0, 4: 1.5, 5: 2.0, 6: 3.5}
            multiplier = mults.get(val, 1.0)
        elif emoji == "🎰":
            if val in [1, 22, 43, 64]:
                multiplier = 15.0
            elif val in [16, 32, 48]:
                multiplier = 5.0
            elif val in [2, 3, 4, 10]:
                multiplier = 1.5
        elif emoji == "🎲":
            multiplier = 2.0 if val >= 4 else 0.0
        elif emoji == "🎯":
            mults = {1: 0.0, 2: 0.5, 3: 1.0, 4: 1.8, 5: 2.5, 6: 5.0}
            multiplier = mults.get(val, 0.0)

        win_sum = int(bet * multiplier)
        new_bal = balance - bet + win_sum

        lost_add = bet if win_sum == 0 else 0
        await db_update(
            user_id, {"ncoin": new_bal, "lost_ncoin": user_data.get("lost_ncoin", 0) + lost_add}
        )

        result_text = f"🎉 <b>Выиграли {win_sum} ncoin!</b>" if win_sum > 0 else "😔 <b>Ставка не сыграла.</b>"
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"{result_text}\n💰 <b>Баланс:</b> <code>{new_bal} ncoin</code>",
            reply_markup=get_back_keyboard(),
            parse_mode="HTML",
        )

    elif query.data == "play_buckshot_now":
        bet = user_data["current_bet"]
        balance = user_data["ncoin"]
        if balance < bet:
            await context.bot.send_message(chat_id=query.message.chat_id, text="❌ <b>Недостаточно ncoin!</b>", parse_mode="HTML")
            return
        
        is_dead = random.choice([True, False, False, False, False, False])
        if is_dead:
            new_bal = balance - bet
            lost_add = bet
            res_header = "💥 <b>БАБАХ! Вы застрелились.</b>"
        else:
            win_sum = int(bet * 1.2)
            new_bal = balance + win_sum - bet
            lost_add = 0
            res_header = f"🔫 *Клик!* <b>Вы выжили!</b>\nВыиграно: <code>{win_sum} ncoin</code>"
            
        await db_update(user_id, {"ncoin": new_bal, "games_played": user_data.get("games_played", 0) + 1, "lost_ncoin": user_data.get("lost_ncoin", 0) + lost_add})
        await context.bot.send_message(chat_id=query.message.chat_id, text=res_header, reply_markup=get_back_keyboard(), parse_mode="HTML")

    elif query.data == "play_coin_now":
        bet = user_data["current_bet"]
        balance = user_data["ncoin"]
        if balance < bet:
            await context.bot.send_message(chat_id=query.message.chat_id, text="❌ <b>Недостаточно ncoin!</b>", parse_mode="HTML")
            return
        
        outcome = random.choice(["орел", "решка"])
        win_sum = int(bet * 1.95)
        new_bal = balance - bet + win_sum
        await db_update(user_id, {"ncoin": new_bal, "games_played": user_data.get("games_played", 0) + 1})
        await context.bot.send_message(chat_id=query.message.chat_id, text=f"🌑 Выпала <b>{outcome}</b>! <b>Вы выиграли {win_sum} ncoin!</b>", reply_markup=get_back_keyboard(), parse_mode="HTML")

    elif query.data == "play_roulette_now":
        bet = user_data["current_bet"]
        balance = user_data["ncoin"]
        if balance < bet:
            await context.bot.send_message(chat_id=query.message.chat_id, text="❌ <b>Недостаточно ncoin!</b>", parse_mode="HTML")
            return
        
        # Честное вращение
        outcome = random.choice(["красный", "черный"])
        win_sum = int(bet * 2)
        new_bal = balance - bet + win_sum
        await db_update(user_id, {"ncoin": new_bal, "games_played": user_data.get("games_played", 0) + 1})
        await context.bot.send_message(chat_id=query.message.chat_id, text=f"🎱 Выпало: <b>{outcome}</b>! Вы выиграли {win_sum} ncoin!", reply_markup=get_back_keyboard(), parse_mode="HTML")

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
            header = "🏀 Проиграли!"
            lost_add = bet

        await db_update(
            user_id,
            {
                "ncoin": balance,
                "games_played": user_data.get("games_played", 0) + 1,
                "lost_ncoin": user_data.get("lost_ncoin", 0) + lost_add,
            },
        )

        game_result_text = (
            f"<b>{username}</b>\n"
            f"🏀 <b>{header}</b>\n"
            "• • • • • • • • •\n"
            f"💸 <b>Ставка:</b> <code>{bet} ncoin</code>\n"
            f"🎲 <b>Выбрано:</b> <code>{user_choice}</code>\n"
            f"{reward_text}\n"
            f"⚡️ <b>Итог:</b> <code>{outcome}</code>"
        )
        await context.bot.send_message(
            chat_id=query.message.chat_id, text=game_result_text, reply_markup=get_basket_replay_keyboard(), parse_mode="HTML"
        )

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

        win = (user_choice == "гол" and is_hit) or (
            user_choice == "мимо" and not is_hit
        )
        multiplier = 1.6 if user_choice == "гол" else 2.4

        if win:
            reward = int(bet * multiplier)
            balance += reward
            reward_text = f"💰 <b>Выигрыш:</b> <code>x{multiplier} / {reward} ncoin</code>"
            header = "⚽ Победа! 🎉"
            lost_add = 0
        else:
            reward_text = "💰 <b>Выигрыш:</b> <code>0 ncoin</code>"
            header = "⚽ Проиграли!"
            lost_add = bet

        await db_update(
            user_id,
            {
                "ncoin": balance,
                "games_played": user_data.get("games_played", 0) + 1,
                "lost_ncoin": user_data.get("lost_ncoin", 0) + lost_add,
            },
        )

        game_result_text = (
            f"<b>{username}</b>\n"
            f"⚽ <b>{header}</b>\n"
            "• • • • • • • • •\n"
            f"💸 <b>Ставка:</b> <code>{bet} ncoin</code>\n"
            f"🎲 <b>Выбрано:</b> <code>{user_choice}</code>\n"
            f"{reward_text}\n"
            f"⚡️ <b>Итог:</b> <code>{outcome}</code>"
        )
        await context.bot.send_message(
            chat_id=query.message.chat_id, text=game_result_text, reply_markup=get_football_replay_keyboard(), parse_mode="HTML"
        )

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

        await query.edit_message_text(
            text=profile_text, reply_markup=get_profile_keyboard(), parse_mode="HTML"
        )

    elif query.data == "open_inventory":
        inventory_text = f"""<b>{username}</b>
📦 Инвентарь
• • • • • • • • • • • • • • • • • • •
Здесь отображаются все ваши предметы – как обычные, так и коллекционные из маркетплейса.

*пусто*"""
        await query.edit_message_text(
            text=inventory_text, reply_markup=get_profile_keyboard(), parse_mode="HTML"
        )

    elif query.data == "open_settings":
        settings_text = f"""<b>{username}</b>
⚙️ Настройки профиля
• • • • • • • • • • • • • • • • • • •
В этом разделе вы можете управлять своим профилем: включать режим «инкогнито», менять никнейм, настраивать уведомления, доступ к RP-командам, а также выбирать язык."""
        await query.edit_message_text(
            text=settings_text, reply_markup=get_profile_keyboard(), parse_mode="HTML"
        )

    elif query.data == "open_titles":
        titles_text = f"""<b>{username}</b>
🏆 МОИ ТИТУЛЫ • 0
• • • • • • • • • • • • • • • • • • •
*пусто*
• • • • • • • • • • • • • • • • • • •
Коллекция ваших титулов. Можно выбрать один для отображения в профиле."""
        await query.edit_message_text(
            text=titles_text, reply_markup=get_profile_keyboard(), parse_mode="HTML"
        )

    elif query.data == "open_vitrina":
        vitrina_text = f"""<b>{username}</b>
🛍️ НАСТРОЙКИ ВИТРИНЫ
• • • • • • • • • • • • • • • • • • •
🎁 Вы можете настроить, кто видит вашу витрину подарков:
├ 🟢 подарок в витрине видно всем
└ 🔴 подарок в витрине скрыт от других

*пусто*"""
        await query.edit_message_text(
            text=vitrina_text, reply_markup=get_profile_keyboard(), parse_mode="HTML"
        )

    # --------------- Изменение ставки ---------------
    elif query.data == "change_bet":
        user_states[user_id] = "awaiting_bet"
        await context.bot.send_message(
            chat_id=query.message.chat_id, text="✍️ <b>Введите новую ставку (числом):</b>", parse_mode="HTML"
        )

    # --------------- Заглушки ---------------
    elif query.data.endswith("_stub"):
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="🚧 Этот раздел сейчас находится в активной разработке!",
            parse_mode="HTML",
        )


# -----------------------
# Обработчик Текста (Текстовые Игры и Баланс)
# -----------------------
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    raw_text = update.message.text or ""
    tokens = raw_text.strip().split()
    if not tokens:
        return
        
    first_word = tokens[0].lower()

    # 1. Запрос баланса / профиля по тексту ("баланс" / "б")
    if first_word in ["баланс", "б", "balance", "b", "профиль", "profile"]:
        user_data = await db_get_or_create(user_id, user.username)
        ncoin_bal = user_data.get("ncoin", 10000)
        nmp_bal = user_data.get("nmp", 0)
        games_played = user_data.get("games_played", 0)
        won_duels = user_data.get("won_duels", 0)
        lost_ncoin = user_data.get("lost_ncoin", 0)
        reg_date = user_data.get("reg_date", "неизвестно")

        profile_text = (
            f"<b>{user.first_name}</b>\n"
            f"👤 Профиль\n\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"👤 Юзернейм: <code>{user.username or 'Не указан'}</code>\n"
            f"• • • • • • • • • • • • • • • • • • •\n"
            f"💰 Баланс: <code>{ncoin_bal} nCoin</code>\n"
            f"💰 Баланс: <code>{nmp_bal} nMP</code>\n"
            f"• • • • • • • • • • • • • • • • • • •\n"
            f"💣 Сыграно игр: <code>{games_played}</code>\n"
            f"⚔️ Выиграно дуэлей: <code>{won_duels}</code>\n"
            f"🏆 Проиграно nCoin: <code>{format_number(lost_ncoin)} nCoin</code>\n"
            f"• • • • • • • • • • • • • • • • • • •\n"
            f"📅 Дата регистрации: <code>{reg_date}</code>"
        )
        await update.message.reply_text(profile_text, reply_markup=get_profile_keyboard(), parse_mode="HTML")
        return

    # 2. Идентификация Игр по первому текстовому слову
    game_type = None
    if first_word in ["краш", "crash", "/crash"]:
        game_type = "crash"
    elif first_word in ["рулетка", "roulette", "/roulette"]:
        game_type = "roulette"
    elif first_word in ["монета", "coin", "/coin"]:
        game_type = "coin"
    elif first_word in ["buckshot", "pp", "рр", "рус.рулетка", "/buckshot", "/pp"]:
        game_type = "buckshot"
    elif first_word in ["боулинг", "bowling", "/bowling"]:
        game_type = "bowling"
    elif first_word in ["слоты", "slots", "/slots"]:
        game_type = "slots"
    elif first_word in ["кубик", "dice", "/dice"]:
        game_type = "dice"
    elif first_word in ["дартс", "darts", "/darts"]:
        game_type = "darts"

    if game_type:
        user_data = await db_get_or_create(user_id, user.username)
        bet = user_data["current_bet"]
        balance = user_data["ncoin"]
        
        # Парсим параметры в зависимости от игры
        extra_param = None
        
        if game_type == "crash":
            target_mult = 2.0
            if len(tokens) >= 3:
                # краш 1к 1.5
                parsed_bet = parse_suffix_number(tokens[1])
                if parsed_bet is not None:
                    bet = parsed_bet
                try:
                    target_mult = float(tokens[2])
                except ValueError:
                    target_mult = 2.0
            elif len(tokens) == 2:
                # краш 1.5 или краш 1к
                token_val = tokens[1]
                if "." in token_val or (token_val.replace(".", "").isdigit() and float(token_val) < 100.0):
                    try:
                        target_mult = float(token_val)
                    except ValueError:
                        target_mult = 2.0
                else:
                    parsed_bet = parse_suffix_number(token_val)
                    if parsed_bet is not None:
                        bet = parsed_bet
            
            if target_mult < 1.01: target_mult = 1.01
            if target_mult > 100.0: target_mult = 100.0
            extra_param = target_mult

        elif game_type in ["roulette", "coin"]:
            if len(tokens) >= 3:
                parsed_bet = parse_suffix_number(tokens[1])
                if parsed_bet is not None:
                    bet = parsed_bet
                extra_param = tokens[2].lower()
            elif len(tokens) == 2:
                token_val = tokens[1].lower()
                # Если второй токен — ставка, либо угадываемый цвет/сторона
                if token_val in ["к", "ч", "красный", "черный", "орел", "решка", "heads", "tails"] or token_val.isdigit():
                    extra_param = token_val
                else:
                    parsed_bet = parse_suffix_number(token_val)
                    if parsed_bet is not None:
                        bet = parsed_bet
            if not extra_param:
                extra_param = "красный" if game_type == "roulette" else "орел"

        else:
            # Для остальных игр просто берем ставку из 2 токена (если есть)
            if len(tokens) >= 2:
                parsed_bet = parse_suffix_number(tokens[1])
                if parsed_bet is not None:
                    bet = parsed_bet

        if balance < bet:
            await update.message.reply_text("❌ <b>У вас недостаточно ncoin для этой ставки!</b>", parse_mode="HTML")
            return

        # Списание баланса
        balance -= bet
        await db_update(user_id, {"ncoin": balance, "games_played": user_data.get("games_played", 0) + 1})

        # --- КРАШ ИГРА ✈️ ---
        if game_type == "crash":
            # Честная генерация краш-поинта (5% моментальный краш, иначе экспонента)
            if random.random() < 0.05:
                crash_point = 1.00
            else:
                crash_point = round(0.99 / (1.0 - random.uniform(0.0, 0.95)), 2)
                if crash_point < 1.01:
                    crash_point = 1.01
            
            win = crash_point >= extra_param
            if win:
                win_sum = int(bet * extra_param)
                new_bal = balance + win_sum
                await db_update(user_id, {"ncoin": new_bal})
                res = f"""✈️ <b>КРАШ (CRASH)</b>
• • • • • • • • • • • • • • • • • • •
📈 График взлетел до: <b>{crash_point}x</b>
✅ Вы успели забрать на <b>{extra_param}x</b>!

💰 Выигрыш: <code>+{format_number(win_sum)} m¢</code>
💸 Баланс: <code>{format_number(new_bal)} m¢</code>"""
            else:
                await db_update(user_id, {"lost_ncoin": user_data.get("lost_ncoin", 0) + bet})
                res = f"""✈️ <b>КРАШ (CRASH)</b>
• • • • • • • • • • • • • • • • • • •
📉 Самолёт улетел на: <b>{crash_point}x</b>
❌ Вы не успели вывести авто-кэшаут на <b>{extra_param}x</b>!

💰 Проиграно: <code>-{format_number(bet)} m¢</code>"""
            await update.message.reply_text(res, parse_mode="HTML")
            return

        # --- ЧЕСТНАЯ РУЛЕТКА 🎱 ---
        elif game_type == "roulette":
            rolled_val = random.randint(0, 36)
            RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
            
            if rolled_val == 0:
                rolled_color = "зеленый"
            elif rolled_val in RED_NUMBERS:
                rolled_color = "красный"
            else:
                rolled_color = "черный"

            multiplier = 0.0
            if extra_param in ["к", "красный", "red"] and rolled_color == "красный":
                multiplier = 2.0
            elif extra_param in ["ч", "черный", "black"] and rolled_color == "черный":
                multiplier = 2.0
            elif extra_param in ["з", "зеленый", "green", "0"] and rolled_val == 0:
                multiplier = 35.0
            elif extra_param.isdigit() and int(extra_param) == rolled_val:
                multiplier = 35.0

            if multiplier > 0:
                win_sum = int(bet * multiplier)
                new_bal = balance + win_sum
                await db_update(user_id, {"ncoin": new_bal})
                res = f"🎱 Выпало: <b>{rolled_val} ({rolled_color})</b>! <b>Вы выиграли!</b>\nВыигрыш: <code>{format_number(win_sum)} m¢</code>"
            else:
                await db_update(user_id, {"lost_ncoin": user_data.get("lost_ncoin", 0) + bet})
                res = f"🎱 Выпало: <b>{rolled_val} ({rolled_color})</b>! Вы проиграли <code>{format_number(bet)} m¢</code>."
            await update.message.reply_text(res, parse_mode="HTML")
            return

        # --- МОНЕТА (Орел/Решка) 🪙 ---
        elif game_type == "coin":
            choice = "орел" if extra_param in ["орел", "heads"] else "решка"
            outcome = random.choice(["орел", "решка"])
            if choice == outcome:
                win_sum = int(bet * 1.95)
                new_bal = balance + win_sum
                await db_update(user_id, {"ncoin": new_bal})
                res = f"🪙 Выпала <b>{outcome}</b>! Вы угадали!\nВыигрыш: <code>{format_number(win_sum)} m¢</code>"
            else:
                await db_update(user_id, {"lost_ncoin": user_data.get("lost_ncoin", 0) + bet})
                res = f"🪙 Выпала <b>{outcome}</b>! Вы проиграли <code>{format_number(bet)} m¢</code>."
            await update.message.reply_text(res, parse_mode="HTML")
            return

        # --- РУССКАЯ РУЛЕТКА (Buckshot) 🔫 ---
        elif game_type == "buckshot":
            is_dead = random.choice([True, False, False, False, False, False])
            if is_dead:
                await db_update(user_id, {"lost_ncoin": user_data.get("lost_ncoin", 0) + bet})
                res = f"💥 <b>БАБАХ! Вы застрелились.</b> Проиграно: <code>{format_number(bet)} m¢</code>"
            else:
                win_sum = int(bet * 1.2)
                await db_update(user_id, {"ncoin": balance + win_sum})
                res = f"🔫 *Клик!* <b>Барабан пуст. Вы выжили!</b>\nВыигрыш: <code>{format_number(win_sum)} m¢</code>"
            await update.message.reply_text(res, parse_mode="HTML")
            return

        # --- Телеграм-Кубики (Слоты, Боулинг, Дартс, Кубик) ---
        emoji_map = {
            "bowling": "🎳",
            "slots": "🎰",
            "darts": "🎯",
            "dice": "🎲"
        }
        emoji = emoji_map[game_type]
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

        await db_update(
            user_id, {"ncoin": balance + win_sum, "lost_ncoin": user_data.get("lost_ncoin", 0) + lost_add}
        )

        res_text = f"🎉 <b>Выиграли {format_number(win_sum)} m¢!</b>" if win_sum > 0 else "😔 <b>Ставка не сыграла.</b>"
        await update.message.reply_text(
            f"{res_text}\n💰 <b>Баланс:</b> <code>{format_number(balance + win_sum)} m¢</code>",
            parse_mode="HTML",
        )
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
            reply_markup=get_fast_keyboard(),
            parse_mode="HTML",
        )


# -----------------------
# Запуск бота
# -----------------------
def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("game", game_command))
    application.add_handler(CommandHandler("top", top_command))
    application.add_handler(CommandHandler("ref", ref_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
    )

    # --- Настройка меню команд в Telegram ---
    application.bot.set_my_commands(
        [
            BotCommand("start", "🚀 Запустить бота"),
            BotCommand("game", "🎮 Открыть игровое меню"),
            BotCommand("profile", "👤 Мой профиль"),
            BotCommand("top", "🏆 Топ игроков"),
            BotCommand("ref", "👥 Пригласить друзей"),
        ]
    )

    logger.info("Бот успешно собран и запущен на Railway!")
    application.run_polling()


if __name__ == "__main__":
    main()
