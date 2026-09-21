# -*- coding: utf-8 -*-
"""
Zeta Security — Защита Git-команд.
Блокирует опасные операции, требующие подтверждения.
Аудит: логирует заблокированные команды.

Особенности:
    - --force-with-lease → CAUTION (безопаснее --force)
    - config --global user.* → SAFE (базовая настройка)
    - _blocked_attempts — ring buffer (100 записей)
    - fetch --prune → CAUTION
    - commit без -m → CAUTION (открывает редактор)
"""

import re
import sys
import logging
from pathlib import Path
from typing import Tuple, List
from datetime import datetime
from enum import Enum

sys.path.insert(0, str(Path(__file__).parent.parent))


# ========== ЛОГИРОВАНИЕ ==========

def _log(msg: str) -> None:
    logging.info(f"[GIT-GUARD] {msg}")


def _log_warn(msg: str) -> None:
    logging.warning(f"[GIT-GUARD] {msg}")


# ========== УРОВНИ ==========

class DangerLevel(Enum):
    """Уровень опасности команды."""
    SAFE = "safe"
    CAUTION = "caution"
    DANGEROUS = "dangerous"
    BLOCKED = "blocked"


# ========== GIT GUARD ==========

class GitGuard:
    """Защита Git-команд."""

    # Максимум записей в _blocked_attempts
    MAX_BLOCKED_HISTORY = 100

    # ========== ЗАБЛОКИРОВАННЫЕ (безвозвратные) ==========
    BLOCKED_PATTERNS = [
        r"push\s+.*--force\b(?!-with-lease)",   # --force, но НЕ --force-with-lease
        r"push\s+-f\b",
        r"reset\s+--hard",
        r"clean\s+-fdx",
        r"clean\s+-xdf",
        r"clean\s+-f\b.*-d\b.*-x\b",            # -f -d -x в любом порядке
        r"filter-branch",
        r"filter-repo",
        r"push\s+.*--delete",
        r"push\s+.*\s+:\S+",                    # push origin :branch
        r"update-ref\s+-d",
        r"update-ref\s+--delete",
        r"reflog\s+expire",
        r"gc\s+--prune=now",
        r"gc\s+--aggressive\s+--prune=now",
        r"rebase\s+.*--root",
        r"rebase\s+-i\s+.*--root",
        r"rm\s+-rf\s+\.git",
        r"del\s+/[fsq]\s+.*\.git",
        r"config\s+--global\s+.*credential",    # credential.helper и т.п.
    ]

    # ========== ОПАСНЫЕ (требуют подтверждения) ==========
    CAUTION_PATTERNS = [
        r"push\s+.*--force-with-lease",         # безопаснее --force, но всё же
        r"reset\s+--soft",
        r"reset\s+--mixed",
        r"rebase\b",
        r"cherry-pick",
        r"revert",
        r"stash\s+drop",
        r"stash\s+clear",
        r"tag\s+-d\b",
        r"commit\s+--amend",
        r"checkout\s+--\s+\.",
        r"restore\s+--staged\s+--worktree",
        r"fetch\s+.*--prune",                   # prune может удалить ссылки
        r"fetch\s+.*--all\s+.*--force",         # принудительное обновление
        r"^commit\s*$",                         # без -m открывает редактор
        r"^commit\s+-[^m]",                     # флаги без -m
    ]

    # ========== БЕЗОПАСНЫЕ ==========
    SAFE_PATTERNS = [
        r"^status\b",
        r"^diff\b",
        r"^log\b",
        r"^branch$",
        r"^branch\s+--list",
        r"^branch\s+-a\b",
        r"^branch\s+-r\b",
        r"^branch\s+-v\b",
        r"^show\b",
        r"^remote\s+-v",
        r"^remote\s+show",
        r"^config\s+--list",
        r"^config\s+--global\s+user\.",         # базовые настройки
        r"^config\s+--global\s+core\.editor",
        r"^config\s+--global\s+init\.defaultbranch",
        r"^fetch\b(?!.*--prune)(?!.*--force)",  # fetch без prune/force
        r"^pull\b(?!.*--force)(?!.*--rebase)",  # pull без force/rebase
        r"^add\b",
        r"^commit\s+-m\b",                      # только с -m!
        r"^stash\s+save",
        r"^stash\s+list",
        r"^stash\s+show",
        r"^stash\s+pop",
        r"^tag\s+-l",
        r"^tag\s+--list",
        r"^blame\b",
        r"^describe\b",
        r"^rev-parse\b",
        r"^ls-files\b",
        r"^diff\s+--stat",
        r"^log\s+--oneline",
    ]

    _blocked_attempts: List[dict] = []

    # ================================================================
    #  ПРОВЕРКА
    # ================================================================

    @classmethod
    def check(cls, command: str) -> Tuple[DangerLevel, str]:
        """Проверяет команду на опасность."""
        if not command or not command.strip():
            return DangerLevel.SAFE, ""

        cmd = command.strip()
        cmd_lower = cmd.lower()

        # === СПЕЦИАЛЬНАЯ ПРОВЕРКА: branch -D vs -d ===
        if re.match(r"^branch\s+-D(?![a-zA-Z])", cmd):
            cls._log_blocked(command, "branch -D")
            return (
                DangerLevel.BLOCKED,
                f"🚫 Команда заблокирована:\n"
                f"   `git {command}`\n\n"
                f"⚠️ Флаг `-D` принудительно удаляет ветку без проверки.\n"
                f"Используй `-d` для безопасного удаления.",
            )

        if re.match(r"^branch\s+-d(?![a-zA-Z])", cmd):
            return (
                DangerLevel.DANGEROUS,
                f"⚠️ Опасная команда: `git {command}`\n\n"
                f"Удаление ветки. Продолжить?",
            )

        # === 1. ЗАБЛОКИРОВАННЫЕ ===
        for pattern in cls.BLOCKED_PATTERNS:
            if re.search(pattern, cmd_lower, re.IGNORECASE):
                cls._log_blocked(command, pattern)
                return (
                    DangerLevel.BLOCKED,
                    f"🚫 Команда заблокирована:\n"
                    f"   `git {command}`\n\n"
                    f"⚠️ Эта операция может уничтожить данные безвозвратно.\n"
                    f"Сделай вручную в терминале.",
                )

        # === 2. ОПАСНЫЕ ===
        for pattern in cls.CAUTION_PATTERNS:
            if re.search(pattern, cmd_lower, re.IGNORECASE):
                return (
                    DangerLevel.DANGEROUS,
                    f"⚠️ Опасная команда: `git {command}`\n\n"
                    f"Она может изменить историю или удалить данные.\n"
                    f"Продолжить? (да/нет)",
                )

        # === 3. БЕЗОПАСНЫЕ ===
        for pattern in cls.SAFE_PATTERNS:
            if re.search(pattern, cmd_lower, re.IGNORECASE):
                return DangerLevel.SAFE, ""

        # === 4. НЕИЗВЕСТНЫЕ ===
        return (
            DangerLevel.CAUTION,
            f"🤔 Неизвестная команда: `git {command}`\n"
            f"Уверен, что хочешь выполнить?",
        )

    # ================================================================
    #  ЛОГИРОВАНИЕ (с аудитом)
    # ================================================================

    @classmethod
    def _log_blocked(cls, command: str, pattern: str) -> None:
        """Логирует блокировку (ring buffer)."""
        cls._blocked_attempts.append({
            "timestamp": datetime.now().isoformat(),
            "command": command[:200],
            "pattern": pattern[:100],
        })

        # Ring buffer: не более MAX_BLOCKED_HISTORY
        if len(cls._blocked_attempts) > cls.MAX_BLOCKED_HISTORY:
            cls._blocked_attempts = cls._blocked_attempts[-cls.MAX_BLOCKED_HISTORY:]

        _log_warn(f"ЗАБЛОКИРОВАНО: {command[:80]}")

        # Аудит
        try:
            from security.audit import get_audit
            get_audit().log_blocked_command(command, pattern)
        except Exception:
            pass

    @classmethod
    def get_blocked_attempts(cls) -> List[dict]:
        return cls._blocked_attempts.copy()

    # ================================================================
    #  УТИЛИТЫ
    # ================================================================

    @classmethod
    def is_safe(cls, command: str) -> bool:
        level, _ = cls.check(command)
        return level == DangerLevel.SAFE

    @classmethod
    def requires_confirmation(cls, command: str) -> bool:
        level, _ = cls.check(command)
        return level in (DangerLevel.DANGEROUS, DangerLevel.CAUTION)

    @classmethod
    def is_blocked(cls, command: str) -> bool:
        level, _ = cls.check(command)
        return level == DangerLevel.BLOCKED

    @classmethod
    def stats(cls) -> dict:
        return {
            "blocked_patterns": len(cls.BLOCKED_PATTERNS),
            "caution_patterns": len(cls.CAUTION_PATTERNS),
            "safe_patterns": len(cls.SAFE_PATTERNS),
            "blocked_attempts": len(cls._blocked_attempts),
            "max_history": cls.MAX_BLOCKED_HISTORY,
        }


# ========== ЭКСПОРТ ==========

__all__ = ["DangerLevel", "GitGuard"]


# ========== ТЕСТ ==========

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    print("🛡️  GitGuard — Тест защиты Git-команд")
    print("=" * 60)

    tests = [
        # SAFE
        ("status", DangerLevel.SAFE),
        ("log", DangerLevel.SAFE),
        ("log --oneline", DangerLevel.SAFE),
        ("diff", DangerLevel.SAFE),
        ("diff --stat", DangerLevel.SAFE),
        ("branch", DangerLevel.SAFE),
        ("branch -a", DangerLevel.SAFE),
        ("fetch", DangerLevel.SAFE),
        ("pull", DangerLevel.SAFE),
        ("add .", DangerLevel.SAFE),
        ("commit -m 'test'", DangerLevel.SAFE),
        ("config --global user.name 'Самир'", DangerLevel.SAFE),
        ("config --global user.email 'x@y.z'", DangerLevel.SAFE),

        # DANGEROUS / CAUTION
        ("reset --soft HEAD~1", DangerLevel.DANGEROUS),
        ("rebase main", DangerLevel.DANGEROUS),
        ("cherry-pick abc123", DangerLevel.DANGEROUS),
        ("stash drop", DangerLevel.DANGEROUS),
        ("branch -d feature", DangerLevel.DANGEROUS),
        ("commit --amend", DangerLevel.DANGEROUS),
        ("push --force-with-lease", DangerLevel.DANGEROUS),  # ← было BLOCKED
        ("fetch --prune", DangerLevel.DANGEROUS),            # ← было SAFE
        ("commit", DangerLevel.DANGEROUS),                   # ← без -m
        ("pull --rebase", DangerLevel.DANGEROUS),            # ← rebase

        # BLOCKED
        ("push --force", DangerLevel.BLOCKED),
        ("push -f", DangerLevel.BLOCKED),
        ("reset --hard HEAD~5", DangerLevel.BLOCKED),
        ("clean -fdx", DangerLevel.BLOCKED),
        ("branch -D main", DangerLevel.BLOCKED),
        ("filter-branch --all", DangerLevel.BLOCKED),
        ("push origin :main", DangerLevel.BLOCKED),
        ("gc --prune=now", DangerLevel.BLOCKED),
    ]

    passed = 0
    failed = 0

    for cmd, expected in tests:
        level, msg = GitGuard.check(cmd)
        status = "✅" if level == expected else "❌"
        if level == expected:
            passed += 1
        else:
            failed += 1
        print(f"   {status} [{level.value:10s}] git {cmd}")
        if level != expected:
            print(f"      Ожидалось: {expected.value}")

    print("\n" + "=" * 60)
    print(f"📊 Результат: {passed} ✅ / {failed} ❌")
    print(f"📈 Статистика: {GitGuard.stats()}")

    if failed == 0:
        print("\n🎉 Все тесты пройдены!")
    else:
        print(f"\n⚠️  Есть ошибки: {failed}")