import logging
import os
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# Загружаем переменные окружения из .env файла
load_dotenv()

# --- Конфигурация ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))  # Ваш Telegram User ID администратора (число)

# Включаем логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Вспомогательные функции ---
def get_user_mention(user_id, username):
    """Возвращает HTML-ссылку для упоминания пользователя."""
    if username:
        return f"<a href='tg://user?id={user_id}'>@{username}</a>"
    return f"<a href='tg://user?id={user_id}'>User {user_id}</a>"

def get_mcoin_amount(evaluation_type):
    """Возвращает количество мкоинов в зависимости от типа оценки."""
    if evaluation_type == "🟢":
        return "1,000,000"  # 1kk
    elif evaluation_type == "🟡":
        return "100,000"
    elif evaluation_type == "🔴":
        return "1,000"
    return "0"

def is_dash_or_minus(text: str) -> bool:
    """Проверяет, является ли введенный текст минусом, дефисом или тире."""
    clean_text = text.strip()
    return clean_text in ["-", "—", "–", "_"]

# --- Обработчики для пользователя ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start. Переводит пользователя в режим ожидания идеи."""
    user = update.effective_user
    logger.info(f"User {user.id} ({user.username}) started the bot.")

    welcome_message = (
        f"Привет {user.mention_html()}!\n\n"
        "Здесь ты получаешь мкоин за описание своей идеи для бота.\n\n"
        "<b>Оценивание работы</b>\n"
        "🟢 Идея понравилась автору+полное описание. Оплата: 1кк\n"
        "🟡 Идея привлекла внимание, есть описание. Оплата: 100к\n"
        "🔴 Идея не понравилась, но спасибо. Оплата: 1к\n\n"
        "Пиши ниже свою идею и попробуй получить 1кк!"
    )
    await update.message.reply_html(welcome_message)
    
    # Устанавливаем пользователю статус ожидания идеи
    context.user_data["state"] = "awaiting_idea"


async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает входящие текстовые сообщения от обычных пользователей."""
    user = update.effective_user
    
    # Игнорируем сообщения от администратора в общем обработчике
    if user.id == ADMIN_ID:
        return

    state = context.user_data.get("state")

    if state == "awaiting_idea":
        idea_text = update.message.text
        logger.info(f"User {user.id} submitted an idea.")

        # Кнопки оценки для админа
        keyboard = [
            [
                InlineKeyboardButton("🟢", callback_data=f"evaluate_🟢_{user.id}"),
                InlineKeyboardButton("🟡", callback_data=f"evaluate_🟡_{user.id}"),
                InlineKeyboardButton("🔴", callback_data=f"evaluate_🔴_{user.id}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Отправляем идею админу
        admin_message_text = (
            f"Новая идея от {get_user_mention(user.id, user.username)} (ID: <code>{user.id}</code>):\n\n"
            f"<b>Идея:</b>\n{idea_text}"
        )
        admin_message = await context.bot.send_message(
            chat_id=ADMIN_ID, text=admin_message_text, reply_markup=reply_markup, parse_mode='HTML'
        )

        # Сохраняем связку сообщения админа с данными пользователя в глобальную память
        context.bot_data[f"admin_msg_{admin_message.message_id}"] = {
            "user_id": user.id,
            "username": user.username,
        }

        # Сбрасываем статус пользователя
        context.user_data["state"] = None
        await update.message.reply_text("Спасибо! Ваша идея отправлена на рассмотрение. Ждите оценки!")

    elif state == "awaiting_answer":
        answer_text = update.message.text
        logger.info(f"User {user.id} answered admin's question.")

        # Получаем данные активной сессии админа
        session = context.bot_data.get("active_admin_session")

        if not session or session["target_user_id"] != user.id:
            await update.message.reply_text("Произошла ошибка сессии. Возможно, админ уже закрыл обсуждение.")
            context.user_data["state"] = None
            return

        original_admin_message_id = session["original_admin_message_id"]

        # Пересылаем ответ админу
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"💬 <b>Ответ от {get_user_mention(user.id, user.username)}:</b>\n\n{answer_text}",
            reply_to_message_id=original_admin_message_id,
            parse_mode='HTML'
        )

        # Возвращаем админа в режим ожидания вопросов
        session["state"] = "awaiting_question_or_dash"
        context.bot_data["active_admin_session"] = session

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"Пользователь ответил. Вы можете задать <b>следующий вопрос</b>.\n"
                 f"Если вопросов больше нет, отправьте минус <code>-</code> для перехода к отправке чека.",
            reply_to_message_id=original_admin_message_id,
            parse_mode='HTML'
        )

        # Сбрасываем статус пользователя (до следующего вопроса админа)
        context.user_data["state"] = None
        await update.message.reply_text("Ваш ответ отправлен админу. Ожидайте решения!")
    else:
        await update.message.reply_text("Чтобы предложить идею, напишите команду /start")

# --- Обработчики для администратора ---

async def admin_evaluate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает нажатия админом на кнопки оценки (🟢, 🟡, 🔴)."""
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        await query.message.reply_text("Вы не администратор.")
        return

    parts = query.data.split('_')
    evaluation = parts[1]
    user_id_evaluated = int(parts[2])

    admin_msg_key = f"admin_msg_{query.message.message_id}"
    idea_data = context.bot_data.get(admin_msg_key)

    if not idea_data:
        await query.edit_message_text("Ошибка: Данные этой идеи устарели или не найдены в памяти бота.")
        return

    # Обновляем текст сообщения, фиксируя оценку, убираем кнопки
    new_text = f"{query.message.text}\n\n<b>Оценка автора:</b> {evaluation}"
    await query.edit_message_text(new_text, parse_mode='HTML', reply_markup=None)

    # Создаем или перезаписываем активную сессию админа в глобальной памяти (БОЛЬШЕ НИКАКИХ СБОЕВ!)
    context.bot_data["active_admin_session"] = {
        "state": "awaiting_question_or_dash",
        "target_user_id": user_id_evaluated,
        "evaluation": evaluation,
        "original_admin_message_id": query.message.message_id,
        "username": idea_data["username"]
    }

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"Оценка {evaluation} сохранена.\n\n"
             f"Напишите <b>вопрос</b> для {get_user_mention(user_id_evaluated, idea_data['username'])}.\n"
             f"Если вопросов нет, отправьте обычный минус: <code>-</code>",
        reply_to_message_id=query.message.message_id,
        parse_mode='HTML'
    )


async def admin_handle_question_or_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Управляет вводом вопросов или ссылок от администратора."""
    if update.effective_user.id != ADMIN_ID:
        return

    # Достаем сессию из сверхнадежного глобального хранилища bot_data
    session = context.bot_data.get("active_admin_session")

    if not session:
        await update.message.reply_text("Не могу определить контекст. Пожалуйста, выберите оценку (круг) на сообщении с идеей.")
        return

    current_task = session["state"]
    user_id_target = session["target_user_id"]
    evaluation_result = session["evaluation"]
    original_admin_message_id = session["original_admin_message_id"]
    target_username = session["username"]

    message_text = update.message.text

    if current_task == "awaiting_question_or_dash":
        if is_dash_or_minus(message_text):
            # Админ написал минус -> вопросов больше нет -> переходим к запросу ссылки
            session["state"] = "awaiting_mcoin_link"
            context.bot_data["active_admin_session"] = session

            await update.message.reply_text(
                f"Вопросов нет. Теперь пришлите <b>ссылку на mcoin чек</b> для {get_user_mention(user_id_target, target_username)}.\n"
                f"Если ссылка не требуется (например, для 🔴), пришлите минус <code>-</code>.",
                reply_to_message_id=original_admin_message_id,
                parse_mode='HTML'
            )
        else:
            # Админ написал вопрос -> отправляем его пользователю
            question_text = message_text
            
            # Включаем у пользователя режим ожидания ответа
            target_user_data = context.application.user_data.get(user_id_target)
            if target_user_data is None:
                context.application.user_data[user_id_target] = {}
                target_user_data = context.application.user_data[user_id_target]
            
            target_user_data["state"] = "awaiting_answer"

            # Отправляем вопрос пользователю
            await context.bot.send_message(
                chat_id=user_id_target,
                text=f"❓ <b>Администратор задал вам вопрос по вашей идее:</b>\n\n<i>{question_text}</i>\n\nПожалуйста, напишите ваш ответ сообщением ниже.",
                parse_mode='HTML'
            )

            # Переводим сессию админа в режим ожидания ответа пользователя
            session["state"] = "waiting_for_user"
            context.bot_data["active_admin_session"] = session
            
            await update.message.reply_text(
                f"Вопрос отправлен пользователю {get_user_mention(user_id_target, target_username)}. Ожидаем его ответа.",
                reply_to_message_id=original_admin_message_id,
                parse_mode='HTML'
            )

    elif current_task == "waiting_for_user":
        # Защита от случайного спама админа, пока пользователь думает над ответом
        await update.message.reply_text(
            "Мы всё еще ждем ответ от пользователя. Пожалуйста, дождитесь ответа, прежде чем писать что-то еще.",
            reply_to_message_id=original_admin_message_id
        )

    elif current_task == "awaiting_mcoin_link":
        mcoin_link = message_text.strip()
        mcoin_amount = get_mcoin_amount(evaluation_result)

        if is_dash_or_minus(mcoin_link):
            # Админ отправил минус вместо чека (не платим)
            user_notification_text = (
                f"Ваша идея оценена: <b>{evaluation_result}</b>\n\n"
                f"Оценка работы: {mcoin_amount} мкоин."
            )
            await context.bot.send_message(
                chat_id=user_id_target,
                text=user_notification_text,
                parse_mode='HTML'
            )
            await update.message.reply_text(
                f"Оценка завершена без ссылки. Пользователь уведомлен.",
                reply_to_message_id=original_admin_message_id,
                parse_mode='HTML'
            )
        else:
            # Админ прислал ссылку на чек -> отправляем ее пользователю
            user_notification_text = (
                f"Ваша идея оценена: <b>{evaluation_result}</b>\n\n"
                f"Оценка работы: {mcoin_amount} мкоин.\n"
                f"Получить свои мкоины можно по ссылке: {mcoin_link}"
            )
            await context.bot.send_message(
                chat_id=user_id_target,
                text=user_notification_text,
                parse_mode='HTML'
            )
            await update.message.reply_text(
                f"Оценка и ссылка отправлены пользователю! Процесс успешно завершен.",
                reply_to_message_id=original_admin_message_id,
                parse_mode='HTML'
            )

        # Очищаем сессию (завершаем процесс)
        if "active_admin_session" in context.bot_data:
            del context.bot_data["active_admin_session"]

        # Сбрасываем статус пользователя на всякий случай
        target_user_data = context.application.user_data.get(user_id_target)
        if target_user_data:
            target_user_data["state"] = None


def main() -> None:
    """Запуск бота."""
    application = Application.builder().token(BOT_TOKEN).build()

    # Регистрация команды /start
    application.add_handler(CommandHandler("start", start))

    # Обработчик кнопок оценки для администратора
    application.add_handler(CallbackQueryHandler(admin_evaluate_callback, pattern=r"^evaluate_"))

    # Обработчик текстовых сообщений администратора (вопросы, минусы, ссылки)
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Chat(ADMIN_ID) & ~filters.COMMAND,
        admin_handle_question_or_link
    ))

    # Обработчик текстовых сообщений от обычных пользователей (идеи и ответы на вопросы)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.Chat(ADMIN_ID) & ~filters.COMMAND,
        handle_user_message
    ))

    logger.info("Бот успешно запущен.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
