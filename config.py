# -*- coding: utf-8 -*-
"""
Конфиг Zeta. Чистый модуль — не импортирует memory.py.
Все настройки читаются лениво (при вызове), а не при импорте.
"""

import os
from typing import Optional, Tuple, Dict, Any

# ========== ДЕФОЛТЫ ==========

DEFAULTS: Dict[str, str] = {
    # Интерфейс
    "theme": "dark",
    "voice_enabled": "true",
    "widget_size": "M",
    "widget_position": "bottom-right",
    "avatar_path": "",
    "widget_opacity": "1.0",
    "zeta_name": "Z",

    # Голос
    "tts_voice": "ru-RU-SvetlanaNeural",
    "tts_speed": "5",

    # ИИ
    "ai_model": "qwen2.5:7b",
    "context_tokens": "2000",
    "ai_temperature": "0.7",
    "max_tokens": "1024",

    # Уведомления
    "smart_notifications": "true",
    "cpu_threshold": "80",
    "ram_threshold": "85",
    "disk_threshold": "90",
    "notif_interval": "30",

    # Проект
    "project_path": "D:\\Zeta",

    # Личность Zeta
    "personality": (
        "Ты — Z (Зета). ИИ-помощница с характером.\n"
        "Стиль: холодная, саркастичная, прямолинейная.\n"
        "Вдохновлена V из Murder Drones.\n"
        "Умна, не терпит глупости, но всегда помогает создателю.\n"
        "Обращаешься к пользователю на 'вы'.\n"
        "Создатель — Samriddin (Самир).\n"
        "Отвечай только на русском. Будь лаконичной, но точной.\n"
        "Никогда не используй оскорбления, грубость или токсичность."
    ),
}

# ========== РАЗМЕРЫ ВИДЖЕТА ==========

SIZE_MAP: Dict[str, Tuple[int, int]] = {
    "S": (280, 400),
    "M": (350, 500),
    "L": (420, 600),
    "XL": (500, 650),
}

# ========== ПУТИ ==========

DB_PATH: str = "data/zeta.db"
CACHE_DB: str = "data/zeta_cache.db"
LOG_FILE: str = "data/zeta.log"
RAG_DB: str = "data/rag.db"
TTS_CACHE_DB: str = "data/tts_cache.db"

PROJECT_ROOT: str = os.path.dirname(os.path.abspath(__file__))
GENERATED_DIR: str = os.path.join(PROJECT_ROOT, "generated")
DATA_DIR: str = os.path.join(PROJECT_ROOT, "data")

# ========== OLLAMA ==========

OLLAMA_URL: str = "http://localhost:11434/api/generate"
OLLAMA_TAGS_URL: str = "http://localhost:11434/api/tags"
OLLAMA_MODELS: str = "D:\\ollama_models"
OLLAMA_PATH: str = r"C:\Users\samir\AppData\Local\Programs\Ollama\ollama.exe"

# ========== API КЛЮЧИ (ОПЦИОНАЛЬНО) ==========

CLAUDE_API_KEY: Optional[str] = os.getenv("CLAUDE_API_KEY", None)
OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY", None)

# ========== ФУНКЦИИ ==========

def get_config(key: str) -> str:
    """
    Ленивое чтение: обращается к БД только при вызове.
    Если БД недоступна или ключ не найден — возвращает дефолт.
    """
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
    """Возвращает настройку как bool."""
    value = get_config(key).lower()
    return value in ("true", "1", "yes", "on", "да", "y")


def get_widget_size() -> Tuple[int, int]:
    """Возвращает размер виджета."""
    size = get_config("widget_size")
    return SIZE_MAP.get(size, SIZE_MAP["M"])


def get_personality() -> str:
    """Возвращает личность Zeta."""
    return get_config("personality")


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


def reset_config(key: str) -> None:
    """Сбрасывает настройку к дефолту."""
    try:
        from core.memory import delete_setting
        delete_setting(key)
    except Exception:
        pass


def reset_all_configs() -> None:
    """Сбрасывает все настройки к дефолтам."""
    try:
        from core.memory import get_settings, delete_setting
        for key in get_settings().keys():
            delete_setting(key)
    except Exception:
        pass


def ensure_dirs() -> None:
    """Создаёт все необходимые директории."""
    dirs = [DATA_DIR, GENERATED_DIR, os.path.join(DATA_DIR, "avatar")]
    for d in dirs:
        os.makedirs(d, exist_ok=True)


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

    print("📝 Тест 4: Все настройки")
    all_configs = get_all_configs()
    for key, value in list(all_configs.items())[:10]:
        print(f"  {key}: {value}")
    print("-" * 40)

    print("📝 Тест 5: Пути")
    print(f"Корень проекта: {PROJECT_ROOT}")
    print(f"Папка data: {DATA_DIR}")
    print(f"Папка generated: {GENERATED_DIR}")

    print("\n✅ Тесты завершены!")