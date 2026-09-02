# -*- coding: utf-8 -*-
"""
Модуль для создания скриншотов.
Поддерживает: полный экран, активное окно, сжатие изображений,
прямую передачу PIL Image для LLaVA и автоматический вызов LLaVA.
"""

import io
import base64
import threading
import time
from typing import Optional, Tuple

import mss
from PIL import Image

# ========== КОНСТАНТЫ ==========
MAX_SIZE = 800          # Максимальный размер стороны изображения
JPEG_QUALITY = 70       # Качество JPEG (1-100)
SCREENSHOT_TIMEOUT = 5  # Таймаут в секундах


# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

def _compress_image(img: Image.Image, max_size: int = MAX_SIZE, quality: int = JPEG_QUALITY) -> bytes:
    """
    Сжимает изображение: уменьшает размер и конвертирует в JPEG.
    Возвращает байты сжатого изображения.
    """
    if img.width > max_size or img.height > max_size:
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG", quality=quality, optimize=True)
    return buffered.getvalue()


def _capture_monitor(monitor: dict) -> Optional[bytes]:
    """Захватывает указанный монитор и возвращает сжатые байты."""
    try:
        with mss.mss() as sct:
            screenshot = sct.grab(monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            return _compress_image(img)
    except Exception as e:
        print(f"⚠️ Ошибка захвата монитора: {e}")
        return None


def _capture_monitor_pil(monitor: dict) -> Optional[Image.Image]:
    """Захватывает указанный монитор и возвращает PIL Image (без сжатия)."""
    try:
        with mss.mss() as sct:
            screenshot = sct.grab(monitor)
            return Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
    except Exception as e:
        print(f"⚠️ Ошибка захвата монитора: {e}")
        return None


def _run_with_timeout(func, args=(), timeout: int = SCREENSHOT_TIMEOUT) -> Optional[bytes]:
    """Запускает функцию с таймаутом."""
    result = [None]
    error = [None]

    def wrapper():
        try:
            result[0] = func(*args)
        except Exception as e:
            error[0] = str(e)

    thread = threading.Thread(target=wrapper, daemon=True)
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        print("⚠️ Скриншот: таймаут")
        return None
    if error[0]:
        print(f"⚠️ Скриншот: {error[0]}")
        return None
    return result[0]


def _bytes_to_base64(data: bytes) -> str:
    """Конвертирует байты в base64 строку."""
    return base64.b64encode(data).decode('utf-8')


# ========== ОСНОВНЫЕ ФУНКЦИИ ==========

def take_screenshot(timeout: int = SCREENSHOT_TIMEOUT) -> Optional[str]:
    """
    Делает скриншот всего экрана.
    Возвращает base64-строку или None при ошибке.
    
    Args:
        timeout: максимальное время выполнения в секундах
    
    Returns:
        base64 строка изображения или None
    """
    monitor = mss.mss().monitors[1]
    data = _run_with_timeout(_capture_monitor, (monitor,), timeout)
    return _bytes_to_base64(data) if data else None


def take_screenshot_pil(timeout: int = SCREENSHOT_TIMEOUT) -> Optional[Image.Image]:
    """
    Делает скриншот всего экрана и возвращает PIL Image.
    Используется для анализа через LLaVA.
    
    Args:
        timeout: максимальное время выполнения в секундах
    
    Returns:
        PIL Image или None
    """
    monitor = mss.mss().monitors[1]
    return _run_with_timeout(_capture_monitor_pil, (monitor,), timeout)


def take_screenshot_active_window(timeout: int = SCREENSHOT_TIMEOUT) -> Optional[str]:
    """
    Делает скриншот активного окна.
    Если активное окно не найдено — делает скриншот всего экрана.
    Возвращает base64-строку или None при ошибке.
    
    Args:
        timeout: максимальное время выполнения в секундах
    
    Returns:
        base64 строка изображения или None
    """
    try:
        import pygetwindow as gw
        active = gw.getActiveWindow()
        if not active:
            return take_screenshot(timeout=2)
        
        monitor = {
            "left": active.left,
            "top": active.top,
            "width": active.width,
            "height": active.height
        }
        data = _run_with_timeout(_capture_monitor, (monitor,), timeout)
        return _bytes_to_base64(data) if data else None
        
    except ImportError:
        print("⚠️ pygetwindow не установлен. Установите: pip install pygetwindow")
        return take_screenshot(timeout=2)
    except Exception as e:
        print(f"⚠️ Ошибка скриншота активного окна: {e}")
        return take_screenshot(timeout=2)


def take_screenshot_region(left: int, top: int, width: int, height: int, 
                           timeout: int = SCREENSHOT_TIMEOUT) -> Optional[str]:
    """
    Делает скриншот указанной области экрана.
    
    Args:
        left, top: координаты левого верхнего угла
        width, height: размеры области
        timeout: максимальное время выполнения в секундах
    
    Returns:
        base64 строка изображения или None
    """
    monitor = {"left": left, "top": top, "width": width, "height": height}
    data = _run_with_timeout(_capture_monitor, (monitor,), timeout)
    return _bytes_to_base64(data) if data else None


# ========== АНАЛИЗ ЭКРАНА ЧЕРЕЗ LLAVA ==========

def analyze_screen_with_llava(question: str = "Опиши экран") -> Optional[str]:
    """
    Анализирует экран через Ollama LLaVA.
    Возвращает текстовое описание экрана или ошибку.
    
    Args:
        question: вопрос к модели (например "Опиши экран")
    
    Returns:
        строка с описанием или None
    """
    try:
        import requests
        
        # Получаем изображение в PIL формате
        img = take_screenshot_pil()
        if not img:
            return "⚠️ Не удалось сделать скриншот"
        
        # Конвертируем в base64 (PNG для лучшего качества)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        # Отправляем в Ollama
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llava:latest",
                "prompt": question,
                "images": [img_base64],
                "stream": False
            },
            timeout=600
        )
        
        return response.json().get("response", "").strip()
        
    except requests.exceptions.Timeout:
        return "⚠️ LLaVA думает слишком долго. Попробуйте ещё раз."
    except Exception as e:
        return f"⚠️ Ошибка LLaVA: {e}"


# ========== ТЕСТ ==========
if __name__ == "__main__":
    print("📸 Тест скриншотов:")
    
    # Полный экран
    img = take_screenshot()
    if img:
        print(f"✅ Полный экран: {len(img)} символов (base64)")
    else:
        print("❌ Ошибка полного экрана")
    
    # Активное окно
    img = take_screenshot_active_window()
    if img:
        print(f"✅ Активное окно: {len(img)} символов (base64)")
    else:
        print("❌ Ошибка активного окна")
    
    # Область
    img = take_screenshot_region(100, 100, 400, 300)
    if img:
        print(f"✅ Область: {len(img)} символов (base64)")
    else:
        print("❌ Ошибка области")
    
    # LLaVA
    print("\n📸 Анализ экрана через LLaVA:")
    description = analyze_screen_with_llava("Опиши кратко, что видишь на экране")
    if description:
        print(f"✅ Описание: {description[:100]}...")
    else:
        print("❌ Ошибка LLaVA")