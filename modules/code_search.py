# -*- coding: utf-8 -*-
"""
Поиск по коду проекта Z.
Безопасный grep: ограничение глубины, фильтр расширений, игнорирование .git/__pycache__.
"""

import os
import re
from pathlib import Path
from typing import List, Tuple, Optional, Set, Dict, Any

# ========== КОНСТАНТЫ ==========
MAX_FILE_SIZE = 1024 * 1024  # 1 MB
MAX_RESULTS = 30
CONTEXT_LINES = 2
MAX_DEPTH = 6

SKIP_DIRS: Set[str] = {
    ".git", "__pycache__", ".venv", "venv", "node_modules",
    ".idea", ".vscode", "dist", "build", "target", ".pytest_cache",
    "migrations", ".mypy_cache", ".tox", "site-packages",
    ".ruff_cache", ".coverage", "htmlcov", ".pytest_cache",
}

SKIP_EXTS: Set[str] = {
    ".pyc", ".pyo", ".so", ".dll", ".exe", ".bin", ".dat",
    ".jpg", ".jpeg", ".png", ".gif", ".ico", ".svg", ".webp",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv",
    ".zip", ".tar", ".gz", ".rar", ".7z",
    ".db", ".sqlite", ".sqlite3",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".pyi", ".pyd",  # C extensions
    ".log", ".tmp", ".cache",
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

    def _get_relative_path(self, file_path: Path) -> str:
        """Возвращает относительный путь к файлу."""
        try:
            return str(file_path.relative_to(self.project_path))
        except ValueError:
            return str(file_path)

    def search(
        self,
        query: str,
        extensions: Optional[List[str]] = None,
        case_sensitive: bool = False,
        regex: bool = False,
        max_depth: int = MAX_DEPTH,
        max_results: int = MAX_RESULTS,
    ) -> List[Tuple[str, int, str, List[str]]]:
        """
        Поиск по содержимому файлов.
        
        Args:
            query: строка поиска
            extensions: список расширений (например, ['.py', '.js'])
            case_sensitive: чувствительность к регистру
            regex: использовать регулярное выражение
            max_depth: максимальная глубина поиска
            max_results: максимальное количество результатов
        
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

        # Подготовка расширений
        ext_set = set()
        if extensions:
            for ext in extensions:
                ext_set.add(ext.lower())
                if not ext.startswith('.'):
                    ext_set.add('.' + ext)

        try:
            for root, dirs, files in os.walk(self.project_path):
                # Фильтруем директории
                dirs[:] = [d for d in dirs if not self._should_skip_dir(d)]
                
                # Проверяем глубину
                rel_root = Path(root).relative_to(self.project_path)
                current_depth = len(rel_root.parts)
                if current_depth > max_depth:
                    dirs.clear()
                    continue

                for filename in files:
                    # Фильтр по расширениям
                    if ext_set:
                        ext = Path(filename).suffix.lower()
                        if ext not in ext_set:
                            continue

                    file_path = Path(root) / filename
                    if self._should_skip_file(file_path):
                        continue

                    # Читаем файл
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                            lines = f.readlines()
                    except Exception:
                        continue

                    # Ищем совпадения
                    for i, line in enumerate(lines, 1):
                        if pattern.search(line):
                            # Контекст
                            start = max(0, i - 1 - CONTEXT_LINES)
                            end = min(len(lines), i + CONTEXT_LINES)
                            context = [
                                f"{j+1:4d}| {lines[j].rstrip()}"
                                for j in range(start, end)
                            ]
                            
                            rel_path = self._get_relative_path(file_path)
                            results.append((rel_path, i, line.strip(), context))
                            
                            if len(results) >= max_results:
                                return results

        except Exception as e:
            return [("ERROR", 0, f"Ошибка поиска: {e}", [])]

        return results

    def search_formatted(
        self,
        query: str,
        **kwargs
    ) -> str:
        """
        Форматированный вывод для чата Z.
        
        Args:
            query: строка поиска
            **kwargs: параметры для search()
        
        Returns:
            отформатированная строка с результатами
        """
        results = self.search(query, **kwargs)
        
        if not results:
            return f"🔍 По запросу `{query}` ничего не найдено. Возможно, код в другом проекте или вы ищете чудеса."

        if results[0][0] == "ERROR":
            return f"⚠️ {results[0][2]}"

        lines = [f"🔍 Результаты поиска: `{query}` (найдено: {len(results)})\n"]
        
        for rel_path, line_no, match_line, context in results:
            lines.append(f"\n📄 {rel_path}:{line_no}")
            lines.append("```")
            for ctx_line in context:
                marker = " >>>" if f"{line_no}|" in ctx_line else "    "
                lines.append(f"{marker}{ctx_line}")
            lines.append("```")
        
        return "\n".join(lines)

    def find_symbol(
        self,
        symbol: str,
        language: str = "python",
        max_results: int = MAX_RESULTS
    ) -> str:
        """
        Умный поиск символа: функций, классов, переменных.
        
        Args:
            symbol: имя символа
            language: язык программирования
            max_results: максимальное количество результатов
        
        Returns:
            отформатированная строка с результатами
        """
        if not symbol or not symbol.strip():
            return "⚠️ Укажите имя символа для поиска."

        # Паттерны для разных языков
        patterns = []
        lang = language.lower()
        
        if lang in ("python", "py"):
            patterns = [
                rf"^\s*(def|class|async def)\s+{re.escape(symbol)}\b",
                rf"^\s*{re.escape(symbol)}\s*[=:\(]",
                rf"@\w+\s*\n\s*def\s+{re.escape(symbol)}\b",
            ]
        elif lang in ("javascript", "js", "ts", "typescript"):
            patterns = [
                rf"^\s*(function|const|let|var|class)\s+{re.escape(symbol)}\b",
                rf"^\s*{re.escape(symbol)}\s*[=:\(]",
                rf"export\s+(default\s+)?{re.escape(symbol)}\b",
            ]
        elif lang in ("java", "cpp", "c", "c++", "cs", "go", "rust"):
            patterns = [
                rf"\b{re.escape(symbol)}\s*[\(:]",
                rf"^\s*(public|private|protected|static)?\s*\w+\s+{re.escape(symbol)}\b",
            ]
        else:
            patterns = [rf"\b{re.escape(symbol)}\b"]

        all_results = []
        for pat in patterns:
            results = self.search(
                pat,
                regex=True,
                max_depth=5,
                max_results=max_results - len(all_results)
            )
            all_results.extend(results)
            if len(all_results) >= max_results:
                break

        if not all_results:
            return f"🔍 Символ `{symbol}` не найден. Возможно, он в другом проекте или ещё не написан."

        # Убираем дубликаты
        seen: Set[Tuple[str, int]] = set()
        unique_results = []
        for r in all_results:
            key = (r[0], r[1])
            if key not in seen:
                seen.add(key)
                unique_results.append(r)

        lines = [f"🔍 Символ `{symbol}` (найдено: {len(unique_results)})\n"]
        for rel_path, line_no, match_line, context in unique_results:
            lines.append(f"\n📄 {rel_path}:{line_no}")
            lines.append("```")
            for ctx_line in context:
                marker = " >>>" if f"{line_no}|" in ctx_line else "    "
                lines.append(f"{marker}{ctx_line}")
            lines.append("```")

        return "\n".join(lines)

    def find_import(self, module: str) -> str:
        """Ищет импорты модуля."""
        return self.search_formatted(
            rf"^(import|from)\s+{re.escape(module)}\b",
            regex=True,
            extensions=['.py']
        )

    def find_function_calls(self, function: str) -> str:
        """Ищет вызовы функции."""
        return self.search_formatted(
            rf"{re.escape(function)}\s*\(",
            regex=True,
            extensions=['.py', '.js']
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
    print("🧪 Тест code_search.py\n")
    
    # Ищем в текущем проекте
    searcher = CodeSearch("D:\\Zeta")
    
    print("📝 Тест 1: Поиск слова 'def'")
    result = searcher.search_formatted("def", extensions=['.py'])
    print(result[:500] + "..." if len(result) > 500 else result)
    print("-" * 40)
    
    print("📝 Тест 2: Поиск символа 'ask_zeta'")
    result = searcher.find_symbol("ask_zeta", "python")
    print(result[:500] + "..." if len(result) > 500 else result)
    print("-" * 40)
    
    print("\n✅ Тесты завершены!")