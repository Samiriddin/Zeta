# -*- coding: utf-8 -*-
"""
Zeta Voice — Синтез речи (TTS).
Два движка:
  1. edge-tts (онлайн, лучшие голоса)
  2. pyttsx3 (офлайн, работает без интернета)
Автоматический fallback.

Особенности:
  - Кэш проверки интернета (сброс при сетевой ошибке)
  - Уникальные mp3 (uuid)
  - Правильная очистка mp3
  - Потокобезопасность через lock
  - Готовый asyncio loop
  - speak_async — обёртка для потоков
  - cleanup_temp — авто-вызов
"""

import os
import re
import sys
import time
import uuid
import asyncio
import logging
import threading
from pathlib import Path
from typing import Optional, Callable

sys.path.insert(0, str(Path(__file__).parent.parent))


# ========== ЛОГИРОВАНИЕ ==========

logger = logging.getLogger("zeta.tts")


def _log(msg: str) -> None:
    logger.info(msg)


def _log_warn(msg: str) -> None:
    logger.warning(msg)


# ========== ЗАВИСИМОСТИ ==========

try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False
    _log_warn("edge-tts не установлен — pip install edge-tts")

try:
    import pyttsx3
    HAS_PYTTSX3 = True
except ImportError:
    HAS_PYTTSX3 = False
    _log_warn("pyttsx3 не установлен — pip install pyttsx3")

try:
    import pygame
    HAS_PYGAME = True
except ImportError:
    HAS_PYGAME = False

try:
    from playsound import playsound
    HAS_PLAYSOUND = True
except ImportError:
    HAS_PLAYSOUND = False


# ========== КОНСТАНТЫ ==========

TEMP_DIR = Path(__file__).parent.parent / "data" / "tts_temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

EDGE_VOICES = {
    "Светлана (русский, женский)": "ru-RU-SvetlanaNeural",
    "Дарья (русский, женский)": "ru-RU-DariyaNeural",
    "Дмитрий (русский, мужской)": "ru-RU-DmitryNeural",
    "Полина (украинский, женский)": "uk-UA-PolinaNeural",
    "Ария (английский, женский)": "en-US-AriaNeural",
    "Гай (английский, мужской)": "en-US-GuyNeural",
}

DEFAULT_VOICE = "ru-RU-SvetlanaNeural"

INTERNET_CACHE_TTL = 60       # секунд
CLEANUP_EVERY_N = 100         # cleanup_temp раз в N вызовов speak


# ================================================================
#  TTS MANAGER
# ================================================================

class TTSManager:
    """Менеджер синтеза речи с fallback."""

    def __init__(self):
        self._engine = None
        self._pygame_ready = False
        self._current_engine: Optional[str] = None

        # Кэш интернета
        self._internet_ok: Optional[bool] = None
        self._internet_checked: float = 0

        # Потокобезопасность
        self._lock = threading.Lock()

        # asyncio loop
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_lock = threading.Lock()

        # Счётчик вызовов speak (для cleanup)
        self._speak_count = 0

        self._init_pygame()
        self._init_pyttsx3()

    # ============================================================
    #  ИНИЦИАЛИЗАЦИЯ
    # ============================================================

    def _init_pygame(self):
        """Инициализировать pygame mixer."""
        if not HAS_PYGAME:
            return
        try:
            pygame.mixer.init()
            self._pygame_ready = True
            _log("pygame mixer готов")
        except Exception as e:
            _log_warn(f"pygame: {e}")
            self._pygame_ready = False

    def _init_pyttsx3(self):
        """Инициализировать pyttsx3."""
        if not HAS_PYTTSX3:
            return
        try:
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", 180)
            self._engine.setProperty("volume", 1.0)
            _log("pyttsx3 готов")
        except Exception as e:
            _log_warn(f"pyttsx3: {e}")
            self._engine = None

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Готовый asyncio loop (создаём один раз)."""
        with self._loop_lock:
            if self._loop is None or self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
            return self._loop

    def close(self) -> None:
        """Закрыть loop (вызывать при выходе Zeta)."""
        with self._loop_lock:
            if self._loop and not self._loop.is_closed():
                try:
                    self._loop.close()
                except Exception:
                    pass
                self._loop = None

    # ============================================================
    #  ИНТЕРНЕТ (кэш)
    # ============================================================

    def _check_internet(self, force: bool = False) -> bool:
        """Проверка интернета с кэшем."""
        if not HAS_EDGE_TTS:
            return False

        now = time.time()

        if not force and self._internet_ok is not None:
            if now - self._internet_checked < INTERNET_CACHE_TTL:
                return self._internet_ok

        try:
            import socket
            socket.create_connection(
                ("speech.platform.bing.com", 443),
                timeout=2,
            )
            self._internet_ok = True
        except Exception:
            self._internet_ok = False

        self._internet_checked = now
        return self._internet_ok

    def _reset_internet_cache(self) -> None:
        """Сбросить кэш — следующий вызов проверит заново."""
        self._internet_ok = None
        self._internet_checked = 0

    # ============================================================
    #  EDGE-TTS
    # ============================================================

    async def _edge_speak_async(
        self,
        text: str,
        voice: str,
        rate: str = "+0%",
        output_file: str = None,
    ) -> Optional[str]:
        """Асинхронный синтез edge-tts."""
        try:
            if output_file is None:
                output_file = str(TEMP_DIR / f"zeta_{uuid.uuid4().hex[:8]}.mp3")

            communicate = edge_tts.Communicate(
                text=text,
                voice=voice,
                rate=rate,
                volume="+0%",
            )

            await communicate.save(output_file)

            if os.path.exists(output_file) and os.path.getsize(output_file) > 1000:
                return output_file

            _log_warn(f"edge-tts: пустой или маленький mp3 "
                      f"({os.path.getsize(output_file) if os.path.exists(output_file) else 0} байт)")
            return None
        except Exception as e:
            _log_warn(f"edge-tts: {e}")
            return None

    def _edge_speak(
        self,
        text: str,
        voice: str = DEFAULT_VOICE,
        rate: str = "+0%",
    ) -> Optional[str]:
        """Синхронная обёртка edge-tts."""
        if not HAS_EDGE_TTS:
            return None

        try:
            output_file = str(TEMP_DIR / f"zeta_{uuid.uuid4().hex[:8]}.mp3")
            loop = self._get_loop()
            return loop.run_until_complete(
                self._edge_speak_async(text, voice, rate, output_file)
            )
        except Exception as e:
            _log_warn(f"edge-tts wrapper: {e}")
            return None

    # ============================================================
    #  PYTTSX3 (офлайн)
    # ============================================================

    def _pyttsx3_speak(self, text: str, rate: int = 180) -> bool:
        """Озвучка через pyttsx3."""
        if not self._engine:
            return False

        try:
            self._engine.setProperty("rate", rate)
            self._engine.say(text)
            self._engine.runAndWait()
            return True
        except RuntimeError as e:
            # pyttsx3 падает при повторном запуске — пересоздаём
            _log_warn(f"pyttsx3 перезапуск: {e}")
            try:
                self._engine = pyttsx3.init()
                self._engine.setProperty("rate", rate)
                self._engine.say(text)
                self._engine.runAndWait()
                return True
            except Exception as e2:
                _log_warn(f"pyttsx3 fail: {e2}")
                return False
        except Exception as e:
            _log_warn(f"pyttsx3: {e}")
            return False

    # ============================================================
    #  ВОСПРОИЗВЕДЕНИЕ
    # ============================================================

    def _play_mp3(self, file_path: str) -> bool:
        """Воспроизвести mp3 и удалить файл."""
        if not os.path.exists(file_path):
            return False

        # Проверка размера
        try:
            if os.path.getsize(file_path) < 500:
                _log_warn(f"mp3 слишком маленький: {file_path}")
                try:
                    os.remove(file_path)
                except Exception:
                    pass
                return False
        except Exception:
            pass

        played = False

        # Pygame
        if self._pygame_ready:
            try:
                pygame.mixer.music.load(file_path)
                pygame.mixer.music.play()

                start = time.time()
                while pygame.mixer.music.get_busy():
                    if time.time() - start > 300:
                        pygame.mixer.music.stop()
                        break
                    pygame.time.Clock().tick(20)

                pygame.mixer.music.unload()
                played = True
            except Exception as e:
                _log_warn(f"pygame play: {e}")

        # Fallback: playsound
        if not played and HAS_PLAYSOUND:
            try:
                playsound(file_path)
                played = True
            except Exception as e:
                _log_warn(f"playsound: {e}")

        # Удаляем
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass

        return played

    # ============================================================
    #  ГЛАВНЫЙ МЕТОД
    # ============================================================

    def speak(
        self,
        text: str,
        voice: str = DEFAULT_VOICE,
        speed: float = 1.0,
    ) -> bool:
        """
        Озвучить текст (БЛОКИРУЮЩИЙ — вызывай из отдельного потока).

        Автоматически выбирает движок:
          1. edge-tts (если интернет)
          2. pyttsx3 (fallback)
        """
        if not text or not text.strip():
            return False

        # Очистка
        cleaned = self._clean_text(text)
        if not cleaned:
            # Fallback: озвучиваем оригинал (первые 500 символов)
            cleaned = re.sub(r"\s+", " ", text).strip()[:500]
            if not cleaned:
                return False

        rate_str = self._format_rate(speed)

        # Lock: только одна озвучка за раз
        with self._lock:
            self._speak_count += 1

            # Периодический cleanup
            if self._speak_count % CLEANUP_EVERY_N == 0:
                self.cleanup_temp()

            _log(f"Озвучка: {cleaned[:50]}...")

            # === 1. EDGE-TTS ===
            if HAS_EDGE_TTS and self._check_internet():
                audio_file = self._edge_speak(cleaned, voice, rate_str)
                if audio_file:
                    self._current_engine = "edge"
                    if self._play_mp3(audio_file):
                        return True
                    # Воспроизведение упало — пробуем pyttsx3
                    _log_warn("edge-tts: воспроизведение упало, fallback")

            # === 2. FALLBACK: PYTTSX3 ===
            if self._engine:
                self._current_engine = "pyttsx3"
                pyttsx3_rate = int(180 * speed)
                return self._pyttsx3_speak(cleaned, pyttsx3_rate)

            _log_warn("Нет доступных TTS движков")
            return False

    def speak_async(
        self,
        text: str,
        voice: str = DEFAULT_VOICE,
        speed: float = 1.0,
        callback: Optional[Callable[[bool], None]] = None,
    ) -> threading.Thread:
        """
        Озвучить текст в отдельном потоке.

        Returns:
            threading.Thread — можно join() если нужно.
        """
        def worker():
            try:
                ok = self.speak(text, voice=voice, speed=speed)
                if callback:
                    callback(ok)
            except Exception as e:
                _log_warn(f"speak_async: {e}")
                if callback:
                    callback(False)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return thread

    # ============================================================
    #  УТИЛИТЫ
    # ============================================================

    def _clean_text(self, text: str) -> str:
        """Очистить текст от markdown и эмодзи."""
        if not text:
            return ""

        # Markdown
        text = re.sub(r"```[\s\S]*?```", "", text)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"\*([^*]+)\*", r"\1", text)
        text = re.sub(r"#+\s*", "", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)

        # Эмодзи
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"
            "\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF"
            "\U0001F700-\U0001F77F"
            "\U0001F780-\U0001F7FF"
            "\U0001F800-\U0001F8FF"
            "\U0001F900-\U0001F9FF"
            "\U0001FA00-\U0001FA6F"
            "\U0001FA70-\U0001FAFF"
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "]+",
            flags=re.UNICODE,
        )
        text = emoji_pattern.sub("", text)

        # Пробелы
        text = re.sub(r"\s+", " ", text).strip()

        # Ограничение
        if len(text) > 5000:
            text = text[:5000] + "..."

        return text

    def _format_rate(self, speed: float) -> str:
        """Форматировать скорость для edge-tts."""
        if speed == 1.0:
            return "+0%"

        rate_percent = int((speed - 1.0) * 100)
        rate_percent = max(-50, min(100, rate_percent))

        if rate_percent >= 0:
            return f"+{rate_percent}%"
        return f"{rate_percent}%"

    # ============================================================
    #  ИНФО
    # ============================================================

    def get_available_voices(self) -> dict:
        return EDGE_VOICES.copy()

    def get_current_engine(self) -> str:
        return self._current_engine or "unknown"

    def has_edge_tts(self) -> bool:
        return HAS_EDGE_TTS

    def has_pyttsx3(self) -> bool:
        return HAS_PYTTSX3 and self._engine is not None

    def status(self) -> dict:
        return {
            "edge_tts": HAS_EDGE_TTS,
            "pyttsx3": self.has_pyttsx3(),
            "pygame": self._pygame_ready,
            "current_engine": self._current_engine,
            "internet": self._internet_ok,
            "speak_count": self._speak_count,
        }

    def stop(self) -> None:
        """Остановить воспроизведение."""
        if self._pygame_ready:
            try:
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
            except Exception:
                pass

    def cleanup_temp(self) -> int:
        """Удалить старые mp3 (старше 1 часа)."""
        removed = 0
        cutoff = time.time() - 3600

        try:
            for f in TEMP_DIR.glob("zeta_*.mp3"):
                try:
                    if f.stat().st_mtime < cutoff:
                        f.unlink()
                        removed += 1
                except Exception:
                    continue
        except Exception:
            pass

        if removed:
            _log(f"Очищено старых mp3: {removed}")
        return removed


# ================================================================
#  ГЛОБАЛЬНЫЙ
# ================================================================

_tts: Optional[TTSManager] = None


def get_tts() -> TTSManager:
    global _tts
    if _tts is None:
        _tts = TTSManager()
    return _tts


def speak(text: str, voice: str = DEFAULT_VOICE, speed: float = 1.0) -> bool:
    """Быстрая озвучка (БЛОКИРУЮЩАЯ — используй speak_async для UI)."""
    return get_tts().speak(text, voice=voice, speed=speed)


def speak_async(
    text: str,
    voice: str = DEFAULT_VOICE,
    speed: float = 1.0,
    callback: Optional[Callable[[bool], None]] = None,
) -> threading.Thread:
    """Озвучка в отдельном потоке (НЕ блокирует UI)."""
    return get_tts().speak_async(text, voice=voice, speed=speed, callback=callback)


# ================================================================
#  ЭКСПОРТ
# ================================================================

__all__ = [
    "TTSManager",
    "get_tts",
    "speak",
    "speak_async",
    "EDGE_VOICES",
    "DEFAULT_VOICE",
    "HAS_EDGE_TTS",
    "HAS_PYTTSX3",
]


# ================================================================
#  ТЕСТ
# ================================================================

if __name__ == "__main__":
    # Для прямого запуска — свой логгер
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    print("🎤 Zeta TTS — Тест")
    print("=" * 60)

    tts = get_tts()

    print("\n📊 Статус:")
    for k, v in tts.status().items():
        print(f"   {k}: {v}")

    print("\n🔧 Движки:")
    print(f"   edge-tts (онлайн): {'✅' if HAS_EDGE_TTS else '❌'}")
    print(f"   pyttsx3 (офлайн):  {'✅' if tts.has_pyttsx3() else '❌'}")
    print(f"   pygame:            {'✅' if tts._pygame_ready else '❌'}")

    # Тест 1: короткая фраза
    print("\n🔊 Тест 1: короткая фраза")
    ok = tts.speak("Привет! Я Zeta.")
    print(f"   Результат: {'✅' if ok else '❌'}")
    print(f"   Движок: {tts.get_current_engine()}")

    # Тест 2: повторная
    print("\n🔊 Тест 2: повторная")
    ok = tts.speak("Вторая фраза для проверки.")
    print(f"   Результат: {'✅' if ok else '❌'}")

    # Тест 3: очистка
    print("\n🧹 Тест 3: очистка текста")
    dirty = "**Жирный** и *курсив* с `кодом` и эмодзи 😀🎉"
    clean = tts._clean_text(dirty)
    print(f"   До:    {dirty}")
    print(f"   После: {clean}")

    # Тест 4: speak_async
    print("\n🔊 Тест 4: speak_async (не блокирует)")
    done = threading.Event()

    def cb(ok):
        print(f"   Async callback: {'✅' if ok else '❌'}")
        done.set()

    tts.speak_async("Асинхронная фраза.", callback=cb)
    print("   (ждём завершения в фоне)")
    done.wait(timeout=30)

    # Очистка
    removed = tts.cleanup_temp()
    print(f"\n🧹 Очищено mp3: {removed}")

    # Закрываем loop
    tts.close()

    print("\n" + "=" * 60)
    print("✅ Тесты завершены!")
    print(f"📊 Итоговый движок: {tts.get_current_engine()}")