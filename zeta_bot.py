# -*- coding: utf-8 -*-
"""
Telegram-бот для Zeta — ПРО-ВЕРСИЯ.
Поддерживает: инлайн-кнопки, голос, скриншоты, напоминания, статус устройства, умные уведомления.
"""

import os
import sys
import logging
import io
import tempfile
import re
import asyncio
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, CallbackQueryHandler
)

from core.ai_engine import ask_zeta
from core.memory import save_message, get_history, get_facts, save_fact, get_setting, save_setting
from modules.system_monitor import get_system_status
from core.screen_capture import take_screenshot
from voice.tts import speak
from modules.smart_notifier import start_notifier, stop_notifier, add_notification_callback, get_system_status as get_smart_status

# ========== КОНФИГ ==========
BOT_TOKEN = "8738891191:AAEh-QWNGxNdMV8NvesniBf-4hnYSYK0D04"

MAX_MESSAGE_LENGTH = 4000

# ========== ЛОГИРОВАНИЕ ==========
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Глобальная переменная для application
_application = None


# ========== ОПРЕДЕЛЕНИЕ УСТРОЙСТВА ==========
def detect_device(user_agent: str) -> str:
    """Определяет модель устройства по User-Agent."""
    if not user_agent:
        return "Неизвестно"
    
    user_agent_lower = user_agent.lower()
    
    if "iphone" in user_agent_lower:
        match = re.search(r"iphone(\d+,\d+)", user_agent_lower)
        if match:
            return f"iPhone {match.group(1)}"
        return "iPhone"
    
    if "ipad" in user_agent_lower:
        return "iPad"
    
    if "android" in user_agent_lower:
        match = re.search(r";\s*([^;]+)\s*;", user_agent_lower)
        if match:
            model = match.group(1).strip()
            if "build" in model.lower():
                model = model.split("build")[0].strip()
            return f"Android: {model}"
        return "Android"
    
    if "mac" in user_agent_lower and "iphone" not in user_agent_lower:
        return "Mac"
    
    if "windows" in user_agent_lower:
        return "Windows PC"
    
    if "telegram" in user_agent_lower:
        return "Telegram Desktop"
    
    return "Другое устройство"


# ========== КЛАВИАТУРА ==========
def get_main_keyboard():
    buttons = [
        ["📊 Статус ПК", "📱 Моё устройство", "🧠 Факты"],
        ["🖥️ Скриншот", "📜 История", "🔊 Голос"],
        ["❓ Помощь", "⚙️ Модель", "📤 Экспорт"],
        ["🗑️ Очистить"]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


# ========== ОТПРАВКА УВЕДОМЛЕНИЙ В TELEGRAM ==========
async def send_telegram_notification(title: str, message: str):
    """Отправляет уведомление в Telegram (администраторам)."""
    global _application
    
    if not _application:
        logger.error("Application не инициализирован")
        return
    
    try:
        admin_ids = [5446527720]  # Ваш Telegram ID
        
        for admin_id in admin_ids:
            try:
                await _application.bot.send_message(
                    chat_id=admin_id,
                    text=f"🔔 {title}\n\n{message}",
                    parse_mode="Markdown"
                )
                logger.info(f"Уведомление отправлено {admin_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления {admin_id}: {e}")
    except Exception as e:
        logger.error(f"Ошибка отправки уведомлений: {e}")


def notification_callback(title: str, message: str):
    """Callback для умных уведомлений (вызывается из smart_notifier)."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(send_telegram_notification(title, message))
        loop.close()
    except Exception as e:
        logger.error(f"Ошибка callback: {e}")


# ========== КОМАНДЫ ==========
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_new = context.user_data.get("is_new", True)
    
    if is_new:
        context.user_data["is_new"] = False
        welcome_text = (
            f"👋 Привет, {user.first_name}!\n\n"
            "Я — **Z**, твой персональный ИИ-помощник.\n"
            "Я умею отвечать на вопросы, писать код, делать скриншоты и многое другое.\n\n"
            "📱 Используй кнопки внизу или команды:\n"
            "/start — это сообщение\n"
            "/help — помощь\n"
            "/status — статус ПК\n"
            "/device — моё устройство\n"
            "/screen — скриншот с ПК\n"
            "/history — последние сообщения\n"
            "/fact — факты о тебе\n"
            "/voice — голос на ПК\n"
            "/model — выбрать модель ИИ\n"
            "/export — экспорт чата\n"
            "/clear — очистить историю\n\n"
            "🔔 **Умные уведомления активны!**\n"
            "Я пришлю предупреждение при перегрузке системы.\n\n"
            "💡 Просто напиши мне что-нибудь!"
        )
        await update.message.reply_text(
            welcome_text,
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text(
            "👋 Я здесь! Что нужно?",
            reply_markup=get_main_keyboard()
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 **Помощь по Zeta**\n\n"
        "**Что я умею:**\n"
        "🔹 Отвечать на вопросы\n"
        "🔹 Писать код (Python, JS, C++)\n"
        "🔹 Делать скриншоты с ПК\n"
        "🔹 Искать в интернете\n"
        "🔹 Переводить тексты\n"
        "🔹 Ставить напоминания\n"
        "🔹 Показывать статус системы\n"
        "🔹 Показывать информацию об устройстве\n"
        "🔹 **Умные уведомления** — предупреждаю о перегрузке системы\n\n"
        "**Команды:**\n"
        "/start — приветствие\n"
        "/help — эта справка\n"
        "/status — статус ПК\n"
        "/device — моё устройство\n"
        "/screen — скриншот с ПК\n"
        "/history — история диалога\n"
        "/clear — очистить историю\n"
        "/fact — факты о вас\n"
        "/voice — включить/выключить голос\n"
        "/model — выбрать модель ИИ\n"
        "/export — экспорт чата\n\n"
        "💬 Или просто напиши сообщение!"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статус системы (ПК)."""
    try:
        status = get_system_status()
        await update.message.reply_text(f"📊 {status}")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка: {e}")


async def device_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает информацию об устройстве пользователя."""
    user = update.effective_user
    message = update.message
    
    # Безопасное получение user_agent
    user_agent = ""
    try:
        if hasattr(message.from_user, 'user_agent'):
            user_agent = message.from_user.user_agent or ""
    except:
        pass
    
    platform = ""
    try:
        if hasattr(message.from_user, 'platform'):
            platform = message.from_user.platform or "Неизвестно"
    except:
        platform = "Неизвестно"
    
    device_model = detect_device(user_agent)
    
    device_info = f"""
📱 **Информация об устройстве**

👤 **Пользователь:** {user.full_name}
🆔 **ID:** `{user.id}`
🌐 **Язык:** {user.language_code or 'Неизвестно'}

📱 **Устройство:**
• **Модель:** {device_model}
• **Платформа:** {platform}

📶 **Тип чата:** {message.chat.type}
🔄 **Дата:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """.strip()
    
    await update.message.reply_text(device_info, parse_mode="Markdown")


async def screen_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Делает скриншот и отправляет в Telegram."""
    await update.message.reply_text("📸 Делаю скриншот...")
    try:
        screenshot = take_screenshot()
        if not screenshot:
            await update.message.reply_text("⚠️ Не удалось сделать скриншот.")
            return
        import base64
        image_data = base64.b64decode(screenshot)
        await update.message.reply_photo(
            photo=io.BytesIO(image_data),
            caption="🖥️ Скриншот экрана"
        )
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка: {e}")


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        history = get_history(limit=10)
        if not history:
            await update.message.reply_text("📭 История пуста.")
            return
        text = "📜 **Последние сообщения:**\n\n"
        for msg in history[-5:]:
            role = "👤 Вы" if msg["role"] == "user" else "🤖 Z"
            content = msg["content"][:200]
            if len(msg["content"]) > 200:
                content += "..."
            text += f"{role}: {content}\n"
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка: {e}")


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from core.memory import clear_history
    clear_history()
    await update.message.reply_text("🗑️ История чата очищена.")


async def fact_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    facts = get_facts()
    if not facts:
        await update.message.reply_text("🧠 У меня пока нет фактов о вас. Расскажите что-нибудь о себе!")
        return
    text = "🧠 **Что я знаю о вас:**\n\n"
    for fact in facts:
        text += f"• {fact['key']}: {fact['content']}\n"
    await update.message.reply_text(text, parse_mode="Markdown")


async def voice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current = get_setting("voice_enabled", "true") == "true"
    new_value = not current
    save_setting("voice_enabled", "true" if new_value else "false")
    status = "включён ✅" if new_value else "выключен ❌"
    await update.message.reply_text(f"🔊 Голос на ПК {status}.")


async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🧠 qwen2.5:7b", callback_data="model_qwen2.5:7b")],
        [InlineKeyboardButton("🧠 mistral", callback_data="model_mistral:latest")],
        [InlineKeyboardButton("🧠 llama3.2:3b", callback_data="model_llama3.2:3b")],
        [InlineKeyboardButton("🧠 phi3:mini", callback_data="model_phi3:mini")],
        [InlineKeyboardButton("🧠 gemma:2b", callback_data="model_gemma:2b")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    current_model = get_setting("ai_model", "qwen2.5:7b")
    await update.message.reply_text(
        f"🧠 **Выберите модель ИИ:**\n\nТекущая: `{current_model}`",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )


async def model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    model = query.data.replace("model_", "")
    save_setting("ai_model", model)
    await query.edit_message_text(
        f"✅ Модель изменена на: `{model}`\n\nПерезапустите Zeta на ПК.",
        parse_mode="Markdown"
    )


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        history = get_history(limit=50)
        if not history:
            await update.message.reply_text("📭 История пуста.")
            return
        text = f"📜 Экспорт чата Zeta\nДата: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n{'='*40}\n\n"
        for msg in history:
            role = "Вы" if msg["role"] == "user" else "Z"
            text += f"{role}: {msg['content']}\n\n"
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8") as f:
            f.write(text)
            path = f.name
        await update.message.reply_document(
            document=open(path, "rb"),
            filename=f"zeta_chat_{datetime.now().strftime('%Y%m%d')}.txt",
            caption="📄 Экспорт чата"
        )
        os.unlink(path)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка: {e}")


# ========== ОБРАБОТКА СООБЩЕНИЙ ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    logger.info(f"Сообщение от {user_name} ({user_id}): {user_message[:50]}...")
    
    # Обработка кнопок
    if user_message == "📊 Статус ПК":
        await status_command(update, context)
        return
    elif user_message == "📱 Моё устройство":
        await device_command(update, context)
        return
    elif user_message == "🧠 Факты":
        await fact_command(update, context)
        return
    elif user_message == "📜 История":
        await history_command(update, context)
        return
    elif user_message == "🖥️ Скриншот":
        await screen_command(update, context)
        return
    elif user_message == "🔊 Голос":
        await voice_command(update, context)
        return
    elif user_message == "🗑️ Очистить":
        await clear_command(update, context)
        return
    elif user_message == "❓ Помощь":
        await help_command(update, context)
        return
    elif user_message == "⚙️ Модель":
        await model_command(update, context)
        return
    elif user_message == "📤 Экспорт":
        await export_command(update, context)
        return
    
    # === ЭФФЕКТ "ДУМАЕТ" ===
    await update.message.chat.send_action(action="typing")
    thinking_msg = await update.message.reply_text("🤔 **Zeta думает...**", parse_mode="Markdown")
    
    try:
        full_answer = ""
        for chunk in ask_zeta(user_message):
            full_answer += chunk
        
        await thinking_msg.delete()
        
        if len(full_answer) > MAX_MESSAGE_LENGTH:
            parts = [full_answer[i:i+MAX_MESSAGE_LENGTH] for i in range(0, len(full_answer), MAX_MESSAGE_LENGTH)]
            for part in parts:
                await update.message.reply_text(part)
        else:
            await update.message.reply_text(full_answer)
            
    except Exception as e:
        await thinking_msg.delete()
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"⚠️ Произошла ошибка: {str(e)}")


# ========== ЗАПУСК ==========
def run_bot():
    global _application
    
    print("🤖 Запуск Telegram-бота Zeta (PRO + умные уведомления)...")
    
    _application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем команды
    _application.add_handler(CommandHandler("start", start_command))
    _application.add_handler(CommandHandler("help", help_command))
    _application.add_handler(CommandHandler("status", status_command))
    _application.add_handler(CommandHandler("device", device_command))
    _application.add_handler(CommandHandler("screen", screen_command))
    _application.add_handler(CommandHandler("history", history_command))
    _application.add_handler(CommandHandler("clear", clear_command))
    _application.add_handler(CommandHandler("fact", fact_command))
    _application.add_handler(CommandHandler("voice", voice_command))
    _application.add_handler(CommandHandler("model", model_command))
    _application.add_handler(CommandHandler("export", export_command))
    
    _application.add_handler(CallbackQueryHandler(model_callback, pattern="^model_"))
    _application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # === ЗАПУСКАЕМ УМНЫЕ УВЕДОМЛЕНИЯ ===
    add_notification_callback(notification_callback)
    start_notifier()
    print("🔔 Умные уведомления активны!")
    
    print("✅ Бот запущен! Найдите своего бота в Telegram и напишите /start")
    
    _application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    run_bot()