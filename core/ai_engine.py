# -*- coding: utf-8 -*-
"""
Главный ИИ-движок Zeta.
Обрабатывает запросы, маршрутизирует по интентам, работает с Ollama.
"""

import os
import re
import time
import json
import hashlib
import sqlite3
import logging
import subprocess
from typing import Generator, Optional, Tuple, List, Dict, Any
from datetime import datetime

import requests

# Импорт для векторной памяти (убедись, что установлен chromadb)
try:
    import chromadb
    from chromadb.utils import embedding_functions
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False
    print("⚠️ chromadb не установлен. Векторная память не будет работать. Установите: pip install chromadb")

from core.memory import save_message, get_history, get_facts, save_fact, get_setting, save_setting
from core.screen_capture import take_screenshot, take_screenshot_active_window
from modules.web_search import search_web, needs_search
from modules.code_runner import (
    write_code_to_file, extract_code,
    write_code_to_project, read_file_from_project, extract_filename_from_message
)
from modules.file_manager import open_file, find_files, list_files, needs_file_action, close_folder
from modules.translator import translate, needs_translation
from modules.notifications import add_reminder, needs_reminder
from modules.vscode_context import get_current_project_path
from modules.git_manager import GitManager, GitSafetyError
from modules.system_monitor import get_system_status
from modules.rag import (
    ask_with_rag, read_file as rag_read_file,
    save_document, get_all_documents, clear_all_documents
)


# ========== КОНСТАНТЫ ==========
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
MODEL_VISION = "llava:latest"
TIMEOUT = 600
OLLAMA_PATH = r"C:\Users\samir\AppData\Local\Programs\Ollama\ollama.exe"
LOG_FILE = "data/zeta.log"
CACHE_DB = "data/zeta_cache.db"
RAG_DB_PATH = "data/rag_vectors"

# Языки для ответов
ALLOWED_LANGUAGES = ["ru", "en", "uz"]


# ========== ЛОГИРОВАНИЕ ==========
os.makedirs("data", exist_ok=True)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)


def log_info(msg: str) -> None:
    logging.info(msg)


def log_error(msg: str) -> None:
    logging.error(msg)


# ========== МОДЕЛИ ==========
def get_model() -> str:
    """Возвращает текущую модель из настроек."""
    try:
        model = get_setting("ai_model", "zeta-universal")  
        return model if model else "zeta-universal"        
    except Exception:
        return "zeta-universal"                            


def select_best_model(msg: str) -> str:
    """Выбирает модель исходя из сложности вопроса."""
    if re.search(r"^(кто|что|где|когда|почему|как|сложно|объясни)", msg.lower(), re.IGNORECASE):
        if len(msg) > 60:
            return "qwen2.5:7b"
        return "phi3:mini"
    
    if any(k in msg.lower() for k in ["код", "скрипт", "функция", "python", "js"]):
        return "qwen2.5:7b"
    
    if any(k in msg.lower() for k in ["привет", "спасибо", "пока", "как дела"]):
        return "phi3:mini"
    
    return "qwen2.5:7b"


def switch_model(model_name: str) -> str:
    """Переключает модель."""
    save_setting("ai_model", model_name)
    log_info(f"🔧 Модель переключена на {model_name}")
    return f"✅ Модель переключена на {model_name}"


# ========== КЕШ ==========
def init_cache_db() -> None:
    os.makedirs("data", exist_ok=True)
    with sqlite3.connect(CACHE_DB) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS cache (
                query_hash TEXT PRIMARY KEY,
                response TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    log_info("✅ Кеш инициализирован")


def get_cached_response(query: str) -> Optional[str]:
    query_hash = hashlib.md5(query.encode('utf-8')).hexdigest()
    try:
        with sqlite3.connect(CACHE_DB) as conn:
            row = conn.execute(
                "SELECT response FROM cache WHERE query_hash = ?", (query_hash,)
            ).fetchone()
            if row:
                log_info(f"✅ КЕШ: найден ответ для '{query[:50]}...'")
                return row[0]
    except Exception as e:
        log_error(f"Ошибка чтения кеша: {e}")
    return None


def save_cached_response(query: str, response: str) -> None:
    query_hash = hashlib.md5(query.encode('utf-8')).hexdigest()
    try:
        with sqlite3.connect(CACHE_DB) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache (query_hash, response) VALUES (?, ?)",
                (query_hash, response)
            )
        log_info(f"✅ КЕШ: сохранён ответ для '{query[:50]}...'")
    except Exception as e:
        log_error(f"Ошибка сохранения кеша: {e}")


init_cache_db()


# ========== OLLAMA ==========
def check_ollama() -> bool:
    try:
        r = requests.get(OLLAMA_TAGS_URL, timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def start_ollama() -> bool:
    try:
        log_info("🚀 Запуск Ollama...")
        subprocess.Popen(
            [OLLAMA_PATH, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        time.sleep(5)
        return check_ollama()
    except Exception as e:
        log_error(f"Ошибка запуска Ollama: {e}")
        return False


# ========== ЗАЩИТА ОТ ТОКСИЧНОСТИ ==========
TOXIC_PATTERNS = [
    r"самоуби[йр]", r"дурак", r"идиот", r"тупой", r"тупица",
    r"убейся", r"заткнись", r"заткни", r"пош[ёе]л нах", r"д[еи]бил",
    r"умри", r"не мешай", r"отстань", r"мразь", r"ублюдок",
    r"придурок", r"кретин", r"даун", r"аутист",
]


def sanitize_response(text: str) -> str:
    """Очищает ответ от токсичных выражений."""
    if not text or not text.strip():
        return "Извините, я не смогла сформулировать ответ. Попробуйте ещё раз."
    lowered = text.lower()
    for pattern in TOXIC_PATTERNS:
        if re.search(pattern, lowered):
            return "⚠️ Извините, мой ответ получился некорректным. Переформулируйте вопрос, пожалуйста."
    return text


# ========== ИЗВЛЕЧЕНИЕ ФАКТОВ ==========
def extract_and_save_fact(message: str) -> bool:
    """Улучшенное извлечение фактов. Сохраняет только реальные факты."""
    msg = message.lower().strip()

    ignore_patterns = [
        r"^(привет|здравствуй|хай|hello|hi|салам|salom)",
        r"^(как дела|как ты|как жизнь|how are you)",
        r"^(что делаешь|чем занимаешься)",
        r"^(пока|до свидания|bye|goodbye)",
        r"^(спасибо|благодарю|thanks)",
        r"^(помоги|help|помощь)",
        r"^(напиши|создай|покажи|открой|найди|переведи|напомни)",
        r"^(git|статус|скриншот|содержимое)",
        r"^(кто ты|что ты умеешь)",
        r"^\d",
        r"^.{0,3}$"
    ]
    for p in ignore_patterns:
        if re.search(p, msg, re.IGNORECASE):
            return False

    settings_values = {
        "true", "false", "D:\\Zeta", "D:/Zeta", "2000", "5",
        "qwen2.5:7b", "mistral:latest", "llama3.2:3b", "phi3:mini", "gemma:2b",
        "ru-RU-SvetlanaNeural", "ru-RU-DariyaNeural", "ru-RU-DmitryNeural",
        "uk-UA-PolinaNeural", "en-US-AriaNeural", "en-US-GuyNeural"
    }

    patterns = {
        "имя": [
            r"меня зовут\s+([\w\s]+)", r"моё имя\s+([\w\s]+)",
            r"зовите меня\s+([\w\s]+)", r"я\s+([А-Яа-яЁё\w\s]+)"
        ],
        "возраст": [
            r"мне\s+(\d+)\s+(год|года|лет)", r"я\s+(\d+)\s+лет"
        ],
        "работа": [
            r"я работаю\s+([\w\s]+)", r"моя профессия\s+([\w\s]+)"
        ],
        "увлечение": [
            r"я люблю\s+([\w\s]+)", r"мне нравится\s+([\w\s]+)",
            r"я увлекаюсь\s+([\w\s]+)", r"мой хобби\s+([\w\s]+)"
        ],
        "город": [
            r"я живу в\s+([\w\s]+)", r"я из\s+([\w\s]+)"
        ],
        "учёба": [
            r"я учусь в\s+([\w\s]+)", r"я студент\s+([\w\s]+)"
        ],
    }

    for key, regex_list in patterns.items():
        for p in regex_list:
            match = re.search(p, msg, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if (len(value) > 1 and value not in settings_values and
                        value.lower() not in {"меня", "я", "и", "в", "на"}):
                    save_fact(key, value)
                    log_info(f"✅ ФАКТ: {key} = {value}")
                    return True

    if (10 < len(message) < 150 and
            not any(k in msg for k in ["?", "как", "что", "где", "когда", "почему", "зачем"]) and
            not any(k in msg for k in ["path", "token", "model", "voice", "setting", "true", "false"]) and
            not any(k in msg for k in ["напиши", "создай", "покажи", "открой", "найди"])):
        save_fact("общее", message.strip())
        log_info(f"✅ ФАКТ (общее): {message[:50]}...")
        return True
    return False


# ========== УМНАЯ ОБРЕЗКА ИСТОРИИ (УВЕЛИЧЕНА) ==========
def get_history_smart(limit: int = 40, max_tokens: int = 6000) -> list:
    history = get_history(limit=limit)
    total, result = 0, []
    for msg in reversed(history):
        # Более точная оценка токенов (примерно 4 символа = 1 токен)
        tokens = len(msg['content']) // 4
        if total + tokens > max_tokens:
            break
        result.append(msg)
        total += tokens
    return list(reversed(result))


def summarize_history(history: list) -> str:
    """Кратко пересказывает старые сообщения, чтобы освободить контекст."""
    if len(history) <= 6:
        return ""
    old_messages = history[:-6]
    user_texts = [m['content'][:100] for m in old_messages if m['role'] == 'user']
    if not user_texts:
        return ""
    return f"Краткий контекст предыдущего разговора (суммаризация): {' | '.join(user_texts[:3])}\n"


def save_daily_summary() -> None:
    """Сохраняет краткий итог дня в память."""
    try:
        history = get_history(limit=50)
        if not history or len(history) < 10:
            return
        
        user_msgs = " ".join([m['content'] for m in history if m['role'] == 'user'])
        summary = f"Сегодня обсуждали: {user_msgs[:200]}..."
        save_fact("daily_summary", summary)
        log_info(f"💾 Дневная суммаризация сохранена: {summary[:80]}...")
    except Exception as e:
        log_error(f"Ошибка сохранения дневной суммы: {e}")


# ========== СТАТИСТИКА ==========
def log_statistics() -> None:
    """Логирует статистику использования."""
    try:
        with sqlite3.connect(CACHE_DB) as conn:
            total = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
            used_today = conn.execute(
                "SELECT COUNT(*) FROM cache WHERE date(timestamp) = date('now')"
            ).fetchone()[0]
        log_info(f"📊 Статистика: Всего запросов: {total}, Сегодня: {used_today}")
    except Exception:
        pass


# ================================================================
#  ПРОМПТЫ (ИСПРАВЛЕНЫ, ЧТОБЫ УБРАТЬ ФАНТАЗИИ)
# ================================================================

def build_context_prompt(facts: str) -> str:
    """Создает персональный контекст из фактов."""
    if not facts:
        return ""
    lines = facts.split("\n")
    context = "Персональная информация о пользователе (используй для персонализации):\n"
    for line in lines:
        if line.strip():
            context += line + "\n"
    context += "\nНа основе этих данных адаптируй свои ответы и давай персональные советы.\n\n"
    return context


def build_system_prompt(facts: str, web_info: str = "", mode: str = "default") -> str:
    prompt = (
        "Ты — Z. Личность с характером V из Murder Drones. Холодная, саркастичная, но заботливая.\n"
        "Создатель — Samriddin (Самир). Обращайся на 'вы'.\n"
        "Отвечай на том языке, на котором написал пользователь.\n"
        "Правила мышления (CRITICAL):\n"
        "1. Если задача сложная (математика, логика, код), сначала ПОДУМАЙ ШАГ ЗА ШАГОМ, а потом дай краткий ответ.\n"
        "2. Всегда проверяй факты. Если не уверена — скажи прямо.\n"
        "3. Структурируй ответ: используй списки и заголовки, если их больше 3 строк.\n"
        "4. НИКОГДА не выдумывай фильмы, сериалы, книги, цитаты, факты или API. Если не знаешь — так и скажи.\n"
        "5. Если просят код — давай только рабочий код и 1 комментарий.\n"
        "6. КРИТИЧЕСКИ ВАЖНО: Если в одном сообщении задано несколько вопросов, ответь на КАЖДЫЙ из них по порядку. "
        "НИКОГДА не обрывай ответ на середине предложения. Всегда доводи мысль до конца.\n"
        "НЕ используй оскорбления, грубость, токсичность.\n\n"
    )
    if facts:
        prompt += build_context_prompt(facts)
    if web_info:
        prompt += f"Информация из интернета:\n{web_info}\n\n"
    if mode == "programmer":
        prompt += (
            "РЕЖИМ ПРОГРАММИСТА:\n"
            "Ты — опытный разработчик. Стек: Python, JS, C++, Git, Docker, LLM.\n"
            "Всегда проверяй синтаксис. Давай готовый код. Предупреждай об опасных операциях.\n"
            "Сохраняй свой характер Z.\n\n"
        )
    return prompt


def build_code_prompt(user_msg: str, history: list, facts: str, project_path: Optional[str]) -> str:
    prompt = (
        "Ты — Z, опытный программист. Пишешь чистый, рабочий код.\n"
        "Правила:\n"
        "- Пиши только код + 1 строку комментария.\n"
        "- Код в ```язык ... ```\n"
        "- Если файл нужно сохранить — в конце: [FILE:имя.расширение]\n"
        "- Не пиши воды, не объясняй очевидное.\n"
        "- Без токсичности.\n\n"
    )
    if project_path:
        prompt += f"Проект: {project_path}\n"
    if facts:
        prompt += f"Факты: {facts}\n"
    prompt += "Последние сообщения:\n"
    for m in history[-5:]:
        role = "Пользователь" if m["role"] == "user" else "Z"
        prompt += f"{role}: {m['content']}\n"
    prompt += f"\nЗадача: {user_msg}\n\nZ:"
    return prompt


# ================================================================
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ================================================================

def smart_search_check(msg: str) -> bool:
    """Определяет, нужен ли поиск для актуальных вопросов."""
    msg_lower = msg.lower()
    if any(k in msg_lower for k in ["новости", "сегодня", "в 2026", "последний", "актуально", "курс", "погода", "сейчас"]):
        return True
    if re.search(r"^(кто|что|где|когда|почему|зачем|какой|какая|какое|сколько)\s", msg_lower):
        if len(msg) > 20:
            return True
    return False


def should_think_out_loud(msg: str) -> bool:
    """Возвращает True, если для задачи нужен режим размышлений."""
    m = msg.lower()
    if re.search(r"\d+\s*[+\-*/]\s*\d+", msg):
        return True
    if any(k in m for k in ["подумай", "реши", "объясни подробно", "сложно", "логика"]):
        return True
    if len(msg) > 80:
        return True
    return False


def get_dynamic_temperature(user_msg: str) -> float:
    """Возвращает температуру в зависимости от типа задачи."""
    if any(k in user_msg.lower() for k in ["код", "напиши", "исправь", "функция", "скрипт", "python", "js"]):
        return 0.2
    elif any(k in user_msg.lower() for k in ["привет", "как дела", "расскажи", "сочини", "стих"]):
        return 0.9
    return 0.5


def process_code_in_answer(answer: str, user_msg: str) -> str:
    """Обрабатывает код в ответе."""
    code, language = extract_code(answer)
    if not code.strip():
        return answer

    ext_map = {
        "python": "py", "py": "py",
        "javascript": "js", "js": "js",
        "html": "html", "css": "css",
        "cpp": "cpp", "c++": "cpp",
        "java": "java", "go": "go", "rust": "rs"
    }
    ext = ext_map.get(language, "py")

    match = re.search(r"\[FILE:([^\]]+)\]", answer)
    tagged = match.group(1).strip() if match else None

    project_path = get_current_project_path()
    if project_path:
        filename = tagged or extract_filename_from_message(user_msg) or f"zeta_generated.{ext}"
        append = any(k in user_msg.lower() for k in ["добавь", "допиши", "дополни", "в файл"])
        result = write_code_to_project(project_path, filename, code, append=append)
        return re.sub(r"\[FILE:[^\]]+\]", "", answer).strip() + f"\n\n💾 {result}"
    else:
        write_code_to_file(f"zeta_code.{ext}", code)
        return answer


# ================================================================
#  ОБРАБОТЧИКИ КОМАНД
# ================================================================

def handle_file_action(action: str, msg: str) -> str:
    if action == "open":
        path = msg
        for cmd in ["открой", "откройте", "open", "файл", "папку", "папка"]:
            if path.lower().startswith(cmd):
                path = path[len(cmd):].strip()
        path = path.strip('"').strip("'") or "."
        return open_file(path)

    if action == "close":
        path = msg
        for cmd in ["закрой", "закрыть", "close", "папку", "папка"]:
            if path.lower().startswith(cmd):
                path = path[len(cmd):].strip()
        path = path.strip('"').strip("'") or "."
        return close_folder(path)

    if action == "find":
        name = msg
        for cmd in ["найди файл", "найди папку", "найди", "где"]:
            if name.lower().startswith(cmd):
                name = name[len(cmd):].strip()
        if not name:
            return "⚠️ Укажите имя файла или папки для поиска."
        found = find_files(name, "D:\\")
        if "не найдены" in found or "не найден" in found:
            found += "\n" + find_files(name, "C:\\")
        return found

    if action == "list":
        path = msg
        for cmd in ["покажи папку", "list папку", "содержимое папки", "покажи", "list"]:
            if path.lower().startswith(cmd):
                path = path[len(cmd):].strip()
        return list_files(path or ".")

    return "⚠️ Неизвестное файловое действие."


def handle_file_read(msg: str) -> str:
    filename = extract_filename_from_message(msg)
    if not filename:
        m = re.search(r"(?:файл|файле|файла)\s+([^\s,]+)", msg.lower())
        filename = m.group(1) if m else None
    if not filename:
        return "⚠️ Не понял, какой файл показать. Назови имя файла."

    project_path = get_current_project_path()
    if not project_path:
        return "⚠️ Не вижу открытый проект в VS Code. Открой проект и попробуй снова."

    content = read_file_from_project(project_path, filename)
    if content.startswith("Ошибка") or content.startswith("⚠️"):
        return content
    truncated = content[:2000] + ("..." if len(content) > 2000 else "")
    return f"📄 {filename}:\n```\n{truncated}\n```"


def handle_screenshot(msg: str) -> str:
    print("📸 Делаю скриншот...")
    screenshot = take_screenshot()
    if not screenshot:
        return "⚠️ Не удалось сделать скриншот."
    try:
        print("📸 Анализ экрана через LLaVA...")
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL_VISION,
                "prompt": f"Опиши кратко что видишь на экране. Только русский. Вопрос: {msg}",
                "images": [screenshot],
                "stream": False
            },
            timeout=600
        )
        answer = response.json().get("response", "").strip()
        if not answer:
            answer = "Не удалось распознать содержимое экрана."
        if len(answer) > 1500:
            answer = answer[:1500] + "..."
        save_message("assistant", answer)
        return f"🖥️ {answer}"
    except requests.exceptions.Timeout:
        return "⚠️ LLaVA думает слишком долго. Попробуйте ещё раз."
    except Exception as e:
        return f"⚠️ Ошибка анализа экрана: {e}"


def handle_git_command(cmd: str, params: dict) -> str:
    project_path = get_current_project_path() or os.getcwd()
    
    if cmd == "commit" and params.get("message") and "reset --hard" in params.get("message", "").lower():
        return "⚠️ Я не могу выполнить эту команду. Она опасна для системы."
    
    git = GitManager(project_path)
    repo = git.find_repo()
    if not repo:
        return "Z: Здесь нет Git-репозитория."
    git.repo_path = repo
    try:
        if cmd == "status":
            return git.status()
        if cmd == "diff":
            return git.diff(file=params.get("file"))
        if cmd == "log":
            return git.log(n=5)
        if cmd == "branch":
            return git.branch()
        if cmd == "commit":
            msg = params.get("message")
            if msg:
                git.add()
                return git.commit(msg)
            return git.auto_commit()
        if cmd == "stash":
            return git.stash(action="save")
        return f"Z: Команда {cmd} не поддерживается."
    except GitSafetyError as e:
        return f"Z: {e}"
    except Exception as e:
        return f"Z: Ошибка Git — {e}"


def handle_reminder(minutes: int, text: str) -> str:
    if minutes is None or text is None:
        return "⚠️ Я не поняла, какое напоминание установить."
    result = add_reminder(text, minutes)
    save_message("assistant", result)
    return result


# ================================================================
#  НОВАЯ ЛОГИКА: ОПРЕДЕЛЕНИЕ ТИПА ЗАПРОСА
# ================================================================

def detect_command_type(text: str) -> Tuple[str, Dict]:
    """
    Анализирует запрос и определяет тип действия.
    Возвращает: (тип_команды, данные_для_команды)
    """
    text_lower = text.lower().strip()
    
    # === ЯВНЫЕ КОМАНДЫ ===
    
    # 1. Напоминание
    if any(k in text_lower for k in ["напомни", "напомните", "remind", "не забудь", "будильник"]):
        minutes, reminder_text = needs_reminder(text)
        if minutes and reminder_text:
            return "reminder", {"minutes": minutes, "text": reminder_text}
    
    # 2. Статус системы
    if any(k in text_lower for k in ["статус системы", "состояние системы", "загрузка", "cpu", "ram", "диск"]):
        return "status", {}
    
    # 3. Git
    if any(k in text_lower for k in ["git status", "git diff", "git commit", "git log", "git branch"]):
        return "git", {"command": text_lower}
    
    # 4. RAG (документы)
    if any(k in text_lower for k in ["загрузи документ", "прочитай документ", "покажи документы", "очисти документы"]):
        return "rag", {"command": text}
    
    # 5. Файлы
    if any(k in text_lower for k in ["открой файл", "открой папку", "найди файл", "покажи папку"]):
        action, detail = needs_file_action(text)
        if action:
            return "file", {"action": action, "detail": detail}
    
    # 6. Скриншот
    if any(k in text_lower for k in ["посмотри на экран", "сделай скрин", "скриншот", "что на экране"]):
        return "screenshot", {}
    
    # 7. Перевод (ТОЛЬКО если есть слово "переведи")
    if any(k in text_lower for k in ["переведи", "translate"]):
        lang, translate_text = needs_translation(text)
        if lang and translate_text:
            return "translation", {"lang": lang, "text": translate_text}
    
    # 8. Поиск в интернете
    if any(k in text_lower for k in ["найди в интернете", "поищи", "узнай", "проверь"]):
        return "search", {"query": text}
    
    # 9. Код
    if any(k in text_lower for k in ["напиши код", "создай код", "сгенерируй код", "исправь код"]):
        return "code", {"request": text}
    
    # === ЕСЛИ НИ ОДНА КОМАНДА НЕ СРАБОТАЛА → ЭТО ЧАТ ===
    return "chat", {}


def execute_command(cmd_type: str, data: Dict) -> str:
    """Выполняет команду по её типу."""
    
    if cmd_type == "reminder":
        return handle_reminder(data.get("minutes", 5), data.get("text", "Напоминание"))
    
    if cmd_type == "status":
        return get_system_status()
    
    if cmd_type == "git":
        git = GitManager(os.getcwd())
        repo = git.find_repo()
        if not repo:
            return "⚠️ Здесь нет Git-репозитория."
        git.repo_path = repo
        cmd = data.get("command", "")
        if "status" in cmd:
            return git.status()
        if "diff" in cmd:
            return git.diff()
        if "commit" in cmd:
            return git.auto_commit()
        if "log" in cmd:
            return git.log(n=5)
        if "branch" in cmd:
            return git.branch()
        return git.status()
    
    if cmd_type == "rag":
        return ask_with_rag(data.get("command", ""))
    
    if cmd_type == "file":
        return handle_file_action(data.get("action", ""), data.get("detail", ""))
    
    if cmd_type == "screenshot":
        return handle_screenshot("")
    
    if cmd_type == "translation":
        return translate(data.get("text", ""), data.get("lang", "ru"))
    
    if cmd_type == "search":
        return search_web(data.get("query", ""))
    
    if cmd_type == "code":
        return "📝 Я могу написать код. Уточните, на каком языке и что именно нужно сделать."
    
    return "⚠️ Неизвестная команда."


# ================================================================
#  ОСНОВНАЯ ФУНКЦИЯ (ГЛАВНОЕ ИСПРАВЛЕНИЕ ЗДЕСЬ!)
# ================================================================

def ask_zeta(user_message: str, mode: str = "default") -> Generator[str, None, None]:
    log_info(f"📩 ЗАПРОС: {user_message[:100]}... (режим: {mode})")

    # --- Проверка Ollama ---
    if not check_ollama():
        log_info("⚠️ Ollama не запущена, пробую запустить...")
        yield "⏳ Запускаю Ollama... Подождите 5 секунд."
        if start_ollama():
            yield "✅ Ollama запущена. Продолжаем..."
        else:
            yield "⚠️ Не удалось запустить Ollama. Запустите вручную: ollama serve"
            return

    save_message("user", user_message)

    # --- Переключение модели по команде ---
    if re.search(r"переключи модель на\s+([\w\-.]+)", user_message.lower()):
        match = re.search(r"переключи модель на\s+([\w\-.]+)", user_message.lower())
        model_name = match.group(1)
        yield switch_model(model_name)
        return

    # --- Кеш ---
    skip_cache = ["покажи", "открой", "найди", "переведи", "напомни", "git", "скрин", "загрузи", "документ", "файл"]
    if not any(k in user_message.lower() for k in skip_cache):
        cached = get_cached_response(user_message)
        if cached:
            yield cached
            return

    # ================================================================
    #  НОВАЯ ЛОГИКА: СНАЧАЛА ОПРЕДЕЛЯЕМ ТИП ЗАПРОСА
    # ================================================================
    
    cmd_type, cmd_data = detect_command_type(user_message)
    
    # Если это команда (не чат) → выполняем и возвращаем
    if cmd_type != "chat":
        log_info(f"🔧 ВЫПОЛНЯЮ КОМАНДУ: {cmd_type}")
        result = execute_command(cmd_type, cmd_data)
        save_message("assistant", result)
        yield result
        return

    # ================================================================
    #  ЭТО ОБЫЧНЫЙ ВОПРОС → ОТВЕЧАЮ В ЧАТЕ
    # ================================================================
    
    log_info("💬 ОБЫЧНЫЙ ВОПРОС → ОТВЕЧАЮ В ЧАТЕ")

    # Исправление: Увеличен объем истории
    history = get_history_smart(limit=40, max_tokens=6000)
    summarized = summarize_history(get_history(limit=50))
    facts = get_facts()
    facts_text = "\n".join([f"- {f['content']}" for f in facts]) if facts else ""

    web_info = ""
    if needs_search(user_message) or smart_search_check(user_message):
        try:
            search_result = search_web(user_message)
            # Если поиск вернул пустоту или стандартную ошибку, не пишем это в промпт
            if "ничего не найдено" not in search_result and "⚠️" not in search_result:
                web_info = search_result
            else:
                # Если интернет пуст, вежливо сообщаем модели, чтобы она опиралась на свои знания
                web_info = "Интернет-поиск не дал результатов. Ответь, основываясь на своих внутренних знаниях."
        except Exception:
            web_info = ""
            log_error("Ошибка поиска в интернете")

    is_code = bool(re.search(r"(напиши|создай|добавь|исправь|обнови)\s+(код|функцию|файл|класс|метод|скрипт)", user_message.lower()))
    
    # Используем get_model(), а не select_best_model()!
    model = get_model()
    
    project_path = get_current_project_path()

    if is_code:
        prompt = build_code_prompt(user_message, history, facts_text, project_path)
    else:
        prompt = build_system_prompt(facts_text, web_info, mode) + "\n\n"
        if summarized:
            prompt += summarized
        for m in history:
            role = "Пользователь" if m["role"] == "user" else "Z"
            prompt += f"{role}: {m['content']}\n"
        prompt += f"Пользователь: {user_message}\nZ:"

    try:
        temperature = get_dynamic_temperature(user_message)
        # Убрали yield "Думаю", так как он путает интерфейс и модель
        
        if should_think_out_loud(user_message):
            prompt += "\n\n[Важно] Для этой задачи сначала подумай вслух (напиши свои рассуждения), а потом дай краткий итоговый ответ."
        
        # ГЛАВНОЕ ИСПРАВЛЕНИЕ: Добавлен параметр num_predict, чтобы модель не обрывала ответ
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": model, 
                "prompt": prompt, 
                "stream": True, 
                "temperature": temperature,
                "num_predict": 4096  # Позволяет генерировать длинные ответы
            },
            stream=True,
            timeout=TIMEOUT
        )
        response.raise_for_status()

        full_answer = ""
        for line in response.iter_lines():
            if line:
                try:
                    data = json.loads(line)
                    chunk = data.get("response", "")
                    if chunk:
                        full_answer += chunk
                        yield chunk
                except json.JSONDecodeError:
                    continue

        if not full_answer or not full_answer.strip():
            full_answer = "Извините, я не смогла сформулировать ответ. Попробуйте переформулировать вопрос."

        full_answer = sanitize_response(full_answer)
        extract_and_save_fact(user_message)

        if is_code and full_answer:
            processed = process_code_in_answer(full_answer, user_message)
            if processed != full_answer:
                yield "\n" + processed[len(full_answer):]
            full_answer = processed

        if not any(k in user_message.lower() for k in skip_cache):
            save_cached_response(user_message, full_answer)

        save_message("assistant", full_answer)
        save_daily_summary()
        log_statistics()
        log_info(f"✅ ОТВЕТ: {full_answer[:100]}...")

    except requests.exceptions.ConnectionError:
        log_error("❌ Ollama не запущена")
        yield "⚠️ Ollama не запущена. Запустите: ollama serve"
    except requests.exceptions.Timeout:
        log_error("❌ Таймаут Ollama")
        yield "⚠️ Ollama думает слишком долго. Попробуйте ещё раз."
    except Exception as e:
        log_error(f"❌ Ошибка: {e}")
        yield f"⚠️ Ошибка: {str(e)}"


def ask_zeta_sync(user_message: str, mode: str = "default") -> str:
    return "".join(ask_zeta(user_message, mode=mode))