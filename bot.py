import re
import os
import json
import logging
import httpx
import random
from datetime import datetime, timedelta
from typing import Dict, Any, List
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
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
ADMIN_ID = 7727345054  # Твой Telegram ID для админ-панели
IMAGE_URL = "https://i.ibb.co/jPJjTDBv/1000093316.jpg"

SUPABASE_URL = "https://gyjwzifhfxrojwjioapp.supabase.co/rest/v1/"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd5and6aWZoZnhyb2p3amlvYXBwIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MzQxNDcxMywiZXhwIjoyMDk4OTkwNzEzfQ.xjicAYNFaI9iTA3PlHvM2L_10r38gJSIlwmopy_3O70"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# -----------------------
# Логирование
# -----------------------
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------
# Локальная память (Fallback)
# -----------------------
user_states: Dict[int, Dict[str, Any]] = {}
LOCAL_DB: Dict[int, Dict[str, Any]] = {}
LOCAL_DEPOSITS: List[Dict[str, Any]] = []
DEPOSIT_FILE = "deposits_cache.json"

FIGHTER_RACES = ["Вампир 🧛", "Орк-Вышибала 👹", "Эльф-Наемник 🧝", "Демон 😈"]
FIGHTER_NAMES = [
    "Дон Сильвио", "Бруно Бритва", "Винсент Клык", "Карл Ломатель", 
    "Сайлас Хакер", "Маркус Тень", "Люциус Горн", "Векс Смертоносный"
]

# Загрузка локальных депозитов
if os.path.exists(DEPOSIT_FILE):
    try:
        with open(DEPOSIT_FILE, "r", encoding="utf-8") as f:
            LOCAL_DEPOSITS = json.load(f)
    except Exception as e:
        logger.error(f"Ошибка загрузки депозитов: {e}")

def save_local_deposits():
    try:
        with open(DEPOSIT_FILE, "w", encoding="utf-8") as f:
            json.dump(LOCAL_DEPOSITS, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Ошибка сохранения депозитов: {e}")

# -----------------------
# Хелперы форматирования
# -----------------------
def format_number(val: int | float) -> str:
    val = int(val)
    if val >= 1_000_000_000: return f"{val / 1_000_000_000:.2f}b"
    if val >= 1_000_000: return f"{val / 1_000_000:.2f}kk"
    if val >= 1000: return f"{val / 1000:.2f}k"
    return str(val)

def parse_suffix_number(text: str) -> int | None:
    text = text.lower().strip().replace(" ", "")
    cleaned = re.sub(r'[^0-9.kmкм]', '', text)
    if not cleaned: return None
    mult = 1_000_000 if any(x in cleaned for x in ["kk", "m", "м"]) else 1000 if any(x in cleaned for x in ["k", "к"]) else 1
    cleaned = re.sub(r'[kmкм]', '', cleaned)
    try: return int(float(cleaned) * mult)
    except: return None

# -----------------------
# Работа с БД (Supabase REST)
# -----------------------
async def db_get_or_create(tg_id: int, username: str | None, referrer_id: int | None = None) -> Dict[str, Any]:
    current_time = datetime.now().strftime("%d-%m-%Y %H:%M")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{SUPABASE_URL}users?tg_id=eq.{tg_id}", headers=HEADERS, timeout=6.0)
            data = r.json()
            if isinstance(data, list) and data: return data[0]
            new_user = {
                "tg_id": tg_id, "username": username or "Игрок", "ncoin": 10000, "nmp": 0, 
                "reg_date": current_time, "current_bet": 10, "games_played": 0, "lost_ncoin": 0,
                "missions_completed": 0, "painting_fragments": 0, "completed_paintings": 0,
                "referrer": referrer_id, "ref_reward_paid": False
            }
            r2 = await client.post(f"{SUPABASE_URL}users", json=new_user, headers=HEADERS, timeout=6.0)
            await db_generate_fighter(tg_id, "Обычный")
            return r2.json()[0] if r2.status_code == 201 else new_user
    except: 
        if tg_id not in LOCAL_DB:
            LOCAL_DB[tg_id] = {"tg_id": tg_id, "username": username or "Игрок", "ncoin": 10000, "nmp": 0, "current_bet": 10, "games_played": 0, "won_duels": 0, "lost_ncoin": 0, "reg_date": current_time, "referrer": referrer_id, "ref_reward_paid": False, "painting_fragments": 0, "completed_paintings": 0, "missions_completed": 0}
        return LOCAL_DB[tg_id]

async def db_update(tg_id: int, updates: Dict[str, Any]) -> None:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.patch(f"{SUPABASE_URL}users?tg_id=eq.{tg_id}", json=updates, headers=HEADERS, timeout=6.0)
            data = r.json()
            user_data = data[0] if isinstance(data, list) and data else None
            if user_data:
                games = user_data.get("games_played", 0)
                referrer = user_data.get("referrer")
                paid = user_data.get("ref_reward_paid", False)
                if games >= 1 and referrer and not paid:
                    await db_add_ref_reward(referrer, 100000)
                    await client.patch(f"{SUPABASE_URL}users?tg_id=eq.{tg_id}", json={"ref_reward_paid": True}, headers=HEADERS, timeout=5.0)
    except: 
        if tg_id in LOCAL_DB: LOCAL_DB[tg_id].update(updates)

async def db_add_ref_reward(referrer_tg_id: int, amount: int) -> None:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{SUPABASE_URL}users?tg_id=eq.{referrer_tg_id}", headers=HEADERS, timeout=5.0)
            data = r.json()
            if isinstance(data, list) and data:
                new_bal = data[0].get("ncoin", 0) + amount
                await client.patch(f"{SUPABASE_URL}users?tg_id=eq.{referrer_tg_id}", json={"ncoin": new_bal}, headers=HEADERS, timeout=5.0)
    except Exception as e:
        logger.error(f"Ref reward fail: {e}")

async def db_get_fighters(tg_id: int) -> List[Dict[str, Any]]:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{SUPABASE_URL}fighters?user_id=eq.{tg_id}", headers=HEADERS, timeout=6.0)
            return r.json() if isinstance(r.json(), list) else []
    except: return []

async def db_generate_fighter(tg_id: int, rarity: str = "Обычный") -> Dict[str, Any]:
    race = random.choice(FIGHTER_RACES)
    name = f"{random.choice(FIGHTER_NAMES)} ({race.split()[0]})"
    m = {"Обычный": 1, "Редкий": 2, "Эпический": 3, "Легендарный": 5}.get(rarity, 1)
    
    fighter = {
        "user_id": tg_id, "name": name, "race": race, "rarity": rarity,
        "strength": random.randint(10, 30) * m, "stealth": random.randint(10, 30) * m,
        "magic": random.randint(10, 30) * m, "health": 100, "status": "idle"
    }
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{SUPABASE_URL}fighters", json=fighter, headers=HEADERS, timeout=6.0)
            if r.status_code == 201: return r.json()[0]
    except Exception as e:
        logger.error(f"Fighter gen fail: {e}")
    return fighter

async def db_get_top_users(order_by: str, limit: int = 10) -> List[Dict[str, Any]]:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{SUPABASE_URL}users?select=tg_id,username,ncoin,nmp&order={order_by}.desc&limit={limit}", headers=HEADERS, timeout=6.0)
            if r.status_code == 200 and isinstance(r.json(), list): return r.json()
    except: pass
    return sorted(LOCAL_DB.values(), key=lambda x: x.get(order_by, 0), reverse=True)[:limit]

# -----------------------
# Депозиты БД
# -----------------------
async def db_get_user_deposits(tg_id: int) -> List[Dict[str, Any]]:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{SUPABASE_URL}deposits?tg_id=eq.{tg_id}&is_active=eq.true", headers=HEADERS, timeout=5.0)
            if r.status_code == 200 and isinstance(r.json(), list): return r.json()
    except: pass
    return [d for d in LOCAL_DEPOSITS if d["tg_id"] == tg_id and d["is_active"]]

async def db_create_deposit(tg_id: int, amount: int, term_days: int, percent: float) -> Dict[str, Any]:
    start_time = datetime.now()
    end_time = start_time + timedelta(days=term_days)
    dep_data = {"tg_id": tg_id, "amount": amount, "term_days": term_days, "percent": percent, "start_time": start_time.strftime("%d-%m-%Y %H:%M"), "end_time": end_time.strftime("%d-%m-%Y %H:%M"), "is_active": True}
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{SUPABASE_URL}deposits", json=dep_data, headers=HEADERS, timeout=5.0)
            if r.status_code == 201:
                dep_data["id"] = r.json()[0].get("id", random.randint(1000, 9999))
                LOCAL_DEPOSITS.append(dep_data)
                save_local_deposits()
                return r.json()[0]
    except: pass
    dep_data["id"] = random.randint(10000, 99999)
    LOCAL_DEPOSITS.append(dep_data)
    save_local_deposits()
    return dep_data

async def db_close_deposit(dep_id: int) -> None:
    try:
        async with httpx.AsyncClient() as client:
            await client.patch(f"{SUPABASE_URL}deposits?id=eq.{dep_id}", json={"is_active": False}, headers=HEADERS, timeout=5.0)
    except: pass
    for d in LOCAL_DEPOSITS:
        if d.get("id") == dep_id:
            d["is_active"] = False
            break
    save_local_deposits()


# -----------------------
# Сборка Клавиатур (Новый компактный дизайн по ТЗ)
# -----------------------
def get_main_keyboard() -> InlineKeyboardMarkup:
    """Две кнопки в ряд, а последняя (досье) во всю ширину"""
    keyboard = [
        [
            InlineKeyboardButton("🏯 Моя База", callback_data="open_base"),
            InlineKeyboardButton("🍻 Вербовка (Gacha)", callback_data="open_gacha")
        ],
        [
            InlineKeyboardButton("🗺️ Вылазки", callback_data="open_missions"),
            InlineKeyboardButton("🏪 Черный рынок (P2P)", callback_data="open_market")
        ],
        [InlineKeyboardButton("👤 Досье профиля", callback_data="open_profile")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_base_keyboard(fighters: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    keyboard = []
    for f in fighters:
        if f["health"] < 100 and f["status"] == "idle":
            keyboard.append([InlineKeyboardButton(f"🏥 Лечить: {f['name']} (XP: {f['health']}/100)", callback_data=f"heal_fighter_{f['id']}")])
    keyboard.append([InlineKeyboardButton("◀️ В штаб", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

def get_missions_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("💰 Ограбление лавки (Простая)", callback_data="mission_start_easy")],
        [InlineKeyboardButton("😈 Ограбление Века (СУПЕР-МИССИЯ 3x)", callback_data="mission_start_super")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_market_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🖼️ Выставить картину", callback_data="market_sell_painting")],
        [InlineKeyboardButton("🛒 Купить картины игроков", callback_data="market_browse")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_deposit_terms_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1 д.", callback_data="dep_term_1"), InlineKeyboardButton("3 д.", callback_data="dep_term_3"), InlineKeyboardButton("7 д.", callback_data="dep_term_7")],
        [InlineKeyboardButton("15 д.", callback_data="dep_term_15"), InlineKeyboardButton("30 д.", callback_data="dep_term_30"), InlineKeyboardButton("60 д.", callback_data="dep_term_60")],
        [InlineKeyboardButton("◀️ назад", callback_data="back_to_main")]
    ])

def get_deposit_amount_keyboard(user_ncoin: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Все • {user_ncoin} m¢", callback_data="dep_amt_all")],
        [InlineKeyboardButton(f"{int(user_ncoin*0.1)} m¢", callback_data="dep_amt_10"), InlineKeyboardButton(f"{int(user_ncoin*0.25)} m¢", callback_data="dep_amt_25"), InlineKeyboardButton(f"{int(user_ncoin*0.5)} m¢", callback_data="dep_amt_50")],
        [InlineKeyboardButton("◀️ назад", callback_data="open_deposit_menu")]
    ])

def get_deposit_active_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Снять всё (досрочно) ⤵️", callback_data="dep_withdraw_all")],
        [InlineKeyboardButton("💳 Положить еще", callback_data="open_deposit_menu"), InlineKeyboardButton("◀️ назад", callback_data="back_to_main")]
    ])

def get_ref_keyboard(bot_username: str, user_id: int) -> InlineKeyboardMarkup:
    share_url = f"https://t.me/share/url?url=https://t.me/{bot_username}?start=ref_{user_id}&text=🎁 Присоединяйся к синдикату!"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Скопировать ссылку", callback_data="ref_copy_link_alert")],
        [InlineKeyboardButton("Поделиться ↩️", url=share_url)],
        [InlineKeyboardButton("◀️ назад", callback_data="back_to_main")]
    ])

# -----------------------
# Логика команд и сообщений
# -----------------------
async def game_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("<b>🏯 Теневой Штаб Синдиката</b>\nВыбери действие, Босс:", reply_markup=get_main_keyboard(), parse_mode="HTML")

async def deposit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_data = await db_get_or_create(user.id, user.username)
    active_deps = await db_get_user_deposits(user.id)
    
    if not active_deps:
        text = f"<b>{user.first_name}</b>\n🏦 <b>ВРЕМЕННЫЕ ДЕПОЗИТЫ</b>\n• • • • • • • • • • • • • • • • • • •\n<blockquote>ℹ️ Здесь вы можете вложить свои mCoin под проценты на фиксированный срок. При досрочном снятии возвращается только сумма без процентов.</blockquote>\n<b>Выбери срок депозита 👇</b>"
        await update.message.reply_text(text, reply_markup=get_deposit_terms_keyboard(), parse_mode="HTML")
    else:
        dep_list_str = ""
        for d in active_deps:
            dep_list_str += f"📅 До {d['end_time']} • {format_number(d['amount'])} m¢ ({d['percent']}%)\n"
        text = f"<b>{user.first_name}</b>\n🏦 <b>МОИ ДЕПОЗИТЫ • {len(active_deps)}</b>\n• • • • • • • • • •\n🟢 <b>Активные:</b>\n{dep_list_str}"
        await update.message.reply_text(text, reply_markup=get_deposit_active_keyboard(), parse_mode="HTML")

async def ref_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    bot_info = await context.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{user.id}"
    invited_count = 0
    earned = 0
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{SUPABASE_URL}users?referrer=eq.{user.id}", headers=HEADERS, timeout=5.0)
            data = res.json()
            if isinstance(data, list):
                invited_count = len(data)
                for p in data:
                    lost = p.get("lost_ncoin", 0) or 0
                    earned += int(lost * 0.02)
                    if p.get("ref_reward_paid", False): earned += 100000
    except: pass

    text = f"<b>👥 ПРИГЛАСИТЬ ДРУЗЕЙ</b>\n• • • • • • •\n🔗 Ссылка:\n<code>{link}</code>\n\n💵 Заработано: <code>{format_number(earned)} mCoin</code>\n👥 Рефералов: <code>{invited_count}</code>"
    await update.message.reply_text(text, reply_markup=get_ref_keyboard(bot_info.username, user.id), parse_mode="HTML")

async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        async with httpx.AsyncClient() as client:
            r1 = await client.get(f"{SUPABASE_URL}users?select=tg_id,username,ncoin&order=ncoin.desc&limit=10", headers=HEADERS, timeout=6.0)
            top_ncoin = r1.json() or []
            r2 = await client.get(f"{SUPABASE_URL}users?select=tg_id,username,nmp&order=nmp.desc&limit=10", headers=HEADERS, timeout=6.0)
            top_nmp = r2.json() or []
    except:
        top_ncoin, top_nmp = [], []

    text_ncoin = "💎 <b>ТОП по mCoin:</b>\n" + "\n".join([f"{i+1}. {p.get('username','Игрок')} | {format_number(p.get('ncoin',0))} m¢" for i, p in enumerate(top_ncoin)])
    text_nmp = "⭐ <b>ТОП по nMP:</b>\n" + "\n".join([f"{i+1}. {p.get('username') or 'Игрок'} | {p.get('nmp', 0)} nMP" for i, p in enumerate(top_nmp)])
    
    await update.message.reply_text(f"<b>🏆 МИРОВОЙ ТОП</b>\n\n{text_ncoin}\n{text_nmp}", parse_mode="HTML")

# -----------------------
# Callback обработчик
# -----------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id, username = query.from_user.id, query.from_user.username or "Игрок"
    user_data = await db_get_or_create(user_id, username)
    
    if query.data == "back_to_main":
        await query.edit_message_text("<b>🏯 Штаб-квартира Синдиката</b>", reply_markup=get_main_keyboard(), parse_mode="HTML")
        
    elif query.data == "open_profile":
        text = f"<b>{username}</b>\n👤 <b>Личное досье</b>\n\n🆔 ID: <code>{user_id}</code>\n💰 mCoin: <code>{format_number(user_data['ncoin'])}</code>\n⭐ nMP: <code>{user_data['nmp']}</code>\n🧩 Фрагментов картины: {user_data.get('painting_fragments', 0)}/20\n🖼️ Собрано картин Дона: {user_data.get('completed_paintings', 0)}"
        kb = []
        if user_data.get("painting_fragments", 0) >= 20:
            kb.append([InlineKeyboardButton("🖼️ Восстановить картину Дона", callback_data="craft_painting")])
        kb.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

    elif query.data == "craft_painting":
        if user_data.get("painting_fragments", 0) < 20: return
        await db_update(user_id, {"painting_fragments": user_data["painting_fragments"] - 20, "completed_paintings": user_data.get("completed_paintings", 0) + 1})
        await query.edit_message_text("🎨 <b>Картина 'Крестный Отец' собрана!</b> Она доступна в профиле и может быть выставлена на продажу.", reply_markup=get_main_keyboard(), parse_mode="HTML")

    elif query.data == "open_gacha":
        text = "<b>🍻 ВЕРБОВОЧНЫЙ ЦЕНТР</b>\n• • • • • • •\nКонтракт на наемника: 5,000 mCoin\nШансы: 🟢Обычный (60%), 🔵Редкий (25%), 🟣Эпик (12%), 🟡Легенда (3%)"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✍️ Нанять бойца (5к m¢)", callback_data="gacha_roll")], [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]])
        await query.edit_message_text(text=text, reply_markup=kb, parse_mode="HTML")

    elif query.data == "gacha_roll":
        if user_data["ncoin"] < 5000:
            await context.bot.send_message(chat_id=query.message.chat_id, text="❌ Мало mCoin!")
            return
        await db_update(user_id, {"ncoin": user_data["ncoin"] - 5000})
        roll = random.random() * 100
        rarity = "Легендарный" if roll < 3 else "Эпический" if roll < 15 else "Редкий" if roll < 40 else "Обычный"
        f = await db_generate_fighter(user_id, rarity)
        await query.edit_message_text(f"⚔️ <b>К банде присоединился:</b> {f['name']} ({f['rarity']})", reply_markup=get_main_keyboard(), parse_mode="HTML")

    elif query.data == "open_base":
        fighters = await db_get_fighters(user_id)
        base_text = "<b>🏯 ТВОЕ УБЕЖИЩЕ</b>\n\n" + "\n".join([f"▪️ {f['name']} [{f['rarity']}] - HP: {f['health']}/100 ({'🏥 капсула' if f['status'] == 'healing' else '🟢 готов'})" for f in fighters])
        await query.edit_message_text(text=base_text, reply_markup=get_base_keyboard(fighters), parse_mode="HTML")

    elif query.data.startswith("heal_fighter_"):
        fid = int(query.data.split("_")[2])
        async with httpx.AsyncClient() as client:
            await client.patch(f"{SUPABASE_URL}fighters?id=eq.{fid}", json={"status": "healing", "healing_start": datetime.now().isoformat()}, headers=HEADERS)
        await query.edit_message_text("🏥 Боец отправлен на лечение в био-капсулу (20 минут).", reply_markup=get_main_keyboard(), parse_mode="HTML")

    elif query.data == "open_missions":
        await query.edit_message_text("<b>🗺️ ВЫЛАЗКИ</b>", reply_markup=get_missions_keyboard(), parse_mode="HTML")

    elif query.data == "mission_start_easy":
        fighters = await db_get_fighters(user_id)
        ready = [f for f in fighters if f["status"] == "idle" and f["health"] >= 20]
        if not ready:
            await context.bot.send_message(chat_id=query.message.chat_id, text="❌ Нет готовых бойцов с HP > 20!")
            return
        f = random.choice(ready)
        new_hp = max(10, f["health"] - random.randint(15, 30))
        async with httpx.AsyncClient() as client:
            await client.patch(f"{SUPABASE_URL}fighters?id=eq.{f['id']}", json={"health": new_hp}, headers=HEADERS)
        reward = random.randint(500, 1500)
        mc = user_data.get("missions_completed", 0) + 1
        frags = user_data.get("painting_fragments", 0)
        got_frag = mc in [2, 5] or (mc > 5 and (mc - 5) % 3 == 0)
        if got_frag: frags = min(20, frags + 1)
        await db_update(user_id, {"ncoin": user_data["ncoin"] + reward, "missions_completed": mc, "painting_fragments": frags})
        
        txt = f"🎯 <b>Миссия успешна!</b>\n\nБоец: {f['name']}\n🩸 Урон: {f['health'] - new_hp} HP\n💰 Награда: +{reward} m¢"
        if got_frag: txt += "\n🧩 <b>Найден фрагмент картины Дона!</b>"
        await query.edit_message_text(txt, reply_markup=get_main_keyboard(), parse_mode="HTML")

    elif query.data == "mission_start_super":
        fighters = await db_get_fighters(user_id)
        ready = [f for f in fighters if f["status"] == "idle" and f["health"] >= 50]
        if len(ready) < 3:
            await context.bot.send_message(chat_id=query.message.chat_id, text="❌ Нужно минимум 3 бойца с HP >= 50!")
            return
        team = ready[:3]
        sum_stats = sum(f["strength"] + f["stealth"] + f["magic"] for f in team)
        chance = min(95, max(15, int((sum_stats / 250) * 85)))
        
        if random.randint(1, 100) <= chance:
            reward = max(15000, int(user_data["ncoin"] * 1.5))
            await db_update(user_id, {"ncoin": user_data["ncoin"] + reward})
            await query.edit_message_text(f"🔥 <b>УСПЕХ! Ограбление века совершено!</b>\nКуш: +{format_number(reward)} m¢", reply_markup=get_main_keyboard(), parse_mode="HTML")
        else:
            lost = int(user_data["ncoin"] * 0.5)
            await db_update(user_id, {"ncoin": user_data["ncoin"] - lost})
            async with httpx.AsyncClient() as client:
                for f in team: await client.delete(f"{SUPABASE_URL}fighters?id=eq.{f['id']}", headers=HEADERS)
            await query.edit_message_text(f"💀 <b>КАТАСТРОФА! Бойцы ликвидированы!</b>\nПотери: 3 бойца\nШтраф: -{format_number(lost)} m¢", reply_markup=get_main_keyboard(), parse_mode="HTML")

    # Депозиты
    elif query.data == "open_deposit_menu":
        await query.edit_message_text("🏦 <b>Выберите срок вклада:</b>", reply_markup=get_deposit_terms_keyboard(), parse_mode="HTML")

    elif query.data.startswith("dep_term_"):
        term = int(query.data.split("_")[2])
        percent = {1: 0.4, 3: 1.5, 7: 4.0, 15: 10.0, 30: 25.0, 60: 60.0}.get(term, 0.4)
        user_states[user_id] = {"state": "awaiting_dep", "term": term, "percent": percent}
        await query.edit_message_text(f"💰 <b>Депозит на {term} дн. ({percent}%)</b>\nУкажите сумму вклада:", reply_markup=get_deposit_amount_keyboard(user_data["ncoin"]), parse_mode="HTML")

    elif query.data.startswith("dep_amt_"):
        state_data = user_states.get(user_id)
        if not state_data or state_data.get("state") != "awaiting_dep": return
        fraction = query.data.split("_")[2]
        balance = user_data["ncoin"]
        amt = balance if fraction == "all" else int(balance * float(fraction)/100) if fraction in ["10", "25", "50"] else 10
        if amt <= 0 or balance < amt: return
        await db_update(user_id, {"ncoin": balance - amt})
        dep = await db_create_deposit(user_id, amt, state_data["term"], state_data["percent"])
        user_states[user_id] = None
        await query.edit_message_text(f"✅ <b>Депозит принят!</b>\nСумма: {amt} m¢\nСрок: {state_data['term']}д.\nДо: {dep['end_time']}", reply_markup=get_main_keyboard(), parse_mode="HTML")

    elif query.data == "dep_withdraw_all":
        deps = await db_get_user_deposits(user_id)
        if not deps: return
        refund = sum(d["amount"] for d in deps)
        for d in deps: await db_close_deposit(d["id"])
        await db_update(user_id, {"ncoin": user_data["ncoin"] + refund})
        await query.answer(f"Вклады закрыты. На баланс возвращено {refund} m¢ (без %)", show_alert=True)
        await query.edit_message_text("<b>🏯 Штаб</b>", reply_markup=get_main_keyboard(), parse_mode="HTML")

    elif query.data == "open_market":
        await query.edit_message_text("<b>🏪 ЧЕРНЫЙ РЫНОК</b>", reply_markup=get_market_keyboard(), parse_mode="HTML")

    elif query.data == "market_sell_painting":
        if user_data.get("completed_paintings", 0) <= 0:
            await context.bot.send_message(chat_id=query.message.chat_id, text="❌ У вас нет картин для продажи!")
            return
        user_states[user_id] = {"state": "awaiting_market_price"}
        await context.bot.send_message(chat_id=query.message.chat_id, text="✍️ Введите желаемую цену картины в mCoin:")

    elif query.data == "market_browse":
        async with httpx.AsyncClient() as client: r = await client.get(f"{SUPABASE_URL}market?is_active=eq.true&limit=5", headers=HEADERS)
        lots = r.json() or []
        if not lots:
            await query.edit_message_text("🏪 На рынке пока нет активных предложений.", reply_markup=get_main_keyboard(), parse_mode="HTML")
            return
        txt = "<b>🏪 ЛОТЫ НА РЫНКЕ:</b>\n\n"
        kb = []
        for l in lots:
            txt += f"▪️ Картина Дона от {l['seller_id']} | Цена: {format_number(l['price'])} m¢\n"
            kb.append([InlineKeyboardButton(f"Купить за {format_number(l['price'])} m¢", callback_data=f"buy_lot_{l['id']}")])
        kb.append([InlineKeyboardButton("◀️ Назад", callback_data="open_market")])
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

    elif query.data.startswith("buy_lot_"):
        lid = int(query.data.split("_")[2])
        async with httpx.AsyncClient() as client: r = await client.get(f"{SUPABASE_URL}market?id=eq.{lid}", headers=HEADERS)
        lot = r.json()[0]
        price = lot["price"]
        if user_data["ncoin"] < price:
            await context.bot.send_message(chat_id=query.message.chat_id, text="❌ Недостаточно mCoin!")
            return
        tax = int(price * 0.10)
        await db_update(user_id, {"ncoin": user_data["ncoin"] - price, "completed_paintings": user_data.get("completed_paintings", 0) + 1})
        # Продавец
        async with httpx.AsyncClient() as client:
            rs = await client.get(f"{SUPABASE_URL}users?tg_id=eq.{lot['seller_id']}", headers=HEADERS)
            seller = rs.json()[0]
            await client.patch(f"{SUPABASE_URL}users?tg_id=eq.{lot['seller_id']}", json={"ncoin": seller["ncoin"] + price - tax}, headers=HEADERS)
            # Налог админу
            ra = await client.get(f"{SUPABASE_URL}users?tg_id=eq.{ADMIN_ID}", headers=HEADERS)
            if ra.status_code == 200 and ra.json():
                await client.patch(f"{SUPABASE_URL}users?tg_id=eq.{ADMIN_ID}", json={"ncoin": ra.json()[0]["ncoin"] + tax}, headers=HEADERS)
            await client.patch(f"{SUPABASE_URL}market?id=eq.{lid}", json={"is_active": False}, headers=HEADERS)
        await query.edit_message_text("✅ Картина успешно куплена! Лот закрыт.", reply_markup=get_main_keyboard(), parse_mode="HTML")

# -----------------------
# КРАШ И ТЕКСТОВЫЙ ОБРАБОТЧИК
# -----------------------
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    raw_text = update.message.text or ""
    tokens = raw_text.strip().split()
    if not tokens: return
    first_word = tokens[0].lower()

    # 1. Изменение ставки
    if user_states.get(user_id, {}).get("state") == "awaiting_market_price":
        price = parse_suffix_number(raw_text)
        user_states[user_id] = None
        user_data = await db_get_or_create(user_id, user.username)
        if not price or price <= 0: return
        await db_update(user_id, {"completed_paintings": user_data["completed_paintings"] - 1})
        async with httpx.AsyncClient() as client:
            await client.post(f"{SUPABASE_URL}market", json={"seller_id": user_id, "item_type": "painting", "price": price, "is_active": True}, headers=HEADERS)
        await update.message.reply_text(f"✅ Картина успешно выставлена за {format_number(price)} m¢! (Синдикат возьмет 10% налога при покупке)")
        return

    # 2. Текстовый КРАШ ИГРА
    if first_word in ["краш", "crash", "кр"]:
        user_data = await db_get_or_create(user_id, user.username)
        bet = user_data["current_bet"]
        target = 2.0
        if len(tokens) >= 3:
            parsed_bet = parse_suffix_number(tokens[1])
            if parsed_bet is not None: bet = parsed_bet
            try: target = float(tokens[2])
            except: pass
        elif len(tokens) == 2:
            if "." in tokens[1] or (tokens[1].isdigit() and float(tokens[1]) < 100.0):
                try: target = float(tokens[1])
                except: pass
            else:
                parsed_bet = parse_suffix_number(tokens[1])
                if parsed_bet is not None: bet = parsed_bet

        if user_data["ncoin"] < bet:
            await update.message.reply_text("❌ Недостаточно средств!")
            return
            
        await db_update(user_id, {"ncoin": user_data["ncoin"] - bet, "games_played": user_data.get("games_played", 0) + 1})
        crash_point = 1.00 if random.random() < 0.05 else round(0.99 / (1.0 - random.uniform(0.0, 0.95)), 2)
        
        if crash_point >= target:
            win = int(bet * target)
            await db_update(user_id, {"ncoin": user_data["ncoin"] - bet + win})
            res = f"✈️ <b>КРАШ</b>\n📈 Самолет улетел на: <b>{crash_point}x</b>\n✅ Вы вывели на <b>{target}x</b>!\nВыигрыш: <code>+{format_number(win)} m¢</code>"
        else:
            await db_update(user_id, {"lost_ncoin": user_data.get("lost_ncoin", 0) + bet})
            res = f"✈️ <b>КРАШ</b>\n📉 Самолет взорвался на: <b>{crash_point}x</b>\n❌ Вы не успели вывести авто-кэшаут на <b>{target}x</b>!\nПроиграно: <code>-{format_number(bet)} m¢</code>"
        await update.message.reply_text(res, parse_mode="HTML")

# -----------------------
# Команда INFO ℹ️
# -----------------------
async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = """<b>🕵️‍♂️ ДОБРО ПОЖАЛОВАТЬ В ТЕНЕВОЙ СИНДИКАТ!</b>
═════════════════════════════
Это текстовая ролевая стратегия, где вы — теневой босс фэнтези-мафии. 

🎯 <b>Как играть и с чего начать?</b>
1️⃣ <b>Вербовка:</b> Напишите `/game` и откройте меню. Зайдите в «🍻 Вербовка» и подпишите контракт. К вам присоединится первый боец!
2️⃣ <b>Вылазки:</b> Отправляйте бойцов в меню «🗺️ Вылазки». Бойцы будут получать опыт, приносить mCoin и терять HP.
3️⃣ <b>База:</b> Раненых бойцов лечите в «🏯 Моя База» — био-капсулы восстанавливают здоровье за 20 минут.
4️⃣ <b>Супер-миссии:</b> Ограбление Века требует 3 сильных бойцов. Будьте осторожны: при неудаче группа погибает навсегда, а вы теряете 50% денег!

🎨 <b>Легендарные картины Дона:</b>
Выполняя вылазки, вы будете находить **Фрагменты картин** (на 2, 5, 8, 11, 14, 17 миссиях). 
Соберите 20 фрагментов, склейте картину в Досье и выгодно продайте её на **Черном Рынке (P2P)** другим игрокам!

💰 <b>Временные вклады:</b>
Используйте команду `/deposit` для вкладов под высокий процент (до 60%!)."""
    await update.message.reply_text(text, parse_mode="HTML")

# -----------------------
# Административные команды
# -----------------------
async def give_cash(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID: return
    try:
        tid, amt = int(context.args[0]), int(context.args[1])
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{SUPABASE_URL}users?tg_id=eq.{tid}", headers=HEADERS)
            new_bal = r.json()[0]["ncoin"] + amt
            await client.patch(f"{SUPABASE_URL}users?tg_id=eq.{tid}", json={"ncoin": new_bal}, headers=HEADERS)
        await update.message.reply_text(f"✅ Начислено {format_number(amt)} mCoin пользователю {tid}")
    except Exception as e: await update.message.reply_text(f"Ошибка: {e}")

async def give_fighter_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID: return
    try:
        tid, rarity = int(context.args[0]), context.args[1]
        await db_generate_fighter(tid, rarity)
        await update.message.reply_text(f"✅ Выдан боец [{rarity}] пользователю {tid}")
    except Exception as e: await update.message.reply_text(f"Ошибка: {e}")

# -----------------------
# Запуск бота
# -----------------------
def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("game", game_command))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("deposit", deposit_command))
    app.add_handler(CommandHandler("ref", ref_command))
    app.add_handler(CommandHandler("top", top_command))
    app.add_handler(CommandHandler("give_cash", give_cash))
    app.add_handler(CommandHandler("give_fighter", give_fighter_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    app.bot.set_my_commands([
        BotCommand("start", "🚀 Запустить Синдикат"),
        BotCommand("game", "🎮 Меню Синдиката"),
        BotCommand("info", "ℹ️ Справка по игре"),
        BotCommand("deposit", "🏦 Вклады под проценты"),
        BotCommand("ref", "👥 Реферальная система"),
        BotCommand("top", "🏆 Топ игроков")
    ])
    
    logger.info("Бот Теневой Мафии успешно запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
