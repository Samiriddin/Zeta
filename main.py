# -*- coding: utf-8 -*-
"""
Главный файл запуска Zeta.
Обрабатывает: автозапуск Ollama, инициализацию БД,
горячие клавиши, системный трей, автообновление.
"""

import sys
import time
import subprocess
import os
import threading
import logging
import signal
from typing import Optional
from datetime import datetime

import requests

# Принудительный вывод в UTF-8 для Windows-терминала
if sys.stdout.encoding != 'utf-8':
    sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
    sys.stderr = open(sys.stderr.fileno(), mode='w', encoding='utf-8', buffering=1)

print("🚀 Запуск Zeta...")

# ========== ЛОГИРОВАНИЕ ==========

LOG_FILE = "data/zeta.log"
os.makedirs("data", exist_ok=True)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)


def log_info(msg: str) -> None:
    print(f"ℹ️ {msg}")
    logging.info(msg)


def log_error(msg: str) -> None:
    print(f"❌ {msg}")
    logging.error(msg)


def log_success(msg: str) -> None:
    print(f"✅ {msg}")
    logging.info(msg)


# ========== КОНСТАНТЫ ==========

OLLAMA_PATH = r"C:\Users\samir\AppData\Local\Programs\Ollama\ollama.exe"
OLLAMA_MODELS_DIR = r"D:\ollama_models"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"

TIMEOUT_CHECK = 2
TIMEOUT_START = 5
MAX_ATTEMPTS = 30
MODEL_PRELOAD_TIMEOUT = 180

# Модели для предзагрузки (в порядке приоритета)
MODELS_TO_PRELOAD = [
    "zeta-universal",
    "llava:latest",
]

# Версия
VERSION = "4.0"
BUILD_DATE = "26 августа 2026"


# ========== ПРОВЕРКА OLLAMA ==========

def check_ollama() -> bool:
    """Проверяет, запущена ли Ollama."""
    try:
        r = requests.get(OLLAMA_TAGS_URL, timeout=TIMEOUT_CHECK)
        return r.status_code == 200
    except Exception:
        return False


def check_ollama_model(model: str) -> bool:
    """Проверяет, загружена ли модель."""
    try:
        r = requests.get(OLLAMA_TAGS_URL, timeout=TIMEOUT_CHECK)
        if r.status_code == 200:
            data = r.json()
            for m in data.get("models", []):
                if m.get("name", "") == model:
                    return True
    except Exception:
        pass
    return False


def get_ollama_models() -> list:
    """Возвращает список установленных моделей."""
    try:
        r = requests.get(OLLAMA_TAGS_URL, timeout=TIMEOUT_CHECK)
        if r.status_code == 200:
            data = r.json()
            return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        pass
    return []


# ========== ЗАПУСК OLLAMA ==========

def start_ollama() -> bool:
    """Запускает Ollama в фоне."""
    try:
        if not os.path.exists(OLLAMA_PATH):
            log_error(f"⚠️ Ollama не найден по пути: {OLLAMA_PATH}")
            log_error("   Скачайте с https://ollama.ai/ и установите")
            return False

        env = os.environ.copy()
        env["OLLAMA_MODELS"] = OLLAMA_MODELS_DIR

        os.makedirs(OLLAMA_MODELS_DIR, exist_ok=True)

        subprocess.Popen(
            [OLLAMA_PATH, "serve"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return True
    except Exception as e:
        log_error(f"⚠️ Не удалось запустить Ollama: {e}")
        return False


def ensure_ollama() -> bool:
    """
    Обеспечивает запуск Ollama.
    Возвращает True если успешно.
    """
    log_info("🔌 Проверка Ollama...")

    if check_ollama():
        log_success("Ollama уже запущена")
        return True

    log_info("⏳ Пробуем запустить Ollama...")

    if not start_ollama():
        log_error("⚠️ Не удалось запустить Ollama")
        return False

    for attempt in range(MAX_ATTEMPTS):
        if check_ollama():
            log_success(f"Ollama запущена (попытка {attempt + 1})")
            return True
        print(f"⏳ Ожидание Ollama... ({attempt + 1}/{MAX_ATTEMPTS})")
        time.sleep(TIMEOUT_START)

    log_error("⚠️ Не удалось запустить Ollama.")
    log_error("⚠️ Запустите вручную:")
    log_error(f"   $env:OLLAMA_MODELS='{OLLAMA_MODELS_DIR}'; ollama serve")
    log_error("⚠️ Zeta запустится, но ИИ не будет работать.")
    return False


# ========== ПРЕДЗАГРУЗКА МОДЕЛЕЙ (ОТКЛЮЧЕНА) ==========

def preload_model(model: str) -> bool:
    """Предзагружает одну модель."""
    try:
        log_info(f"⏳ Прогрев {model}...")
        start = time.time()

        response = requests.post(
            OLLAMA_GENERATE_URL,
            json={
                "model": model,
                "prompt": "test",
                "stream": False,
                "temperature": 0.1,
                "max_tokens": 5
            },
            timeout=MODEL_PRELOAD_TIMEOUT
        )

        elapsed = time.time() - start
        if response.status_code == 200:
            log_success(f"{model} прогрета ({elapsed:.1f}с)")
            return True
        else:
            log_error(f"⚠️ {model} не прогрета (статус {response.status_code})")
            return False

    except requests.exceptions.Timeout:
        log_error(f"⚠️ {model} не прогрета (таймаут {MODEL_PRELOAD_TIMEOUT}с)")
        return False
    except Exception as e:
        log_error(f"⚠️ {model} не прогрета: {e}")
        return False


def preload_models() -> None:
    """Предзагружает все модели в фоне."""
    try:
        if not check_ollama():
            log_error("⚠️ Ollama не запущена, предзагрузка отменена")
            return

        log_info("🔄 Начинаю предзагрузку моделей...")

        for model in MODELS_TO_PRELOAD:
            installed = get_ollama_models()
            found = any(model in m for m in installed)
            
            if not found:
                log_info(f"⏳ Модель {model} не найдена, пробую прогреть через Ollama...")
            
            try:
                preload_model(model)
            except Exception as e:
                log_error(f"⚠️ Ошибка предзагрузки {model}: {e}")

        log_success("Предзагрузка завершена!")

    except Exception as e:
        log_error(f"⚠️ Ошибка предзагрузки: {e}")


# ========== ИНИЦИАЛИЗАЦИЯ ==========

def init_project() -> bool:
    """Инициализирует проект."""
    dirs = [
        "data",
        "data/avatar",
        "data/backups",
        "generated",
        "logs"
    ]
    for d in dirs:
        try:
            os.makedirs(d, exist_ok=True)
        except Exception as e:
            log_error(f"⚠️ Не удалось создать папку {d}: {e}")

    gitignore_path = "data/.gitignore"
    if not os.path.exists(gitignore_path):
        try:
            with open(gitignore_path, "w") as f:
                f.write("# Защита данных Zeta\n")
                f.write("*.db\n")
                f.write("*.log\n")
                f.write("*.cache\n")
                f.write("avatar/*\n")
        except Exception:
            pass

    try:
        from core.memory import init_db
        init_db()
        log_success("База данных инициализирована")
        return True
    except Exception as e:
        log_error(f"⚠️ Ошибка инициализации БД: {e}")
        return False


# ========== ОБРАБОТКА ЗАВЕРШЕНИЯ ==========

def cleanup() -> None:
    """Очистка при завершении."""
    log_info("🔄 Завершение работы...")
    try:
        from core.memory import save_setting
        save_setting("last_run", datetime.now().isoformat())
    except Exception:
        pass
    log_success("До свидания! 👋")


def signal_handler(sig, frame):
    """Обработчик сигналов."""
    cleanup()
    sys.exit(0)


# ========== ОСНОВНОЙ ЗАПУСК ==========

def main():
    """Главная функция."""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    log_info(f"Zeta v{VERSION} ({BUILD_DATE})")

    if not init_project():
        log_error("⚠️ Критическая ошибка инициализации. Выход.")
        sys.exit(1)

    ollama_ready = ensure_ollama()

    if ollama_ready:
        installed = get_ollama_models()
        if not installed:
            log_info("📦 Модели не найдены. Установите:")
            log_info("   ollama pull qwen2.5:7b")
            log_info("   ollama pull llava:latest")

    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt
        from ui.widget import ZetaWidget

        if hasattr(Qt, 'HighDpiScaleFactorRoundingPolicy'):
            QApplication.setHighDpiScaleFactorRoundingPolicy(
                Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
            )
        if hasattr(Qt, 'AA_EnableHighDpiScaling'):
            QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
            QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

        app = QApplication(sys.argv)

        app.setApplicationName("Zeta")
        app.setApplicationDisplayName("Zeta AI Assistant")

        window = ZetaWidget()
        window.show()

        # ⚠️⚠️⚠️ ПРЕДЗАГРУЗКА ОТКЛЮЧЕНА (чтобы Ollama не падала) ⚠️⚠️⚠️
        # if ollama_ready:
        #     threading.Timer(5.0, preload_models).start()

        # Периодическая проверка статуса Ollama
        def check_ollama_loop():
            while True:
                time.sleep(60)
                if not check_ollama():
                    log_error("⚠️ Ollama упала! Попробуйте перезапустить Zeta.")
                    try:
                        from modules.notifications import show_notification
                        show_notification("⚠️ Zeta", "Ollama упала! Перезапустите Zeta.")
                    except Exception:
                        pass

        threading.Thread(target=check_ollama_loop, daemon=True).start()

        sys.exit(app.exec())

    except ImportError as e:
        log_error(f"⚠️ Ошибка импорта PyQt6: {e}")
        log_error("Установите: pip install PyQt6")
        sys.exit(1)
    except Exception as e:
        log_error(f"⚠️ Непредвиденная ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()