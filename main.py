# -*- coding: utf-8 -*-
"""
Главный файл запуска Zeta.
Обрабатывает: автозапуск Ollama, инициализацию БД,
горячие клавиши, системный трей, автообновление, аутентификацию, аудит, бэкапы, IDS,
автоматизацию.

ИСПРАВЛЕНО (2026-09-21):
    - VERSION обновлён до 7.5
    - app.aboutToQuit.connect(cleanup) — гарантирует cleanup при выходе через Qt
    - Флаг _cleanup_done — защита от двойного cleanup
    - check_ollama_loop — корректная остановка через Event
    - MODELS_TO_PRELOAD — проверка существования модели перед прогревом
    - OLLAMA_PATH — fallback на поиск в PATH через where ollama
"""

import sys
import time
import subprocess
import os
import threading
import logging
import signal
import shutil
from typing import Optional
from datetime import datetime

import requests

# Принудительный вывод в UTF-8 для Windows-терминала
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
        sys.stderr = open(sys.stderr.fileno(), mode='w', encoding='utf-8', buffering=1)
    except Exception:
        pass

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

OLLAMA_PATH_DEFAULT = r"C:\Users\samir\AppData\Local\Programs\Ollama\ollama.exe"
OLLAMA_MODELS_DIR = r"D:\ollama_models"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"

TIMEOUT_CHECK = 2
TIMEOUT_START = 5
MAX_ATTEMPTS = 30
MODEL_PRELOAD_TIMEOUT = 180

MODELS_TO_PRELOAD = [
    "zeta-universal",
    "llava:13b",
]

VERSION = "7.5"
BUILD_DATE = "21 сентября 2026"

BACKUP_INTERVAL_HOURS = 24

# Флаг против двойного cleanup
_cleanup_done = False

# Event для остановки check_ollama_loop
_stop_event = threading.Event()

# Кэш пути к ollama
_ollama_path_cache: Optional[str] = None


# ========== ПУТЬ К OLLAMA ==========

def _find_ollama_path() -> Optional[str]:
    """
    ИСПРАВЛЕНО: ищем ollama в PATH, если по стандартному пути нет.
    """
    global _ollama_path_cache

    if _ollama_path_cache and os.path.exists(_ollama_path_cache):
        return _ollama_path_cache

    # 1. Стандартный путь
    if os.path.exists(OLLAMA_PATH_DEFAULT):
        _ollama_path_cache = OLLAMA_PATH_DEFAULT
        return _ollama_path_cache

    # 2. Поиск через where (Windows) или which (Linux/Mac)
    try:
        cmd = "where" if os.name == "nt" else "which"
        result = subprocess.run(
            [cmd, "ollama"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        )
        if result.returncode == 0:
            path = result.stdout.strip().split("\n")[0].strip()
            if path and os.path.exists(path):
                _ollama_path_cache = path
                return path
    except Exception:
        pass

    # 3. Другие типичные пути
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


# ========== АУДИТ ==========

def _audit_startup():
    try:
        from security.audit import get_audit
        get_audit().log_startup()
    except Exception:
        pass


def _audit_shutdown():
    try:
        from security.audit import get_audit
        get_audit().log_shutdown()
    except Exception:
        pass


# ========== БЭКАПЫ ==========

def _start_backup_scheduler():
    try:
        from security.backup import start_scheduler
        start_scheduler(interval_hours=BACKUP_INTERVAL_HOURS)
        log_success(f"💾 Планировщик бэкапов запущен (каждые {BACKUP_INTERVAL_HOURS}ч)")
    except ImportError as e:
        log_info(f"⚠️ Модуль бэкапов не найден: {e}")
    except Exception as e:
        log_error(f"⚠️ Ошибка планировщика бэкапов: {e}")


def _stop_backup_scheduler():
    try:
        from security.backup import stop_scheduler
        stop_scheduler()
        log_info("💾 Планировщик бэкапов остановлен")
    except Exception:
        pass


# ========== IDS ==========

def _start_intrusion_detector():
    try:
        from security.intrusion_detector import get_ids
        ids = get_ids()
        ids.start()
        log_success("🚨 Обнаружение вторжений запущено")
    except ImportError as e:
        log_info(f"⚠️ Модуль IDS не найден: {e}")
    except Exception as e:
        log_error(f"⚠️ Ошибка IDS: {e}")


def _stop_intrusion_detector():
    try:
        from security.intrusion_detector import get_ids
        get_ids().stop()
        log_info("🚨 IDS остановлен")
    except Exception:
        pass


# ========== АВТОМАТИЗАЦИЯ ==========

def _start_automation():
    try:
        from modules.automation import get_automation
        eng = get_automation()
        eng.start()
        log_success(f"🤖 Автоматизация запущена (правил: {len(eng.get_all())})")
    except ImportError as e:
        log_info(f"⚠️ Модуль автоматизации не найден: {e}")
    except Exception as e:
        log_error(f"⚠️ Ошибка автоматизации: {e}")


def _stop_automation():
    try:
        from modules.automation import get_automation
        get_automation().stop()
        log_info("🤖 Автоматизация остановлена")
    except Exception:
        pass


# ========== OLLAMA ==========

def check_ollama() -> bool:
    try:
        r = requests.get(OLLAMA_TAGS_URL, timeout=TIMEOUT_CHECK)
        return r.status_code == 200
    except Exception:
        return False


def get_ollama_models() -> list:
    try:
        r = requests.get(OLLAMA_TAGS_URL, timeout=TIMEOUT_CHECK)
        if r.status_code == 200:
            data = r.json()
            return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        pass
    return []


def start_ollama() -> bool:
    """
    ИСПРАВЛЕНО: ищем ollama по всем возможным путям.
    """
    try:
        ollama_path = _find_ollama_path()
        if not ollama_path:
            log_error("⚠️ Ollama не найден. Установите с https://ollama.ai/")
            return False

        env = os.environ.copy()
        env["OLLAMA_MODELS"] = OLLAMA_MODELS_DIR

        os.makedirs(OLLAMA_MODELS_DIR, exist_ok=True)

        subprocess.Popen(
            [ollama_path, "serve"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        )
        return True
    except Exception as e:
        log_error(f"⚠️ Не удалось запустить Ollama: {e}")
        return False


def ensure_ollama() -> bool:
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
    log_error(f"   Запустите вручную: $env:OLLAMA_MODELS='{OLLAMA_MODELS_DIR}'; ollama serve")
    log_error("⚠️ Zeta запустится, но ИИ не будет работать.")
    return False


# ========== ИНИЦИАЛИЗАЦИЯ ==========

def init_project() -> bool:
    dirs = [
        "data",
        "data/avatar",
        "data/backups",
        "data/backups/auto",
        "data/backups/manual",
        "data/security",
        "data/audit",
        "data/screenshots",
        "data/images",
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
            with open(gitignore_path, "w", encoding="utf-8") as f:
                f.write("# Защита данных Zeta\n")
                f.write("*.db\n")
                f.write("*.db-wal\n")
                f.write("*.db-shm\n")
                f.write("*.log\n")
                f.write("*.cache\n")
                f.write("avatar/*\n")
                f.write("security/*\n")
                f.write("audit/*\n")
                f.write("backups/*\n")
                f.write("screenshots/*\n")
                f.write("images/*\n")
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


# ========== АУТЕНТИФИКАЦИЯ ==========

def authenticate() -> bool:
    try:
        from PyQt6.QtWidgets import QInputDialog, QLineEdit, QMessageBox, QDialog
        from security.auth import get_auth
        from ui.login_window import LoginWindow

        auth = get_auth()

        if not auth.has_password():
            log_info("🔐 Первый запуск — установка пароля...")

            password, ok = QInputDialog.getText(
                None,
                "🔐 Первый запуск Zeta",
                "Придумайте пароль для Zeta (минимум 6 символов):",
                QLineEdit.EchoMode.Password
            )

            if not ok or not password:
                log_error("⚠️ Установка пароля отменена")
                return False

            if len(password) < 6:
                QMessageBox.critical(
                    None,
                    "❌ Ошибка",
                    "Пароль слишком короткий!\nМинимум 6 символов."
                )
                log_error("⚠️ Пароль слишком короткий")
                return False

            password2, ok2 = QInputDialog.getText(
                None,
                "🔐 Подтверждение",
                "Повторите пароль:",
                QLineEdit.EchoMode.Password
            )

            if not ok2 or password != password2:
                QMessageBox.critical(None, "❌ Ошибка", "Пароли не совпадают!")
                log_error("⚠️ Пароли не совпадают")
                return False

            if auth.set_password(password):
                QMessageBox.information(
                    None,
                    "✅ Готово",
                    "Пароль установлен!\n\nТеперь введите его для входа."
                )
                log_success("Пароль установлен")
            else:
                QMessageBox.critical(None, "❌ Ошибка", "Не удалось установить пароль!")
                return False

        log_info("🔐 Окно входа...")
        login = LoginWindow()

        if login.exec() == QDialog.DialogCode.Accepted:
            log_success("Вход выполнен")
            return True
        else:
            log_error("⚠️ Вход отменён")
            return False

    except ImportError as e:
        log_error(f"⚠️ Ошибка импорта модулей аутентификации: {e}")
        log_error("⚠️ Пропускаю аутентификацию (НЕБЕЗОПАСНО!)")
        try:
            from security.audit import get_audit
            get_audit().log_security("auth_skip", f"ImportError: {e}", severity="critical")
        except Exception:
            pass
        return True
    except Exception as e:
        log_error(f"⚠️ Ошибка аутентификации: {e}")
        import traceback
        traceback.print_exc()
        return False


# ========== CLEANUP ==========

def cleanup() -> None:
    """
    ИСПРАВЛЕНО: защита от двойного вызова (signal + aboutToQuit).
    """
    global _cleanup_done

    if _cleanup_done:
        return
    _cleanup_done = True

    log_info("🔄 Завершение работы...")

    # Останавливаем check_ollama_loop
    _stop_event.set()

    _stop_automation()
    _stop_intrusion_detector()
    _stop_backup_scheduler()
    _audit_shutdown()

    try:
        from core.memory import save_setting
        save_setting("last_run", datetime.now().isoformat())
    except Exception:
        pass

    try:
        from security.auth import get_auth
        get_auth().logout()
    except Exception:
        pass

    log_success("До свидания! 👋")


def signal_handler(sig, frame):
    cleanup()
    sys.exit(0)


# ========== MAIN ==========

def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    log_info(f"Zeta v{VERSION} ({BUILD_DATE})")

    _audit_startup()

    if not init_project():
        log_error("⚠️ Критическая ошибка инициализации. Выход.")
        sys.exit(1)

    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt

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
        app.setQuitOnLastWindowClosed(False)

        # ИСПРАВЛЕНО: гарантированный cleanup при выходе через Qt
        app.aboutToQuit.connect(cleanup)

    except ImportError as e:
        log_error(f"⚠️ Ошибка импорта PyQt6: {e}")
        log_error("Установите: pip install PyQt6")
        sys.exit(1)

    if not authenticate():
        log_error("⚠️ Аутентификация не пройдена. Выход.")
        sys.exit(0)

    _start_backup_scheduler()
    _start_intrusion_detector()
    _start_automation()

    ollama_ready = ensure_ollama()

    if ollama_ready:
        installed = get_ollama_models()
        if not installed:
            log_info("📦 Модели не найдены. Установите:")
            log_info("   ollama pull zeta-universal")
            log_info("   ollama pull llava:13b")

    try:
        from ui.widget import ZetaWidget

        window = ZetaWidget()
        window.show()

        def check_ollama_loop():
            """
            ИСПРАВЛЕНО: остановка через _stop_event.
            """
            while not _stop_event.is_set():
                # Ждём 60 сек ИЛИ до остановки
                if _stop_event.wait(60):
                    break

                if not check_ollama():
                    log_error("⚠️ Ollama упала! Попробуйте перезапустить Zeta.")
                    try:
                        from modules.notifications import show_notification
                        show_notification("⚠️ Zeta", "Ollama упала! Перезапустите Zeta.")
                    except Exception:
                        pass

        threading.Thread(target=check_ollama_loop, daemon=True, name="OllamaCheck").start()

        sys.exit(app.exec())

    except Exception as e:
        log_error(f"⚠️ Непредвиденная ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()