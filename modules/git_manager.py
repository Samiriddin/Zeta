# -*- coding: utf-8 -*-
"""
Git-интеграция Z.
Безопасная обёртка над subprocess. Никаких force-push, rm -rf или rebase без подтверждения.
Автоматические коммиты с умными сообщениями.
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any


# ========== КОНСТАНТЫ ==========
GIT_TIMEOUT = 15
MAX_DIFF_LINES = 300
MAX_LOG_ENTRIES = 10

# Словарь для генерации умных сообщений
COMMIT_MESSAGES = {
    "add": "Добавлен новый функционал",
    "update": "Обновлена логика",
    "fix": "Исправлена ошибка",
    "remove": "Удалён неиспользуемый код",
    "style": "Улучшена структура кода",
    "docs": "Обновлена документация",
    "refactor": "Рефакторинг кода",
    "test": "Добавлены тесты",
}


# ========== ИСКЛЮЧЕНИЯ ==========

class GitSafetyError(Exception):
    """Z не позволит испортить репозиторий."""
    pass


class GitNotFoundError(Exception):
    """Git не найден в системе."""
    pass


# ========== ОСНОВНОЙ КЛАСС ==========

class GitManager:
    """
    Безопасный менеджер для работы с Git.
    Защищает от опасных команд: force-push, hard reset, rebase, clean.
    Автоматически генерирует умные сообщения для коммитов.
    """

    DANGEROUS_FLAGS: set = {
        "--force", "-f", "--hard", "reset", "clean", "-d",
        "push --force", "push -f", "filter-branch", "rebase",
    }

    SAFE_COMMANDS: set = {
        "status", "diff", "log", "branch", "show", "blame",
        "stash list", "remote -v", "config --list",
    }

    def __init__(self, repo_path: Optional[str] = None):
        """
        Инициализирует GitManager.
        
        Args:
            repo_path: путь к репозиторию (по умолчанию текущая директория)
        """
        self.repo_path = Path(repo_path).resolve() if repo_path else Path.cwd()
        self.git_exe = self._find_git()

    def _find_git(self) -> str:
        """Ищет git в PATH."""
        for candidate in ["git", "git.exe"]:
            try:
                subprocess.run(
                    [candidate, "--version"],
                    capture_output=True,
                    check=True,
                    timeout=5
                )
                return candidate
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                continue
        
        # Проверяем стандартные пути
        common_paths = [
            r"C:\Program Files\Git\bin\git.exe",
            r"C:\Program Files (x86)\Git\bin\git.exe",
        ]
        for path in common_paths:
            if os.path.exists(path):
                return path
        
        raise GitNotFoundError(
            "Git не найден в PATH. Установите Git для Windows: https://git-scm.com/download/win"
        )

    def _run(self, args: List[str], cwd: Optional[Path] = None, timeout: int = GIT_TIMEOUT) -> Tuple[int, str, str]:
        """
        Безопасный запуск git. Проверяет опасные флаги перед выполнением.
        
        Args:
            args: аргументы команды
            cwd: рабочая директория
            timeout: таймаут в секундах
        
        Returns:
            (returncode, stdout, stderr)
        """
        cmd_str = " ".join(args).lower()
        
        # Проверка опасных флагов
        for danger in self.DANGEROUS_FLAGS:
            if danger in cmd_str:
                raise GitSafetyError(
                    f"🛡️ Обнаружена потенциально опасная команда: `{danger}`. "
                    f"Z не выполняет деструктивные операции."
                )

        try:
            result = subprocess.run(
                [self.git_exe] + args,
                cwd=str(cwd or self.repo_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        
        except subprocess.TimeoutExpired:
            return -1, "", "⏱️ Команда git зависла (timeout). Возможно, репозиторий слишком большой."
        except FileNotFoundError:
            raise GitNotFoundError("Git не найден. Проверьте установку.")
        except Exception as e:
            return -1, "", f"⚠️ Ошибка Git: {str(e)}"

    def _is_git_repo(self, path: Optional[Path] = None) -> bool:
        """Проверяет, является ли путь git-репозиторием."""
        check_path = path or self.repo_path
        dot_git = check_path / ".git"
        return dot_git.exists() and dot_git.is_dir()

    def find_repo(self, start_path: Optional[Path] = None, max_depth: int = 10) -> Optional[Path]:
        """
        Поднимается вверх по дереву каталогов, ища .git.
        
        Args:
            start_path: начальный путь
            max_depth: максимальная глубина поиска
        
        Returns:
            путь к репозиторию или None
        """
        current = Path(start_path or self.repo_path).resolve()
        for _ in range(max_depth):
            if self._is_git_repo(current):
                return current
            parent = current.parent
            if parent == current:
                break
            current = parent
        return None

    def ensure_repo(self) -> Optional[Path]:
        """Проверяет и возвращает путь к репозиторию."""
        if self._is_git_repo():
            return self.repo_path
        
        repo = self.find_repo()
        if repo:
            self.repo_path = repo
            return repo
        
        return None

    # ========== ГЕНЕРАЦИЯ УМНЫХ СООБЩЕНИЙ ==========

    def _analyze_changes(self) -> List[str]:
        """Анализирует изменения для генерации осмысленного сообщения."""
        code, out, _ = self._run(["status", "--short"])
        if code != 0 or not out:
            return []
        
        lines = out.split("\n")
        actions = []
        for line in lines:
            if not line.strip():
                continue
            # Статус в первой колонке
            status = line[0]
            if status == "??":
                actions.append("add")
            elif status in ("M", "R"):
                actions.append("update")
            elif status == "D":
                actions.append("remove")
            elif status == "A":
                actions.append("add")
        
        return actions

    def _generate_commit_message(self) -> str:
        """Генерирует осмысленное сообщение коммита на основе изменений."""
        actions = self._analyze_changes()
        if not actions:
            return "update: изменения от Z"
        
        # Подсчитываем частоту действий
        action_counts = {}
        for action in actions:
            action_counts[action] = action_counts.get(action, 0) + 1
        
        # Выбираем основное действие
        primary_action = max(action_counts, key=action_counts.get)
        message = COMMIT_MESSAGES.get(primary_action, "Обновление проекта")
        
        # Добавляем детали
        if len(actions) > 1:
            message += f" (+{len(actions) - 1} изм.)"
        
        return message

    # ========== ОСНОВНЫЕ КОМАНДЫ ==========

    def status(self, short: bool = True) -> str:
        """git status. Возвращает читаемый вывод."""
        repo = self.ensure_repo()
        if not repo:
            return "📂 Здесь нет Git-репозитория. Инициализируйте: `git init`"

        flag = "-sb" if short else ""
        code, out, err = self._run(["status"] + ([flag] if flag else []))
        
        if code != 0:
            return f"⚠️ Ошибка git status:\n{err}"
        
        if not out:
            return "✅ Рабочая директория чиста. Нечего коммитить — отличная работа!"

        lines = out.split("\n")
        formatted = ["📊 **Статус репозитория:**\n"]
        
        for line in lines:
            if not line:
                continue
            if line.startswith("##"):
                branch = line.replace("## ", "")
                formatted.append(f"🌿 Ветка: {branch}")
            elif line.startswith("??"):
                formatted.append(f"  ❓ [Новый]    {line[3:]}")
            elif line.startswith(" M"):
                formatted.append(f"  📝 [Изменён]  {line[3:]}")
            elif line.startswith("M "):
                formatted.append(f"  📝 [Изменён]  {line[3:]}")
            elif line.startswith("D "):
                formatted.append(f"  🗑️ [Удалён]   {line[3:]}")
            elif line.startswith("A "):
                formatted.append(f"  ➕ [Добавлен] {line[3:]}")
            elif line.startswith("R "):
                formatted.append(f"  🔄 [Переименован] {line[3:]}")
            else:
                formatted.append(f"  {line}")
        
        return "\n".join(formatted)

    def diff(self, cached: bool = False, file: Optional[str] = None) -> str:
        """git diff. Показывает изменения."""
        if not self.ensure_repo():
            return "📂 Нет репозитория. Z не может показать diff."

        args = ["diff", "--color=never"]
        if cached:
            args.append("--cached")
        if file:
            args.append(file)

        code, out, err = self._run(args)
        if code != 0:
            return f"⚠️ Ошибка diff:\n{err}"
        if not out:
            return "📭 Нет изменений для отображения."
        
        lines = out.split("\n")
        if len(lines) > MAX_DIFF_LINES:
            out = "\n".join(lines[:MAX_DIFF_LINES]) + f"\n\n... и ещё {len(lines) - MAX_DIFF_LINES} строк."
        
        return f"📝 **Изменения:**\n```diff\n{out}\n```"

    def log(self, n: int = MAX_LOG_ENTRIES, oneline: bool = True) -> str:
        """История коммитов."""
        if not self.ensure_repo():
            return "📂 Нет репозитория. Нет истории."

        args = ["log", f"-n{n}"]
        if oneline:
            args.append("--oneline")
        else:
            args.append("--pretty=format:%h - %s (%an, %ar)")

        code, out, err = self._run(args)
        if code != 0:
            return f"⚠️ Ошибка log:\n{err}"
        
        if not out:
            return "📭 История пуста."
        
        return f"📜 **История коммитов:**\n```\n{out}\n```"

    def branch(self) -> str:
        """Список веток."""
        if not self.ensure_repo():
            return "📂 Нет репозитория."

        code, out, err = self._run(["branch", "-a"])
        if code != 0:
            return f"⚠️ Ошибка branch:\n{err}"
        if not out:
            return "📭 Нет веток."

        # Форматируем вывод
        lines = out.split("\n")
        formatted = ["🌿 **Ветки:**\n"]
        for line in lines:
            if line.startswith("*"):
                formatted.append(f"  ⭐ {line[1:].strip()} (текущая)")
            elif "->" in line:
                formatted.append(f"  🔗 {line.strip()}")
            else:
                formatted.append(f"  {line.strip()}")
        
        return "\n".join(formatted)

    def add(self, files: Optional[List[str]] = None) -> str:
        """git add. Безопасная версия — только конкретные файлы или все изменённые."""
        if not self.ensure_repo():
            return "📂 Нет репозитория."

        if files:
            # Проверяем существование файлов
            missing = []
            for f in files:
                fpath = self.repo_path / f
                if not fpath.exists():
                    missing.append(f)
            if missing:
                return f"⚠️ Файлы не найдены: {', '.join(missing)}"
            
            code, out, err = self._run(["add"] + files)
        else:
            code, out, err = self._run(["add", "-u"])  # Только изменённые
        
        if code != 0:
            return f"⚠️ Ошибка add:\n{err}"
        return "✅ Файлы добавлены в индекс."

    def commit(self, message: str, allow_empty: bool = False) -> str:
        """git commit. Проверяет, что сообщение не пустое."""
        if not self.ensure_repo():
            return "📂 Нет репозитория."

        if not message or len(message.strip()) < 3:
            return "⚠️ Сообщение коммита слишком короткое. Напишите осмысленное описание."

        # Проверяем, есть ли изменения в индексе
        code, out, _ = self._run(["diff", "--cached", "--stat"])
        if not out.strip() and not allow_empty:
            return "📭 Нет изменений в индексе. Сначала добавьте файлы через `git add`."

        safe_msg = message.replace('"', '\\"')
        args = ["commit", "-m", safe_msg]
        if allow_empty:
            args.append("--allow-empty")

        code, out, err = self._run(args)
        if code != 0:
            return f"⚠️ Ошибка commit:\n{err}"
        
        # Извлекаем хеш коммита
        hash_match = re.search(r"\[([^\]]+)\]", out)
        if hash_match:
            return f"✅ Коммит создан: [{hash_match.group(1)}] {message}"
        return f"✅ Коммит создан: {message}"

    def auto_commit(self, message: Optional[str] = None) -> str:
        """Автокоммит: add + commit с умным сообщением."""
        if not self.ensure_repo():
            return "📂 Нет репозитория."

        # Проверяем, есть ли изменения
        code, out, _ = self._run(["status", "--short"])
        if not out.strip():
            return "📭 Нет изменений для коммита."

        # Добавляем изменения
        add_result = self.add()
        if "Ошибка" in add_result:
            return add_result

        # Создаём сообщение (умное или переданное)
        if not message:
            message = self._generate_commit_message()

        return self.commit(message)

    def stash(self, action: str = "list", message: Optional[str] = None) -> str:
        """git stash. Только save/list/show — pop только по явному запросу."""
        if not self.ensure_repo():
            return "📂 Нет репозитория."

        if action == "save":
            msg = message or "WIP: автосохранение Z"
            code, out, err = self._run(["stash", "save", msg])
        elif action == "list":
            code, out, err = self._run(["stash", "list"])
        elif action == "show":
            code, out, err = self._run(["stash", "show", "-p"])
        elif action == "pop":
            # Разрешаем только если пользователь явно попросил "вернуть из stash"
            code, out, err = self._run(["stash", "pop"])
        else:
            return f"⚠️ Z не поддерживает `stash {action}` без подтверждения. Слишком рискованно."

        if code != 0:
            return f"⚠️ Ошибка stash:\n{err}"
        
        if not out.strip():
            return "📭 Stash пуст."
        return f"📦 **Stash:**\n```\n{out}\n```"

    def get_repo_info(self) -> Dict[str, Any]:
        """Метаданные репозитория для контекста."""
        info = {
            "path": str(self.repo_path),
            "is_repo": self._is_git_repo(),
            "branch": "unknown",
            "last_commit": "unknown",
            "untracked": 0,
            "modified": 0,
        }
        
        if not info["is_repo"]:
            return info

        code, out, _ = self._run(["rev-parse", "--abbrev-ref", "HEAD"])
        if code == 0:
            info["branch"] = out.strip()

        code, out, _ = self._run(["log", "-1", "--format=%h %s"])
        if code == 0:
            info["last_commit"] = out.strip()

        code, out, _ = self._run(["status", "--short"])
        if code == 0:
            for line in out.split("\n"):
                if line.startswith("??"):
                    info["untracked"] += 1
                elif line.startswith(" M") or line.startswith("M "):
                    info["modified"] += 1

        return info


# ========== УДОБНЫЕ ФУНКЦИИ ==========

def git_status(repo_path: Optional[str] = None) -> str:
    """Быстрый статус репозитория."""
    git = GitManager(repo_path)
    return git.status()


def git_diff(repo_path: Optional[str] = None, cached: bool = False) -> str:
    """Быстрый diff."""
    git = GitManager(repo_path)
    return git.diff(cached=cached)


def git_commit(repo_path: Optional[str] = None, message: str = "update from Z") -> str:
    """Быстрый коммит."""
    git = GitManager(repo_path)
    git.add()
    return git.commit(message)


def git_auto_commit(repo_path: Optional[str] = None) -> str:
    """Быстрый автокоммит с умным сообщением."""
    git = GitManager(repo_path)
    return git.auto_commit()


# ========== ТЕСТ ==========
if __name__ == "__main__":
    print("🧪 Тест GitManager\n")
    
    # Тест в текущей директории
    try:
        git = GitManager("D:\\Zeta")
        
        print("📝 Тест 1: Статус")
        status = git.status()
        print(status[:200] + "..." if len(status) > 200 else status)
        print("-" * 40)
        
        print("📝 Тест 2: Информация о репозитории")
        info = git.get_repo_info()
        print(f"Путь: {info['path']}")
        print(f"Ветка: {info['branch']}")
        print(f"Последний коммит: {info['last_commit']}")
        print(f"Неотслеживаемых: {info['untracked']}")
        print(f"Изменённых: {info['modified']}")
        print("-" * 40)
        
        print("📝 Тест 3: Ветки")
        branches = git.branch()
        print(branches[:200] + "..." if len(branches) > 200 else branches)
        print("-" * 40)
        
        print("📝 Тест 4: Умный автокоммит")
        auto_msg = git._generate_commit_message()
        print(f"Сгенерированное сообщение: {auto_msg}")
        
    except GitNotFoundError as e:
        print(f"❌ {e}")
    except Exception as e:
        print(f"⚠️ Ошибка: {e}")