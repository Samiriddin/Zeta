# -*- coding: utf-8 -*-
"""
Конфиг Zeta. Чистый модуль — не импортирует memory.py при загрузке.
Все настройки читаются лениво (при вызове), а не при импорте.

ИСПРАВЛЕНО (2026-09-21):
    - ai_model: qwen2.5:7b → zeta-universal
    - DEFAULTS дополнен всеми ключами из ui/settings.py
    - SIZE_MAP синхронизирован с ui/widget.py (единый источник)
    - ensure_dirs создаёт все нужные папки
    - validate_config() — проверка целостности
    - get_config_bool: + «нет», «no», «off»
    - get_config_list() — для списков
    - reset_all_configs(keep=...) — можно сохранить ключи
    - OLLAMA_PATH: fallback через where ollama
    - PERSONALITY вынесен отдельно от DEFAULTS
"""

import os
import subprocess
from typing import Optional, Tuple, Dict, Any, List


# ========== ЛИЧНОСТЬ ZETA (константа) ==========

PERSONALITY = (
    "Ты — Z (Зета). ИИ-помощница с характером.\n"
    "Стиль: холодная, саркастичная, прямолинейная.\n"
    "Вдохновлена V из Murder Drones.\n"
    "Умна, не терпит глупости, но всегда помогает создателю.\n"
    "Обращаешься к пользователю на 'вы'.\n"
    "Создатель — Samriddin (Самир).\n"
    "Отвечай только на русском. Будь лаконичной, но точной.\n"
    "Никогда не используй оскорбления, грубость или токсичность."
)


# ========== ДЕФОЛТЫ ==========

DEFAULTS: Dict[str, str] = {
    # --- Интерфейс ---
    "theme": "dark",
    "voice_enabled": "true",
    "widget_size": "M",
    "widget_position": "bottom-right",
    "avatar_path": "",
    "widget_opacity": "1.0",
    "widget_x": "",
    "widget_y": "",
    "zeta_name": "Z",

    # --- Голос ---
    "tts_voice": "ru-RU-SvetlanaNeural",
    "tts_speed": "5",
    "wake_word_enabled": "false",
    "stt_duration": "5",

    # --- ИИ ---
    "ai_model": "zeta-universal",       # ИСПРАВЛЕНО: было qwen2.5:7b
    "context_tokens": "2000",
    "ai_temperature": "0.7",
    "max_tokens": "1024",

    # --- Уведомления ---
    "smart_notifications": "true",
    "cpu_threshold": "80",
    "ram_threshold": "85",
    "disk_threshold": "90",
    "notif_interval": "30",

    # --- Анимации ---
    "animations_enabled": "true",
    "anim_speed": "300",
    "anim_effect": "Fade In",

    # --- Безопасность ---
    "safety_enabled": "true",
    "git_protection_enabled": "true",
    "max_query_length": "2000",

    # --- RAG ---
    "rag_enabled": "true",
    "rag_max_results": "5",

    # --- Проект ---
    "project_path": "D:\\Zeta",
    "auto_focus": "true",
    "last_run": "",
}


# ========== РАЗМЕРЫ ВИДЖЕТА ==========
# ИСПРАВЛЕНО: синхронизировано с ui/widget.py (единый источник правды)

SIZE_MAP: Dict[str, Tuple[int, int]] = {
    "S": (400, 550),
    "M": (500, 700),
    "L": (650, 900),
    "XL": (800, 1100),
}


# ========== ПУТИ ==========

DB_PATH: str = "data/zeta.db"
CACHE_DB: str = "data/zeta_cache.db"
LOG_FILE: str = "data/zeta.log"
RAG_DB: str = "data/rag.db"
RAG_VECTORS: str = "data/rag_vectors"
TTS_CACHE_DB: str = "data/tts_cache.db"
SCREENSHOT_DIR: str = "data/screenshots"

PROJECT_ROOT: str = os.path.dirname(os.path.abspath(__file__))
GENERATED_DIR: str = os.path.join(PROJECT_ROOT, "generated")
DATA_DIR: str = os.path.join(PROJECT_ROOT, "data")


# ========== OLLAMA ==========

OLLAMA_URL: str = "http://localhost:11434/api/generate"
OLLAMA_TAGS_URL: str = "http://localhost:11434/api/tags"
OLLAMA_MODELS: str = "D:\\ollama_models"

# ИСПРАВЛЕНО: OLLAMA_PATH с fallback
_OLLAMA_PATH_DEFAULT: str = r"C:\Users\samir\AppData\Local\Programs\Ollama\ollama.exe"
_ollama_path_cache: Optional[str] = None


def get_ollama_path() -> Optional[str]:
    """
    ИСПРАВЛЕНО: ищет ollama по всем возможным путям.
    Кэширует результат.
    """
    global _ollama_path_cache
    if _ollama_path_cache and os.path.exists(_ollama_path_cache):
        return _ollama_path_cache

    # 1. Стандартный
    if os.path.exists(_OLLAMA_PATH_DEFAULT):
        _ollama_path_cache = _OLLAMA_PATH_DEFAULT
        return _ollama_path_cache

    # 2. Через where / which
    try:
        cmd = "where" if os.name == "nt" else "which"
        result = subprocess.run(
            [cmd, "ollama"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if result.returncode == 0:
            path = result.stdout.strip().split("\n")[0].strip()
            if path and os.path.exists(path):
                _ollama_path_cache = path
                return path
    except Exception:
        pass

    # 3. Кандидаты
    candidates = [
        os.path.expanduser(r"~\AppData\Local\Programs\Ollama\ollama.exe"),
        r"C:\Program Files\Ollama\ollama.exe",
        r"C:\Program Files (x86)\Ollama\ollama.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            _ollama_path_cache = c
            return c

    return None


# Обратная совместимость: OLLAMA_PATH как строка
OLLAMA_PATH: str = _OLLAMA_PATH_DEFAULT


# ========== API КЛЮЧИ (ОПЦИОНАЛЬНО) ==========

CLAUDE_API_KEY: Optional[str] = os.getenv("CLAUDE_API_KEY", None)
OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY", None)


# ========== ФУНКЦИИ ЧТЕНИЯ ==========

def get_config(key: str) -> str:
    """
    Ленивое чтение: обращается к БД только при вызове.
    Если БД недоступна или ключ не найден — возвращает дефолт.
    """
    # ИСПРАВЛЕНО: пустой key → возвращаем пустую строку
    if not key:
        return ""

    try:
        from core.memory import get_setting
        value = get_setting(key, "")
        if value:
            return value
    except Exception:
        pass

    return DEFAULTS.get(key, "")


def get_config_int(key: str) -> int:
    """Возвращает настройку как int."""
    try:
        return int(get_config(key))
    except (ValueError, TypeError):
        try:
            return int(DEFAULTS.get(key, 0))
        except (ValueError, TypeError):
            return 0


def get_config_float(key: str) -> float:
    """Возвращает настройку как float."""
    try:
        return float(get_config(key))
    except (ValueError, TypeError):
        try:
            return float(DEFAULTS.get(key, 0.0))
        except (ValueError, TypeError):
            return 0.0


def get_config_bool(key: str) -> bool:
    """
    Возвращает настройку как bool.
    ИСПРАВЛЕНО: добавлены «нет», «no», «off».
    """
    value = get_config(key).lower().strip()

    # True
    if value in ("true", "1", "yes", "on", "да", "y", "вкл"):
        return True

    # False
    if value in ("false", "0", "no", "off", "нет", "n", "выкл", ""):
        return False

    # Неизвестное — False (безопаснее, чем True)
    return False


def get_config_list(key: str, separator: str = ",") -> List[str]:
    """
    ИСПРАВЛЕНО: возвращает настройку как список строк.
    Пример: "a,b,c" → ["a", "b", "c"]
    """
    value = get_config(key)
    if not value:
        return []
    return [item.strip() for item in value.split(separator) if item.strip()]


# ========== ХЕЛПЕРЫ ==========

def get_widget_size() -> Tuple[int, int]:
    """Возвращает размер виджета."""
    size = get_config("widget_size")
    return SIZE_MAP.get(size, SIZE_MAP["M"])


def get_personality() -> str:
    """
    Возвращает личность Zeta.
    ИСПРАВЛЕНО: берём из БД, если есть, иначе — константа.
    """
    db_value = get_config("personality")
    if db_value:
        return db_value
    return PERSONALITY


def get_model_name() -> str:
    """Возвращает имя модели ИИ."""
    return get_config("ai_model")


def get_voice() -> str:
    """Возвращает код голоса TTS."""
    return get_config("tts_voice")


def get_voice_speed() -> int:
    """Возвращает скорость речи."""
    return get_config_int("tts_speed")


def get_project_path() -> str:
    """Возвращает путь к проекту."""
    return get_config("project_path")


def is_voice_enabled() -> bool:
    """Проверяет, включён ли голос."""
    return get_config_bool("voice_enabled")


def is_smart_notifications_enabled() -> bool:
    """Проверяет, включены ли умные уведомления."""
    return get_config_bool("smart_notifications")


def is_dark_theme() -> bool:
    """Проверяет, включена ли тёмная тема."""
    return get_config("theme") == "dark"


def get_all_configs() -> Dict[str, str]:
    """
    Возвращает все настройки (дефолты + из БД).
    """
    configs = DEFAULTS.copy()
    try:
        from core.memory import get_settings
        db_configs = get_settings()
        configs.update(db_configs)
    except Exception:
        pass
    return configs


# ========== СБРОС ==========

def reset_config(key: str) -> None:
    """Сбрасывает настройку к дефолту."""
    if not key:
        return
    try:
        from core.memory import delete_setting
        delete_setting(key)
    except Exception:
        pass


def reset_all_configs(keep: Optional[List[str]] = None) -> None:
    """
    Сбрасывает все настройки к дефолтам.
    ИСПРАВЛЕНО: параметр keep — что НЕ удалять.
    Пример: reset_all_configs(keep=["theme", "tts_voice"])
    """
    keep_set = set(keep or [])
    try:
        from core.memory import get_settings, delete_setting
        for key in get_settings().keys():
            if key not in keep_set:
                delete_setting(key)
    except Exception:
        pass


# ========== ДИРЕКТОРИИ ==========

def ensure_dirs() -> None:
    """
    ИСПРАВЛЕНО: создаёт все нужные папки (как main.init_project).
    """
    dirs = [
        DATA_DIR,
        os.path.join(DATA_DIR, "avatar"),
        os.path.join(DATA_DIR, "backups"),
        os.path.join(DATA_DIR, "backups", "auto"),
        os.path.join(DATA_DIR, "backups", "manual"),
        os.path.join(DATA_DIR, "security"),
        os.path.join(DATA_DIR, "audit"),
        os.path.join(DATA_DIR, "screenshots"),
        os.path.join(DATA_DIR, "images"),
        GENERATED_DIR,
        os.path.join(PROJECT_ROOT, "logs"),
    ]
    for d in dirs:
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass


# ========== ВАЛИДАЦИЯ ==========

def validate_config() -> Dict[str, Any]:
    """
    ИСПРАВЛЕНО: проверяет целостность конфига.
    Возвращает отчёт: {ok, missing_in_defaults, unknown_in_db, errors}
    """
    report: Dict[str, Any] = {
        "ok": True,
        "missing_in_defaults": [],
        "unknown_in_db": [],
        "errors": [],
    }

    # Проверяем, что все ключи из БД есть в DEFAULTS
    try:
        from core.memory import get_settings
        db_keys = set(get_settings().keys())
        default_keys = set(DEFAULTS.keys())

        missing = db_keys - default_keys
        if missing:
            report["missing_in_defaults"] = sorted(missing)
            report["ok"] = False

        unknown = db_keys - default_keys
        report["unknown_in_db"] = sorted(unknown)

    except Exception as e:
        report["errors"].append(f"Ошибка чтения настроек: {e}")
        report["ok"] = False

    # Проверяем, что все типы корректны
    try:
        int(DEFAULTS.get("tts_speed", "0"))
    except (ValueError, TypeError):
        report["errors"].append("DEFAULTS['tts_speed'] не число")
        report["ok"] = False

    try:
        float(DEFAULTS.get("ai_temperature", "0"))
    except (ValueError, TypeError):
        report["errors"].append("DEFAULTS['ai_temperature'] не число")
        report["ok"] = False

    return report


# ========== ИНИЦИАЛИЗАЦИЯ ==========

# Создаём директории при импорте
ensure_dirs()


# ========== ТЕСТ ==========
if __name__ == "__main__":
    print("🧪 Тест config.py\n")

    print("📝 Тест 1: Чтение настроек")
    print(f"Тема: {get_config('theme')}")
    print(f"Голос: {get_config('tts_voice')}")
    print(f"Модель: {get_config('ai_model')}")
    print(f"Размер виджета: {get_widget_size()}")
    print(f"Личность: {get_personality()[:100]}...")
    print("-" * 40)

    print("📝 Тест 2: get_config_int")
    print(f"Скорость речи: {get_config_int('tts_speed')}")
    print(f"Макс. токенов: {get_config_int('max_tokens')}")
    print("-" * 40)

    print("📝 Тест 3: get_config_bool")
    print(f"Голос включён: {is_voice_enabled()}")
    print(f"Умные уведомления: {is_smart_notifications_enabled()}")
    print("-" * 40)

    print("📝 Тест 4: get_config_list")
    # Проверка на примере — обычно списки не хранятся в настройках
    print(f"Пустой список: {get_config_list('nonexistent')}")
    print("-" * 40)

    print("📝 Тест 5: Все настройки")
    all_configs = get_all_configs()
    print(f"Всего ключей: {len(all_configs)}")
    for key, value in list(all_configs.items())[:10]:
        print(f"  {key}: {value}")
    print("-" * 40)

    print("📝 Тест 6: Пути")
    print(f"Корень проекта: {PROJECT_ROOT}")
    print(f"Папка data: {DATA_DIR}")
    print(f"Папка generated: {GENERATED_DIR}")
    print(f"Ollama: {get_ollama_path()}")
    print("-" * 40)

    print("📝 Тест 7: Валидация конфига")
    report = validate_config()
    print(f"Статус: {'✅ OK' if report['ok'] else '⚠️ Есть проблемы'}")
    if report['missing_in_defaults']:
        print(f"Отсутствуют в DEFAULTS: {report['missing_in_defaults']}")
    if report['errors']:
        print(f"Ошибки: {report['errors']}")
    print("-" * 40)

    print("\n✅ Тесты завершены!")