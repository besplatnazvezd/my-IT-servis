import re
import os
import json
import logging
import httpx
import random
from datetime import datetime
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

# ---------------------------------------------------------------------------
# НАСТРОЙКИ СЕТИ И ТОКЕНЫ
# ---------------------------------------------------------------------------
BOT_TOKEN = "8894416195:AAHZ4i0sTodK5AYKhqZfNIlrFBnlRTOiVR8"
ADMIN_ID = 7727345054
IMAGE_URL = "https://i.ibb.co/jPJjTDBv/1000093316.jpg"

SUPABASE_URL = "https://gyjwzifhfxrojwjioapp.supabase.co/rest/v1/"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd5and6aWZoZnhyb2p3amlvYXBwIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MzQxNDcxMywiZXhwIjoyMDk4OTkwNzEzfQ.xjicAYNFaI9iTA3PlHvM2L_10r38gJSIlwmopy_3O70"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния игроков
user_states: Dict[int, Dict[str, Any]] = {}
LOCAL_DB: Dict[int, Dict[str, Any]] = {}
LOCAL_DEPOSITS: List[Dict[str, Any]] = []
DEPOSIT_FILE = "space_deposits.json"

# Загрузка локальных данных
if os.path.exists(DEPOSIT_FILE):
    try:
        with open(DEPOSIT_FILE, "r", encoding="utf-8") as f:
            LOCAL_DEPOSITS = json.load(f)
    except Exception as e:
        logger.error(f"Error loading deposits: {e}")

def save_local_deposits():
    try:
        with open(DEPOSIT_FILE, "w", encoding="utf-8") as f:
            json.dump(LOCAL_DEPOSITS, f, ensure_ascii=False, indent=4)
    except: pass

# ---------------------------------------------------------------------------
# МАТЕМАТИКА И СИСТЕМА ФОРМАТИРОВАНИЯ
# ---------------------------------------------------------------------------
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

def get_market_prices() -> Dict[str, int]:
    """Генерирует волатильные, прыгающие цены для сырья на Галактической бирже."""
    random.seed(datetime.now().hour)  # Цены стабильны в течение часа
    return {
        "iron_ore": random.randint(5, 12),
        "gold_ore": random.randint(15, 35),
        "steel_alloy": random.randint(45, 95),
        "gold_bar": random.randint(150, 380)
    }

# ---------------------------------------------------------------------------
# РАБОТА С БД SUPABASE
# ---------------------------------------------------------------------------
async def db_get_or_create(tg_id: int, username: str | None, referrer_id: int | None = None) -> Dict[str, Any]:
    current_time = datetime.now().strftime("%d-%m-%Y %H:%M")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{SUPABASE_URL}users?tg_id=eq.{tg_id}", headers=HEADERS, timeout=6.0)
            data = r.json()
            if isinstance(data, list) and data: return data[0]
            
            new_user = {
                "tg_id": tg_id, "username": username or "Капитан", "ncoin": 10000, "nmp": 10,
                "reg_date": current_time, "current_bet": 10, "games_played": 0, "lost_ncoin": 0,
                "cargo_level": 1, "drill_level": 1, "energy": 100, "drones": 0,
                "iron_ore": 0, "gold_ore": 0, "steel_alloy": 0, "gold_bar": 0,
                "referrer": referrer_id, "ref_reward_paid": False
            }
            await client.post(f"{SUPABASE_URL}users", json=new_user, headers=HEADERS, timeout=6.0)
            return new_user
    except Exception as e:
        logger.error(f"DB Load failed: {e}")
        if tg_id not in LOCAL_DB:
            LOCAL_DB[tg_id] = {
                "tg_id": tg_id, "username": username or "Капитан", "ncoin": 10000, "nmp": 10,
                "cargo_level": 1, "drill_level": 1, "energy": 100, "drones": 0,
                "iron_ore": 0, "gold_ore": 0, "steel_alloy": 0, "gold_bar": 0, "games_played": 0, "lost_ncoin": 0
            }
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
                if games >= 5 and referrer and not paid:
                    await db_add_ref_reward(referrer, 100000)
                    await client.patch(f"{SUPABASE_URL}users?tg_id=eq.{tg_id}", json={"ref_reward_paid": True}, headers=HEADERS)
    except Exception as e:
        logger.error(f"DB Update failed: {e}")
        if tg_id in LOCAL_DB: LOCAL_DB[tg_id].update(updates)

async def db_add_ref_reward(referrer_id: int, amount: int) -> None:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{SUPABASE_URL}users?tg_id=eq.{referrer_id}", headers=HEADERS)
            data = r.json()
            if data:
                await client.patch(f"{SUPABASE_URL}users?tg_id=eq.{referrer_id}", json={"ncoin": data[0]["ncoin"] + amount}, headers=HEADERS)
    except: pass

async def db_get_top_users(order_by: str, limit: int = 10) -> List[Dict[str, Any]]:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{SUPABASE_URL}users?select=tg_id,username,ncoin,nmp&order={order_by}.desc&limit={limit}", headers=HEADERS, timeout=6.0)
            if r.status_code == 200: return r.json()
    except: pass
    return sorted(LOCAL_DB.values(), key=lambda x: x.get(order_by, 0), reverse=True)[:limit]

# ---------------------------------------------------------------------------
# СБОРКА КЛАВИАТУР (СТРОГО 2 В РЯД, ПОСЛЕДНЯЯ НА ВСЮ ШИРИНУ)
# ---------------------------------------------------------------------------
def get_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🚀 Активное Бурение", callback_data="space_mine"),
            InlineKeyboardButton("🛠️ Улучшение Корабля", callback_data="space_upgrade")
        ],
        [
            InlineKeyboardButton("🌌 Экспедиции", callback_data="space_expedition"),
            InlineKeyboardButton("📈 Галактическая Биржа", callback_data="space_market")
        ],
        [InlineKeyboardButton("👤 Бортовое Досье (Профиль)", callback_data="space_profile")]
    ])

def get_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Вернуться на капитанский мостик", callback_data="back_to_bridge")]])

def get_market_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🧱 Плавленный Сплав", callback_data="refine_iron"),
            InlineKeyboardButton("🔱 Чистый Слиток", callback_data="refine_gold")
        ],
        [
            InlineKeyboardButton("💰 Продать Всё сырье", callback_data="sell_all_ore"),
            InlineKeyboardButton("📈 Продать Сплавы", callback_data="sell_refined")
        ],
        [InlineKeyboardButton("◀️ Капитанский мостик", callback_data="back_to_bridge")]
    ])

def get_expedition_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛰️ Пояс Астероидов (Низкий риск)", callback_data="exp_belt")],
        [InlineKeyboardButton("🪐 Сверхновая Аномалия (ВЫСОКИЙ РИСК 3x)", callback_data="exp_anomaly")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_bridge")]
    ])

def get_ref_keyboard(bot_username: str, user_id: int) -> InlineKeyboardMarkup:
    url = f"https://t.me/share/url?url=https://t.me/{bot_username}?start=ref_{user_id}&text=🚀 Стань капитаном космического флота в AstroMiner!"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Скопировать реф-код", callback_data="copy_ref_code")],
        [InlineKeyboardButton("Пригласить пилотов ↩️", url=url)],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_bridge")]
    ])

# ---------------------------------------------------------------------------
# ОБРАБОТЧИКИ КОМАНД С ТЕЛЕФОНА
# ---------------------------------------------------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ref_id = None
    if update.message and update.message.text:
        parts = update.message.text.split()
        if len(parts) > 1 and parts[1].startswith("ref_"):
            try: ref_id = int(parts[1].split("_", 1)[1])
            except: pass

    user = update.effective_user
    await db_get_or_create(user.id, user.username, ref_id)
    
    text = (
        "<b>🛸 СИСТЕМА ИНИЦИАЛИЗИРОВАНА. ДОБРО ПОЖАЛОВАТЬ, КАПИТАН!</b>\n"
        "═" * 30 + "\n"
        "Вы получили под командование тяжелый шахтерский корвет класса 'AstroMiner'.\n\n"
        "Ваша цель — бурить недра мертвых планет, очищать ценные металлы и продавать сплавы на Галактической бирже по лучшему курсу.\n\n"
        "🛰️ Управляйте системами жизнеобеспечения корабля, закупайте буровые дроны и снаряжайте опасные научные экспедиции за Темной Материей!"
    )
    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=IMAGE_URL, caption=text, reply_markup=get_main_keyboard(), parse_mode="HTML")

async def game_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("<b>🛸 Мостик Управления Корветом</b>\nВыберите бортовой сектор:", reply_markup=get_main_keyboard(), parse_mode="HTML")

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "<b>📖 БОРТОВОЙ СПРАВОЧНИК КОРВЕТА AstroMiner</b>\n"
        "═" * 30 + "\n"
        "👨‍🚀 <b>Основные игровые механики:</b>\n\n"
        "🚀 <b>Бурение:</b> Буровой лазер расходует энергию щитов для добычи Железной и Золотой руды. Объем добычи зависит от уровня Буровых Лазеров.\n\n"
        "📦 <b>Трюм:</b> Ваш корабль имеет лимит вместимости руды и металлов. Каждое улучшение трюма увеличивает его объем.\n\n"
        "🧱 <b>Очистительный завод:</b> На Галактической Бирже сырая руда стоит дешево. Переплавляйте Железо в Сплавы стали, а Золотую руду — в Золотые слитки. Это умножает их стоимость в разы!\n\n"
        "🌌 <b>Экспедиции:</b> Отправка корабля в Сверхновую Аномалию — опасный шаг. Либо вы привезете кучу Темной Материи (nMP), либо попадете в метеоритную бурю, уничтожите 3 своих пассивных Дрона и потеряете 50% накопленной в трюме чистой руды!\n\n"
        "🏦 <b>Межзвездные депозиты:</b> Напишите `/deposit` чтобы открыть вклад с доходностью до 60%."
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def deposit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_data = await db_get_or_create(user.id, user.username)
    deps = await db_get_user_deposits(user.id)
    
    if not deps:
        text = (
            f"<b>{user.first_name}</b>\n"
            "🏦 <b>МЕЖЗВЕЗДНЫЕ ФОНДОВЫЕ ВКЛАДЫ</b>\n"
            "═" * 30 + "\n"
            "Вы можете вложить свои накопленные Кредиты mCoin под процентные обязательства Галактического банка.\n\n"
            "⚠️ <i>При попытке забрать вклад раньше времени, выплачивается исключительно сумма вклада без начисленных процентов.</i>"
        )
        await update.message.reply_text(text, reply_markup=get_deposit_terms_keyboard(), parse_mode="HTML")
    else:
        dep_list = "".join([f"⏳ Выплата: {d['end_time']} • {format_number(d['amount'])} m¢ ({d['percent']}%)\n" for d in deps])
        await update.message.reply_text(f"<b>🏦 Ваши активные вклады:</b>\n\n{dep_list}", reply_markup=get_deposit_active_keyboard(), parse_mode="HTML")

async def ref_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    bot_info = await context.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{user.id}"
    await update.message.reply_text(f"<b>👥 Корпоративная реферальная сеть</b>\n\nПриглашайте новых пилотов по вашей ссылке:\n<code>{link}</code>\n\n🎁 Вы получите 100k mCoin, когда приглашенный друг сделает 5 вылазок в экспедиции!", reply_markup=get_ref_keyboard(bot_info.username, user.id), parse_mode="HTML")

async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    top_coin = await db_get_top_users("ncoin", 10)
    top_nmp = await db_get_top_users("nmp", 10)
    
    text_c = "💎 <b>Лидеры по Кредитам mCoin:</b>\n" + "\n".join([f"{i+1}. {p.get('username','Капитан')} | {format_number(p.get('ncoin',0))} m¢" for i, p in enumerate(top_coin)])
    text_m = "⭐ <b>Лидеры по Темной Материи nMP:</b>\n" + "\n".join([f"{i+1}. {p.get('username','Капитан')} | {p.get('nmp',0)} nMP" for i, p in enumerate(top_nmp)])
    await update.message.reply_text(f"<b>🏆 РЕЙТИНГ ГАЛАКТИЧЕСКИХ КОРПОРАЦИЙ</b>\n\n{text_c}\n\n{text_m}", parse_mode="HTML")

# ---------------------------------------------------------------------------
# АДМИН ПАНЕЛЬ (Только для ADMIN_ID)
# ---------------------------------------------------------------------------
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID: return
    text = (
        "<b>🛠️ СЛУЖЕБНАЯ КОНСОЛЬ АДМИНИСТРАТОРА AstroMiner</b>\n\n"
        "<code>/give_credits [ID] [Сумма]</code> — выдать Кредиты\n"
        "<code>/give_matter [ID] [Сумма]</code> — выдать Темную Материю\n"
        "<code>/give_drones [ID] [Кол-во]</code> — выдать Автономных Дронов"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def give_credits(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID: return
    try:
        tid, amt = int(context.args[0]), int(context.args[1])
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{SUPABASE_URL}users?tg_id=eq.{tid}", headers=HEADERS)
            new_bal = r.json()[0]["ncoin"] + amt
            await client.patch(f"{SUPABASE_URL}users?tg_id=eq.{tid}", json={"ncoin": new_bal}, headers=HEADERS)
        await update.message.reply_text(f"✅ Баланс mCoin пользователя {tid} успешно пополнен на {format_number(amt)}")
    except Exception as e: await update.message.reply_text(f"Ошибка команды: {e}")

async def give_matter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID: return
    try:
        tid, amt = int(context.args[0]), int(context.args[1])
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{SUPABASE_URL}users?tg_id=eq.{tid}", headers=HEADERS)
            new_bal = r.json()[0]["nmp"] + amt
            await client.patch(f"{SUPABASE_URL}users?tg_id=eq.{tid}", json={"nmp": new_bal}, headers=HEADERS)
        await update.message.reply_text(f"✅ Баланс Темной Материи пользователя {tid} успешно пополнен на {amt}")
    except Exception as e: await update.message.reply_text(f"Ошибка команды: {e}")

# ---------------------------------------------------------------------------
# ОБРАБОТЧИК НАЖАТИЙ КНОПОК НА КАПИТАНСКОМ МОСТИКЕ
# ---------------------------------------------------------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    username = query.from_user.username or "Капитан"
    user_data = await db_get_or_create(user_id, username)
    
    if query.data == "copy_ref_code":
        bot_info = await context.bot.get_me()
        await query.answer(f"Ссылка скопирована:\nhttps://t.me/{bot_info.username}?start=ref_{user_id}", show_alert=True)
        return

    if query.data == "back_to_bridge":
        await query.edit_message_text("<b>🛸 Капитанский мостик AstroMiner</b>\nБортовые модули работают стабильно. Выберите сектор:", reply_markup=get_main_keyboard(), parse_mode="HTML")

    # --------------- 1. СЕКТОР АКТИВНОГО БУРЕНИЯ ---------------
    elif query.data == "space_mine":
        # Множители от уровня лазера
        lvl = user_data.get("cargo_level", 1)
        drill = user_data.get("drill_level", 1)
        cargo_max = lvl * 200
        
        # Считаем текущий объем трюма
        current_load = user_data.get("iron_ore", 0) + user_data.get("gold_ore", 0) + user_data.get("steel_alloy", 0) + user_data.get("gold_bar", 0)
        
        if current_load >= cargo_max:
            await context.bot.send_message(chat_id=query.message.chat_id, text="⚠️ <b>ВНИМАНИЕ! Трюм переполнен!</b> Очистите руду на Очистительном заводе или продайте ресурсы.", parse_mode="HTML")
            return
            
        if user_data.get("energy", 100) < 15:
            # Медленная регенерация энергии при клике
            user_data["energy"] = min(100, user_data.get("energy", 100) + 15)
            await db_update(user_id, {"energy": user_data["energy"]})
            await query.answer("Щиты перезаряжаются! Батареи восполнены на +15%.", show_alert=True)
            return

        # Бурим! Награды
        mined_iron = random.randint(5, 15) * drill
        mined_gold = random.randint(1, 4) * drill
        
        # Обновляем трюм и энергию
        new_iron = min(cargo_max, user_data.get("iron_ore", 0) + mined_iron)
        new_gold = min(cargo_max, user_data.get("gold_ore", 0) + mined_gold)
        new_energy = max(0, user_data.get("energy", 100) - 15)
        
        await db_update(user_id, {
            "iron_ore": new_iron,
            "gold_ore": new_gold,
            "energy": new_energy
        })
        
        text = (
            f"<b>🚀 РЕЖИМ БУРЕНИЯ АСТЕРОИДОВ</b>\n"
            f"═" * 30 + "\n"
            f"📡 <b>Сектор сканирования:</b> Успешно пробурен\n"
            f"🔋 <b>Энергия бурового лазера:</b> <code>{new_energy}%</code> (-15%)\n\n"
            f"⚙️ <b>Добытые материалы:</b>\n"
            f"├ 🪵 Железная руда: <code>+{mined_iron} ед.</code>\n"
            f"└ 🪙 Золотая руда: <code>+{mined_gold} ед.</code>\n\n"
            f"📦 <b>Загрузка трюма:</b> <code>{new_iron + new_gold + user_data.get('steel_alloy',0) + user_data.get('gold_bar',0)}/{cargo_max} ед.</code>"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚡ Запустить Буровой Лазер еще раз", callback_data="space_mine")],
            [InlineKeyboardButton("◀️ Вернуться на мостик", callback_data="back_to_bridge")]
        ])
        await query.edit_message_text(text=text, reply_markup=kb, parse_mode="HTML")

    # --------------- 2. СЕКТОР УЛУЧШЕНИЙ ЗВЕЗДОЛЕТА ---------------
    elif query.data == "space_upgrade":
        cargo_lvl = user_data.get("cargo_level", 1)
        drill_lvl = user_data.get("drill_level", 1)
        drones_cnt = user_data.get("drones", 0)
        
        cost_cargo = cargo_lvl * 8000
        cost_drill = drill_lvl * 12000
        cost_drone = (drones_cnt + 1) * 20000
        
        text = (
            f"<b>🛠️ ТЕХНИЧЕСКИЙ ДОК УЛУЧШЕНИЙ</b>\n"
            f"═" * 30 + "\n"
            f"📦 <b>Уровень Грузового Трюма:</b> {cargo_lvl} (Макс. вместимость: <code>{cargo_lvl*200} ед.</code>)\n"
            f"💸 Модернизация трюма: <code>{format_number(cost_cargo)} m¢</code>\n\n"
            f"⚙️ <b>Мощность Лазеров:</b> {drill_lvl}x к добыче\n"
            f"💸 Модернизация буров: <code>{format_number(cost_drill)} m¢</code>\n\n"
            f"🤖 <b>Пассивные буровые дроны:</b> {drones_cnt} шт. (приносят руду каждый час)\n"
            f"💸 Покупка бурового дрона: <code>{format_number(cost_drone)} m¢</code>"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"📦 Апгрейд Трюма ({format_number(cost_cargo)} m¢)", callback_data="up_cargo")],
            [InlineKeyboardButton(f"⚙️ Мощные Лазеры ({format_number(cost_drill)} m¢)", callback_data="up_drill")],
            [InlineKeyboardButton(f"🤖 Купить Дрона ({format_number(cost_drone)} m¢)", callback_data="buy_drone")],
            [InlineKeyboardButton("◀️ Назад", callback_data="back_to_bridge")]
        ])
        await query.edit_message_text(text=text, reply_markup=kb, parse_mode="HTML")

    elif query.data == "up_cargo":
        lvl = user_data.get("cargo_level", 1)
        cost = lvl * 8000
        if user_data["ncoin"] < cost:
            await query.answer("❌ У вас недостаточно кредитов mCoin!", show_alert=True)
            return
        await db_update(user_id, {"ncoin": user_data["ncoin"] - cost, "cargo_level": lvl + 1})
        await query.answer("🎉 Грузовой отсек звездолета расширен!", show_alert=True)
        await button_handler(update, context) # Перезапуск меню

    elif query.data == "up_drill":
        lvl = user_data.get("drill_level", 1)
        cost = lvl * 12000
        if user_data["ncoin"] < cost:
            await query.answer("❌ У вас недостаточно кредитов mCoin!", show_alert=True)
            return
        await db_update(user_id, {"ncoin": user_data["ncoin"] - cost, "drill_level": lvl + 1})
        await query.answer("🎉 Лазеры откалиброваны и улучшены!", show_alert=True)
        await button_handler(update, context)

    elif query.data == "buy_drone":
        cnt = user_data.get("drones", 0)
        cost = (cnt + 1) * 20000
        if user_data["ncoin"] < cost:
            await query.answer("❌ У вас недостаточно кредитов mCoin!", show_alert=True)
            return
        await db_update(user_id, {"ncoin": user_data["ncoin"] - cost, "drones": cnt + 1})
        await query.answer("🎉 Автономный буровой дрон запущен!", show_alert=True)
        await button_handler(update, context)

    # --------------- 3. БИРЖА И ПЕРЕРАБОТКА ---------------
    elif query.data == "space_market":
        prices = get_market_prices()
        text = (
            f"<b>📈 ГАЛАКТИЧЕСКАЯ ТОВАРНАЯ БИРЖА</b>\n"
            f"═" * 30 + "\n"
            f"Цены обновляются каждый час! Очищенные сплавы стоят значительно дороже!\n\n"
            f"🪵 Сырое Железо: <code>{prices['iron_ore']} m¢/ед.</code> (У вас: {user_data.get('iron_ore', 0)} ед.)\n"
            f"🪙 Сырое Золото: <code>{prices['gold_ore']} m¢/ед.</code> (У вас: {user_data.get('gold_ore', 0)} ед.)\n\n"
            f"🧱 Стальной сплав: <code>{prices['steel_alloy']} m¢/ед.</code> (У вас: {user_data.get('steel_alloy', 0)} ед.)\n"
            f"🔱 Золотой слиток: <code>{prices['gold_bar']} m¢/ед.</code> (У вас: {user_data.get('gold_bar', 0)} ед.)\n"
        )
        await query.edit_message_text(text=text, reply_markup=get_market_keyboard(), parse_mode="HTML")

    elif query.data == "refine_iron":
        # Плавка железа (10 руды -> 1 сплав)
        iron = user_data.get("iron_ore", 0)
        if iron < 10:
            await query.answer("❌ Нужно минимум 10 единиц сырого железа для плавки стального сплава!", show_alert=True)
            return
        refined = iron // 10
        await db_update(user_id, {
            "iron_ore": iron % 10,
            "steel_alloy": user_data.get("steel_alloy", 0) + refined
        })
        await query.answer(f"🏭 Переработано: {refined*10} железа -> {refined} Стальных сплавов!", show_alert=True)
        await button_handler(update, context)

    elif query.data == "refine_gold":
        # Плавка золота (10 руды -> 1 слиток)
        gold = user_data.get("gold_ore", 0)
        if gold < 10:
            await query.answer("❌ Нужно минимум 10 единиц сырого золота для отлива слитка!", show_alert=True)
            return
        refined = gold // 10
        await db_update(user_id, {
            "gold_ore": gold % 10,
            "gold_bar": user_data.get("gold_bar", 0) + refined
        })
        await query.answer(f"🏭 Отлито: {refined*10} золотой руды -> {refined} Слитков золота!", show_alert=True)
        await button_handler(update, context)

    elif query.data == "sell_all_ore":
        # Продажа сырого железа и золота
        prices = get_market_prices()
        iron = user_data.get("iron_ore", 0)
        gold = user_data.get("gold_ore", 0)
        
        if iron == 0 and gold == 0:
            await query.answer("Трюм пуст! Нечего продавать.", show_alert=True)
            return
            
        profit = (iron * prices["iron_ore"]) + (gold * prices["gold_ore"])
        await db_update(user_id, {
            "iron_ore": 0,
            "gold_ore": 0,
            "ncoin": user_data["ncoin"] + profit
        })
        await query.answer(f"💰 Продано сырой руды на сумму +{profit} mCoin!", show_alert=True)
        await button_handler(update, context)

    elif query.data == "sell_refined":
        # Продажа сплавов
        prices = get_market_prices()
        steel = user_data.get("steel_alloy", 0)
        gold_bar = user_data.get("gold_bar", 0)
        
        if steel == 0 and gold_bar == 0:
            await query.answer("У вас нет переработанных сплавов!", show_alert=True)
            return
            
        profit = (steel * prices["steel_alloy"]) + (gold_bar * prices["gold_bar"])
        await db_update(user_id, {
            "steel_alloy": 0,
            "gold_bar": 0,
            "ncoin": user_data["ncoin"] + profit
        })
        await query.answer(f"💰 Сплавы проданы! Баланс пополнен на +{profit} mCoin!", show_alert=True)
        await button_handler(update, context)

    # --------------- 4. КОСМИЧЕСКИЕ ЭКСПЕДИЦИИ ---------------
    elif query.data == "space_expedition":
        await query.edit_message_text("<b>🌌 КОСМИЧЕСКИЕ НАУЧНЫЕ ЭКСПЕДИЦИИ</b>\nВыберите регион для прыжка звездолета. Помните об опасности метеоритных бурь!", reply_markup=get_expedition_keyboard(), parse_mode="HTML")

    elif query.data == "exp_belt":
        # Безопасная экспедиция (Низкий риск)
        reward_iron = random.randint(30, 80)
        reward_gold = random.randint(10, 30)
        
        cargo_max = user_data.get("cargo_level", 1) * 200
        new_iron = min(cargo_max, user_data.get("iron_ore", 0) + reward_iron)
        new_gold = min(cargo_max, user_data.get("gold_ore", 0) + reward_gold)
        
        await db_update(user_id, {
            "iron_ore": new_iron,
            "gold_ore": new_gold,
            "games_played": user_data.get("games_played", 0) + 1
        })
        
        text = f"""<b>🛰️ ЭКСПЕДИЦИЯ: Пояс Астероидов завершена!</b>
• • • • • • • • • • • • • • • • • • •
Корабль успешно просканировал дальний сектор и загрузил трюмы сырьем!

🪵 Добыто Железа: <code>+{reward_iron} ед.</code>
🪙 Добыто Золота: <code>+{reward_gold} ед.</code>"""
        await query.edit_message_text(text=text, reply_markup=get_back_keyboard(), parse_mode="HTML")

    elif query.data == "exp_anomaly":
        # СУПЕР-ЗАДАНИЕ: Высокий риск. Либо 3x Темной материи (nMP), либо потеря дронов и 50% руды!
        chance = 45 # Шанс успеха 45%
        
        if random.randint(1, 100) <= chance:
            # УСПЕХ
            reward_nmp = random.randint(15, 45)
            await db_update(user_id, {
                "nmp": user_data.get("nmp", 0) + reward_nmp,
                "games_played": user_data.get("games_played", 0) + 1
            })
            text = f"""<b>🔥 ПОТРЯСАЮЩЕ! АНОМАЛИЯ ПОКОРЕНА!</b>
• • • • • • • • • • • • • • • • • • •
Датчики щитов выдержали излучение! Корабль собрал из ядра Сверхновой чистую Темную Материю!

⭐ Награда: <code>+{reward_nmp} nMP (Темная Материя)</code>"""
        else:
            # КРАХ
            lost_drones = min(3, user_data.get("drones", 0))
            lost_iron = int(user_data.get("iron_ore", 0) * 0.5)
            lost_gold = int(user_data.get("gold_ore", 0) * 0.5)
            
            await db_update(user_id, {
                "drones": user_data.get("drones", 0) - lost_drones,
                "iron_ore": user_data.get("iron_ore", 0) - lost_iron,
                "gold_ore": user_data.get("gold_ore", 0) - lost_gold,
                "games_played": user_data.get("games_played", 0) + 1
            })
            
            text = f"""<b>💥 КАТАСТРОФА! КОРАБЛЬ ПОПАЛ ПОД ГРАВИТАЦИОННЫЙ УДАР!</b>
• • • • • • • • • • • • • • • • • • •
Выброс радиации сжег щиты и уничтожил буровые системы!

📉 <b>Потери флота:</b>
- Уничтожено Дронов: <code>{lost_drones} шт.</code>
- Разгерметизация трюма: потеряно <code>{lost_iron} железа</code> и <code>{lost_gold} золота</code>!"""
            
        await query.edit_message_text(text=text, reply_markup=get_back_keyboard(), parse_mode="HTML")

    # --------------- 5. БОРТОВОЕ ДОСЬЕ (ПРОФИЛЬ) ---------------
    elif query.data == "space_profile":
        # Подсчет всего груза
        load = user_data.get("iron_ore", 0) + user_data.get("gold_ore", 0) + user_data.get("steel_alloy", 0) + user_data.get("gold_bar", 0)
        max_c = user_data.get("cargo_level", 1) * 200
        
        text = f"""<b>{username}</b>
👤 <b>БОРТОВОЕ ДОСЬЕ КАПИТАНА</b>

🆔 ID: <code>{user_id}</code>
🛰️ Звездолет: <b>AstroMiner Корвет</b>
• • • • • • • • • • • • • • • • • • •
💰 Межзвездные Кредиты: <code>{format_number(user_data['ncoin'])} mCoin</code>
⭐ Темная Материя: <code>{user_data['nmp']} nMP</code>
📦 Загрузка трюма: <code>{load}/{max_c} ед.</code>
• • • • • • • • • • • • • • • • • • •
🪵 Железная руда: <code>{user_data.get('iron_ore', 0)} ед.</code>
🪙 Золотая руда: <code>{user_data.get('gold_ore', 0)} ед.</code>
🧱 Стальные Сплавы: <code>{user_data.get('steel_alloy', 0)} ед.</code>
🔱 Золотые Слитки: <code>{user_data.get('gold_bar', 0)} ед.</code>"""
        
        await query.edit_message_text(text=text, reply_markup=get_back_keyboard(), parse_mode="HTML")

    # Вклады
    elif query.data == "open_deposit_menu":
        await query.edit_message_text("🏦 <b>Выберите срок депозитного вклада:</b>", reply_markup=get_deposit_terms_keyboard(), parse_mode="HTML")

    elif query.data.startswith("dep_term_"):
        term = int(query.data.split("_")[2])
        percent = {1: 0.4, 3: 1.5, 7: 4.0, 15: 10.0, 30: 25.0, 60: 60.0}.get(term, 0.4)
        user_states[user_id] = {"state": "awaiting_dep", "term": term, "percent": percent}
        await query.edit_message_text(f"💰 <b>Вклад на {term} дн. под {percent}%</b>\nУкажите сумму Кредитов для отправки на счет:", reply_markup=get_deposit_amount_keyboard(user_data["ncoin"]), parse_mode="HTML")

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
        await query.edit_message_text(f"✅ <b>Вклад успешно открыт!</b>\nСумма: {amt} m¢\nСрок: {state_data['term']} дней\nВозврат: {dep['end_time']}", reply_markup=get_back_keyboard(), parse_mode="HTML")

    elif query.data == "dep_withdraw_all":
        deps = await db_get_user_deposits(user_id)
        if not deps: return
        refund = sum(d["amount"] for d in deps)
        for d in deps: await db_close_deposit(d["id"])
        await db_update(user_id, {"ncoin": user_data["ncoin"] + refund})
        await query.answer(f"Вклады аннулированы. Возвращено {refund} m¢ без процентов.", show_alert=True)
        await query.edit_message_text("<b>🛸 Мостик управления</b>", reply_markup=get_main_keyboard(), parse_mode="HTML")


# ---------------------------------------------------------------------------
# ОБРАБОТЧИК ТЕКСТА
# ---------------------------------------------------------------------------
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    raw_text = update.message.text or ""
    
    # 1. Смена ставки по умолчанию (команды из прошлых шагов)
    if user_states.get(user_id, {}).get("state") == "awaiting_dep_manual":
        # Ручной ввод для вклада
        amt = parse_suffix_number(raw_text)
        state_data = user_states[user_id]
        user_data = await db_get_or_create(user_id, user.username)
        user_states[user_id] = None
        
        if not amt or amt <= 0 or user_data["ncoin"] < amt:
            await update.message.reply_text("❌ Ошибка ввода или недостаточно средств!")
            return
            
        await db_update(user_id, {"ncoin": user_data["ncoin"] - amt})
        dep = await db_create_deposit(user_id, amt, state_data["term"], state_data["percent"])
        await update.message.reply_text(f"✅ <b>Депозит успешно запущен!</b>\nСумма: {amt} m¢\nСрок: {state_data['term']} дней.", reply_markup=get_back_keyboard(), parse_mode="HTML")
        return

    # Быстрый баланс
    if raw_text.lower() in ["баланс", "б", "профиль"]:
        data = await db_get_or_create(user_id, user.username)
        await update.message.reply_text(f"🛸 <b>Капитан {user.first_name}</b>\n💰 Кредиты: <code>{format_number(data['ncoin'])} mCoin</code>\n⭐ Материя: <code>{data['nmp']} nMP</code>", parse_mode="HTML")


# ---------------------------------------------------------------------------
# ЗАПУСК БОТА (MAIN)
# ---------------------------------------------------------------------------
def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Сектора команд
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("game", game_command))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("deposit", deposit_command))
    app.add_handler(CommandHandler("ref", ref_command))
    app.add_handler(CommandHandler("top", top_command))
    
    # Команды Администратора
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("give_credits", give_credits))
    app.add_handler(CommandHandler("give_matter", give_matter))
    
    # Инлайн кнопки и сообщения
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    # Кнопки синего меню Telegram
    app.bot.set_my_commands([
        BotCommand("start", "🛸 Запустить звездолет"),
        BotCommand("game", "🎮 Капитанский мостик"),
        BotCommand("info", "📖 Справка AstroMiner"),
        BotCommand("deposit", "🏦 Фондовые депозиты"),
        BotCommand("ref", "👥 Пригласить пилотов"),
        BotCommand("top", "🏆 Рейтинг флотов")
    ])
    
    logger.info("AstroMiner Bot запущен на Railway!")
    app.run_polling()

if __name__ == "__main__":
    main()
