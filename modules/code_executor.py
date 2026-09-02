# -*- coding: utf-8 -*-
"""
Безопасный запуск кода Z.
Поддерживает: Python, JavaScript.
Защита: статический анализ, таймаут, ограниченное окружение.
"""

import os
import re
import sys
import tempfile
import subprocess
import py_compile
from typing import Tuple, Optional, List


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
    Sandbox-запуск кода с двойной защитой:
    1. Статический анализ (регулярки)
    2. Ограниченное окружение (subprocess + timeout)
    """

    # ===== ОБЩИЕ ОПАСНЫЕ ПАТТЕРНЫ =====
    DANGEROUS_PATTERNS: List[str] = [
        r"rm\s+-rf",
        r"rmdir\s+/s\s+/q",
        r"del\s+/f\s+/s\s+/q",
        r"format\s+[a-zA-Z]:",
        r"diskpart",
        r"reg\s+delete",
        r"shutdown\s+/s",
        r"shutdown\s+/r",
        r"shutdown\s+-h",
        r"rd\s+/s\s+/q",
        r"erase\s+/[fq]",
    ]

    # ===== ОПАСНЫЕ КОНСТРУКЦИИ PYTHON =====
    PYTHON_DANGEROUS: List[str] = [
        r"os\.system\s*\(",
        r"subprocess\.call\s*\(",
        r"subprocess\.run\s*\(",
        r"subprocess\.Popen\s*\(",
        r"__import__\s*\(\s*['\"]os['\"]",
        r"eval\s*\(",
        r"exec\s*\(",
        r"compile\s*\(",
        r"shutil\.rmtree",
        r"os\.remove\s*\(",
        r"os\.unlink\s*\(",
        r"os\.rmdir\s*\(",
        r"os\.removedirs\s*\(",
        r"builtins\.",  # Доступ к встроенным функциям
        r"globals\(\)",  # Манипуляция глобальными переменными
        r"locals\(\)",   # Манипуляция локальными переменными
    ]

    # ===== ОПАСНЫЕ КОНСТРУКЦИИ JAVASCRIPT =====
    JS_DANGEROUS: List[str] = [
        r"require\s*\(\s*['\"]child_process['\"]",
        r"require\s*\(\s*['\"]fs['\"]",
        r"require\s*\(\s*['\"]os['\"]",
        r"process\.exit",
        r"eval\s*\(",
        r"Function\s*\(",
        r"setInterval\s*\(",
        r"setTimeout\s*\(",
        r"console\.log",  # Не опасно, но для чистоты
    ]

    # ===== ОПАСНЫЕ BATCH-КОНСТРУКЦИИ =====
    BATCH_DANGEROUS: List[str] = [
        r"format\s+",
        r"del\s+/[fq]",
        r"rd\s+/s",
        r"rmdir\s+/s",
        r"reg\s+delete",
        r"shutdown",
        r"taskkill\s+/[fm]",
    ]

    # ===== НАСТРОЙКИ =====
    MAX_OUTPUT: int = 3000
    TIMEOUT: int = 10
    MAX_CODE_LENGTH: int = 10000


    # ========== СТАТИЧЕСКИЙ АНАЛИЗ ==========

    @classmethod
    def _is_safe(cls, code: str, language: str) -> Tuple[bool, str]:
        """Статический анализ кода перед запуском."""
        if len(code) > cls.MAX_CODE_LENGTH:
            return False, f"Код слишком длинный ({len(code)} символов). Максимум: {cls.MAX_CODE_LENGTH}"

        lowered = code.lower()

        # Общие опасные паттерны
        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, lowered):
                return False, f"🛡️ Обнаружена системная опасная команда: `{pattern}`. Z не рискует вашими данными."

        # Python
        if language in ("python", "py"):
            for pattern in cls.PYTHON_DANGEROUS:
                if re.search(pattern, code, re.IGNORECASE):
                    return False, f"🛡️ Обнаружена опасная конструкция Python: `{pattern}`. Используйте безопасные альтернативы."

        # JavaScript
        if language in ("javascript", "js", "node"):
            for pattern in cls.JS_DANGEROUS:
                if re.search(pattern, code, re.IGNORECASE):
                    return False, f"🛡️ Обнаружена опасная конструкция JavaScript: `{pattern}`."

        # Batch
        if language in ("batch", "cmd", "bat", "shell"):
            return False, "🛡️ Batch-скрипты Z не выполняет — слишком высокий риск случайного форматирования диска."

        return True, ""


    # ========== ПРОВЕРКА СИНТАКСИСА PYTHON ==========

    @classmethod
    def check_syntax_python(cls, code: str) -> Tuple[bool, str]:
        """Проверка синтаксиса Python через py_compile."""
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
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


    # ========== ЗАПУСК КОДА ==========

    @classmethod
    def run_python(cls, code: str, timeout: int = TIMEOUT) -> Tuple[bool, str, str]:
        """Запуск Python-кода в изолированном процессе."""
        safe, reason = cls._is_safe(code, "python")
        if not safe:
            return False, "", reason

        ok, msg = cls.check_syntax_python(code)
        if not ok:
            return False, "", msg

        try:
            result = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            return True, result.stdout, result.stderr

        except subprocess.TimeoutExpired:
            return False, "", "⏱️ Код выполнялся слишком долго — вероятно, бесконечный цикл. Прервала выполнение."

        except Exception as e:
            return False, "", f"⚠️ Ошибка при запуске: {str(e)}"


    @classmethod
    def run_javascript(cls, code: str, timeout: int = TIMEOUT) -> Tuple[bool, str, str]:
        """Запуск JavaScript через Node.js."""
        safe, reason = cls._is_safe(code, "javascript")
        if not safe:
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
            return False, "", "❌ Node.js не найден в PATH. Установите Node.js для запуска JavaScript."

        except subprocess.TimeoutExpired:
            return False, "", "⏱️ Код выполнялся слишком долго — прервала."

        except Exception as e:
            return False, "", f"⚠️ Ошибка при запуске: {str(e)}"


    @classmethod
    def run_bash(cls, code: str, timeout: int = TIMEOUT) -> Tuple[bool, str, str]:
        """Запуск Bash-скрипта (только на Linux/WSL)."""
        safe, reason = cls._is_safe(code, "bash")
        if not safe:
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


    @classmethod
    def _truncate_output(cls, text: str, max_len: int = MAX_OUTPUT) -> str:
        """Обрезает вывод до указанной длины."""
        if len(text) <= max_len:
            return text
        return text[:max_len] + f"\n... [обрезано, {len(text) - max_len} символов]"


    @classmethod
    def execute(cls, code: str, language: str = "python", timeout: int = TIMEOUT) -> str:
        """
        Универсальная точка входа. Возвращает форматированный ответ для чата.
        
        Args:
            code: исходный код
            language: python, javascript, js, bash
            timeout: таймаут в секундах
        
        Returns:
            отформатированный вывод
        """
        language = language.lower().strip()

        # Очищаем код от маркеров
        code = re.sub(r"^```\w*\n?", "", code)
        code = re.sub(r"\n?```$", "", code)

        if not code.strip():
            return "⚠️ Код пуст. Напишите что-нибудь."

        # Маршрутизация
        if language in ("python", "py"):
            ok, stdout, stderr = cls.run_python(code, timeout)
        elif language in ("javascript", "js", "node"):
            ok, stdout, stderr = cls.run_javascript(code, timeout)
        elif language in ("bash", "sh", "shell"):
            ok, stdout, stderr = cls.run_bash(code, timeout)
        else:
            return f"⚠️ Язык `{language}` пока не поддерживается. Доступны: Python, JavaScript, Bash."

        # Форматирование результата
        if not ok:
            return stderr

        parts = []

        if stdout.strip():
            truncated = cls._truncate_output(stdout)
            parts.append(f"📤 stdout:\n```\n{truncated}\n```")

        if stderr.strip():
            truncated = cls._truncate_output(stderr, 1000)
            parts.append(f"⚠️ stderr:\n```\n{truncated}\n```")

        if not parts:
            return "✅ Код выполнен успешно. Вывода нет — возможно, вы забыли `print()` или `console.log()`?"

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
    print("🧪 Тест CodeExecutor\n")

    # Тест 1: Безопасный Python
    print("📝 Тест 1: Безопасный Python")
    result = run_code("print('Hello, Zeta!')")
    print(result)
    print("-" * 50)

    # Тест 2: Опасный Python
    print("📝 Тест 2: Опасный Python")
    result = run_code("import os; os.system('rm -rf /')")
    print(result)
    print("-" * 50)

    # Тест 3: JavaScript
    print("📝 Тест 3: JavaScript")
    result = run_code("console.log('Hello from JS');", "javascript")
    print(result)
    print("-" * 50)

    # Тест 4: Пустой код
    print("📝 Тест 4: Пустой код")
    result = run_code("")
    print(result)
    print("-" * 50)

    # Тест 5: Синтаксическая ошибка
    print("📝 Тест 5: Синтаксическая ошибка")
    result = run_code("print('Hello'")
    print(result)
    print("-" * 50)