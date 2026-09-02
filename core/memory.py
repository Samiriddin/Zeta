# -*- coding: utf-8 -*-
"""
Модуль работы с базой данных Zeta.
Хранит: историю сообщений, факты о пользователе, настройки.
"""

import os
import sqlite3
from datetime import datetime
from typing import List, Dict, Optional, Any

DB_PATH = "data/zeta.db"

# Список технических настроек, которые НЕ должны попадать в факты
SYSTEM_KEYS = {
    "theme", "voice_enabled", "widget_size", "avatar_path", "widget_x", "widget_y",
    "ai_model", "tts_voice", "tts_speed", "max_tokens", "context_tokens",
    "ai_temperature", "widget_opacity", "notif_interval", "cpu_threshold",
    "ram_threshold", "disk_threshold", "smart_notifications", "project_path"
}


def _get_conn() -> sqlite3.Connection:
    """Возвращает соединение с БД, создавая папку data при необходимости."""
    os.makedirs("data", exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    """
    Создаёт все таблицы. Безопасно запускать при старте программы.
    Выполняет миграцию старых фактов из settings в facts.
    """
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

        # --- Факты о пользователе ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        # --- Миграция старых фактов (с фильтрацией технических настроек) ---
        try:
            cursor.execute("SELECT key, value FROM settings WHERE key NOT LIKE 'setting_%'")
            old_facts = cursor.fetchall()
            for key, value in old_facts:
                # Пропускаем технические настройки, чтобы они не попадали в факты
                if key not in SYSTEM_KEYS:
                    cursor.execute(
                        "INSERT OR IGNORE INTO facts (key, content, created_at) VALUES (?, ?, ?)",
                        (key, value, datetime.now().isoformat())
                    )
                    cursor.execute("DELETE FROM settings WHERE key = ?", (key,))
        except Exception:
            pass  # Если таблицы ещё нет — ничего страшного

        conn.commit()
    finally:
        conn.close()


# ========== СООБЩЕНИЯ ==========

def save_message(role: str, content: str) -> None:
    """Сохраняет сообщение в историю."""
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO messages (role, content, timestamp) VALUES (?, ?, ?)",
            (role, content, datetime.now().isoformat())
        )


def get_history(limit: int = 50) -> List[Dict[str, str]]:
    """
    Возвращает последние N сообщений в хронологическом порядке.
    Формат: [{"role": "user", "content": "..."}, ...]
    """
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


def clear_history() -> None:
    """Очищает всю историю сообщений."""
    with _get_conn() as conn:
        conn.execute("DELETE FROM messages")


# ========== ФАКТЫ О ПОЛЬЗОВАТЕЛЕ ==========

def save_fact(key: str, content: str) -> None:
    """
    Сохраняет факт о пользователе.
    key — категория (например 'имя', 'увлечение', 'работа')
    content — текст факта
    """
    with _get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO facts (key, content, created_at) VALUES (?, ?, ?)",
            (key, content, datetime.now().isoformat())
        )


def get_facts() -> List[Dict[str, str]]:
    """
    Возвращает список фактов: [{"key": "имя", "content": "Самир"}, ...]
    """
    with _get_conn() as conn:
        rows = conn.execute("SELECT key, content FROM facts ORDER BY id DESC").fetchall()
    return [{"key": r[0], "content": r[1]} for r in rows]


def delete_fact(key: str) -> None:
    """Удаляет факт по ключу."""
    with _get_conn() as conn:
        conn.execute("DELETE FROM facts WHERE key = ?", (key,))


def clear_facts() -> None:
    """Удаляет все факты."""
    with _get_conn() as conn:
        conn.execute("DELETE FROM facts")


# ========== НАСТРОЙКИ ==========

def save_setting(key: str, value: str) -> None:
    """Сохраняет настройку."""
    with _get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )


def get_setting(key: str, default: str = "") -> str:
    """Возвращает настройку или значение по умолчанию."""
    with _get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def get_settings() -> Dict[str, str]:
    """Возвращает все настройки в виде словаря."""
    with _get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {r[0]: r[1] for r in rows}


def delete_setting(key: str) -> None:
    """Удаляет настройку."""
    with _get_conn() as conn:
        conn.execute("DELETE FROM settings WHERE key = ?", (key,))


# ========== УТИЛИТЫ ==========

def get_db_stats() -> Dict[str, int]:
    """Возвращает статистику БД: количество записей в каждой таблице."""
    stats = {}
    with _get_conn() as conn:
        for table in ("messages", "facts", "settings"):
            stats[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return stats


def vacuum_db() -> None:
    """Оптимизирует базу данных (удаляет удалённые записи)."""
    with _get_conn() as conn:
        conn.execute("VACUUM")


def backup_db(backup_path: str) -> bool:
    """Создаёт резервную копию базы данных."""
    try:
        with _get_conn() as conn:
            backup = sqlite3.connect(backup_path)
            conn.backup(backup)
            backup.close()
        return True
    except Exception as e:
        print(f"Ошибка резервного копирования: {e}")
        return False


# ========== ИНИЦИАЛИЗАЦИЯ ==========
init_db()