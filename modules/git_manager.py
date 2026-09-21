# -*- coding: utf-8 -*-
"""
Git-интеграция Z.
Безопасная обёртка над subprocess. Никаких force-push, rm -rf или rebase без подтверждения.
Автоматические коммиты с умными сообщениями.

Безопасность:
    - Проверка опасных команд по позиции (args[0]) и флагам (in args)
    - Логирование всех операций в data/zeta.log
    - Экранирование не через shell
"""

import os
import re
import sys
import logging
import subprocess
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))


# ========== ЛОГИРОВАНИЕ ==========

def _log(msg: str) -> None:
    logging.info(f"[GIT] {msg}")


def _log_warn(msg: str) -> None:
    logging.warning(f"[GIT] {msg}")


def _audit(msg: str) -> None:
    """Логировать в аудит, если доступен."""
    try:
        from security.audit import get_audit
        get_audit().log_git("auto", msg, level="safe")
    except Exception:
        pass


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

    # Опасные КОМАНДЫ (проверяются как args[0])
    DANGEROUS_COMMANDS: set = {
        "reset", "rebase", "clean", "filter-branch",
        "gc", "prune", "reflog", "update-ref",
        "filter-repo", "fast-import", "replace",
    }

    # Опасные ФЛАГИ (проверяются как элемент в args)
    DANGEROUS_FLAGS: set = {
        "--force", "-f",
        "--hard",
        "--mixed",       # частично опасен
        "--keep",
        "--mirror",
        "--delete",
        "--prune",
        "-d", "-D",      # удаление ветки
        "--all",         # для git clean
        "-x",            # для git clean — удаление ignored файлов
    }

    # Безопасные команды (для справки)
    SAFE_COMMANDS: set = {
        "status", "diff", "log", "show", "blame",
        "branch", "remote", "config", "rev-parse",
        "ls-files", "ls-tree", "cat-file", "describe",
        "add", "commit", "stash", "init", "fetch",
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
                    timeout=5,
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

    def _check_safety(self, args: List[str]) -> None:
        """
        Проверяет команду на опасность.
        Правильная логика:
            - args[0] — команда. Если опасна → блок.
            - args[1:] — флаги. Если опасный флаг → блок.
            - НЕ проверяем подстроки! `git log --grep "reset"` — безопасно.
        """
        if not args:
            return

        command = args[0].lower()
        flags = [a.lower() for a in args[1:]]

        # 1. Опасная команда?
        if command in self.DANGEROUS_COMMANDS:
            _log_warn(f"Блок опасной команды: {command}")
            _audit(f"blocked_command: {command}")
            raise GitSafetyError(
                f"🛡️ Команда `git {command}` заблокирована.\n"
                f"Z не выполняет деструктивные операции. Сделайте вручную в терминале."
            )

        # 2. Опасный флаг?
        for flag in flags:
            if flag in self.DANGEROUS_FLAGS:
                _log_warn(f"Блок опасного флага: {flag} в {command}")
                _audit(f"blocked_flag: {command} {flag}")
                raise GitSafetyError(
                    f"🛡️ Флаг `{flag}` в команде `git {command}` заблокирован.\n"
                    f"Z не выполняет деструктивные операции."
                )

        # 3. Специальный случай: push --force (одним элементом)
        for arg in [command] + flags:
            if "push" in arg and ("--force" in arg or "-f" in arg):
                _log_warn(f"Блок force-push: {arg}")
                _audit(f"blocked_force_push: {arg}")
                raise GitSafetyError(
                    "🛡️ Force-push заблокирован. Это перезапишет чужую работу."
                )

    def _run(self, args: List[str], cwd: Optional[Path] = None,
             timeout: int = GIT_TIMEOUT) -> Tuple[int, str, str]:
        """
        Безопасный запуск git. Проверяет опасные команды перед выполнением.

        Returns:
            (returncode, stdout, stderr)
        """
        self._check_safety(args)

        _log(f"git {' '.join(args)}")

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
            _log_warn(f"Timeout: git {' '.join(args)}")
            return -1, "", "⏱️ Команда git зависла (timeout). Возможно, репозиторий слишком большой."
        except FileNotFoundError:
            raise GitNotFoundError("Git не найден. Проверьте установку.")
        except Exception as e:
            _log_warn(f"Ошибка запуска git: {e}")
            return -1, "", f"⚠️ Ошибка Git: {str(e)}"

    def _is_git_repo(self, path: Optional[Path] = None) -> bool:
        """Проверяет, является ли путь git-репозиторием."""
        check_path = path or self.repo_path
        dot_git = check_path / ".git"
        return dot_git.exists() and dot_git.is_dir()

    def find_repo(self, start_path: Optional[Path] = None,
                  max_depth: int = 10) -> Optional[Path]:
        """Поднимается вверх по дереву каталогов, ища .git."""
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

    @staticmethod
    def _parse_status_line(line: str) -> Optional[str]:
        """
        Парсит одну строку git status --short.
        Возвращает действие: add / update / remove / rename или None.

        Формат git: XY путь
            X — статус в индексе
            Y — статус в рабочей директории
            ?? — untracked
            !! — ignored
        """
        if not line or len(line) < 2:
            return None

        # Untracked
        if line.startswith("??"):
            return "add"

        # Ignored — пропускаем
        if line.startswith("!!"):
            return None

        x = line[0]  # статус в индексе
        y = line[1]  # статус в рабочей директории

        # Приоритет: add > remove > rename > update
        if x == "A" or y == "A":
            return "add"
        if x == "D" or y == "D":
            return "remove"
        if x == "R" or y == "R":
            return "rename"
        if x == "M" or y == "M":
            return "update"
        if x == "C" or y == "C":
            return "update"

        return None

    def _analyze_changes(self) -> List[str]:
        """Анализирует изменения для генерации осмысленного сообщения."""
        code, out, _ = self._run(["status", "--short"])
        if code != 0 or not out:
            return []

        actions = []
        for line in out.split("\n"):
            if not line.strip():
                continue
            action = self._parse_status_line(line)
            if action:
                actions.append(action)

        return actions

    def _generate_commit_message(self) -> str:
        """Генерирует осмысленное сообщение коммита на основе изменений."""
        actions = self._analyze_changes()
        if not actions:
            return "update: изменения от Z"

        # Подсчитываем частоту
        action_counts: Dict[str, int] = {}
        for action in actions:
            action_counts[action] = action_counts.get(action, 0) + 1

        # Выбираем основное
        primary_action = max(action_counts, key=action_counts.get)
        message = COMMIT_MESSAGES.get(primary_action, "Обновление проекта")

        # Добавляем детали
        total = len(actions)
        if total > 1:
            message += f" ({total} файлов)"

        return message

    # ========== ОСНОВНЫЕ КОМАНДЫ ==========

    def status(self, short: bool = True) -> str:
        """git status. Возвращает читаемый вывод."""
        repo = self.ensure_repo()
        if not repo:
            return "📂 Здесь нет Git-репозитория. Инициализируйте: `git init`"

        args = ["status"]
        if short:
            args.append("-sb")

        code, out, err = self._run(args)

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
                continue

            # Двухбуквенные статусы
            status = line[:2]
            path = line[3:] if len(line) > 3 else ""

            if status == "??":
                formatted.append(f"  ❓ [Новый]        {path}")
            elif status[0] == "A" or status[1] == "A":
                formatted.append(f"  ➕ [Добавлен]     {path}")
            elif status[0] == "D" or status[1] == "D":
                formatted.append(f"  🗑️ [Удалён]       {path}")
            elif status[0] == "R" or status[1] == "R":
                formatted.append(f"  🔄 [Переименован] {path}")
            elif status[0] == "M" or status[1] == "M":
                formatted.append(f"  📝 [Изменён]      {path}")
            elif status[0] == "C" or status[1] == "C":
                formatted.append(f"  📋 [Скопирован]   {path}")
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
            args.append("--")
            args.append(file)

        code, out, err = self._run(args)
        if code != 0:
            return f"⚠️ Ошибка diff:\n{err}"
        if not out:
            return "📭 Нет изменений для отображения."

        lines = out.split("\n")
        if len(lines) > MAX_DIFF_LINES:
            out = (
                "\n".join(lines[:MAX_DIFF_LINES])
                + f"\n\n... и ещё {len(lines) - MAX_DIFF_LINES} строк."
            )

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

    def add(self, files: Optional[List[str]] = None, all_files: bool = False) -> str:
        """
        git add.

        Args:
            files: список конкретных файлов (или None)
            all_files: True → git add -A (все изменения, включая untracked)
                       False → git add -u (только изменённые)
        """
        if not self.ensure_repo():
            return "📂 Нет репозитория."

        if files:
            # Проверяем существование
            missing = []
            for f in files:
                fpath = self.repo_path / f
                if not fpath.exists():
                    missing.append(f)
            if missing:
                return f"⚠️ Файлы не найдены: {', '.join(missing)}"

            code, out, err = self._run(["add"] + files)
        else:
            flag = "-A" if all_files else "-u"
            code, out, err = self._run(["add", flag])

        if code != 0:
            return f"⚠️ Ошибка add:\n{err}"

        # Проверяем, что реально что-то добавилось
        code2, out2, _ = self._run(["diff", "--cached", "--stat"])
        if code2 == 0 and not out2.strip():
            return "📭 Нечего добавлять — нет изменений."

        return "✅ Файлы добавлены в индекс."

    def commit(self, message: str, allow_empty: bool = False) -> str:
        """git commit. Проверяет, что сообщение не пустое."""
        if not self.ensure_repo():
            return "📂 Нет репозитория."

        if not message or len(message.strip()) < 3:
            return "⚠️ Сообщение коммита слишком короткое. Напишите осмысленное описание."

        # Проверяем, что есть изменения в индексе
        code, out, _ = self._run(["diff", "--cached", "--stat"])
        if not out.strip() and not allow_empty:
            return "📭 Нет изменений в индексе. Сначала добавьте файлы через `git add`."

        # subprocess.run без shell=True — экранирование не нужно
        args = ["commit", "-m", message]
        if allow_empty:
            args.append("--allow-empty")

        code, out, err = self._run(args)
        if code != 0:
            return f"⚠️ Ошибка commit:\n{err}"

        _log(f"Коммит создан: {message}")
        _audit(f"commit: {message}")

        # Извлекаем хеш коммита
        hash_match = re.search(r"\[([^\]]+)\]", out)
        if hash_match:
            return f"✅ Коммит создан: [{hash_match.group(1)}] {message}"
        return f"✅ Коммит создан: {message}"

    def auto_commit(self, message: Optional[str] = None,
                    all_files: bool = False) -> str:
        """
        Автокоммит: add + commit с умным сообщением.

        Args:
            message: своё сообщение (или None — сгенерировать)
            all_files: True → добавлять и новые файлы (add -A)
        """
        if not self.ensure_repo():
            return "📂 Нет репозитория."

        # Проверяем, есть ли изменения
        code, out, _ = self._run(["status", "--short"])
        if not out.strip():
            return "📭 Нет изменений для коммита."

        # Добавляем изменения
        add_result = self.add(all_files=all_files)
        if "Ошибка" in add_result or "⚠️" in add_result:
            return add_result

        # Создаём сообщение
        if not message:
            message = self._generate_commit_message()

        return self.commit(message)

    def stash(self, action: str = "list", message: Optional[str] = None) -> str:
        """git stash. Только save/list/show/pop."""
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
            code, out, err = self._run(["stash", "pop"])
        else:
            return f"⚠️ Z не поддерживает `stash {action}` без подтверждения."

        if code != 0:
            return f"⚠️ Ошибка stash:\n{err}"

        if not out.strip():
            return "📭 Stash пуст."
        return f"📦 **Stash:**\n```\n{out}\n```"

    def get_repo_info(self) -> Dict[str, Any]:
        """Метаданные репозитория для контекста."""
        info: Dict[str, Any] = {
            "path": str(self.repo_path),
            "is_repo": self._is_git_repo(),
            "branch": "unknown",
            "last_commit": "unknown",
            "untracked": 0,
            "modified": 0,
            "staged": 0,
        }

        if not info["is_repo"]:
            return info

        code, out, _ = self._run(["rev-parse", "--abbrev-ref", "HEAD"])
        if code == 0:
            info["branch"] = out.strip()

        code, out, _ = self._run(["log", "-1", "--format=%h %s"])
        if code == 0 and out.strip():
            info["last_commit"] = out.strip()

        code, out, _ = self._run(["status", "--short"])
        if code == 0:
            for line in out.split("\n"):
                if not line.strip():
                    continue
                action = self._parse_status_line(line)
                if action == "add" and line.startswith("??"):
                    info["untracked"] += 1
                elif action == "add":
                    info["staged"] += 1
                elif action in ("update", "remove", "rename"):
                    info["modified"] += 1

        return info


# ========== УДОБНЫЕ ФУНКЦИИ ==========

def git_status(repo_path: Optional[str] = None) -> str:
    """Быстрый статус репозитория."""
    return GitManager(repo_path).status()


def git_diff(repo_path: Optional[str] = None, cached: bool = False) -> str:
    """Быстрый diff."""
    return GitManager(repo_path).diff(cached=cached)


def git_commit(repo_path: Optional[str] = None, message: str = "update from Z") -> str:
    """Быстрый коммит."""
    git = GitManager(repo_path)
    git.add()
    return git.commit(message)


def git_auto_commit(repo_path: Optional[str] = None,
                    all_files: bool = False) -> str:
    """Быстрый автокоммит с умным сообщением."""
    return GitManager(repo_path).auto_commit(all_files=all_files)


# ========== ТЕСТ ==========

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    print("🧪 Тест GitManager\n")
    print("=" * 60)

    try:
        git = GitManager("D:\\Zeta")
        print(f"✅ Git найден: {git.git_exe}")
    except GitNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    # --- Тест 1: Статус ---
    print("\n📝 Тест 1: Статус")
    print(git.status()[:300])

    # --- Тест 2: Информация ---
    print("\n📝 Тест 2: get_repo_info()")
    info = git.get_repo_info()
    for k, v in info.items():
        print(f"   {k}: {v}")

    # --- Тест 3: Ветки ---
    print("\n📝 Тест 3: Ветки")
    print(git.branch()[:300])

    # --- Тест 4: Анализ изменений ---
    print("\n📝 Тест 4: Анализ изменений")
    actions = git._analyze_changes()
    print(f"Действия: {actions}")
    print(f"Сообщение: {git._generate_commit_message()}")

    # --- Тест 5: Проверка безопасности ---
    print("\n📝 Тест 5: Проверка опасных команд")
    test_cases = [
        ["status"],                       # ✅ ok
        ["log", "--grep", "reset"],       # ✅ ok (теперь!)
        ["reset", "--hard"],              # 🛡️ блок
        ["push", "--force"],              # 🛡️ блок
        ["clean", "-fd"],                 # 🛡️ блок
        ["rebase", "main"],               # 🛡️ блок
        ["branch", "-d", "test"],         # 🛡️ блок (-d)
        ["log", "-p", "--follow"],        # ✅ ok
        ["diff", "--find-renames"],       # ✅ ok (был ложный блок на -f)
    ]
    for args in test_cases:
        try:
            git._check_safety(args)
            print(f"✅ git {' '.join(args)}")
        except GitSafetyError as e:
            print(f"🛡️ git {' '.join(args)} → {str(e).splitlines()[0]}")

    print("\n" + "=" * 60)
    print("✅ Тесты завершены!")