# -*- coding: utf-8 -*-
"""
Zeta Security — Санитизация ввода.
Защита от SQL, Command, Python, XSS инъекций.

Особенности:
    - sanitize_sql — блокирует (возвращает "")
    - sanitize_command — не удаляет () из текста
    - sanitize_path — защита от префиксных атак (D:\Zeta vs D:\Zeta_evil)
    - sanitize_filename — не ломает .gitignore, .env
    - is_safe("text") — мягкий контекст
    - Логирование в data/zeta.log
"""

import os
import re
import sys
import html
import logging
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))


# ========== ЛОГИРОВАНИЕ ==========

def _log_warn(msg: str) -> None:
    logging.warning(f"[SANITIZER] {msg}")


def _audit(msg: str) -> None:
    try:
        from security.audit import get_audit
        get_audit().log_security("sanitizer_blocked", msg, severity="warning")
    except Exception:
        pass


# ================================================================
#  PATTERNS
# ================================================================

DANGEROUS_PATTERNS = {
    "sql": [
        r"\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b",
        r"--",
        r";\s*(DROP|DELETE|UPDATE|INSERT)",
        r"\bOR\b\s+['\"]?\d+['\"]?\s*=\s*['\"]?\d+",
        r"\bUNION\b.*\bSELECT\b",
        r"\bINTO\s+OUTFILE\b",
        r"\bLOAD_FILE\b",
    ],
    "command": [
        r"[;&|`$]",
        r"\brm\s+-rf\b",
        r"\bdel\s+/[fsq]\b",
        r"\bformat\s+[a-z]:",
        r"\bsudo\b",
        r"\bshutdown\b",
        r"\breboot\b",
        r"\bcurl\s+.*\|\s*sh\b",
        r"\bwget\s+.*\|\s*sh\b",
    ],
    "python": [
        r"\b(__import__|eval|exec|compile|globals|locals)\s*\(",
        r"\bos\.(system|popen|spawn|exec|remove|unlink)\b",
        r"\bsubprocess\.(call|run|Popen)\b",
        r"\bshutil\.(rmtree|move|copy)\b",
    ],
    "xss": [
        r"<\s*script[^>]*>",
        r"javascript\s*:",
        r"\bon\w+\s*=",
        r"<\s*iframe",
        r"<\s*object",
        r"<\s*embed",
    ],
    # Мягкий контекст — только то, что реально опасно в тексте
    "text": [
        r"\b(DROP\s+TABLE|DROP\s+DATABASE)\b",
        r"\brm\s+-rf\s+/\b",
        r"<\s*script[^>]*>.*?<\s*/\s*script\s*>",
    ],
}


# ================================================================
#  SANITIZER
# ================================================================

class InputSanitizer:
    """Санитизация ввода."""

    # Запрещённые управляющие символы (кроме \t, \n, \r)
    CONTROL_CHARS = re.compile(r"[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]")

    # Небезопасные символы для имён файлов
    UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1F]')

    # -----------------------------------------------------------------
    #  TEXT
    # -----------------------------------------------------------------

    @staticmethod
    def sanitize_text(text: str, max_length: int = 10000) -> str:
        """Очистить обычный текст: убрать control chars, обрезать."""
        if not text:
            return ""

        # Обрезаем
        if len(text) > max_length:
            text = text[:max_length]

        # Убираем управляющие символы (кроме \t, \n, \r)
        text = InputSanitizer.CONTROL_CHARS.sub("", text)

        return text.strip()

    # -----------------------------------------------------------------
    #  HTML
    # -----------------------------------------------------------------

    @staticmethod
    def sanitize_html(text: str) -> str:
        """
        Очистить HTML.
        html.escape достаточно — <script> станет &lt;script&gt;.
        """
        if not text:
            return ""
        return html.escape(text)

    # -----------------------------------------------------------------
    #  SQL
    # -----------------------------------------------------------------

    @staticmethod
    def sanitize_sql(text: str) -> str:
        """
        Проверить SQL. Если опасно — вернуть "".
        Не пытается "очистить" — SQL-инъекцию нельзя очистить.
        """
        if not text:
            return ""

        for pattern in DANGEROUS_PATTERNS["sql"]:
            if re.search(pattern, text, re.IGNORECASE):
                _log_warn(f"SQL-инъекция заблокирована: {text[:80]}")
                _audit(f"sql_injection: {text[:200]}")
                return ""

        return text

    # -----------------------------------------------------------------
    #  COMMAND
    # -----------------------------------------------------------------

    @staticmethod
    def sanitize_command(text: str) -> str:
        """
        Санитизация для shell-команд.
        НЕ использовать для обычного текста!
        """
        if not text:
            return ""

        # Опасные символы для shell
        dangerous = [";", "&", "|", "`", "$", "<", ">", "\n", "\r"]
        for char in dangerous:
            text = text.replace(char, "")

        return text.strip()

    # -----------------------------------------------------------------
    #  FILENAME
    # -----------------------------------------------------------------

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Очистить имя файла. Не ломает .gitignore, .env."""
        if not filename:
            return "unnamed"

        # Убираем путь (берём только последний компонент)
        filename = filename.replace("\\", "/").split("/")[-1]

        # Убираем `..` (выход из папки)
        while ".." in filename:
            filename = filename.replace("..", "")

        # Заменяем опасные символы
        filename = InputSanitizer.UNSAFE_FILENAME_CHARS.sub("_", filename)

        # НЕ удаляем ведущую точку — .gitignore, .env важны!
        # Удаляем только если имя стало пустым или из одних точек
        if filename and filename.strip(".") == "":
            filename = "unnamed"

        # Ограничение длины
        if len(filename) > 255:
            if "." in filename:
                name, ext = filename.rsplit(".", 1)
                filename = name[:250] + "." + ext
            else:
                filename = filename[:255]

        return filename or "unnamed"

    # -----------------------------------------------------------------
    #  PATH
    # -----------------------------------------------------------------

    @staticmethod
    def sanitize_path(path: str, allowed_dir: Optional[str] = None) -> Optional[str]:
        """
        Очистить путь.
        Если allowed_dir задан — путь должен быть ВНУТРИ него.
        Возвращает None, если путь небезопасен.
        """
        if not path:
            return None

        try:
            p = Path(path).resolve()

            if allowed_dir:
                allowed = Path(allowed_dir).resolve()
                # Нормализуем регистр (Windows)
                p_str = os.path.normcase(str(p))
                allowed_str = os.path.normcase(str(allowed))

                # Защита от префиксных атак: D:\Zeta vs D:\Zeta_evil
                if p_str != allowed_str and not p_str.startswith(allowed_str + os.sep):
                    _log_warn(f"Path traversal: {path}")
                    _audit(f"path_traversal: {path}")
                    return None

            return str(p)

        except Exception as e:
            _log_warn(f"Ошибка sanitize_path: {e}")
            return None

    # -----------------------------------------------------------------
    #  IS SAFE
    # -----------------------------------------------------------------

    @staticmethod
    def is_safe(text: str, context: str = "text") -> bool:
        """
        Проверяет, безопасен ли текст в данном контексте.
        context: text / html / sql / command / python / xss
        """
        if not text:
            return True

        patterns = DANGEROUS_PATTERNS.get(context, [])
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return False
        return True


# ================================================================
#  УДОБНЫЕ ФУНКЦИИ
# ================================================================

_sanitizer = InputSanitizer()


def sanitize(text: str, context: str = "text") -> str:
    """Быстрая санитизация."""
    if not text:
        return ""

    if context == "html":
        return _sanitizer.sanitize_html(text)
    elif context == "sql":
        return _sanitizer.sanitize_sql(text)
    elif context == "command":
        return _sanitizer.sanitize_command(text)
    elif context == "filename":
        return _sanitizer.sanitize_filename(text)
    else:
        return _sanitizer.sanitize_text(text)


def is_safe(text: str, context: str = "text") -> bool:
    """Проверка безопасности."""
    return _sanitizer.is_safe(text, context)


def sanitize_path(path: str, allowed_dir: Optional[str] = None) -> Optional[str]:
    """Очистить путь."""
    return _sanitizer.sanitize_path(path, allowed_dir)


def sanitize_filename(filename: str) -> str:
    """Очистить имя файла."""
    return _sanitizer.sanitize_filename(filename)


# ================================================================
#  ЭКСПОРТ
# ================================================================

__all__ = [
    "InputSanitizer",
    "sanitize",
    "is_safe",
    "sanitize_path",
    "sanitize_filename",
    "DANGEROUS_PATTERNS",
]


# ================================================================
#  ТЕСТ
# ================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    print("🧪 Тест санитизации")
    print("=" * 60)

    # --- TEXT ---
    print("\n📝 Тест 1: text")
    for text in ["Привет, Zeta!", "Что такое Python (язык)?", "A & B | C"]:
        result = sanitize(text, "text")
        print(f"  {text!r:40} → {result!r}")

    # --- SQL ---
    print("\n📝 Тест 2: sql (должно блокировать)")
    sql_tests = [
        "SELECT * FROM users",
        "1' OR '1'='1",
        "DROP TABLE users",
        "Обычный текст без SQL",
    ]
    for text in sql_tests:
        result = sanitize(text, "sql")
        marker = "🚫" if result == "" else "✅"
        print(f"  {marker} {text!r:35} → {result!r}")

    # --- COMMAND ---
    print("\n📝 Тест 3: command")
    cmd_tests = [
        "ls; rm -rf /",
        "echo hello",
        "cat file.txt | grep test",
    ]
    for text in cmd_tests:
        result = sanitize(text, "command")
        print(f"  {text!r:35} → {result!r}")

    # --- HTML ---
    print("\n📝 Тест 4: html")
    html_tests = [
        "<script>alert('xss')</script>",
        "<b>bold</b>",
        "normal text",
    ]
    for text in html_tests:
        result = sanitize(text, "html")
        print(f"  {text!r:40} → {result!r}")

    # --- FILENAME ---
    print("\n📝 Тест 5: filename")
    fname_tests = [
        "../../../etc/passwd",
        "C:\\Windows\\system32\\cmd.exe",
        ".gitignore",
        ".env",
        "normal.txt",
        "test?.py",
    ]
    for text in fname_tests:
        result = sanitize_filename(text)
        print(f"  {text!r:40} → {result!r}")

    # --- PATH ---
    print("\n📝 Тест 6: path (защита от префиксов)")
    path_tests = [
        ("D:\\Zeta\\file.txt", "D:\\Zeta"),
        ("D:\\Zeta_evil\\file.txt", "D:\\Zeta"),  # ← должно блокироваться
        ("D:\\Other\\file.txt", "D:\\Zeta"),
        ("D:\\Zeta\\sub\\file.txt", "D:\\Zeta"),
    ]
    for path, allowed in path_tests:
        result = sanitize_path(path, allowed)
        marker = "✅" if result else "🚫"
        print(f"  {marker} {path!r:35} (allowed: {allowed!r}) → {result}")

    # --- is_safe ---
    print("\n📝 Тест 7: is_safe")
    safe_tests = [
        ("Обычный текст", "text", True),
        ("DROP TABLE users", "text", False),
        ("SELECT * FROM users", "sql", False),
        ("hello world", "sql", True),
        ("rm -rf /", "command", False),
    ]
    for text, ctx, expected in safe_tests:
        result = is_safe(text, ctx)
        marker = "✅" if result == expected else "❌"
        print(f"  {marker} [{ctx:8s}] {text!r:35} → {result}")

    print("\n" + "=" * 60)
    print("✅ Тесты пройдены!")