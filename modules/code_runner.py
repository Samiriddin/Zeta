# -*- coding: utf-8 -*-
"""
Модуль для работы с кодом: запись, чтение, извлечение из сообщений.
Поддерживает: Python, JavaScript, HTML, CSS, JSON, и другие форматы.

Безопасность:
    - Защита от path traversal (realpath на обоих путях + os.sep)
    - Защита от shell injection (shell=False)
    - Логирование всех операций
"""

import os
import re
import sys
import logging
import subprocess
from pathlib import Path
from typing import Tuple, Optional, List, Dict

sys.path.insert(0, str(Path(__file__).parent.parent))


# ========== ЛОГИРОВАНИЕ ==========

def _log(msg: str) -> None:
    logging.info(f"[CODE_RUNNER] {msg}")


def _log_warn(msg: str) -> None:
    logging.warning(f"[CODE_RUNNER] {msg}")


def _audit(msg: str) -> None:
    """Логировать в аудит, если доступен."""
    try:
        from security.audit import get_audit
        get_audit().log_security("code_runner", msg)
    except Exception:
        pass


# ========== КОНСТАНТЫ ==========
DEFAULT_OUTPUT_DIR = "D:\\Zeta\\generated"
DEFAULT_LANGUAGE = "python"
MAX_FILENAME_LENGTH = 100
MAX_CODE_LENGTH = 50000
MAX_READ_CHARS = 2000  # сколько символов из файла отдавать в промпт

# Карта расширений для языков
LANGUAGE_EXTENSIONS: Dict[str, str] = {
    "python": "py",
    "py": "py",
    "javascript": "js",
    "js": "js",
    "typescript": "ts",
    "ts": "ts",
    "html": "html",
    "css": "css",
    "json": "json",
    "txt": "txt",
    "md": "md",
    "markdown": "md",
    "java": "java",
    "cpp": "cpp",
    "c++": "cpp",
    "c": "c",
    "c#": "cs",
    "cs": "cs",
    "go": "go",
    "rust": "rs",
    "rs": "rs",
    "php": "php",
    "ruby": "rb",
    "rb": "rb",
    "swift": "swift",
    "kotlin": "kt",
    "kt": "kt",
    "sql": "sql",
    "yaml": "yaml",
    "yml": "yml",
    "xml": "xml",
    "sh": "sh",
    "bash": "sh",
    "dockerfile": "dockerfile",
    "makefile": "mk",
    "mk": "mk",
    "cmake": "cmake",
}


# ========== ИСКЛЮЧЕНИЯ ==========

class CodePathError(Exception):
    """Ошибка при работе с путями файлов."""
    pass


class CodeTooLongError(Exception):
    """Ошибка при слишком длинном коде."""
    pass


# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

def _normalize_path(base_path: str, filename: str) -> str:
    """
    Нормализует путь и проверяет, что он не выходит за пределы base_path.
    Защита от path traversal (..) и симлинков.

    Бросает CodePathError, если путь небезопасен.
    """
    if not base_path or not filename:
        raise CodePathError("Путь или имя файла пустые")

    # 1. Ранняя проверка на .. в filename (до join)
    if ".." in filename.replace("\\", "/").split("/"):
        _log_warn(f"Path traversal попытка: {filename}")
        _audit(f"path_traversal: {filename}")
        raise CodePathError(f"Имя файла содержит '..': {filename}")

    # 2. Абсолютный путь в filename — сразу блок
    if os.path.isabs(filename):
        _log_warn(f"Абсолютный путь в filename: {filename}")
        _audit(f"absolute_path: {filename}")
        raise CodePathError(f"Абсолютный путь не разрешён: {filename}")

    # 3. Собираем полный путь
    joined = os.path.join(base_path, filename)

    # 4. realpath на обоих — защита от симлинков
    real_file = os.path.realpath(joined)
    real_base = os.path.realpath(base_path)

    # 5. Сравнение с учётом разделителя
    # base="D:\Zeta", file="D:\Zeta_evil" — НЕ должно проходить
    if real_file != real_base and not real_file.startswith(real_base + os.sep):
        _log_warn(f"Выход за пределы проекта: {real_file} (base: {real_base})")
        _audit(f"path_outside: {filename}")
        raise CodePathError(f"Путь выходит за пределы проекта: {filename}")

    return real_file


def _open_in_vscode(filepath: str) -> bool:
    """Открывает файл в VS Code. Возвращает True если успешно."""
    try:
        # shell=False — защита от инъекций через filename
        subprocess.Popen(
            ["code", filepath],
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except FileNotFoundError:
        _log_warn("VS Code (code) не найден в PATH")
        return False
    except Exception as e:
        _log_warn(f"Не удалось открыть в VS Code: {e}")
        return False


def _get_extension(language: str) -> str:
    """Возвращает расширение файла для языка."""
    language = language.lower().strip()
    return LANGUAGE_EXTENSIONS.get(language, "py")


def _is_valid_filename(filename: str) -> bool:
    """Проверяет, что имя файла корректно."""
    if not filename or len(filename) > MAX_FILENAME_LENGTH:
        return False

    # Запрещённые символы Windows
    if re.search(r'[<>:"/\\|?*]', filename):
        return False

    # Зарезервированные имена Windows
    if filename.lower() in [
        "con", "prn", "aux", "nul",
        "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
        "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
    ]:
        return False

    # Запрет на .. и .
    if ".." in filename or filename.strip() in (".", ".."):
        return False

    # Пустое имя после отбрасывания пробелов
    if not filename.strip():
        return False

    return True


def _sanitize_code(code: str) -> str:
    """Очищает код от лишних пробелов и символов."""
    if not code:
        return ""

    code = code.strip()

    if len(code) > MAX_CODE_LENGTH:
        raise CodeTooLongError(
            f"Код слишком длинный ({len(code)} символов). Максимум: {MAX_CODE_LENGTH}"
        )

    return code


def _format_output_result(filepath: str, action: str, is_opened: bool) -> str:
    """Форматирует результат операции с файлом."""
    result = f"✅ {action} файл: {filepath}"
    if is_opened:
        result += " (открыт в VS Code)"
    return result


# ========== ОСНОВНЫЕ ФУНКЦИИ ==========

def write_code_to_file(filename: str, code: str) -> str:
    """Записывает код в файл в папку generated/ и открывает в VS Code."""
    if not _is_valid_filename(filename):
        _log_warn(f"Некорректное имя: {filename}")
        return f"⚠️ Некорректное имя файла: {filename}"

    try:
        code = _sanitize_code(code)
        os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)
        filepath = os.path.join(DEFAULT_OUTPUT_DIR, filename)

        with open(filepath, "w", encoding="utf-8", newline="\n") as f:
            f.write(code)

        _log(f"Создан файл: {filepath}")
        opened = _open_in_vscode(filepath)
        return _format_output_result(filepath, "Создан", opened)

    except CodeTooLongError as e:
        return f"⚠️ {e}"
    except Exception as e:
        _log_warn(f"Ошибка записи: {e}")
        return f"⚠️ Ошибка записи: {str(e)}"


def write_code_to_project(project_path: str, filename: str,
                          code: str, append: bool = False) -> str:
    """Пишет код прямо в файл проекта."""
    if not _is_valid_filename(filename):
        _log_warn(f"Некорректное имя: {filename}")
        return f"⚠️ Некорректное имя файла: {filename}"

    try:
        code = _sanitize_code(code)
        filepath = _normalize_path(project_path, filename)

        dir_name = os.path.dirname(filepath)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        exists = os.path.isfile(filepath)
        mode = "a" if (append and exists) else "w"

        with open(filepath, mode, encoding="utf-8", newline="\n") as f:
            if mode == "a":
                f.write("\n\n" + code)
            else:
                f.write(code)

        _log(f"{'Дополнен' if mode == 'a' else 'Создан'}: {filepath}")
        opened = _open_in_vscode(filepath)
        action = "Дополнен" if mode == "a" else "Создан/обновлён"
        return _format_output_result(filepath, action, opened)

    except CodePathError as e:
        return f"⚠️ Ошибка: {e}"
    except CodeTooLongError as e:
        return f"⚠️ {e}"
    except Exception as e:
        _log_warn(f"Ошибка записи в проект: {e}")
        return f"⚠️ Ошибка записи в проект: {str(e)}"


def read_file_from_project(project_path: str, filename: str,
                           max_chars: int = MAX_READ_CHARS) -> str:
    """
    Читает содержимое файла из проекта.
    Ограничивает вывод max_chars символами (для промпта модели).
    """
    try:
        filepath = _normalize_path(project_path, filename)

        if not os.path.isfile(filepath):
            return f"⚠️ Файл не найден: {filepath}"

        file_size = os.path.getsize(filepath)
        if file_size > 1024 * 1024:
            return (
                f"⚠️ Файл слишком большой ({file_size // 1024} KB). "
                f"Чтение ограничено 1 MB."
            )

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        _log(f"Прочитан файл: {filepath} ({len(content)} символов)")

        # Ограничение для промпта
        if len(content) > max_chars:
            content = content[:max_chars] + "\n... [обрезано]"

        return content

    except CodePathError as e:
        return f"⚠️ Ошибка: {e}"
    except UnicodeDecodeError:
        return (
            f"⚠️ Не удалось прочитать файл "
            f"(возможно, бинарный или другая кодировка): {filename}"
        )
    except Exception as e:
        _log_warn(f"Ошибка чтения: {e}")
        return f"⚠️ Ошибка чтения: {str(e)}"


def extract_code(text: str) -> Tuple[str, str]:
    """
    Извлекает код из markdown-блоков.
    Возвращает (код, язык).
    Если блока нет — возвращает ("", "py").
    """
    if not text:
        return "", "py"

    # Основной паттерн
    pattern = r"```(\w*)\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)

    if matches:
        lang = matches[0][0].strip() or "py"
        code = matches[0][1].strip()
        return code, lang

    # Fallback: парсим построчно
    lines = text.split("\n")
    code_lines = []
    language = "py"
    in_code = False

    for line in lines:
        if line.startswith("```"):
            if not in_code:
                in_code = True
                lang = line.replace("```", "").strip()
                if lang:
                    language = lang
            else:
                in_code = False
        elif in_code:
            code_lines.append(line)

    if code_lines:
        return "\n".join(code_lines), language

    # ← Никакого fallback на весь текст: это НЕ код
    return "", "py"


def extract_filename_from_message(message: str) -> Optional[str]:
    """Извлекает имя файла из сообщения."""
    if not message:
        return None

    # 1. Ищем имя с расширением
    pattern = (
        r"\b([\w\-\.]+\.(py|js|ts|html|css|json|txt|md|java|cpp|c|cs|go|rs|"
        r"php|rb|swift|kt|sql|yaml|yml|xml|sh|dockerfile|mk))\b"
    )
    match = re.search(pattern, message, re.IGNORECASE)
    if match:
        filename = match.group(1)
        # Проверка: имя не должно быть просто расширением
        if len(filename) > 4 and not filename.startswith("."):
            return filename

    # 2. Ищем "в файле X"
    pattern2 = r"(?:в\s+)?файл(?:е|а)?\s+([\w\-\.]+)"
    match2 = re.search(pattern2, message, re.IGNORECASE)
    if match2:
        filename = match2.group(1)
        if len(filename) < 2 or filename.startswith("."):
            return None
        if "." not in filename:
            filename += ".py"
        return filename

    return None


def extract_all_code_blocks(text: str) -> List[Tuple[str, str]]:
    """Извлекает все блоки кода из текста."""
    if not text:
        return []

    pattern = r"```(\w*)\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    return [(code.strip(), lang or "py") for lang, code in matches]


def detect_language_from_filename(filename: str) -> str:
    """Определяет язык программирования по расширению файла."""
    if not filename:
        return "python"

    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    for lang, lang_ext in LANGUAGE_EXTENSIONS.items():
        if lang_ext == ext:
            return lang
    return "python"


def get_supported_languages() -> List[str]:
    """Возвращает список поддерживаемых языков."""
    return sorted(set(LANGUAGE_EXTENSIONS.keys()))


def get_supported_extensions() -> List[str]:
    """Возвращает список поддерживаемых расширений."""
    return sorted(set(LANGUAGE_EXTENSIONS.values()))


# ========== ТЕСТ ==========

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    print("🧪 Тест code_runner.py\n")
    print("=" * 60)

    # --- Тест 1: Извлечение кода ---
    print("\n📝 Тест 1: Извлечение кода")
    test_text = '```python\ndef hello():\n    print("Hello, World!")\n```'
    code, lang = extract_code(test_text)
    print(f"Язык: {lang}")
    print(f"Код: {code[:50]}...")

    # --- Тест 2: Нет блока кода ---
    print("\n📝 Тест 2: Текст без блока кода")
    code, lang = extract_code("Просто текст без кода")
    print(f"Код: '{code}' | Язык: {lang}")
    print(f"→ {'✅ OK (пусто)' if not code else '❌ Должно быть пусто'}")

    # --- Тест 3: Имя файла ---
    print("\n📝 Тест 3: Имя файла")
    for msg in [
        "Напиши функцию в файле test.py",
        "Создай app.js",
        "Файл .py",              # ← мусор, должен быть None
    ]:
        filename = extract_filename_from_message(msg)
        print(f"'{msg}' → {filename}")

    # --- Тест 4: Язык по расширению ---
    print("\n📝 Тест 4: Язык по расширению")
    for ext_file in ["app.js", "main.go", "index.html", "style.css", "Dockerfile"]:
        lang = detect_language_from_filename(ext_file)
        print(f"{ext_file} → {lang}")

    # --- Тест 5: Валидация имён ---
    print("\n📝 Тест 5: Валидация имён")
    for name in ["test.py", "con.py", "../evil.txt", "test?.py", "D:\\abs.py"]:
        valid = _is_valid_filename(name)
        print(f"{name!r:20} → {'✅ OK' if valid else '❌ Заблокировано'}")

    # --- Тест 6: Path traversal ---
    print("\n📝 Тест 6: Path traversal защита")
    test_cases = [
        ("D:\\Zeta\\project", "test.py"),          # OK
        ("D:\\Zeta\\project", "..\\..\\evil.py"),  # Блок
        ("D:\\Zeta\\project", "D:\\abs.py"),       # Блок
        ("D:\\Zeta\\project", "sub\\file.py"),     # OK
    ]
    for base, fname in test_cases:
        try:
            result = _normalize_path(base, fname)
            print(f"✅ {fname:20} → {result}")
        except CodePathError as e:
            print(f"🛡️ {fname:20} → {e}")

    # --- Тест 7: Поддерживаемые языки ---
    print("\n📝 Тест 7: Поддерживаемые языки")
    langs = get_supported_languages()
    print(f"Всего языков: {len(langs)}")
    print(f"Примеры: {', '.join(langs[:10])}...")

    print("\n" + "=" * 60)
    print("✅ Все тесты завершены!")