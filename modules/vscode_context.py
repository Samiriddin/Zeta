# -*- coding: utf-8 -*-
"""
Модуль для определения контекста VS Code.
Определяет текущий проект, извлекает имя проекта, получает Git-контекст.
"""

import os
import re
import glob
from pathlib import Path
from typing import Optional, List, Dict, Any

from core.memory import get_setting, save_setting

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


# ========== ОПРЕДЕЛЕНИЕ VS CODE ==========

def get_active_vscode_window_title() -> str:
    """
    Возвращает заголовок активного или любого окна VS Code.
    """
    if HAS_GW:
        try:
            # Сначала пробуем активное окно
            active = gw.getActiveWindow()
            if active and _is_vscode_window(active.title):
                return active.title
            
            # Ищем среди всех окон
            for window in gw.getAllWindows():
                if _is_vscode_window(window.title) and window.title.strip():
                    return window.title
        except Exception:
            pass
    
    # Fallback через ctypes
    title = _get_window_title_ctypes()
    if _is_vscode_window(title):
        return title
    
    return ""


def get_all_vscode_windows() -> List[str]:
    """
    Возвращает список заголовков всех окон VS Code.
    """
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


# ========== ИЗВЛЕЧЕНИЕ ИМЕНИ ПРОЕКТА ==========

def _extract_project_name(title: str) -> str:
    """
    Из 'main.py - Zeta - Visual Studio Code' достаёт 'Zeta'.
    
    Форматы:
    - "main.py - Zeta - Visual Studio Code" → "Zeta"
    - "Zeta - Visual Studio Code" → "Zeta"
    - "Zeta [Workspace]" → "Zeta"
    - "D:\\Zeta\\main.py - Visual Studio Code" → "Zeta"
    """
    if not title:
        return ""
    
    # Убираем суффиксы
    for suffix in VS_CODE_TITLE_KEYWORDS:
        title = title.replace(suffix, "").strip(" -")
    
    # Убираем расширения файлов в начале
    title = re.sub(r'^[^\s-]+\.\w+\s*-\s*', '', title)
    
    # Убираем путь в начале
    title = re.sub(r'^[A-Za-z]:\\[^\\]+\\', '', title)
    
    # Убираем [Workspace]
    title = re.sub(r'\s*\[Workspace\]', '', title)
    
    # Убираем лишние пробелы
    parts = [p.strip() for p in title.split(" - ") if p.strip()]
    
    if not parts:
        return ""
    
    # Если есть несколько частей, берём последнюю (обычно имя проекта)
    # Или первую, если она выглядит как имя
    result = parts[-1] if len(parts) >= 2 else parts[0]
    
    # Убираем путь, если остался
    result = result.split("\\")[-1].split("/")[-1]
    
    return result.strip()


def get_project_name_from_title() -> str:
    """Просто имя проекта из заголовка."""
    return _extract_project_name(get_active_vscode_window_title())


# ========== ПОИСК ПРОЕКТА ==========

def _is_valid_project(path: str) -> bool:
    """Проверяет, что по пути действительно лежит проект (есть маркеры)."""
    if not os.path.isdir(path):
        return False
    try:
        entries = os.listdir(path)
        return any(marker in entries for marker in PROJECT_MARKERS)
    except Exception:
        return False


def _fast_search(project_name: str) -> Optional[str]:
    """
    Быстрый поиск: scandir по 1 уровню в common roots, затем по 1 уровню в подпапках.
    """
    for root in COMMON_ROOTS:
        if not os.path.exists(root):
            continue
        try:
            with os.scandir(root) as it:
                for entry in it:
                    if entry.is_dir() and entry.name.lower() == project_name.lower():
                        candidate = entry.path
                        if _is_valid_project(candidate):
                            return candidate
                    # Проверяем подпапки
                    if entry.is_dir():
                        try:
                            with os.scandir(entry.path) as it2:
                                for sub in it2:
                                    if sub.is_dir() and sub.name.lower() == project_name.lower():
                                        candidate = sub.path
                                        if _is_valid_project(candidate):
                                            return candidate
                        except PermissionError:
                            continue
        except PermissionError:
            continue
    return None


def _glob_search(project_name: str) -> Optional[str]:
    """
    Fallback: glob по дискам.
    """
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


def _search_project(project_name: str) -> Optional[str]:
    """
    Ищет проект по имени.
    """
    if not project_name:
        return None
    
    # Сначала быстрый поиск
    found = _fast_search(project_name)
    if found:
        return found
    
    # Затем glob
    found = _glob_search(project_name)
    if found:
        return found
    
    return None


def get_current_project_path() -> str:
    """
    Определяет путь к текущему проекту VS Code.
    Кэш → fast search → glob fallback.
    """
    title = get_active_vscode_window_title()
    if not title:
        return ""

    project_name = _extract_project_name(title)
    if not project_name:
        return ""

    # Проверяем кэш
    cache_key = f"vscode_project_{project_name.lower().replace(' ', '_')}"
    cached = get_setting(cache_key, "")
    if cached and os.path.isdir(cached) and _is_valid_project(cached):
        return cached

    # Ищем проект
    found = _search_project(project_name)
    if found:
        save_setting(cache_key, found)
        return found

    # Если не нашли по имени, пробуем найти по пути из заголовка
    path_match = re.search(r'([A-Za-z]:\\[^\\]+\\[^\\]+)', title)
    if path_match:
        possible_path = path_match.group(1)
        if os.path.isdir(possible_path) and _is_valid_project(possible_path):
            save_setting(cache_key, possible_path)
            return possible_path

    return ""


# ========== GIT КОНТЕКСТ ==========

def get_git_context() -> str:
    """
    Возвращает git-контекст текущего проекта для системного промпта.
    """
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


# ========== ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ ==========

def get_project_context() -> Dict[str, Any]:
    """
    Возвращает полный контекст проекта в виде словаря.
    """
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


def get_project_summary() -> str:
    """
    Возвращает краткую сводку о проекте для чата.
    """
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
    
    if context.get("git_context"):
        lines.append(f"\n{context['git_context']}")
    
    return "\n".join(lines)


# ========== ТЕСТ ==========
if __name__ == "__main__":
    print("🧪 Тест vscode_context.py\n")
    
    print("📝 Тест 1: Активное окно VS Code")
    title = get_active_vscode_window_title()
    print(f"Заголовок: {title}")
    print("-" * 40)
    
    print("📝 Тест 2: Имя проекта")
    name = get_project_name_from_title()
    print(f"Имя проекта: {name}")
    print("-" * 40)
    
    print("📝 Тест 3: Путь к проекту")
    path = get_current_project_path()
    print(f"Путь: {path}")
    print("-" * 40)
    
    print("📝 Тест 4: Проектный контекст")
    print(get_project_summary())
    print("-" * 40)
    
    print("📝 Тест 5: Все окна VS Code")
    windows = get_all_vscode_windows()
    for w in windows:
        print(f"  {w}")
    print("-" * 40)
    
    print("\n✅ Тесты завершены!")