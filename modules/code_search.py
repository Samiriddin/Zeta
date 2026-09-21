# -*- coding: utf-8 -*-
"""
Поиск по коду проекта Z.
Безопасный grep: ограничение глубины, фильтр расширений, игнорирование .git/__pycache__.

Особенности:
    - Проверка бинарных файлов (по \x00 в первых 8 КБ)
    - Лимит времени поиска (защита от гигантских проектов)
    - Итератор по строкам (не readlines) — экономия памяти
    - Один скомпилированный regex для find_symbol
    - Логирование
"""

import os
import re
import time
import logging
import sys
from pathlib import Path
from typing import List, Tuple, Optional, Set, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))


# ========== ЛОГИРОВАНИЕ ==========

def _log(msg: str) -> None:
    logging.info(f"[CODE_SEARCH] {msg}")


def _log_warn(msg: str) -> None:
    logging.warning(f"[CODE_SEARCH] {msg}")


# ========== КОНСТАНТЫ ==========
MAX_FILE_SIZE = 1024 * 1024      # 1 MB
MAX_RESULTS = 30
CONTEXT_LINES = 2
MAX_DEPTH = 6
SEARCH_TIMEOUT = 10              # секунд на весь поиск
BINARY_CHECK_BYTES = 8192        # сколько байт проверять на бинарность
MAX_FILES_SCANNED = 5000         # страховка: не более N файлов просматривать

SKIP_DIRS: Set[str] = {
    ".git", "__pycache__", ".venv", "venv", "node_modules",
    ".idea", ".vscode", "dist", "build", "target", ".pytest_cache",
    "migrations", ".mypy_cache", ".tox", "site-packages",
    ".ruff_cache", ".coverage", "htmlcov",
}

SKIP_EXTS: Set[str] = {
    ".pyc", ".pyo", ".so", ".dll", ".exe", ".bin", ".dat",
    ".jpg", ".jpeg", ".png", ".gif", ".ico", ".svg", ".webp",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv",
    ".zip", ".tar", ".gz", ".rar", ".7z",
    ".db", ".sqlite", ".sqlite3",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".pyi", ".pyd",
    ".log", ".tmp", ".cache",
    ".lock",  # package-lock.json, poetry.lock
}


# ========== ИСКЛЮЧЕНИЯ ==========

class SearchError(Exception):
    """Ошибка при поиске."""
    pass


# ========== ОСНОВНОЙ КЛАСС ==========

class CodeSearch:
    """
    Поиск по содержимому файлов проекта.
    Аналог grep, но безопасный и с умными фильтрами.
    """

    def __init__(self, project_path: str):
        self.project_path = Path(project_path).resolve()
        if not self.project_path.exists():
            raise SearchError(f"Путь не существует: {project_path}")
        if not self.project_path.is_dir():
            raise SearchError(f"Путь не является директорией: {project_path}")

    # ----- ФИЛЬТРЫ -----

    def _should_skip_dir(self, dir_name: str) -> bool:
        """Проверяет, нужно ли пропустить директорию."""
        return dir_name in SKIP_DIRS or dir_name.startswith(".")

    def _should_skip_file(self, file_path: Path) -> bool:
        """Проверяет, нужно ли пропустить файл."""
        if file_path.suffix.lower() in SKIP_EXTS:
            return True
        try:
            if file_path.stat().st_size > MAX_FILE_SIZE:
                return True
        except Exception:
            return True
        return False

    @staticmethod
    def _is_binary(file_path: Path) -> bool:
        """
        Быстрая проверка на бинарность: ищем \x00 в первых 8 КБ.
        Возвращает True, если файл похож на бинарный.
        """
        try:
            with open(file_path, "rb") as f:
                chunk = f.read(BINARY_CHECK_BYTES)
            return b"\x00" in chunk
        except Exception:
            return True  # если не можем прочитать — считаем бинарным

    def _get_relative_path(self, file_path: Path) -> str:
        """Возвращает относительный путь к файлу."""
        try:
            return str(file_path.relative_to(self.project_path))
        except ValueError:
            return str(file_path)

    # ----- ОСНОВНОЙ ПОИСК -----

    def search(
        self,
        query: str,
        extensions: Optional[List[str]] = None,
        case_sensitive: bool = False,
        regex: bool = False,
        max_depth: int = MAX_DEPTH,
        max_results: int = MAX_RESULTS,
        timeout: int = SEARCH_TIMEOUT,
    ) -> List[Tuple[str, int, str, List[str]]]:
        """
        Поиск по содержимому файлов.

        Returns:
            Список кортежей: (относительный_путь, номер_строки, строка_совпадения, контекст)
        """
        if not query or not query.strip():
            return [("ERROR", 0, "Пустой запрос. Напишите что искать.", [])]

        results: List[Tuple[str, int, str, List[str]]] = []
        flags = 0 if case_sensitive else re.IGNORECASE

        try:
            if regex:
                pattern = re.compile(query, flags)
            else:
                pattern = re.compile(re.escape(query), flags)
        except re.error as e:
            return [("ERROR", 0, f"Некорректное регулярное выражение: {e}", [])]

        # Нормализация расширений: ['.py', 'py'] → {'.py'}
        ext_set: Set[str] = set()
        if extensions:
            for ext in extensions:
                e = ext.lower().strip()
                if not e:
                    continue
                if not e.startswith("."):
                    e = "." + e
                ext_set.add(e)

        deadline = time.time() + timeout
        files_scanned = 0

        try:
            for root, dirs, files in os.walk(self.project_path, followlinks=False):
                # Фильтруем директории на месте
                dirs[:] = [d for d in dirs if not self._should_skip_dir(d)]

                # Проверка глубины
                rel_root = Path(root).relative_to(self.project_path)
                if len(rel_root.parts) > max_depth:
                    dirs.clear()
                    continue

                # Проверка таймаута
                if time.time() > deadline:
                    _log_warn(
                        f"Поиск прерван по таймауту {timeout}с "
                        f"(найдено {len(results)}, файлов {files_scanned})"
                    )
                    break

                for filename in files:
                    # Лимит по количеству файлов (страховка)
                    if files_scanned >= MAX_FILES_SCANNED:
                        _log_warn(f"Достигнут лимит файлов {MAX_FILES_SCANNED}")
                        return results
                    files_scanned += 1

                    # Фильтр по расширениям
                    if ext_set:
                        ext = Path(filename).suffix.lower()
                        if ext not in ext_set:
                            continue

                    file_path = Path(root) / filename
                    if self._should_skip_file(file_path):
                        continue
                    if self._is_binary(file_path):
                        continue

                    # Читаем файл построчно (не всё сразу)
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                            lines = f.readlines()
                    except Exception as e:
                        _log_warn(f"Не удалось прочитать {file_path}: {e}")
                        continue

                    # Ищем совпадения
                    for i, line in enumerate(lines, 1):
                        if pattern.search(line):
                            start = max(0, i - 1 - CONTEXT_LINES)
                            end = min(len(lines), i + CONTEXT_LINES)
                            context = [
                                f"{j + 1:4d}| {lines[j].rstrip()}"
                                for j in range(start, end)
                            ]

                            rel_path = self._get_relative_path(file_path)
                            results.append((rel_path, i, line.strip(), context))

                            if len(results) >= max_results:
                                return results

        except Exception as e:
            _log_warn(f"Ошибка поиска: {e}")
            return [("ERROR", 0, f"Ошибка поиска: {e}", [])]

        _log(f"Поиск '{query[:50]}': найдено {len(results)} (файлов: {files_scanned})")
        return results

    # ----- ФОРМАТИРОВАНИЕ -----

    def search_formatted(self, query: str, **kwargs) -> str:
        """Форматированный вывод для чата Z."""
        results = self.search(query, **kwargs)

        if not results:
            return (
                f"🔍 По запросу `{query}` ничего не найдено. "
                f"Возможно, код в другом проекте или вы ищете чудеса."
            )

        if results[0][0] == "ERROR":
            return f"⚠️ {results[0][2]}"

        lines = [f"🔍 Результаты поиска: `{query}` (найдено: {len(results)})\n"]

        for rel_path, line_no, match_line, context in results:
            lines.append(f"\n📄 {rel_path}:{line_no}")
            lines.append("```")
            for ctx_line in context:
                marker = " >>>" if f"{line_no:4d}|" in ctx_line else "    "
                lines.append(f"{marker}{ctx_line}")
            lines.append("```")

        return "\n".join(lines)

    # ----- УМНЫЙ ПОИСК СИМВОЛА -----

    def find_symbol(
        self,
        symbol: str,
        language: str = "python",
        max_results: int = MAX_RESULTS,
    ) -> str:
        """
        Умный поиск символа: функций, классов, переменных.
        Один скомпилированный regex на все паттерны.
        """
        if not symbol or not symbol.strip():
            return "⚠️ Укажите имя символа для поиска."

        esc = re.escape(symbol)
        lang = language.lower()

        if lang in ("python", "py"):
            raw_patterns = [
                rf"^\s*(?:def|class|async\s+def)\s+{esc}\b",
                rf"^\s*{esc}\s*[=:\(]",
            ]
        elif lang in ("javascript", "js", "ts", "typescript"):
            raw_patterns = [
                rf"^\s*(?:function|const|let|var|class)\s+{esc}\b",
                rf"^\s*{esc}\s*[=:\(]",
                rf"export\s+(?:default\s+)?{esc}\b",
            ]
        elif lang in ("java", "cpp", "c", "c++", "cs", "go", "rust"):
            raw_patterns = [
                rf"\b{esc}\s*[\(:]",
                rf"^\s*(?:public|private|protected|static)?\s*\w+\s+{esc}\b",
            ]
        else:
            raw_patterns = [rf"\b{esc}\b"]

        # Один regex из всех паттернов
        combined = "|".join(f"(?:{p})" for p in raw_patterns)

        results = self.search(
            combined,
            regex=True,
            max_depth=5,
            max_results=max_results,
        )

        if not results:
            return (
                f"🔍 Символ `{symbol}` не найден. "
                f"Возможно, он в другом проекте или ещё не написан."
            )

        if results[0][0] == "ERROR":
            return f"⚠️ {results[0][2]}"

        # Дедупликация (один файл:строка — одна запись)
        seen: Set[Tuple[str, int]] = set()
        unique_results = []
        for r in results:
            key = (r[0], r[1])
            if key not in seen:
                seen.add(key)
                unique_results.append(r)

        lines = [f"🔍 Символ `{symbol}` (найдено: {len(unique_results)})\n"]
        for rel_path, line_no, match_line, context in unique_results:
            lines.append(f"\n📄 {rel_path}:{line_no}")
            lines.append("```")
            for ctx_line in context:
                marker = " >>>" if f"{line_no:4d}|" in ctx_line else "    "
                lines.append(f"{marker}{ctx_line}")
            lines.append("```")

        return "\n".join(lines)

    # ----- СПЕЦИАЛИЗИРОВАННЫЕ ПОИСКИ -----

    def find_import(self, module: str, **kwargs) -> str:
        """Ищет импорты модуля."""
        return self.search_formatted(
            rf"^(?:import|from)\s+{re.escape(module)}\b",
            regex=True,
            extensions=[".py"],
            **kwargs,
        )

    def find_function_calls(self, function: str, **kwargs) -> str:
        """Ищет вызовы функции."""
        return self.search_formatted(
            rf"\b{re.escape(function)}\s*\(",
            regex=True,
            extensions=[".py", ".js"],
            **kwargs,
        )

    def find_todo(self, **kwargs) -> str:
        """Находит все TODO / FIXME / XXX."""
        return self.search_formatted(
            r"\b(?:TODO|FIXME|XXX|HACK|NOTE)\b",
            regex=True,
            **kwargs,
        )


# ========== УДОБНЫЕ ФУНКЦИИ ==========

def search_code(project_path: str, query: str, **kwargs) -> str:
    """Упрощённая обёртка для поиска."""
    searcher = CodeSearch(project_path)
    return searcher.search_formatted(query, **kwargs)


def find_symbol(project_path: str, symbol: str, language: str = "python") -> str:
    """Упрощённая обёртка для поиска символа."""
    searcher = CodeSearch(project_path)
    return searcher.find_symbol(symbol, language)


# ========== ТЕСТ ==========

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    print("🧪 Тест code_search.py\n")
    print("=" * 60)

    try:
        searcher = CodeSearch("D:\\Zeta")
    except SearchError as e:
        print(f"❌ {e}")
        print("⚠️ Измени путь в тесте (по умолчанию D:\\Zeta)")
        sys.exit(1)

    # --- Тест 1: Поиск 'def' ---
    print("\n📝 Тест 1: Поиск 'def' в .py")
    result = searcher.search_formatted("def", extensions=[".py"], max_results=5)
    print(result[:600] + "..." if len(result) > 600 else result)
    print("-" * 50)

    # --- Тест 2: Поиск символа 'ask_zeta' ---
    print("\n📝 Тест 2: Символ 'ask_zeta' (python)")
    result = searcher.find_symbol("ask_zeta", "python", max_results=5)
    print(result[:600] + "..." if len(result) > 600 else result)
    print("-" * 50)

    # --- Тест 3: Импорты ---
    print("\n📝 Тест 3: Импорты 'requests'")
    result = searcher.find_import("requests")
    print(result[:400] + "..." if len(result) > 400 else result)
    print("-" * 50)

    # --- Тест 4: TODO ---
    print("\n📝 Тест 4: TODO/FIXME")
    result = searcher.find_todo(max_results=5)
    print(result[:400] + "..." if len(result) > 400 else result)
    print("-" * 50)

    # --- Тест 5: Биномарность ---
    print("\n📝 Тест 5: Проверка бинарности")
    test_files = [
        "D:\\Zeta\\main.py",
        "D:\\Zeta\\data\\zeta.db",
    ]
    for tf in test_files:
        p = Path(tf)
        if p.exists():
            is_bin = CodeSearch._is_binary(p)
            print(f"{tf} → {'бинарный' if is_bin else 'текстовый'}")
        else:
            print(f"{tf} → не существует")

    print("\n" + "=" * 60)
    print("✅ Тесты завершены!")