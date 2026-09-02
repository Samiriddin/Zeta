# -*- coding: utf-8 -*-
"""
Модуль маршрутизации запросов Zeta.
Определяет, что хочет пользователь: команду или обычный вопрос.
"""

import os  # ← ДОБАВЛЕНО!
import re
from typing import Optional, Tuple, Dict, Any


class RequestRouter:
    """
    Анализирует запрос пользователя и определяет, что нужно сделать.
    """

    # ========== ЯВНЫЕ КОМАНДЫ ==========

    @staticmethod
    def is_explicit_reminder(text: str) -> bool:
        """Проверяет, есть ли явная команда на напоминание."""
        keywords = ["напомни", "напомните", "remind", "не забудь", "будильник", "напоминание"]
        return any(kw in text.lower() for kw in keywords)

    @staticmethod
    def is_explicit_status(text: str) -> bool:
        """Проверяет, есть ли явная команда на статус системы."""
        keywords = ["статус системы", "состояние системы", "загрузка", "cpu", "ram", "диск", "мониторинг"]
        return any(kw in text.lower() for kw in keywords)

    @staticmethod
    def is_explicit_git(text: str) -> bool:
        """Проверяет, есть ли явная команда Git."""
        keywords = ["git status", "git diff", "git commit", "git log", "git branch", "git stash"]
        return any(kw in text.lower() for kw in keywords)

    @staticmethod
    def is_explicit_rag(text: str) -> bool:
        """Проверяет, есть ли явная команда RAG (документы)."""
        keywords = ["загрузи документ", "загрузи файл", "прочитай документ", "покажи документы", "очисти документы"]
        return any(kw in text.lower() for kw in keywords)

    @staticmethod
    def is_explicit_file(text: str) -> bool:
        """Проверяет, есть ли явная команда для файлов."""
        keywords = ["открой файл", "открой папку", "найди файл", "найди папку", "покажи папку", "покажи файл"]
        return any(kw in text.lower() for kw in keywords)

    @staticmethod
    def is_explicit_screenshot(text: str) -> bool:
        """Проверяет, есть ли явная команда для скриншота."""
        keywords = ["посмотри на экран", "сделай скрин", "скриншот", "что на экране", "опиши экран"]
        return any(kw in text.lower() for kw in keywords)

    @staticmethod
    def is_explicit_translation(text: str) -> bool:
        """Проверяет, есть ли явная команда для перевода."""
        keywords = ["переведи", "перевод", "translate"]
        return any(kw in text.lower() for kw in keywords)

    @staticmethod
    def is_explicit_code(text: str) -> bool:
        """Проверяет, есть ли явная команда для кода."""
        keywords = ["напиши код", "создай код", "исправь код", "сгенерируй код"]
        return any(kw in text.lower() for kw in keywords)

    @staticmethod
    def is_explicit_search(text: str) -> bool:
        """Проверяет, есть ли явная команда для поиска."""
        keywords = ["найди в интернете", "поищи", "узнай", "проверь"]
        return any(kw in text.lower() for kw in keywords)

    # ========== ОСНОВНОЙ МЕТОД ==========

    @classmethod
    def route(cls, text: str) -> Dict[str, Any]:
        """
        Анализирует запрос и возвращает тип действия.
        """
        text_lower = text.lower().strip()

        # --- Проверяем явные команды ---

        if cls.is_explicit_reminder(text):
            from modules.notifications import needs_reminder
            minutes, reminder_text = needs_reminder(text)
            if minutes:
                return {
                    "type": "reminder",
                    "confidence": 1.0,
                    "data": {"minutes": minutes, "text": reminder_text}
                }

        if cls.is_explicit_status(text):
            return {"type": "status", "confidence": 1.0, "data": {}}

        if cls.is_explicit_git(text):
            if "status" in text_lower:
                return {"type": "git", "confidence": 1.0, "data": {"command": "status"}}
            if "diff" in text_lower:
                return {"type": "git", "confidence": 1.0, "data": {"command": "diff"}}
            if "commit" in text_lower:
                return {"type": "git", "confidence": 1.0, "data": {"command": "commit"}}
            if "log" in text_lower:
                return {"type": "git", "confidence": 1.0, "data": {"command": "log"}}
            return {"type": "git", "confidence": 1.0, "data": {"command": "status"}}

        if cls.is_explicit_rag(text):
            return {"type": "rag", "confidence": 1.0, "data": {"command": text}}

        if cls.is_explicit_file(text):
            from modules.file_manager import needs_file_action
            action, detail = needs_file_action(text)
            if action:
                return {"type": "file", "confidence": 1.0, "data": {"action": action, "detail": detail}}

        if cls.is_explicit_screenshot(text):
            return {"type": "screenshot", "confidence": 1.0, "data": {}}

        if cls.is_explicit_translation(text):
            from modules.translator import needs_translation
            lang, translate_text = needs_translation(text)
            if lang and translate_text:
                return {"type": "translation", "confidence": 1.0, "data": {"lang": lang, "text": translate_text}}

        if cls.is_explicit_code(text):
            return {"type": "code", "confidence": 0.9, "data": {"request": text}}

        if cls.is_explicit_search(text):
            return {"type": "search", "confidence": 0.9, "data": {"query": text}}

        # --- Если ни одна явная команда не сработала → ЭТО ЧАТ! ---

        return {"type": "chat", "confidence": 1.0, "data": {}}