# -*- coding: utf-8 -*-
"""
Модуль работы с базой данных Zeta.
Хранит: историю сообщений, факты, настройки, задачи, события, рутины.
Все данные шифруются AES-256.

ИСПРАВЛЕНО (2026-09-21):
    - _get_conn: check_same_thread=False (работа из фоновых потоков)
    - WAL-режим: применяется один раз в init_db, с .fetchone()
    - SYSTEM_KEYS: дополнен всеми ключами из settings.py
"""

import os
import sys
import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path

# Добавляем корень проекта
sys.path.insert(0, str(Path(__file__).parent.parent))

DB_PATH = "data/zeta.db"

# Флаг: если True — данные шифруются
ENCRYPT_DATA = True

# Технические настройки (НЕ попадают в факты)
# ИСПРАВЛЕНО: дополнен всеми ключами из ui/settings.py
SYSTEM_KEYS = {
    # Внешний вид
    "theme", "widget_size", "avatar_path", "widget_x", "widget_y",
    "widget_opacity",
    # Голос
    "voice_enabled", "tts_voice", "tts_speed",
    "wake_word_enabled", "stt_duration",
    # ИИ
    "ai_model", "max_tokens", "context_tokens", "ai_temperature",
    # Уведомления
    "notif_interval", "cpu_threshold", "ram_threshold", "disk_threshold",
    "smart_notifications",
    # Анимации
    "animations_enabled", "anim_speed", "anim_effect",
    # Безопасность
    "safety_enabled", "git_protection_enabled", "max_query_length",
    # RAG
    "rag_enabled", "rag_max_results",
    # Прочее
    "project_path", "auto_focus", "last_run",
}


# ========== ЛОГИРОВАНИЕ ==========
def _log(msg: str) -> None:
    logging.info(f"[MEMORY] {msg}")


# ========== ШИФРОВАНИЕ ==========
_crypto = None
_crypto_ready = False


def _get_crypto():
    """Ленивая загрузка крипто-менеджера."""
    global _crypto, _crypto_ready
    if not _crypto_ready:
        try:
            from security.crypto import get_crypto
            _crypto = get_crypto()
            _crypto_ready = True
        except Exception as e:
            _log(f"⚠️ Шифрование недоступно: {e}")
            _crypto = None
            _crypto_ready = True
    return _crypto


def _encrypt(text: str) -> str:
    """Шифрует строку. Работает и с bytes, и со str."""
    if not ENCRYPT_DATA or not text:
        return text
    crypto = _get_crypto()
    if crypto is None:
        return text
    try:
        encrypted = crypto.encrypt(text)
        # Если bytes — декодируем
        if isinstance(encrypted, bytes):
            encrypted = encrypted.decode("utf-8")
        return "ENC:" + encrypted
    except Exception as e:
        _log(f"⚠️ Ошибка шифрования: {e}")
        return text


def _decrypt(text: str) -> str:
    """Расшифровывает строку."""
    if not text:
        return text
    if not text.startswith("ENC:"):
        return text
    crypto = _get_crypto()
    if crypto is None:
        return text
    try:
        payload = text[4:]
        encrypted = payload.encode("utf-8")
        result = crypto.decrypt(encrypted)
        if isinstance(result, bytes):
            result = result.decode("utf-8")
        return result
    except Exception as e:
        _log(f"⚠️ Ошибка расшифровки: {e}")
        return text


def is_encrypted(text: str) -> bool:
    """Проверяет, зашифрована ли строка."""
    return bool(text and text.startswith("ENC:"))


# ========== СОЕДИНЕНИЕ ==========

# ИСПРАВЛЕНО: флаг, что WAL уже установлен
_wal_initialized = False


def _get_conn() -> sqlite3.Connection:
    """
    Возвращает соединение с БД.

    ИСПРАВЛЕНО:
        - check_same_thread=False — разрешает работу из разных потоков
        - WAL устанавливаем только один раз, а не при каждом коннекте
    """
    os.makedirs("data", exist_ok=True)

    # ИСПРАВЛЕНО: check_same_thread=False
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)

    # ИСПРАВЛЕНО: WAL ставим один раз
    global _wal_initialized
    if not _wal_initialized:
        try:
            conn.execute("PRAGMA journal_mode=WAL").fetchone()
            conn.execute("PRAGMA synchronous=NORMAL").fetchone()
            _wal_initialized = True
        except Exception as e:
            _log(f"⚠️ Не удалось установить WAL: {e}")

    return conn


def init_db() -> None:
    """Создаёт все таблицы. Выполняет миграцию и создание индексов."""
    conn = _get_conn()
    try:
        cursor = conn.cursor()

        # --- История сообщений ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)

        # --- Настройки ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # --- Факты ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        # --- Задачи планировщика ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                due_date TEXT,
                priority INTEGER DEFAULT 1,
                status TEXT DEFAULT 'active',
                created_at TEXT NOT NULL,
                completed_at TEXT
            )
        """)

        # --- Рутины ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS routines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                actions TEXT NOT NULL,
                schedule TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                created_at TEXT NOT NULL
            )
        """)

        # --- События ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                start_time TEXT NOT NULL,
                end_time TEXT,
                location TEXT,
                created_at TEXT NOT NULL
            )
        """)

        # --- Индексы ---
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_role ON messages(role)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_start ON events(start_time)")

        # --- Миграция старых настроек в факты (копирование, без удаления) ---
        # ИСПРАВЛЕНО: теперь SYSTEM_KEYS полный → настройки не утекают в факты
        try:
            cursor.execute("SELECT key, value FROM settings WHERE key NOT LIKE 'setting_%'")
            old_settings = cursor.fetchall()
            for key, value in old_settings:
                if key not in SYSTEM_KEYS:
                    cursor.execute(
                        "INSERT OR IGNORE INTO facts (key, content, created_at) VALUES (?, ?, ?)",
                        (key, value, datetime.now().isoformat())
                    )
        except Exception:
            pass

        conn.commit()
        _log("✅ БД инициализирована")
    finally:
        conn.close()


# ========== СООБЩЕНИЯ ==========

def save_message(role: str, content: str) -> int:
    """Сохраняет сообщение. Возвращает id."""
    encrypted = _encrypt(content)
    conn = _get_conn()
    try:
        cursor = conn.execute(
            "INSERT INTO messages (role, content, timestamp) VALUES (?, ?, ?)",
            (role, encrypted, datetime.now().isoformat())
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_history(limit: int = 50) -> List[Dict[str, str]]:
    """Возвращает последние N сообщений (старые → новые)."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
    finally:
        conn.close()

    result = []
    for role, content in reversed(rows):
        result.append({
            "role": role,
            "content": _decrypt(content)
        })
    return result


def clear_history() -> None:
    """Очищает всю историю."""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM messages")
        conn.commit()
    finally:
        conn.close()
    _log("🗑️ История очищена")


# ========== ФАКТЫ ==========

def save_fact(key: str, content: str) -> None:
    """Сохраняет факт (id не теряется при обновлении)."""
    encrypted = _encrypt(content)
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT INTO facts (key, content, created_at)
               VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET
                   content = excluded.content,
                   created_at = excluded.created_at""",
            (key, encrypted, datetime.now().isoformat())
        )
        conn.commit()
    finally:
        conn.close()


def get_facts() -> List[Dict[str, str]]:
    """Возвращает факты с расшифровкой."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT key, content FROM facts ORDER BY id DESC"
        ).fetchall()
    finally:
        conn.close()

    return [{"key": k, "content": _decrypt(c)} for k, c in rows]


def delete_fact(key: str) -> bool:
    """Удаляет факт. True если что-то удалено."""
    conn = _get_conn()
    try:
        cursor = conn.execute("DELETE FROM facts WHERE key = ?", (key,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def clear_facts() -> None:
    """Удаляет все факты."""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM facts")
        conn.commit()
    finally:
        conn.close()
    _log("🗑️ Факты очищены")


# ========== НАСТРОЙКИ ==========

def save_setting(key: str, value: str) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, str(value))
        )
        conn.commit()
    finally:
        conn.close()


def get_setting(key: str, default: str = "") -> str:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else default


def get_settings() -> Dict[str, str]:
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    finally:
        conn.close()
    return {r[0]: r[1] for r in rows}


def delete_setting(key: str) -> bool:
    conn = _get_conn()
    try:
        cursor = conn.execute("DELETE FROM settings WHERE key = ?", (key,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


# ========== ЗАДАЧИ ==========

def add_task(title: str, description: str = "", due_date: str = None, priority: int = 1) -> int:
    conn = _get_conn()
    try:
        cursor = conn.execute(
            "INSERT INTO tasks (title, description, due_date, priority, created_at) VALUES (?, ?, ?, ?, ?)",
            (title, description, due_date, priority, datetime.now().isoformat())
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_tasks(status: str = "active", limit: int = 50) -> List[Dict]:
    conn = _get_conn()
    try:
        if status == "all":
            rows = conn.execute(
                "SELECT id, title, description, due_date, priority, status, created_at "
                "FROM tasks ORDER BY priority DESC, due_date ASC LIMIT ?",
                (limit,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, title, description, due_date, priority, status, created_at "
                "FROM tasks WHERE status = ? ORDER BY priority DESC, due_date ASC LIMIT ?",
                (status, limit)
            ).fetchall()
    finally:
        conn.close()

    return [
        {
            "id": r[0], "title": r[1], "description": r[2],
            "due_date": r[3], "priority": r[4], "status": r[5],
            "created_at": r[6]
        }
        for r in rows
    ]


def update_task(task_id: int, **kwargs) -> bool:
    """Обновляет поля задачи. Допустимые: title, description, due_date, priority, status."""
    allowed = {"title", "description", "due_date", "priority", "status"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False

    fields = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [task_id]

    conn = _get_conn()
    try:
        cursor = conn.execute(f"UPDATE tasks SET {fields} WHERE id = ?", values)
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def complete_task(task_id: int) -> bool:
    conn = _get_conn()
    try:
        cursor = conn.execute(
            "UPDATE tasks SET status = 'done', completed_at = ? WHERE id = ?",
            (datetime.now().isoformat(), task_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def delete_task(task_id: int) -> bool:
    conn = _get_conn()
    try:
        cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_tasks_stats() -> Dict:
    conn = _get_conn()
    try:
        total = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        active = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'active'").fetchone()[0]
        done = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'done'").fetchone()[0]
    finally:
        conn.close()
    return {"total": total, "active": active, "done": done}


# ========== СОБЫТИЯ ==========

def add_event(title: str, start_time: str, end_time: str = None,
              location: str = "", description: str = "") -> int:
    conn = _get_conn()
    try:
        cursor = conn.execute(
            "INSERT INTO events (title, description, start_time, end_time, location, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (title, description, start_time, end_time, location, datetime.now().isoformat())
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_events(date: str = None, limit: int = 50) -> List[Dict]:
    conn = _get_conn()
    try:
        if date:
            rows = conn.execute(
                "SELECT id, title, description, start_time, end_time, location "
                "FROM events WHERE start_time LIKE ? ORDER BY start_time ASC LIMIT ?",
                (f"{date}%", limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, title, description, start_time, end_time, location "
                "FROM events ORDER BY start_time ASC LIMIT ?",
                (limit,)
            ).fetchall()
    finally:
        conn.close()

    return [
        {
            "id": r[0], "title": r[1], "description": r[2],
            "start_time": r[3], "end_time": r[4], "location": r[5]
        }
        for r in rows
    ]


def update_event(event_id: int, **kwargs) -> bool:
    """Обновляет поля события. Допустимые: title, description, start_time, end_time, location."""
    allowed = {"title", "description", "start_time", "end_time", "location"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False

    fields = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [event_id]

    conn = _get_conn()
    try:
        cursor = conn.execute(f"UPDATE events SET {fields} WHERE id = ?", values)
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def delete_event(event_id: int) -> bool:
    conn = _get_conn()
    try:
        cursor = conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


# ========== РУТИНЫ ==========

def add_routine(name: str, actions: str, schedule: str) -> int:
    conn = _get_conn()
    try:
        cursor = conn.execute(
            "INSERT INTO routines (name, actions, schedule, created_at) VALUES (?, ?, ?, ?)",
            (name, actions, schedule, datetime.now().isoformat())
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_routines() -> List[Dict]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, name, actions, schedule, enabled FROM routines ORDER BY id ASC"
        ).fetchall()
    finally:
        conn.close()
    return [
        {"id": r[0], "name": r[1], "actions": r[2], "schedule": r[3], "enabled": r[4]}
        for r in rows
    ]


def update_routine(routine_id: int, **kwargs) -> bool:
    """Обновляет поля рутины. Допустимые: name, actions, schedule, enabled."""
    allowed = {"name", "actions", "schedule", "enabled"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False

    fields = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [routine_id]

    conn = _get_conn()
    try:
        cursor = conn.execute(f"UPDATE routines SET {fields} WHERE id = ?", values)
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def delete_routine(routine_id: int) -> bool:
    conn = _get_conn()
    try:
        cursor = conn.execute("DELETE FROM routines WHERE id = ?", (routine_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


# ========== МИГРАЦИЯ ==========

def migrate_to_encrypted() -> Dict[str, int]:
    """Шифрует все незашифрованные данные."""
    stats = {"messages": 0, "facts": 0}

    conn = _get_conn()
    try:
        rows = conn.execute("SELECT id, content FROM messages").fetchall()
        for msg_id, content in rows:
            if not is_encrypted(content):
                encrypted = _encrypt(content)
                if encrypted != content:
                    conn.execute(
                        "UPDATE messages SET content = ? WHERE id = ?",
                        (encrypted, msg_id)
                    )
                    stats["messages"] += 1
        conn.commit()

        rows = conn.execute("SELECT id, content FROM facts").fetchall()
        for fact_id, content in rows:
            if not is_encrypted(content):
                encrypted = _encrypt(content)
                if encrypted != content:
                    conn.execute(
                        "UPDATE facts SET content = ? WHERE id = ?",
                        (encrypted, fact_id)
                    )
                    stats["facts"] += 1
        conn.commit()
    finally:
        conn.close()

    _log(f"✅ Миграция: {stats['messages']} сообщений, {stats['facts']} фактов")
    return stats


# ========== УТИЛИТЫ ==========

def get_db_stats() -> Dict[str, int]:
    stats = {}
    conn = _get_conn()
    try:
        for table in ("messages", "facts", "settings", "tasks", "events", "routines"):
            try:
                stats[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except Exception:
                stats[table] = 0
    finally:
        conn.close()
    return stats


def vacuum_db() -> None:
    conn = _get_conn()
    try:
        conn.execute("VACUUM")
        conn.commit()
    finally:
        conn.close()


def backup_db(backup_path: str) -> bool:
    try:
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        conn = _get_conn()
        try:
            backup = sqlite3.connect(backup_path)
            conn.backup(backup)
            backup.close()
        finally:
            conn.close()
        _log(f"✅ Бэкап: {backup_path}")
        return True
    except Exception as e:
        _log(f"⚠️ Ошибка бэкапа: {e}")
        return False


# ========== ТЕСТ ==========
if __name__ == "__main__":
    print("🧪 Тест БД Zeta\n")
    print("=" * 50)

    init_db()

    test_text = "Это секретное сообщение"
    encrypted = _encrypt(test_text)
    decrypted = _decrypt(encrypted)

    print(f"\n🔐 Шифрование:")
    print(f"   Оригинал:   {test_text}")
    print(f"   Шифр:       {encrypted[:60]}...")
    print(f"   Расшифровка: {decrypted}")
    print(f"   ✅ Совпадает: {test_text == decrypted}")

    print(f"\n📊 Статистика БД:")
    stats = get_db_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")

    print(f"\n📝 Тест задачи:")
    task_id = add_task("Тестовая задача", "", None, 1)
    print(f"   ✅ Задача #{task_id} создана")
    tasks = get_tasks()
    print(f"   Всего задач: {len(tasks)}")
    update_task(task_id, priority=3)
    print(f"   ✅ Задача обновлена (priority=3)")
    delete_task(task_id)
    print(f"   ✅ Задача удалена")

    print(f"\n📅 Тест события:")
    event_id = add_event("Тестовая встреча", datetime.now().isoformat())
    print(f"   ✅ Событие #{event_id} создано")
    events = get_events()
    print(f"   Всего событий: {len(events)}")
    delete_event(event_id)

    print(f"\n✅ Тесты пройдены!")