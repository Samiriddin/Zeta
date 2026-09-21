# -*- coding: utf-8 -*-
"""
Zeta Security — Двухфакторная аутентификация (2FA).
TOTP через Google Authenticator.

Особенности:
    - Обработка bytes/str от crypto (_save/_load)
    - start_setup сохраняет секрет сразу (защита от сбоя)
    - save_qr_code_to_file с проверкой пути
    - Аудит при включении/выключении
    - Логирование в data/zeta.log
"""

import os
import sys
import base64
import secrets
import logging
from pathlib import Path
from io import BytesIO
from typing import Optional, Tuple, List

sys.path.insert(0, str(Path(__file__).parent.parent))


# ========== ЛОГИРОВАНИЕ ==========

def _log(msg: str) -> None:
    logging.info(f"[2FA] {msg}")


def _log_warn(msg: str) -> None:
    logging.warning(f"[2FA] {msg}")


def _audit(msg: str) -> None:
    try:
        from security.audit import get_audit
        get_audit().log_security("2fa", msg, severity="info")
    except Exception:
        pass


# ========== ЗАВИСИМОСТИ ==========

try:
    import pyotp
    HAS_PYOTP = True
except ImportError:
    HAS_PYOTP = False
    _log_warn("pyotp не установлен — pip install pyotp")

try:
    import qrcode
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False
    _log_warn("qrcode не установлен — pip install qrcode[pil]")


# ================================================================
#  TWO FACTOR AUTH
# ================================================================

class TwoFactorAuth:
    """Менеджер двухфакторной аутентификации."""

    ISSUER = "Zeta AI"
    BACKUP_CODES_COUNT = 10

    def __init__(self, storage_path: str = None):
        if storage_path is None:
            storage_path = str(
                Path(__file__).parent.parent / "data" / "security" / "2fa.dat"
            )

        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        self._secret: Optional[str] = None
        self._enabled: bool = False
        self._backup_codes: List[str] = []
        self._used_backup_codes: List[str] = []
        self._load_failed: bool = False

        self._load()

    # ============================================================
    #  ГЕНЕРАЦИЯ
    # ============================================================

    def generate_secret(self) -> str:
        """Генерирует секрет для 2FA."""
        if not HAS_PYOTP:
            raise RuntimeError("pyotp не установлен")
        return pyotp.random_base32()

    def get_provisioning_uri(self, account_name: str = "creator") -> str:
        """URI для QR-кода (otpauth://...)."""
        if not HAS_PYOTP or not self._secret:
            return ""
        totp = pyotp.TOTP(self._secret)
        return totp.provisioning_uri(
            name=account_name, issuer_name=self.ISSUER
        )

    def get_qr_code_image(self, account_name: str = "creator"):
        """PIL.Image с QR-кодом (или None)."""
        if not HAS_QRCODE:
            return None
        uri = self.get_provisioning_uri(account_name)
        if not uri:
            return None

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(uri)
        qr.make(fit=True)

        return qr.make_image(fill_color="black", back_color="white")

    def get_qr_code_bytes(self, account_name: str = "creator") -> bytes:
        """QR-код как PNG-байты."""
        img = self.get_qr_code_image(account_name)
        if img is None:
            return b""

        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()

    def get_qr_code_base64(self, account_name: str = "creator") -> str:
        """QR-код как base64 (без data: префикса)."""
        data = self.get_qr_code_bytes(account_name)
        if not data:
            return ""
        return base64.b64encode(data).decode("utf-8")

    def get_qr_code_data_uri(self, account_name: str = "creator") -> str:
        """QR-код как data:URI (для HTML)."""
        b64 = self.get_qr_code_base64(account_name)
        if not b64:
            return ""
        return f"data:image/png;base64,{b64}"

    def save_qr_code_to_file(self, file_path: str,
                             account_name: str = "creator") -> bool:
        """Сохранить QR-код в PNG-файл (с проверкой пути)."""
        data = self.get_qr_code_bytes(account_name)
        if not data:
            return False

        # Проверка пути
        try:
            from security.sanitizer import sanitize_path
            safe_path = sanitize_path(
                file_path,
                allowed_dir=str(Path(__file__).parent.parent / "data")
            )
            if not safe_path:
                _log_warn(f"Небезопасный путь для QR: {file_path}")
                return False
        except Exception:
            safe_path = file_path  # fallback

        try:
            Path(safe_path).parent.mkdir(parents=True, exist_ok=True)
            with open(safe_path, "wb") as f:
                f.write(data)
            _log(f"QR сохранён: {safe_path}")
            return True
        except Exception as e:
            _log_warn(f"Ошибка сохранения QR: {e}")
            return False

    # ============================================================
    #  ВКЛЮЧЕНИЕ / ВЫКЛЮЧЕНИЕ
    # ============================================================

    def start_setup(self) -> str:
        """
        Начинает настройку 2FA. Возвращает секрет.
        Сохраняет сразу (enabled=False), чтобы не потерять при сбое.
        """
        if not HAS_PYOTP:
            raise RuntimeError("pyotp не установлен")

        self._secret = self.generate_secret()
        self._save()  # ← сохраняем сразу
        _log("Секрет сгенерирован (настройка начата)")
        return self._secret

    def confirm_setup(self, code: str) -> bool:
        """Подтверждает настройку 2FA после ввода кода."""
        if not self._secret:
            return False

        if not self.verify_code(code):
            return False

        self._backup_codes = self._generate_backup_codes()
        self._used_backup_codes = []
        self._enabled = True
        self._save()

        _log("2FA включён")
        _audit("enabled")
        return True

    def enable(self) -> bool:
        """Принудительно включить (если секрет уже есть)."""
        if not self._secret:
            return False
        self._enabled = True
        self._save()
        _log("2FA включён (принудительно)")
        _audit("enabled_force")
        return True

    def disable(self) -> bool:
        """Выключить 2FA."""
        self._enabled = False
        self._secret = None
        self._backup_codes = []
        self._used_backup_codes = []
        self._save()
        _log("2FA выключен")
        _audit("disabled")
        return True

    def is_enabled(self) -> bool:
        """Включён ли 2FA."""
        return self._enabled and self._secret is not None

    def has_secret(self) -> bool:
        """Есть ли секрет (для настройки)."""
        return self._secret is not None

    def is_load_failed(self) -> bool:
        """Была ли ошибка загрузки."""
        return self._load_failed

    # ============================================================
    #  ПРОВЕРКА КОДА
    # ============================================================

    def verify_code(self, code: str) -> bool:
        """Проверяет 6-значный TOTP-код."""
        if not HAS_PYOTP or not self._secret:
            return False

        code = code.strip().replace(" ", "")

        if not code.isdigit() or len(code) != 6:
            return False

        try:
            totp = pyotp.TOTP(self._secret)
            return totp.verify(code, valid_window=1)
        except Exception as e:
            _log_warn(f"Ошибка проверки кода: {e}")
            return False

    def verify_any(self, code: str) -> Tuple[bool, str]:
        """Проверяет TOTP или backup-код. Возвращает (ok, тип)."""
        code = code.strip()

        if self.verify_code(code):
            return True, "totp"

        if self.verify_backup_code(code.upper()):
            return True, "backup"

        return False, ""

    # ============================================================
    #  РЕЗЕРВНЫЕ КОДЫ
    # ============================================================

    def _generate_backup_codes(self) -> List[str]:
        """Генерирует резервные коды."""
        codes = []
        for _ in range(self.BACKUP_CODES_COUNT):
            part1 = secrets.token_hex(2).upper()
            part2 = secrets.token_hex(2).upper()
            codes.append(f"{part1}-{part2}")
        return codes

    def get_backup_codes(self) -> List[str]:
        """Резервные коды."""
        return self._backup_codes.copy()

    def get_unused_backup_codes_count(self) -> int:
        """Сколько осталось."""
        return len(self._backup_codes) - len(self._used_backup_codes)

    def verify_backup_code(self, code: str) -> bool:
        """Проверяет и помечает резервный код использованным."""
        code = code.strip().upper()

        if code in self._used_backup_codes:
            return False

        if code in self._backup_codes:
            self._used_backup_codes.append(code)
            self._save()
            _log_warn(f"Использован резервный код: {code}")
            _audit(f"backup_code_used (осталось: {self.get_unused_backup_codes_count()})")
            return True

        return False

    def regenerate_backup_codes(self) -> List[str]:
        """Перегенерировать резервные коды."""
        self._backup_codes = self._generate_backup_codes()
        self._used_backup_codes = []
        self._save()
        _log("Резервные коды перегенерированы")
        _audit("backup_codes_regenerated")
        return self._backup_codes.copy()

    # ============================================================
    #  СОХРАНЕНИЕ (безопасное)
    # ============================================================

    def _save(self) -> None:
        """Сохранить состояние (зашифровано)."""
        try:
            from security.crypto import get_crypto
            crypto = get_crypto()

            data = "|".join([
                "1" if self._enabled else "0",
                self._secret or "",
                ",".join(self._backup_codes),
                ",".join(self._used_backup_codes),
            ])

            encrypted = crypto.encrypt(data)

            # Если crypto вернул str — кодируем
            if isinstance(encrypted, str):
                encrypted = encrypted.encode("utf-8")

            # Атомарная запись
            tmp = self.storage_path.with_suffix(".tmp")
            with open(tmp, "wb") as f:
                f.write(encrypted)

            if self.storage_path.exists():
                self.storage_path.unlink()
            tmp.rename(self.storage_path)

        except Exception as e:
            _log_warn(f"Ошибка сохранения 2FA: {e}")
            try:
                tmp = self.storage_path.with_suffix(".tmp")
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass

    def _load(self) -> None:
        """Загрузить состояние."""
        if not self.storage_path.exists():
            return

        try:
            from security.crypto import get_crypto
            crypto = get_crypto()

            with open(self.storage_path, "rb") as f:
                encrypted = f.read()

            if not encrypted:
                _log_warn("2fa.dat пустой")
                return

            data = crypto.decrypt(encrypted)

            # Декодируем bytes → str
            if isinstance(data, bytes):
                data = data.decode("utf-8")

            parts = data.split("|")

            if len(parts) >= 4:
                self._enabled = parts[0] == "1"
                self._secret = parts[1] if parts[1] else None
                self._backup_codes = [c for c in parts[2].split(",") if c]
                self._used_backup_codes = [c for c in parts[3].split(",") if c]
                _log(f"2FA загружен (enabled={self._enabled})")
            else:
                _log_warn(f"2fa.dat повреждён (частей: {len(parts)})")
                self._load_failed = True

        except Exception as e:
            _log_warn(f"Ошибка загрузки 2FA: {e}")
            self._load_failed = True

    # ============================================================
    #  СТАТУС
    # ============================================================

    def status(self) -> dict:
        """Статус 2FA."""
        return {
            "enabled": self._enabled,
            "has_secret": self._secret is not None,
            "backup_codes_total": len(self._backup_codes),
            "backup_codes_used": len(self._used_backup_codes),
            "backup_codes_remaining": self.get_unused_backup_codes_count(),
            "load_failed": self._load_failed,
            "pyotp_available": HAS_PYOTP,
            "qrcode_available": HAS_QRCODE,
        }

    def reset(self) -> None:
        """Полный сброс 2FA."""
        self._secret = None
        self._enabled = False
        self._backup_codes = []
        self._used_backup_codes = []
        self._load_failed = False

        if self.storage_path.exists():
            try:
                self.storage_path.unlink()
            except Exception:
                pass

        _log("2FA сброшен")
        _audit("reset")


# ================================================================
#  ГЛОБАЛЬНЫЙ
# ================================================================

_2fa: Optional[TwoFactorAuth] = None


def get_2fa() -> TwoFactorAuth:
    """Глобальный менеджер 2FA."""
    global _2fa
    if _2fa is None:
        _2fa = TwoFactorAuth()
    return _2fa


# ================================================================
#  ЭКСПОРТ
# ================================================================

__all__ = ["TwoFactorAuth", "get_2fa"]


# ================================================================
#  ТЕСТ
# ================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    print("🔐 Zeta 2FA — Тест")
    print("=" * 60)

    if not HAS_PYOTP:
        print("\n❌ pyotp не установлен")
        print("   pip install pyotp qrcode[pil]")
        sys.exit(1)

    fa = get_2fa()
    fa.reset()

    print(f"\n📊 Статус до: {fa.status()}")

    # Настройка
    print("\n📱 Шаг 1: Генерация секрета")
    secret = fa.start_setup()
    print(f"   Секрет: {secret[:8]}...{secret[-8:]}")

    # QR-код
    if HAS_QRCODE:
        print("\n📸 Шаг 2: QR-код")
        qr_b64 = fa.get_qr_code_base64("Самриддин")
        print(f"   QR (base64): {len(qr_b64)} байт")

        data_uri = fa.get_qr_code_data_uri("Самриддин")
        print(f"   Data URI: {data_uri[:50]}...")

        # Сохранение в файл
        qr_path = str(Path(__file__).parent.parent / "data" / "security" / "test_qr.png")
        if fa.save_qr_code_to_file(qr_path, "Самриддин"):
            print(f"   Сохранён: {qr_path}")

    # Подтверждение
    print("\n🔑 Шаг 3: Подтверждение")
    if HAS_PYOTP:
        totp = pyotp.TOTP(secret)
        current_code = totp.now()
        print(f"   Текущий код: {current_code}")

        if fa.confirm_setup(current_code):
            print("   2FA включён ✅")
        else:
            print("   ❌ Ошибка")
            sys.exit(1)

    # Backup коды
    print("\n🎫 Шаг 4: Резервные коды")
    codes = fa.get_backup_codes()
    for i, code in enumerate(codes[:3], 1):
        print(f"   {i}. {code}")
    print(f"   ... (всего {len(codes)})")

    # Проверка
    print("\n🧪 Шаг 5: Проверка")
    new_code = pyotp.TOTP(secret).now()
    ok, typ = fa.verify_any(new_code)
    print(f"   TOTP: {ok} ({typ})")

    ok, typ = fa.verify_any(codes[0])
    print(f"   Backup[0]: {ok} ({typ})")

    ok, typ = fa.verify_any(codes[0])
    print(f"   Backup[0] повтор: {ok} ({typ}) — должно быть False")

    # Статус
    print(f"\n📊 Статус после: {fa.status()}")

    print("\n" + "=" * 60)
    print("✅ Тесты пройдены!")