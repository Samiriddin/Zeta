# -*- coding: utf-8 -*-
"""
Модуль распознавания создателя Zeta.
Секретное слово → режим создателя.

ВАЖНО: секретное слово с опечатками — это специальная защита.
Никаких альтернатив! Только точное написание!
Аудит: логирует активацию режима.

Особенности:
    - Убирает пунктуацию при проверке (секрет сработает с «!», «.», «,»)
    - Быстрый путь: точное совпадение в начале
    - Не сохраняет пустой файл при reset
    - Декодирует bytes → str при загрузке
"""

import os
import re
import sys
import hashlib
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))


# ========== НАСТРОЙКИ ==========

CONFIG_PATH = Path("data/security/creator.dat")

# Секретное слово с опечатками — СПЕЦИАЛЬНО!
DEFAULT_SECRET = "Да здраствуйет владыку Kurayami"


# ========== ЛОГИРОВАНИЕ ==========

def _log(msg: str) -> None:
    logging.info(f"[CREATOR] {msg}")


def _log_warn(msg: str) -> None:
    logging.warning(f"[CREATOR] {msg}")


# ========== МЕНЕДЖЕР ==========

class CreatorManager:
    """Менеджер режима создателя."""

    def __init__(self):
        self.config_path = CONFIG_PATH
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        self._secret_hash: Optional[str] = None
        self._is_creator_mode: bool = False
        self._session_start: Optional[str] = None

        self._load()

    # ========== ХЭШИРОВАНИЕ ==========

    @staticmethod
    def _normalize(text: str) -> str:
        """Нормализация: нижний регистр + удаление пунктуации по краям."""
        if not text:
            return ""
        # Нижний регистр
        text = text.strip().lower()
        # Убираем пунктуацию в начале и конце
        text = text.strip(" .,!?;:…—–-\"'`«»()[]{}")
        # Сжимаем пробелы
        text = re.sub(r"\s+", " ", text)
        return text

    def _hash(self, text: str) -> str:
        normalized = self._normalize(text)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    # ========== СЕКРЕТНОЕ СЛОВО ==========

    def set_secret(self, secret: str) -> bool:
        """Устанавливает секретное слово."""
        if not secret or len(secret.strip()) < 2:
            return False

        self._secret_hash = self._hash(secret)
        self._save()
        _log("Секретное слово установлено (с опечатками)")
        return True

    def has_secret(self) -> bool:
        return self._secret_hash is not None

    def check_secret(self, text: str) -> bool:
        """
        Проверяет, содержит ли сообщение секретное слово.
        Секрет ищется как подстрока по границам слов (до 8 слов).
        """
        if not text or not self._secret_hash:
            return False

        # Быстрый путь: нормализуем текст и проверим
        text_norm = self._normalize(text)
        if not text_norm:
            return False

        # 1. Точное совпадение всей строки
        if self._hash(text_norm) == self._secret_hash:
            return True

        # 2. Ограничение на длину: если сообщение > 200 символов — вряд ли секрет
        if len(text_norm) > 200:
            return False

        # 3. Поиск подстроки по словам (до 8 слов)
        words = text_norm.split()
        max_len = min(len(words), 8)

        for i in range(len(words)):
            for j in range(i + 1, min(i + max_len + 1, len(words) + 1)):
                candidate = " ".join(words[i:j])
                if self._hash(candidate) == self._secret_hash:
                    return True

        return False

    # ========== РЕЖИМ ==========

    def activate(self) -> bool:
        """Активирует режим создателя (с аудитом)."""
        if self._is_creator_mode:
            return True

        self._is_creator_mode = True
        self._session_start = datetime.now().isoformat()
        _log("РЕЖИМ СОЗДАТЕЛЯ АКТИВИРОВАН")

        # Аудит
        try:
            from security.audit import get_audit
            get_audit().log_creator_activation()
        except Exception:
            pass

        return True

    def deactivate(self) -> bool:
        """Деактивирует режим (с аудитом)."""
        if not self._is_creator_mode:
            return True

        self._is_creator_mode = False
        self._session_start = None
        _log("Режим создателя деактивирован")

        # Аудит — используем log_security (универсально)
        try:
            from security.audit import get_audit
            audit = get_audit()
            # Пробуем разные методы (чтобы работало с любой версией audit)
            if hasattr(audit, "log_security"):
                audit.log_security("creator_deactivated", "Режим создателя выключен")
            elif hasattr(audit, "log_system"):
                audit.log_system("creator_deactivated", "Режим создателя выключен")
        except Exception:
            pass

        return True

    def is_active(self) -> bool:
        return self._is_creator_mode

    # ========== СОХРАНЕНИЕ ==========

    def _save(self) -> None:
        """Сохраняет хэш. Если пусто — удаляет файл."""
        # Если хэша нет — удаляем файл
        if not self._secret_hash:
            if self.config_path.exists():
                try:
                    self.config_path.unlink()
                    _log("Файл creator.dat удалён (пустой)")
                except Exception as e:
                    _log_warn(f"Не удалось удалить creator.dat: {e}")
            return

        try:
            from security.crypto import get_crypto
            crypto = get_crypto()

            encrypted = crypto.encrypt(self._secret_hash)

            # На случай, если encrypt вернул str
            if isinstance(encrypted, str):
                encrypted = encrypted.encode("utf-8")

            with open(self.config_path, "wb") as f:
                f.write(encrypted)

            _log(f"Сохранён: {self.config_path}")
        except Exception as e:
            _log_warn(f"Ошибка сохранения: {e}")

    def _load(self) -> None:
        """Загружает хэш. Декодирует bytes → str."""
        if not self.config_path.exists():
            _log("creator.dat не найден — секрет не установлен")
            return

        try:
            from security.crypto import get_crypto
            crypto = get_crypto()

            with open(self.config_path, "rb") as f:
                encrypted = f.read()

            if not encrypted:
                _log_warn("creator.dat пустой — игнорирую")
                return

            data = crypto.decrypt(encrypted)

            # Декодируем bytes → str
            if isinstance(data, bytes):
                data = data.decode("utf-8")

            if data:
                self._secret_hash = data
                _log(f"Конфиг создателя загружен (hash: {data[:16]}...)")
            else:
                _log_warn("Расшифровка вернула пусто")
        except Exception as e:
            _log_warn(f"Ошибка загрузки: {e}")

    def reset(self) -> None:
        """Сбрасывает секретное слово (с аудитом)."""
        had_secret = self._secret_hash is not None

        self._secret_hash = None
        self._is_creator_mode = False
        self._session_start = None

        if self.config_path.exists():
            try:
                self.config_path.unlink()
            except Exception:
                pass

        _log("Секретное слово сброшено")

        # Аудит
        if had_secret:
            try:
                from security.audit import get_audit
                audit = get_audit()
                if hasattr(audit, "log_security"):
                    audit.log_security("creator_reset", "Секретное слово сброшено")
            except Exception:
                pass

    # ========== СТАТУС ==========

    def status(self) -> dict:
        return {
            "has_secret": self.has_secret(),
            "creator_mode": self._is_creator_mode,
            "session_start": self._session_start,
            "exact_match_only": True,
            "config_path": str(self.config_path),
        }


# ========== ГЛОБАЛЬНЫЙ ==========

_creator: Optional[CreatorManager] = None


def get_creator() -> CreatorManager:
    global _creator
    if _creator is None:
        _creator = CreatorManager()
    return _creator


# ========== ЭКСПОРТ ==========

__all__ = ["CreatorManager", "get_creator", "DEFAULT_SECRET"]


# ========== ТЕСТ ==========

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    creator = get_creator()

    print("🔑 Менеджер создателя Zeta")
    print("=" * 60)
    print("⚠️  Секретное слово с ОПЕЧАТКАМИ — защита!")
    print("=" * 60)

    creator.reset()
    print("\n🔐 Установка секретного слова...")
    creator.set_secret(DEFAULT_SECRET)
    print("✅ Установлено")

    print("\n🧪 Проверка:")
    tests = [
        # Должны сработать
        ("Да здраствуйет владыку Kurayami", True),
        ("да здраствуйет владыку kurayami", True),
        ("Привет! Да здраствуйет владыку Kurayami", True),
        ("Да здраствуйет владыку Kurayami!", True),   # ← с восклицательным
        ("Да здраствуйет владыку Kurayami.", True),   # ← с точкой
        ("Да здраствуйет владыку Kurayami, как дела?", True),  # ← с запятой

        # Не должны
        ("Да здравствует владыка Kurayami", False),
        ("Куrayami", False),
        ("Что такое атом?", False),
        ("привет", False),
    ]

    for text, expected in tests:
        result = creator.check_secret(text)
        status = "✅" if result == expected else "❌"
        mark = "ДА" if result else "нет"
        print(f"   {status} {mark:3s} | {text[:55]!r}")

    print(f"\n📊 Статус: {creator.status()}")

    print("\n📝 Тест: Активация / деактивация")
    creator.activate()
    print(f"   is_active: {creator.is_active()}")
    creator.deactivate()
    print(f"   is_active: {creator.is_active()}")

    print("\n📝 Тест: Сброс")
    creator.reset()
    print(f"   has_secret: {creator.has_secret()}")

    print("\n" + "=" * 60)
    print("✅ Тесты пройдены!")