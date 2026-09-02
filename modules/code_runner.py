# -*- coding: utf-8 -*-
"""
Модуль для работы с кодом: запись, чтение, извлечение из сообщений.
Поддерживает: Python, JavaScript, HTML, CSS, JSON, и другие форматы.
"""

import os
import re
import subprocess
from typing import Tuple, Optional, List, Dict

# ========== КОНСТАНТЫ ==========
DEFAULT_OUTPUT_DIR = "D:\\Zeta\\generated"
DEFAULT_LANGUAGE = "python"
MAX_FILENAME_LENGTH = 100
MAX_CODE_LENGTH = 50000

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
    """Нормализует путь и проверяет, что он не выходит за пределы base_path."""
    if not base_path or not filename:
        raise CodePathError("Путь или имя файла пустые")
    
    filepath = os.path.normpath(os.path.join(base_path, filename))
    real_base = os.path.normpath(os.path.realpath(base_path))
    
    if not filepath.startswith(real_base):
        raise CodePathError(f"Путь выходит за пределы проекта: {filename}")
    
    return filepath


def _open_in_vscode(filepath: str) -> bool:
    """Открывает файл в VS Code. Возвращает True если успешно."""
    try:
        subprocess.Popen(["code", filepath], shell=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def _get_extension(language: str) -> str:
    """Возвращает расширение файла для языка."""
    language = language.lower().strip()
    return LANGUAGE_EXTENSIONS.get(language, "py")


def _is_valid_filename(filename: str) -> bool:
    """Проверяет, что имя файла корректно."""
    if not filename or len(filename) > MAX_FILENAME_LENGTH:
        return False
    
    if re.search(r'[<>:"/\\|?*]', filename):
        return False
    
    if filename.lower() in ["con", "prn", "aux", "nul", 
                            "com1", "com2", "com3", "com4",
                            "lpt1", "lpt2", "lpt3", "lpt4"]:
        return False
    
    if ".." in filename:
        return False
    
    return True


def _sanitize_code(code: str) -> str:
    """Очищает код от лишних пробелов и символов."""
    if not code:
        return ""
    
    code = code.strip()
    
    if len(code) > MAX_CODE_LENGTH:
        raise CodeTooLongError(f"Код слишком длинный ({len(code)} символов). Максимум: {MAX_CODE_LENGTH}")
    
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
        return f"⚠️ Некорректное имя файла: {filename}"
    
    try:
        code = _sanitize_code(code)
        os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)
        filepath = os.path.join(DEFAULT_OUTPUT_DIR, filename)
        
        with open(filepath, "w", encoding="utf-8", newline='\n') as f:
            f.write(code)
        
        opened = _open_in_vscode(filepath)
        return _format_output_result(filepath, "Создан", opened)
    
    except CodeTooLongError as e:
        return f"⚠️ {e}"
    except Exception as e:
        return f"⚠️ Ошибка записи: {str(e)}"


def write_code_to_project(project_path: str, filename: str, code: str, append: bool = False) -> str:
    """Пишет код прямо в файл проекта."""
    if not _is_valid_filename(filename):
        return f"⚠️ Некорректное имя файла: {filename}"
    
    try:
        code = _sanitize_code(code)
        filepath = _normalize_path(project_path, filename)
        
        dir_name = os.path.dirname(filepath)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        exists = os.path.isfile(filepath)
        mode = "a" if (append and exists) else "w"
        
        with open(filepath, mode, encoding="utf-8", newline='\n') as f:
            if mode == "a":
                f.write("\n\n" + code)
            else:
                f.write(code)

        opened = _open_in_vscode(filepath)
        action = "Дополнен" if mode == "a" else "Создан/обновлён"
        return _format_output_result(filepath, action, opened)
    
    except CodePathError as e:
        return f"⚠️ Ошибка: {e}"
    except CodeTooLongError as e:
        return f"⚠️ {e}"
    except Exception as e:
        return f"⚠️ Ошибка записи в проект: {str(e)}"


def read_file_from_project(project_path: str, filename: str) -> str:
    """Читает содержимое файла из проекта."""
    try:
        filepath = _normalize_path(project_path, filename)
        
        if not os.path.isfile(filepath):
            return f"⚠️ Файл не найден: {filepath}"
        
        file_size = os.path.getsize(filepath)
        if file_size > 1024 * 1024:
            return f"⚠️ Файл слишком большой ({file_size // 1024} KB). Чтение ограничено 1MB."
        
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    
    except CodePathError as e:
        return f"⚠️ Ошибка: {e}"
    except UnicodeDecodeError:
        return f"⚠️ Не удалось прочитать файл (возможно, бинарный или другая кодировка): {filename}"
    except Exception as e:
        return f"⚠️ Ошибка чтения: {str(e)}"


def extract_code(text: str) -> Tuple[str, str]:
    """Извлекает код из markdown-блоков."""
    if not text:
        return "", "py"

    pattern = r"```(\w*)\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    
    if matches:
        lang = matches[0][0].strip() or "py"
        code = matches[0][1].strip()
        return code, lang

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
    
    return text.strip(), "py"


def extract_filename_from_message(message: str) -> Optional[str]:
    """Извлекает имя файла из сообщения."""
    if not message:
        return None
    
    pattern = r'\b([\w\-\.]+\.(py|js|ts|html|css|json|txt|md|java|cpp|c|cs|go|rs|php|rb|swift|kt|sql|yaml|yml|xml|sh|dockerfile|mk))\b'
    match = re.search(pattern, message, re.IGNORECASE)
    if match:
        return match.group(1)
    
    pattern2 = r'(?:в\s+)?файл(?:е|а)?\s+([\w\-\.]+)'
    match2 = re.search(pattern2, message, re.IGNORECASE)
    if match2:
        filename = match2.group(1)
        if '.' not in filename:
            filename += '.py'
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
    
    ext = os.path.splitext(filename)[1].lower().lstrip('.')
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
    print("🧪 Тест code_runner.py\n")
    
    # Тест 1: Извлечение кода
    print("📝 Тест 1: Извлечение кода")
    test_text = '```python\ndef hello():\n    print("Hello, World!")\n```'
    code, lang = extract_code(test_text)
    print(f"Язык: {lang}")
    print(f"Код: {code[:50]}...")
    print("-" * 40)
    
    # Тест 2: Имя файла
    print("📝 Тест 2: Имя файла")
    msg = "Напиши функцию в файле test.py"
    filename = extract_filename_from_message(msg)
    print(f"Имя файла: {filename}")
    print("-" * 40)
    
    # Тест 3: Язык по расширению
    print("📝 Тест 3: Язык по расширению")
    test_files = ["app.js", "main.go", "index.html", "style.css", "Dockerfile"]
    for ext_file in test_files:
        lang = detect_language_from_filename(ext_file)
        print(f"{ext_file} → {lang}")
    print("-" * 40)
    
    # Тест 4: Поддерживаемые языки
    print("📝 Тест 4: Поддерживаемые языки")
    langs = get_supported_languages()
    print(f"Всего языков: {len(langs)}")
    print(f"Языки: {', '.join(langs[:10])}...")
    
    print("\n✅ Все тесты завершены!")