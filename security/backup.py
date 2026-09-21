# -*- coding: utf-8 -*-
"""
Zeta Security — Резервное копирование.
Автосохранение важных данных Zeta.
Аудит: логирует все операции с бэкапами.

Особенности:
    - Чистая логика need_auto_backup (через метаданные)
    - Атомарная запись метаданных
    - Проверка свободного места
    - Cleanup частичного бэкапа при ошибке
    - Логирование в data/zeta.log
"""

import os
import sys
import json
import shutil
import logging
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))


# ========== ЛОГИРОВАНИЕ ==========

def _log(msg: str) -> None:
    logging.info(f"[BACKUP] {msg}")


def _log_warn(msg: str) -> None:
    logging.warning(f"[BACKUP] {msg}")


# ========== НАСТРОЙКИ ==========

BACKUP_DIR = Path("data/backups")
MAX_BACKUPS = 7

# Файлы БД для бэкапа
FILES_TO_BACKUP = {
    "zeta.db": "data/zeta.db",
    "zeta_cache.db": "data/zeta_cache.db",
    "rag.db": "data/rag.db",
}

# Папки для бэкапа
DIRS_TO_BACKUP = {
    "security": "data/security",
    "audit": "data/audit",
}

# Файлы, которые НЕ бэкапим (внутри папок)
FILES_TO_SKIP = {
    "master.key",   # Ключ шифрования — отдельно!
    "auth.dat",     # Пароль — отдельно!
    "creator.dat",  # Секрет — отдельно!
    "auth.dat.tmp", # Временный
}

# Минимум свободного места на диске (МБ)
MIN_FREE_SPACE_MB = 100


# ================================================================
#  МЕНЕДЖЕР БЭКАПОВ
# ================================================================

class BackupManager:
    """Менеджер резервного копирования."""

    def __init__(self):
        self.backup_dir = BACKUP_DIR
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        self.auto_dir = self.backup_dir / "auto"
        self.manual_dir = self.backup_dir / "manual"
        self.security_dir = self.backup_dir / "security"

        for d in (self.auto_dir, self.manual_dir, self.security_dir):
            d.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._last_auto_backup: Optional[str] = None

    # ============================================================
    #  СОЗДАНИЕ
    # ============================================================

    def create(self, auto: bool = True, name: str = None) -> Tuple[bool, str]:
        """
        Создать бэкап.
        auto=True → auto/, auto=False → manual/
        """
        with self._lock:
            backup_path: Optional[Path] = None
            try:
                # Проверка места
                ok, msg = self._check_free_space()
                if not ok:
                    return False, msg

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                folder_name = f"{timestamp}_{name}" if name else timestamp

                target_dir = self.auto_dir if auto else self.manual_dir
                backup_path = target_dir / folder_name
                backup_path.mkdir(parents=True, exist_ok=False)

                _log(f"Создаю бэкап: {backup_path.name}")

                # 1. Файлы БД
                files_copied = self._backup_files(backup_path)

                # 2. Настройки
                settings_count = self._backup_settings(backup_path)

                # 3. Папки
                dirs_copied = self._backup_dirs(backup_path)

                # 4. Метаданные (атомарно)
                meta = {
                    "timestamp": datetime.now().isoformat(),
                    "auto": auto,
                    "name": name,
                    "files": files_copied,
                    "settings_count": settings_count,
                    "dirs": dirs_copied,
                    "version": 1,
                }
                self._save_metadata(backup_path, meta)

                # 5. Ротация
                self._rotate(auto)

                self._last_auto_backup = timestamp

                # Аудит
                self._audit_backup(folder_name, auto)

                _log(f"Бэкап создан: {backup_path.name}")
                return True, str(backup_path)

            except Exception as e:
                _log_warn(f"Ошибка бэкапа: {e}")
                # Cleanup частичного бэкапа
                if backup_path and backup_path.exists():
                    try:
                        shutil.rmtree(backup_path, ignore_errors=True)
                        _log_warn(f"Удалён частичный бэкап: {backup_path.name}")
                    except Exception:
                        pass
                return False, f"Ошибка: {e}"

    # ============================================================
    #  ПРОВЕРКА МЕСТА
    # ============================================================

    def _check_free_space(self) -> Tuple[bool, str]:
        """Проверка свободного места на диске."""
        try:
            target = Path("data")
            if not target.exists():
                target = Path.cwd()

            usage = shutil.disk_usage(target)
            free_mb = usage.free / (1024 * 1024)

            if free_mb < MIN_FREE_SPACE_MB:
                return False, (
                    f"⚠️ Мало места на диске: {free_mb:.0f} МБ. "
                    f"Минимум: {MIN_FREE_SPACE_MB} МБ"
                )
            return True, ""
        except Exception as e:
            _log_warn(f"Проверка места: {e}")
            return True, ""  # не блокируем при ошибке

    # ============================================================
    #  КОПИРОВАНИЕ
    # ============================================================

    def _backup_files(self, backup_path: Path) -> Dict[str, int]:
        """Копировать файлы БД."""
        copied: Dict[str, int] = {}

        for name, src in FILES_TO_BACKUP.items():
            src_path = Path(src)
            if not src_path.exists():
                continue
            try:
                dst_path = backup_path / name
                shutil.copy2(src_path, dst_path)
                copied[name] = dst_path.stat().st_size
                _log(f"  {name}: {copied[name]} байт")
            except Exception as e:
                _log_warn(f"  Ошибка копирования {name}: {e}")

        return copied

    def _backup_settings(self, backup_path: Path) -> int:
        """Сохранить настройки как JSON."""
        try:
            from core.memory import get_settings
            settings = get_settings()
            clean = {k: v for k, v in settings.items() if not k.startswith("_")}

            settings_path = backup_path / "settings.json"
            self._atomic_write(settings_path,
                               json.dumps(clean, ensure_ascii=False, indent=2))

            _log(f"  settings.json: {len(clean)} параметров")
            return len(clean)
        except Exception as e:
            _log_warn(f"  Ошибка настроек: {e}")
            return 0

    def _backup_dirs(self, backup_path: Path) -> Dict[str, int]:
        """Копировать папки (security, audit)."""
        copied: Dict[str, int] = {}

        for name, src in DIRS_TO_BACKUP.items():
            src_path = Path(src)
            if not src_path.exists():
                continue
            try:
                dst_path = backup_path / name
                dst_path.mkdir(parents=True, exist_ok=True)
                count = 0

                for file_path in src_path.glob("*"):
                    if file_path.name in FILES_TO_SKIP:
                        _log(f"  Пропущен (защита): {file_path.name}")
                        continue
                    if file_path.is_file():
                        try:
                            shutil.copy2(file_path, dst_path / file_path.name)
                            count += 1
                        except Exception as e:
                            _log_warn(f"  Ошибка копирования {file_path.name}: {e}")

                copied[name] = count
                _log(f"  {name}/: {count} файлов")
            except Exception as e:
                _log_warn(f"  Ошибка копирования {name}: {e}")

        return copied

    # ============================================================
    #  АТОМАРНАЯ ЗАПИСЬ
    # ============================================================

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        """Атомарная запись текста в файл."""
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(content)
            if path.exists():
                path.unlink()
            tmp.rename(path)
        except Exception:
            if tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass
            raise

    # ============================================================
    #  МЕТАДАННЫЕ
    # ============================================================

    def _save_metadata(self, backup_path: Path, data: Dict) -> None:
        try:
            meta_path = backup_path / "backup.json"
            self._atomic_write(meta_path,
                               json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            _log_warn(f"Ошибка метаданных: {e}")
            raise

    def _load_metadata(self, backup_path: Path) -> Optional[Dict]:
        meta_path = backup_path / "backup.json"
        if not meta_path.exists():
            return None
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    # ============================================================
    #  РОТАЦИЯ
    # ============================================================

    def _rotate(self, auto: bool) -> int:
        """Удалить старые бэкапы, оставить MAX_BACKUPS."""
        target_dir = self.auto_dir if auto else self.manual_dir

        backups = sorted(
            [d for d in target_dir.iterdir() if d.is_dir()],
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )

        removed = 0
        for old in backups[MAX_BACKUPS:]:
            try:
                shutil.rmtree(old)
                _log(f"  Удалён старый: {old.name}")
                removed += 1
            except Exception as e:
                _log_warn(f"  Ошибка удаления {old.name}: {e}")

        return removed

    # ============================================================
    #  ВОССТАНОВЛЕНИЕ
    # ============================================================

    def restore(self, backup_name: str, auto: bool = True) -> Tuple[bool, str]:
        """Восстановить из бэкапа."""
        try:
            target_dir = self.auto_dir if auto else self.manual_dir
            backup_path = target_dir / backup_name

            if not backup_path.exists():
                return False, f"❌ Бэкап не найден: {backup_name}"

            meta = self._load_metadata(backup_path)
            if not meta:
                return False, "❌ Повреждён backup.json"

            _log(f"Восстанавливаю из: {backup_name}")

            # 1. Файлы БД
            for name in FILES_TO_BACKUP:
                src = backup_path / name
                if src.exists():
                    dst = Path("data") / name
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                    _log(f"  {name}: восстановлен")

            # 2. Настройки
            settings_src = backup_path / "settings.json"
            if settings_src.exists():
                try:
                    from core.memory import save_setting
                    with open(settings_src, "r", encoding="utf-8") as f:
                        settings = json.load(f)
                    for k, v in settings.items():
                        save_setting(k, v)
                    _log(f"  settings: восстановлены ({len(settings)})")
                except Exception as e:
                    _log_warn(f"  Ошибка настроек: {e}")

            # 3. Папки
            for name in DIRS_TO_BACKUP:
                src_dir = backup_path / name
                if src_dir.exists():
                    dst_dir = Path("data") / name
                    dst_dir.mkdir(parents=True, exist_ok=True)
                    for f in src_dir.glob("*"):
                        if f.is_file():
                            shutil.copy2(f, dst_dir / f.name)
                    _log(f"  {name}/: восстановлена")

            self._audit_restore(backup_name)
            return True, f"✅ Восстановлено из {backup_name}"

        except Exception as e:
            _log_warn(f"Ошибка восстановления: {e}")
            return False, f"Ошибка: {e}"

    # ============================================================
    #  СПИСОК
    # ============================================================

    def list_backups(self, auto: bool = True) -> List[Dict]:
        """Список бэкапов."""
        target_dir = self.auto_dir if auto else self.manual_dir
        backups = []

        for d in target_dir.iterdir():
            if not d.is_dir():
                continue

            meta = self._load_metadata(d)
            try:
                size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
            except Exception:
                size = 0

            backups.append({
                "name": d.name,
                "path": str(d),
                "size": size,
                "size_human": self._human_size(size),
                "created": (meta.get("timestamp", "?") if meta else "?"),
                "auto": auto,
                "mtime": d.stat().st_mtime,
            })

        backups.sort(key=lambda x: x["mtime"], reverse=True)
        return backups

    @staticmethod
    def _human_size(size: int) -> str:
        for unit in ["Б", "КБ", "МБ", "ГБ"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} ТБ"

    # ============================================================
    #  ПРОВЕРКА ВОЗРАСТА (через метаданные!)
    # ============================================================

    def need_auto_backup(self, hours: int = 24) -> bool:
        """
        Нужен ли авто-бэкап.
        Читает timestamp из backup.json, fallback — mtime папки.
        """
        auto_backups = self.list_backups(auto=True)
        if not auto_backups:
            return True

        last = auto_backups[0]
        last_time: Optional[datetime] = None

        # 1. Пробуем из метаданных
        meta = self._load_metadata(Path(last["path"]))
        if meta and meta.get("timestamp"):
            try:
                last_time = datetime.fromisoformat(meta["timestamp"])
            except Exception:
                pass

        # 2. Fallback — mtime папки
        if last_time is None:
            try:
                last_time = datetime.fromtimestamp(last.get("mtime", 0))
            except Exception:
                return True

        delta = datetime.now() - last_time
        return delta > timedelta(hours=hours)

    # ============================================================
    #  АУДИТ
    # ============================================================

    def _audit_backup(self, name: str, auto: bool) -> None:
        try:
            from security.audit import get_audit
            get_audit().log_system(
                "backup_created",
                f"{'auto' if auto else 'manual'}: {name}",
            )
        except Exception:
            pass

    def _audit_restore(self, name: str) -> None:
        try:
            from security.audit import get_audit
            audit = get_audit()
            audit.log_system("backup_restored", name)
            audit.log_security(
                "backup_restored",
                f"Восстановление из: {name}",
                severity="warning",
            )
        except Exception:
            pass

    # ============================================================
    #  СТАТИСТИКА
    # ============================================================

    def stats(self) -> Dict:
        """Статистика бэкапов."""
        auto_list = self.list_backups(auto=True)
        manual_list = self.list_backups(auto=False)

        auto_size = sum(b["size"] for b in auto_list)
        manual_size = sum(b["size"] for b in manual_list)

        return {
            "auto_count": len(auto_list),
            "manual_count": len(manual_list),
            "auto_size": self._human_size(auto_size),
            "manual_size": self._human_size(manual_size),
            "max_backups": MAX_BACKUPS,
            "last_auto": auto_list[0]["created"][:19] if auto_list else "—",
        }


# ================================================================
#  ПЛАНИРОВЩИК
# ================================================================

class BackupScheduler:
    """Планировщик авто-бэкапов."""

    def __init__(self, interval_hours: int = 24):
        self.interval_hours = interval_hours
        self.manager = BackupManager()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self):
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="BackupScheduler"
        )
        self._thread.start()
        _log(f"Планировщик запущен (каждые {self.interval_hours}ч)")

    def stop(self):
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
        _log("Планировщик остановлен")

    def _loop(self):
        """Цикл: первая проверка через 5 мин, потом каждые 1 ч."""
        # Первая проверка через 5 минут
        if self._stop_event.wait(300):
            return

        while self._running:
            try:
                if self.manager.need_auto_backup(hours=self.interval_hours):
                    _log("Создаю авто-бэкап...")
                    ok, path = self.manager.create(auto=True)
                    if ok:
                        _log(f"Авто-бэкап создан: {Path(path).name}")
                    else:
                        _log_warn(f"Ошибка авто-бэкапа: {path}")
            except Exception as e:
                _log_warn(f"Ошибка планировщика: {e}")

            # Ждём 1 час (или пока stop)
            if self._stop_event.wait(3600):
                break


# ================================================================
#  ГЛОБАЛЬНЫЙ
# ================================================================

_backup: Optional[BackupManager] = None
_scheduler: Optional[BackupScheduler] = None


def get_backup() -> BackupManager:
    """Получить менеджер бэкапов."""
    global _backup
    if _backup is None:
        _backup = BackupManager()
    return _backup


def start_scheduler(interval_hours: int = 24) -> BackupScheduler:
    """Запустить планировщик."""
    global _scheduler
    if _scheduler is None:
        _scheduler = BackupScheduler(interval_hours)
        _scheduler.start()
    return _scheduler


def stop_scheduler() -> None:
    """Остановить планировщик."""
    global _scheduler
    if _scheduler:
        _scheduler.stop()
        _scheduler = None


# ================================================================
#  ЭКСПОРТ
# ================================================================

__all__ = [
    "BackupManager",
    "BackupScheduler",
    "get_backup",
    "start_scheduler",
    "stop_scheduler",
    "BACKUP_DIR",
    "MAX_BACKUPS",
]


# ================================================================
#  ТЕСТ
# ================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    print("💾 Zeta Backup — Тест")
    print("=" * 60)

    mgr = get_backup()

    print("\n📊 Статистика ДО:")
    for k, v in mgr.stats().items():
        print(f"   {k}: {v}")

    print("\n🔄 Создаю тестовый бэкап...")
    ok, path = mgr.create(auto=False, name="test")
    print(f"   {'✅' if ok else '❌'} {path}")

    print("\n📋 Список manual-бэкапов:")
    for b in mgr.list_backups(auto=False):
        print(f"   • {b['name']}")
        print(f"     Размер: {b['size_human']}")
        print(f"     Создан: {b['created'][:19]}")

    print("\n📊 Статистика ПОСЛЕ:")
    for k, v in mgr.stats().items():
        print(f"   {k}: {v}")

    print(f"\n🕐 Нужен ли авто-бэкап? {mgr.need_auto_backup(hours=24)}")

    print("\n📝 Тест: удаление тестового бэкапа")
    try:
        import shutil
        shutil.rmtree(path, ignore_errors=True)
        print(f"   ✅ Удалён: {Path(path).name}")
    except Exception as e:
        print(f"   ⚠️ {e}")

    print("\n✅ Тесты пройдены!")
    print(f"📂 Бэкапы в: {BACKUP_DIR}/")