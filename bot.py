import re
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
ADMIN_ID = 7727345054  # Твой Telegram ID
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

user_states: Dict[int, Dict[str, Any]] = {}

FIGHTER_RACES = ["Вампир 🧛", "Орк-Вышибала 👹", "Эльф-Наемник 🧝", "Демон 😈"]
FIGHTER_NAMES = [
    "Дон Сильвио", "Бруно Бритва", "Винсент Клык", "Карл Ломатель", 
    "Сайлас Хакер", "Маркус Тень", "Люциус Горн", "Векс Смертоносный"
]

# -----------------------
# Вспомогательные функции
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
# Интеграция с Supabase
# -----------------------
async def db_get_or_create(tg_id: int, username: str | None) -> Dict[str, Any]:
    current_time = datetime.now().strftime("%d-%m-%Y %H:%M")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{SUPABASE_URL}users?tg_id=eq.{tg_id}", headers=HEADERS, timeout=6.0)
            data = r.json()
            if isinstance(data, list) and data: return data[0]
            
            new_user = {
                "tg_id": tg_id,
                "username": username or "Игрок",
                "ncoin": 10000,
                "nmp": 0,
                "reg_date": current_time,
                "current_bet": 10,
                "games_played": 0,
                "lost_ncoin": 0,
                "missions_completed": 0,
                "painting_fragments": 0,
                "completed_paintings": 0
            }
            await client.post(f"{SUPABASE_URL}users", json=new_user, headers=HEADERS, timeout=6.0)
            
            # Сразу дарим одного стартового Обычного бойца
            await db_generate_fighter(tg_id, "Обычный")
            return new_user
    except Exception as e:
        logger.error(f"DB Error: {e}")
        return {"tg_id": tg_id, "username": username or "Игрок", "ncoin": 10000, "nmp": 0, "painting_fragments": 0, "completed_paintings": 0, "current_bet": 10}

async def db_update(tg_id: int, updates: Dict[str, Any]) -> None:
    try:
        async with httpx.AsyncClient() as client:
            await client.patch(f"{SUPABASE_URL}users?tg_id=eq.{tg_id}", json=updates, headers=HEADERS, timeout=6.0)
    except Exception as e:
        logger.error(f"DB Update Error: {e}")

async def db_get_fighters(tg_id: int) -> List[Dict[str, Any]]:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{SUPABASE_URL}fighters?user_id=eq.{tg_id}", headers=HEADERS, timeout=6.0)
            return r.json() if isinstance(r.json(), list) else []
    except:
        return []

async def db_generate_fighter(tg_id: int, rarity: str = "Обычный") -> Dict[str, Any]:
    race = random.choice(FIGHTER_RACES)
    name = f"{random.choice(FIGHTER_NAMES)} ({race.split()[0]})"
    
    multipliers = {"Обычный": 1, "Редкий": 2, "Эпический": 3, "Легендарный": 5}
    m = multipliers.get(rarity, 1)
    
    fighter = {
        "user_id": tg_id,
        "name": name,
        "race": race,
        "rarity": rarity,
        "strength": random.randint(10, 30) * m,
        "stealth": random.randint(10, 30) * m,
        "magic": random.randint(10, 30) * m,
        "health": 100,
        "status": "idle"
    }
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{SUPABASE_URL}fighters", json=fighter, headers=HEADERS, timeout=6.0)
            if r.status_code == 201:
                return r.json()[0]
    except Exception as e:
        logger.error(f"Fighter generation error: {e}")
    return fighter

# -----------------------
# Сборка Клавиатур
# -----------------------
def get_main_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🏯 Моя База (Убежище)", callback_data="open_base")],
        [InlineKeyboardButton("🍻 Вербовка (Gacha)", callback_data="open_gacha")],
        [InlineKeyboardButton("🗺️ Вылазки синдиката", callback_data="open_missions")],
        [InlineKeyboardButton("🏪 Черный рынок (P2P)", callback_data="open_market")],
        [InlineKeyboardButton("👤 Досье профиля", callback_data="open_profile")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_base_keyboard(fighters: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    keyboard = []
    # Каждого раненого бойца можно отправить лечиться
    for f in fighters:
        if f["health"] < 100 and f["status"] == "idle":
            keyboard.append([InlineKeyboardButton(f"🏥 Лечить: {f['name']} (XP: {f['health']}/100)", callback_data=f"heal_fighter_{f['id']}")])
    keyboard.append([InlineKeyboardButton("◀️ В главное меню", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

def get_missions_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("💰 Ограбление лавки (Простая)", callback_data="mission_start_easy")],
        [InlineKeyboardButton("😈 Ограбление Века (СУПЕР-МИССИЯ 3x)", callback_data="mission_start_super")],
        [InlineKeyboardButton("◀️ В главное меню", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_market_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🖼️ Продать картину Дона", callback_data="market_sell_painting")],
        [InlineKeyboardButton("🛒 Купить у других", callback_data="market_browse")],
        [InlineKeyboardButton("◀️ В главное меню", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

# -----------------------
# Команды бота
# -----------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await db_get_or_create(user.id, user.username)
    text = (
        "<b>Добро пожаловать в Теневой Синдикат, Босс! 🧛👹</b>\n\n"
        "Здесь ты возглавишь криминальную империю фэнтезийного мегаполиса. "
        "Нанимай бойцов, отправляй их на грабежи, торгуй артефактами и доминируй на улицах города!"
    )
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=IMAGE_URL,
        caption=text,
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )

# -----------------------
# АДМИН ПАНЕЛЬ (Выдача ресурсов)
# -----------------------
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещен!")
        return

    text = (
        "<b>🛠️ АДМИН-ПАНЕЛЬ СИНДИКАТА</b>\n\n"
        "Команды управления игроками:\n"
        "<code>/give_cash [ID] [Сумма]</code> — выдать mCoin\n"
        "<code>/give_nmp [ID] [Сумма]</code> — выдать nMP\n"
        "<code>/give_fighter [ID] [Редкость]</code> — выдать бойца (Обычный, Редкий, Эпический, Легендарный)\n"
        "<code>/give_fragment [ID] [Кол-во]</code> — выдать фрагменты картины"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def give_cash(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID: return
    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
        
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{SUPABASE_URL}users?tg_id=eq.{target_id}", headers=HEADERS)
            user_data = r.json()[0]
            new_bal = user_data["ncoin"] + amount
            await client.patch(f"{SUPABASE_URL}users?tg_id=eq.{target_id}", json={"ncoin": new_bal}, headers=HEADERS)
            
        await update.message.reply_text(f"✅ Успешно выдано {format_number(amount)} mCoin пользователю {target_id}")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def give_fighter_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID: return
    try:
        target_id = int(context.args[0])
        rarity = context.args[1]
        await db_generate_fighter(target_id, rarity)
        await update.message.reply_text(f"✅ Выдан боец [{rarity}] пользователю {target_id}")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

# -----------------------
# Обработчик кнопок (Главная Логика)
# -----------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    username = query.from_user.username or "Игрок"
    user_data = await db_get_or_create(user_id, username)
    
    # Возврат на главную
    if query.data == "back_to_main":
        await query.edit_message_text(
            text="<b>🏯 Главный штаб Синдиката</b>\nВыбери свои дальнейшие шаги, Босс:",
            reply_markup=get_main_keyboard(),
            parse_mode="HTML"
        )

    # --------------- 1. МОЯ БАЗА ---------------
    elif query.data == "open_base":
        fighters = await db_get_fighters(user_id)
        
        # Обновляем здоровье лечащихся бойцов перед показом
        now = datetime.now()
        updated_fighters = []
        for f in fighters:
            if f["status"] == "healing" and f["healing_start"]:
                h_start = datetime.fromisoformat(f["healing_start"].replace("Z", "+00:00"))
                # 20 минут до полного восстановления
                mins_passed = (now.astimezone() - h_start).total_seconds() / 60
                if mins_passed >= 20:
                    f["health"] = 100
                    f["status"] = "idle"
                    f["healing_start"] = None
                    # Пишем изменения в Supabase
                    async with httpx.AsyncClient() as client:
                        await client.patch(f"{SUPABASE_URL}fighters?id=eq.{f['id']}", json={"health": 100, "status": "idle", "healing_start": None}, headers=HEADERS)
                else:
                    healed_amount = int((mins_passed / 20) * 100)
                    f["health"] = min(100, f["health"] + healed_amount)
            updated_fighters.append(f)

        base_text = f"<b>🏯 УБЕЖИЩЕ СИНДИКАТА</b>\n• • • • • • • • • •\n"
        if not updated_fighters:
            base_text += "🔴 У вас пока нет бойцов! Вербуйте их в таверне."
        else:
            base_text += "👥 <b>Твоя банда:</b>\n\n"
            for f in updated_fighters:
                status_emoji = "🟢 Свободен" if f["status"] == "idle" else "🏥 Восстанавливается в Био-капсуле"
                base_text += (
                    f"▪️ <b>{f['name']}</b> ({f['rarity']})\n"
                    f"   ❤️ Здоровье: {f['health']}/100\n"
                    f"   ⚔️ С: {f['strength']} | Скр: {f['stealth']} | М: {f['magic']}\n"
                    f"   {status_emoji}\n\n"
                )
        await query.edit_message_text(text=base_text, reply_markup=get_base_keyboard(updated_fighters), parse_mode="HTML")

    # Лечение бойца (20 минут)
    elif query.data.startswith("heal_fighter_"):
        fighter_id = int(query.data.split("_")[2])
        async with httpx.AsyncClient() as client:
            now_str = datetime.now().isoformat()
            await client.patch(f"{SUPABASE_URL}fighters?id=eq.{fighter_id}", json={"status": "healing", "healing_start": now_str}, headers=HEADERS)
        await query.edit_message_text("💉 Боец помещен в Био-капсулу. Полное восстановление займет 20 минут!", reply_markup=get_back_keyboard(), parse_mode="HTML")

    # --------------- 2. GACHA (ВЕРБОВКА) ---------------
    elif query.data == "open_gacha":
        gacha_text = (
            "<b>🍻 ТАВЕРНА ВЕРБОВКИ</b>\n• • • • • • • • • •\n"
            "Вы можете нанять нового элитного бойца в свою банду!\n\n"
            "🎫 <b>Стоимость Контракта:</b> 5,000 mCoin\n"
            "Шансы:\n"
            "🟢 Обычный: 60%\n"
            "🔵 Редкий: 25%\n"
            "🟣 Эпический: 12%\n"
            "🟡 Легендарный: 3%"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✍️ Подписать Контракт (5к mCoin)", callback_data="gacha_roll")],
            [InlineKeyboardButton("◀️ Главное меню", callback_data="back_to_main")]
        ])
        await query.edit_message_text(text=gacha_text, reply_markup=keyboard, parse_mode="HTML")

    elif query.data == "gacha_roll":
        balance = user_data["ncoin"]
        if balance < 5000:
            await context.bot.send_message(chat_id=query.message.chat_id, text="❌ У вас недостаточно mCoin для контракта!", parse_mode="HTML")
            return
            
        await db_update(user_id, {"ncoin": balance - 5000})
        
        # Определяем редкость
        roll = random.random() * 100
        if roll < 3: rarity = "Легендарный"
        elif roll < 15: rarity = "Эпический"
        elif roll < 40: rarity = "Редкий"
        else: rarity = "Обычный"
        
        new_fighter = await db_generate_fighter(user_id, rarity)
        
        result_text = f"""<b>🍻 КОНТРАКТ ПОДПИСАН!</b>
• • • • • • • • • • • • • • • • • • •
К вашей банде присоединяется:
👤 <b>{new_fighter['name']}</b>
🎨 Редкость: <b>{new_fighter['rarity']}</b>

⚔️ <b>Характеристики:</b>
└ 💪 Сила: <code>{new_fighter['strength']}</code>
└ 👤 Скрытность: <code>{new_fighter['stealth']}</code>
└ 🔮 Магия: <code>{new_fighter['magic']}</code>"""
        
        await query.edit_message_text(text=result_text, reply_markup=get_back_keyboard(), parse_mode="HTML")

    # --------------- 3. ВЫЛАЗКИ И СУПЕР-ЗАДАНИЯ ---------------
    elif query.data == "open_missions":
        await query.edit_message_text(
            text="<b>🗺️ ТЕРРИТОРИИ СИНДИКАТА</b>\n\nВыбери миссию для своих бойцов. Помни: супер-миссии невероятно опасны!",
            reply_markup=get_missions_keyboard(),
            parse_mode="HTML"
        )

    # Простая миссия
    elif query.data == "mission_start_easy":
        fighters = await db_get_fighters(user_id)
        ready_fighters = [f for f in fighters if f["status"] == "idle" and f["health"] >= 20]
        
        if not ready_fighters:
            await context.bot.send_message(chat_id=query.message.chat_id, text="❌ У вас нет здоровых и свободных бойцов для отправки!", parse_mode="HTML")
            return
            
        fighter = random.choice(ready_fighters)
        # Наносим урон и переводим в статус
        new_hp = max(10, fighter["health"] - random.randint(10, 30))
        async with httpx.AsyncClient() as client:
            await client.patch(f"{SUPABASE_URL}fighters?id=eq.{fighter['id']}", json={"health": new_hp}, headers=HEADERS)
        
        # Начисляем награду
        reward = random.randint(500, 1500)
        user_data["ncoin"] += reward
        user_data["missions_completed"] = user_data.get("missions_completed", 0) + 1
        
        # Логика выдачи фрагментов: 2-я, затем 5-я, затем через каждые 3 миссии (8, 11, 14, 17...)
        mc = user_data["missions_completed"]
        got_fragment = False
        if mc == 2 or mc == 5 or (mc > 5 and (mc - 5) % 3 == 0):
            user_data["painting_fragments"] = min(20, user_data.get("painting_fragments", 0) + 1)
            got_fragment = True

        await db_update(user_id, {
            "ncoin": user_data["ncoin"],
            "missions_completed": mc,
            "painting_fragments": user_data["painting_fragments"]
        })

        frag_text = "<b>🧩 Вы нашли Фрагмент Картины Дона!</b>" if got_fragment else ""
        
        success_text = f"""<b>🤠 Миссия Успешна!</b>
• • • • • • • • • • • • • •
👤 Отправлялся: {fighter['name']}
🩸 Полученный урон: {fighter['health'] - new_hp} HP

💰 Награда: <code>+{reward} mCoin</code>
{frag_text}"""
        await query.edit_message_text(text=success_text, reply_markup=get_back_keyboard(), parse_mode="HTML")

    # СУПЕР-МИССИЯ
    elif query.data == "mission_start_super":
        fighters = await db_get_fighters(user_id)
        ready_fighters = [f for f in fighters if f["status"] == "idle" and f["health"] >= 50]
        
        if len(ready_fighters) < 3:
            await context.bot.send_message(chat_id=query.message.chat_id, text="❌ Для Ограбления Века нужно минимум 3 здоровых свободных бойца!", parse_mode="HTML")
            return
            
        # Берем троих лучших
        team = ready_fighters[:3]
        sum_stats = sum(f["strength"] + f["stealth"] + f["magic"] for f in team)
        
        # Шанс победы зависит от их характеристик (требуется 250 очков характеристик для 85% шанса)
        win_chance = min(95, max(15, int((sum_stats / 250) * 85)))
        
        if random.randint(1, 100) <= win_chance:
            # УСПЕХ (3x Награда)
            win_amount = int(user_data["ncoin"] * 1.5)  # 3x текущей ставки или огромный бонус
            if win_amount < 5000: win_amount = 15000
            
            user_data["ncoin"] += win_amount
            await db_update(user_id, {"ncoin": user_data["ncoin"]})
            
            res_text = f"""<b>🔥 ОГРАБЛЕНИЕ ВЕКА ПРОШЛО УСПЕШНО!</b>
• • • • • • • • • • • • • • • • • • • • • • •
⚡ Шанс успеха составлял: <code>{win_chance}%</code>
Бойцы разгромили хранилище магов и принесли невероятную добычу!

💰 Куш: <code>+{format_number(win_amount)} mCoin</code>"""
        else:
            # ПРОВАЛ (Минус 3 бойца навсегда + потеря 50% ресурсов)
            lost_cash = int(user_data["ncoin"] * 0.5)
            user_data["ncoin"] -= lost_cash
            await db_update(user_id, {"ncoin": user_data["ncoin"]})
            
            # Удаляем бойцов из базы
            async with httpx.AsyncClient() as client:
                for f in team:
                    await client.delete(f"{SUPABASE_URL}fighters?id=eq.{f['id']}", headers=HEADERS)
                    
            res_text = f"""<b>💀 КАТАСТРОФА! ОГРАБЛЕНИЕ ПРОВАЛЕНО!</b>
• • • • • • • • • • • • • • • • • • • • • • •
⚡ Шанс успеха составлял: <code>{win_chance}%</code>
Вся штурмовая группа попала в засаду полиции и была ликвидирована!

🪦 <b>Потери банды:</b>
- {team[0]['name']} (Ликвидирован)
- {team[1]['name']} (Ликвидирован)
- {team[2]['name']} (Ликвидирован)

📉 <b>Конфисковано ресурсов:</b> <code>-{format_number(lost_cash)} mCoin</code>"""
            
        await query.edit_message_text(text=res_text, reply_markup=get_back_keyboard(), parse_mode="HTML")

    # --------------- 4. ДОСЬЕ ПРОФИЛЯ & КАРТИНА ---------------
    elif query.data == "open_profile":
        fighters = await db_get_fighters(user_id)
        
        # Кнопка сбора картины
        keyboard_list = []
        if user_data.get("painting_fragments", 0) >= 20:
            keyboard_list.append([InlineKeyboardButton("🖼️ Собрать картину Дона", callback_data="craft_painting")])
        keyboard_list.append([InlineKeyboardButton("◀️ Главное меню", callback_data="back_to_main")])
        
        profile_text = f"""<b>{username}</b>
👤 <b>Досье профиля</b>

🆔 ID: <code>{user_id}</code>
• • • • • • • • • • • • • • • • • • •
💰 Баланс: <code>{user_data['ncoin']} mCoin</code>
⭐ Авторитет: <code>{user_data['nmp']} nMP</code>
👥 Членов банды: <code>{len(fighters)} чел.</code>
• • • • • • • • • • • • • • • • • • •
🧩 Фрагментов картины: <code>{user_data.get('painting_fragments', 0)}/20</code>
🖼️ Готовых картин: <code>{user_data.get('completed_paintings', 0)} шт</code>"""
        
        await query.edit_message_text(text=profile_text, reply_markup=InlineKeyboardMarkup(keyboard_list), parse_mode="HTML")

    elif query.data == "craft_painting":
        if user_data.get("painting_fragments", 0) < 20:
            await query.answer("Недостаточно фрагментов!", show_alert=True)
            return
            
        await db_update(user_id, {
            "painting_fragments": user_data["painting_fragments"] - 20,
            "completed_paintings": user_data.get("completed_paintings", 0) + 1
        })
        await query.edit_message_text("🎨 <b>Поздравляем!</b> Вы успешно восстановили легендарную картину <b>'Крестный Отец'</b>. Она добавлена в ваш профиль и готова к продаже на Черном рынке!", reply_markup=get_back_keyboard(), parse_mode="HTML")

    # --------------- 5. ЧЕРНЫЙ РЫНОК (P2P) ---------------
    elif query.data == "open_market":
        await query.edit_message_text(
            text="<b>🏪 Черный рынок Синдиката</b>\n\nЗдесь вы можете продать свои картины Дона другим игрокам или купить редкие товары.",
            reply_markup=get_market_keyboard(),
            parse_mode="HTML"
        )

    elif query.data == "market_sell_painting":
        if user_data.get("completed_paintings", 0) <= 0:
            await context.bot.send_message(chat_id=query.message.chat_id, text="❌ У вас нет картин для продажи в профиле!", parse_mode="HTML")
            return
            
        user_states[user_id] = {"state": "awaiting_market_price"}
        await context.bot.send_message(chat_id=query.message.chat_id, text="✍️ <b>Введите цену продажи картины в mCoin:</b>", parse_mode="HTML")

    elif query.data == "market_browse":
        # Ищем лоты в таблице
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{SUPABASE_URL}market?is_active=eq.true&limit=5", headers=HEADERS)
            lots = r.json()
            
        if not lots:
            await query.edit_message_text("🏪 На рынке пока нет активных лотов. Будьте первыми!", reply_markup=get_back_keyboard(), parse_mode="HTML")
            return
            
        market_text = "<b>🏪 Активные лоты на Черном Рынке:</b>\n\n"
        kb = []
        for lot in lots:
            market_text += f"▪️ <b>Лора Картины</b> | Продавец: <code>{lot['seller_id']}</code>\n   💰 Цена: <code>{format_number(lot['price'])} mCoin</code>\n\n"
            kb.append([InlineKeyboardButton(f"🛒 Купить за {format_number(lot['price'])}", callback_data=f"buy_lot_{lot['id']}")])
        kb.append([InlineKeyboardButton("◀️ назад", callback_data="open_market")])
        await query.edit_message_text(text=market_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

    elif query.data.startswith("buy_lot_"):
        lot_id = int(query.data.split("_")[2])
        
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{SUPABASE_URL}market?id=eq.{lot_id}", headers=HEADERS)
            lot = r.json()[0]
            
        price = lot["price"]
        seller_id = lot["seller_id"]
        
        if user_data["ncoin"] < price:
            await context.bot.send_message(chat_id=query.message.chat_id, text="❌ Недостаточно mCoin для совершения сделки!", parse_mode="HTML")
            return
            
        # Проведение транзакции
        tax = int(price * 0.10) # Твои 10% комиссии синдиката
        seller_earned = price - tax
        
        # Обновляем покупателя
        await db_update(user_id, {"ncoin": user_data["ncoin"] - price, "completed_paintings": user_data.get("completed_paintings", 0) + 1})
        
        # Обновляем продавца
        async with httpx.AsyncClient() as client:
            r_sel = await client.get(f"{SUPABASE_URL}users?tg_id=eq.{seller_id}", headers=HEADERS)
            seller_data = r_sel.json()[0]
            await client.patch(f"{SUPABASE_URL}users?tg_id=eq.{seller_id}", json={
                "ncoin": seller_data["ncoin"] + seller_earned
            }, headers=HEADERS)
            
            # Начисляем 10% тебе (Админу)
            r_adm = await client.get(f"{SUPABASE_URL}users?tg_id=eq.{ADMIN_ID}", headers=HEADERS)
            if r_adm.status_code == 200 and r_adm.json():
                adm_data = r_adm.json()[0]
                await client.patch(f"{SUPABASE_URL}users?tg_id=eq.{ADMIN_ID}", json={"ncoin": adm_data["ncoin"] + tax}, headers=HEADERS)
            
            # Закрываем лот
            await client.patch(f"{SUPABASE_URL}market?id=eq.{lot_id}", json={"is_active": False}, headers=HEADERS)
            
        await query.edit_message_text(f"✅ <b>Сделка завершена!</b>\nВы приобрели картину Дона за {format_number(price)} mCoin. 10% комиссии синдиката выплачены.", reply_markup=get_back_keyboard(), parse_mode="HTML")


# -----------------------
# Обработчик текста
# -----------------------
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    raw_text = update.message.text or ""
    
    # Регистрация лота на рынке
    if user_states.get(user_id, {}).get("state") == "awaiting_market_price":
        price = parse_suffix_number(raw_text)
        user_states[user_id] = None
        user_data = await db_get_or_create(user_id, user.username)
        
        if not price or price <= 0:
            await update.message.reply_text("❌ Введена некорректная цена!")
            return
            
        # Удаляем картину из профиля и создаем лот
        await db_update(user_id, {"completed_paintings": user_data["completed_paintings"] - 1})
        
        async with httpx.AsyncClient() as client:
            lot_data = {
                "seller_id": user_id,
                "item_type": "painting",
                "price": price,
                "is_active": True
            }
            await client.post(f"{SUPABASE_URL}market", json=lot_data, headers=HEADERS)
            
        await update.message.reply_text(f"✅ Ваша картина Дона выставлена на рынок за <code>{format_number(price)} mCoin</code>! (Комиссия составит 10%)", parse_mode="HTML")


# -----------------------
# Запуск бота
# -----------------------
def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("give_cash", give_cash))
    app.add_handler(CommandHandler("give_fighter", give_fighter_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    # Telegram меню команд
    app.bot.set_my_commands([
        BotCommand("start", "🚀 Запустить бота"),
        BotCommand("admin", "🛠️ Панель управления (Admin)")
    ])
    
    logger.info("Бот Теневого Синдиката успешно запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
