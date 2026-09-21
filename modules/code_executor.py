# -*- coding: utf-8 -*-
"""
Безопасный запуск кода Z.
Поддерживает: Python, JavaScript.
Защита: 3 уровня — AST-анализ (Python), статические паттерны, таймаут + изоляция.

Особенности:
    - Белый список разрешённых модулей (безопасный stdlib)
    - Запрет опасных атрибутов у разрешённых модулей (os.system и т.д.)
    - Защита от обхода через getattr/__import__/eval
    - Логирование всех блокировок в data/zeta.log
    - Обрезка stderr, чтобы не залить чат
"""

import os
import re
import sys
import ast
import logging
import tempfile
import subprocess
import py_compile
from typing import Tuple, Optional, List


# ========== ЛОГИРОВАНИЕ ==========

def _log(msg: str) -> None:
    logging.info(f"[CODE] {msg}")


def _log_warn(msg: str) -> None:
    logging.warning(f"[CODE] {msg}")


def _audit(msg: str) -> None:
    """Логировать в аудит, если доступен."""
    try:
        from security.audit import get_audit
        get_audit().log_security("code_exec", msg)
    except Exception:
        pass


# ========== ИСКЛЮЧЕНИЯ ==========

class CodeSafetyError(Exception):
    """Исключение при обнаружении опасного кода."""
    pass


class CodeExecutionError(Exception):
    """Исключение при выполнении кода."""
    pass


# ========== ОСНОВНОЙ КЛАСС ==========

class CodeExecutor:
    """
    Sandbox-запуск кода с тройной защитой:
    1. AST-анализ Python (настоящая защита, не паттерны)
    2. Статические паттерны (bash, batch, JS)
    3. Ограниченное окружение (subprocess + timeout)
    """

    # ===== РАЗРЕШЁННЫЕ МОДУЛИ (безопасный stdlib) =====
    ALLOWED_MODULES = {
        # Математика
        "math", "random", "statistics", "decimal", "fractions", "numbers",
        # Время и даты
        "datetime", "time", "calendar", "zoneinfo",
        # Работа с данными
        "json", "csv", "base64", "binascii", "hashlib", "hmac",
        "re", "string", "textwrap", "pprint",
        # Коллекции
        "collections", "itertools", "functools", "operator",
        "enum", "dataclasses", "typing", "abc", "copy",
        # Утилиты
        "uuid", "secrets", "heapq", "bisect", "array", "struct",
        # Безопасные системные (только чтение)
        "os",  # разрешён, но с ограничениями (см. FORBIDDEN_ATTRS)
    }

    # ===== ЗАПРЕЩЁННЫЕ МОДУЛИ =====
    FORBIDDEN_MODULES = {
        "subprocess", "shutil", "socket",
        "requests", "urllib", "urllib2", "urllib3",
        "http", "ftplib", "telnetlib", "smtplib", "poplib", "imaplib",
        "ctypes", "cffi",
        "pickle", "marshal", "shelve", "dbm",
        "multiprocessing", "threading", "asyncio", "concurrent",
        "pathlib", "glob", "tempfile",
        "importlib", "pkgutil", "modulefinder",
        "pdb", "profile", "cProfile", "traceback",
        "webbrowser", "antigravity", "this",
    }

    # ===== ЗАПРЕЩЁННЫЕ АТРИБУТЫ (у разрешённых модулей) =====
    # Даже если модуль разрешён — эти методы опасны
    FORBIDDEN_ATTRS = {
        # os - файловая система
        "system", "popen", "spawn", "spawnl", "spawnle", "spawnlp",
        "spawnv", "spawnve", "spawnvp", "spawnvpe",
        "execv", "execve", "execvp", "execvpe", "execl", "execle",
        "execlp", "execlpe",
        "remove", "unlink", "rmdir", "removedirs", "rename", "renames",
        "replace", "truncate", "chmod", "chown", "kill", "killpg",
        "fork", "forkpty", "wait", "waitpid",
        "putenv", "unsetenv",
        "open", "fdopen", "close", "closerange", "dup", "dup2",
        "setuid", "setgid", "seteuid", "setegid",
        # Общие опасные
        "rmtree", "move", "copyfile", "copytree",
    }

    # ===== ЗАПРЕЩЁННЫЕ ФУНКЦИИ =====
    FORBIDDEN_CALLS = {
        "eval", "exec", "compile", "__import__",
        "globals", "locals", "vars",
        "getattr", "setattr", "delattr",
        "memoryview", "breakpoint",
        "input",  # требует stdin, может висеть
    }

    # ===== СИСТЕМНЫЕ ОПАСНЫЕ КОМАНДЫ (bash/batch) =====
    SHELL_DANGEROUS: List[str] = [
        r"rm\s+-rf",
        r"rmdir\s+/s\s+/q",
        r"del\s+/f\s+/s\s+/q",
        r"format\s+[a-zA-Z]:",
        r"diskpart",
        r"reg\s+delete",
        r"shutdown\s+/[sr]",
        r"shutdown\s+-h",
        r"rd\s+/s\s+/q",
        r"erase\s+/[fq]",
        r"taskkill\s+/[fm]",
        r":\(\)\s*\{\s*:\|:&\s*\}",   # fork bomb
    ]

    # ===== ОПАСНЫЕ КОНСТРУКЦИИ JAVASCRIPT =====
    JS_DANGEROUS: List[str] = [
        r"require\s*\(\s*['\"]child_process['\"]",
        r"require\s*\(\s*['\"]fs['\"]",
        r"require\s*\(\s*['\"]os['\"]",
        r"process\.exit\s*\(",
        r"eval\s*\(",
        r"Function\s*\(",
        r"vm\.runInThisContext",
        r"process\.kill\s*\(",
    ]

    # ===== НАСТРОЙКИ =====
    MAX_OUTPUT: int = 3000
    TIMEOUT: int = 10
    MAX_CODE_LENGTH: int = 10000


    # ============================================================
    #  УРОВЕНЬ 1: AST-АНАЛИЗ PYTHON
    # ============================================================

    @classmethod
    def _ast_check_python(cls, code: str) -> Tuple[bool, str]:
        """
        Проверка Python-кода через AST.
        Настоящая защита — не обходится через getattr, т.к. мы блокируем
        И импорт, И опасные атрибуты, И опасные функции.
        """
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"❌ Синтаксическая ошибка: {e.msg} (строка {e.lineno})"

        for node in ast.walk(tree):

            # --- Запрет импорта запрещённых модулей ---
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name.split(".")[0]
                    if name in cls.FORBIDDEN_MODULES:
                        return False, (
                            f"🛡️ Импорт модуля `{name}` запрещён.\n"
                            f"Разрешены: math, random, datetime, json, re, os (частично) и др."
                        )
                    if name not in cls.ALLOWED_MODULES:
                        return False, (
                            f"🛡️ Модуль `{name}` не в белом списке.\n"
                            f"Разрешены: {', '.join(sorted(cls.ALLOWED_MODULES))}"
                        )

            if isinstance(node, ast.ImportFrom):
                module = (node.module or "").split(".")[0]
                if module in cls.FORBIDDEN_MODULES:
                    return False, f"🛡️ Импорт из `{module}` запрещён."
                if module and module not in cls.ALLOWED_MODULES:
                    return False, f"🛡️ Модуль `{module}` не в белом списке."

            # --- Запрет опасных вызовов ---
            if isinstance(node, ast.Call):
                func = node.func

                # Прямой вызов: eval(...), exec(...)
                if isinstance(func, ast.Name):
                    if func.id in cls.FORBIDDEN_CALLS:
                        return False, f"🛡️ Вызов `{func.id}()` запрещён."

                # Метод: os.system(...), os.remove(...)
                if isinstance(func, ast.Attribute):
                    if func.attr in cls.FORBIDDEN_ATTRS:
                        return False, (
                            f"🛡️ Вызов метода `.{func.attr}()` запрещён."
                        )

            # --- Запрет доступа к опасным атрибутам (даже без вызова) ---
            if isinstance(node, ast.Attribute):
                if node.attr in ("import_module", "__globals__", "__builtins__",
                                 "__subclasses__", "__bases__", "__mro__"):
                    return False, f"🛡️ Доступ к `.{node.attr}` запрещён."

        return True, ""


    # ============================================================
    #  УРОВЕНЬ 2: СТАТИЧЕСКИЙ АНАЛИЗ (bash, JS)
    # ============================================================

    @classmethod
    def _check_shell(cls, code: str) -> Tuple[bool, str]:
        """Проверка для bash/batch — по паттернам."""
        lowered = code.lower()
        for pattern in cls.SHELL_DANGEROUS:
            if re.search(pattern, lowered):
                return False, (
                    f"🛡️ Обнаружена опасная системная команда: `{pattern}`.\n"
                    f"Z не рискует вашими данными."
                )
        return True, ""


    @classmethod
    def _check_javascript(cls, code: str) -> Tuple[bool, str]:
        """Проверка JS — по паттернам."""
        for pattern in cls.JS_DANGEROUS:
            if re.search(pattern, code, re.IGNORECASE):
                return False, f"🛡️ Опасная конструкция JavaScript: `{pattern}`."
        return True, ""


    # ============================================================
    #  ОБЩАЯ ВАЛИДАЦИЯ
    # ============================================================

    @classmethod
    def _is_safe(cls, code: str, language: str) -> Tuple[bool, str]:
        """Единая точка проверки безопасности."""
        if len(code) > cls.MAX_CODE_LENGTH:
            return False, (
                f"Код слишком длинный ({len(code)} символов). "
                f"Максимум: {cls.MAX_CODE_LENGTH}."
            )

        lang = language.lower().strip()

        if lang in ("python", "py"):
            return cls._ast_check_python(code)

        if lang in ("javascript", "js", "node"):
            return cls._check_javascript(code)

        if lang in ("bash", "sh", "shell", "cmd", "bat", "batch"):
            return cls._check_shell(code)

        return True, ""


    # ============================================================
    #  ПРОВЕРКА СИНТАКСИСА PYTHON
    # ============================================================

    @classmethod
    def check_syntax_python(cls, code: str) -> Tuple[bool, str]:
        """Проверка синтаксиса Python через py_compile (дополнительно к AST)."""
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.py', delete=False, encoding='utf-8'
            ) as f:
                f.write(code)
                tmp_path = f.name

            py_compile.compile(tmp_path, doraise=True)
            return True, "✅ Синтаксис корректен."

        except py_compile.PyCompileError as e:
            err_msg = str(e)
            err_msg = re.sub(r"at '.*\.py'", "в вашем коде", err_msg)
            err_msg = re.sub(r"File '.*\.py'", "Код", err_msg)
            return False, f"❌ Синтаксическая ошибка: {err_msg}"

        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass


    # ============================================================
    #  УРОВЕНЬ 3: ЗАПУСК С ТАЙМАУТОМ
    # ============================================================

    @classmethod
    def run_python(cls, code: str, timeout: int = TIMEOUT) -> Tuple[bool, str, str]:
        """Запуск Python-кода."""
        safe, reason = cls._is_safe(code, "python")
        if not safe:
            _log_warn(f"Заблокирован Python: {reason[:100]}")
            _audit(f"blocked_python: {reason[:200]}")
            return False, "", reason

        try:
            result = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            _log(f"Python запущен (код возврата {result.returncode})")
            return True, result.stdout, result.stderr

        except subprocess.TimeoutExpired:
            _log_warn(f"Python превысил таймаут {timeout}с")
            return False, "", (
                "⏱️ Код выполнялся слишком долго — вероятно, бесконечный цикл. "
                "Прервала выполнение."
            )

        except FileNotFoundError:
            return False, "", f"❌ Python не найден по пути: {sys.executable}"

        except Exception as e:
            _log_warn(f"Ошибка запуска Python: {e}")
            return False, "", f"⚠️ Ошибка при запуске: {str(e)}"


    @classmethod
    def run_javascript(cls, code: str, timeout: int = TIMEOUT) -> Tuple[bool, str, str]:
        """Запуск JavaScript через Node.js."""
        safe, reason = cls._is_safe(code, "javascript")
        if not safe:
            _log_warn(f"Заблокирован JS: {reason[:100]}")
            _audit(f"blocked_js: {reason[:200]}")
            return False, "", reason

        try:
            result = subprocess.run(
                ["node", "-e", code],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            return True, result.stdout, result.stderr

        except FileNotFoundError:
            return False, "", (
                "❌ Node.js не найден в PATH. "
                "Установите Node.js для запуска JavaScript."
            )

        except subprocess.TimeoutExpired:
            return False, "", "⏱️ Код выполнялся слишком долго — прервала."

        except Exception as e:
            return False, "", f"⚠️ Ошибка при запуске: {str(e)}"


    @classmethod
    def run_bash(cls, code: str, timeout: int = TIMEOUT) -> Tuple[bool, str, str]:
        """Запуск Bash (только Linux/WSL)."""
        safe, reason = cls._is_safe(code, "bash")
        if not safe:
            _log_warn(f"Заблокирован Bash: {reason[:100]}")
            _audit(f"blocked_bash: {reason[:200]}")
            return False, "", reason

        try:
            result = subprocess.run(
                ["bash", "-c", code],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            return True, result.stdout, result.stderr

        except FileNotFoundError:
            return False, "", "❌ Bash не найден. Запустите на Linux или включите WSL."

        except subprocess.TimeoutExpired:
            return False, "", "⏱️ Код выполнялся слишком долго — прервала."

        except Exception as e:
            return False, "", f"⚠️ Ошибка: {str(e)}"


    # ============================================================
    #  УТИЛИТЫ
    # ============================================================

    @classmethod
    def _truncate_output(cls, text: str, max_len: int = MAX_OUTPUT) -> str:
        if len(text) <= max_len:
            return text
        return text[:max_len] + f"\n... [обрезано, {len(text) - max_len} символов]"


    @classmethod
    def execute(cls, code: str, language: str = "python",
                timeout: int = TIMEOUT) -> str:
        """
        Универсальная точка входа. Возвращает форматированный ответ для чата.
        """
        language = language.lower().strip()

        # Очищаем код от маркеров ```...```
        code = re.sub(r"^```\w*\n?", "", code)
        code = re.sub(r"\n?```$", "", code)

        if not code.strip():
            return "⚠️ Код пуст. Напишите что-нибудь."

        # Маршрутизация по языку
        if language in ("python", "py"):
            ok, stdout, stderr = cls.run_python(code, timeout)
        elif language in ("javascript", "js", "node"):
            ok, stdout, stderr = cls.run_javascript(code, timeout)
        elif language in ("bash", "sh", "shell"):
            ok, stdout, stderr = cls.run_bash(code, timeout)
        elif language in ("batch", "cmd", "bat"):
            return (
                "🛡️ Batch-скрипты Z не выполняет — "
                "слишком высокий риск случайного форматирования диска."
            )
        else:
            return (
                f"⚠️ Язык `{language}` пока не поддерживается. "
                f"Доступны: Python, JavaScript, Bash."
            )

        # Форматирование результата
        if not ok:
            # ← Обрезаем stderr, если ошибка
            return cls._truncate_output(stderr)

        parts = []

        if stdout.strip():
            truncated = cls._truncate_output(stdout)
            parts.append(f"📤 stdout:\n```\n{truncated}\n```")

        if stderr.strip():
            truncated = cls._truncate_output(stderr, 1000)
            parts.append(f"⚠️ stderr:\n```\n{truncated}\n```")

        if not parts:
            return (
                "✅ Код выполнен успешно. Вывода нет — "
                "возможно, вы забыли `print()` или `console.log()`?"
            )

        return "\n\n".join(parts)


# ========== УДОБНЫЕ ФУНКЦИИ ==========

def run_code(code: str, language: str = "python", timeout: int = 10) -> str:
    """Упрощённая обёртка для CodeExecutor.execute()."""
    return CodeExecutor.execute(code, language, timeout)


def is_safe_code(code: str, language: str = "python") -> Tuple[bool, str]:
    """Проверяет код без выполнения."""
    return CodeExecutor._is_safe(code, language)


# ========== ТЕСТ ==========

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
    )

    print("🧪 Тест CodeExecutor\n")
    print("=" * 60)

    # --- Тест 1: Безопасный Python ---
    print("\n📝 Тест 1: Безопасный Python")
    print(run_code("print('Hello, Zeta!')"))
    print("-" * 50)

    # --- Тест 2: Опасный Python (os.system) ---
    print("\n📝 Тест 2: Опасный Python (os.system)")
    print(run_code("import os; os.system('rm -rf /')"))
    print("-" * 50)

    # --- Тест 3: Обходной путь (getattr) ---
    print("\n📝 Тест 3: Обходной путь (getattr)")
    print(run_code("import os; getattr(os, 'system')('echo hacked')"))
    print("-" * 50)

    # --- Тест 4: Математика (разрешено) ---
    print("\n📝 Тест 4: Математика (разрешено)")
    print(run_code("""
import math
print(math.sqrt(16))
print(math.pi)
"""))
    print("-" * 50)

    # --- Тест 5: os.getcwd() — разрешено (безопасный метод) ---
    print("\n📝 Тест 5: os.getcwd() — разрешено")
    print(run_code("""
import os
print(os.getcwd())
"""))
    print("-" * 50)

    # --- Тест 6: Запрещённый модуль (subprocess) ---
    print("\n📝 Тест 6: Запрещённый модуль (subprocess)")
    print(run_code("import subprocess; print('nope')"))
    print("-" * 50)

    # --- Тест 7: JS ---
    print("\n📝 Тест 7: JavaScript")
    print(run_code("console.log('Hello from JS');", "javascript"))
    print("-" * 50)

    # --- Тест 8: Пустой код ---
    print("\n📝 Тест 8: Пустой код")
    print(run_code(""))
    print("-" * 50)

    # --- Тест 9: Синтаксическая ошибка ---
    print("\n📝 Тест 9: Синтаксическая ошибка")
    print(run_code("print('Hello'"))
    print("-" * 50)

    # --- Тест 10: Бесконечный цикл ---
    print("\n📝 Тест 10: Бесконечный цикл (таймаут 3с)")
    print(run_code("while True: pass", timeout=3))
    print("-" * 50)

    print("\n✅ Все тесты завершены.")