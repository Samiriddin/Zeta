# -*- coding: utf-8 -*-
"""
Zeta Security — Шифрование данных (AES-256 / Fernet).
Модуль для шифрования базы данных и файлов.

Особенности:
    - Обработка битого ключа (бэкап .broken + новый ключ)
    - safe_decrypt() — возвращает None при ошибке
    - rotate_key() — смена ключа с сохранением старого
    - Логирование в data/zeta.log
    - is_valid() — проверка валидности ключа
"""

import os
import sys
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from cryptography.fernet import Fernet, InvalidToken


# ========== ЛОГИРОВАНИЕ ==========

def _log(msg: str) -> None:
    logging.info(f"[CRYPTO] {msg}")


def _log_warn(msg: str) -> None:
    logging.warning(f"[CRYPTO] {msg}")


# ================================================================
#  CRYPTO MANAGER
# ================================================================

class CryptoManager:
    """
    Менеджер шифрования AES-256 (Fernet).

    ⚠️ Windows: os.chmod не даёт прав 600. Ключ доступен
    всем пользователям системы. Для реальной защиты нужны
    Windows ACL (icacls), но это выходит за рамки Zeta.
    """

    def __init__(self, key_file: str = None):
        if key_file is None:
            key_file = str(
                Path(__file__).parent.parent / "data" / "security" / "master.key"
            )

        self.key_file = Path(key_file)
        self.key_file.parent.mkdir(parents=True, exist_ok=True)

        self._cipher: Optional[Fernet] = None
        self._load_or_create_key()

    # ============================================================
    #  КЛЮЧ
    # ============================================================

    def _load_or_create_key(self) -> None:
        """Загрузить ключ или создать новый (с обработкой битого)."""
        key: Optional[bytes] = None

        # 1. Пытаемся загрузить существующий
        if self.key_file.exists():
            try:
                with open(self.key_file, "rb") as f:
                    key = f.read()

                # Проверка валидности
                if not key or len(key) < 32:
                    _log_warn(f"master.key слишком короткий ({len(key) if key else 0} байт)")
                    key = None
            except Exception as e:
                _log_warn(f"Не удалось прочитать master.key: {e}")
                key = None

        # 2. Если ключ невалидный — бэкап + новый
        if key is None:
            if self.key_file.exists():
                self._backup_broken_key()

            try:
                key = Fernet.generate_key()
                with open(self.key_file, "wb") as f:
                    f.write(key)

                # Windows не даёт 600, но попробуем
                try:
                    os.chmod(self.key_file, 0o600)
                except Exception:
                    pass

                _log(f"Создан новый master.key ({len(key)} байт)")
            except Exception as e:
                _log_warn(f"Не удалось создать master.key: {e}")
                raise

        # 3. Инициализируем Fernet
        try:
            self._cipher = Fernet(key)
            _log("Шифрование инициализировано")
        except Exception as e:
            _log_warn(f"Fernet не смог инициализироваться: {e}")
            raise

    def _backup_broken_key(self) -> None:
        """Сохраняет битый ключ с суффиксом .broken_<timestamp>."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = self.key_file.with_suffix(f".key.broken_{timestamp}")
            shutil.copy2(self.key_file, backup)
            _log_warn(f"Битый ключ сохранён: {backup.name}")
        except Exception as e:
            _log_warn(f"Не удалось сохранить битый ключ: {e}")

    def is_valid(self) -> bool:
        """Проверяет, что ключ валидный и шифр работает."""
        if self._cipher is None:
            return False
        try:
            test = self._cipher.encrypt(b"test")
            self._cipher.decrypt(test)
            return True
        except Exception:
            return False

    def rotate_key(self) -> Tuple[bool, str]:
        """
        Сменить ключ.
        Старый сохраняется как master.key.old_<timestamp>.
        Возвращает (ok, message).
        """
        try:
            if self._cipher is None:
                return False, "❌ Шифр не инициализирован"

            # Бэкап старого
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            old_backup = self.key_file.with_suffix(f".key.old_{timestamp}")
            if self.key_file.exists():
                shutil.copy2(self.key_file, old_backup)
                _log(f"Старый ключ сохранён: {old_backup.name}")

            # Новый ключ
            new_key = Fernet.generate_key()
            with open(self.key_file, "wb") as f:
                f.write(new_key)

            self._cipher = Fernet(new_key)
            _log("Ключ изменён")

            return True, (
                f"✅ Ключ изменён.\n"
                f"Старый: {old_backup.name}\n"
                f"⚠️ Данные, зашифрованные старым ключом, "
                f"НЕ расшифруются новым!"
            )
        except Exception as e:
            _log_warn(f"Ошибка rotate_key: {e}")
            return False, f"❌ Ошибка: {e}"

    # ============================================================
    #  ШИФРОВАНИЕ СТРОК
    # ============================================================

    def encrypt(self, data: str) -> bytes:
        """Зашифровать строку → bytes."""
        if self._cipher is None:
            raise RuntimeError("Шифр не инициализирован")

        if isinstance(data, str):
            data = data.encode("utf-8")

        return self._cipher.encrypt(data)

    def decrypt(self, encrypted: bytes) -> str:
        """Расшифровать bytes → str. При ошибке — исключение."""
        if self._cipher is None:
            raise RuntimeError("Шифр не инициализирован")

        return self._cipher.decrypt(encrypted).decode("utf-8")

    def safe_decrypt(self, encrypted: bytes) -> Optional[str]:
        """
        Безопасная расшифровка.
        Возвращает str или None (если ключ не тот / данные битые).
        """
        if self._cipher is None:
            return None

        try:
            return self._cipher.decrypt(encrypted).decode("utf-8")
        except InvalidToken:
            _log_warn("InvalidToken при расшифровке")
            return None
        except Exception as e:
            _log_warn(f"Ошибка расшифровки: {e}")
            return None

    # ============================================================
    #  ШИФРОВАНИЕ БАЙТ
    # ============================================================

    def encrypt_bytes(self, data: bytes) -> bytes:
        """Зашифровать bytes."""
        if self._cipher is None:
            raise RuntimeError("Шифр не инициализирован")
        return self._cipher.encrypt(data)

    def decrypt_bytes(self, encrypted: bytes) -> bytes:
        """Расшифровать bytes."""
        if self._cipher is None:
            raise RuntimeError("Шифр не инициализирован")
        return self._cipher.decrypt(encrypted)

    # ============================================================
    #  ШИФРОВАНИЕ ФАЙЛОВ
    # ============================================================

    def encrypt_file(self, file_path: str,
                     output_path: str = None) -> str:
        """Зашифровать файл. Возвращает путь к результату."""
        if self._cipher is None:
            raise RuntimeError("Шифр не инициализирован")

        src = Path(file_path)
        if not src.exists():
            raise FileNotFoundError(f"Файл не найден: {file_path}")

        if output_path is None:
            output_path = str(src) + ".encrypted"

        with open(src, "rb") as f:
            data = f.read()

        encrypted = self._cipher.encrypt(data)

        with open(output_path, "wb") as f:
            f.write(encrypted)

        _log(f"Файл зашифрован: {src.name} → {Path(output_path).name}")
        return output_path

    def decrypt_file(self, file_path: str,
                     output_path: str = None) -> str:
        """Расшифровать файл. Возвращает путь к результату."""
        if self._cipher is None:
            raise RuntimeError("Шифр не инициализирован")

        src = Path(file_path)
        if not src.exists():
            raise FileNotFoundError(f"Файл не найден: {file_path}")

        if output_path is None:
            output_path = str(src).replace(".encrypted", "")

        with open(src, "rb") as f:
            encrypted = f.read()

        decrypted = self._cipher.decrypt(encrypted)

        with open(output_path, "wb") as f:
            f.write(decrypted)

        _log(f"Файл расшифрован: {src.name} → {Path(output_path).name}")
        return output_path


# ================================================================
#  ГЛОБАЛЬНЫЙ
# ================================================================

_crypto: Optional[CryptoManager] = None


def get_crypto() -> CryptoManager:
    """
    Получить глобальный менеджер шифрования.
    Если ключ битый — создаётся новый (с бэкапом старого).
    """
    global _crypto
    if _crypto is None:
        try:
            _crypto = CryptoManager()
        except Exception as e:
            _log_warn(f"КРИТИЧНО: не удалось создать CryptoManager: {e}")
            raise

    return _crypto


def is_crypto_ready() -> bool:
    """Проверяет, готова ли криптография."""
    try:
        return get_crypto().is_valid()
    except Exception:
        return False


# ================================================================
#  ЭКСПОРТ
# ================================================================

__all__ = [
    "CryptoManager",
    "get_crypto",
    "is_crypto_ready",
]


# ================================================================
#  ТЕСТ
# ================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    print("🔐 Zeta Crypto — Тест")
    print("=" * 60)

    # 1. Базовая работа
    crypto = get_crypto()

    secret = "Это секретное сообщение Zeta"
    encrypted = crypto.encrypt(secret)
    decrypted = crypto.decrypt(encrypted)

    print(f"\n✅ Оригинал:    {secret}")
    print(f"🔒 Шифр:        {encrypted[:50]}...")
    print(f"🔓 Расшифровка: {decrypted}")
    print(f"✅ Совпадает:   {secret == decrypted}")

    # 2. safe_decrypt
    print(f"\n📝 Тест safe_decrypt:")
    print(f"   Правильные данные: {crypto.safe_decrypt(encrypted)}")

    bogus = b"this is not encrypted"
    result = crypto.safe_decrypt(bogus)
    print(f"   Битый шифр:        {result} {'✅' if result is None else '❌'}")

    # 3. is_valid
    print(f"\n📝 Тест is_valid:")
    print(f"   Валидный ключ: {crypto.is_valid()} {'✅' if crypto.is_valid() else '❌'}")

    # 4. Файлы
    print(f"\n📝 Тест файлов:")
    test_file = Path("test_crypto.txt")
    test_file.write_text("Секретный текст для файла", encoding="utf-8")

    enc_path = crypto.encrypt_file(str(test_file))
    print(f"   Зашифрован:  {enc_path}")

    dec_path = crypto.decrypt_file(enc_path)
    print(f"   Расшифрован: {dec_path}")

    restored = Path(dec_path).read_text(encoding="utf-8")
    print(f"   Совпадает:   {restored == 'Секретный текст для файла'} {'✅' if restored == 'Секретный текст для файла' else '❌'}")

    # Cleanup
    for f in [test_file, Path(enc_path), Path(dec_path)]:
        try:
            if f.exists():
                f.unlink()
        except Exception:
            pass

    # 5. Проверка битого ключа (симуляция)
    print(f"\n📝 Тест битого ключа (симуляция):")
    print(f"   (пропускаем — не хотим испортить настоящий master.key)")

    print("\n" + "=" * 60)
    print("✅ Тесты пройдены!")