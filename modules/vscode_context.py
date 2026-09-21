# -*- coding: utf-8 -*-
"""
Модуль для определения контекста VS Code.
Определяет текущий проект, извлекает имя проекта, получает Git-контекст.
+ Сканирование проекта (scan_project, get_file_tree) — перенесено из project_context.py.

Особенности:
    - Работа с несколькими окнами VS Code
    - Кэш проверки проектов
    - Таймаут на glob-поиск (защита от зависаний)
    - Логирование в data/zeta.log
    - Безопасная работа с memory (try/except)
"""

import os
import re
import sys
import glob
import time
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))


# ========== ЛОГИРОВАНИЕ ==========

def _log(msg: str) -> None:
    logging.info(f"[VSCODE] {msg}")


def _log_warn(msg: str) -> None:
    logging.warning(f"[VSCODE] {msg}")


# ========== ИМПОРТ MEMORY (безопасно) ==========

try:
    from core.memory import get_setting, save_setting
    HAS_MEMORY = True
except Exception as e:
    HAS_MEMORY = False
    get_setting = None
    save_setting = None
    _log_warn(f"memory недоступна: {e}")


# ========== ПРОВЕРКА БИБЛИОТЕК ==========

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


# ========== КОНСТАНТЫ ==========

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

GLOB_TIMEOUT = 5  # секунд

SKIP_DIRS = {
    "__pycache__", ".git", ".venv", "venv", "node_modules",
    "dist", "build", ".idea", ".vscode", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".tox", "site-packages",
}

SKIP_EXTS = {
    ".pyc", ".pyo", ".exe", ".dll", ".so", ".pyd",
    ".db", ".sqlite", ".sqlite3", ".log", ".tmp",
    ".jpg", ".jpeg", ".png", ".gif", ".ico", ".svg",
    ".mp3", ".mp4", ".wav", ".zip", ".tar", ".gz", ".rar",
}

# Кэш проверенных проектов
_project_validity_cache: Dict[str, bool] = {}


# ========== ВСПОМОГАТЕЛЬНЫЕ ==========

def _get_window_title_ctypes() -> str:
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
    if not title:
        return False
    return any(kw in title for kw in VS_CODE_TITLE_KEYWORDS)


# ========== VS CODE ОКНА ==========

def get_active_vscode_window_title() -> str:
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


def get_all_vscode_windows() -> List[str]:
    if not HAS_GW:
        return []
    try:
        titles = []
        for window in gw.getAllWindows():
            if _is_vscode_window(window.title) and window.title.strip():
                titles.append(window.title)
        return titles
    except Exception:
        return []


# ========== ИЗВЛЕЧЕНИЕ ИМЕНИ ==========

def _extract_project_name(title: str) -> str:
    if not title:
        return ""

    for suffix in VS_CODE_TITLE_KEYWORDS:
        title = title.replace(suffix, "").strip(" -")

    title = re.sub(r'\s*\[[^\]]*\]', '', title)
    title = re.sub(r'^[^\s-]+\.\w+\s*-\s*', '', title)
    title = re.sub(r'^[A-Za-z]:\\[^\\]+\\', '', title)

    parts = [p.strip() for p in title.split(" - ") if p.strip()]
    if not parts:
        return ""

    result = parts[-1] if len(parts) >= 2 else parts[0]
    result = result.split("\\")[-1].split("/")[-1]
    return result.strip()


def get_project_name_from_title() -> str:
    return _extract_project_name(get_active_vscode_window_title())


# ========== ПОИСК ПРОЕКТА ==========

def _is_valid_project(path: str) -> bool:
    if not os.path.isdir(path):
        return False
    if path in _project_validity_cache:
        return _project_validity_cache[path]

    try:
        entries = os.listdir(path)
        result = any(marker in entries for marker in PROJECT_MARKERS)
        _project_validity_cache[path] = result
        return result
    except Exception:
        _project_validity_cache[path] = False
        return False


def _fast_search(project_name: str) -> Optional[str]:
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
    return None


def _glob_search(project_name: str, timeout: int = GLOB_TIMEOUT) -> Optional[str]:
    patterns = [
        f"D:\\**\\{project_name}",
        f"C:\\**\\{project_name}",
    ]
    start = time.time()
    for pattern in patterns:
        if time.time() - start > timeout:
            _log_warn(f"Glob таймаут: {project_name}")
            break
        try:
            for path in glob.iglob(pattern, recursive=True):
                if time.time() - start > timeout:
                    break
                if os.path.isdir(path) and _is_valid_project(path):
                    return path
        except Exception:
            continue
    return None


def _search_project(project_name: str) -> Optional[str]:
    if not project_name:
        return None

    found = _fast_search(project_name)
    if found:
        _log(f"Найден (fast): {found}")
        return found

    found = _glob_search(project_name)
    if found:
        _log(f"Найден (glob): {found}")
        return found

    _log_warn(f"Проект '{project_name}' не найден")
    return None


def get_current_project_path() -> str:
    try:
        title = get_active_vscode_window_title()
        if not title:
            return ""

        project_name = _extract_project_name(title)
        if not project_name:
            return ""

        cache_key = f"vscode_project_{project_name.lower().replace(' ', '_')}"

        if HAS_MEMORY:
            try:
                cached = get_setting(cache_key, "")
                if cached and os.path.isdir(cached) and _is_valid_project(cached):
                    return cached
            except Exception:
                pass

        found = _search_project(project_name)
        if found:
            if HAS_MEMORY:
                try:
                    save_setting(cache_key, found)
                except Exception:
                    pass
            return found

        path_match = re.search(r"([A-Za-z]:\\[^\\]+\\[^\\]+)", title)
        if path_match:
            possible = path_match.group(1)
            if os.path.isdir(possible) and _is_valid_project(possible):
                if HAS_MEMORY:
                    try:
                        save_setting(cache_key, possible)
                    except Exception:
                        pass
                return possible

        return ""
    except Exception as e:
        _log_warn(f"Ошибка get_current_project_path: {e}")
        return ""


# ========== GIT КОНТЕКСТ ==========

def get_git_context() -> str:
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
    except Exception as e:
        _log_warn(f"Ошибка get_git_context: {e}")
        return ""


# ========== КОНТЕКСТ ПРОЕКТА ==========

def get_project_context() -> Dict[str, Any]:
    try:
        project_path = get_current_project_path()
        project_name = get_project_name_from_title()

        context = {
            "project_name": project_name,
            "project_path": project_path,
            "is_vscode_open": bool(get_active_vscode_window_title()),
            "git_context": get_git_context() if project_path else "",
        }

        if project_path and os.path.isdir(project_path):
            try:
                files = os.listdir(project_path)
                context["files_count"] = len(files)
                context["has_git"] = ".git" in files
                context["has_readme"] = any(f.lower() == "readme.md" for f in files)
                context["has_requirements"] = "requirements.txt" in files
                context["has_pyproject"] = "pyproject.toml" in files
            except Exception:
                pass

        return context
    except Exception as e:
        _log_warn(f"Ошибка get_project_context: {e}")
        return {
            "project_name": "",
            "project_path": "",
            "is_vscode_open": False,
            "git_context": "",
        }


def _read_readme_preview(project_path: str, lines: int = 3) -> str:
    try:
        for name in ("README.md", "README.txt", "README"):
            path = os.path.join(project_path, name)
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = []
                    for _ in range(lines):
                        line = f.readline()
                        if not line:
                            break
                        content.append(line.rstrip())
                    return "\n".join(content)
    except Exception:
        pass
    return ""


def get_project_summary() -> str:
    context = get_project_context()

    if not context["project_path"]:
        return "📂 Проект не обнаружен. Откройте папку в VS Code."

    lines = [
        f"📂 **Проект:** {context['project_name']}",
        f"📁 **Путь:** {context['project_path']}",
    ]

    if context.get("files_count"):
        lines.append(f"📄 **Файлов:** {context['files_count']}")
    if context.get("has_git"):
        lines.append("🔗 **Git:** ✅")
    if context.get("has_readme"):
        lines.append("📖 **README:** ✅")
    if context.get("has_requirements"):
        lines.append("📦 **requirements.txt:** ✅")
    if context.get("has_pyproject"):
        lines.append("⚙️ **pyproject.toml:** ✅")

    readme = _read_readme_preview(context["project_path"])
    if readme:
        lines.append(f"\n📖 **О проекте:**\n{readme}")

    if context.get("git_context"):
        lines.append(f"\n{context['git_context']}")

    return "\n".join(lines)


# ============================================================
#  СКАНИРОВАНИЕ ПРОЕКТА (перенесено из project_context.py)
# ============================================================

def scan_project(path: str, max_items: int = 80) -> str:
    """Сканирует проект и возвращает сводку с деревом."""
    if not path or not os.path.isdir(path):
        return f"⚠️ Путь не найден: {path}"

    stats = {
        "files": 0, "dirs": 0, "py": 0, "js": 0, "html": 0,
        "css": 0, "json": 0, "md": 0, "other": 0, "lines": 0,
    }

    tree_lines = []
    count = 0

    try:
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            stats["dirs"] += len(dirs)

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
                        with open(os.path.join(root, f), "r",
                                  encoding="utf-8", errors="ignore") as file:
                            stats["lines"] += sum(1 for _ in file)
                    except Exception:
                        pass

                if count < max_items:
                    tree_lines.append(f"{indent}  📄 {f}")
                    count += 1

            if count >= max_items:
                break
    except PermissionError:
        return "⚠️ Нет доступа к некоторым папкам."

    tree_str = "\n".join(tree_lines)
    if count >= max_items:
        tree_str += f"\n... (обрезано на {max_items})"

    return (
        f"📊 **Статистика проекта:**\n\n"
        f"📁 Папок: {stats['dirs']}\n"
        f"📄 Файлов: {stats['files']}\n\n"
        f"🐍 Python: {stats['py']}\n"
        f"📜 JS/TS: {stats['js']}\n"
        f"🌐 HTML: {stats['html']}\n"
        f"🎨 CSS: {stats['css']}\n"
        f"📋 JSON: {stats['json']}\n"
        f"📝 Markdown: {stats['md']}\n"
        f"📦 Другое: {stats['other']}\n\n"
        f"📏 Строк: {stats['lines']:,}\n\n"
        f"📁 **Структура:**\n{tree_str}"
    )


def get_file_tree(path: str, max_depth: int = 3, max_files: int = 15) -> str:
    """Дерево файлов с ограниченной глубиной."""
    if not path or not os.path.isdir(path):
        return f"⚠️ Путь не найден: {path}"

    lines = [f"📁 {os.path.basename(path) or path}"]

    try:
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            level = root.replace(path, "").count(os.sep)
            if level >= max_depth:
                dirs[:] = []
                continue

            indent = "  " * (level + 1)
            display_name = os.path.basename(root) or root
            lines.append(f"{indent}📁 {display_name}")

            file_indent = "  " * (level + 2)
            for f in sorted(files)[:max_files]:
                if f.startswith("."):
                    continue
                ext = os.path.splitext(f)[1].lower()
                if ext in SKIP_EXTS:
                    continue
                lines.append(f"{file_indent}📄 {f}")

            if len(files) > max_files:
                lines.append(f"{file_indent}... и ещё {len(files) - max_files}")
    except PermissionError:
        return "⚠️ Нет доступа к некоторым папкам."

    return "\n".join(lines)


# ========== ЭКСПОРТ ==========

__all__ = [
    "get_active_vscode_window_title",
    "get_all_vscode_windows",
    "get_project_name_from_title",
    "get_current_project_path",
    "get_git_context",
    "get_project_context",
    "get_project_summary",
    "scan_project",
    "get_file_tree",
]


# ========== ТЕСТ ==========

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    print("🧪 Тест vscode_context.py\n")
    print("=" * 60)

    print("\n📝 Тест 1: Активное окно VS Code")
    title = get_active_vscode_window_title()
    print(f"Заголовок: {title or '(нет)'}")

    print("\n📝 Тест 2: Путь к проекту")
    path = get_current_project_path()
    print(f"Путь: {path or '(не найден)'}")

    print("\n📝 Тест 3: scan_project (D:\\Zeta)")
    if os.path.isdir("D:\\Zeta"):
        result = scan_project("D:\\Zeta")
        print(result[:500] + "..." if len(result) > 500 else result)

    print("\n📝 Тест 4: get_file_tree (D:\\Zeta, depth=2)")
    if os.path.isdir("D:\\Zeta"):
        print(get_file_tree("D:\\Zeta", max_depth=2))

    print("\n📝 Тест 5: Сводка проекта")
    print(get_project_summary())

    print("\n" + "=" * 60)
    print("✅ Тесты завершены!")