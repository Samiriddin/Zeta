# -*- coding: utf-8 -*-
"""
Модуль для создания скриншотов Zeta.
Поддерживает: полный экран, активное окно, сжатие изображений,
прямую передачу PIL Image для LLaVA, автоматический вызов LLaVA,
сохранение скриншотов в файл.

ИСПРАВЛЕНО (2026-09-21):
    - Добавлен import os
    - take_screenshot: добавлен параметр save_path (для ai_engine.handle_screenshot)
    - При save_path файл сохраняется как JPEG (не PNG, чтобы не путать расширения)
    - Добавлена функция save_screenshot_to_file() — отдельная утилита
    - Унифицированы сообщения логирования
    - MODEL_VISION = "llava:13b" (актуальное имя)
"""

import os
import io
import base64
import logging
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

# mss: fallback между новым API (MSS) и старым (mss)
try:
    from mss import MSS as _MSS
except ImportError:
    from mss import mss as _MSS

import requests
from PIL import Image


# ========== КОНСТАНТЫ ==========
MAX_SIZE = 800
JPEG_QUALITY = 70
SCREENSHOT_TIMEOUT = 5
DEFAULT_MONITOR = 1
MODEL_VISION = "llava:13b"   # ← проверь имя через `ollama list`

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="zeta_screen")


# ========== ЛОГИРОВАНИЕ ==========

def _log_info(msg: str) -> None:
    logging.info(f"[SCREEN] {msg}")


def _log_error(msg: str) -> None:
    logging.error(f"[SCREEN] {msg}")


# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

def _compress_image(img: Image.Image, max_size: int = MAX_SIZE, quality: int = JPEG_QUALITY) -> bytes:
    """Сжимает изображение в JPEG-байты."""
    if img.width > max_size or img.height > max_size:
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG", quality=quality, optimize=True)
    return buffered.getvalue()


def _capture_monitor(monitor: dict) -> Optional[bytes]:
    """Захватывает монитор и возвращает сжатые JPEG-байты."""
    try:
        with _MSS() as sct:
            screenshot = sct.grab(monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            return _compress_image(img)
    except Exception as e:
        _log_error(f"Ошибка захвата монитора: {e}")
        return None


def _capture_monitor_pil(monitor: dict) -> Optional[Image.Image]:
    """Захватывает монитор и возвращает PIL Image (без сжатия)."""
    try:
        with _MSS() as sct:
            screenshot = sct.grab(monitor)
            return Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
    except Exception as e:
        _log_error(f"Ошибка захвата монитора (PIL): {e}")
        return None


def _run_with_timeout(func, args=(), timeout: int = SCREENSHOT_TIMEOUT):
    """Запускает функцию с таймаутом."""
    try:
        future = _executor.submit(func, *args)
        return future.result(timeout=timeout)
    except FutureTimeout:
        _log_error(f"Скриншот: таймаут {timeout}с")
        return None
    except Exception as e:
        _log_error(f"Скриншот: {e}")
        return None


def _bytes_to_base64(data: bytes) -> str:
    """Конвертирует байты в base64-строку."""
    return base64.b64encode(data).decode('utf-8')


def _get_monitor(monitor_index: int = DEFAULT_MONITOR) -> Optional[dict]:
    """Возвращает словарь-описание монитора."""
    try:
        with _MSS() as sct:
            monitors = sct.monitors
            if monitor_index < 0 or monitor_index >= len(monitors):
                _log_error(f"Монитор {monitor_index} не найден (всего {len(monitors)})")
                return None
            return dict(monitors[monitor_index])
    except Exception as e:
        _log_error(f"Ошибка получения монитора: {e}")
        return None


def _save_bytes_to_file(data: bytes, save_path: str) -> bool:
    """
    ИСПРАВЛЕНО: сохраняет JPEG-байты в файл.
    Создаёт папку, если её нет.
    """
    if not save_path:
        return False
    try:
        save_dir = os.path.dirname(save_path)
        if save_dir:
            os.makedirs(save_dir, exist_ok=True)
        with open(save_path, "wb") as f:
            f.write(data)
        _log_info(f"📁 Скриншот сохранён: {save_path}")
        return True
    except Exception as e:
        _log_error(f"Не удалось сохранить скриншот: {e}")
        return False


# ========== ОСНОВНЫЕ ФУНКЦИИ ==========

def take_screenshot(timeout: int = SCREENSHOT_TIMEOUT,
                    monitor_index: int = DEFAULT_MONITOR,
                    save_path: Optional[str] = None) -> Optional[str]:
    """
    Делает скриншот экрана.

    Args:
        timeout: таймаут в секундах
        monitor_index: индекс монитора (обычно 1 — основной)
        save_path: если указан, сохранит JPEG-файл по этому пути

    Returns:
        base64-строка (JPEG) или None при ошибке.
    """
    monitor = _get_monitor(monitor_index)
    if not monitor:
        return None

    data = _run_with_timeout(_capture_monitor, (monitor,), timeout)
    if not data:
        return None

    # ИСПРАВЛЕНО: сохраняем в файл, если указан путь
    if save_path:
        _save_bytes_to_file(data, save_path)

    return _bytes_to_base64(data)


def take_screenshot_pil(timeout: int = SCREENSHOT_TIMEOUT,
                        monitor_index: int = DEFAULT_MONITOR) -> Optional[Image.Image]:
    """Делает скриншот и возвращает PIL Image."""
    monitor = _get_monitor(monitor_index)
    if not monitor:
        return None
    return _run_with_timeout(_capture_monitor_pil, (monitor,), timeout)


def take_screenshot_active_window(timeout: int = SCREENSHOT_TIMEOUT,
                                   save_path: Optional[str] = None) -> Optional[str]:
    """Скриншот активного окна."""
    try:
        import pygetwindow as gw
        active = gw.getActiveWindow()
        if not active:
            return take_screenshot(timeout=2, save_path=save_path)

        main = _get_monitor(DEFAULT_MONITOR)
        if not main:
            return take_screenshot(timeout=2, save_path=save_path)

        left = max(active.left, main["left"])
        top = max(active.top, main["top"])
        right = min(active.left + active.width, main["left"] + main["width"])
        bottom = min(active.top + active.height, main["top"] + main["height"])

        if right <= left or bottom <= top:
            _log_error("Активное окно вне экрана — делаю полный скриншот")
            return take_screenshot(timeout=2, save_path=save_path)

        monitor = {
            "left": left,
            "top": top,
            "width": right - left,
            "height": bottom - top,
        }
        data = _run_with_timeout(_capture_monitor, (monitor,), timeout)
        if not data:
            return None

        # ИСПРАВЛЕНО: сохраняем в файл, если указан путь
        if save_path:
            _save_bytes_to_file(data, save_path)

        return _bytes_to_base64(data)

    except ImportError:
        _log_error("pygetwindow не установлен. pip install pygetwindow")
        return take_screenshot(timeout=2, save_path=save_path)
    except Exception as e:
        _log_error(f"Ошибка скриншота активного окна: {e}")
        return take_screenshot(timeout=2, save_path=save_path)


def take_screenshot_region(left: int, top: int, width: int, height: int,
                           timeout: int = SCREENSHOT_TIMEOUT,
                           save_path: Optional[str] = None) -> Optional[str]:
    """Скриншот произвольной области."""
    monitor = {"left": left, "top": top, "width": width, "height": height}
    data = _run_with_timeout(_capture_monitor, (monitor,), timeout)
    if not data:
        return None

    if save_path:
        _save_bytes_to_file(data, save_path)

    return _bytes_to_base64(data)


def save_screenshot_to_file(save_path: str,
                             monitor_index: int = DEFAULT_MONITOR,
                             timeout: int = SCREENSHOT_TIMEOUT) -> bool:
    """
    ИСПРАВЛЕНО: отдельная утилита — сделать скриншот и сразу сохранить в файл.
    Возвращает True при успехе.
    """
    data = _run_with_timeout(_capture_monitor, (_get_monitor(monitor_index),), timeout)
    if not data:
        return False
    return _save_bytes_to_file(data, save_path)


# ========== АНАЛИЗ ЭКРАНА ЧЕРЕЗ LLAVA ==========

def analyze_screen_with_llava(question: str = "Опиши экран",
                               monitor_index: int = DEFAULT_MONITOR,
                               model: str = MODEL_VISION) -> Optional[str]:
    """Анализирует экран через LLaVA."""
    try:
        img = take_screenshot_pil(monitor_index=monitor_index)
        if not img:
            return "⚠️ Не удалось сделать скриншот"

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": question,
                "images": [img_base64],
                "stream": False,
            },
            timeout=600,
        )

        if response.status_code != 200:
            return f"⚠️ Ollama вернул {response.status_code}: {response.text[:200]}"

        data = response.json()
        return data.get("response", "").strip() or "(пустой ответ)"

    except requests.exceptions.ConnectionError:
        return "⚠️ Ollama не запущена. Запусти: ollama serve"
    except requests.exceptions.Timeout:
        return "⚠️ LLaVA думает слишком долго. Попробуй ещё раз."
    except Exception as e:
        _log_error(f"Ошибка LLaVA: {e}")
        return f"⚠️ Ошибка LLaVA: {type(e).__name__}: {e}"


# ========== ЭКСПОРТ ==========

__all__ = [
    "take_screenshot",
    "take_screenshot_pil",
    "take_screenshot_active_window",
    "take_screenshot_region",
    "save_screenshot_to_file",
    "analyze_screen_with_llava",
    "MAX_SIZE",
    "JPEG_QUALITY",
    "MODEL_VISION",
]


# ========== ТЕСТ ==========
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
    )

    print("📸 Тест скриншотов Zeta")
    print("=" * 50)

    # 1. Полный экран
    img = take_screenshot()
    print(f"{'✅' if img else '❌'} Полный экран: {len(img) if img else 0} символов base64")

    # 2. Активное окно
    img = take_screenshot_active_window()
    print(f"{'✅' if img else '❌'} Активное окно: {len(img) if img else 0} символов base64")

    # 3. Область
    img = take_screenshot_region(100, 100, 400, 300)
    print(f"{'✅' if img else '❌'} Область: {len(img) if img else 0} символов base64")

    # 4. С сохранением
    test_path = "data/screenshots/_test_screenshot.jpg"
    img = take_screenshot(save_path=test_path)
    exists = os.path.exists(test_path)
    print(f"{'✅' if exists else '❌'} Сохранение в файл: {test_path} ({os.path.getsize(test_path) if exists else 0} байт)")
    # Удаляем тестовый
    try:
        if exists:
            os.remove(test_path)
    except Exception:
        pass

    # 5. Проверка Ollama
    print("\n🔍 Проверка Ollama и модели:")
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            print(f"✅ Ollama работает. Модели: {models}")
            if MODEL_VISION not in models:
                llava_variants = [m for m in models if "llava" in m.lower()]
                if llava_variants:
                    print(f"⚠️ Модель '{MODEL_VISION}' не найдена. Похожие: {llava_variants}")
                    print(f"💡 Используй: {llava_variants[0]}")
                else:
                    print(f"⚠️ Модель '{MODEL_VISION}' не найдена. LLaVA не установлена?")
                    print(f"💡 Установи: ollama pull llava:13b")
        else:
            print(f"❌ Ollama вернула {r.status_code}")
    except requests.exceptions.ConnectionError:
        print("❌ Ollama не запущена. Запусти: ollama serve")
    except Exception as e:
        print(f"❌ Ошибка проверки Ollama: {e}")

    print("\n📸 Анализ экрана через LLaVA:")
    description = analyze_screen_with_llava("Опиши кратко, что видишь на экране")
    if description and not description.startswith("⚠️"):
        print(f"✅ Описание: {description[:200]}...")
    else:
        print(f"❌ {description}")

    print("\n" + "=" * 50)
    print("✅ Тесты завершены!")