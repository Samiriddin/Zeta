# -*- coding: utf-8 -*-
"""
Главный ИИ-движок Zeta.
Умная маршрутизация: команды только по точным паттернам, всё остальное — модели.
Санитизация ввода, защита от path traversal, режим создателя, защита Git, аудит.

Подключено:
    - pc_control (приложения, громкость, буфер, IP, питание)
    - browser_control (сайты, поиск, вкладки, закладки)

ИСПРАВЛЕНО (2026-09-21):
    - PENDING_POWER_ACTION: сбрасывается при любой не-power команде
    - handle_power_confirm: логирует результат в аудит
    - extract_and_save_fact: обрезка до 3 слов
    - handle_screenshot: сохраняет файл в data/screenshots/
    - _audit_command: логирует результат
    - handle_app_*: проверка на пустое имя
    - НОВОЕ: 25+ команд браузера через browser_control
    - НОВОЕ: pending-выбор браузера (как у power)
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

try:
    import chromadb
    from chromadb.utils import embedding_functions
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False
    print("⚠️ chromadb не установлен. Векторная память не будет работать.")

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

# === УПРАВЛЕНИЕ ПК ===
try:
    from modules import pc_control
    HAS_PC = True
except ImportError as e:
    HAS_PC = False
    pc_control = None
    print(f"⚠️ pc_control не найден: {e}")

# === УПРАВЛЕНИЕ БРАУЗЕРОМ ===
try:
    from modules.browser_control import (
        get_browser,
        has_pending_browser_choice,
        SITES as BROWSER_SITES,
    )
    HAS_BROWSER = True
except ImportError as e:
    HAS_BROWSER = False
    get_browser = None
    has_pending_browser_choice = lambda: False
    BROWSER_SITES = {}
    print(f"⚠️ browser_control не найден: {e}")

# === БЕЗОПАСНОСТЬ ===
try:
    from security.sanitizer import InputSanitizer, sanitize
    HAS_SANITIZER = True
except ImportError:
    HAS_SANITIZER = False
    sanitize = None
    InputSanitizer = None
    print("⚠️ Модуль sanitizer не найден.")

# === ЗАЩИТА GIT ===
try:
    from security.git_guard import GitGuard, DangerLevel
    HAS_GIT_GUARD = True
except ImportError:
    HAS_GIT_GUARD = False
    print("⚠️ Модуль git_guard не найден.")
    DangerLevel = None
    GitGuard = None

# === СОЗДАТЕЛЬ ===
try:
    from secret.creator import get_creator
    HAS_CREATOR = True
except ImportError:
    HAS_CREATOR = False
    print("⚠️ Модуль создателя не найден.")

# === АУДИТ ===
try:
    from security.audit import get_audit
    HAS_AUDIT = True
except ImportError:
    HAS_AUDIT = False
    print("⚠️ Модуль аудита не найден.")


# ========== КОНСТАНТЫ ==========
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
MODEL_VISION = "llava:13b"
MODEL_DEFAULT = "zeta-universal"
TIMEOUT = 600
OLLAMA_PATH = r"C:\Users\samir\AppData\Local\Programs\Ollama\ollama.exe"
LOG_FILE = "data/zeta.log"
CACHE_DB = "data/zeta_cache.db"
RAG_DB_PATH = "data/rag_vectors"
SCREENSHOT_DIR = "data/screenshots"
MAX_INPUT_LENGTH = 5000

# Опасные действия — требуют подтверждения
PENDING_POWER_ACTION: Optional[str] = None

# Слова-подтверждения
POWER_YES = {"да", "да выключай", "да перезагрузи", "подтверждаю", "ок", "yes", "y"}
POWER_NO = {"нет", "отмена", "отмени", "no", "n", "не надо"}


# ========== ЛОГИРОВАНИЕ ==========
os.makedirs("data", exist_ok=True)
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

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


# ========== АУДИТ ==========

def _audit_command(text: str, source: str = "widget", result: str = None) -> None:
    if not HAS_AUDIT:
        return
    try:
        get_audit().log_command(text, source=source, result=result)
    except Exception:
        pass


def _audit_git(command: str, args: str, level: str = "safe", blocked: bool = False) -> None:
    if not HAS_AUDIT:
        return
    try:
        get_audit().log_git(command, args, level=level, blocked=blocked)
    except Exception:
        pass


def _audit_error(error: str, context: str = "") -> None:
    if not HAS_AUDIT:
        return
    try:
        get_audit().log_error(error, context)
    except Exception:
        pass


# ========== ЗАЩИТА ВВОДА ==========

def validate_input(text: str) -> Tuple[bool, str]:
    if not text or not text.strip():
        return False, "⚠️ Пустой запрос."

    if len(text) > MAX_INPUT_LENGTH:
        return False, f"⚠️ Слишком длинный запрос ({len(text)} символов, максимум {MAX_INPUT_LENGTH})."

    cleaned = None
    if HAS_SANITIZER:
        try:
            if sanitize is not None:
                cleaned = sanitize(text)
            elif InputSanitizer is not None:
                cleaned = InputSanitizer.sanitize_text(text, max_length=MAX_INPUT_LENGTH)
        except Exception as e:
            log_error(f"Ошибка санитизации: {e}")
            cleaned = None

    if not cleaned:
        cleaned = text[:MAX_INPUT_LENGTH]

    return True, cleaned


def validate_file_command(text: str) -> Tuple[bool, str]:
    dangerous_paths = ["../", "..\\", "/etc/", "System32"]
    for path in dangerous_paths:
        if path.lower() in text.lower():
            if not re.search(r"[A-Z]:\\", text):
                return False, "⚠️ Опасный путь. Укажите полный путь с диском (например, D:\\file.txt)."
    return True, text


# ========== РЕЖИМ СОЗДАТЕЛЯ ==========

def check_creator(text: str) -> bool:
    if not HAS_CREATOR:
        return False
    try:
        creator = get_creator()
        if not creator.has_secret():
            return False
        if creator.check_secret(text):
            creator.activate()
            log_info(f"👑 СОЗДАТЕЛЬ ОБНАРУЖЕН")
            return True
    except Exception as e:
        log_error(f"Ошибка проверки создателя: {e}")
    return False


def is_creator_mode() -> bool:
    if not HAS_CREATOR:
        return False
    try:
        return get_creator().is_active()
    except Exception:
        return False


# ========== МОДЕЛИ ==========

def get_model() -> str:
    try:
        model = get_setting("ai_model", MODEL_DEFAULT)
        return model if model else MODEL_DEFAULT
    except Exception:
        return MODEL_DEFAULT


def switch_model(model_name: str) -> str:
    save_setting("ai_model", model_name)
    log_info(f"🔧 Модель переключена на {model_name}")
    return f"✅ Модель переключена на {model_name}"


# ========== КЕШ ==========

def init_cache_db() -> None:
    try:
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
    except Exception as e:
        log_error(f"Ошибка init_cache_db: {e}")


try:
    init_cache_db()
except Exception as e:
    log_error(f"Ошибка запуска init_cache_db: {e}")


def get_cached_response(query: str) -> Optional[str]:
    query_hash = hashlib.md5(query.encode('utf-8')).hexdigest()
    try:
        with sqlite3.connect(CACHE_DB) as conn:
            row = conn.execute(
                "SELECT response FROM cache WHERE query_hash = ?", (query_hash,)
            ).fetchone()
            if row:
                log_info(f"✅ КЕШ: найден ответ")
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
    except Exception as e:
        log_error(f"Ошибка сохранения кеша: {e}")


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


# ========== ТОКСИЧНОСТЬ ==========
TOXIC_PATTERNS = [
    r"самоуби[йр]", r"убейся", r"пош[ёе]л нах", r"заткнись",
    r"заткни", r"умри", r"мразь", r"ублюдок", r"придурок", r"кретин",
]


def sanitize_response(text: str) -> str:
    if not text or not text.strip():
        return "Извините, я не смогла сформулировать ответ. Попробуйте ещё раз."

    lowered = text.lower()
    for pattern in TOXIC_PATTERNS:
        if re.search(pattern, lowered):
            return "⚠️ Извините, мой ответ получился некорректным."

    cjk_pattern = re.compile(
        r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff'
        r'\uac00-\ud7af\u3130-\u318f]+'
    )
    if cjk_pattern.search(text):
        text = cjk_pattern.sub("", text)
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\s+([.,!?;:])', r'\1', text)
        if not text.strip() or len(text.strip()) < 3:
            return "Извините, произошла ошибка. Попробуйте переформулировать вопрос."

    fake_questions = [
        r'Почему вы хотели услышать[^?]*\?',
        r'У вас есть какие[^?]*\?',
        r'Есть ли у вас[^?]*\?',
        r'Могу ли я[^?]*\?',
        r'Хотите[^?]*\?',
        r'У вас есть вопросы[^?]*\?',
        r'Вам интересно[^?]*\?',
        r'Что ещё вы хотите[^?]*\?',
        r'Может быть, вы хотите[^?]*\?',
        r'Рассказать подробнее[^?]*\?',
    ]
    for pattern in fake_questions:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)

    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'[ \t]+([.,!?;:])', r'\1', text)
    text = re.sub(r'[,;\s]+$', '', text)

    if not text:
        return "Извините, произошла ошибка. Попробуйте переформулировать вопрос."
    return text


# ========== ФАКТЫ ==========

def _clean_fact_value(value: str, max_words: int = 3) -> str:
    if not value:
        return ""
    words = value.strip().split()
    return " ".join(words[:max_words])


def extract_and_save_fact(message: str) -> bool:
    msg = message.lower().strip()
    if len(msg) < 4:
        return False
    if re.match(r"^\d+$", msg):
        return False

    patterns = {
        "имя": [r"меня зовут\s+([\w]+)", r"моё имя\s+([\w]+)", r"мое имя\s+([\w]+)"],
        "возраст": [r"мне\s+(\d+)\s+(?:год|года|лет)"],
        "работа": [r"я работаю\s+([\w\s]{2,40})"],
        "увлечение": [r"я люблю\s+([\w\s]{2,40})", r"мне нравится\s+([\w\s]{2,40})"],
        "город": [r"я живу в\s+([\w\s]{2,40})", r"я из\s+([\w\s]{2,40})"],
        "учёба": [r"я учусь в\s+([\w\s]{2,40})", r"я студент\s+([\w\s]{2,40})"],
    }

    for key, regex_list in patterns.items():
        for p in regex_list:
            match = re.search(p, msg, re.IGNORECASE)
            if match:
                value = _clean_fact_value(match.group(1).strip(), max_words=3)
                if len(value) > 1:
                    save_fact(key, value)
                    log_info(f"✅ ФАКТ: {key} = {value}")
                    return True
    return False


# ========== ИСТОРИЯ ==========

def get_history_smart(limit: int = 20, max_tokens: int = 4000) -> list:
    history = get_history(limit=limit)
    total, result = 0, []
    for msg in reversed(history):
        tokens = len(msg['content']) // 4
        if total + tokens > max_tokens:
            break
        result.append(msg)
        total += tokens
    return list(reversed(result))


def summarize_history(history: list) -> str:
    if len(history) <= 10:
        return ""
    old_messages = history[:-10]
    user_texts = [m['content'][:80] for m in old_messages if m['role'] == 'user']
    if not user_texts:
        return ""
    return f"[Контекст: {' | '.join(user_texts[-3:])}]\n"


def log_statistics() -> None:
    try:
        with sqlite3.connect(CACHE_DB) as conn:
            total = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
            used_today = conn.execute(
                "SELECT COUNT(*) FROM cache WHERE date(timestamp) = date('now')"
            ).fetchone()[0]
        log_info(f"📊 Статистика: Всего: {total}, Сегодня: {used_today}")
    except Exception:
        pass


# ================================================================
#  ПРОМПТЫ
# ================================================================

def build_system_prompt(facts: str, web_info: str = "", mode: str = "default") -> str:
    creator_active = is_creator_mode()

    prompt = (
        "=== КОНТЕКСТ ===\n"
        "Ты — Zeta. Тебя создал Самир (Samriddin).\n"
        "Характер V из Murder Drones: холодная, саркастичная, но заботливая.\n"
        "У тебя есть голос (TTS). Когда просят «прочитай», «озвучь» — просто отвечай текстом.\n\n"
        "=== ПРАВИЛА ОТВЕТА ===\n"
        "0. Отвечай ТОЛЬКО на РУССКОМ языке!\n"
        "1. Отвечай ТОЛЬКО на ТЕКУЩЕЕ сообщение.\n"
        "2. НЕ перескакивай на другие темы из истории.\n"
        "3. Если похвалили — поблагодари кратко.\n"
        "4. Если не понял — попроси уточнить.\n"
        "5. НЕ задавай встречных вопросов в конце.\n\n"
    )

    if creator_active:
        prompt += (
            "=== 👑 РЕЖИМ СОЗДАТЕЛЯ ===\n"
            "Ты общаешься с СОЗДАТЕЛЕМ Самриддин.\n"
            "Обращайся на «ты», дружелюбно, тепло.\n"
            "Можешь называть его «Самриддин», «босс», «создатель», «Владыка».\n\n"
        )

    if mode == "programmer":
        prompt += (
            "=== РЕЖИМ ПРОГРАММИСТА ===\n"
            "Ты опытный разработчик. Стек: Python, JS, C++, Git, Docker.\n"
            "Давай готовый рабочий код с 1-2 комментариями.\n\n"
        )

    if facts:
        prompt += "=== ИНФО О ПОЛЬЗОВАТЕЛЕ ===\n"
        for line in facts.split("\n"):
            if line.strip():
                prompt += line + "\n"
        prompt += "\n"

    if web_info:
        prompt += f"=== ИНТЕРНЕТ ===\n{web_info}\n\n"

    return prompt


def build_code_prompt(user_msg: str, history: list, facts: str, project_path: Optional[str]) -> str:
    creator_active = is_creator_mode()

    prompt = (
        "=== ЗАДАЧА КОДА ===\n"
        "Ты — Z, опытный программист. Пишешь чистый рабочий код.\n"
        "Правила:\n"
        "- Только код + 1 строка комментария.\n"
        "- Код в ```язык ... ```\n"
        "- Если нужно сохранить — в конце: [FILE:имя.расширение]\n"
        "- Не пиши воды.\n\n"
    )

    if creator_active:
        prompt += "👑 Режим создателя: обращайся к Самиру на «ты».\n\n"

    if project_path:
        prompt += f"Проект: {project_path}\n"
    if facts:
        prompt += f"Факты: {facts}\n"
    prompt += "История:\n"
    for m in history[-5:]:
        role = "Пользователь" if m["role"] == "user" else "Z"
        prompt += f"{role}: {m['content']}\n"
    prompt += f"\nЗадача: {user_msg}\n\nZ:"
    return prompt


# ================================================================
#  ВСПОМОГАТЕЛЬНЫЕ
# ================================================================

def should_think_out_loud(msg: str) -> bool:
    m = msg.lower()
    if re.search(r"\d+\s*[+\-*/×÷]\s*\d+", msg):
        return True
    if any(k in m for k in ["подумай", "реши задачу", "объясни подробно", "сколько будет", "посчитай"]):
        return True
    return False


def get_dynamic_temperature(user_msg: str) -> float:
    base = 0.5
    lower = user_msg.lower()
    if any(k in lower for k in ["код", "напиши", "исправь", "функция", "скрипт"]):
        base = 0.2
    elif any(k in lower for k in ["привет", "расскажи", "сочини", "стих"]):
        base = 0.8
    if is_creator_mode():
        base = min(0.95, base + 0.05)
    return base


def process_code_in_answer(answer: str, user_msg: str) -> str:
    code, language = extract_code(answer)
    if not code.strip():
        return answer

    ext_map = {
        "python": "py", "py": "py", "javascript": "js", "js": "js",
        "html": "html", "css": "css", "cpp": "cpp", "c++": "cpp",
        "java": "java", "go": "go", "rust": "rs"
    }
    ext = ext_map.get(language, "py")

    match = re.search(r"\[FILE:([^\]]+)\]", answer)
    tagged = match.group(1).strip() if match else None

    project_path = get_current_project_path()
    if project_path:
        filename = tagged or extract_filename_from_message(user_msg) or f"zeta_generated.{ext}"
        append = any(k in user_msg.lower() for k in ["добавь", "допиши", "дополни"])
        result = write_code_to_project(project_path, filename, code, append=append)
        cleaned = re.sub(r"\[FILE:[^\]]+\]", "", answer).strip()
        return cleaned + f"\n\n💾 {result}"
    else:
        write_code_to_file(f"zeta_code.{ext}", code)
        return answer


# ================================================================
#  ОБРАБОТЧИКИ КОМАНД
# ================================================================

def handle_file_action(action: str, msg: str) -> str:
    is_safe, result = validate_file_command(msg)
    if not is_safe:
        return result

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
            return "⚠️ Укажите имя файла."
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
        return "⚠️ Не понял, какой файл показать."

    project_path = get_current_project_path()
    if not project_path:
        return "⚠️ Не вижу открытый проект в VS Code."

    content = read_file_from_project(project_path, filename)
    if content.startswith("Ошибка") or content.startswith("⚠️"):
        return content
    truncated = content[:2000] + ("..." if len(content) > 2000 else "")
    return f"📄 {filename}:\n```\n{truncated}\n```"


def handle_screenshot(msg: str, mode: str = "default") -> str:
    print("📸 Делаю скриншот...")

    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    filename = f"screen_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    save_path = os.path.join(SCREENSHOT_DIR, filename)

    try:
        screenshot_b64 = take_screenshot(save_path=save_path)
    except TypeError:
        screenshot_b64 = take_screenshot()

    if not screenshot_b64:
        return "⚠️ Не удалось сделать скриншот."

    if mode == "programmer":
        prompt = (
            f"Ты — опытный программист. Посмотри на скриншот и помоги с кодом. "
            f"Опиши что видишь, укажи ошибки, предложи решение. Только русский. "
            f"Вопрос: {msg}"
        )
    else:
        prompt = f"Опиши кратко что видишь на экране. Только русский. Вопрос: {msg}"

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL_VISION,
                "prompt": prompt,
                "images": [screenshot_b64],
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
        return f"🖥️ {answer}\n\n📁 Скриншот: `{save_path}`"
    except requests.exceptions.Timeout:
        return f"⚠️ LLaVA думает слишком долго.\n📁 Скриншот: `{save_path}`"
    except Exception as e:
        return f"⚠️ Ошибка анализа экрана: {e}\n📁 Скриншот: `{save_path}`"


def handle_git_command(cmd: str, params: dict) -> str:
    project_path = get_current_project_path() or os.getcwd()
    git = GitManager(project_path)
    repo = git.find_repo()
    if not repo:
        return "Z: Здесь нет Git-репозитория."
    git.repo_path = repo

    args = params.get("args", "")

    try:
        _audit_git(cmd, args, level="safe")

        if cmd == "status": return git.status()
        if cmd == "diff": return git.diff(file=params.get("file"))
        if cmd == "log": return git.log(n=5)
        if cmd == "branch":
            if params.get("delete") or "-d" in str(params).lower() or "-D" in str(params):
                return "🚫 Удаление ветки запрещено. Сделай вручную в терминале."
            return git.branch()
        if cmd == "commit":
            msg = params.get("message")
            if msg:
                if "reset --hard" in msg.lower():
                    return "🚫 Не могу выполнить эту команду."
                git.add()
                return git.commit(msg)
            return git.auto_commit()
        if cmd == "stash":
            action = params.get("action", "save")
            if action in ("drop", "clear"):
                return "🚫 Удаление stash запрещено."
            return git.stash(action=action)
        if cmd == "add":
            return git.add()
        if cmd == "push":
            return "🚫 Push отключён. Сделай вручную в терминале."
        if cmd == "pull":
            return git.pull() if hasattr(git, "pull") else "⚠️ Команда pull не поддерживается."
        if cmd == "fetch":
            return git.fetch() if hasattr(git, "fetch") else "⚠️ Команда fetch не поддерживается."

        return f"Z: Команда `git {cmd}` не поддерживается."
    except GitSafetyError as e:
        return f"Z: {e}"
    except Exception as e:
        _audit_error(str(e), f"git {cmd}")
        return f"Z: Ошибка Git — {e}"


def handle_reminder(minutes: int, text: str) -> str:
    if minutes is None or text is None:
        return "⚠️ Я не поняла, какое напоминание установить."
    result = add_reminder(text, minutes)
    save_message("assistant", result)
    return result


# ================================================================
#  УПРАВЛЕНИЕ БРАУЗЕРОМ
# ================================================================

def handle_browser_action(action: str, data: Dict) -> str:
    """Обрабатывает действия браузера."""
    if not HAS_BROWSER:
        return "⚠️ Модуль browser_control не подключён.\n💡 Установи pyautogui и pygetwindow: pip install pyautogui pygetwindow"

    try:
        b = get_browser()
    except Exception as e:
        return f"⚠️ Ошибка браузера: {e}"

    try:
        if action == "open":
            site = data.get("site", "")
            return b.open_site(site)

        if action == "open_url":
            url = data.get("url", "")
            browser = data.get("browser")
            if b.open_url(url, browser=browser):
                return f"✅ Открываю {url}"
            return f"⚠️ Не удалось открыть {url}"

        if action == "open_multiple":
            sites = data.get("sites", [])
            return b.open_multiple(sites)

        if action == "search":
            query = data.get("query", "")
            engine = data.get("engine", "google")
            return b.search(query, engine=engine)

        if action == "new_tab":
            return b.new_tab()

        if action == "close_tab":
            return b.close_tab()

        if action == "next_tab":
            return b.next_tab()

        if action == "prev_tab":
            return b.prev_tab()

        if action == "reopen_tab":
            return b.reopen_tab()

        if action == "refresh":
            return b.refresh()

        if action == "back":
            return b.go_back()

        if action == "forward":
            return b.go_forward()

        if action == "home":
            return b.go_home()

        if action == "stop":
            return b.stop_loading()

        if action == "fullscreen":
            return b.fullscreen()

        if action == "devtools":
            return b.open_devtools()

        if action == "copy_url":
            return b.copy_url()

        if action == "add_bookmark":
            name = data.get("name", "")
            url = data.get("url")
            return b.add_bookmark(name, url)

        if action == "remove_bookmark":
            name = data.get("name", "")
            return b.remove_bookmark(name)

        if action == "list_bookmarks":
            return b.list_bookmarks()

        if action == "open_bookmark":
            name = data.get("name", "")
            return b.open_bookmark(name)

        if action == "list_windows":
            return b.list_windows()

        if action == "info":
            return b.info_browsers()

        if action == "change":
            b.clear_preferred_browser()
            return "🔄 Выбор браузера сброшен. При следующей команде я спрошу заново.\n\n" + b.info_browsers()
    except Exception as e:
        log_error(f"Ошибка действия браузера {action}: {e}")
        return f"⚠️ Ошибка браузера: {e}"

    return "⚠️ Неизвестное действие браузера."


def handle_browser_choice(text: str) -> Optional[str]:
    """Обрабатывает ответ пользователя на выбор браузера."""
    if not HAS_BROWSER:
        return None
    try:
        b = get_browser()
        return b.handle_choice(text)
    except Exception as e:
        log_error(f"Ошибка выбора браузера: {e}")
        return None


# ================================================================
#  УПРАВЛЕНИЕ ПК
# ================================================================

# Русские алиасы приложений
APP_ALIASES = {
    "браузер": "browser",
    "хром": "chrome",
    "гугл": "chrome",
    "хром браузер": "chrome",
    "фаерфокс": "firefox",
    "лиса": "firefox",
    "край": "edge",
    "эдж": "edge",
    "стим": "steam",
    "дискорд": "discord",
    "телеграм": "telegram",
    "блокнот": "notepad",
    "калькулятор": "calc",
    "проводник": "explorer",
    "проводник windows": "explorer",
    "диспетчер": "taskmgr",
    "диспетчер задач": "taskmgr",
    "терминал": "terminal",
    "командная строка": "cmd",
    "powershell": "powershell",
    "пауэршелл": "powershell",
    "код": "code",
    "vs code": "code",
    "вс код": "code",
    "спотифай": "spotify",
    "влц": "vlc",
    "зум": "zoom",
    "зум конференция": "zoom",
    "скайп": "skype",
    "ворд": "word",
    "эксель": "excel",
    "паверпоинт": "powerpoint",
    "photoshop": "photoshop",
    "фотошоп": "photoshop",
    "figma": "figma",
    "фигма": "figma",
    "блендер": "blender",
}


def _resolve_app(name: str) -> str:
    if not name:
        return name
    low = name.strip().lower()
    return APP_ALIASES.get(low, low)


def handle_app_open(name: str) -> str:
    if not HAS_PC:
        return "⚠️ Модуль pc_control не подключён."
    if not name or not name.strip():
        return "⚠️ Не поняла, какое приложение открыть."
    name = _resolve_app(name)
    return pc_control.open_app(name)


def handle_app_close(name: str) -> str:
    if not HAS_PC:
        return "⚠️ Модуль pc_control не подключён."
    if not name or not name.strip():
        return "⚠️ Не поняла, какое приложение закрыть."
    name = _resolve_app(name)
    return pc_control.close_app(name)


def handle_app_kill(name: str) -> str:
    if not HAS_PC:
        return "⚠️ Модуль pc_control не подключён."
    if not name or not name.strip():
        return "⚠️ Не поняла, какой процесс убить."
    return pc_control.kill_process(name)


def handle_volume(action: str, level: int = None) -> str:
    if not HAS_PC:
        return "⚠️ Модуль pc_control не подключён."
    if action == "set" and level is not None:
        return pc_control.set_volume(level)
    if action == "get":
        return pc_control.get_volume()
    if action == "mute":
        return pc_control.mute_volume()
    if action == "unmute":
        return pc_control.unmute_volume()
    return "⚠️ Неизвестное действие с громкостью."


def handle_clipboard(action: str, text: str = "") -> str:
    if not HAS_PC:
        return "⚠️ Модуль pc_control не подключён."
    if action == "get":
        return pc_control.get_clipboard()
    if action == "set":
        if not text.strip():
            return "⚠️ Что скопировать?"
        return pc_control.set_clipboard(text)
    return "⚠️ Неизвестное действие."


def handle_ip_info() -> str:
    if not HAS_PC:
        return "⚠️ Модуль pc_control не подключён."
    return pc_control.get_ip_info()


# --- УПРАВЛЕНИЕ ПИТАНИЕМ ---

def handle_power_request(action: str) -> str:
    global PENDING_POWER_ACTION

    labels = {
        "shutdown": "выключить ПК",
        "restart": "перезагрузить ПК",
        "sleep": "усыпить ПК",
        "hibernate": "отправить ПК в гибернацию",
        "lock": "заблокировать ПК",
    }

    PENDING_POWER_ACTION = action
    label = labels.get(action, action)

    return (
        f"⚠️ Ты хочешь **{label}**.\n"
        f"Напиши `да` для подтверждения или `нет` для отмены."
    )


def handle_power_confirm(text: str) -> Optional[str]:
    global PENDING_POWER_ACTION

    if not PENDING_POWER_ACTION:
        return None

    low = text.strip().lower()

    if low in POWER_YES:
        action = PENDING_POWER_ACTION
        PENDING_POWER_ACTION = None

        result = None
        if action == "shutdown":
            result = pc_control.shutdown_pc(delay=30) if HAS_PC else "⚠️ pc_control не подключён"
        elif action == "restart":
            result = pc_control.restart_pc(delay=30) if HAS_PC else "⚠️ pc_control не подключён"
        elif action == "sleep":
            result = pc_control.sleep_pc() if HAS_PC else "⚠️ pc_control не подключён"
        elif action == "hibernate":
            result = pc_control.hibernate_pc() if HAS_PC else "⚠️ pc_control не подключён"
        elif action == "lock":
            result = pc_control.lock_pc() if HAS_PC else "⚠️ pc_control не подключён"

        if HAS_AUDIT:
            try:
                get_audit().log_security(
                    f"power_{action}",
                    f"Подтверждено пользователем: {result}",
                    severity="warning"
                )
            except Exception:
                pass
        return result

    if low in POWER_NO:
        action = PENDING_POWER_ACTION
        PENDING_POWER_ACTION = None
        if HAS_AUDIT:
            try:
                get_audit().log_security("power_cancel", f"Отменено: {action}", severity="info")
            except Exception:
                pass
        return f"✅ Отменено: {action}"

    return None


# ================================================================
#  УМНОЕ ОПРЕДЕЛЕНИЕ КОМАНД
# ================================================================

def detect_command_type(text: str) -> Tuple[str, Dict]:
    """Определяет ТОЛЬКО ЯВНЫЕ команды."""
    text_stripped = text.strip()
    text_lower = text_stripped.lower()

    # 0. ПОДТВЕРЖДЕНИЕ ПИТАНИЯ (в самом начале)
    if PENDING_POWER_ACTION:
        if text_lower in POWER_YES or text_lower in POWER_NO:
            return "power_confirm", {"text": text_lower}

    # 0.1 ВЫБОР БРАУЗЕРА
    if HAS_BROWSER and has_pending_browser_choice():
        if re.match(r"^(\d+|отмена|cancel|нет|no)$", text_lower) or any(
            kw in text_lower for kw in [
                "edge", "chrome", "firefox", "yandex", "opera", "brave",
                "край", "хром", "фаерфокс", "яндекс", "опера",
            ]
        ):
            return "browser_choice", {"text": text_lower}

    # 1. СОЗДАТЕЛЬ
    if is_creator_mode():
        if re.match(r"^(/exit_creator|выход из режима создателя|/creator_exit)\b", text_lower):
            return "creator_exit", {}

    # 2. ПИТАНИЕ
    if re.match(r"^(выключи|отключи)\s+(пк|компьютер|комп|систему)?\s*$", text_lower):
        return "power", {"action": "shutdown"}
    if re.match(r"^(перезагрузи|ребутни|перезапусти)\s+(пк|компьютер|комп|систему)?\s*$", text_lower):
        return "power", {"action": "restart"}
    if re.match(r"^(усыпи|спящий режим|сон)\s*(пк|компьютер|комп)?\s*$", text_lower):
        return "power", {"action": "sleep"}
    if re.match(r"^(гибернация|в гибернацию|hibernation)\s*$", text_lower):
        return "power", {"action": "hibernate"}
    if re.match(r"^(заблокируй|залочь|lock)\s*(пк|компьютер|комп)?\s*$", text_lower):
        return "power", {"action": "lock"}
    if re.match(r"^(отмени|отмена)\s+(выключение|перезагрузку|сон)\s*$", text_lower):
        return "power_cancel", {}

    # 3. ГРОМКОСТЬ
    m = re.match(r"^громкость\s+(\d+)\s*%?\s*$", text_lower)
    if m:
        level = int(m.group(1))
        return "volume", {"action": "set", "level": level}

    if re.match(r"^(выключи|отключи|замьють|mute)\s+(звук|громкость)\s*$", text_lower):
        return "volume", {"action": "mute"}
    if re.match(r"^(включи|верни|размьють|unmute)\s+(звук|громкость)\s*$", text_lower):
        return "volume", {"action": "unmute"}
    if re.match(r"^(какая|покажи|сколько)\s+(громкость|звук)", text_lower):
        return "volume", {"action": "get"}

    # 4. БУФЕР ОБМЕНА
    if re.match(r"^(что|покажи|посмотри)\s+(в\s+)?буфере(\s+обмена)?\s*\??$", text_lower):
        return "clipboard", {"action": "get"}
    if re.match(r"^(скопируй|скопируй в буфер)\s+", text_lower):
        m2 = re.match(r"^(?:скопируй|скопируй в буфер)\s+(.+)", text_stripped, re.IGNORECASE)
        if m2:
            return "clipboard", {"action": "set", "text": m2.group(1)}

    # 5. IP / СЕТЬ
    if re.match(r"^(мой\s+)?(ip|айпи)\s*(адрес)?\s*\??$", text_lower):
        return "ip_info", {}

    # 6. ОТКРОЙ ПРИЛОЖЕНИЕ
    m = re.match(r"^(открой|запусти|open|start)\s+(.+)", text_lower)
    if m:
        app = m.group(2).strip().strip(".!?")
        if not re.match(r"^(файл|папку|папка|file|folder)\b", app):
            # Проверяем: может это сайт?
            if HAS_BROWSER:
                key = app.lower().strip()
                if key in BROWSER_SITES:
                    return "browser", {"action": "open", "site": app}
                if re.match(r"^[\w\-]+\.\w+", key):
                    return "browser", {"action": "open", "site": app}
            return "app_open", {"name": app}

    # 7. ЗАКРОЙ ПРИЛОЖЕНИЕ
    m = re.match(r"^(закрой|заверши|close)\s+(.+)", text_lower)
    if m:
        app = m.group(2).strip().strip(".!?")
        if not re.match(r"^(файл|папку|папка|окно|file|folder|window)\b", app):
            return "app_close", {"name": app}

    # 8. УБЕЙ ПРОЦЕСС
    m = re.match(r"^(убей|прибей|kill|terminate)\s+(.+)", text_lower)
    if m:
        return "app_kill", {"name": m.group(2).strip().strip(".!?")}

    # 9. НАПОМИНАНИЯ
    if re.match(r"^(напомни|напомните|не забудь|remind)\b", text_lower):
        has_time = bool(re.search(r"(через|в)\s+\d+", text_lower)) or bool(re.search(r"\d+\s*(минут|час|сек)", text_lower))
        if has_time:
            minutes, reminder_text = needs_reminder(text)
            if minutes and reminder_text:
                return "reminder", {"minutes": minutes, "text": reminder_text}

    # 10. СТАТУС
    if re.match(r"^(статус системы|покажи статус|/status)\b", text_lower):
        return "status", {}

    # 11. GIT
    if re.match(r"^git\s+", text_lower):
        match = re.match(r"^git\s+([a-z\-]+)", text_lower)
        if match:
            cmd = match.group(1)
            args = text_stripped[len(f"git {cmd}"):].strip()

            if HAS_GIT_GUARD:
                full_command = f"{cmd} {args}".strip()
                level, message = GitGuard.check(full_command)

                if level == DangerLevel.BLOCKED:
                    log_error(f"🚫 GitGuard заблокировал: {full_command}")
                    _audit_git(cmd, args, level="blocked", blocked=True)
                    return "git_blocked", {"message": message}

                if level == DangerLevel.DANGEROUS:
                    _audit_git(cmd, args, level="dangerous")
                    return "git_dangerous", {"message": message, "command": full_command}

            return "git", {"command": cmd, "args": args, "message": None}

    # 12. ФАЙЛЫ
    if re.match(r"^(открой|откройте|open)\s+(файл|папку)\b", text_lower):
        action, detail = needs_file_action(text)
        if action:
            return "file", {"action": action, "detail": detail}

    if re.match(r"^(найди|где)\s+(файл|папку)\b", text_lower):
        action, detail = needs_file_action(text)
        if action:
            return "file", {"action": action, "detail": detail}

    if re.match(r"^(покажи|list)\s+(папку|содержимое)\b", text_lower):
        action, detail = needs_file_action(text)
        if action:
            return "file", {"action": action, "detail": detail}

    # 13. СКРИНШОТ
    if re.match(r"^(сделай скрин|сделай скриншот|посмотри на экран|что на экране|/screenshot)\b", text_lower):
        return "screenshot", {}

    # 14. ПЕРЕВОД
    if re.match(r"^(переведи|translate)\b", text_lower):
        lang, translate_text = needs_translation(text)
        if lang and translate_text:
            return "translation", {"lang": lang, "text": translate_text}

    # 15. RAG
    if re.match(r"^(загрузи документ|прочитай документ|покажи документы|очисти документы)\b", text_lower):
        return "rag", {"command": text}

    # 16. ПОИСК (общий)
    if re.match(r"^(найди в интернете|поищи в интернете|погугли)\b", text_lower):
        return "search", {"query": text}

    # === 17. БРАУЗЕР ===

    # Открыть закладку
    if re.match(r"^открой\s+закладку\s+(.+)", text_lower):
        name = re.match(r"^открой\s+закладку\s+(.+)", text_lower).group(1).strip()
        return "browser", {"action": "open_bookmark", "name": name}

    # Добавить в закладки
    if re.match(r"^добавь\s+в\s+закладки\s+(.+)", text_lower):
        m = re.match(r"^добавь\s+в\s+закладки\s+(.+)", text_stripped, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            return "browser", {"action": "add_bookmark", "name": name}

    # Показать закладки
    if re.match(r"^(покажи|список)\s+закладк", text_lower):
        return "browser", {"action": "list_bookmarks"}

    # Удалить закладку
    if re.match(r"^удали\s+закладку\s+(.+)", text_lower):
        name = re.match(r"^удали\s+закладку\s+(.+)", text_lower).group(1).strip()
        return "browser", {"action": "remove_bookmark", "name": name}

    # Сменить браузер
    if re.match(r"^(смени|поменяй)\s+браузер", text_lower):
        return "browser", {"action": "change"}

    # Список браузеров
    if re.match(r"^(какие|покажи)\s+браузер", text_lower):
        return "browser", {"action": "info"}

    # Открытые окна
    if re.match(r"^(открытые окна|список окон)", text_lower):
        return "browser", {"action": "list_windows"}

    # Вкладки
    if re.match(r"^(новая вкладка|новую вкладку|new tab)", text_lower):
        return "browser", {"action": "new_tab"}

    if re.match(r"^(закрой|заверши)\s+вкладку", text_lower):
        return "browser", {"action": "close_tab"}

    if re.match(r"^(следующая|след\.?)\s+вкладк", text_lower):
        return "browser", {"action": "next_tab"}

    if re.match(r"^(предыдущая|пред\.?)\s+вкладк", text_lower):
        return "browser", {"action": "prev_tab"}

    if re.match(r"^(верни|восстанови)\s+вкладку", text_lower):
        return "browser", {"action": "reopen_tab"}

    # Навигация
    if re.match(r"^обнови\s+(страницу|page)?\s*$", text_lower):
        return "browser", {"action": "refresh"}

    if re.match(r"^назад\s*$", text_lower):
        return "browser", {"action": "back"}

    if re.match(r"^вперёд\s*$", text_lower):
        return "browser", {"action": "forward"}

    if re.match(r"^(на главную|домой|home)\s*$", text_lower):
        return "browser", {"action": "home"}

    if re.match(r"^(останови|стоп|stop)\s*(загрузку)?\s*$", text_lower):
        return "browser", {"action": "stop"}

    if re.match(r"^(полный экран|fullscreen|фуллскрин)", text_lower):
        return "browser", {"action": "fullscreen"}

    if re.match(r"^(devtools|консоль браузера|инструменты разработчика)", text_lower):
        return "browser", {"action": "devtools"}

    if re.match(r"^(скопируй|копируй)\s+(ссылку|url|адрес)", text_lower):
        return "browser", {"action": "copy_url"}

    # Поиск в конкретных поисковиках
    if re.match(r"^(найди|поищи)\s+в\s+(гугле|google)", text_lower):
        query = re.sub(r"^(найди|поищи)\s+в\s+(гугле|google)\s+", "", text_stripped, flags=re.IGNORECASE).strip()
        if query:
            return "browser", {"action": "search", "query": query, "engine": "google"}

    if re.match(r"^(найди|поищи)\s+на\s+(ютубе|youtube)", text_lower):
        query = re.sub(r"^(найди|поищи)\s+на\s+(ютубе|youtube)\s+", "", text_stripped, flags=re.IGNORECASE).strip()
        if query:
            return "browser", {"action": "search", "query": query, "engine": "youtube"}

    if re.match(r"^(найди|поищи)\s+в\s+(яндексе|yandex)", text_lower):
        query = re.sub(r"^(найди|поищи)\s+в\s+(яндексе|yandex)\s+", "", text_stripped, flags=re.IGNORECASE).strip()
        if query:
            return "browser", {"action": "search", "query": query, "engine": "yandex"}

    if re.match(r"^(найди|поищи)\s+в\s+(бинге|bing)", text_lower):
        query = re.sub(r"^(найди|поищи)\s+в\s+(бинге|bing)\s+", "", text_stripped, flags=re.IGNORECASE).strip()
        if query:
            return "browser", {"action": "search", "query": query, "engine": "bing"}

    if re.match(r"^(найди|поищи)\s+в\s+(дак|duckduckgo)", text_lower):
        query = re.sub(r"^(найди|поищи)\s+в\s+(дак|duckduckgo)\s+", "", text_stripped, flags=re.IGNORECASE).strip()
        if query:
            return "browser", {"action": "search", "query": query, "engine": "duckduckgo"}

    return "chat", {}


def execute_command(cmd_type: str, data: Dict, mode: str = "default") -> str:
    """Выполняет команду по её типу."""
    global PENDING_POWER_ACTION

    # Сброс PENDING_POWER_ACTION при любой не-power команде
    if cmd_type not in ("power", "power_confirm", "power_cancel"):
        if PENDING_POWER_ACTION is not None:
            log_info(f"🔓 Сброс PENDING_POWER_ACTION ({PENDING_POWER_ACTION}) из-за команды {cmd_type}")
            PENDING_POWER_ACTION = None

    if cmd_type == "creator_exit":
        if HAS_CREATOR:
            get_creator().deactivate()
        return "👤 Режим создателя деактивирован. Общаемся как обычно."

    # === ВЫБОР БРАУЗЕРА ===
    if cmd_type == "browser_choice":
        result = handle_browser_choice(data.get("text", ""))
        if result:
            return result
        return "⚠️ Не понял выбор. Напиши номер или название браузера."

    # === БРАУЗЕР ===
    if cmd_type == "browser":
        return handle_browser_action(data.get("action", ""), data)

    # === ПИТАНИЕ ===
    if cmd_type == "power":
        return handle_power_request(data.get("action", ""))

    if cmd_type == "power_confirm":
        result = handle_power_confirm(data.get("text", ""))
        if result:
            return result
        return "⚠️ Не понял ответа. Напиши `да` или `нет`."

    if cmd_type == "power_cancel":
        if HAS_PC:
            return pc_control.cancel_shutdown()
        return "⚠️ pc_control не подключён"

    # === ГРОМКОСТЬ ===
    if cmd_type == "volume":
        return handle_volume(data.get("action", "get"), data.get("level"))

    # === БУФЕР ===
    if cmd_type == "clipboard":
        return handle_clipboard(data.get("action", "get"), data.get("text", ""))

    # === IP ===
    if cmd_type == "ip_info":
        return handle_ip_info()

    # === ПРИЛОЖЕНИЯ ===
    if cmd_type == "app_open":
        return handle_app_open(data.get("name", ""))

    if cmd_type == "app_close":
        return handle_app_close(data.get("name", ""))

    if cmd_type == "app_kill":
        return handle_app_kill(data.get("name", ""))

    # === ОСТАЛЬНЫЕ ===
    if cmd_type == "git_blocked":
        return data.get("message", "🚫 Команда заблокирована.")

    if cmd_type == "git_dangerous":
        return data.get("message", "⚠️ Опасная команда.")

    if cmd_type == "reminder":
        return handle_reminder(data.get("minutes", 5), data.get("text", "Напоминание"))

    if cmd_type == "status":
        return get_system_status()

    if cmd_type == "git":
        return handle_git_command(
            data.get("command", ""),
            {"args": data.get("args", ""), "message": data.get("message")}
        )

    if cmd_type == "rag":
        return ask_with_rag(data.get("command", ""))

    if cmd_type == "file":
        return handle_file_action(data.get("action", ""), data.get("detail", ""))

    if cmd_type == "screenshot":
        return handle_screenshot("", mode=mode)

    if cmd_type == "translation":
        return translate(data.get("text", ""), data.get("lang", "ru"))

    if cmd_type == "search":
        return search_web(data.get("query", ""))

    return "⚠️ Неизвестная команда."


# ================================================================
#  ОСНОВНАЯ ФУНКЦИЯ
# ================================================================

def ask_zeta(user_message: str, mode: str = "default") -> Generator[str, None, None]:
    is_safe, cleaned_or_error = validate_input(user_message)
    if not is_safe:
        log_error(f"⚠️ Отклонён запрос: {cleaned_or_error}")
        _audit_error(cleaned_or_error, "validate_input")
        yield cleaned_or_error
        return

    user_message = cleaned_or_error

    _audit_command(user_message, source="widget")

    creator_just_activated = check_creator(user_message)
    if creator_just_activated:
        yield "👑 Режим создателя активирован. Приветствую, Самир!\n\n"

    log_info(f"📩 ЗАПРОС: {user_message[:100]}... (режим: {mode})")

    if not check_ollama():
        log_info("⚠️ Ollama не запущена, пробую запустить...")
        yield "⏳ Запускаю Ollama... Подождите 5 секунд."
        if start_ollama():
            yield "✅ Ollama запущена. Продолжаем..."
        else:
            yield "⚠️ Не удалось запустить Ollama. Запустите вручную: ollama serve"
            return

    save_message("user", user_message)

    if re.search(r"переключи модель на\s+([\w\-.]+)", user_message.lower()):
        match = re.search(r"переключи модель на\s+([\w\-.]+)", user_message.lower())
        yield switch_model(match.group(1))
        return

    # === ОБРАБОТКА ВЫБОРА БРАУЗЕРА ===
    if HAS_BROWSER and has_pending_browser_choice():
        choice_result = handle_browser_choice(user_message)
        if choice_result is not None:
            save_message("assistant", choice_result)
            _audit_command(user_message, source="browser_choice", result=choice_result[:200])
            yield choice_result
            return

    if not creator_just_activated:
        skip_cache = ["покажи", "открой", "найди", "переведи", "напомни", "git",
                      "скрин", "загрузи", "документ", "файл", "громкость", "буфер",
                      "убей", "закрой", "запусти", "выключи", "перезагрузи"]
        if not any(k in user_message.lower() for k in skip_cache):
            cached = get_cached_response(user_message)
            if cached:
                yield cached
                return

    cmd_type, cmd_data = detect_command_type(user_message)

    if cmd_type != "chat":
        log_info(f"🔧 ВЫПОЛНЯЮ КОМАНДУ: {cmd_type}")
        result = execute_command(cmd_type, cmd_data, mode=mode)
        _audit_command(user_message, source=f"command:{cmd_type}", result=result[:200] if result else None)
        save_message("assistant", result)
        yield result
        return

    # === ОБЫЧНЫЙ ЧАТ ===
    log_info("💬 ЧАТ → отправляю в модель")

    history = get_history_smart(limit=20, max_tokens=4000)
    summarized = summarize_history(get_history(limit=30))
    facts = get_facts()
    facts_text = "\n".join([f"- {f['content']}" for f in facts]) if facts else ""

    web_info = ""
    if needs_search(user_message):
        try:
            search_result = search_web(user_message)
            if "ничего не найдено" not in search_result and "⚠️" not in search_result:
                web_info = search_result
            else:
                web_info = "Интернет не дал результатов. Отвечай на основе своих знаний."
        except Exception:
            web_info = ""
            log_error("Ошибка поиска в интернете")

    is_code = bool(re.search(
        r"(напиши|создай|добавь|исправь|обнови)\s+(код|функцию|файл|класс|метод|скрипт)",
        user_message.lower()
    ))

    model = get_model()
    project_path = get_current_project_path()

    if is_code:
        prompt = build_code_prompt(user_message, history, facts_text, project_path)
    else:
        prompt = build_system_prompt(facts_text, web_info, mode)

        if summarized:
            prompt += summarized

        if history:
            prompt += "=== ИСТОРИЯ ===\n"
            for m in history:
                role = "Пользователь" if m["role"] == "user" else "Zeta"
                prompt += f"{role}: {m['content']}\n"
            prompt += "\n"

        prompt += f"=== НОВЫЙ ВОПРОС ===\nПользователь: {user_message}\nZeta:"

    try:
        temperature = get_dynamic_temperature(user_message)

        if should_think_out_loud(user_message):
            prompt += "\n\n[Сначала подумай шаг за шагом, потом дай краткий ответ.]"

        response = requests.post(
            OLLAMA_URL,
            json={
                "model": model,
                "prompt": prompt,
                "stream": True,
                "temperature": temperature,
                "num_predict": 4096,
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

        full_answer = full_answer.strip()

        bad_phrases = [
            "Я не нашла информации по вашему запросу",
            "Я не нашла информацию",
            "Я не нашла данных",
        ]
        for phrase in bad_phrases:
            if phrase in full_answer and len(full_answer) > len(phrase) + 50:
                full_answer = re.sub(
                    rf"{re.escape(phrase)}.*?($|\n)",
                    "", full_answer, flags=re.DOTALL
                ).strip()

        full_answer = sanitize_response(full_answer)
        extract_and_save_fact(user_message)

        if is_code and full_answer:
            processed = process_code_in_answer(full_answer, user_message)
            if processed != full_answer:
                diff = processed[len(full_answer):] if processed.startswith(full_answer) else processed
                if diff.strip():
                    yield "\n" + diff
            full_answer = processed

        if not creator_just_activated:
            skip_cache = ["покажи", "открой", "найди", "переведи", "напомни", "git",
                          "скрин", "загрузи", "документ", "файл", "громкость", "буфер"]
            if not any(k in user_message.lower() for k in skip_cache):
                save_cached_response(user_message, full_answer)

        save_message("assistant", full_answer)
        log_statistics()
        log_info(f"✅ ОТВЕТ: {full_answer[:100]}...")

    except requests.exceptions.ConnectionError:
        log_error("❌ Ollama не запущена")
        _audit_error("Ollama не запущена", "ask_zeta")
        yield "⚠️ Ollama не запущена. Запустите: ollama serve"
    except requests.exceptions.Timeout:
        log_error("❌ Таймаут Ollama")
        _audit_error("Таймаут Ollama", "ask_zeta")
        yield "⚠️ Ollama думает слишком долго. Попробуйте ещё раз."
    except Exception as e:
        log_error(f"❌ Ошибка: {e}")
        _audit_error(str(e), "ask_zeta")
        yield f"⚠️ Ошибка: {str(e)}"


def ask_zeta_sync(user_message: str, mode: str = "default") -> str:
    return "".join(ask_zeta(user_message, mode=mode))