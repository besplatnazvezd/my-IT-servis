mport re
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

# ---------------------------------------------------------------------------
# СЛУЖЕБНЫЕ НАСТРОЙКИ СИНДИКАТА ОБОРОНЫ
# ---------------------------------------------------------------------------
BOT_TOKEN = "8894416195:AAHZ4i0sTodK5AYKhqZfNIlrFBnlRTOiVR8"
ADMIN_ID = 7727345054
IMAGE_URL = "https://i.ibb.co/jPJjTDBv/1000093316.jpg"

# Ссылка на репозиторий Frontend-сайта (замените на ваш домен на Vercel/Netlify)
WEBAPP_URL = "https://your-frontend-project.vercel.app"

SUPABASE_URL = "https://gyjwzifhfxrojwjioapp.supabase.co/rest/v1/"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd5and6aWZoZnhyb2p3amlvYXBwIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MzQxNDcxMywiZXhwIjoyMDk4OTkwNzEzfQ.xjicAYNFaI9iTA3PlHvM2L_10r38gJSIlwmopy_3O70"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния пользователей
user_states: Dict[int, Dict[str, Any]] = {}
LOCAL_DB: Dict[int, Dict[str, Any]] = {}
LOCAL_DEPOSITS: List[Dict[str, Any]] = []
DEPOSIT_FILE = "outpost_deposits_cache.json"

# Загрузка локального кэша депозитов
if os.path.exists(DEPOSIT_FILE):
    try:
        with open(DEPOSIT_FILE, "r", encoding="utf-8") as f:
            LOCAL_DEPOSITS = json.load(f)
            logger.info("Локальный кэш депозитов успешно загружен.")
    except Exception as e:
        logger.error(f"Ошибка загрузки кэша депозитов: {e}")

def save_local_deposits():
    try:
        with open(DEPOSIT_FILE, "w", encoding="utf-8") as f:
            json.dump(LOCAL_DEPOSITS, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Ошибка сохранения кэша депозитов: {e}")

# ---------------------------------------------------------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ФОРМАТИРОВАНИЯ И ПАРСИНГА
# ---------------------------------------------------------------------------
def format_number(val: int | float) -> str:
    val = int(val)
    if val >= 1_000_000_000:
        return f"{val / 1_000_000_000:.2f}b"
    if val >= 1_000_000:
        return f"{val / 1_000_000:.2f}kk"
    if val >= 1000:
        return f"{val / 1000:.2f}k"
    return str(val)

def parse_suffix_number(text: str) -> int | None:
    text = text.lower().strip().replace(" ", "")
    cleaned = re.sub(r'[^0-9.kmкм]', '', text)
    if not cleaned:
        return None
    
    mult = 1
    if any(x in cleaned for x in ["kk", "m", "м"]):
        mult = 1_000_000
    elif any(x in cleaned for x in ["k", "к"]):
        mult = 1000
        
    cleaned = re.sub(r'[kmкм]', '', cleaned)
    try:
        return int(float(cleaned) * mult)
    except ValueError:
        return None

# ---------------------------------------------------------------------------
# РАБОТА С СУБД SUPABASE REST API
# ---------------------------------------------------------------------------
async def db_get_or_create(tg_id: int, username: str | None, referrer_id: int | None = None) -> Dict[str, Any]:
    current_time = datetime.now().strftime("%d-%m-%Y %H:%M")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{SUPABASE_URL}outpost_users?tg_id=eq.{tg_id}", headers=HEADERS, timeout=6.0)
            data = r.json()
            if isinstance(data, list) and data:
                return data[0]
            
            new_user = {
                "tg_id": tg_id,
                "username": username or "Командир",
                "mcoins": 5000,
                "scrap_metal": 1000,
                "bio_materials": 200,
                "wave_level": 1,
                "cmd_level": 1,
                "wall_level": 1,
                "generator_level": 1,
                "turret_mg_level": 1,
                "turret_laser_level": 0,
                "reg_date": current_time,
                "referrer": referrer_id,
                "ref_reward_paid": False
            }
            r2 = await client.post(f"{SUPABASE_URL}outpost_users", json=new_user, headers=HEADERS, timeout=6.0)
            return r2.json()[0] if r2.status_code == 201 else new_user
    except Exception as e:
        logger.error(f"Ошибка БД: {e}")
        if tg_id not in LOCAL_DB:
            LOCAL_DB[tg_id] = {
                "tg_id": tg_id, "username": username or "Командир", "mcoins": 5000, 
                "scrap_metal": 1000, "bio_materials": 200, "wave_level": 1,
                "cmd_level": 1, "wall_level": 1, "generator_level": 1,
                "turret_mg_level": 1, "turret_laser_level": 0,
                "reg_date": current_time, "referrer": referrer_id, "ref_reward_paid": False
            }
        return LOCAL_DB[tg_id]

async def db_update(tg_id: int, updates: Dict[str, Any]) -> None:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.patch(f"{SUPABASE_URL}outpost_users?tg_id=eq.{tg_id}", json=updates, headers=HEADERS, timeout=6.0)
            data = r.json()
            user_data = data[0] if isinstance(data, list) and data else None
            
            if user_data:
                waves = user_data.get("wave_level", 1)
                referrer = user_data.get("referrer")
                paid = user_data.get("ref_reward_paid", False)
                if waves >= 5 and referrer and not paid:
                    await db_add_ref_reward(referrer, 100000)
                    await client.patch(
                        f"{SUPABASE_URL}outpost_users?tg_id=eq.{tg_id}", 
                        json={"ref_reward_paid": True}, 
                        headers=HEADERS, 
                        timeout=5.0
                    )
    except Exception as e:
        logger.error(f"Ошибка обновления пользователя: {e}")
        if tg_id in LOCAL_DB:
            LOCAL_DB[tg_id].update(updates)

async def db_add_ref_reward(referrer_tg_id: int, amount: int) -> None:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{SUPABASE_URL}outpost_users?tg_id=eq.{referrer_tg_id}", headers=HEADERS, timeout=5.0)
            data = r.json()
            if isinstance(data, list) and data:
                new_bal = data[0].get("mcoins", 0) + amount
                await client.patch(f"{SUPABASE_URL}outpost_users?tg_id=eq.{referrer_tg_id}", json={"mcoins": new_bal}, headers=HEADERS, timeout=5.0)
    except Exception as e:
        logger.error(f"Ошибка выплаты реф-бонуса: {e}")

async def db_get_top_users() -> List[Dict[str, Any]]:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{SUPABASE_URL}outpost_users?select=username,wave_level,cmd_level&order=wave_level.desc&limit=10", headers=HEADERS, timeout=6.0)
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.error(f"Ошибка получения топа: {e}")
    return sorted(LOCAL_DB.values(), key=lambda x: x.get("wave_level", 1), reverse=True)[:10]

# ---------------------------------------------------------------------------
# РАБОТА С ДЕПОЗИТАМИ В SUPABASE И ЛОКАЛЬНО
# ---------------------------------------------------------------------------
async def db_get_user_deposits(tg_id: int) -> List[Dict[str, Any]]:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{SUPABASE_URL}deposits?tg_id=eq.{tg_id}&is_active=eq.true", headers=HEADERS, timeout=5.0)
            if r.status_code == 200 and isinstance(r.json(), list):
                return r.json()
    except Exception as e:
        logger.error(f"Ошибка получения депозитов: {e}")
    return [d for d in LOCAL_DEPOSITS if d["tg_id"] == tg_id and d["is_active"]]

async def db_create_deposit(tg_id: int, amount: int, term_days: int, percent: float) -> Dict[str, Any]:
    start_time = datetime.now()
    end_time = start_time + timedelta(days=term_days)
    dep_data = {
        "tg_id": tg_id,
        "amount": amount,
        "term_days": term_days,
        "percent": percent,
        "start_time": start_time.strftime("%d-%m-%Y %H:%M"),
        "end_time": end_time.strftime("%d-%m-%Y %H:%M"),
        "is_active": True
    }
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{SUPABASE_URL}deposits", json=dep_data, headers=HEADERS, timeout=5.0)
            if r.status_code == 201:
                dep_data["id"] = r.json()[0].get("id", random.randint(1000, 9999))
                LOCAL_DEPOSITS.append(dep_data)
                save_local_deposits()
                return r.json()[0]
    except Exception as e:
        logger.error(f"Ошибка создания депозита в БД: {e}")
    
    dep_data["id"] = random.randint(10000, 99999)
    LOCAL_DEPOSITS.append(dep_data)
    save_local_deposits()
    return dep_data

async def db_close_deposit(dep_id: int) -> None:
    try:
        async with httpx.AsyncClient() as client:
            await client.patch(f"{SUPABASE_URL}deposits?id=eq.{dep_id}", json={"is_active": False}, headers=HEADERS, timeout=5.0)
    except Exception as e:
        logger.error(f"Ошибка закрытия депозита в БД: {e}")
        
    for d in LOCAL_DEPOSITS:
        if d.get("id") == dep_id:
            d["is_active"] = False
            break
    save_local_deposits()

# ---------------------------------------------------------------------------
# КЛАВИАТУРЫ (СТРОГО 2 В РЯД, ПОСЛЕДНЯЯ НА ВСЮ ШИРИНУ)
# ---------------------------------------------------------------------------
def get_main_keyboard() -> InlineKeyboardMarkup:
    webapp_btn = InlineKeyboardButton("🕹️ Открыть Аванпост", web_app=WebAppInfo(url=WEBAPP_URL))
    keyboard = [
        [webapp_btn],
        [
            InlineKeyboardButton("📖 Справка", callback_data="btn_info"),
            InlineKeyboardButton("🏆 Топ Баз", callback_data="btn_top")
        ],
        [
            InlineKeyboardButton("🏦 Депозиты", callback_data="btn_deposits"),
            InlineKeyboardButton("👥 Рефералы", callback_data="btn_ref")
        ],
        [InlineKeyboardButton("👤 Досье профиля", callback_data="btn_profile")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад на Командный пункт", callback_data="back_to_main")]])

def get_deposit_terms_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("1 д. (0.4%)", callback_data="dep_term_1"), 
            InlineKeyboardButton("3 д. (1.5%)", callback_data="dep_term_3"), 
            InlineKeyboardButton("7 д. (4%)", callback_data="dep_term_7")
        ],
        [
            InlineKeyboardButton("15 д. (10%)", callback_data="dep_term_15"), 
            InlineKeyboardButton("30 д. (25%)", callback_data="dep_term_30"), 
            InlineKeyboardButton("60 д. (60%)", callback_data="dep_term_60")
        ],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
    ])

def get_deposit_amount_keyboard(user_mcoin: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Все mCoin • {user_mcoin} m¢", callback_data="dep_amt_all")],
        [
            InlineKeyboardButton(f"{int(user_mcoin*0.1)} m¢", callback_data="dep_amt_10"), 
            InlineKeyboardButton(f"{int(user_mcoin*0.25)} m¢", callback_data="dep_amt_25"), 
            InlineKeyboardButton(f"{int(user_mcoin*0.5)} m¢", callback_data="dep_amt_50")
        ],
        [InlineKeyboardButton("◀️ Назад", callback_data="open_deposit_menu")]
    ])

def get_deposit_active_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Снять всё (без %)", callback_data="dep_withdraw_all")],
        [InlineKeyboardButton("💳 Новый вклад", callback_data="open_deposit_menu"), InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
    ])

# ---------------------------------------------------------------------------
# ОБРАБОТЧИКИ ТЕКСТОВЫХ И СЕРВЕРНЫХ КОМАНД
# ---------------------------------------------------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    ref_id = None
    if update.message and update.message.text:
        parts = update.message.text.split()
        if len(parts) > 1 and parts[1].startswith("ref_"):
            try:
                ref_id = int(parts[1].split("_", 1)[1])
            except ValueError:
                ref_id = None

    await db_get_or_create(user.id, user.username, ref_id)
    text = (
        "<b>🛡️ АВАНПОСТ: Последний Рубеж</b>\n"
        "═" * 30 + "\n"
        "Приветствую, Командир! Зомби-апокалипсис наступил внезапно. Вы взяли под командование стратегически важное оборонительное укрепление.\n\n"
        "Отражайте атаки орд мутантов, стройте укрепления, устанавливайте пулеметы и термоядерные лазеры!\n\n"
        "👇 <b>Нажмите кнопку ниже, чтобы войти в оборонительный сектор базы!</b>"
    )
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=IMAGE_URL,
        caption=text,
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )

async def game_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("<b>🛸 Командный Пункт Аванпоста</b>\nВыберите бортовой сектор:", reply_markup=get_main_keyboard(), parse_mode="HTML")

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "<b>🛡️ ТАКТИЧЕСКОЕ РУКОВОДСТВО ПО ОБОРОНЕ</b>\n"
        "═" * 30 + "\n"
        "🧟 <b>Прогресс волн:</b>\n"
        "Запускайте волны в WebApp. Зомби будут атаковать стену. Ваши защитные турели стреляют автоматически по целям.\n\n"
        "🏗️ <b>Развитие строений:</b>\n"
        "• <b>Командный центр:</b> Главное здание базы. Повышает лимиты апгрейда всех остальных защитных сооружений.\n"
        "• <b>Оборонительная Стена:</b> Повышает запас прочности (HP) вашего аванпоста во время вылазок зомби.\n"
        "• <b>Генератор:</b> Вырабатывает термоядерную энергию, необходимую для работы защитных систем.\n\n"
        "🔫 <b>Вооружение:</b>\n"
        "• <b>Пулемет (MG):</b> Скорострельный физический урон. Быстро уничтожает легких зомби.\n"
        "• <b>Плазменный лазер:</b> Испепеляет тяжело бронированных зомби и боссов. Требует энергию генератора."
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def deposit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_data = await db_get_or_create(user.id, user.username)
    active_deps = await db_get_user_deposits(user.id)
    
    if not active_deps:
        text = (
            f"<b>{user.first_name}</b>\n"
            "🏦 <b>МЕЖЗВЕЗДНЫЕ ФОНДОВЫЕ ДЕПОЗИТЫ</b>\n"
            "═" * 30 + "\n"
            "<blockquote>ℹ️ Здесь вы можете выгодно разместить свободные mCoin под проценты. При досрочном снятии выплачивается только сумма вклада без накопленных процентов.</blockquote>\n"
            "<b>Выберите срок вклада 👇</b>"
        )
        await update.message.reply_text(text, reply_markup=get_deposit_terms_keyboard(), parse_mode="HTML")
    else:
        dep_list_str = ""
        for d in active_deps:
            dep_list_str += f"⏳ До {d['end_time']} • {format_number(d['amount'])} m¢ ({d['percent']}%)\n"
        text = f"<b>{user.first_name}</b>\n🏦 <b>АКТИВНЫЕ ДЕПОЗИТЫ • {len(active_deps)}</b>\n• • • • • • • • • •\n🟢 <b>Список вкладов в обработке:</b>\n{dep_list_str}"
        await update.message.reply_text(text, reply_markup=get_deposit_active_keyboard(), parse_mode="HTML")

async def ref_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    bot_info = await context.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{user.id}"
    invited_count = 0
    earned = 0
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{SUPABASE_URL}outpost_users?referrer=eq.{user.id}", headers=HEADERS, timeout=5.0)
            data = res.json()
            if isinstance(data, list):
                invited_count = len(data)
                for p in data:
                    lost = p.get("lost_ncoin", 0) or 0
                    earned += int(lost * 0.02)
                    if p.get("ref_reward_paid", False): earned += 100000
    except: pass

    text = (
        f"<b>👥 РЕФЕРАЛЬНАЯ СЕТЬ КОМАНДИРА</b>\n"
        f"═" * 30 + "\n"
        f"🎁 Приглашайте других выживших пилотов и получайте бонусы:\n\n"
        f"• 100,000 mCoin за каждого активного друга, отбившего 5 волн.\n"
        f"• 2% от потраченных на ремонт базы коинов рефералов.\n\n"
        f"🔗 <b>Ваша персональная ссылка для вербовки:</b>\n"
        f"<code>{link}</code>\n\n"
        f"💵 <b>Суммарный доход:</b> <code>{format_number(earned)} mCoin</code>\n"
        f"👥 <b>Зарегистрировано подельников:</b> <code>{invited_count} командиров</code>"
    )
    await update.message.reply_text(text, reply_markup=get_ref_keyboard(bot_info.username, user.id), parse_mode="HTML")

async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    leaders = await db_get_top_users()
    text = "<b>🏆 ГЛОБАЛЬНЫЙ РЕЙТИНГ АВАНПОСТОВ</b>\n" + "═" * 30 + "\n"
    if not leaders:
        text += "Список пуст."
    for i, l in enumerate(leaders):
        text += f"{i+1}. 🛡️ <b>{l.get('username','Командир')}</b> — Волна {l.get('wave_level', 1)} [Командный центр: {l.get('cmd_level', 1)}]\n"
    await update.message.reply_text(text, parse_mode="HTML")
  

# ---------------------------------------------------------------------------
# АДМИНИСТРАТИВНЫЕ КОМАНДЫ (Только для ADMIN_ID)
# ---------------------------------------------------------------------------
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID: return
    text = (
        "<b>🛠️ СЛУЖЕБНАЯ КОНСОЛЬ АДМИНИСТРАТОРА АВАНПОСТА</b>\n\n"
        "<code>/give_coins [ID] [Сумма]</code> — выдать mCoin\n"
        "<code>/give_scrap [ID] [Сумма]</code> — выдать Металл\n"
        "<code>/give_bio [ID] [Сумма]</code> — выдать Биоматериалы"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def give_cash(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID: return
    try:
        tid, amt = int(context.args[0]), int(context.args[1])
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{SUPABASE_URL}outpost_users?tg_id=eq.{tid}", headers=HEADERS)
            new_bal = r.json()[0]["mcoins"] + amt
            await client.patch(f"{SUPABASE_URL}outpost_users?tg_id=eq.{tid}", json={"mcoins": new_bal}, headers=HEADERS)
        await update.message.reply_text(f"✅ Баланс mCoin пользователя {tid} пополнен на {format_number(amt)}")
    except Exception as e: await update.message.reply_text(f"Ошибка команды: {e}")

async def give_scrap(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID: return
    try:
        tid, amt = int(context.args[0]), int(context.args[1])
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{SUPABASE_URL}outpost_users?tg_id=eq.{tid}", headers=HEADERS)
            new_bal = r.json()[0]["scrap_metal"] + amt
            await client.patch(f"{SUPABASE_URL}outpost_users?tg_id=eq.{tid}", json={"scrap_metal": new_bal}, headers=HEADERS)
        await update.message.reply_text(f"✅ Баланс Металла пользователя {tid} пополнен на {format_number(amt)}")
    except Exception as e: await update.message.reply_text(f"Ошибка команды: {e}")

async def give_bio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID: return
    try:
        tid, amt = int(context.args[0]), int(context.args[1])
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{SUPABASE_URL}outpost_users?tg_id=eq.{tid}", headers=HEADERS)
            new_bal = r.json()[0]["bio_materials"] + amt
            await client.patch(f"{SUPABASE_URL}outpost_users?tg_id=eq.{tid}", json={"bio_materials": new_bal}, headers=HEADERS)
        await update.message.reply_text(f"✅ Баланс Биоматериалов пользователя {tid} пополнен на {format_number(amt)}")
    except Exception as e: await update.message.reply_text(f"Ошибка команды: {e}")

# ---------------------------------------------------------------------------
# ОБРАБОТЧИК ИНЛАЙН КНОПОК
# ---------------------------------------------------------------------------
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    username = query.from_user.username or "Командир"
    user_data = await db_get_or_create(uid, username)
    
    if query.data == "ref_copy_link_alert":
        bot_info = await context.bot.get_me()
        link = f"https://t.me/{bot_info.username}?start=ref_{uid}"
        await query.answer(f"Ссылка скопирована:\n{link}", show_alert=True)
        return

    if query.data == "back_to_main":
        await query.edit_message_text(
            text="<b>🛸 Командный Пункт Аванпоста</b>\nБортовые модули работают стабильно. Выберите сектор:", 
            reply_markup=get_main_keyboard(), 
            parse_mode="HTML"
        )
        
    elif query.data == "btn_info":
        text = (
            "<b>🛡️ ТАКТИЧЕСКОЕ РУКОВОДСТВО ПО ОБОРОНЕ</b>\n"
            "═" * 30 + "\n"
            "🧟 <b>Прогресс волн:</b>\n"
            "Запускайте волны в WebApp. Зомби будут атаковать стену. Ваши защитные турели стреляют автоматически по целям.\n\n"
            "🏗️ <b>Развитие строений:</b>\n"
            "• <b>Командный центр:</b> Главное здание базы. Повышает лимиты апгрейда всех остальных защитных сооружений.\n"
            "• <b>Оборонительная Стена:</b> Повышает запас прочности (HP) вашего аванпоста во время вылазок зомби.\n"
            "• <b>Генератор:</b> Вырабатывает термоядерную энергию, необходимую для работы защитных систем.\n\n"
            "🔫 <b>Вооружение:</b>\n"
            "• <b>Пулемет (MG):</b> Скорострельный физический урон. Быстро уничтожает легких зомби.\n"
            "• <b>Плазменный лазер:</b> Испепеляет тяжело бронированных зомби и боссов. Требует энергию генератора."
        )
        await query.edit_message_text(text=text, reply_markup=get_back_keyboard(), parse_mode="HTML")
        
    elif query.data == "btn_top":
        leaders = await db_get_top_users()
        text = "<b>🏆 ГЛОБАЛЬНЫЙ РЕЙТИНГ АВАНПОСТОВ</b>\n" + "═" * 30 + "\n"
        if not leaders:
            text += "Список пуст."
        for i, l in enumerate(leaders):
            text += f"{i+1}. 🛡️ <b>{l.get('username','Командир')}</b> — Волна {l.get('wave_level', 1)} [Штаб: {l.get('cmd_level', 1)}]\n"
        await query.edit_message_text(text=text, reply_markup=get_back_keyboard(), parse_mode="HTML")
        
    elif query.data == "btn_ref":
        bot_info = await context.bot.get_me()
        link = f"https://t.me/{bot_info.username}?start=ref_{uid}"
        text = (
            f"<b>👥 РЕФЕРАЛЬНАЯ СЕТЬ КОМАНДИРА</b>\n"
            f"═" * 30 + "\n"
            f"🎁 Приглашайте других выживших пилотов и получайте бонусы:\n\n"
            f"• 100,000 mCoin за каждого активного друга, отбившего 5 волн.\n"
            f"• 2% от потраченных на ремонт базы коинов рефералов.\n\n"
            f"🔗 <b>Ваша персональная ссылка для вербовки:</b>\n"
            f"<code>{link}</code>"
        )
        await query.edit_message_text(text=text, reply_markup=get_ref_keyboard(bot_info.username, uid), parse_mode="HTML")
        
    elif query.data == "btn_profile":
        text = (
            f"<b>{username}</b>\n"
            f"👤 <b>ЛИЧНОЕ ДОСЬЕ КОМАНДИРА</b>\n"
            f"═" * 30 + "\n"
            f"🆔 ID: <code>{uid}</code>\n"
            f"💰 Баланс mCoin: <code>{format_number(user_data['mcoins'])}</code>\n"
            f"🔩 Лом металла: <code>{format_number(user_data['scrap_metal'])}</code>\n"
            f"🧬 Биоматериалы: <code>{format_number(user_data['bio_materials'])}</code>\n"
            f"🛡️ Пройдено волн: <code>{user_data['wave_level'] - 1}</code>\n"
            f"🏢 Уровень Штаба: <code>{user_data['cmd_level']}</code>"
        )
        await query.edit_message_text(text=text, reply_markup=get_back_keyboard(), parse_mode="HTML")

    elif query.data == "btn_deposits":
        active_deps = await db_get_user_deposits(uid)
        if not active_deps:
            text = (
                f"<b>{username}</b>\n"
                "🏦 <b>ВРЕМЕННЫЕ ДЕПОЗИТЫ СИНДИКАТА</b>\n"
                "═" * 30 + "\n"
                "<blockquote>ℹ️ Здесь вы можете выгодно разместить свободные mCoin под высокие проценты. При досрочном выводе средств выплачивается только сумма тела вклада БЕЗ процентов.</blockquote>\n"
                "<b>Выберите срок вклада 👇</b>"
            )
            await query.edit_message_text(text=text, reply_markup=get_deposit_terms_keyboard(), parse_mode="HTML")
        else:
            dep_list_str = ""
            for d in active_deps:
                dep_list_str += f"⏳ До {d['end_time']} • {format_number(d['amount'])} m¢ (под {d['percent']}%)\n"
            text = f"<b>{username}</b>\n🏦 <b>АКТИВНЫЕ ДЕПОЗИТЫ • {len(active_deps)}</b>\n• • • • • • • • • •\n🟢 <b>Список вкладов в обработке:</b>\n{dep_list_str}"
            await query.edit_message_text(text=text, reply_markup=get_deposit_active_keyboard(), parse_mode="HTML")

    elif query.data == "open_deposit_menu":
        await query.edit_message_text("🏦 <b>Выберите срок депозитного вклада:</b>", reply_markup=get_deposit_terms_keyboard(), parse_mode="HTML")

    elif query.data.startswith("dep_term_"):
        term = int(query.data.split("_")[2])
        percent = {1: 0.4, 3: 1.5, 7: 4.0, 15: 10.0, 30: 25.0, 60: 60.0}.get(term, 0.4)
        user_states[uid] = {"state": "awaiting_dep", "term": term, "percent": percent}
        await query.edit_message_text(f"💰 <b>Вклад на {term} дн. под {percent}%</b>\nУкажите сумму mCoin для отправки на счет:", reply_markup=get_deposit_amount_keyboard(user_data["mcoins"]), parse_mode="HTML")

    elif query.data.startswith("dep_amt_"):
        state_data = user_states.get(uid)
        if not state_data or state_data.get("state") != "awaiting_dep": return
        fraction = query.data.split("_")[2]
        balance = user_data["mcoins"]
        amt = balance if fraction == "all" else int(balance * float(fraction)/100) if fraction in ["10", "25", "50"] else 10
        if amt <= 0 or balance < amt: return
        await db_update(uid, {"mcoins": balance - amt})
        dep = await db_create_deposit(uid, amt, state_data["term"], state_data["percent"])
        user_states[uid] = None
        await query.edit_message_text(f"✅ <b>Вклад успешно открыт банком!</b>\n\nСумма: {amt} m¢\nСрок: {state_data['term']} дней\nДата возврата: {dep['end_time']}", reply_markup=get_back_keyboard(), parse_mode="HTML")

    elif query.data == "dep_withdraw_all":
        deps = await db_get_user_deposits(uid)
        if not deps: return
        refund = sum(d["amount"] for d in deps)
        for d in deps: await db_close_deposit(d["id"])
        await db_update(uid, {"mcoins": user_data["mcoins"] + refund})
        await query.answer(f"Вклады досрочно закрыты! Баланс пополнен на {refund} m¢ (проценты аннулированы).", show_alert=True)
        await query.edit_message_text("<b>🏯 Штаб-квартира</b>", reply_markup=get_main_keyboard(), parse_mode="HTML")

# ---------------------------------------------------------------------------
# ОБРАБОТЧИК ВВОДА С ТЕКСТОВОГО ПОЛЯ
# ---------------------------------------------------------------------------
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    raw_text = update.message.text or ""
    
    # Смена ставки
    if user_states.get(user_id, {}).get("state") == "awaiting_bet":
        bet = parse_suffix_number(raw_text)
        if bet:
            await db_update(user_id, {"current_bet": bet})
            await update.message.reply_text("✅ Ставка успешно обновлена!")
            user_states[user_id] = None
        return

    # Быстрая проверка баланса
    if raw_text.lower() in ["баланс", "б", "профиль"]:
        data = await db_get_or_create(user_id, user.username)
        await update.message.reply_text(f"💰 <b>Баланс mCoin:</b> <code>{format_number(data['mcoins'])}</code>\n🔩 <b>Металл:</b> <code>{format_number(data['scrap_metal'])}</code>", parse_mode="HTML")

# ---------------------------------------------------------------------------
# ЗАПУСК ТЕЛЕГРАМ-БОТА
# ---------------------------------------------------------------------------
def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("game", game_command))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("deposit", deposit_command))
    app.add_handler(CommandHandler("ref", ref_command))
    app.add_handler(CommandHandler("top", top_command))
    
    # Команды Администратора
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("give_coins", give_cash))
    app.add_handler(CommandHandler("give_scrap", give_scrap))
    app.add_handler(CommandHandler("give_bio", give_bio))
    
    # Обработчики инлайна и ввода текста
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    app.bot.set_my_commands([
        BotCommand("start", "🚀 Запустить Аванпост"),
        BotCommand("game", "🎮 Командный пункт"),
        BotCommand("info", "📖 Справка по обороне"),
        BotCommand("deposit", "🏦 Фондовые депозиты"),
        BotCommand("ref", "👥 Реферальная сеть"),
        BotCommand("top", "🏆 Топ баз")
    ])
    
    logger.info("Бот Аванпоста успешно запущен на Railway!")
    app.run_polling()

if __name__ == "__main__":
    main()
