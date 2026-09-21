# -*- coding: utf-8 -*-
"""
Модуль для работы с файлами и папками.
Работает ТОЛЬКО с явными командами! Никаких ложных срабатываний.

Безопасность:
    - Удаление через корзину (send2trash) — восстановимо
    - Белый список папок, где разрешено удаление
    - Защита системных папок (Windows, Program Files)
    - Логирование в data/zeta.log + аудит
"""

import os
import re
import sys
import time
import logging
import subprocess
from pathlib import Path
from typing import Tuple, Optional, List, Set

sys.path.insert(0, str(Path(__file__).parent.parent))


# ========== ЛОГИРОВАНИЕ ==========

def _log(msg: str) -> None:
    logging.info(f"[FILE] {msg}")


def _log_warn(msg: str) -> None:
    logging.warning(f"[FILE] {msg}")


def _audit(msg: str) -> None:
    """Логировать в аудит, если доступен."""
    try:
        from security.audit import get_audit
        get_audit().log_security("file_manager", msg)
    except Exception:
        pass


# ========== КОНСТАНТЫ ==========
MAX_SEARCH_RESULTS = 10
MAX_LIST_ITEMS = 20
SEARCH_ROOT_DEFAULT = "D:\\"
PROJECT_ROOT = "D:\\Zeta"
MAX_SEARCH_DEPTH = 6
MAX_SEARCH_TIME = 10  # секунд

# Папки, где РАЗРЕШЕНО удаление (белый список)
DELETE_ALLOWED_PREFIXES: List[str] = [
    "D:\\Zeta\\generated",
    "D:\\Zeta\\temp",
    "D:\\Zeta\\cache",
    "D:\\Zeta\\data\\images",
    "D:\\Zeta\\data\\screenshots",
    "D:\\Zeta\\data\\backups\\manual",
]

# Папки, которые НЕ сканируем при поиске
SEARCH_SKIP_DIRS: Set[str] = {
    "$RECYCLE.BIN", "System Volume Information", "Windows",
    "Program Files", "Program Files (x86)", "ProgramData",
    "AppData", "node_modules", "__pycache__", ".git",
    "$WinREAgent", "Recovery", "PerfLogs", "Intel", "AMD",
    "NVIDIA", "Drivers", "OneDriveTemp", "Config.Msi",
}

# Системные префиксы — вообще не трогаем
SYSTEM_PREFIXES: List[str] = [
    "C:\\Windows", "D:\\Windows",
    "C:\\Program Files", "D:\\Program Files",
    "C:\\Program Files (x86)", "D:\\Program Files (x86)",
]


# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

def _clean_path(path: str, remove_commands: List[str] = None) -> str:
    """Очищает путь от лишних слов и кавычек."""
    if not path:
        return ""
    path = path.strip()
    if remove_commands:
        for cmd in remove_commands:
            if path.lower().startswith(cmd):
                path = path[len(cmd):].strip()
    path = path.strip('"').strip("'")
    return path


def _resolve_path(path: str, base_dirs: List[str] = None) -> str:
    """
    Пытается найти существующий путь.
    Для абсолютных — возвращает как есть.
    Для относительных — ищет в base_dirs, иначе возвращает abspath.
    """
    if not path:
        return ""

    if os.path.isabs(path):
        return path

    if base_dirs is None:
        base_dirs = [PROJECT_ROOT, "D:\\", "C:\\"]

    for base in base_dirs:
        test_path = os.path.join(base, path)
        if os.path.exists(test_path):
            return test_path

    # Не нашли в базах — возвращаем от текущей рабочей директории
    return os.path.abspath(path)


def _format_size(size: int) -> str:
    """Форматирует размер файла в удобочитаемый вид."""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    else:
        return f"{size / (1024 * 1024 * 1024):.2f} GB"


def _open_in_explorer(path: str, select: bool = False) -> bool:
    """Открывает путь в Проводнике."""
    try:
        if select:
            subprocess.Popen(
                ["explorer", "/select,", path],
                shell=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(
                ["explorer", path],
                shell=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return True
    except Exception as e:
        _log_warn(f"Не удалось открыть в Проводнике: {e}")
        return False


def _is_delete_allowed(path: str) -> Tuple[bool, str]:
    """
    Проверяет, разрешено ли удаление по этому пути.
    Возвращает (ok, reason).
    """
    if not path:
        return False, "Пустой путь"

    # Нормализуем
    try:
        normalized = os.path.abspath(path)
    except Exception:
        return False, "Некорректный путь"

    # Системные префиксы — блок
    for prefix in SYSTEM_PREFIXES:
        if normalized.lower().startswith(prefix.lower()):
            return False, f"Системная папка: {prefix}"

    # Сам проект и его подпапки (кроме белого списка)
    if normalized.lower().startswith(PROJECT_ROOT.lower()):
        # Разрешено только то, что в белом списке
        for allowed in DELETE_ALLOWED_PREFIXES:
            if normalized.lower().startswith(allowed.lower()):
                return True, "В белом списке"

        # Особая защита: сам Zeta и его код
        protected_in_project = [
            "D:\\Zeta\\core", "D:\\Zeta\\modules", "D:\\Zeta\\ui",
            "D:\\Zeta\\voice", "D:\\Zeta\\security", "D:\\Zeta\\secret",
            "D:\\Zeta\\data\\zeta.db", "D:\\Zeta\\main.py", "D:\\Zeta\\config.py",
        ]
        for prot in protected_in_project:
            if normalized.lower().startswith(prot.lower()):
                return False, f"Защищённая папка/файл: {prot}"

        return False, "Вне белого списка удаления"

    # Всё остальное (за пределами проекта) — блок
    return False, "Вне проекта Zeta — удаление запрещено"


# ========== ОСНОВНЫЕ ФУНКЦИИ ==========

def open_file(path: str) -> str:
    """Открывает файл или папку в Проводнике."""
    if not path or not path.strip():
        return "⚠️ Укажите путь к файлу или папке."

    path = _clean_path(path, ["открой", "откройте", "open", "файл", "папку", "папка"])
    path = _resolve_path(path)

    if not os.path.exists(path):
        return f"⚠️ Папка или файл не найден: {path}"

    _log(f"Открываю: {path}")

    if os.path.isdir(path):
        if _open_in_explorer(path, select=False):
            return f"📂 Открыта папка: {path}"
        return f"⚠️ Не удалось открыть папку: {path}"
    else:
        if _open_in_explorer(path, select=True):
            return f"📄 Открыт файл: {path}"
        return f"⚠️ Не удалось открыть файл: {path}"


def close_folder(path: str = "") -> str:
    """
    Безопасное закрытие папок.
    ВАЖНО: НЕ убивает explorer.exe (это закрыло бы все окна пользователя).
    Возвращает сообщение о том, что нужно сделать вручную.
    """
    _log("Запрос на закрытие папок")
    return (
        "ℹ️ Безопасное закрытие папок недоступно в Zeta.\n"
        "Причина: убийство explorer.exe закрыло бы панель задач и все ваши окна.\n"
        "💡 Закройте нужные окна вручную."
    )


def find_files(name: str, root_dir: str = SEARCH_ROOT_DEFAULT) -> str:
    """Ищет файлы и папки по имени."""
    if not name or not name.strip():
        return "⚠️ Укажите имя файла или папки для поиска."

    name = name.strip()

    # Если это уже существующий путь — возвращаем сразу
    if os.path.exists(name):
        if os.path.isdir(name):
            return (
                f"📂 Найдена папка: {name}\n"
                f"💡 Используйте 'покажи папку {name}' для просмотра содержимого."
            )
        return f"📄 Найден файл: {name}"

    if not os.path.isdir(root_dir):
        return f"⚠️ Папка поиска не найдена: {root_dir}"

    _log(f"Поиск '{name}' в {root_dir}")
    results: List[str] = []
    count = 0
    start_time = time.time()
    timed_out = False

    def _depth(path_root: str) -> int:
        try:
            rel = os.path.relpath(path_root, root_dir)
            if rel == ".":
                return 0
            return rel.count(os.sep) + 1
        except Exception:
            return 0

    try:
        for dirpath, dirnames, filenames in os.walk(root_dir, followlinks=False):
            # Лимит времени
            if time.time() - start_time > MAX_SEARCH_TIME:
                timed_out = True
                break

            # Лимит глубины
            if _depth(dirpath) > MAX_SEARCH_DEPTH:
                dirnames.clear()
                continue

            # Пропускаем системные папки
            dirnames[:] = [
                d for d in dirnames
                if d not in SEARCH_SKIP_DIRS and not d.startswith("$")
            ]

            # Файлы
            for filename in filenames:
                if name.lower() in filename.lower():
                    results.append(os.path.join(dirpath, filename))
                    count += 1
                    if count >= MAX_SEARCH_RESULTS:
                        break

            if count >= MAX_SEARCH_RESULTS:
                break

            # Папки
            for dirname in dirnames:
                if name.lower() in dirname.lower():
                    results.append(os.path.join(dirpath, dirname) + os.sep)
                    count += 1
                    if count >= MAX_SEARCH_RESULTS:
                        break

            if count >= MAX_SEARCH_RESULTS:
                break

    except PermissionError:
        return "⚠️ Нет доступа к некоторым папкам. Поиск ограничен."
    except Exception as e:
        _log_warn(f"Ошибка поиска: {e}")
        return f"⚠️ Ошибка поиска: {str(e)}"

    elapsed = time.time() - start_time
    _log(f"Поиск завершён: {len(results)} результатов за {elapsed:.1f}с")

    if not results:
        if timed_out:
            return (
                f"❌ Ничего не найдено (поиск прерван по таймауту {MAX_SEARCH_TIME}с).\n"
                f"💡 Попробуйте сузить область поиска."
            )
        return f"❌ Файл или папка '{name}' не найдены в {root_dir}"

    result = f"🔍 Найдено ({len(results)}):\n"
    for r in results:
        result += f"  {r}\n"
    if timed_out:
        result += f"\n⏱️ Поиск прерван по таймауту {MAX_SEARCH_TIME}с."
    return result


def list_files(path: str) -> str:
    """Показывает содержимое папки."""
    if not path or not path.strip():
        return "⚠️ Укажите путь к папке."

    path = _clean_path(path, ["покажи", "list", "содержимое", "папку", "папка"])
    path = _resolve_path(path)

    if not os.path.exists(path):
        return f"⚠️ Папка не найдена: {path}"
    if not os.path.isdir(path):
        return f"⚠️ Это не папка: {path}"

    try:
        items = os.listdir(path)
    except PermissionError:
        return f"⚠️ Нет доступа к папке: {path}"
    except Exception as e:
        return f"⚠️ Ошибка чтения папки: {str(e)}"

    folders: List[str] = []
    files: List[str] = []

    for item in sorted(items):
        full_path = os.path.join(path, item)
        try:
            if os.path.isdir(full_path):
                folders.append(f"📁 {item}")
            else:
                size = os.path.getsize(full_path)
                files.append(f"📄 {item} ({_format_size(size)})")
        except Exception:
            continue

    result = f"📂 Содержимое {path}:\n"

    if folders:
        result += f"\n📁 Папки ({len(folders)}):\n"
        result += "\n".join(folders[:MAX_LIST_ITEMS])
        if len(folders) > MAX_LIST_ITEMS:
            result += f"\n... и ещё {len(folders) - MAX_LIST_ITEMS} папок"

    if files:
        result += f"\n\n📄 Файлы ({len(files)}):\n"
        result += "\n".join(files[:MAX_LIST_ITEMS])
        if len(files) > MAX_LIST_ITEMS:
            result += f"\n... и ещё {len(files) - MAX_LIST_ITEMS} файлов"

    if not folders and not files:
        result += "\n📭 Папка пуста."

    return result


def delete_file(path: str) -> str:
    """
    Удаляет файл или папку (через корзину).
    Только для белого списка папок.
    """
    if not path or not path.strip():
        return "⚠️ Укажите путь к файлу или папке."

    path = _clean_path(path, ["удали", "удалить", "delete", "файл", "папку", "папка"])
    path = _resolve_path(path)

    if not os.path.exists(path):
        return f"⚠️ Файл или папка не найдены: {path}"

    # Проверка белого списка
    allowed, reason = _is_delete_allowed(path)
    if not allowed:
        _log_warn(f"Удаление запрещено: {path} ({reason})")
        _audit(f"delete_denied: {path} ({reason})")
        return (
            f"🛡️ Удаление запрещено: {reason}\n"
            f"Путь: {path}\n"
            f"💡 Разрешено удалять только из:\n"
            + "\n".join(f"   • {p}" for p in DELETE_ALLOWED_PREFIXES)
        )

    # Проверяем наличие send2trash
    try:
        from send2trash import send2trash
    except ImportError:
        return (
            "⚠️ Модуль send2trash не установлен.\n"
            "Установите: pip install send2trash\n"
            "Это нужно, чтобы файлы попадали в корзину, а не удалялись насовсем."
        )

    try:
        _log(f"Удаляю в корзину: {path}")
        _audit(f"delete: {path}")
        send2trash(path)
        return f"🗑️ Перемещено в корзину: {path}"
    except Exception as e:
        _log_warn(f"Ошибка удаления: {e}")
        _audit(f"delete_error: {path} ({e})")
        return f"⚠️ Ошибка удаления: {str(e)}"


# ⚠️ ВАЖНО: Функция работает ТОЛЬКО с явными командами!
def needs_file_action(message: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Определяет, является ли сообщение файловой командой.
    ВАЖНО: Теперь это происходит ТОЛЬКО если есть явные слова!
    """
    if not message:
        return None, None

    msg = message.lower().strip()

    # ✅ ТОЛЬКО команда "ОТКРОЙ" / "OPEN"
    if re.search(r"(открой\s+(файл|папку|папка)|open\s+file|open\s+folder)", msg):
        match = re.search(r"открой\s+(?:файл|папку|папка)\s+(.+)", message, re.IGNORECASE)
        if match:
            return "open", match.group(1).strip()
        return "open", ""

    # ✅ ТОЛЬКО команда "ЗАКРОЙ" / "CLOSE"
    if re.search(r"(закрой\s+(папку|папка|файл)|close\s+folder)", msg):
        match = re.search(r"закрой\s+(?:папку|папка|файл)\s+(.+)", message, re.IGNORECASE)
        if match:
            return "close", match.group(1).strip()
        return "close", ""

    # ✅ ТОЛЬКО команда "НАЙДИ ФАЙЛ" / "НАЙДИ ПАПКУ"
    if re.search(r"(найди\s+(файл|папку|папка)|where\s+is|find\s+file)", msg):
        match = re.search(r"найди\s+(?:файл|папку|папка)\s+(.+)", message, re.IGNORECASE)
        if match:
            return "find", match.group(1).strip()
        return "find", ""

    # ✅ ТОЛЬКО команда "ПОКАЖИ ПАПКУ" / "LIST"
    if re.search(r"(покажи\s+папку|list\s+folder)", msg):
        match = re.search(r"покажи\s+папку\s+(.+)", message, re.IGNORECASE)
        if match:
            return "list", match.group(1).strip()
        return "list", ""

    # ✅ ТОЛЬКО команда "СОДЕРЖИМОЕ ПАПКИ"
    if re.search(r"содержимое\s+папки", msg):
        match = re.search(r"содержимое\s+папки\s+(.+)", message, re.IGNORECASE)
        if match:
            return "list", match.group(1).strip()
        return "list", ""

    # ✅ ТОЛЬКО команда "УДАЛИ ФАЙЛ" / "DELETE"
    if re.search(r"(удали\s+(файл|папку|папка)|delete\s+file)", msg):
        match = re.search(r"удали\s+(?:файл|папку|папка)\s+(.+)", message, re.IGNORECASE)
        if match:
            return "delete", match.group(1).strip()
        return "delete", ""

    # ❌ ВСЁ ОСТАЛЬНОЕ — НЕ ФАЙЛОВАЯ КОМАНДА!
    return None, None


# ========== ТЕСТ ==========

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    print("🧪 Тест file_manager.py\n")
    print("=" * 60)

    # --- Тест 1: needs_file_action ---
    print("\n📝 Тест 1: Распознавание команд")
    test_messages = [
        "открой папку D:\\Zeta",
        "найди файл config.py",
        "покажи папку D:\\Zeta",
        "расскажи про атом",       # НЕ команда
        "привет как дела",         # НЕ команда
        "что такое файл?",         # НЕ команда
    ]
    for msg in test_messages:
        action, detail = needs_file_action(msg)
        marker = "✅" if action else "⭕"
        print(f"{marker} {msg!r:35} → {action or 'не команда'}")

    # --- Тест 2: list_files ---
    print("\n📝 Тест 2: Список файлов D:\\Zeta")
    result = list_files("D:\\Zeta")
    print(result[:400] + "..." if len(result) > 400 else result)

    # --- Тест 3: Проверка белого списка ---
    print("\n📝 Тест 3: Проверка удаления")
    test_paths = [
        "D:\\Zeta\\generated\\test.py",          # ✅ разрешено
        "D:\\Zeta\\core\\ai_engine.py",          # 🛡️ запрещено
        "D:\\Zeta\\main.py",                     # 🛡️ запрещено
        "C:\\Windows\\System32\\cmd.exe",        # 🛡️ запрещено
        "C:\\Users\\samir\\Documents\\test.txt", # 🛡️ запрещено
    ]
    for p in test_paths:
        allowed, reason = _is_delete_allowed(p)
        marker = "✅" if allowed else "🛡️"
        print(f"{marker} {p:40} → {reason}")

    # --- Тест 4: find_files (короткий поиск) ---
    print("\n📝 Тест 4: Поиск 'config' в D:\\Zeta")
    result = find_files("config", "D:\\Zeta")
    print(result[:400] + "..." if len(result) > 400 else result)

    print("\n" + "=" * 60)
    print("✅ Тесты завершены!")