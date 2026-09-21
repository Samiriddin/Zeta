# -*- coding: utf-8 -*-
"""
Публичный Telegram-бот Zeta.
Не связан с ПК пользователя. Работает как ChatGPT.
Поддерживает: выбор языка, анализ изображений, голосовые сообщения.

ИСПРАВЛЕНО (2026-09-21):
    - Токен из .env (python-dotenv)
    - Обновлены модели: zeta-universal, llava:13b
    - ask_zeta_sync вместо дублирующего ask_llm
    - init_db() вызывается в run_bot, а не при импорте
    - ask_zeta_sync в asyncio.to_thread
    - Кэш IP-инфо на 5 минут
    - handle_voice — одно сообщение
    - except Exception вместо голого except
    - parse_mode: хелпер с fallback
"""

import os
import sys
import logging
import base64
import sqlite3
import re
import tempfile
import time
from datetime import datetime
from typing import Optional, Dict, Any, List

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# === ЗАГРУЗКА .env ===
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    print("⚠️ python-dotenv не установлен: pip install python-dotenv")

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, CallbackQueryHandler,
)

# === ЕДИНАЯ ЛОГИКА ИИ (вместо своего ask_llm) ===
from core.ai_engine import ask_zeta_sync


# ========== КОНФИГ ИЗ .env ==========

PUBLIC_BOT_TOKEN = os.getenv("ZETA_PUBLIC_BOT_TOKEN", "").strip()

if not PUBLIC_BOT_TOKEN:
    raise RuntimeError(
        "❌ ZETA_PUBLIC_BOT_TOKEN не найден!\n"
        "Создай файл D:\\Zeta\\.env со строкой:\n"
        "   ZETA_PUBLIC_BOT_TOKEN=твой_токен_сюда\n"
        "Токен получи у @BotFather (и СМЕНИ старый!)."
    )

# Ollama
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_CHAT = "zeta-universal"      # ИСПРАВЛЕНО
MODEL_VISION = "llava:13b"         # ИСПРАВЛЕНО

MAX_MESSAGE_LENGTH = 4000

# Кэш IP-инфо (5 минут)
_IP_CACHE_TTL = 300
_ip_cache: Dict[str, Any] = {"data": None, "time": 0}


# ========== ЛОГИРОВАНИЕ ==========

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ========== ХЕЛПЕР parse_mode ==========

async def safe_reply(message, text: str, **kwargs):
    """
    ИСПРАВЛЕНО: пытается Markdown, при ошибке — plain text.
    """
    try:
        return await message.reply_text(text, parse_mode="Markdown", **kwargs)
    except Exception:
        # Markdown упал — пробуем без него
        return await message.reply_text(text, **kwargs)


# ========== ЯЗЫКИ ==========

LANGUAGES: Dict[str, Dict[str, str]] = {
    "ru": {
        "name": "Русский",
        "start": "👋 Привет, {name}!\n\nЯ — **Z Public**, твой ИИ-помощник.\nЯ отвечаю на вопросы, помогаю с кодом и анализирую изображения.\n\n📋 Команды:\n/start — приветствие\n/help — помощь\n/language — выбрать язык\n/fact — факты о тебе\n/history — история\n/clear — очистить\n\n💡 Просто напиши мне что-нибудь!",
        "help": "📖 **Помощь**\n\nЯ умею:\n💬 Отвечать на вопросы\n🖼️ Анализировать изображения\n🧠 Запоминать факты\n📜 Помнить историю\n🌍 Понимать русский, английский, узбекский\n\nКоманды:\n/start — приветствие\n/help — помощь\n/language — выбрать язык\n/fact — факты\n/history — история\n/clear — очистить",
        "thinking": "🤔 **Zeta думает...**",
        "fact_empty": "🧠 У меня пока нет фактов о тебе. Расскажи что-нибудь о себе!",
        "fact_title": "🧠 **Что я знаю о тебе:**",
        "history_title": "📜 **Последние сообщения:**",
        "history_empty": "📭 История пуста.",
        "cleared": "🗑️ История чата очищена.",
        "error": "⚠️ Произошла ошибка: {e}",
        "image_analyzing": "🖼️ Анализирую изображение...",
        "image_error": "⚠️ Не удалось проанализировать изображение.",
        "lang_changed": "🌍 Язык изменён на: **Русский**",
        "voice_processing": "🎤 Голосовые сообщения пока в разработке. Напиши текстом!",
        "lang_select": "🌍 **Выбери язык:**",
        "device_title": "📱 **Информация об устройстве**",
        "ip_title": "🌐 **Информация о подключении**",
        "no_ip": "⚠️ Не удалось получить информацию о подключении.",
        "loading": "⏳ Загрузка...",
        "done": "✅ Готово!",
    },
    "en": {
        "name": "English",
        "start": "👋 Hi, {name}!\n\nI'm **Z Public**, your AI assistant.\nI answer questions, help with code, and analyze images.\n\n📋 Commands:\n/start — welcome\n/help — help\n/language — select language\n/fact — facts about you\n/history — history\n/clear — clear\n\n💡 Just write me something!",
        "help": "📖 **Help**\n\nI can:\n💬 Answer questions\n🖼️ Analyze images\n🧠 Remember facts\n📜 Keep history\n🌍 Understand Russian, English, Uzbek\n\nCommands:\n/start — welcome\n/help — help\n/language — select language\n/fact — facts\n/history — history\n/clear — clear",
        "thinking": "🤔 **Zeta is thinking...**",
        "fact_empty": "🧠 I don't have any facts about you yet. Tell me something about yourself!",
        "fact_title": "🧠 **What I know about you:**",
        "history_title": "📜 **Last messages:**",
        "history_empty": "📭 History is empty.",
        "cleared": "🗑️ Chat history cleared.",
        "error": "⚠️ An error occurred: {e}",
        "image_analyzing": "🖼️ Analyzing image...",
        "image_error": "⚠️ Could not analyze image.",
        "lang_changed": "🌍 Language changed to: **English**",
        "voice_processing": "🎤 Voice messages are in development. Write text!",
        "lang_select": "🌍 **Select language:**",
        "device_title": "📱 **Device Information**",
        "ip_title": "🌐 **Connection Information**",
        "no_ip": "⚠️ Could not get connection information.",
        "loading": "⏳ Loading...",
        "done": "✅ Done!",
    },
    "uz": {
        "name": "O'zbekcha",
        "start": "👋 Salom, {name}!\n\nMen **Z Public**, sizning AI yordamchingiz.\nMen savollarga javob beraman, kod yozishda yordam beraman va rasmlarni tahlil qilaman.\n\n📋 Buyruqlar:\n/start — salomlashish\n/help — yordam\n/language — tilni tanlash\n/fact — siz haqingizdagi faktlar\n/history — tarix\n/clear — tozalash\n\n💡 Menga biror narsa yozing!",
        "help": "📖 **Yordam**\n\nMen qila olaman:\n💬 Savollarga javob berish\n🖼️ Rasmlarni tahlil qilish\n🧠 Faktlarni eslab qolish\n📜 Tarixni saqlash\n🌍 Rus, Ingliz, O'zbek tillarini tushunish\n\nBuyruqlar:\n/start — salomlashish\n/help — yordam\n/language — tilni tanlash\n/fact — faktlar\n/history — tarix\n/clear — tozalash",
        "thinking": "🤔 **Zeta o'ylayapti...**",
        "fact_empty": "🧠 Siz haqingizda hali faktlar yo'q. O'zingiz haqingizda biror narsa ayting!",
        "fact_title": "🧠 **Siz haqingizda bilganlarim:**",
        "history_title": "📜 **Oxirgi xabarlar:**",
        "history_empty": "📭 Tarix bo'sh.",
        "cleared": "🗑️ Chat tarixi tozalandi.",
        "error": "⚠️ Xatolik yuz berdi: {e}",
        "image_analyzing": "🖼️ Rasmni tahlil qilmoqdaman...",
        "image_error": "⚠️ Rasmni tahlil qilib bo'lmadi.",
        "lang_changed": "🌍 Til o'zgartirildi: **O'zbekcha**",
        "voice_processing": "🎤 Ovozli xabarlar ishlab chiqilmoqda. Matn yozing!",
        "lang_select": "🌍 **Tilni tanlang:**",
        "device_title": "📱 **Qurilma haqida ma'lumot**",
        "ip_title": "🌐 **Ulanish haqida ma'lumot**",
        "no_ip": "⚠️ Ulanish haqida ma'lumot olib bo'lmadi.",
        "loading": "⏳ Yuklanmoqda...",
        "done": "✅ Tayyor!",
    },
}


# ========== БАЗА ДАННЫХ ==========

DB_PATH = "data/public_bot.db"
_db_initialized = False


def init_db():
    """ИСПРАВЛЕНО: идемпотентная инициализация."""
    global _db_initialized
    if _db_initialized:
        return

    os.makedirs("data", exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                role TEXT,
                content TEXT,
                timestamp TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                key TEXT,
                content TEXT,
                timestamp TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                user_id INTEGER PRIMARY KEY,
                language TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pub_msg_user ON messages(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pub_fact_user ON facts(user_id)")

    _db_initialized = True


def save_message(user_id: int, role: str, content: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO messages (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (user_id, role, content, datetime.now().isoformat()),
        )


def get_history(user_id: int, limit: int = 10) -> List[Dict[str, str]]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


def get_facts(user_id: int) -> List[Dict[str, str]]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT key, content FROM facts WHERE user_id = ?", (user_id,)
        ).fetchall()
    return [{"key": r[0], "content": r[1]} for r in rows]


def save_fact(user_id: int, key: str, content: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO facts (user_id, key, content, timestamp) VALUES (?, ?, ?, ?)",
            (user_id, key, content, datetime.now().isoformat()),
        )


def clear_history(user_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))


def get_language(user_id: int) -> str:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT language FROM settings WHERE user_id = ?", (user_id,)
        ).fetchone()
    return row[0] if row else "ru"


def set_language(user_id: int, lang: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (user_id, language) VALUES (?, ?)",
            (user_id, lang),
        )


# ========== ОПРЕДЕЛЕНИЕ УСТРОЙСТВА ==========

def detect_device(user_agent: str) -> str:
    if not user_agent:
        return "Неизвестно"
    ua = user_agent.lower()
    if "iphone" in ua:
        return "iPhone"
    if "ipad" in ua:
        return "iPad"
    if "android" in ua:
        return "Android"
    if "mac" in ua:
        return "Mac"
    if "windows" in ua:
        return "Windows PC"
    if "telegram" in ua:
        return "Telegram Desktop"
    return "Другое устройство"


def get_ip_info() -> dict:
    """
    ИСПРАВЛЕНО: кэш на 5 минут, чтобы не дёргать ip-api.com каждый раз.
    """
    now = time.time()

    # Кэш
    if _ip_cache["data"] is not None and now - _ip_cache["time"] < _IP_CACHE_TTL:
        return _ip_cache["data"]

    fallback = {
        "ip": "Неизвестно",
        "country": "Неизвестно",
        "city": "Неизвестно",
        "isp": "Неизвестно",
        "org": "Неизвестно",
        "region": "Неизвестно",
        "timezone": "Неизвестно",
        "lat": 0,
        "lon": 0,
    }

    try:
        response = requests.get("http://ip-api.com/json/", timeout=5)
        data = response.json()
        if data.get("status") == "success":
            result = {
                "ip": data.get("query", "Неизвестно"),
                "country": data.get("country", "Неизвестно"),
                "city": data.get("city", "Неизвестно"),
                "isp": data.get("isp", "Неизвестно"),
                "org": data.get("org", "Неизвестно"),
                "region": data.get("regionName", "Неизвестно"),
                "timezone": data.get("timezone", "Неизвестно"),
                "lat": data.get("lat", 0),
                "lon": data.get("lon", 0),
            }
            _ip_cache["data"] = result
            _ip_cache["time"] = now
            return result
    except Exception as e:
        logger.warning(f"IP-api ошибка: {e}")

    _ip_cache["data"] = fallback
    _ip_cache["time"] = now
    return fallback


# ========== АНАЛИЗ ИЗОБРАЖЕНИЙ ==========

def analyze_image(image_data: bytes) -> str:
    """Анализирует изображение через LLaVA."""
    try:
        img_base64 = base64.b64encode(image_data).decode("utf-8")
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL_VISION,
                "prompt": "Опиши кратко что видишь на изображении. Только на русском языке.",
                "images": [img_base64],
                "stream": False,
            },
            timeout=120,
        )
        answer = response.json().get("response", "").strip()
        return answer if answer else "Не удалось распознать изображение."
    except requests.exceptions.Timeout:
        return "⚠️ Модель зрения думает слишком долго."
    except Exception as e:
        return f"⚠️ Ошибка анализа: {str(e)}"


# ========== КЛАВИАТУРА ==========

def get_main_keyboard(lang: str = "ru"):
    texts = {
        "ru": ["💬 Чат", "🖼️ Анализ фото", "📱 Устройство", "🧠 Факты", "📜 История", "🗑️ Очистить", "❓ Помощь", "🌍 Язык"],
        "en": ["💬 Chat", "🖼️ Analyze Photo", "📱 Device", "🧠 Facts", "📜 History", "🗑️ Clear", "❓ Help", "🌍 Language"],
        "uz": ["💬 Chat", "🖼️ Rasm tahlil", "📱 Qurilma", "🧠 Faktlar", "📜 Tarix", "🗑️ Tozalash", "❓ Yordam", "🌍 Til"],
    }
    buttons = texts.get(lang, texts["ru"])
    return ReplyKeyboardMarkup(
        [
            [buttons[0], buttons[1], buttons[2]],
            [buttons[3], buttons[4], buttons[5]],
            [buttons[6], buttons[7]],
        ],
        resize_keyboard=True,
    )


# ========== КОМАНДЫ ==========

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = get_language(user.id)
    texts = LANGUAGES.get(lang, LANGUAGES["ru"])
    await safe_reply(
        update.message,
        texts["start"].format(name=user.first_name),
        reply_markup=get_main_keyboard(lang),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_language(user_id)
    texts = LANGUAGES.get(lang, LANGUAGES["ru"])
    await safe_reply(update.message, texts["help"])


async def device_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    lang = get_language(user_id)
    texts = LANGUAGES.get(lang, LANGUAGES["ru"])

    user_agent = ""
    try:
        if hasattr(update.message.from_user, "user_agent"):
            user_agent = update.message.from_user.user_agent or ""
    except Exception:
        pass

    platform = "Неизвестно"
    try:
        if hasattr(update.message.from_user, "platform"):
            platform = update.message.from_user.platform or "Неизвестно"
    except Exception:
        pass

    device_model = detect_device(user_agent)

    device_info = f"""
{texts['device_title']}

👤 **Пользователь:** {user.full_name}
🆔 **ID:** `{user.id}`
🌐 **Язык:** {user.language_code or 'Неизвестно'}

📱 **Устройство:**
• **Модель:** {device_model}
• **Платформа:** {platform}

📶 **Тип чата:** {update.message.chat.type}
🔄 **Дата:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """.strip()
    await safe_reply(update.message, device_info)

    ip_info = get_ip_info()
    if ip_info["ip"] != "Неизвестно":
        ip_text = f"""
{texts['ip_title']}

🌍 **IP-адрес:** `{ip_info['ip']}`
🏳️ **Страна:** {ip_info['country']}
🏙️ **Город:** {ip_info['city']}
🗺️ **Регион:** {ip_info['region']}
🕐 **Часовой пояс:** {ip_info['timezone']}
📡 **Провайдер:** {ip_info['isp']}
🏢 **Организация:** {ip_info['org']}
📍 **Координаты:** {ip_info['lat']}, {ip_info['lon']}
        """.strip()
        await safe_reply(update.message, ip_text)
    else:
        await update.message.reply_text(texts["no_ip"])


async def fact_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_language(user_id)
    texts = LANGUAGES.get(lang, LANGUAGES["ru"])
    facts = get_facts(user_id)
    if not facts:
        await update.message.reply_text(texts["fact_empty"])
        return
    text = texts["fact_title"] + "\n\n"
    for fact in facts:
        text += f"• {fact['key']}: {fact['content']}\n"
    await safe_reply(update.message, text)


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_language(user_id)
    texts = LANGUAGES.get(lang, LANGUAGES["ru"])
    history = get_history(user_id, limit=10)
    if not history:
        await update.message.reply_text(texts["history_empty"])
        return
    text = texts["history_title"] + "\n\n"
    for msg in history[-5:]:
        role = "👤 Вы" if msg["role"] == "user" else "🤖 Z"
        content = msg["content"][:200]
        if len(msg["content"]) > 200:
            content += "..."
        text += f"{role}: {content}\n"
    await safe_reply(update.message, text)


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_language(user_id)
    texts = LANGUAGES.get(lang, LANGUAGES["ru"])
    clear_history(user_id)
    await update.message.reply_text(texts["cleared"])


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data="lang_uz")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await safe_reply(
        update.message,
        "🌍 **Выберите язык / Select language / Tilni tanlang:**",
        reply_markup=reply_markup,
    )


async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    lang = query.data.replace("lang_", "")
    set_language(user_id, lang)
    texts = LANGUAGES.get(lang, LANGUAGES["ru"])
    try:
        await query.edit_message_text(texts["lang_changed"], parse_mode="Markdown")
    except Exception:
        await query.edit_message_text(texts["lang_changed"])
    await query.message.reply_text(
        "🔄 Интерфейс обновлён!",
        reply_markup=get_main_keyboard(lang),
    )


# ========== ОБРАБОТКА ИЗОБРАЖЕНИЙ ==========

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_language(user_id)
    texts = LANGUAGES.get(lang, LANGUAGES["ru"])

    await update.message.reply_text(texts["image_analyzing"])

    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        image_data = await file.download_as_bytearray()

        # ИСПРАВЛЕНО: анализ в отдельном потоке
        result = await asyncio.to_thread(analyze_image, bytes(image_data))

        await update.message.reply_text(f"🖼️ {result}")
    except Exception as e:
        logger.error(f"Ошибка фото: {e}")
        await update.message.reply_text(texts["image_error"])


# ========== ОБРАБОТКА ГОЛОСОВЫХ ==========

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ИСПРАВЛЕНО: одно сообщение вместо двух."""
    user_id = update.effective_user.id
    lang = get_language(user_id)
    texts = LANGUAGES.get(lang, LANGUAGES["ru"])
    await update.message.reply_text(texts["voice_processing"])


# ========== ОБРАБОТКА ТЕКСТА ==========

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    user_id = update.effective_user.id
    lang = get_language(user_id)
    texts = LANGUAGES.get(lang, LANGUAGES["ru"])

    logger.info(f"Сообщение от {user_id}: {user_message[:50]}...")

    # Кнопки
    if user_message in ["💬 Чат", "💬 Chat"]:
        await update.message.reply_text("💬 Напиши мне что-нибудь!")
        return
    if user_message in ["📱 Устройство", "📱 Device", "📱 Qurilma"]:
        await device_command(update, context); return
    if user_message in ["🧠 Факты", "🧠 Facts", "🧠 Faktlar"]:
        await fact_command(update, context); return
    if user_message in ["📜 История", "📜 History", "📜 Tarix"]:
        await history_command(update, context); return
    if user_message in ["🗑️ Очистить", "🗑️ Clear", "🗑️ Tozalash"]:
        await clear_command(update, context); return
    if user_message in ["❓ Помощь", "❓ Help", "❓ Yordam"]:
        await help_command(update, context); return
    if user_message in ["🌍 Язык", "🌍 Language", "🌍 Til"]:
        await language_command(update, context); return
    if user_message in ["🖼️ Анализ фото", "🖼️ Analyze Photo", "🖼️ Rasm tahlil"]:
        await update.message.reply_text("📸 Отправь мне фото!")
        return

    # === ОТВЕТ ИИ ===
    await update.message.chat.send_action(action="typing")
    thinking_msg = await update.message.reply_text(
        texts["thinking"], parse_mode="Markdown"
    )

    try:
        save_message(user_id, "user", user_message)

        # ИСПРАВЛЕНО: ask_zeta_sync в отдельном потоке
        answer = await asyncio.to_thread(ask_zeta_sync, user_message)

        save_message(user_id, "assistant", answer)

        await thinking_msg.delete()

        if len(answer) > MAX_MESSAGE_LENGTH:
            parts = [
                answer[i:i + MAX_MESSAGE_LENGTH]
                for i in range(0, len(answer), MAX_MESSAGE_LENGTH)
            ]
            for part in parts:
                await update.message.reply_text(part)
        else:
            await update.message.reply_text(answer)

    except Exception as e:
        try:
            await thinking_msg.delete()
        except Exception:
            pass
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(texts["error"].format(e=str(e)))


# ========== ЗАПУСК ==========

def run_bot():
    # ИСПРАВЛЕНО: init_db здесь, а не при импорте
    init_db()

    print("🤖 Запуск Публичного Telegram-бота Zeta (PRO)...")
    print(f"📱 Токен: {PUBLIC_BOT_TOKEN[:20]}...")
    print(f"🧠 Модель: {MODEL_CHAT}")
    print(f"👁️ Зрение: {MODEL_VISION}")

    application = Application.builder().token(PUBLIC_BOT_TOKEN).build()

    # Команды
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("device", device_command))
    application.add_handler(CommandHandler("fact", fact_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CommandHandler("language", language_command))

    application.add_handler(CallbackQueryHandler(language_callback, pattern="^lang_"))

    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))

    print("✅ Публичный бот запущен! Найди бота в Telegram и напиши /start")

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    run_bot()