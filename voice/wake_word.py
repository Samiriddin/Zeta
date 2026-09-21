# -*- coding: utf-8 -*-
"""
Zeta Voice — Wake Word.
Слушает фон, активируется по слову (модель настраивается).

⚠️ По умолчанию ВЫКЛЮЧЕН.
Включай вручную (кнопка в UI).

Особенности:
  - Потокобезопасность (Lock для буфера, Event для состояния)
  - Ограниченный буфер (deque)
  - Сброс модели при pause (не слышит себя)
  - Мгновенный stop (join)
  - Callback в отдельном потоке (опционально)
  - Логирование через zeta.wake
"""

import os
import sys
import time
import logging
import threading
from pathlib import Path
from collections import deque
from typing import Optional, Callable

sys.path.insert(0, str(Path(__file__).parent.parent))


# ========== ЛОГИРОВАНИЕ ==========

logger = logging.getLogger("zeta.wake")


def _log(msg: str) -> None:
    logger.info(msg)


def _log_warn(msg: str) -> None:
    logger.warning(msg)


# ========== OPENWAKEWORD ==========

try:
    import numpy as np
    import sounddevice as sd
    from openwakeword.model import Model
    HAS_WAKEWORD = True
except ImportError as e:
    HAS_WAKEWORD = False
    np = None
    sd = None
    Model = None
    _log_warn(f"openwakeword недоступен: {e}")
    _log_warn("Установите: pip install openwakeword onnxruntime")


# ========== КОНСТАНТЫ ==========

SAMPLE_RATE = 16000
CHUNK_SIZE = 1280  # 80 ms
DEFAULT_MODEL = "hey_jarvis"
DEFAULT_THRESHOLD = 0.5
MAX_BUFFER_CHUNKS = 50  # ~4 секунды при 80ms чанках


# ================================================================
#  WAKE WORD MANAGER
# ================================================================

class WakeWordManager:
    """Менеджер Wake Word (потокобезопасный)."""

    def __init__(self):
        self._model = None
        self._stream = None
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable] = None

        # Состояние через Event (потокобезопасно)
        self._running = threading.Event()
        self._paused = threading.Event()

        # Буфер с ограничением и блокировкой
        self._buffer: deque = deque(maxlen=MAX_BUFFER_CHUNKS)
        self._buffer_lock = threading.Lock()

        # Параметры
        self._model_name: str = DEFAULT_MODEL
        self._threshold: float = DEFAULT_THRESHOLD
        self._async_callback: bool = False

    # ============================================================
    #  МОДЕЛЬ
    # ============================================================

    def _init_model(self, model_name: str = None) -> bool:
        """Инициализировать модель (лениво)."""
        if self._model is not None:
            return True

        if not HAS_WAKEWORD:
            _log_warn("openwakeword не установлен")
            return False

        model_name = model_name or self._model_name

        try:
            _log(f"Загрузка модели: {model_name}...")
            self._model = Model(
                wakeword_models=[model_name],
                inference_framework="onnx",
            )
            self._model_name = model_name
            _log(f"Модель загружена: {model_name}")
            return True
        except Exception as e:
            _log_warn(f"Ошибка загрузки модели: {e}")
            self._model = None
            return False

    # ============================================================
    #  ЗАПУСК / ОСТАНОВКА
    # ============================================================

    def start(
        self,
        callback: Callable,
        threshold: float = DEFAULT_THRESHOLD,
        model_name: str = DEFAULT_MODEL,
        async_callback: bool = False,
    ) -> bool:
        """
        Запустить прослушивание фона.

        Args:
            callback: (name, score) — вызывается при активации
            threshold: 0.0-1.0 — порог срабатывания
            model_name: название модели openwakeword
            async_callback: True — callback в отдельном потоке
        """
        if self._running.is_set():
            _log_warn("Уже запущен")
            return True

        if not self._init_model(model_name):
            return False

        self._callback = callback
        self._threshold = threshold
        self._async_callback = async_callback

        self._running.set()
        self._paused.clear()

        # Очистка буфера
        with self._buffer_lock:
            self._buffer.clear()

        self._thread = threading.Thread(
            target=self._listen_loop,
            daemon=True,
            name="WakeWord",
        )
        self._thread.start()

        _log(f"Wake Word запущен (модель: {model_name}, threshold: {threshold})")
        return True

    def stop(self) -> None:
        """Остановить прослушивание (мгновенно)."""
        if not self._running.is_set():
            return

        self._running.clear()
        self._paused.clear()

        # Останавливаем stream
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                _log_warn(f"Ошибка закрытия stream: {e}")
            self._stream = None

        # Ждём поток
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

        # Очистка буфера
        with self._buffer_lock:
            self._buffer.clear()

        _log("Wake Word остановлен")

    def pause(self) -> None:
        """Пауза (пока Zeta говорит — не слышать себя)."""
        if not self._paused.is_set():
            self._paused.set()

            # Сброс модели (не слышит свои слова)
            if self._model is not None:
                try:
                    if hasattr(self._model, "reset"):
                        self._model.reset()
                except Exception:
                    pass

            with self._buffer_lock:
                self._buffer.clear()

            _log("Wake Word на паузе")

    def resume(self) -> None:
        """Возобновить после паузы."""
        if self._paused.is_set():
            self._paused.clear()
            _log("Wake Word возобновлён")

    def is_running(self) -> bool:
        return self._running.is_set()

    def is_paused(self) -> bool:
        return self._paused.is_set()

    # ============================================================
    #  ЦИКЛ ПРОСЛУШИВАНИЯ
    # ============================================================

    def _listen_loop(self) -> None:
        """Фоновый цикл прослушивания."""
        try:
            def audio_callback(indata, frames, time_info, status):
                if not self._running.is_set():
                    return
                if self._paused.is_set():
                    return

                try:
                    audio_data = (indata[:, 0] * 32767).astype(np.int16)
                    with self._buffer_lock:
                        self._buffer.append(audio_data)
                except Exception as e:
                    _log_warn(f"audio_callback: {e}")

            # Открываем поток
            try:
                self._stream = sd.InputStream(
                    samplerate=SAMPLE_RATE,
                    channels=1,
                    dtype="float32",
                    blocksize=CHUNK_SIZE,
                    callback=audio_callback,
                )
                self._stream.start()
            except Exception as e:
                _log_warn(f"Ошибка открытия микрофона: {e}")
                self._running.clear()
                return

            _log("Слушаю фон...")

            # Основной цикл
            while self._running.is_set():
                time.sleep(0.1)

                if self._paused.is_set():
                    continue

                # Забираем буфер
                chunk = None
                with self._buffer_lock:
                    if self._buffer:
                        try:
                            chunk = np.concatenate(list(self._buffer))
                            self._buffer.clear()
                        except Exception as e:
                            _log_warn(f"concatenate: {e}")
                            self._buffer.clear()

                if chunk is None or len(chunk) == 0:
                    continue

                # Предикт
                try:
                    prediction = self._model.predict(chunk)
                except Exception as e:
                    _log_warn(f"predict: {e}")
                    continue

                # Проверка
                for name, score in prediction.items():
                    if score > self._threshold:
                        _log(f"WAKE WORD: {name} (score: {score:.2f})")

                        # Пауза на время обработки
                        self._paused.set()

                        # Callback
                        self._fire_callback(name, score)
                        break

        except Exception as e:
            _log_warn(f"Ошибка потока: {e}")
        finally:
            self._running.clear()
            with self._buffer_lock:
                self._buffer.clear()

    def _fire_callback(self, name: str, score: float) -> None:
        """Вызвать callback (синхронно или в потоке)."""
        if not self._callback:
            return

        if self._async_callback:
            def worker():
                try:
                    self._callback(name, score)
                except Exception as e:
                    _log_warn(f"callback: {e}")

            threading.Thread(target=worker, daemon=True).start()
        else:
            try:
                self._callback(name, score)
            except Exception as e:
                _log_warn(f"callback: {e}")

    # ============================================================
    #  СТАТУС
    # ============================================================

    def status(self) -> dict:
        return {
            "available": HAS_WAKEWORD,
            "running": self._running.is_set(),
            "paused": self._paused.is_set(),
            "model": self._model_name,
            "threshold": self._threshold,
            "buffer_size": len(self._buffer),
            "max_buffer": MAX_BUFFER_CHUNKS,
        }

    def get_available_models(self) -> list:
        """Стандартные модели openwakeword."""
        return [
            "alexa",
            "hey_jarvis",
            "hey_mycroft",
            "hey_rhasspy",
        ]


# ================================================================
#  ГЛОБАЛЬНЫЙ
# ================================================================

_wake: Optional[WakeWordManager] = None


def get_wake_word() -> WakeWordManager:
    global _wake
    if _wake is None:
        _wake = WakeWordManager()
    return _wake


# ================================================================
#  ЭКСПОРТ
# ================================================================

__all__ = [
    "WakeWordManager",
    "get_wake_word",
    "HAS_WAKEWORD",
    "DEFAULT_MODEL",
    "DEFAULT_THRESHOLD",
]


# ================================================================
#  ТЕСТ
# ================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    print("🎯 Zeta Wake Word — Тест")
    print("=" * 60)

    if not HAS_WAKEWORD:
        print("\n❌ Установите: pip install openwakeword onnxruntime")
        sys.exit(1)

    ww = get_wake_word()
    print(f"\n📊 Статус до: {ww.status()}")

    print(f"\n📋 Доступные модели: {', '.join(ww.get_available_models())}")
    print(f"⚠️  Используется: {DEFAULT_MODEL}")
    print(f"   Скажи: 'Hey Jarvis'")
    print(f"   Для выхода: Ctrl+C")

    triggered_count = [0]

    def on_wake(name, score):
        triggered_count[0] += 1
        print(f"\n🎯 АКТИВАЦИЯ #{triggered_count[0]}! "
              f"{name} (score: {score:.2f})")

    if not ww.start(on_wake, threshold=0.5):
        print("❌ Не удалось запустить")
        sys.exit(1)

    print("\n🎤 Слушаю...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n🛑 Остановка...")
        ww.stop()
        print(f"✅ Остановлено. Срабатываний: {triggered_count[0]}")
        print(f"📊 Статус после: {ww.status()}")