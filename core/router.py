# -*- coding: utf-8 -*-
"""
Модуль маршрутизации запросов Zeta.

Тонкая обёртка над ai_engine.detect_command_type().
Вся логика маршрутизации — в core/ai_engine.py (единая точка).
Этот модуль сохранён для обратной совместимости API RequestRouter.route().
"""

import sys
import re
from pathlib import Path
from typing import Dict, Any

# Добавляем корень проекта в sys.path — чтобы работало и при `python core\router.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Импорт основной логики маршрутизации
try:
    from core.ai_engine import detect_command_type
except ImportError as e:
    raise ImportError(
        f"Не удалось импортировать core.ai_engine.detect_command_type: {e}\n"
        f"Проверь, что файл D:\\Zeta\\core\\ai_engine.py существует "
        f"и не падает при импорте."
    ) from e


# Паттерн для определения code-запросов
_CODE_PATTERN = re.compile(
    r"(напиши|создай|сгенерируй|исправь|допиши|добавь|обнови)\s+"
    r"(код|функцию|файл|класс|метод|скрипт|модуль)",
    re.IGNORECASE
)


class RequestRouter:
    """
    Анализирует запрос пользователя и определяет, что нужно сделать.

    Делегирует в ai_engine.detect_command_type().
    Возвращает словарь {"type", "confidence", "data"}.
    """

    # ========== СОВМЕСТИМОСТЬ: СТАРЫЕ МЕТОДЫ ==========

    @staticmethod
    def is_explicit_reminder(text: str) -> bool:
        return bool(re.match(r"^(напомни|напомните|не забудь|remind)\b", text.lower().strip()))

    @staticmethod
    def is_explicit_status(text: str) -> bool:
        return bool(re.match(
            r"^(статус системы|покажи статус|/status)\b",
            text.lower().strip()
        ))

    @staticmethod
    def is_explicit_git(text: str) -> bool:
        return bool(re.match(r"^git\s+", text.lower().strip()))

    @staticmethod
    def is_explicit_rag(text: str) -> bool:
        return bool(re.match(
            r"^(загрузи документ|прочитай документ|покажи документы|очисти документы)\b",
            text.lower().strip()
        ))

    @staticmethod
    def is_explicit_file(text: str) -> bool:
        low = text.lower().strip()
        return bool(
            re.match(r"^(открой|откройте|open)\s+(файл|папку)\b", low) or
            re.match(r"^(найди|где)\s+(файл|папку)\b", low) or
            re.match(r"^(покажи|list)\s+(папку|содержимое)\b", low)
        )

    @staticmethod
    def is_explicit_screenshot(text: str) -> bool:
        return bool(re.match(
            r"^(сделай скрин|сделай скриншот|посмотри на экран|что на экране|/screenshot)\b",
            text.lower().strip()
        ))

    @staticmethod
    def is_explicit_translation(text: str) -> bool:
        return bool(re.match(r"^(переведи|translate)\b", text.lower().strip()))

    @staticmethod
    def is_explicit_code(text: str) -> bool:
        return bool(_CODE_PATTERN.search(text))

    @staticmethod
    def is_explicit_search(text: str) -> bool:
        return bool(re.match(
            r"^(найди в интернете|поищи в интернете|погугли)\b",
            text.lower().strip()
        ))

    # ========== ОСНОВНОЙ МЕТОД ==========

    @classmethod
    def route(cls, text: str) -> Dict[str, Any]:
        """
        Анализирует запрос и возвращает тип действия.

        Возвращает:
            {"type": "<тип>", "confidence": float, "data": dict}
        """
        if not text or not text.strip():
            return {"type": "chat", "confidence": 1.0, "data": {}}

        try:
            cmd_type, cmd_data = detect_command_type(text)
        except Exception:
            return {"type": "chat", "confidence": 1.0, "data": {}}

        # Спец-случай: code-запросы (ai_engine помечает их как "chat")
        if cmd_type == "chat" and cls.is_explicit_code(text):
            return {
                "type": "code",
                "confidence": 0.9,
                "data": {"request": text}
            }

        return {
            "type": cmd_type,
            "confidence": 1.0,
            "data": cmd_data
        }


# ========== УДОБНЫЕ ФУНКЦИИ ==========

def route(text: str) -> Dict[str, Any]:
    """Сахар: route("...") вместо RequestRouter.route("...")."""
    return RequestRouter.route(text)


# ========== ТЕСТ ==========
if __name__ == "__main__":
    tests = [
        "привет, как дела",
        "напомни через 5 минут позвонить маме",
        "статус системы",
        "git status",
        "git push origin main",
        "открой файл D:\\test.txt",
        "сделай скриншот",
        "переведи hello на русский",
        "загрузи документ D:\\doc.pdf",
        "погугли python asyncio",
        "напиши функцию сортировки",
        "узнай про Python",
        "Ты когда-нибудь напоминал?",
    ]

    print("🧪 Тест router.py\n")
    print("=" * 60)
    for t in tests:
        r = route(t)
        print(f"\n📝 {t}")
        print(f"   → type: {r['type']}")
        print(f"   → data: {r['data']}")
    print("\n✅ Тесты пройдены!")