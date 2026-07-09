mport logging
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

# --- Внутренние состояния для логики администратора ---
ADMIN_STATE_KEY = "admin_current_task"
ADMIN_TASK_AWAITING_QUESTION_OR_DASH = "awaiting_question_or_dash"
ADMIN_TASK_AWAITING_MCOIN_LINK = "awaiting_mcoin_link"

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
        "🟢 Идея понравилась автору+полное описание. Оплата 1кк\n"
        "🟡 Идея привлекла внимание, есть описание. Оплата 100к\n"
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

        # Сохраняем информацию об идее
        context.bot_data[f"idea_temp_{user.id}"] = {
            "user_id": user.id,
            "username": user.username,
            "idea_text": idea_text,
        }

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

        # Связываем сообщение админа с данными пользователя
        context.bot_data[f"admin_msg_link_{admin_message.message_id}"] = {
            "user_id": user.id,
            "username": user.username,
            "admin_chat_id": admin_message.chat_id,
            "admin_message_id": admin_message.message_id,
        }

        # Сбрасываем статус пользователя, чтобы он не спамил идеями без команды /start
        context.user_data["state"] = None
        await update.message.reply_text("Спасибо! Ваша идея отправлена на рассмотрение. Ждите оценки!")

    elif state == "awaiting_answer":
        answer_text = update.message.text
        logger.info(f"User {user.id} answered admin's question.")

        # Получаем контекст вопроса
        admin_question_context_key = f"admin_question_for_{user.id}"
        admin_context = context.bot_data.get(admin_question_context_key)

        if not admin_context:
            await update.message.reply_text("Произошла ошибка (не найден контекст вопроса). Пожалуйста, свяжитесь с админом.")
            context.user_data["state"] = None
            return

        admin_chat_id = admin_context["admin_chat_id"]
        original_admin_message_id = admin_context["original_admin_message_id"]
        evaluation_result = admin_context["evaluation"]

        # Пересылаем ответ админу
        await context.bot.send_message(
            chat_id=admin_chat_id,
            text=f"💬 Ответ от {get_user_mention(user.id, user.username)}:\n\n<b>{answer_text}</b>",
            reply_to_message_id=original_admin_message_id,
            parse_mode='HTML'
        )

        # Переводим админа в режим ожидания ссылки
        context.chat_data[admin_chat_id] = {
            ADMIN_STATE_KEY: ADMIN_TASK_AWAITING_MCOIN_LINK,
            "target_user_id": user.id,
            "evaluation": evaluation_result,
            "original_admin_message_id": original_admin_message_id,
            "username": user.username
        }

        await context.bot.send_message(
            chat_id=admin_chat_id,
            text=f"Пользователь ответил. Теперь пришлите <b>ссылку на mcoin чек</b>.\n"
                 f"Если ссылка не требуется (например, оценка 🔴), отправьте минус <code>-</code>.",
            reply_to_message_id=original_admin_message_id,
            parse_mode='HTML'
        )

        # Сбрасываем статус пользователя и удаляем временный ключ
        context.user_data["state"] = None
        if admin_question_context_key in context.bot_data:
            del context.bot_data[admin_question_context_key]
        
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

    admin_msg_link_key = f"admin_msg_link_{query.message.message_id}"
    idea_data = context.bot_data.get(admin_msg_link_key)

    if not idea_data or idea_data["user_id"] != user_id_evaluated:
        await query.edit_message_text("Ошибка: Данные идеи не найдены.")
        return

    # Обновляем текст сообщения, фиксируя оценку, убираем кнопки
    new_text = f"{query.message.text}\n\n<b>Оценка автора:</b> {evaluation}"
    await query.edit_message_text(new_text, parse_mode='HTML', reply_markup=None)

    # Сохраняем состояние админа: ждем вопрос или пропуск
    context.chat_data[query.from_user.id] = {
        ADMIN_STATE_KEY: ADMIN_TASK_AWAITING_QUESTION_OR_DASH,
        "target_user_id": user_id_evaluated,
        "evaluation": evaluation,
        "original_admin_message_id": query.message.message_id,
        "username": idea_data["username"]
    }

    await context.bot.send_message(
        chat_id=query.from_user.id,
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

    admin_chat_id = update.effective_user.id
    admin_state_data = context.chat_data.get(admin_chat_id)

    if not admin_state_data or ADMIN_STATE_KEY not in admin_state_data:
        await update.message.reply_text("Не могу определить контекст. Выберите оценку на сообщении с идеей.")
        return

    current_task = admin_state_data[ADMIN_STATE_KEY]
    user_id_target = admin_state_data.get("target_user_id")
    evaluation_result = admin_state_data.get("evaluation")
    original_admin_message_id = admin_state_data.get("original_admin_message_id")
    target_username = admin_state_data.get("username")

    message_text = update.message.text

    if current_task == ADMIN_TASK_AWAITING_QUESTION_OR_DASH:
        if is_dash_or_minus(message_text):
            # Вопросов нет -> Переходим к запросу ссылки на mcoin
            context.chat_data[admin_chat_id][ADMIN_STATE_KEY] = ADMIN_TASK_AWAITING_MCOIN_LINK
            await update.message.reply_text(
                f"Вопросов нет. Теперь отправьте <b>ссылку на получение mcoin</b> для пользователя {get_user_mention(user_id_target, target_username)}.\n"
                f"Если ссылка не требуется, отправьте минус <code>-</code>.",
                reply_to_message_id=original_admin_message_id,
                parse_mode='HTML'
            )
        else:
            # Админ задал вопрос
            question_text = message_text
            
            # Переводим целевого пользователя в режим ожидания ответа на вопрос
            target_user_data = context.application.user_data.get(user_id_target)
            if target_user_data is None:
                context.application.user_data[user_id_target] = {}
                target_user_data = context.application.user_data[user_id_target]
            
            target_user_data["state"] = "awaiting_answer"

            # Сохраняем информацию о вопросе для связки при ответе
            context.bot_data[f"admin_question_for_{user_id_target}"] = {
                "admin_chat_id": admin_chat_id,
                "original_admin_message_id": original_admin_message_id,
                "evaluation": evaluation_result
            }

            # Отправляем вопрос пользователю
            await context.bot.send_message(
                chat_id=user_id_target,
                text=f"❓ <b>Администратор задал вам вопрос по вашей идее:</b>\n\n<i>{question_text}</i>\n\nПожалуйста, напишите ваш ответ сообщением ниже.",
                parse_mode='HTML'
            )

            # Очищаем состояние админа, так как теперь мы ждем действий от пользователя
            del context.chat_data[admin_chat_id]
            
            await update.message.reply_text(
                f"Вопрос отправлен пользователю {get_user_mention(user_id_target, target_username)}. Ожидаем его ответа.",
                reply_to_message_id=original_admin_message_id,
                parse_mode='HTML'
            )

    elif current_task == ADMIN_TASK_AWAITING_MCOIN_LINK:
        mcoin_link = message_text.strip()
        mcoin_amount = get_mcoin_amount(evaluation_result)

        if is_dash_or_minus(mcoin_link):
            # Админ решил не прикреплять ссылку (например, при оценке 🔴)
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
                f"Оценка без ссылки успешно отправлена пользователю {get_user_mention(user_id_target, target_username)}.",
                reply_to_message_id=original_admin_message_id,
                parse_mode='HTML'
            )
        else:
            # Админ прислал ссылку. Отправляем пользователю оценку + ссылку
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
                f"Оценка и ссылка успешно отправлены пользователю {get_user_mention(user_id_target, target_username)}.",
                reply_to_message_id=original_admin_message_id,
                parse_mode='HTML'
            )

        # Полностью очищаем временные данные этой сессии
        if admin_chat_id in context.chat_data:
            del context.chat_data[admin_chat_id]
        if f"idea_temp_{user_id_target}" in context.bot_data:
            del context.bot_data[f"idea_temp_{user_id_target}"]
        if f"admin_msg_link_{original_admin_message_id}" in context.bot_data:
            del context.bot_data[f"admin_msg_link_{original_admin_message_id}"]

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

    logger.info("Бот запущен.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
