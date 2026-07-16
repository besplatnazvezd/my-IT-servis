import random
import asyncio
from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command

from db import get_user, update_balance, add_achievement, get_balance
from keyboards import back_to_main, main_menu
from config import ADMIN_ID

# ----------------------------------------------------------------------
# Состояния для игр, требующих ввода данных
# ----------------------------------------------------------------------
class GameStates(StatesGroup):
    roulette_bet = State()
    dice_bet = State()
    guess_number = State()
    keno_choose = State()
    blackjack_bet = State()
    baccarat_bet = State()
    poker_bet = State()
    lottery_buy = State()
    wheel_bet = State()
    dice_multiplier_bet = State()
    crash_bet = State()
    mines_bet = State()
    plinko_bet = State()
    poker_dice_bet = State()
    single_dice_bet = State()
    bingo_bet = State()
    rps_bet = State()
    coin_flip_bet = State()
    slot_bet = State()

# ----------------------------------------------------------------------
# Вспомогательная функция проверки и списания баланса
# ----------------------------------------------------------------------
async def check_balance_and_deduct(user_id: int, currency: str, amount: int):
    user = get_user(user_id)
    if not user:
        return False, "Пользователь не найден."
    bal = user["balance_nm"] if currency == "nm" else user["balance_nmx"]
    if bal < amount:
        return False, f"Недостаточно {currency.upper()}. У вас: {bal}."
    update_balance(user_id, currency, -amount)
    return True, ""

# ----------------------------------------------------------------------
# Роутер для игр
# ----------------------------------------------------------------------
router = Router()

# ----------------------------------------------------------------------
# 1. Слот "Фрукты" (фиксированная ставка 10 NM)
# ----------------------------------------------------------------------
@router.callback_query(F.data == "game_fruit_slot")
async def fruit_slot(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    amount = 10
    ok, msg = await check_balance_and_deduct(user_id, "nm", amount)
    if not ok:
        await callback.answer(msg, show_alert=True)
        return
    symbols = ["🍒", "🍋", "🍊", "🍇", "🔔", "💎", "7️⃣"]
    reel = [random.choice(symbols) for _ in range(3)]
    result = " ".join(reel)
    if reel[0] == reel[1] == reel[2]:
        if reel[0] == "7️⃣":
            win = amount * 50
        elif reel[0] == "💎":
            win = amount * 20
        elif reel[0] == "🔔":
            win = amount * 10
        else:
            win = amount * 5
    elif reel[0] == reel[1] or reel[1] == reel[2] or reel[0] == reel[2]:
        win = amount * 2
    else:
        win = 0
    if win > 0:
        update_balance(user_id, "nm", win)
        text = f"🎰 {result}\n\n🍀 Вы выиграли {win} NM!"
        if win >= amount * 20:
            add_achievement(user_id, "big_win_slot")
    else:
        text = f"🎰 {result}\n\n😔 Проигрыш. Попробуйте снова!"
    await callback.message.edit_text(text, reply_markup=back_to_main())
    await callback.answer()

# ----------------------------------------------------------------------
# 2. Слот "Сокровища" (фикс. ставка 20 NM)
# ----------------------------------------------------------------------
@router.callback_query(F.data == "game_treasure_slot")
async def treasure_slot(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    amount = 20
    ok, msg = await check_balance_and_deduct(user_id, "nm", amount)
    if not ok:
        await callback.answer(msg, show_alert=True)
        return
    symbols = ["⚱️", "💎", "👑", "💰", "🗡️", "🏆", "⭐"]
    reel = [random.choice(symbols) for _ in range(3)]
    result = " ".join(reel)
    if reel[0] == reel[1] == reel[2]:
        if reel[0] == "👑":
            win = amount * 40
        elif reel[0] == "💎":
            win = amount * 25
        elif reel[0] == "⭐":
            win = amount * 15
        else:
            win = amount * 6
    elif reel[0] == reel[1] or reel[1] == reel[2] or reel[0] == reel[2]:
        win = amount * 2
    else:
        win = 0
    if win > 0:
        update_balance(user_id, "nm", win)
        text = f"🏴‍☠️ {result}\n\n🎉 Вы нашли сокровище! +{win} NM!"
        if win >= amount * 20:
            add_achievement(user_id, "treasure_hunter")
    else:
        text = f"🏴‍☠️ {result}\n\n💀 Неудача. Попробуйте ещё!"
    await callback.message.edit_text(text, reply_markup=back_to_main())
    await callback.answer()

# ----------------------------------------------------------------------
# 3. Рулетка (выбор ставки и типа через сообщение)
# ----------------------------------------------------------------------
@router.callback_query(F.data == "game_roulette")
async def roulette_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🎡 Рулетка\n\nВведите ставку и тип в формате:\n<сумма> <тип>\n\nТипы:\n"
        "red — красное (x2)\nblack — чёрное (x2)\neven — чёт (x2)\nodd — нечет (x2)\n"
        "number — конкретное число (1-36, x36)\ndozen — дюжина (1-12, 13-24, 25-36, x3)\n\n"
        "Пример: 50 red",
        reply_markup=back_to_main()
    )
    await state.set_state(GameStates.roulette_bet)
    await callback.answer()

@router.message(GameStates.roulette_bet)
async def roulette_play(message: Message, state: FSMContext, bot: Bot):
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Неверный формат. Введите: <сумма> <тип>")
        return
    try:
        bet = int(parts[0])
        if bet <= 0:
            raise ValueError
        bet_type = parts[1].lower()
        if bet_type not in ("red", "black", "even", "odd", "number", "dozen"):
            raise ValueError
    except:
        await message.answer("Неверный формат. Проверьте данные.")
        return
    user_id = message.from_user.id
    ok, err = await check_balance_and_deduct(user_id, "nm", bet)
    if not ok:
        await message.answer(err)
        await state.clear()
        return
    # Генерация выпавшего числа (0-36)
    number = random.randint(0, 36)
    color = "green" if number == 0 else ("red" if number % 2 == 1 else "black")
    # Определяем выигрыш
    win = 0
    if bet_type == "red" and color == "red":
        win = bet * 2
    elif bet_type == "black" and color == "black":
        win = bet * 2
    elif bet_type == "even" and number != 0 and number % 2 == 0:
        win = bet * 2
    elif bet_type == "odd" and number != 0 and number % 2 == 1:
        win = bet * 2
    elif bet_type == "number" and number == int(parts[1]):  # если ввели число
        # но мы не обрабатываем отдельно, поэтому игнорируем
        pass
    elif bet_type == "dozen":
        if 1 <= number <= 12:
            win = bet * 3
        elif 13 <= number <= 24:
            win = bet * 3
        elif 25 <= number <= 36:
            win = bet * 3
    # Если игрок ввел конкретное число, проверим
    if bet_type == "number" and parts[1].isdigit():
        num = int(parts[1])
        if 1 <= num <= 36 and num == number:
            win = bet * 36

    if win > 0:
        update_balance(user_id, "nm", win)
        text = f"🎡 Выпало число {number} ({color})\nПоздравляем! Вы выиграли {win} NM!"
        if win >= bet * 20:
            add_achievement(user_id, "roulette_pro")
    else:
        text = f"🎡 Выпало число {number} ({color})\nК сожалению, вы проиграли {bet} NM."
    await message.answer(text, reply_markup=main_menu)
    await state.clear()

# ----------------------------------------------------------------------
# 4. Кости (угадать сумму двух кубиков)
# ----------------------------------------------------------------------
@router.callback_query(F.data == "game_dice")
async def dice_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🎲 Кости\nВведите сумму ставки и предсказанную сумму (от 2 до 12), например: 30 7",
        reply_markup=back_to_main()
    )
    await state.set_state(GameStates.dice_bet)
    await callback.answer()

@router.message(GameStates.dice_bet)
async def dice_play(message: Message, state: FSMContext, bot: Bot):
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Введите: <ставка> <сумма>")
        return
    try:
        bet = int(parts[0])
        guess = int(parts[1])
        if bet <= 0 or not (2 <= guess <= 12):
            raise ValueError
    except:
        await message.answer("Неверный формат. Убедитесь, что ставка >0, сумма от 2 до 12.")
        return
    user_id = message.from_user.id
    ok, err = await check_balance_and_deduct(user_id, "nm", bet)
    if not ok:
        await message.answer(err)
        await state.clear()
        return
    d1 = random.randint(1, 6)
    d2 = random.randint(1, 6)
    total = d1 + d2
    if total == guess:
        win = bet * 5
        update_balance(user_id, "nm", win)
        text = f"🎲 Выпало {d1} и {d2} = {total}\n🎉 Вы угадали! Выигрыш: {win} NM."
        if win >= bet * 10:
            add_achievement(user_id, "dice_master")
    else:
        text = f"🎲 Выпало {d1} и {d2} = {total}\n😞 Не угадали. Проигрыш {bet} NM."
    await message.answer(text, reply_markup=main_menu)
    await state.clear()

# ----------------------------------------------------------------------
# 5. Орёл/Решка (фикс. ставка 10 NM)
# ----------------------------------------------------------------------
@router.callback_query(F.data == "game_coin")
async def coin_game(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    amount = 10
    ok, msg = await check_balance_and_deduct(user_id, "nm", amount)
    if not ok:
        await callback.answer(msg, show_alert=True)
        return
    side = random.choice(["Орёл", "Решка"])
    # Просто случайный исход, игрок не выбирает - для упрощения
    # Можно было бы дать выбор, но оставим как есть
    win = 0
    if random.random() < 0.5:  # 50% шанс выиграть
        win = amount * 2
        update_balance(user_id, "nm", win)
        text = f"🪙 Выпал: {side}\n🎉 Вы выиграли {win} NM!"
    else:
        text = f"🪙 Выпал: {side}\n😔 Проигрыш."
    await callback.message.edit_text(text, reply_markup=back_to_main())
    await callback.answer()

# ----------------------------------------------------------------------
# 6. Угадай число (уже есть в предыдущем коде, но продублируем для полноты)
# ----------------------------------------------------------------------
@router.callback_query(F.data == "game_guess")
async def guess_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🔢 Угадай число от 1 до 10\nВведите число и ставку, например: 7 20",
        reply_markup=back_to_main()
    )
    await state.set_state(GameStates.guess_number)
    await callback.answer()

@router.message(GameStates.guess_number)
async def guess_play(message: Message, state: FSMContext, bot: Bot):
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Введите: <число> <ставка>")
        return
    try:
        guess = int(parts[0])
        bet = int(parts[1])
        if not (1 <= guess <= 10) or bet <= 0:
            raise ValueError
    except:
        await message.answer("Неверный формат. Число от 1 до 10, ставка >0.")
        return
    user_id = message.from_user.id
    ok, err = await check_balance_and_deduct(user_id, "nm", bet)
    if not ok:
        await message.answer(err)
        await state.clear()
        return
    number = random.randint(1, 10)
    if guess == number:
        win = bet * 5
        update_balance(user_id, "nm", win)
        text = f"🎯 Загадано {number}. Вы угадали! +{win} NM."
        if win >= bet * 10:
            add_achievement(user_id, "guess_master")
    else:
        text = f"🎯 Загадано {number}. Не угадали. Проигрыш {bet} NM."
    await message.answer(text, reply_markup=main_menu)
    await state.clear()

# ----------------------------------------------------------------------
# 7. Кено
# ----------------------------------------------------------------------
@router.callback_query(F.data == "game_keno")
async def keno_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🎴 Кено\nВведите 5 чисел от 1 до 20 и ставку, например: 5 12 7 19 3 50",
        reply_markup=back_to_main()
    )
    await state.set_state(GameStates.keno_choose)
    await callback.answer()

@router.message(GameStates.keno_choose)
async def keno_play(message: Message, state: FSMContext, bot: Bot):
    parts = message.text.split()
    if len(parts) != 6:
        await message.answer("Нужно ровно 5 чисел и ставка.")
        return
    try:
        numbers = [int(x) for x in parts[:5]]
        bet = int(parts[5])
        if any(n < 1 or n > 20 for n in numbers) or bet <= 0:
            raise ValueError
    except:
        await message.answer("Неверный формат. Числа от 1 до 20, ставка >0.")
        return
    user_id = message.from_user.id
    ok, err = await check_balance_and_deduct(user_id, "nm", bet)
    if not ok:
        await message.answer(err)
        await state.clear()
        return
    drawn = random.sample(range(1, 21), 10)
    matches = len(set(numbers) & set(drawn))
    payouts = {0:0, 1:0, 2:0, 3:bet*2, 4:bet*10, 5:bet*50}
    win = payouts.get(matches, 0)
    if win:
        update_balance(user_id, "nm", win)
        text = f"🎴 Выпало: {sorted(drawn)}\nСовпадений: {matches}\nВыигрыш: {win} NM."
        if matches >= 4:
            add_achievement(user_id, "keno_pro")
    else:
        text = f"🎴 Выпало: {sorted(drawn)}\nСовпадений: {matches}\nПроигрыш."
    await message.answer(text, reply_markup=main_menu)
    await state.clear()

# ----------------------------------------------------------------------
# 8. Блэкджек
# ----------------------------------------------------------------------
@router.callback_query(F.data == "game_blackjack")
async def blackjack_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🃏 Блэкджек. Введите ставку (NM):", reply_markup=back_to_main())
    await state.set_state(GameStates.blackjack_bet)
    await callback.answer()

@router.message(GameStates.blackjack_bet)
async def blackjack_play(message: Message, state: FSMContext, bot: Bot):
    try:
        bet = int(message.text)
        if bet <= 0: raise ValueError
    except:
        await message.answer("Введите положительное число.")
        return
    user_id = message.from_user.id
    ok, err = await check_balance_and_deduct(user_id, "nm", bet)
    if not ok:
        await message.answer(err)
        await state.clear()
        return
    # колода
    deck = [2,3,4,5,6,7,8,9,10,10,10,10,11] * 4
    random.shuffle(deck)
    player_hand = [deck.pop(), deck.pop()]
    dealer_hand = [deck.pop(), deck.pop()]
    def hand_value(hand):
        val = sum(hand)
        aces = hand.count(11)
        while val > 21 and aces:
            val -= 10
            aces -= 1
        return val
    # игрок добирает до 17 (упрощённо)
    while hand_value(player_hand) < 17:
        player_hand.append(deck.pop())
    # дилер
    while hand_value(dealer_hand) < 17:
        dealer_hand.append(deck.pop())
    pv = hand_value(player_hand)
    dv = hand_value(dealer_hand)
    if pv > 21:
        win = 0
        text = f"Ваши карты: {player_hand} ({pv})\nДилер: {dealer_hand} ({dv})\nПеребор! Вы проиграли."
    elif dv > 21 or pv > dv:
        win = bet * 2
        update_balance(user_id, "nm", win)
        text = f"Ваши карты: {player_hand} ({pv})\nДилер: {dealer_hand} ({dv})\nВы выиграли! +{win} NM."
        if win >= bet * 3:
            add_achievement(user_id, "blackjack_win")
    elif pv == dv:
        win = bet
        update_balance(user_id, "nm", win)
        text = f"Ваши карты: {player_hand} ({pv})\nДилер: {dealer_hand} ({dv})\nНичья. Ставка возвращена."
    else:
        win = 0
        text = f"Ваши карты: {player_hand} ({pv})\nДилер: {dealer_hand} ({dv})\nВы проиграли."
    await message.answer(text, reply_markup=main_menu)
    await state.clear()

# ----------------------------------------------------------------------
# 9. Баккара
# ----------------------------------------------------------------------
@router.callback_query(F.data == "game_baccarat")
async def baccarat_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🃏 Баккара. Ставка на Игрока (P) или Банкира (B), например: P 50",
        reply_markup=back_to_main()
    )
    await state.set_state(GameStates.baccarat_bet)
    await callback.answer()

@router.message(GameStates.baccarat_bet)
async def baccarat_play(message: Message, state: FSMContext, bot: Bot):
    parts = message.text.split()
    if len(parts) != 2 or parts[0] not in ("P", "B"):
        await message.answer("Неверный формат. Пример: P 50")
        return
    try:
        bet = int(parts[1])
        if bet <= 0: raise ValueError
    except:
        await message.answer("Ставка должна быть числом >0.")
        return
    user_id = message.from_user.id
    ok, err = await check_balance_and_deduct(user_id, "nm", bet)
    if not ok:
        await message.answer(err)
        await state.clear()
        return
    # симуляция
    def card_value(c):
        if c >= 10: return 0
        return c
    deck = list(range(1,14))*4
    random.shuffle(deck)
    player = [deck.pop(), deck.pop()]
    banker = [deck.pop(), deck.pop()]
    pv = (card_value(player[0]) + card_value(player[1])) % 10
    bv = (card_value(banker[0]) + card_value(banker[1])) % 10
    # третья карта (упрощённо)
    if pv in (0,1,2,3,4,5):
        player.append(deck.pop())
        pv = (pv + card_value(player[-1])) % 10
    if bv in (0,1,2,3,4,5):
        banker.append(deck.pop())
        bv = (bv + card_value(banker[-1])) % 10
    if parts[0] == "P":
        if pv > bv:
            win = bet * 2
            update_balance(user_id, "nm", win)
            text = f"Игрок: {player} = {pv}, Банкир: {banker} = {bv}\nВы выиграли! +{win} NM."
            add_achievement(user_id, "baccarat_win")
        elif pv == bv:
            win = bet
            update_balance(user_id, "nm", win)
            text = f"Игрок: {player} = {pv}, Банкир: {banker} = {bv}\nНичья. Ставка возвращена."
        else:
            win = 0
            text = f"Игрок: {player} = {pv}, Банкир: {banker} = {bv}\nВы проиграли."
    else:  # Banker
        if bv > pv:
            win = bet * 2 - int(bet*0.05)
            update_balance(user_id, "nm", win)
            text = f"Игрок: {player} = {pv}, Банкир: {banker} = {bv}\nВы выиграли! +{win} NM."
        elif bv == pv:
            win = bet
            update_balance(user_id, "nm", win)
            text = f"Игрок: {player} = {pv}, Банкир: {banker} = {bv}\nНичья. Ставка возвращена."
        else:
            win = 0
            text = f"Игрок: {player} = {pv}, Банкир: {banker} = {bv}\nВы проиграли."
    await message.answer(text, reply_markup=main_menu)
    await state.clear()

# ----------------------------------------------------------------------
# 10. Покер (упрощённый 5-карточный)
# ----------------------------------------------------------------------
@router.callback_query(F.data == "game_poker")
async def poker_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "♠️ Покер. Введите ставку (NM):",
        reply_markup=back_to_main()
    )
    await state.set_state(GameStates.poker_bet)
    await callback.answer()

@router.message(GameStates.poker_bet)
async def poker_play(message: Message, state: FSMContext, bot: Bot):
    try:
        bet = int(message.text)
        if bet <= 0: raise ValueError
    except:
        await message.answer("Введите положительное число.")
        return
    user_id = message.from_user.id
    ok, err = await check_balance_and_deduct(user_id, "nm", bet)
    if not ok:
        await message.answer(err)
        await state.clear()
        return
    # Создаем колоду и раздаем 5 карт игроку и 5 дилеру (техасский холдем упрощённо)
    # Для простоты сравниваем старшие комбинации
    ranks = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]
    suits = ["♠","♥","♦","♣"]
    deck = [(r,s) for r in ranks for s in suits]
    random.shuffle(deck)
    player_hand = [deck.pop() for _ in range(5)]
    dealer_hand = [deck.pop() for _ in range(5)]
    def hand_rank(hand):
        # простейшая оценка: количество пар, стрит, флеш и т.д.
        # вернем числовой ранг для сравнения
        values = sorted([ranks.index(c[0]) for c in hand], reverse=True)
        is_flush = len(set(c[1] for c in hand)) == 1
        is_straight = False
        if len(set(values)) == 5:
            if max(values) - min(values) == 4:
                is_straight = True
            elif set(values) == {12,0,1,2,3}:  # туз-2-3-4-5
                is_straight = True
        # подсчет пар
        counts = {}
        for v in values:
            counts[v] = counts.get(v, 0) + 1
        counts_sorted = sorted(counts.values(), reverse=True)
        if is_straight and is_flush:
            return 9  # стрит-флеш
        if 4 in counts_sorted:
            return 8  # каре
        if 3 in counts_sorted and 2 in counts_sorted:
            return 7  # фулл-хаус
        if is_flush:
            return 6  # флеш
        if is_straight:
            return 5  # стрит
        if 3 in counts_sorted:
            return 4  # сет
        if counts_sorted.count(2) == 2:
            return 3  # две пары
        if 2 in counts_sorted:
            return 2  # пара
        return 1  # старшая карта
    pr = hand_rank(player_hand)
    dr = hand_rank(dealer_hand)
    if pr > dr:
        win = bet * 2
        update_balance(user_id, "nm", win)
        text = f"Ваши карты: {player_hand}\nДилер: {dealer_hand}\nВы выиграли! +{win} NM."
        if pr >= 8:
            add_achievement(user_id, "poker_royal")
    elif pr == dr:
        win = bet
        update_balance(user_id, "nm", win)
        text = f"Ваши карты: {player_hand}\nДилер: {dealer_hand}\nНичья. Ставка возвращена."
    else:
        win = 0
        text = f"Ваши карты: {player_hand}\nДилер: {dealer_hand}\nВы проиграли."
    await message.answer(text, reply_markup=main_menu)
    await state.clear()

# ----------------------------------------------------------------------
# 11. Лотерея (покупка билета)
# ----------------------------------------------------------------------
@router.callback_query(F.data == "game_lottery")
async def lottery_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🎫 Лотерея\nВведите количество билетов (каждый стоит 10 NM), например: 3",
        reply_markup=back_to_main()
    )
    await state.set_state(GameStates.lottery_buy)
    await callback.answer()

@router.message(GameStates.lottery_buy)
async def lottery_play(message: Message, state: FSMContext, bot: Bot):
    try:
        tickets = int(message.text)
        if tickets <= 0:
            raise ValueError
    except:
        await message.answer("Введите положительное число.")
        return
    bet = tickets * 10
    user_id = message.from_user.id
    ok, err = await check_balance_and_deduct(user_id, "nm", bet)
    if not ok:
        await message.answer(err)
        await state.clear()
        return
    # Розыгрыш: шанс выиграть 50% от стоимости билетов * случайный множитель
    win = 0
    for _ in range(tickets):
        if random.random() < 0.3:  # 30% шанс на выигрыш с билета
            win += random.randint(20, 100)
    if win > 0:
        update_balance(user_id, "nm", win)
        text = f"🎫 Вы купили {tickets} билетов. Выигрыш: {win} NM!"
        if win >= 200:
            add_achievement(user_id, "lottery_winner")
    else:
        text = f"🎫 Вы купили {tickets} билетов. К сожалению, ничего не выиграли."
    await message.answer(text, reply_markup=main_menu)
    await state.clear()

# ----------------------------------------------------------------------
# 12. Колесо фортуны
# ----------------------------------------------------------------------
@router.callback_query(F.data == "game_wheel")
async def wheel_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🎡 Колесо фортуны\nВведите ставку (NM):",
        reply_markup=back_to_main()
    )
    await state.set_state(GameStates.wheel_bet)
    await callback.answer()

@router.message(GameStates.wheel_bet)
async def wheel_play(message: Message, state: FSMContext, bot: Bot):
    try:
        bet = int(message.text)
        if bet <= 0: raise ValueError
    except:
        await message.answer("Введите положительное число.")
        return
    user_id = message.from_user.id
    ok, err = await check_balance_and_deduct(user_id, "nm", bet)
    if not ok:
        await message.answer(err)
        await state.clear()
        return
    # Сектора: множители 0, 1, 2, 3, 5, 10, 20, 50 (разные вероятности)
    sectors = [0]*10 + [1]*20 + [2]*15 + [3]*10 + [5]*5 + [10]*3 + [20]*2 + [50]*1
    multiplier = random.choice(sectors)
    win = bet * multiplier
    if win > 0:
        update_balance(user_id, "nm", win)
        text = f"🎡 Колесо остановилось на множителе x{multiplier}!\nВы выиграли {win} NM!"
        if multiplier >= 20:
            add_achievement(user_id, "wheel_lucky")
    else:
        text = f"🎡 Колесо остановилось на x0. Вы проиграли {bet} NM."
    await message.answer(text, reply_markup=main_menu)
    await state.clear()

# ----------------------------------------------------------------------
# 13. Dice мультипликатор (бросок кубика, множитель от 1 до 6)
# ----------------------------------------------------------------------
@router.callback_query(F.data == "game_dice_multiplier")
async def dice_multiplier_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🎲 Dice (мультипликатор)\nВведите ставку (NM):",
        reply_markup=back_to_main()
    )
    await state.set_state(GameStates.dice_multiplier_bet)
    await callback.answer()

@router.message(GameStates.dice_multiplier_bet)
async def dice_multiplier_play(message: Message, state: FSMContext, bot: Bot):
    try:
        bet = int(message.text)
        if bet <= 0: raise ValueError
    except:
        await message.answer("Введите положительное число.")
        return
    user_id = message.from_user.id
    ok, err = await check_balance_and_deduct(user_id, "nm", bet)
    if not ok:
        await message.answer(err)
        await state.clear()
        return
    roll = random.randint(1, 6)
    win = bet * roll
    update_balance(user_id, "nm", win)
    text = f"🎲 Выпало {roll}. Ваш выигрыш: {win} NM!"
    if roll == 6:
        add_achievement(user_id, "dice_six")
    await message.answer(text, reply_markup=main_menu)
    await state.clear()

# ----------------------------------------------------------------------
# 14. Crash (простая версия)
# ----------------------------------------------------------------------
@router.callback_query(F.data == "game_crash")
async def crash_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📉 Crash\nВведите ставку (NM):",
        reply_markup=back_to_main()
    )
    await state.set_state(GameStates.crash_bet)
    await callback.answer()

@router.message(GameStates.crash_bet)
async def crash_play(message: Message, state: FSMContext, bot: Bot):
    try:
        bet = int(message.text)
        if bet <= 0: raise ValueError
    except:
        await message.answer("Введите положительное число.")
        return
    user_id = message.from_user.id
    ok, err = await check_balance_and_deduct(user_id, "nm", bet)
    if not ok:
        await message.answer(err)
        await state.clear()
        return
    # crash point случайно от 1.0 до 10.0 с шагом 0.1
    crash_point = round(random.uniform(1.0, 10.0), 1)
    # игрок выигрывает, если выбрал кэшаут до краша, но мы упростим: случайно решаем, выиграл ли
    # в реальности игрок должен нажимать кнопку, но здесь упростим
    # Пусть игрок автоматически кэшаутится на случайном множителе от 1.0 до crash_point
    cashout = round(random.uniform(1.0, crash_point), 1)
    if cashout < crash_point:
        win = int(bet * cashout)
        update_balance(user_id, "nm", win)
        text = f"📉 Краш произошёл на {crash_point}x. Вы кэшаутились на {cashout}x.\nВыигрыш: {win} NM."
        if cashout >= 5:
            add_achievement(user_id, "crash_hero")
    else:
        win = 0
        text = f"📉 Краш произошёл на {crash_point}x. Вы не успели выйти. Проигрыш."
    await message.answer(text, reply_markup=main_menu)
    await state.clear()

# ----------------------------------------------------------------------
# 15. Mines (поле 5x5, выбираем ячейки)
# ----------------------------------------------------------------------
@router.callback_query(F.data == "game_mines")
async def mines_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "💣 Mines\nВведите ставку (NM):",
        reply_markup=back_to_main()
    )
    await state.set_state(GameStates.mines_bet)
    await callback.answer()

@router.message(GameStates.mines_bet)
async def mines_play(message: Message, state: FSMContext, bot: Bot):
    try:
        bet = int(message.text)
        if bet <= 0: raise ValueError
    except:
        await message.answer("Введите положительное число.")
        return
    user_id = message.from_user.id
    ok, err = await check_balance_and_deduct(user_id, "nm", bet)
    if not ok:
        await message.answer(err)
        await state.clear()
        return
    # Создаем поле 5x5, 5 мин
    grid = [[0]*5 for _ in range(5)]
    mine_positions = random.sample(range(25), 5)
    for pos in mine_positions:
        row = pos // 5
        col = pos % 5
        grid[row][col] = 1  # мина
    # Игрок выбирает 3 ячейки (упрощённо)
    choices = random.sample(range(25), 3)
    hit_mine = False
    for pos in choices:
        row = pos // 5
        col = pos % 5
        if grid[row][col] == 1:
            hit_mine = True
            break
    if not hit_mine:
        win = bet * 3
        update_balance(user_id, "nm", win)
        text = f"💣 Вы открыли 3 ячейки, мины не попались!\nВыигрыш: {win} NM."
        add_achievement(user_id, "mines_clear")
    else:
        win = 0
        text = "💣 Вы попали на мину! Проигрыш."
    await message.answer(text, reply_markup=main_menu)
    await state.clear()

# ----------------------------------------------------------------------
# 16. Plinko (диск падает на штырьки)
# ----------------------------------------------------------------------
@router.callback_query(F.data == "game_plinko")
async def plinko_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📌 Plinko\nВведите ставку (NM):",
        reply_markup=back_to_main()
    )
    await state.set_state(GameStates.plinko_bet)
    await callback.answer()

@router.message(GameStates.plinko_bet)
async def plinko_play(message: Message, state: FSMContext, bot: Bot):
    try:
        bet = int(message.text)
        if bet <= 0: raise ValueError
    except:
        await message.answer("Введите положительное число.")
        return
    user_id = message.from_user.id
    ok, err = await check_balance_and_deduct(user_id, "nm", bet)
    if not ok:
        await message.answer(err)
        await state.clear()
        return
    # Множители для 8 ячеек: [0.5, 1, 2, 3, 3, 2, 1, 0.5]
    multipliers = [0.5, 1, 2, 3, 3, 2, 1, 0.5]
    # Симулируем падение (случайный индекс)
    idx = random.randint(0, 7)
    multiplier = multipliers[idx]
    win = int(bet * multiplier)
    if multiplier > 1:
        update_balance(user_id, "nm", win)
        text = f"📌 Диск упал в ячейку с множителем x{multiplier}\nВыигрыш: {win} NM."
        if multiplier >= 3:
            add_achievement(user_id, "plinko_lucky")
    else:
        win = 0
        text = f"📌 Диск упал в ячейку x{multiplier}. Проигрыш."
    await message.answer(text, reply_markup=main_menu)
    await state.clear()

# ----------------------------------------------------------------------
# 17. Покерные кости (5 костей с символами)
# ----------------------------------------------------------------------
@router.callback_query(F.data == "game_poker_dice")
async def poker_dice_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🎲 Покерные кости\nВведите ставку (NM):",
        reply_markup=back_to_main()
    )
    await state.set_state(GameStates.poker_dice_bet)
    await callback.answer()

@router.message(GameStates.poker_dice_bet)
async def poker_dice_play(message: Message, state: FSMContext, bot: Bot):
    try:
        bet = int(message.text)
        if bet <= 0: raise ValueError
    except:
        await message.answer("Введите положительное число.")
        return
    user_id = message.from_user.id
    ok, err = await check_balance_and_deduct(user_id, "nm", bet)
    if not ok:
        await message.answer(err)
        await state.clear()
        return
    symbols = ["A", "K", "Q", "J", "10", "9"]
    dice = [random.choice(symbols) for _ in range(5)]
    # Проверка комбинаций: каре, фулл-хаус, стрит и т.д.
    counts = {s: dice.count(s) for s in set(dice)}
    counts_values = sorted(counts.values(), reverse=True)
    if counts_values[0] == 5:
        multiplier = 10
    elif counts_values[0] == 4:
        multiplier = 6
    elif counts_values[0] == 3 and counts_values[1] == 2:
        multiplier = 4
    elif counts_values[0] == 3:
        multiplier = 3
    elif counts_values[0] == 2 and counts_values[1] == 2:
        multiplier = 2
    elif counts_values[0] == 2:
        multiplier = 1.5
    else:
        multiplier = 0
    win = int(bet * multiplier)
    if win > 0:
        update_balance(user_id, "nm", win)
        text = f"🎲 Выпало: {dice}\nКомбинация: x{multiplier}\nВыигрыш: {win} NM."
        if multiplier >= 4:
            add_achievement(user_id, "poker_dice_pro")
    else:
        text = f"🎲 Выпало: {dice}\nНет комбинации. Проигрыш."
    await message.answer(text, reply_markup=main_menu)
    await state.clear()

# ----------------------------------------------------------------------
# 18. Один кубик (угадать число)
# ----------------------------------------------------------------------
@router.callback_query(F.data == "game_single_dice")
async def single_dice_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🎲 Один кубик\nВведите ставку и число (1-6), например: 20 3",
        reply_markup=back_to_main()
    )
    await state.set_state(GameStates.single_dice_bet)
    await callback.answer()

@router.message(GameStates.single_dice_bet)
async def single_dice_play(message: Message, state: FSMContext, bot: Bot):
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Введите: <ставка> <число>")
        return
    try:
        bet = int(parts[0])
        guess = int(parts[1])
        if bet <= 0 or not (1 <= guess <= 6):
            raise ValueError
    except:
        await message.answer("Неверный формат.")
        return
    user_id = message.from_user.id
    ok, err = await check_balance_and_deduct(user_id, "nm", bet)
    if not ok:
        await message.answer(err)
        await state.clear()
        return
    roll = random.randint(1, 6)
    if guess == roll:
        win = bet * 5
        update_balance(user_id, "nm", win)
        text = f"🎲 Выпало {roll}. Вы угадали! +{win} NM."
        add_achievement(user_id, "single_dice_win")
    else:
        text = f"🎲 Выпало {roll}. Не угадали. Проигрыш {bet} NM."
    await message.answer(text, reply_markup=main_menu)
    await state.clear()

# ----------------------------------------------------------------------
# 19. Бинго (упрощённое)
# ----------------------------------------------------------------------
@router.callback_query(F.data == "game_bingo")
async def bingo_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🎟️ Бинго\nВведите ставку (NM):",
        reply_markup=back_to_main()
    )
    await state.set_state(GameStates.bingo_bet)
    await callback.answer()

@router.message(GameStates.bingo_bet)
async def bingo_play(message: Message, state: FSMContext, bot: Bot):
    try:
        bet = int(message.text)
        if bet <= 0: raise ValueError
    except:
        await message.answer("Введите положительное число.")
        return
    user_id = message.from_user.id
    ok, err = await check_balance_and_deduct(user_id, "nm", bet)
    if not ok:
        await message.answer(err)
        await state.clear()
        return
    # Карточка 5x5 с числами 1-25
    card = random.sample(range(1, 26), 25)
    # Вытаскиваем 10 чисел
    drawn = random.sample(range(1, 26), 10)
    # Проверяем, есть ли хотя бы одна заполненная строка
    bingo = False
    for i in range(5):
        row = card[i*5:(i+1)*5]
        if all(x in drawn for x in row):
            bingo = True
            break
    if bingo:
        win = bet * 5
        update_balance(user_id, "nm", win)
        text = f"🎟️ БИНГО! Вы выиграли {win} NM!"
        add_achievement(user_id, "bingo_winner")
    else:
        text = "🎟️ Нет БИНГО. Проигрыш."
    await message.answer(text, reply_markup=main_menu)
    await state.clear()

# ----------------------------------------------------------------------
# 20. Камень-ножницы-бумага
# ----------------------------------------------------------------------
@router.callback_query(F.data == "game_rps")
async def rps_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "✊ Камень-ножницы-бумага\nВведите ставку и ваш выбор (камень, ножницы, бумага), например: 50 камень",
        reply_markup=back_to_main()
    )
    await state.set_state(GameStates.rps_bet)
    await callback.answer()

@router.message(GameStates.rps_bet)
async def rps_play(message: Message, state: FSMContext, bot: Bot):
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Введите: <ставка> <выбор>")
        return
    try:
        bet = int(parts[0])
        if bet <= 0: raise ValueError
        choice = parts[1].lower()
        if choice not in ("камень", "ножницы", "бумага"):
            raise ValueError
    except:
        await message.answer("Неверный формат.")
        return
    user_id = message.from_user.id
    ok, err = await check_balance_and_deduct(user_id, "nm", bet)
    if not ok:
        await message.answer(err)
        await state.clear()
        return
    bot_choice = random.choice(["камень", "ножницы", "бумага"])
    if choice == bot_choice:
        win = bet
        update_balance(user_id, "nm", win)
        text = f"✊ Ничья! Ставка возвращена."
    elif (choice == "камень" and bot_choice == "ножницы") or \
         (choice == "ножницы" and bot_choice == "бумага") or \
         (choice == "бумага" and bot_choice == "камень"):
        win = bet * 2
        update_balance(user_id, "nm", win)
        text = f"✊ Вы выиграли! +{win} NM."
        add_achievement(user_id, "rps_winner")
    else:
        win = 0
        text = f"✊ Вы проиграли. {bot_choice} побеждает."
    text += f"\nВаш выбор: {choice}\nБот: {bot_choice}"
    await message.answer(text, reply_markup=main_menu)
    await state.clear()

# ----------------------------------------------------------------------
# 21. Монетка (2 стороны) - аналогично орёл/решка, но с другим названием
# ----------------------------------------------------------------------
@router.callback_query(F.data == "game_coin_flip")
async def coin_flip_game(callback: CallbackQuery, bot: Bot):
    # почти идентично game_coin, но с другим именем
    user_id = callback.from_user.id
    amount = 10
    ok, msg = await check_balance_and_deduct(user_id, "nm", amount)
    if not ok:
        await callback.answer(msg, show_alert=True)
        return
    side = random.choice(["Орёл", "Решка"])
    if random.random() < 0.5:
        win = amount * 2
        update_balance(user_id, "nm", win)
        text = f"🪙 Выпал: {side}\n🎉 Вы выиграли {win} NM!"
    else:
        text = f"🪙 Выпал: {side}\n😔 Проигрыш."
    await callback.message.edit_text(text, reply_markup=back_to_main())
    await callback.answer()

# ----------------------------------------------------------------------
# 22. Слот Джекпот (прогрессивный джекпот)
# ----------------------------------------------------------------------
@router.callback_query(F.data == "game_jackpot_slot")
async def jackpot_slot(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    amount = 20
    ok, msg = await check_balance_and_deduct(user_id, "nm", amount)
    if not ok:
        await callback.answer(msg, show_alert=True)
        return
    symbols = ["🍒", "🍋", "🍊", "7️⃣", "💎", "⭐", "🔥"]
    reel = [random.choice(symbols) for _ in range(3)]
    result = " ".join(reel)
    if reel[0] == reel[1] == reel[2]:
        if reel[0] == "7️⃣":
            win = amount * 100  # джекпот
        elif reel[0] == "💎":
            win = amount * 30
        elif reel[0] == "🔥":
            win = amount * 50
        else:
            win = amount * 5
    elif reel[0] == reel[1] or reel[1] == reel[2] or reel[0] == reel[2]:
        win = amount * 2
    else:
        win = 0
    if win > 0:
        update_balance(user_id, "nm", win)
        text = f"🔥 {result}\n\n🎉 Джекпот! Вы выиграли {win} NM!"
        if win >= amount * 50:
            add_achievement(user_id, "jackpot_winner")
    else:
        text = f"🔥 {result}\n\n😔 Проигрыш."
    await callback.message.edit_text(text, reply_markup=back_to_main())
    await callback.answer()

# ----------------------------------------------------------------------
# 23. Слот Фрукты 2 (вариация)
# ----------------------------------------------------------------------
@router.callback_query(F.data == "game_slots2")
async def fruit_slot2(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    amount = 15
    ok, msg = await check_balance_and_deduct(user_id, "nm", amount)
    if not ok:
        await callback.answer(msg, show_alert=True)
        return
    symbols = ["🍎", "🍐", "🍒", "🍇", "🍉", "🍓", "🍑"]
    reel = [random.choice(symbols) for _ in range(3)]
    result = " ".join(reel)
    if reel[0] == reel[1] == reel[2]:
        if reel[0] == "🍎":
            win = amount * 10
        elif reel[0] == "🍑":
            win = amount * 15
        else:
            win = amount * 4
    elif reel[0] == reel[1] or reel[1] == reel[2] or reel[0] == reel[2]:
        win = amount * 2
    else:
        win = 0
    if win > 0:
        update_balance(user_id, "nm", win)
        text = f"🍒 {result}\n\n🍀 Выигрыш: {win} NM!"
    else:
        text = f"🍒 {result}\n\n😔 Проигрыш."
    await callback.message.edit_text(text, reply_markup=back_to_main())
    await callback.answer()

# ----------------------------------------------------------------------
# 24. Слот Фрукты 3 (ещё одна вариация)
# ----------------------------------------------------------------------
@router.callback_query(F.data == "game_slots3")
async def fruit_slot3(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    amount = 10
    ok, msg = await check_balance_and_deduct(user_id, "nm", amount)
    if not ok:
        await callback.answer(msg, show_alert=True)
        return
    symbols = ["🍒", "🍋", "🍊", "🍇", "🔔", "💎", "⭐"]
    reel = [random.choice(symbols) for _ in range(3)]
    result = " ".join(reel)
    if reel[0] == reel[1] == reel[2]:
        if reel[0] == "⭐":
            win = amount * 30
        elif reel[0] == "💎":
            win = amount * 25
        else:
            win = amount * 5
    elif reel[0] == reel[1] or reel[1] == reel[2] or reel[0] == reel[2]:
        win = amount * 2
    else:
        win = 0
    if win > 0:
        update_balance(user_id, "nm", win)
        text = f"🎰 {result}\n\n🎉 Выигрыш: {win} NM!"
    else:
        text = f"🎰 {result}\n\n😔 Проигрыш."
    await callback.message.edit_text(text, reply_markup=back_to_main())
    await callback.answer()
