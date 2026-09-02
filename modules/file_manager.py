# -*- coding: utf-8 -*-
"""
Модуль для работы с файлами и папками.
Работает ТОЛЬКО с явными командами! Никаких ложных срабатываний.
"""

import os
import re
import subprocess
import chardet
from typing import Tuple, Optional, List, Union
from pathlib import Path

# ========== КОНСТАНТЫ ==========
MAX_SEARCH_RESULTS = 10
MAX_LIST_ITEMS = 20
SEARCH_ROOT_DEFAULT = "D:\\"
PROJECT_ROOT = "D:\\Zeta"
MAX_CONTENT_SEARCH_RESULTS = 5
CONTENT_SEARCH_CHUNK = 200


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
    """Пытается найти существующий путь."""
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
    return path


def _format_size(size: int) -> str:
    """Форматирует размер файла в удобочитаемый вид."""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size // 1024} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size // (1024 * 1024)} MB"
    else:
        return f"{size // (1024 * 1024 * 1024)} GB"


def _open_in_explorer(path: str, select: bool = False) -> bool:
    """Открывает путь в Проводнике."""
    try:
        if select:
            subprocess.Popen(['explorer', '/select,', path])
        else:
            subprocess.Popen(['explorer', path])
        return True
    except Exception:
        return False


# ========== ОСНОВНЫЕ ФУНКЦИИ ==========

def open_file(path: str) -> str:
    """Открывает файл или папку в Проводнике."""
    if not path or not path.strip():
        return "⚠️ Укажите путь к файлу или папке."
    path = _clean_path(path, ["открой", "откройте", "open", "файл", "папку", "папка"])
    path = _resolve_path(path)
    if not os.path.exists(path):
        return f"⚠️ Папка или файл не найден: {path}"
    try:
        if os.path.isdir(path):
            if _open_in_explorer(path, select=False):
                return f"📂 Открыта папка: {path}"
            else:
                return f"⚠️ Не удалось открыть папку: {path}"
        else:
            if _open_in_explorer(path, select=True):
                return f"📄 Открыт файл: {path}"
            else:
                return f"⚠️ Не удалось открыть файл: {path}"
    except Exception as e:
        return f"⚠️ Ошибка открытия: {str(e)}"


def close_folder(path: str) -> str:
    """Закрывает все окна Проводника и перезапускает его."""
    try:
        result = subprocess.run(
            ['taskkill', '/F', '/IM', 'explorer.exe'],
            capture_output=True,
            text=True
        )
        if result.returncode != 0 and "not found" not in result.stderr:
            return f"⚠️ Ошибка закрытия Проводника: {result.stderr}"
        subprocess.Popen(['explorer.exe'])
        return f"📂 Проводник перезапущен (все окна закрыты)"
    except Exception as e:
        return f"⚠️ Ошибка закрытия: {str(e)}"


def find_files(name: str, root_dir: str = SEARCH_ROOT_DEFAULT) -> str:
    """Ищет файлы и папки по имени."""
    if not name or not name.strip():
        return "⚠️ Укажите имя файла или папки для поиска."
    name = name.strip()
    results: List[str] = []
    count = 0
    if os.path.exists(name):
        if os.path.isdir(name):
            return f"📂 Найдена папка: {name}\n💡 Используйте 'покажи папку {name}' для просмотра содержимого."
        else:
            return f"📄 Найден файл: {name}"
    try:
        for dirpath, dirnames, filenames in os.walk(root_dir):
            for filename in filenames:
                if name.lower() in filename.lower():
                    results.append(os.path.join(dirpath, filename))
                    count += 1
                    if count >= MAX_SEARCH_RESULTS:
                        break
            if count >= MAX_SEARCH_RESULTS:
                break
            for dirname in dirnames:
                if name.lower() in dirname.lower():
                    results.append(os.path.join(dirpath, dirname) + "\\")
                    count += 1
                    if count >= MAX_SEARCH_RESULTS:
                        break
            if count >= MAX_SEARCH_RESULTS:
                break
    except PermissionError:
        return "⚠️ Нет доступа к некоторым папкам. Поиск ограничен."
    except Exception as e:
        return f"⚠️ Ошибка поиска: {str(e)}"
    if not results:
        return f"❌ Файл или папка '{name}' не найдены в {root_dir}"
    result = f"🔍 Найдено ({len(results)}):\n"
    for r in results:
        result += f"  {r}\n"
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
        files: List[str] = []
        folders: List[str] = []
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
    except PermissionError:
        return f"⚠️ Нет доступа к папке: {path}"
    except Exception as e:
        return f"⚠️ Ошибка чтения папки: {str(e)}"


def delete_file(path: str) -> str:
    """Удаляет файл или папку."""
    if not path or not path.strip():
        return "⚠️ Укажите путь к файлу или папке."
    path = _clean_path(path, ["удали", "удалить", "delete", "файл", "папку", "папка"])
    path = _resolve_path(path)
    if not os.path.exists(path):
        return f"⚠️ Файл или папка не найдены: {path}"
    try:
        protected = ["D:\\Zeta", "D:\\Zeta\\core", "D:\\Zeta\\modules", "D:\\Zeta\\ui", "D:\\Zeta\\voice"]
        if path in protected or path.startswith("D:\\Windows") or path.startswith("C:\\Windows"):
            return f"⚠️ Удаление защищённой папки запрещено: {path}"
        if os.path.isdir(path):
            if not os.listdir(path):
                os.rmdir(path)
                return f"🗑️ Удалена папка: {path}"
            else:
                return f"⚠️ Папка не пуста. Удалите содержимое вручную: {path}"
        else:
            os.remove(path)
            return f"🗑️ Удалён файл: {path}"
    except Exception as e:
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
    
    # ✅ ТОЛЬКО команда "НАЙДИ ФАЙЛ" / "НАЙДИ ПАПКУ" / "WHERE IS"
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
    print("🧪 Тест file_manager.py\n")
    
    print("📝 Тест 1: needs_file_action")
    actions = [
        "открой папку D:\\Zeta",
        "найди файл config.py",
        "покажи папку D:\\Zeta",
        "расскажи про атом",  # ДОЛЖНО ВЕРНУТЬ None!
        "привет как дела",    # ДОЛЖНО ВЕРНУТЬ None!
    ]
    for msg in actions:
        action, detail = needs_file_action(msg)
        if action:
            print(f"✅ {msg} → {action}: {detail}")
        else:
            print(f"❌ {msg} → не распознано")
    print("-" * 40)
    
    print("📝 Тест 2: list_files")
    result = list_files("D:\\Zeta")
    print(result[:300] + "..." if len(result) > 300 else result)
    print("-" * 40)
    
    print("\n✅ Тесты завершены!")