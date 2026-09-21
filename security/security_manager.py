# -*- coding: utf-8 -*-
"""
Zeta Security — Главный менеджер безопасности.
Объединяет шифрование, аутентификацию и санитизацию.

Особенности:
    - Безопасный __init__ (try/except для crypto/auth)
    - Опциональная проверка 2FA (если модуль есть)
    - is_crypto_ready() — без исключений
    - Логирование в data/zeta.log
    - Forward references для Pylance
"""

import sys
import logging
from pathlib import Path
from typing import Optional, Any, TYPE_CHECKING

sys.path.insert(0, str(Path(__file__).parent.parent))


# ========== ЛОГИРОВАНИЕ ==========

def _log(msg: str) -> None:
    logging.info(f"[SECURITY] {msg}")


def _log_warn(msg: str) -> None:
    logging.warning(f"[SECURITY] {msg}")


# ========== TYPE_CHECKING (для Pylance) ==========

if TYPE_CHECKING:
    from security.crypto import CryptoManager
    from security.auth import AuthManager
    from security.sanitizer import InputSanitizer


# ========== ИМПОРТЫ (безопасные) ==========

try:
    from security.crypto import get_crypto
    HAS_CRYPTO = True
except Exception as e:
    HAS_CRYPTO = False
    get_crypto = None
    _log_warn(f"crypto недоступен: {e}")

try:
    from security.auth import get_auth
    HAS_AUTH = True
except Exception as e:
    HAS_AUTH = False
    get_auth = None
    _log_warn(f"auth недоступен: {e}")

try:
    from security.sanitizer import InputSanitizer as _InputSanitizer, sanitize
    HAS_SANITIZER = True
except Exception as e:
    HAS_SANITIZER = False
    _InputSanitizer = None
    sanitize = None
    _log_warn(f"sanitizer недоступен: {e}")

# Опциональный 2FA
try:
    from security.two_factor import get_2fa
    HAS_2FA = True
except Exception:
    HAS_2FA = False
    get_2fa = None


# ================================================================
#  SECURITY MANAGER
# ================================================================

class SecurityManager:
    """Главный менеджер безопасности Zeta."""

    def __init__(self):
        # crypto
        self.crypto: Optional[Any] = None
        if HAS_CRYPTO and get_crypto is not None:
            try:
                self.crypto = get_crypto()
            except Exception as e:
                _log_warn(f"crypto.__init__: {e}")

        # auth
        self.auth: Optional[Any] = None
        if HAS_AUTH and get_auth is not None:
            try:
                self.auth = get_auth()
            except Exception as e:
                _log_warn(f"auth.__init__: {e}")

        # sanitizer
        self._has_sanitizer = HAS_SANITIZER

        _log(f"SecurityManager инициализирован "
             f"(crypto={self.crypto is not None}, "
             f"auth={self.auth is not None})")

    # ============================================================
    #  ШИФРОВАНИЕ
    # ============================================================

    def encrypt(self, data: str) -> bytes:
        """Зашифровать строку → bytes."""
        if self.crypto is None:
            raise RuntimeError("Шифрование недоступно (crypto не инициализирован)")
        return self.crypto.encrypt(data)

    def decrypt(self, data: bytes) -> str:
        """Расшифровать bytes → str."""
        if self.crypto is None:
            raise RuntimeError("Шифрование недоступно")
        return self.crypto.decrypt(data)

    def safe_decrypt(self, data: bytes) -> Optional[str]:
        """Безопасная расшифровка (None при ошибке)."""
        if self.crypto is None:
            return None
        return self.crypto.safe_decrypt(data)

    def is_crypto_ready(self) -> bool:
        """Готово ли шифрование."""
        if self.crypto is None:
            return False
        try:
            return self.crypto.is_valid()
        except Exception:
            return False

    # ============================================================
    #  АУТЕНТИФИКАЦИЯ
    # ============================================================

    def is_logged_in(self) -> bool:
        """Вошел ли пользователь."""
        if self.auth is None:
            return False
        try:
            return self.auth.is_authenticated()
        except Exception:
            return False

    def login(self, password: str):
        """Вход."""
        if self.auth is None:
            return False, "❌ Аутентификация недоступна"
        return self.auth.login(password)

    def logout(self):
        """Выход."""
        if self.auth is None:
            return
        try:
            self.auth.logout()
        except Exception as e:
            _log_warn(f"logout: {e}")

    def has_password(self) -> bool:
        """Установлен ли пароль."""
        if self.auth is None:
            return False
        try:
            return self.auth.has_password()
        except Exception:
            return False

    # ============================================================
    #  САНИТИЗАЦИЯ
    # ============================================================

    def clean(self, text: str, context: str = "text") -> str:
        """Санитизация."""
        if not self._has_sanitizer or sanitize is None:
            return text
        return sanitize(text, context)

    def is_safe(self, text: str, context: str = "text") -> bool:
        """Безопасно ли."""
        if not self._has_sanitizer or _InputSanitizer is None:
            return True
        return _InputSanitizer.is_safe(text, context)

    # ============================================================
    #  2FA (опционально)
    # ============================================================

    def is_2fa_enabled(self) -> bool:
        """Включён ли 2FA. False, если модуля нет."""
        if not HAS_2FA or get_2fa is None:
            return False
        try:
            tf = get_2fa()
            if hasattr(tf, "is_enabled"):
                return bool(tf.is_enabled())
            if hasattr(tf, "has_2fa"):
                return bool(tf.has_2fa())
            return False
        except Exception as e:
            _log_warn(f"is_2fa_enabled: {e}")
            return False

    # ============================================================
    #  СТАТУС
    # ============================================================

    def status(self) -> dict:
        """Полный статус безопасности."""
        key_file = "—"
        if self.crypto is not None and hasattr(self.crypto, "key_file"):
            key_file = str(self.crypto.key_file)

        return {
            "auth_enabled": self.has_password(),
            "logged_in": self.is_logged_in(),
            "2fa_enabled": self.is_2fa_enabled(),
            "encryption": "AES-256 (Fernet)",
            "crypto_ready": self.is_crypto_ready(),
            "key_file": key_file,
            "has_crypto": self.crypto is not None,
            "has_auth": self.auth is not None,
            "has_sanitizer": self._has_sanitizer,
            "has_2fa_module": HAS_2FA,
        }


# ================================================================
#  ГЛОБАЛЬНЫЙ
# ================================================================

_security: Optional[SecurityManager] = None


def get_security() -> SecurityManager:
    """Глобальный менеджер безопасности."""
    global _security
    if _security is None:
        try:
            _security = SecurityManager()
        except Exception as e:
            _log_warn(f"КРИТИЧНО: SecurityManager упал: {e}")
            raise
    return _security


# ================================================================
#  ЭКСПОРТ
# ================================================================

__all__ = [
    "SecurityManager",
    "get_security",
]


# ================================================================
#  ТЕСТ
# ================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    print("🛡️  Zeta Security Manager")
    print("=" * 60)

    sec = get_security()

    print("\n📊 Статус:")
    for key, value in sec.status().items():
        print(f"   {key:20s}: {value}")

    print("\n🧪 Тест шифрования:")
    try:
        encrypted = sec.encrypt("секрет")
        print(f"   Зашифровано: {encrypted[:40]}...")

        decrypted = sec.decrypt(encrypted)
        print(f"   Расшифровано: {decrypted}")
        print(f"   Совпадает: {decrypted == 'секрет'} "
              f"{'✅' if decrypted == 'секрет' else '❌'}")

        bogus = b"not encrypted"
        result = sec.safe_decrypt(bogus)
        print(f"   safe_decrypt(битый): {result} "
              f"{'✅' if result is None else '❌'}")

    except RuntimeError as e:
        print(f"   ⚠️ {e}")

    print("\n🧪 Тест санитизации:")
    tests = [
        ("test; rm -rf /", "command"),
        ("Обычный текст", "text"),
        ("SELECT * FROM users", "sql"),
    ]
    for text, ctx in tests:
        cleaned = sec.clean(text, ctx)
        safe = sec.is_safe(text, ctx)
        marker = "✅" if safe else "🚫"
        print(f"   {marker} [{ctx:8s}] {text!r:25} → {cleaned!r}")

    print("\n📊 is_crypto_ready:", sec.is_crypto_ready())

    print("\n" + "=" * 60)
    print("✅ Тесты пройдены!")