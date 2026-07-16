from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from db import get_all_users, update_balance, add_admin_log, get_user
from keyboards import back_to_main

router = Router()

@router.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("У вас нет доступа.")
        return
    text = "👑 Админ-панель\nДоступные команды:\n/list - список пользователей\n/give <user_id> <nm|nmx> <amount> - выдать валюту\n/stats - статистика\n/logs - логи действий"
    await message.answer(text)

@router.message(Command("list"))
async def list_users(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    users = get_all_users()
    text = "📋 Список пользователей (ID, username, NM, NMX):\n"
    for u in users:
        text += f"{u[0]} @{u[1] or 'no_username'} - NM:{u[2]} NMX:{u[3]}\n"
    await message.answer(text[:4000])

@router.message(Command("give"))
async def give_currency(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) != 4:
        await message.answer("Использование: /give <user_id> <nm|nmx> <amount>")
        return
    _, user_id, currency, amount = parts
    try:
        user_id = int(user_id)
        amount = int(amount)
        if currency not in ("nm", "nmx"):
            raise ValueError
    except:
        await message.answer("Неверный формат.")
        return
    update_balance(user_id, currency, amount)
    add_admin_log(ADMIN_ID, f"give_{currency}", user_id, f"{amount}")
    await message.answer(f"✅ Выдано {amount} {currency.upper()} пользователю {user_id}.")

@router.message(Command("stats"))
async def stats_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    # простая статистика
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]
    cur.execute("SELECT SUM(balance_nm) FROM users")
    total_nm = cur.fetchone()[0] or 0
    cur.execute("SELECT SUM(balance_nmx) FROM users")
    total_nmx = cur.fetchone()[0] or 0
    conn.close()
    text = f"📊 Статистика:\nВсего пользователей: {total_users}\nОбщий NM: {total_nm}\nОбщий NMX: {total_nmx}"
    await message.answer(text)

@router.message(Command("logs"))
async def admin_logs(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM admin_logs ORDER BY timestamp DESC LIMIT 20")
    rows = cur.fetchall()
    conn.close()
    if not rows:
        await message.answer("Логов нет.")
        return
    text = "📜 Последние логи:\n"
    for row in rows:
        text += f"{row[4]} - {row[1]} (target {row[2]}) {row[3]}\n"
    await message.answer(text[:4000])
