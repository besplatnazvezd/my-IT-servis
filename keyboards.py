from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

main_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🎰 Игры", callback_data="games_menu")],
    [InlineKeyboardButton(text="💰 Баланс", callback_data="balance")],
    [InlineKeyboardButton(text="🎁 Ежедневный бонус", callback_data="daily_bonus")],
    [InlineKeyboardButton(text="👥 Рефералы", callback_data="ref_system")],
    [InlineKeyboardButton(text="🏆 Достижения", callback_data="achievements")],
    [InlineKeyboardButton(text="⭐ Купить NM", callback_data="buy_nm")],
])

games_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🎲 Слоты", callback_data="game_slots")],
    [InlineKeyboardButton(text="🎡 Рулетка", callback_data="game_roulette")],
    [InlineKeyboardButton(text="🎲 Кости", callback_data="game_dice")],
    [InlineKeyboardButton(text="🪙 Орёл/Решка", callback_data="game_coin")],
    [InlineKeyboardButton(text="🔢 Угадай число", callback_data="game_guess")],
    [InlineKeyboardButton(text="🎴 Кено", callback_data="game_keno")],
    [InlineKeyboardButton(text="🃏 Блэкджек", callback_data="game_blackjack")],
    [InlineKeyboardButton(text="🃏 Баккара", callback_data="game_baccarat")],
    [InlineKeyboardButton(text="♠️ Покер", callback_data="game_poker")],
    [InlineKeyboardButton(text="🎫 Лотерея", callback_data="game_lottery")],
    [InlineKeyboardButton(text="🎡 Колесо фортуны", callback_data="game_wheel")],
    [InlineKeyboardButton(text="🎲 Dice (мультипликатор)", callback_data="game_dice_multiplier")],
    [InlineKeyboardButton(text="📉 Crash", callback_data="game_crash")],
    [InlineKeyboardButton(text="💣 Mines", callback_data="game_mines")],
    [InlineKeyboardButton(text="📌 Plinko", callback_data="game_plinko")],
    [InlineKeyboardButton(text="🎲 Покерные кости", callback_data="game_poker_dice")],
    [InlineKeyboardButton(text="🎲 Один кубик", callback_data="game_single_dice")],
    [InlineKeyboardButton(text="🎟️ Бинго", callback_data="game_bingo")],
    [InlineKeyboardButton(text="✊ Камень-ножницы-бумага", callback_data="game_rps")],
    [InlineKeyboardButton(text="🪙 Монетка (2 стороны)", callback_data="game_coin_flip")],
    [InlineKeyboardButton(text="💰 Слот Джекпот", callback_data="game_jackpot")],
    [InlineKeyboardButton(text="🎰 Слот Фрукты 2", callback_data="game_slots2")],
    [InlineKeyboardButton(text="🎰 Слот Фрукты 3", callback_data="game_slots3")],
    [InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")],
])

slot_games_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🍒 Слот Фрукты", callback_data="game_fruit_slot")],
    [InlineKeyboardButton(text="💎 Слот Сокровища", callback_data="game_treasure_slot")],
    [InlineKeyboardButton(text="🔥 Слот Джекпот", callback_data="game_jackpot_slot")],
    [InlineKeyboardButton(text="⬅️ Назад", callback_data="games_menu")],
])

def buy_nm_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ 100 NM за 5⭐", callback_data="buy_100")],
        [InlineKeyboardButton(text="⭐ 500 NM за 20⭐", callback_data="buy_500")],
        [InlineKeyboardButton(text="⭐ 2000 NM за 70⭐", callback_data="buy_2000")],
        [InlineKeyboardButton(text="⭐ 10000 NM + 10 NMX за 300⭐", callback_data="buy_10000")],
    ])

def back_to_main():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="main_menu")]
    ])
