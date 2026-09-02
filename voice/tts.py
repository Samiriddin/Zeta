# -*- coding: utf-8 -*-
"""
Модуль синтеза речи через edge-tts (Microsoft Neural TTS).
Поддерживает 6 голосов, регулировку скорости.
Озвучивает ВЕСЬ текст без обрезки.
"""

import asyncio
import tempfile
import os
import threading
import re
import time
from typing import Optional

try:
    import edge_tts
    HAS_EDGE = True
except ImportError:
    HAS_EDGE = False

try:
    from playsound import playsound
    HAS_PLAYSOUND = True
except ImportError:
    HAS_PLAYSOUND = False


def _clean_text(text: str) -> str:
    """Очищает текст для TTS. БЕЗ ОБРЕЗКИ."""
    if not text:
        return ""
    # Убираем markdown/код, чтобы не читать лишнее
    text = re.sub(r"```[\s\S]*?```", " Код пропущен. ", text)
    text = re.sub(r"`[^`]*`", " Код пропущен. ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"https?://\S+", " ссылка. ", text)
    # Убираем нечитаемые символы, но сохраняем русские и английские буквы, цифры и знаки препинания
    text = re.sub(r"[^\w\s\.\,\!\?\-\:\;\(\)\'\"А-Яа-яЁё0-9]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    
    # ❌ УДАЛИЛИ MAX_LEN = 400. Теперь текст не обрезается!
    return text


def _format_rate(speed: float) -> str:
    """
    Форматирует скорость для edge-tts.
    edge-tts ожидает формат: "+0%", "-50%", "+100%"
    """
    if speed == 1.0:
        return "+0%"
    
    rate_percent = int((speed - 1.0) * 100)
    
    if rate_percent < -50:
        rate_percent = -50
    elif rate_percent > 100:
        rate_percent = 100
    
    if rate_percent >= 0:
        return f"+{rate_percent}%"
    else:
        return f"{rate_percent}%"


def _play_audio(path: str) -> bool:
    """Воспроизводит аудио файл."""
    if HAS_PLAYSOUND:
        try:
            playsound(path, block=True)
            return True
        except Exception as e:
            print(f"⚠️ Ошибка playsound: {e}")

    try:
        os.startfile(path)
        return False
    except Exception as e:
        print(f"⚠️ Ошибка воспроизведения: {e}")
        return False


def _get_voices() -> list:
    """Возвращает список доступных голосов."""
    all_voices = [
        "ru-RU-SvetlanaNeural",
        "ru-RU-DariyaNeural",
        "ru-RU-DmitryNeural",
        "uk-UA-PolinaNeural",
        "en-US-AriaNeural",
        "en-US-GuyNeural",
    ]
    try:
        from core.memory import get_setting
        preferred = get_setting("tts_voice", "ru-RU-SvetlanaNeural")
        if preferred in all_voices:
            return [preferred] + [v for v in all_voices if v != preferred]
    except Exception:
        pass
    return all_voices


def speak(text: str, voice: Optional[str] = None, speed: float = 1.0):
    """
    Озвучивает текст через edge-tts.
    voice — код голоса (например, "ru-RU-SvetlanaNeural").
    speed — скорость речи (0.5 - 2.0).
    Если voice не указан — используется голос из настроек.
    """
    if not HAS_EDGE:
        print("🔇 TTS: edge-tts не установлен. Установите: pip install edge-tts")
        return

    clean = _clean_text(text)
    if not clean:
        return

    # Если голос не указан — берём из настроек
    if voice is None:
        try:
            from core.memory import get_setting
            voice = get_setting("tts_voice", "ru-RU-SvetlanaNeural")
        except Exception:
            voice = "ru-RU-SvetlanaNeural"

    # Форматируем скорость правильно
    rate = _format_rate(speed)

    voices = [voice] + [v for v in [
        "ru-RU-SvetlanaNeural",
        "ru-RU-DariyaNeural",
        "ru-RU-DmitryNeural",
        "uk-UA-PolinaNeural",
        "en-US-AriaNeural",
        "en-US-GuyNeural"
    ] if v != voice]

    def run():
        tmp_path = None
        loop = None
        for v in voices:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                communicate = edge_tts.Communicate(clean, v, rate=rate)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3", prefix="zeta_") as tmp:
                    tmp_path = tmp.name

                loop.run_until_complete(communicate.save(tmp_path))

                if not (os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 1024):
                    continue

                _play_audio(tmp_path)

                # Удаляем файл после воспроизведения
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

                return

            except Exception as e:
                print(f"⚠️ Ошибка TTS ({v}, rate={rate}): {e}")
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass
                continue
            finally:
                if loop:
                    try:
                        loop.close()
                    except Exception:
                        pass

        print("🔇 TTS: все голоса недоступны.")

    t = threading.Thread(target=run, daemon=True)
    t.start()


def speak_sync(text: str, voice: Optional[str] = None, speed: float = 1.0):
    """Синхронная обёртка для speak."""
    speak(text, voice, speed)


def set_voice(voice_name: str) -> bool:
    """Устанавливает голос по имени."""
    from core.memory import save_setting
    valid_voices = [
        "ru-RU-SvetlanaNeural",
        "ru-RU-DariyaNeural",
        "ru-RU-DmitryNeural",
        "uk-UA-PolinaNeural",
        "en-US-AriaNeural",
        "en-US-GuyNeural",
    ]
    if voice_name in valid_voices:
        save_setting("tts_voice", voice_name)
        return True
    return False


def get_voice_name() -> str:
    try:
        from core.memory import get_setting
        return get_setting("tts_voice", "ru-RU-SvetlanaNeural")
    except Exception:
        return "ru-RU-SvetlanaNeural"


def get_voices_list() -> list:
    return [
        "ru-RU-SvetlanaNeural",
        "ru-RU-DariyaNeural",
        "ru-RU-DmitryNeural",
        "uk-UA-PolinaNeural",
        "en-US-AriaNeural",
        "en-US-GuyNeural",
    ]


def get_voice_names() -> dict:
    """Возвращает словарь {имя: код_голоса}."""
    return {
        "Светлана": "ru-RU-SvetlanaNeural",
        "Дарья": "ru-RU-DariyaNeural",
        "Дмитрий": "ru-RU-DmitryNeural",
        "Полина": "uk-UA-PolinaNeural",
        "Ария": "en-US-AriaNeural",
        "Гай": "en-US-GuyNeural",
    }


if __name__ == "__main__":
    print("🎤 Тест TTS:")
    if HAS_EDGE:
        speak("Привет! Это тест голоса Светлана. Я теперь умею говорить длинные тексты без обрезки.")
        time.sleep(3)
        speak("А теперь голос Дарьи.", voice="ru-RU-DariyaNeural")
        time.sleep(3)
        speak("Медленная речь.", speed=0.7)
        time.sleep(3)
        speak("Быстрая речь!", speed=1.5)
    else:
        print("❌ edge-tts не установлен. Установите: pip install edge-tts")