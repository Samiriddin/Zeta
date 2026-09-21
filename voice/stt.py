# -*- coding: utf-8 -*-
"""
Zeta Voice — Распознавание речи (STT).
Использует sounddevice вместо PyAudio.

Возможности:
  - Ручная запись (start_recording / stop_recording / cancel_recording)
  - Запись до тишины (record_until_silence)
  - Запись с фиксированным временем (record)
  - Уникальные WAV-файлы (без перезаписи)
  - Auto-stop если нет речи (5 сек)
  - Cleanup WAV после распознавания
  - Список микрофонов с дефолтным
"""

import os
import sys
import time
import uuid
import wave
import logging
import tempfile
from pathlib import Path
from typing import Optional, Callable, List, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))


# ========== ЛОГИРОВАНИЕ ==========

def _log(msg: str) -> None:
    logging.info(f"[STT] {msg}")


def _log_warn(msg: str) -> None:
    logging.warning(f"[STT] {msg}")


# ========== ЗАВИСИМОСТИ ==========

try:
    import sounddevice as sd
    import numpy as np
    HAS_SOUND = True
except ImportError:
    HAS_SOUND = False
    sd = None
    np = None
    _log_warn("Установите: pip install sounddevice numpy")

try:
    import soundfile as sf
    HAS_SF = True
except ImportError:
    HAS_SF = False

try:
    import speech_recognition as sr
    HAS_SR = True
except ImportError:
    HAS_SR = False
    sr = None
    _log_warn("Установите: pip install SpeechRecognition")


# ========== КОНСТАНТЫ ==========

SAMPLE_RATE = 16000
CHANNELS = 1
DURATION = 5
LANGUAGE = "ru-RU"

# Директория для временных WAV
TEMP_DIR = Path(__file__).parent.parent / "data" / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Минимальная длина записи (сек)
MIN_RECORDING_SEC = 0.5

# Auto-stop при отсутствии речи (сек)
NO_SPEECH_TIMEOUT = 5.0

# Таймаут для Google-распознавания
RECOGNIZE_TIMEOUT = 10


# ================================================================
#  STT MANAGER
# ================================================================

class STTManager:
    """Менеджер распознавания речи."""

    def __init__(self):
        self.recognizer = sr.Recognizer() if HAS_SR else None
        self.sample_rate = SAMPLE_RATE
        self.duration = DURATION

        # Для ручной записи
        self._recording = False
        self._stream = None
        self._audio_frames = []

        # Уникальный суффикс для этого запуска
        self._session_id = uuid.uuid4().hex[:8]

    # ============================================================
    #  УТИЛИТЫ
    # ============================================================

    def _new_wav_path(self) -> Path:
        """Создаёт уникальный путь для WAV."""
        timestamp = int(time.time() * 1000)
        name = f"zeta_stt_{self._session_id}_{timestamp}.wav"
        return TEMP_DIR / name

    @staticmethod
    def _save_wav(audio_data, sample_rate: int, path: Path) -> bool:
        """Сохраняет numpy-массив в WAV."""
        try:
            with wave.open(str(path), "wb") as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(sample_rate)
                wf.writeframes(audio_data.tobytes())
            return True
        except Exception as e:
            _log_warn(f"Ошибка сохранения WAV: {e}")
            return False

    @staticmethod
    def _delete_file(path: str) -> None:
        """Удаляет файл молча."""
        try:
            p = Path(path)
            if p.exists():
                p.unlink()
        except Exception:
            pass

    # ============================================================
    #  ЗАПИСЬ (ФИКСИРОВАННОЕ ВРЕМЯ)
    # ============================================================

    def record(self, duration: int = None) -> Optional[str]:
        """Записать с микрофона в WAV (фиксированное время)."""
        if not HAS_SOUND:
            _log_warn("sounddevice не установлен")
            return None

        duration = duration or self.duration

        try:
            _log(f"Запись {duration} сек...")

            audio_data = sd.rec(
                int(duration * self.sample_rate),
                samplerate=self.sample_rate,
                channels=CHANNELS,
                dtype="int16",
            )
            sd.wait()

            wav_path = self._new_wav_path()
            if not self._save_wav(audio_data, self.sample_rate, wav_path):
                return None

            _log(f"Записано: {wav_path.name}")
            return str(wav_path)

        except Exception as e:
            _log_warn(f"Ошибка записи: {e}")
            return None

    # ============================================================
    #  РУЧНАЯ ЗАПИСЬ (START / STOP)
    # ============================================================

    def start_recording(self) -> bool:
        """Начать запись в фоне."""
        if not HAS_SOUND:
            _log_warn("sounddevice не установлен")
            return False

        if self._recording:
            _log_warn("Запись уже идёт")
            return True

        try:
            self._recording = True
            self._audio_frames = []

            def callback(indata, frames, time_info, status):
                if self._recording:
                    self._audio_frames.append(indata.copy())

            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=CHANNELS,
                dtype="int16",
                callback=callback,
            )
            self._stream.start()
            _log("Запись начата (ручная)")
            return True

        except Exception as e:
            _log_warn(f"Ошибка старта: {e}")
            self._recording = False
            self._stream = None
            return False

    def stop_recording(self) -> Optional[str]:
        """Остановить запись и сохранить в WAV."""
        if not self._recording:
            _log_warn("Запись не идёт")
            return None

        self._recording = False

        try:
            if self._stream:
                self._stream.stop()
                self._stream.close()
                self._stream = None

            if not self._audio_frames:
                _log_warn("Нет записанных данных")
                return None

            audio_data = np.concatenate(self._audio_frames, axis=0)
            self._audio_frames = []

            # Минимальная длина
            min_samples = int(self.sample_rate * MIN_RECORDING_SEC)
            if len(audio_data) < min_samples:
                _log_warn(f"Слишком короткая запись: {len(audio_data)} сэмплов")
                return None

            wav_path = self._new_wav_path()
            if not self._save_wav(audio_data, self.sample_rate, wav_path):
                return None

            _log(f"Запись остановлена: {wav_path.name} "
                 f"({len(audio_data)} сэмплов)")
            return str(wav_path)

        except Exception as e:
            _log_warn(f"Ошибка стопа: {e}")
            return None

    def cancel_recording(self) -> None:
        """Отменить запись без сохранения."""
        if not self._recording:
            return

        self._recording = False
        try:
            if self._stream:
                self._stream.stop()
                self._stream.close()
                self._stream = None
            self._audio_frames = []
            _log("Запись отменена")
        except Exception as e:
            _log_warn(f"Ошибка отмены: {e}")

    def is_recording(self) -> bool:
        return self._recording

    # ============================================================
    #  ЗАПИСЬ ДО ТИШИНЫ
    # ============================================================

    def record_until_silence(
        self,
        max_duration: int = 30,
        silence_duration: float = 3.0,
        silence_threshold: float = 500,
        no_speech_timeout: float = NO_SPEECH_TIMEOUT,
        callback: Optional[Callable[[float], None]] = None,
    ) -> Optional[str]:
        """
        Записать с микрофона до наступления тишины.

        Args:
            max_duration: Максимум секунд записи
            silence_duration: Тишина для стопа (сек)
            silence_threshold: Порог тишины (0-32767)
            no_speech_timeout: Если речи нет N секунд — выходим
            callback: Функция для индикации уровня (volume)

        Returns:
            Путь к WAV или None
        """
        if not HAS_SOUND:
            _log_warn("sounddevice не установлен")
            return None

        try:
            _log(f"Запись до тишины "
                 f"(макс {max_duration}с, тишина {silence_duration}с)")

            self._recording = True
            self._audio_frames = []
            stream = None

            def audio_callback(indata, frames, time_info, status):
                if self._recording:
                    self._audio_frames.append(indata.copy())
                    if callback:
                        try:
                            volume = float(np.abs(indata).mean())
                            callback(volume)
                        except Exception:
                            pass

            stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=CHANNELS,
                dtype="int16",
                callback=audio_callback,
            )
            stream.start()

            start_time = time.time()
            silence_start: Optional[float] = None
            speech_detected = False
            no_speech_start = start_time

            while self._recording:
                time.sleep(0.1)

                # Максимальное время
                if time.time() - start_time > max_duration:
                    _log("Максимум времени достигнут")
                    break

                # Проверка уровня
                if self._audio_frames:
                    last_frame = self._audio_frames[-1]
                    volume = float(np.abs(last_frame).mean())

                    if volume > silence_threshold:
                        speech_detected = True
                        silence_start = None
                    elif speech_detected:
                        if silence_start is None:
                            silence_start = time.time()
                        elif time.time() - silence_start > silence_duration:
                            _log(f"Тишина {silence_duration}с — стоп")
                            break

                # Auto-stop: речи нет N секунд
                if not speech_detected and (time.time() - no_speech_start > no_speech_timeout):
                    _log(f"Речь не обнаружена за {no_speech_timeout}с — стоп")
                    self._recording = False
                    stream.stop()
                    stream.close()
                    self._audio_frames = []
                    return None

            # Останавливаем
            self._recording = False
            stream.stop()
            stream.close()

            if not self._audio_frames:
                _log_warn("Нет записанных данных")
                return None

            audio_data = np.concatenate(self._audio_frames, axis=0)
            self._audio_frames = []

            # Минимальная длина
            min_samples = int(self.sample_rate * MIN_RECORDING_SEC)
            if len(audio_data) < min_samples:
                _log_warn("Слишком короткая запись")
                return None

            wav_path = self._new_wav_path()
            if not self._save_wav(audio_data, self.sample_rate, wav_path):
                return None

            duration_sec = len(audio_data) / self.sample_rate
            _log(f"Записано до тишины: {duration_sec:.1f}с")
            return str(wav_path)

        except Exception as e:
            self._recording = False
            _log_warn(f"Ошибка записи до тишины: {e}")
            return None

    # ============================================================
    #  РАСПОЗНАВАНИЕ
    # ============================================================

    def recognize_file(
        self,
        wav_path: str,
        language: str = LANGUAGE,
        delete_after: bool = True,
    ) -> Optional[str]:
        """
        Распознать WAV-файл.

        Args:
            wav_path: путь к WAV
            language: язык (ru-RU, en-US, uz-UZ)
            delete_after: удалить WAV после распознавания
        """
        if not HAS_SR or not self.recognizer:
            return None

        if not wav_path or not Path(wav_path).exists():
            _log_warn(f"Файл не найден: {wav_path}")
            return None

        result: Optional[str] = None

        try:
            with sr.AudioFile(wav_path) as source:
                audio = self.recognizer.record(source)

            # Таймаут для Google API
            try:
                self.recognizer.operation_timeout = RECOGNIZE_TIMEOUT
            except Exception:
                pass

            result = self.recognizer.recognize_google(audio, language=language)
            _log(f"Распознано: {result}")

        except sr.UnknownValueError:
            _log_warn("Речь не распознана")
        except sr.RequestError as e:
            _log_warn(f"Ошибка сервиса: {e}")
        except Exception as e:
            _log_warn(f"Ошибка распознавания: {e}")
        finally:
            if delete_after:
                self._delete_file(wav_path)

        return result

    # ============================================================
    #  ГЛАВНЫЕ МЕТОДЫ
    # ============================================================

    def listen(self, duration: int = None,
               language: str = LANGUAGE) -> Optional[str]:
        """Слушать + распознать (фиксированное время)."""
        wav_path = self.record(duration)
        if not wav_path:
            return None
        return self.recognize_file(wav_path, language, delete_after=True)

    def listen_async(
        self,
        callback: Callable[[Optional[str]], None],
        duration: int = None,
        language: str = LANGUAGE,
    ):
        """Слушать + распознать (в отдельном потоке)."""
        import threading

        def worker():
            text = self.listen(duration, language)
            if callback:
                try:
                    callback(text)
                except Exception as e:
                    _log_warn(f"Callback: {e}")

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return thread

    # ============================================================
    #  СПИСОК МИКРОФОНОВ
    # ============================================================

    def list_devices(self) -> List[Dict[str, Any]]:
        """Список микрофонов (с пометкой дефолтного)."""
        if not HAS_SOUND:
            return []

        try:
            default_device = None
            try:
                default_device = sd.default.device
                if isinstance(default_device, (list, tuple)):
                    default_device = default_device[0]
            except Exception:
                pass

            devices = sd.query_devices()
            inputs = []
            for i, d in enumerate(devices):
                max_in = d.get("max_input_channels", 0)
                if max_in > 0:
                    inputs.append({
                        "id": i,
                        "name": d.get("name", "?"),
                        "channels": max_in,
                        "default": (i == default_device),
                    })
            return inputs
        except Exception as e:
            _log_warn(f"Ошибка списка устройств: {e}")
            return []

    def get_default_device(self) -> Optional[int]:
        """ID дефолтного микрофона."""
        if not HAS_SOUND:
            return None
        try:
            default = sd.default.device
            if isinstance(default, (list, tuple)):
                return default[0]
            return default
        except Exception:
            return None

    def cleanup_old_wavs(self, max_age_hours: int = 1) -> int:
        """Удаляет старые WAV из data/temp."""
        try:
            cutoff = time.time() - max_age_hours * 3600
            count = 0
            for f in TEMP_DIR.glob("zeta_stt_*.wav"):
                try:
                    if f.stat().st_mtime < cutoff:
                        f.unlink()
                        count += 1
                except Exception:
                    continue
            if count:
                _log(f"Очищено старых WAV: {count}")
            return count
        except Exception:
            return 0


# ================================================================
#  ГЛОБАЛЬНЫЙ
# ================================================================

_stt: Optional[STTManager] = None


def get_stt() -> STTManager:
    global _stt
    if _stt is None:
        _stt = STTManager()
    return _stt


def listen(duration: int = None) -> Optional[str]:
    return get_stt().listen(duration)


# ================================================================
#  ЭКСПОРТ
# ================================================================

__all__ = [
    "STTManager",
    "get_stt",
    "listen",
    "HAS_SOUND",
    "HAS_SR",
]


# ================================================================
#  ТЕСТ
# ================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    print("🎤 Zeta STT — Тест")
    print("=" * 60)

    if not HAS_SOUND:
        print("\n❌ sounddevice не установлен")
        print("   pip install sounddevice soundfile numpy SpeechRecognition")
        sys.exit(1)

    if not HAS_SR:
        print("\n❌ SpeechRecognition не установлен")
        print("   pip install SpeechRecognition")
        sys.exit(1)

    stt = get_stt()

    print("\n🎧 Микрофоны:")
    for d in stt.list_devices():
        marker = " ⭐" if d.get("default") else ""
        print(f"   [{d['id']:2d}] {d['name']}{marker}")

    default_id = stt.get_default_device()
    print(f"\n⭐ Дефолтный: [{default_id}]")

    # Тест 1: Ручная запись
    print("\n" + "=" * 60)
    print("🎤 ТЕСТ 1: Ручная запись")
    print("=" * 60)

    input("\nEnter чтобы начать запись...")

    if stt.start_recording():
        print("\n🔴 Запись... Enter чтобы остановить")
        input()

        wav_path = stt.stop_recording()
        if wav_path:
            print(f"\n🔄 Распознаю...")
            text = stt.recognize_file(wav_path, delete_after=True)
            if text:
                print(f"\n✅ «{text}»")
            else:
                print(f"\n❌ Не распознано")
        else:
            print("\n❌ Не удалось сохранить")
    else:
        print("\n❌ Не удалось начать")

    # Тест 2: До тишины
    print("\n" + "=" * 60)
    print("🎤 ТЕСТ 2: Запись до тишины (3 сек тишины = стоп)")
    print("=" * 60)

    input("\nEnter чтобы начать...")
    print("\n🎤 Говори...")

    wav_path = stt.record_until_silence(
        max_duration=30,
        silence_duration=3.0,
        silence_threshold=500,
    )

    if wav_path:
        print(f"\n🔄 Распознаю...")
        text = stt.recognize_file(wav_path, delete_after=True)
        if text:
            print(f"\n✅ «{text}»")
        else:
            print(f"\n❌ Не распознано")
    else:
        print("\n❌ Не удалось записать (тишина?)")

    # Очистка
    print("\n🧹 Очистка старых WAV...")
    count = stt.cleanup_old_wavs(max_age_hours=0)
    print(f"   Удалено: {count}")

    print("\n" + "=" * 60)
    print("✅ Тесты завершены!")