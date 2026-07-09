import logging
import os
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# Загружаем переменные окружения из .env файла
load_dotenv()

# --- Конфигурация ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))  # Ваш Telegram User ID администратора (число)
# MCOIN_CHECK_BASE_URL удален, так как админ сам вводит полную ссылку.

# Включаем логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Состояния для ConversationHandler пользователя ---
IDEA_SUBMISSION = 0
WAITING_FOR_ANSWER = 1

# --- Внутренние состояния для логики администратора (хранятся в context.chat_data) ---
# ADMIN_WAITING_FOR_QUESTION_OR_LINK: Админ ожидает вопрос или "-"
# ADMIN_WAITING_FOR_MCOIN_LINK: Админ ожидает ссылку на mcoin
ADMIN_STATE_KEY = "admin_current_task"
ADMIN_TASK_AWAITING_QUESTION_OR_DASH = "awaiting_question_or_dash"
ADMIN_TASK_AWAITING_MCOIN_LINK = "awaiting_mcoin_link"

# --- Вспомогательные функции ---
def get_user_mention(user_id, username):
    """Возвращает HTML-ссылку для упоминания пользователя."""
    if username:
        # Используем html.escape для безопасности, если имя пользователя содержит спецсимволы,
        # хотя для mention_html обычно это не требуется, но хорошая практика.
        return f"<a href='tg://user?id={user_id}'>{username}</a>"
    return f"<a href='tg://user?id={user_id}'>User {user_id}</a>"

def get_mcoin_amount(evaluation_type):
    """Возвращает количество мкоинов в зависимости от типа оценки."""
    if evaluation_type == "🟢":
        return "1,000,000" # 1kk
    elif evaluation_type == "🟡":
        return "100,000"
    elif evaluation_type == "🔴":
        return "5,000"
    return "0" # Не должно произойти

# --- Обработчики для пользователя ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды /start. Отправляет приветственное сообщение."""
    user = update.effective_user
    logger.info(f"User {user.id} ({user.username}) started the bot.")

    welcome_message = (
        f"Привет {user.mention_html()}!\n\n"
        "Здесь ты получаешь мкоин за описание своей идеи для бота.\n\n"
        "<b>Оценивание работы</b>\n"
        "🟢 Идея понравилась автору+полное описание. Оплата 1кк\n"
        "🟡 Идея привлекла внимание, есть описание. Оплата 100к\n"
        "🔴 Идея не понравилась, но спасибо. Оплата: 5к\n\n"
        "Пиши ниже свою идею и попробуй получить 1кк!"
    )
    await update.message.reply_html(welcome_message)

    return IDEA_SUBMISSION

async def receive_idea(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Принимает идею пользователя и пересылает ее администратору."""
    user = update.effective_user
    idea_text = update.message.text
    logger.info(f"User {user.id} ({user.username}) submitted an idea.")

    # Сохраняем детали пользователя и идею для последующего использования администратором
    # `context.bot_data` сохраняется между перезапусками бота, если бот запущен с помощью `Updater` и не `run_polling` в prod.
    # В данном случае, это временное хранилище для текущей сессии.
    context.bot_data[f"idea_temp_{user.id}"] = {
        "user_id": user.id,
        "username": user.username,
        "idea_text": idea_text,
    }

    # Создаем кнопки для оценки администратором
    keyboard = [
        [
            InlineKeyboardButton("🟢", callback_data=f"evaluate_🟢_{user.id}"),
            InlineKeyboardButton("🟡", callback_data=f"evaluate_🟡_{user.id}"),
            InlineKeyboardButton("🔴", callback_data=f"evaluate_🔴_{user.id}"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Отправляем идею администратору
    admin_message_text = (
        f"Новая идея от пользователя {get_user_mention(user.id, user.username)} (ID: <code>{user.id}</code>):\n\n"
        f"<b>Идея:</b>\n{idea_text}"
    )
    admin_message = await context.bot.send_message(
        chat_id=ADMIN_ID, text=admin_message_text, reply_markup=reply_markup, parse_mode='HTML'
    )

    # Связываем ID сообщения администратора с деталями идеи пользователя для обратного вызова
    context.bot_data[f"admin_msg_link_{admin_message.message_id}"] = {
        "user_id": user.id,
        "username": user.username,
        "admin_chat_id": admin_message.chat_id,
        "admin_message_id": admin_message.message_id,
        "idea_text": idea_text # Сохраняем идею здесь тоже, для полной независимости.
    }

    await update.message.reply_text(
        "Спасибо! Ваша идея отправлена на рассмотрение. Ждите оценки!"
    )

    return ConversationHandler.END # Завершаем диалог пользователя до ответа админа

async def receive_user_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Принимает ответ пользователя на вопрос администратора и пересылает его админу."""
    user = update.effective_user
    answer_text = update.message.text
    logger.info(f"User {user.id} ({user.username}) sent an answer to admin.")

    # Извлекаем контекст вопроса администратора для этого пользователя
    admin_question_context_key = f"admin_question_for_{user.id}"
    admin_context = context.bot_data.get(admin_question_context_key)

    if not admin_context:
        logger.warning(f"No admin context found for user {user.id} to receive answer.")
        await update.message.reply_text(
            "Что-то пошло не так, не удалось найти связанный вопрос. "
            "Пожалуйста, сообщите администратору."
        )
        return WAITING_FOR_ANSWER # Остаемся в состоянии или завершаем? Пусть пользователь попробует еще раз или админ вручную продолжит.

    admin_chat_id = admin_context["admin_chat_id"]
    original_admin_message_id = admin_context["original_admin_message_id"]
    evaluation_result = admin_context["evaluation"]

    await context.bot.send_message(
        chat_id=admin_chat_id,
        text=f"Ответ от пользователя {get_user_mention(user.id, user.username)} (ID: <code>{user.id}</code>) на ваш вопрос:\n\n<b>{answer_text}</b>",
        reply_to_message_id=original_admin_message_id,
        parse_mode='HTML'
    )

    # Теперь администратору нужно решить: задать еще вопрос или отправить ссылку
    # Переводим администратора обратно в состояние ожидания действий для этого пользователя.
    context.chat_data[admin_chat_id] = {
        ADMIN_STATE_KEY: ADMIN_TASK_AWAITING_MCOIN_LINK, # После ответа пользователя админ должен прислать ссылку
        "target_user_id": user.id,
        "evaluation": evaluation_result, # Сохраняем результат оценки
        "original_admin_message_id": original_admin_message_id, # Сохраняем ID сообщения, к которому админ будет отвечать
        "username": user.username # Сохраняем username для удобства
    }

    await context.bot.send_message(
        chat_id=admin_chat_id,
        text=f"Пользователь {get_user_mention(user.id, user.username)} ответил. "
             f"Теперь введите <b>ссылку на получение mcoin</b> для пользователя "
             f"или '—' если не нужно отправлять ссылку (например, при оценке 🔴).",
        reply_to_message_id=original_admin_message_id,
        parse_mode='HTML'
    )
    
    # Очищаем временный контекст вопроса администратора
    if admin_question_context_key in context.bot_data:
        del context.bot_data[admin_question_context_key]

    await update.message.reply_text("Ваш ответ отправлен админу. Ждите дальнейших инструкций.")

    return ConversationHandler.END # Завершаем диалог пользователя по ответам

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды /cancel. Отменяет текущий диалог."""
    await update.message.reply_text("Действие отменено.")
    return ConversationHandler.END

# --- Обработчики для администратора ---

async def admin_evaluate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает нажатия кнопок оценки администратором (🟢, 🟡, 🔴)."""
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        await query.message.reply_text("Вы не являетесь администратором.")
        return

    # Формат callback_data: "evaluate_🟢_USER_ID"
    parts = query.data.split('_')
    evaluation = parts[1]
    user_id_evaluated = int(parts[2])

    logger.info(f"Admin {query.from_user.id} evaluated idea for user {user_id_evaluated} as {evaluation}.")

    # Извлекаем данные идеи, используя ID сообщения администратора
    admin_msg_link_key = f"admin_msg_link_{query.message.message_id}"
    idea_data = context.bot_data.get(admin_msg_link_key)

    if not idea_data or idea_data["user_id"] != user_id_evaluated:
        logger.error(f"Failed to retrieve idea data for admin msg {query.message.message_id} and user {user_id_evaluated}")
        await query.edit_message_text("Ошибка: Не удалось найти данные идеи.")
        return

    # Обновляем сообщение администратора, чтобы показать оценку
    new_text = f"{query.message.text}\n\n<b>Оценка:</b> {evaluation}"
    # Удаляем кнопки после оценки
    await query.edit_message_text(new_text, parse_mode='HTML', reply_markup=None)

    # Сохраняем временное состояние администратора для следующего шага
    context.chat_data[query.from_user.id] = {
        ADMIN_STATE_KEY: ADMIN_TASK_AWAITING_QUESTION_OR_DASH,
        "target_user_id": user_id_evaluated,
        "evaluation": evaluation,
        "original_admin_message_id": query.message.message_id, # Сохраняем ID сообщения для ответов
        "username": idea_data["username"]
    }

    await context.bot.send_message(
        chat_id=query.from_user.id,
        text=f"Оценка <b>{evaluation}</b> установлена. "
             f"Введите <b>вопрос для пользователя</b> {get_user_mention(user_id_evaluated, idea_data['username'])} "
             f"или '—' если вопросов нет.",
        reply_to_message_id=query.message.message_id,
        parse_mode='HTML'
    )

async def admin_handle_question_or_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает последующие вопросы администратора или отправку ссылки на mcoin."""
    if update.effective_user.id != ADMIN_ID:
        return

    admin_chat_id = update.effective_user.id
    admin_state_data = context.chat_data.get(admin_chat_id)

    if not admin_state_data or ADMIN_STATE_KEY not in admin_state_data:
        await update.message.reply_text(
            "Не могу определить контекст. Пожалуйста, начните заново или выберите оценку для идеи.",
            reply_to_message_id=update.message.message_id
        )
        return

    current_task = admin_state_data[ADMIN_STATE_KEY]
    user_id_target = admin_state_data.get("target_user_id")
    evaluation_result = admin_state_data.get("evaluation")
    original_admin_message_id = admin_state_data.get("original_admin_message_id")
    target_username = admin_state_data.get("username", f"User {user_id_target}")

    if not user_id_target or not evaluation_result:
        await update.message.reply_text(
            "Ошибка контекста. Отсутствуют данные пользователя или оценки. Пожалуйста, начните заново.",
            reply_to_message_id=update.message.message_id
        )
        del context.chat_data[admin_chat_id]
        return

    message_text = update.message.text

    if current_task == ADMIN_TASK_AWAITING_QUESTION_OR_DASH:
        if message_text == "—":
            # Вопросов нет, переходим к запросу ссылки на mcoin
            context.chat_data[admin_chat_id][ADMIN_STATE_KEY] = ADMIN_TASK_AWAITING_MCOIN_LINK
            await update.message.reply_text(
                f"Вопросов нет. Теперь введите <b>ссылку на получение mcoin</b> для пользователя {get_user_mention(user_id_target, target_username)}.",
                reply_to_message_id=original_admin_message_id,
                parse_mode='HTML'
            )
        else:
            # Админ задал вопрос
            question_text = message_text
            await context.bot.send_message(
                chat_id=user_id_target,
                text=f"Админ задал вам вопрос по вашей идее:\n\n<i>{question_text}</i>\n\nПожалуйста, напишите свой ответ ниже.",
                parse_mode='HTML'
            )
            # Сохраняем контекст вопроса для пользователя, чтобы он знал, куда отвечать
            context.bot_data[f"admin_question_for_{user_id_target}"] = {
                "admin_chat_id": admin_chat_id,
                "original_admin_message_id": original_admin_message_id,
                "evaluation": evaluation_result
            }
            # Удаляем состояние админа из context.chat_data, пока пользователь не ответит.
            # Админ не может действовать дальше по этой идее, пока не получит ответ.
            del context.chat_data[admin_chat_id]
            await update.message.reply_text(
                f"Ваш вопрос отправлен пользователю {get_user_mention(user_id_target, target_username)}. Я уведомлю вас, когда он ответит.",
                reply_to_message_id=original_admin_message_id,
                parse_mode='HTML'
            )

    elif current_task == ADMIN_TASK_AWAITING_MCOIN_LINK:
        mcoin_link = message_text
        if mcoin_link == "—":
            # Админ решил не отправлять ссылку
            await update.message.reply_text(
                f"Ссылка не отправлена. Оценка для пользователя {get_user_mention(user_id_target, target_username)} завершена.",
                reply_to_message_id=original_admin_message_id,
                parse_mode='HTML'
            )
        else:
            # Отправляем окончательную оценку и ссылку пользователю
            mcoin_amount = get_mcoin_amount(evaluation_result)
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
                f"Оценка и ссылка отправлены пользователю {get_user_mention(user_id_target, target_username)}. Работа завершена.",
                reply_to_message_id=original_admin_message_id,
                parse_mode='HTML'
            )

        # Очищаем состояние администратора
        if admin_chat_id in context.chat_data:
            del context.chat_data[admin_chat_id]
        
        # Очищаем связанные данные идеи, если они больше не нужны
        if f"idea_temp_{user_id_target}" in context.bot_data:
            del context.bot_data[f"idea_temp_{user_id_target}"]
        if f"admin_msg_link_{original_admin_message_id}" in context.bot_data:
            del context.bot_data[f"admin_msg_link_{original_admin_message_id}"]
    else:
        await update.message.reply_text("Неизвестное состояние администратора. Пожалуйста, проверьте контекст.")

def main() -> None:
    """Запускает бота."""
    application = Application.builder().token(BOT_TOKEN).build()

    # Обработчик диалога пользователя для подачи идеи и ответов на вопросы
    user_conversation_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            IDEA_SUBMISSION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_idea)],
            WAITING_FOR_ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_user_answer)],
        },
        fallbacks=[CommandHandler("cancel", cancel)], # Можно добавить обработчик /cancel
    )

    application.add_handler(user_conversation_handler)

    # Обработчики для администратора
    # Обработчик callback-кнопок для оценки идеи
    application.add_handler(CallbackQueryHandler(admin_evaluate_callback, pattern=r"^evaluate_"))
    
    # Обработчик текстовых сообщений от администратора (вопросы или ссылки)
    # Фильтруем по ID администратора и тексту (не команды)
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Chat(ADMIN_ID) & ~filters.COMMAND,
        admin_handle_question_or_link
    ))

    # Запускаем бота в режиме опроса (polling)
    logger.info("Бот начал опрос.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
