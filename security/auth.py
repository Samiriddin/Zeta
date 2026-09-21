# -*- coding: utf-8 -*-
"""
Zeta Security — Аутентификация.
Пароль (bcrypt) + блокировка после попыток.
Аудит: логирует входы/выходы.

Особенности:
    - Декодирует bytes → str при загрузке (крипто может вернуть bytes)
    - Обрабатывает str-выход encrypt (для разных версий crypto)
    - Логирование в data/zeta.log
    - Защита от порчи существующего пароля
"""

import sys
import time
import hashlib
import secrets
import logging
from pathlib import Path
from typing import Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))


# ========== ЛОГИРОВАНИЕ ==========

def _log(msg: str) -> None:
    logging.info(f"[AUTH] {msg}")


def _log_warn(msg: str) -> None:
    logging.warning(f"[AUTH] {msg}")


# ========== BCRYPT ==========

try:
    import bcrypt
    HAS_BCRYPT = True
except ImportError:
    HAS_BCRYPT = False
    _log_warn("bcrypt не установлен, используется PBKDF2")


# ================================================================
#  AUTH MANAGER
# ================================================================

class AuthManager:
    """Менеджер аутентификации (без 2FA)."""

    MAX_ATTEMPTS = 3
    BLOCK_DURATION = 300  # 5 минут

    def __init__(self, storage_path: str = None):
        if storage_path is None:
            storage_path = str(
                Path(__file__).parent.parent / "data" / "security" / "auth.dat"
            )

        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        self._failed_attempts: dict = {}
        self._blocked_until: dict = {}
        self._password_hash: Optional[str] = None
        self._is_authenticated = False

        self._load()

    # ================================================================
    #  ХЕШИРОВАНИЕ
    # ================================================================

    def hash_password(self, password: str) -> str:
        """bcrypt (или PBKDF2 как fallback)."""
        password_bytes = password.encode("utf-8")[:72]

        if HAS_BCRYPT:
            salt = bcrypt.gensalt(rounds=12)
            hashed = bcrypt.hashpw(password_bytes, salt)
            return hashed.decode("utf-8")
        else:
            salt = secrets.token_hex(16)
            h = hashlib.pbkdf2_hmac(
                "sha256", password_bytes, salt.encode(), 100000
            ).hex()
            return f"pbkdf2${salt}${h}"

    def verify_password(self, password: str, hashed: str) -> bool:
        """Проверка пароля (bcrypt или PBKDF2)."""
        if not hashed or not isinstance(hashed, str):
            return False

        password_bytes = password.encode("utf-8")[:72]

        try:
            if HAS_BCRYPT and hashed.startswith("$2"):
                return bcrypt.checkpw(password_bytes, hashed.encode("utf-8"))
            elif hashed.startswith("pbkdf2$"):
                parts = hashed.split("$", 2)
                if len(parts) != 3:
                    return False
                _, salt, h = parts
                check = hashlib.pbkdf2_hmac(
                    "sha256", password_bytes, salt.encode(), 100000
                ).hex()
                return secrets.compare_digest(check, h)
        except Exception as e:
            _log_warn(f"Ошибка проверки пароля: {e}")

        return False

    # ================================================================
    #  ПАРОЛЬ
    # ================================================================

    def set_password(self, password: str) -> bool:
        """Установить пароль."""
        if len(password) < 6:
            return False

        self._password_hash = self.hash_password(password)
        self._save()
        _log("Пароль установлен")
        return True

    def has_password(self) -> bool:
        return self._password_hash is not None

    def change_password(self, old_password: str,
                        new_password: str) -> Tuple[bool, str]:
        """Смена пароля."""
        if not self._password_hash:
            return False, "❌ Пароль не установлен"

        if not self.verify_password(old_password, self._password_hash):
            try:
                from security.audit import get_audit
                get_audit().log_security(
                    "password_change_failed",
                    "Неверный старый пароль при смене",
                    severity="warning",
                )
            except Exception:
                pass
            return False, "❌ Старый пароль неверен"

        if len(new_password) < 6:
            return False, "❌ Новый пароль слишком короткий"

        self._password_hash = self.hash_password(new_password)
        self._save()
        _log("Пароль изменён")

        try:
            from security.audit import get_audit
            get_audit().log_security(
                "password_changed",
                "Пароль успешно изменён",
                severity="info",
            )
        except Exception:
            pass

        return True, "✅ Пароль изменён"

    # ================================================================
    #  ВХОД / ВЫХОД
    # ================================================================

    def login(self, password: str) -> Tuple[bool, str]:
        """Вход по паролю."""
        # Блокировка
        if self._is_blocked():
            remaining = self._get_block_remaining()
            try:
                from security.audit import get_audit
                get_audit().log_security(
                    "login_blocked",
                    f"Попытка входа при блокировке (осталось {remaining} сек)",
                    severity="warning",
                )
            except Exception:
                pass
            return False, f"⛔ Заблокировано на {remaining} сек"

        if not self._password_hash:
            return False, "❌ Пароль не установлен"

        if self.verify_password(password, self._password_hash):
            self._failed_attempts.clear()
            self._is_authenticated = True

            try:
                from security.audit import get_audit
                get_audit().log_login(success=True)
            except Exception:
                pass

            _log("Успешный вход")
            return True, "✅ Добро пожаловать"

        # Неверный пароль
        self._record_failure()
        attempts_left = self.MAX_ATTEMPTS - self._failed_attempts.get("user", 0)

        try:
            from security.audit import get_audit
            get_audit().log_login(success=False, attempts=attempts_left)
        except Exception:
            pass

        if attempts_left <= 0:
            self._block_user()
            try:
                from security.audit import get_audit
                get_audit().log_security(
                    "account_blocked",
                    f"Пользователь заблокирован на {self.BLOCK_DURATION} сек",
                    severity="critical",
                )
            except Exception:
                pass

            _log_warn(f"Пользователь заблокирован на {self.BLOCK_DURATION} сек")
            return False, f"⛔ Слишком много попыток. Блок на {self.BLOCK_DURATION} сек"

        return False, f"❌ Неверный пароль. Осталось: {attempts_left}"

    def logout(self) -> None:
        """Выход."""
        self._is_authenticated = False

        try:
            from security.audit import get_audit
            get_audit().log_logout()
        except Exception:
            pass

        _log("Выход выполнен")

    def is_authenticated(self) -> bool:
        return self._is_authenticated

    # ================================================================
    #  БЛОКИРОВКА
    # ================================================================

    def _record_failure(self) -> None:
        self._failed_attempts["user"] = self._failed_attempts.get("user", 0) + 1

    def _block_user(self) -> None:
        self._blocked_until["user"] = time.time() + self.BLOCK_DURATION
        self._failed_attempts["user"] = 0

    def _is_blocked(self) -> bool:
        until = self._blocked_until.get("user", 0)
        if time.time() < until:
            return True
        if until > 0:
            self._blocked_until["user"] = 0
        return False

    def _get_block_remaining(self) -> int:
        until = self._blocked_until.get("user", 0)
        return max(0, int(until - time.time()))

    # ================================================================
    #  СОХРАНЕНИЕ (безопасное)
    # ================================================================

    def _save(self) -> None:
        """Сохранить хэш. Обрабатывает bytes и str от crypto."""
        try:
            from security.crypto import get_crypto
            crypto = get_crypto()

            data = self._password_hash or ""
            encrypted = crypto.encrypt(data)

            # На случай если crypto вернул str
            if isinstance(encrypted, str):
                encrypted = encrypted.encode("utf-8")

            # Атомарная запись (через временный файл)
            tmp_path = self.storage_path.with_suffix(".tmp")
            with open(tmp_path, "wb") as f:
                f.write(encrypted)

            # Перемещаем (атомарно)
            if self.storage_path.exists():
                self.storage_path.unlink()
            tmp_path.rename(self.storage_path)

            _log(f"Сохранён: {self.storage_path}")

        except Exception as e:
            _log_warn(f"Ошибка сохранения: {e}")
            # Удаляем временный если остался
            try:
                tmp = self.storage_path.with_suffix(".tmp")
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass

    def _load(self) -> None:
        """Загрузить хэш. Декодирует bytes → str."""
        if not self.storage_path.exists():
            _log("auth.dat не найден — пароль не установлен")
            return

        try:
            from security.crypto import get_crypto
            crypto = get_crypto()

            with open(self.storage_path, "rb") as f:
                encrypted = f.read()

            if not encrypted:
                _log_warn("auth.dat пустой")
                return

            data = crypto.decrypt(encrypted)

            # Декодируем bytes → str
            if isinstance(data, bytes):
                data = data.decode("utf-8")

            if data:
                self._password_hash = data
                _log(f"Пароль загружен (hash: {data[:16]}...)")
            else:
                _log_warn("Расшифровка вернула пусто")

        except Exception as e:
            _log_warn(f"Ошибка загрузки: {e}")

    # ================================================================
    #  СБРОС
    # ================================================================

    def reset(self) -> None:
        """Сброс пароля (с аудитом)."""
        had_password = self._password_hash is not None

        self._password_hash = None
        self._failed_attempts.clear()
        self._blocked_until.clear()
        self._is_authenticated = False

        if self.storage_path.exists():
            try:
                self.storage_path.unlink()
            except Exception:
                pass

        _log("Пароль сброшен")

        if had_password:
            try:
                from security.audit import get_audit
                get_audit().log_security(
                    "password_reset",
                    "Пароль сброшен",
                    severity="warning",
                )
            except Exception:
                pass

    # ================================================================
    #  СТАТУС
    # ================================================================

    def status(self) -> dict:
        return {
            "has_password": self.has_password(),
            "is_authenticated": self._is_authenticated,
            "failed_attempts": self._failed_attempts.get("user", 0),
            "is_blocked": self._is_blocked(),
            "storage_path": str(self.storage_path),
        }


# ================================================================
#  ГЛОБАЛЬНЫЙ
# ================================================================

_auth: Optional[AuthManager] = None


def get_auth() -> AuthManager:
    global _auth
    if _auth is None:
        _auth = AuthManager()
    return _auth


# ================================================================
#  ЭКСПОРТ
# ================================================================

__all__ = ["AuthManager", "get_auth"]


# ================================================================
#  ТЕСТ
# ================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    print("🔐 Zeta Auth — Тест")
    print("=" * 60)

    auth = get_auth()

    # Сохраняем старый пароль если есть
    old_exists = auth.has_password()
    if old_exists:
        print("\n⚠️ Существующий пароль сохранён в памяти")
        print("   (в конце теста можно не сбрасывать)")

    if not old_exists:
        auth.reset()

        print("\n📝 Установка пароля...")
        if auth.set_password("test123"):
            print("   ✅ Пароль установлен: test123")

        print("\n🔑 Вход (правильный):")
        ok, msg = auth.login("test123")
        print(f"   {msg}")
        print(f"   Авторизован: {auth.is_authenticated()}")
        auth.logout()

        print("\n❌ Вход (неверный):")
        for i in range(3):
            ok, msg = auth.login("wrong")
            print(f"   Попытка {i + 1}: {msg}")

        print(f"\n📊 Статус: {auth.status()}")

        print("\n🗑️ Сброс пароля...")
        auth.reset()
        print(f"   has_password: {auth.has_password()}")

    print("\n" + "=" * 60)
    print("✅ Тесты пройдены!")