# -*- coding: utf-8 -*-
"""
Модуль для сканирования и анализа структуры проекта.
Поддерживает: обзор проекта, дерево файлов, поиск файлов, статистику.
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple

# ========== КОНСТАНТЫ ==========

SKIP_DIRS: Set[str] = {
    "__pycache__", ".git", ".venv", "venv", "node_modules",
    "dist", "build", ".idea", ".vscode",
    "egg-info", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".coverage", "htmlcov", ".tox", "site-packages",
    "logs", "tmp", "temp", "cache", ".cache",
}

SKIP_EXTS: Set[str] = {
    ".pyc", ".pyo", ".class", ".o", ".exe", ".dll",
    ".so", ".pyd", ".db", ".sqlite", ".sqlite3",
    ".log", ".tmp", ".bak", ".swp", ".swo",
    ".jpg", ".jpeg", ".png", ".gif", ".ico", ".svg", ".webp",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv",
    ".zip", ".tar", ".gz", ".rar", ".7z",
}

MAX_TREE_ITEMS = 50
MAX_FILES_LIST = 15

# Для VS Code контекста
try:
    import pygetwindow as gw
    HAS_GW = True
except ImportError:
    HAS_GW = False

try:
    import ctypes
    HAS_CTYPES = True
except ImportError:
    HAS_CTYPES = False

COMMON_ROOTS = [
    "D:\\",
    "C:\\",
    os.path.expanduser("~\\Documents"),
    os.path.expanduser("~\\Desktop"),
    os.path.expanduser("~\\source"),
    os.path.expanduser("~\\PycharmProjects"),
    os.path.expanduser("~\\Projects"),
    os.path.expanduser("~\\GitHub"),
    "D:\\Projects",
    "D:\\Dev",
]

PROJECT_MARKERS = [
    ".git", "main.py", "app.py", "package.json", 
    "pyproject.toml", "requirements.txt", "README.md",
    "setup.py", "manage.py", "docker-compose.yml",
    "Cargo.toml", "go.mod", "composer.json", "Gemfile",
]

VS_CODE_TITLE_KEYWORDS = [
    "Visual Studio Code",
    "VS Code",
    "code -",
    "VSCode",
]


# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

def _get_window_title_ctypes() -> str:
    """Получает заголовок активного окна через ctypes (без pygetwindow)."""
    if not HAS_CTYPES:
        return ""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        return buff.value
    except Exception:
        return ""


def _is_vscode_window(title: str) -> bool:
    """Проверяет, является ли окно окном VS Code."""
    if not title:
        return False
    for keyword in VS_CODE_TITLE_KEYWORDS:
        if keyword in title:
            return True
    return False


def _extract_project_name(title: str) -> str:
    """Извлекает имя проекта из заголовка VS Code."""
    if not title:
        return ""
    
    for suffix in VS_CODE_TITLE_KEYWORDS:
        title = title.replace(suffix, "").strip(" -")
    
    title = re.sub(r'^[^\s-]+\.\w+\s*-\s*', '', title)
    title = re.sub(r'^[A-Za-z]:\\[^\\]+\\', '', title)
    title = re.sub(r'\s*\[Workspace\]', '', title)
    
    parts = [p.strip() for p in title.split(" - ") if p.strip()]
    if not parts:
        return ""
    
    result = parts[-1] if len(parts) >= 2 else parts[0]
    result = result.split("\\")[-1].split("/")[-1]
    return result.strip()


def _is_valid_project(path: str) -> bool:
    """Проверяет, что по пути лежит проект."""
    if not os.path.isdir(path):
        return False
    try:
        entries = os.listdir(path)
        return any(marker in entries for marker in PROJECT_MARKERS)
    except Exception:
        return False


def _search_project(project_name: str) -> Optional[str]:
    """Ищет проект по имени."""
    if not project_name:
        return None
    
    # Быстрый поиск
    for root in COMMON_ROOTS:
        if not os.path.exists(root):
            continue
        try:
            with os.scandir(root) as it:
                for entry in it:
                    if entry.is_dir() and entry.name.lower() == project_name.lower():
                        if _is_valid_project(entry.path):
                            return entry.path
                    if entry.is_dir():
                        try:
                            with os.scandir(entry.path) as it2:
                                for sub in it2:
                                    if sub.is_dir() and sub.name.lower() == project_name.lower():
                                        if _is_valid_project(sub.path):
                                            return sub.path
                        except PermissionError:
                            continue
        except PermissionError:
            continue
    
    # Глобальный поиск
    import glob
    patterns = [
        f"D:\\**\\{project_name}",
        f"C:\\**\\{project_name}",
        os.path.expanduser(f"~\\**\\{project_name}"),
    ]
    for pattern in patterns:
        try:
            for path in glob.iglob(pattern, recursive=True):
                if os.path.isdir(path) and _is_valid_project(path):
                    return path
        except Exception:
            continue
    
    return None


# ========== ОСНОВНЫЕ ФУНКЦИИ ==========

def scan_project(path: str, max_items: int = MAX_TREE_ITEMS) -> str:
    """Сканирует проект и возвращает краткую сводку с деревом."""
    if not path or not path.strip():
        return "⚠️ Укажите путь к проекту."

    if not os.path.isdir(path):
        return f"⚠️ Путь не найден: {path}"

    stats = {
        "files": 0,
        "dirs": 0,
        "py": 0,
        "js": 0,
        "html": 0,
        "css": 0,
        "json": 0,
        "md": 0,
        "other": 0,
        "total_lines": 0,
    }

    tree_lines = []
    count = 0

    try:
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".") and not d.startswith("_")]
            level = root.replace(path, "").count(os.sep)
            indent = "  " * level
            display_name = os.path.basename(root) or root

            if count < max_items:
                tree_lines.append(f"{indent}📁 {display_name}")
                count += 1

            for f in files:
                if f.startswith("."):
                    continue
                ext = os.path.splitext(f)[1].lower()
                if ext in SKIP_EXTS:
                    continue
                stats["files"] += 1

                if ext == ".py":
                    stats["py"] += 1
                elif ext in (".js", ".ts", ".jsx", ".tsx"):
                    stats["js"] += 1
                elif ext in (".html", ".htm"):
                    stats["html"] += 1
                elif ext == ".css":
                    stats["css"] += 1
                elif ext == ".json":
                    stats["json"] += 1
                elif ext in (".md", ".markdown"):
                    stats["md"] += 1
                else:
                    stats["other"] += 1

                if ext in {".py", ".js", ".ts", ".html", ".css", ".json", ".md", ".txt"}:
                    try:
                        with open(os.path.join(root, f), "r", encoding="utf-8", errors="ignore") as file:
                            stats["total_lines"] += sum(1 for _ in file)
                    except Exception:
                        pass

                if count < max_items:
                    file_indent = "  " * (level + 1)
                    tree_lines.append(f"{file_indent}📄 {f}")
                    count += 1

            if count >= max_items:
                break
    except PermissionError:
        return "⚠️ Нет доступа к некоторым папкам."

    tree_str = "\n".join(tree_lines[:max_items])
    if len(tree_lines) > max_items:
        tree_str += f"\n  ... и ещё {len(tree_lines) - max_items} элементов"

    result = f"""
📊 **Статистика проекта:**

📁 **Папок:** {stats['dirs']}
📄 **Файлов:** {stats['files']}

📂 **По типам:**
🐍 Python: {stats['py']}
📜 JS/TS: {stats['js']}
🌐 HTML: {stats['html']}
🎨 CSS: {stats['css']}
📋 JSON: {stats['json']}
📝 Markdown: {stats['md']}
📦 Другое: {stats['other']}

📏 **Строк кода:** {stats['total_lines']:,}

📁 **Структура проекта:**
{tree_str}
    """.strip()

    return result


def get_file_tree(path: str, max_depth: int = 3, max_files: int = MAX_FILES_LIST) -> str:
    """Возвращает дерево файлов с ограниченной глубиной."""
    if not path or not path.strip():
        return "⚠️ Укажите путь."

    if not os.path.isdir(path):
        return f"⚠️ Путь не найден: {path}"

    lines = []
    root_name = os.path.basename(path) or path
    lines.append(f"📁 {root_name}")

    try:
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".") and not d.startswith("_")]
            level = root.replace(path, "").count(os.sep)
            if level >= max_depth:
                dirs[:] = []
                continue
            indent = "  " * (level + 1)
            display_name = os.path.basename(root) or root

            if level >= 0:
                lines.append(f"{indent}📁 {display_name}")

            file_indent = "  " * (level + 2)
            for f in sorted(files)[:max_files]:
                if f.startswith("."):
                    continue
                ext = os.path.splitext(f)[1].lower()
                if ext in SKIP_EXTS:
                    continue

                icon = "📄"
                if ext == ".py":
                    icon = "🐍"
                elif ext in (".js", ".ts"):
                    icon = "📜"
                elif ext == ".html":
                    icon = "🌐"
                elif ext == ".css":
                    icon = "🎨"
                elif ext == ".json":
                    icon = "📋"
                elif ext == ".md":
                    icon = "📝"
                elif ext in (".jpg", ".png", ".gif"):
                    icon = "🖼️"

                lines.append(f"{file_indent}{icon} {f}")

            if len(files) > max_files:
                lines.append(f"{file_indent}... и ещё {len(files) - max_files} файлов")
    except PermissionError:
        return "⚠️ Нет доступа к некоторым папкам."

    return "\n".join(lines)


def find_files_by_pattern(path: str, pattern: str, limit: int = 20) -> str:
    """Ищет файлы по паттерну."""
    if not path or not path.strip():
        return "⚠️ Укажите путь."

    if not os.path.isdir(path):
        return f"⚠️ Путь не найден: {path}"

    if not pattern or not pattern.strip():
        return "⚠️ Укажите паттерн для поиска."

    results = []
    pattern_lower = pattern.lower()

    try:
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            for f in files:
                if f.startswith("."):
                    continue
                if pattern_lower in f.lower():
                    results.append(os.path.join(root, f))
                    if len(results) >= limit:
                        break
            if len(results) >= limit:
                break
    except PermissionError:
        return "⚠️ Нет доступа к некоторым папкам."

    if not results:
        return f"🔍 Файлы с паттерном '{pattern}' не найдены."

    result = f"🔍 Найдено {len(results)} файлов:\n"
    for i, r in enumerate(results, 1):
        result += f"  {i}. {r}\n"
    return result


def get_project_stats(path: str) -> str:
    """Возвращает подробную статистику проекта."""
    if not path or not path.strip():
        return "⚠️ Укажите путь."

    if not os.path.isdir(path):
        return f"⚠️ Путь не найден: {path}"

    stats = {
        "total_files": 0,
        "total_dirs": 0,
        "total_lines": 0,
        "by_ext": {},
        "by_lang": {},
    }

    try:
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            stats["total_dirs"] += len(dirs)

            for f in files:
                if f.startswith("."):
                    continue
                ext = os.path.splitext(f)[1].lower()
                if ext in SKIP_EXTS:
                    continue

                stats["total_files"] += 1
                stats["by_ext"][ext] = stats["by_ext"].get(ext, 0) + 1

                lang = _detect_language(ext)
                if lang:
                    stats["by_lang"][lang] = stats["by_lang"].get(lang, 0) + 1

                if ext in {".py", ".js", ".ts", ".html", ".css", ".json", ".md", ".txt"}:
                    try:
                        with open(os.path.join(root, f), "r", encoding="utf-8", errors="ignore") as file:
                            stats["total_lines"] += sum(1 for _ in file)
                    except Exception:
                        pass
    except PermissionError:
        return "⚠️ Нет доступа к некоторым папкам."

    result = f"""
📊 **Подробная статистика проекта:**

📁 **Папок:** {stats['total_dirs']}
📄 **Файлов:** {stats['total_files']}
📏 **Строк кода:** {stats['total_lines']:,}

📂 **По расширениям:**
"""
    for ext, count in sorted(stats["by_ext"].items(), key=lambda x: -x[1]):
        result += f"  {ext or 'без расширения'}: {count}\n"

    if stats["by_lang"]:
        result += "\n📂 **По языкам:**\n"
        for lang, count in sorted(stats["by_lang"].items(), key=lambda x: -x[1]):
            result += f"  {lang}: {count}\n"

    return result.strip()


def _detect_language(ext: str) -> Optional[str]:
    """Определяет язык по расширению."""
    lang_map = {
        ".py": "Python",
        ".js": "JavaScript",
        ".ts": "TypeScript",
        ".jsx": "React (JSX)",
        ".tsx": "React (TSX)",
        ".html": "HTML",
        ".htm": "HTML",
        ".css": "CSS",
        ".scss": "SCSS",
        ".sass": "Sass",
        ".json": "JSON",
        ".xml": "XML",
        ".yaml": "YAML",
        ".yml": "YAML",
        ".md": "Markdown",
        ".txt": "Text",
        ".java": "Java",
        ".cpp": "C++",
        ".c": "C",
        ".cs": "C#",
        ".go": "Go",
        ".rs": "Rust",
        ".php": "PHP",
        ".rb": "Ruby",
        ".swift": "Swift",
        ".kt": "Kotlin",
    }
    return lang_map.get(ext)


def get_active_vscode_window_title() -> str:
    """Возвращает заголовок активного или любого окна VS Code."""
    if HAS_GW:
        try:
            active = gw.getActiveWindow()
            if active and _is_vscode_window(active.title):
                return active.title
            for window in gw.getAllWindows():
                if _is_vscode_window(window.title) and window.title.strip():
                    return window.title
        except Exception:
            pass
    title = _get_window_title_ctypes()
    if _is_vscode_window(title):
        return title
    return ""


def get_current_project_path() -> str:
    """Определяет путь к текущему проекту VS Code."""
    title = get_active_vscode_window_title()
    if not title:
        return ""

    project_name = _extract_project_name(title)
    if not project_name:
        return ""

    # Проверяем кэш
    try:
        from core.memory import get_setting, save_setting
        cache_key = f"vscode_project_{project_name.lower().replace(' ', '_')}"
        cached = get_setting(cache_key, "")
        if cached and os.path.isdir(cached) and _is_valid_project(cached):
            return cached
    except Exception:
        pass

    found = _search_project(project_name)
    if found:
        try:
            from core.memory import save_setting
            save_setting(cache_key, found)
        except Exception:
            pass
        return found

    return ""


def get_project_name_from_title() -> str:
    """Возвращает имя проекта из заголовка VS Code."""
    return _extract_project_name(get_active_vscode_window_title())


def get_git_context() -> str:
    """Возвращает git-контекст текущего проекта."""
    project_path = get_current_project_path()
    if not project_path:
        return ""
    try:
        from modules.git_manager import GitManager
        git = GitManager(project_path)
        repo = git.find_repo()
        if not repo:
            return ""
        git.repo_path = repo
        info = git.get_repo_info()
        lines = [
            f"📂 Репозиторий: {info['path']}",
            f"🌿 Ветка: {info['branch']}",
            f"📝 Последний коммит: {info['last_commit']}",
        ]
        if info.get("modified", 0) > 0:
            lines.append(f"📄 Изменённые файлы: {info['modified']}")
        if info.get("untracked", 0) > 0:
            lines.append(f"➕ Новые файлы: {info['untracked']}")
        return "\n".join(lines)
    except Exception:
        return ""


def quick_scan(path: str = "D:\\Zeta") -> str:
    """Быстрый обзор проекта."""
    return scan_project(path)


def tree(path: str = "D:\\Zeta", depth: int = 3) -> str:
    """Быстрое дерево проекта."""
    return get_file_tree(path, max_depth=depth)


# ========== ЭКСПОРТ ==========
__all__ = [
    'scan_project',
    'get_file_tree',
    'find_files_by_pattern',
    'get_project_stats',
    'get_current_project_path',
    'get_project_name_from_title',
    'get_git_context',
    'quick_scan',
    'tree'
]