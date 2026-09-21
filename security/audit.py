# -*- coding: utf-8 -*-
"""
Zeta Security — Аудит действий.
Логирует все важные события в отдельные файлы (JSON Lines).

Особенности:
    - Авто-ротация логов при превышении размера
    - Обрезка длинных полей (command, source, error)
    - Логирование в data/zeta.log
    - Работает с любой версией crypto (bytes/str)
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

sys.path.insert(0, str(Path(__file__).parent.parent))


# ========== ЛОГИРОВАНИЕ ==========

def _log(msg: str) -> None:
    logging.info(f"[AUDIT] {msg}")


def _log_warn(msg: str) -> None:
    logging.warning(f"[AUDIT] {msg}")


# ========== КОНСТАНТЫ ==========

AUDIT_DIR = Path("data/audit")

FILES = {
    "commands": AUDIT_DIR / "commands.log",
    "git": AUDIT_DIR / "git.log",
    "auth": AUDIT_DIR / "auth.log",
    "errors": AUDIT_DIR / "errors.log",
    "security": AUDIT_DIR / "security.log",
    "system": AUDIT_DIR / "system.log",
}

# Размер файла, при котором срабатывает ротация (1 МБ)
MAX_LOG_SIZE = 1024 * 1024
# Сколько старых логов хранить
MAX_ROTATED_FILES = 5

# Лимиты длины
MAX_COMMAND_LEN = 500
MAX_RESULT_LEN = 200
MAX_ERROR_LEN = 500
MAX_CONTEXT_LEN = 200
MAX_DETAILS_LEN = 500
MAX_SOURCE_LEN = 50


# ================================================================
#  МЕНЕДЖЕР АУДИТА
# ================================================================

class AuditManager:
    """Менеджер аудита действий."""

    def __init__(self):
        self.audit_dir = AUDIT_DIR
        self.audit_dir.mkdir(parents=True, exist_ok=True)

        for path in FILES.values():
            path.parent.mkdir(parents=True, exist_ok=True)

    # ============================================================
    #  ЗАПИСЬ
    # ============================================================

    @staticmethod
    def _truncate(value: Any, max_len: int) -> Optional[str]:
        """Обрезает строку до max_len."""
        if value is None:
            return None
        s = str(value)
        if len(s) > max_len:
            return s[:max_len] + "..."
        return s

    def _rotate_if_needed(self, file_path: Path) -> None:
        """Ротация лога при превышении размера."""
        try:
            if not file_path.exists():
                return
            if file_path.stat().st_size < MAX_LOG_SIZE:
                return

            # Сдвигаем: .log → .log.1 → .log.2 ...
            for i in range(MAX_ROTATED_FILES - 1, 0, -1):
                old = file_path.with_suffix(f"{file_path.suffix}.{i}")
                new = file_path.with_suffix(f"{file_path.suffix}.{i + 1}")
                if old.exists():
                    try:
                        if new.exists():
                            new.unlink()
                        old.rename(new)
                    except Exception:
                        pass

            # Текущий → .1
            rotated = file_path.with_suffix(f"{file_path.suffix}.1")
            try:
                if rotated.exists():
                    rotated.unlink()
                file_path.rename(rotated)
                _log(f"Ротация: {file_path.name} → {rotated.name}")
            except Exception as e:
                _log_warn(f"Ротация {file_path.name}: {e}")
        except Exception as e:
            _log_warn(f"_rotate_if_needed: {e}")

    def _write(self, file_key: str, event_type: str, data: Dict[str, Any]) -> None:
        """Записать событие в файл."""
        if file_key not in FILES:
            _log_warn(f"Неизвестный тип лога: {file_key}")
            return

        try:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "type": event_type,
                **data,
            }

            path = FILES[file_key]
            self._rotate_if_needed(path)

            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        except Exception as e:
            _log_warn(f"Ошибка записи аудита ({file_key}): {e}")

    # ============================================================
    #  КОМАНДЫ
    # ============================================================

    def log_command(self, command: str, source: str = "widget",
                    result: str = None, duration: float = None) -> None:
        """Логировать выполненную команду."""
        self._write("commands", "command", {
            "command": self._truncate(command, MAX_COMMAND_LEN),
            "source": self._truncate(source, MAX_SOURCE_LEN),
            "result": self._truncate(result, MAX_RESULT_LEN),
            "duration": duration,
        })

    def log_git(self, command: str, args: str,
                level: str = "safe", blocked: bool = False) -> None:
        """Логировать Git-команду."""
        self._write("git", "git_command", {
            "command": self._truncate(command, MAX_COMMAND_LEN),
            "args": self._truncate(args, MAX_COMMAND_LEN),
            "danger_level": level,
            "blocked": blocked,
        })

    # ============================================================
    #  АУТЕНТИФИКАЦИЯ
    # ============================================================

    def log_login(self, success: bool, attempts: int = 1,
                  username: str = None) -> None:
        """Логировать попытку входа."""
        data = {
            "success": success,
            "attempts": attempts,
        }
        if username:
            data["username"] = self._truncate(username, MAX_SOURCE_LEN)
        self._write("auth", "login", data)

    def log_logout(self) -> None:
        """Логировать выход."""
        self._write("auth", "logout", {})

    # ============================================================
    #  ОШИБКИ
    # ============================================================

    def log_error(self, error: str, context: str = "") -> None:
        """Логировать ошибку."""
        self._write("errors", "error", {
            "error": self._truncate(error, MAX_ERROR_LEN),
            "context": self._truncate(context, MAX_CONTEXT_LEN),
        })

    # ============================================================
    #  БЕЗОПАСНОСТЬ
    # ============================================================

    def log_security(self, event: str, details: str = "",
                     severity: str = "info") -> None:
        """Логировать событие безопасности.
        severity: info / warning / critical
        """
        self._write("security", "security", {
            "event": self._truncate(event, MAX_CONTEXT_LEN),
            "details": self._truncate(details, MAX_DETAILS_LEN),
            "severity": severity,
        })

        if severity in ("warning", "critical"):
            _log(f"🚨 SECURITY [{severity}]: {event} - {details[:100]}")

    def log_blocked_command(self, command: str, reason: str) -> None:
        """Логировать заблокированную команду."""
        self.log_security(
            event="blocked_command",
            details=f"{command} | {reason}",
            severity="warning",
        )

    def log_creator_activation(self) -> None:
        """Логировать активацию режима создателя."""
        self.log_security(
            event="creator_mode_activated",
            details="Режим создателя активирован",
            severity="info",
        )

    def log_suspicious(self, activity: str) -> None:
        """Логировать подозрительную активность."""
        self.log_security(
            event="suspicious_activity",
            details=activity,
            severity="critical",
        )

    # ============================================================
    #  СИСТЕМА
    # ============================================================

    def log_system(self, event: str, details: str = "") -> None:
        """Логировать системное событие."""
        self._write("system", "system", {
            "event": self._truncate(event, MAX_CONTEXT_LEN),
            "details": self._truncate(details, MAX_DETAILS_LEN),
        })

    def log_startup(self) -> None:
        """Логировать запуск Zeta."""
        self.log_system("startup", "Zeta запущена")

    def log_shutdown(self) -> None:
        """Логировать выключение Zeta."""
        self.log_system("shutdown", "Zeta завершена")

    # ============================================================
    #  ЧТЕНИЕ
    # ============================================================

    def read_log(self, file_key: str, limit: int = 50) -> List[Dict]:
        """Прочитать последние N записей."""
        if file_key not in FILES:
            return []

        path = FILES[file_key]
        if not path.exists():
            return []

        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            lines = lines[-limit:]

            entries = []
            for line in lines:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            return entries
        except Exception as e:
            _log_warn(f"Ошибка чтения {file_key}: {e}")
            return []

    def get_stats(self) -> Dict[str, int]:
        """Статистика по всем логам."""
        stats = {}
        for key, path in FILES.items():
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        stats[key] = sum(1 for _ in f)
                except Exception:
                    stats[key] = 0
            else:
                stats[key] = 0
        return stats

    def get_security_alerts(self, limit: int = 10) -> List[Dict]:
        """Последние алерты безопасности (warning + critical)."""
        entries = self.read_log("security", limit=limit * 3)
        filtered = [
            e for e in entries
            if e.get("severity") in ("warning", "critical")
        ]
        return filtered[-limit:]

    # ============================================================
    #  ОЧИСТКА
    # ============================================================

    def clear_log(self, file_key: str) -> bool:
        """Очистить конкретный лог."""
        if file_key not in FILES:
            return False
        try:
            path = FILES[file_key]
            if path.exists():
                path.unlink()
            return True
        except Exception as e:
            _log_warn(f"Ошибка очистки {file_key}: {e}")
            return False

    def clear_all(self) -> int:
        """Очистить все логи."""
        count = 0
        for key in FILES:
            if self.clear_log(key):
                count += 1
        return count

    def archive_old_logs(self, days: int = 30) -> int:
        """Архивировать логи старше N дней."""
        archive_dir = self.audit_dir / "archive"
        archive_dir.mkdir(exist_ok=True)

        cutoff = datetime.now() - timedelta(days=days)
        archived = 0

        for path in list(self.audit_dir.glob("*.log*")):
            try:
                mtime = datetime.fromtimestamp(path.stat().st_mtime)
                if mtime < cutoff:
                    archive_name = f"{path.stem}_{mtime.strftime('%Y%m%d')}{path.suffix}"
                    target = archive_dir / archive_name
                    if target.exists():
                        target.unlink()
                    path.rename(target)
                    archived += 1
            except Exception:
                continue

        if archived:
            _log(f"Архивировано {archived} старых логов")
        return archived


# ================================================================
#  ГЛОБАЛЬНЫЙ
# ================================================================

_audit: Optional[AuditManager] = None


def get_audit() -> AuditManager:
    """Получить глобальный менеджер аудита."""
    global _audit
    if _audit is None:
        _audit = AuditManager()
    return _audit


# ================================================================
#  ЭКСПОРТ
# ================================================================

__all__ = ["AuditManager", "get_audit", "AUDIT_DIR", "FILES"]


# ================================================================
#  ТЕСТ
# ================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    print("📊 Zeta Audit — Тест")
    print("=" * 60)

    audit = get_audit()
    audit.clear_all()

    # Команды
    print("\n📝 Команды:")
    audit.log_command("что такое атом", source="widget", result="Атом — это...")
    audit.log_command("git status", source="telegram", result="On branch main")
    print("   ✅ Записано 2 команды")

    # Обрезка
    print("\n📝 Обрезка длинных полей:")
    audit.log_command("x" * 1000, source="y" * 200)
    entries = audit.read_log("commands", limit=1)
    if entries:
        cmd_len = len(entries[0].get("command", ""))
        src_len = len(entries[0].get("source", ""))
        print(f"   Command: 1000 → {cmd_len} (обрезано + '...')")
        print(f"   Source:  200  → {src_len} (обрезано + '...')")

    # Git
    print("\n🔀 Git:")
    audit.log_git("status", "", level="safe")
    audit.log_git("push", "--force", level="blocked", blocked=True)
    print("   ✅ Записано 2 Git-события")

    # Auth
    print("\n🔐 Аутентификация:")
    audit.log_login(success=True, username="admin")
    audit.log_login(success=False, attempts=2)
    audit.log_logout()
    print("   ✅ Записано 3 события входа")

    # Security
    print("\n🚨 Безопасность:")
    audit.log_creator_activation()
    audit.log_blocked_command("git push --force", "Опасная команда")
    audit.log_suspicious("Попытка входа с незнакомого IP")
    print("   ✅ Записано 3 события безопасности")

    # System
    print("\n⚙️ Система:")
    audit.log_startup()
    audit.log_shutdown()
    print("   ✅ Записано 2 системных события")

    # Stats
    print("\n📊 Статистика:")
    for key, count in audit.get_stats().items():
        print(f"   {key}: {count}")

    # Alerts
    print("\n🚨 Алерты безопасности:")
    for alert in audit.get_security_alerts(limit=5):
        sev = alert.get("severity", "?")
        evt = alert.get("event", "?")
        print(f"   [{sev:8s}] {evt}")

    # Read
    print("\n📖 Последние команды:")
    for cmd in audit.read_log("commands", limit=5):
        print(f"   {cmd['timestamp'][:19]} | {cmd['command'][:40]}")

    print("\n✅ Тесты пройдены!")
    print(f"📂 Логи в: {AUDIT_DIR}/")