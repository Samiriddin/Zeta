# -*- coding: utf-8 -*-
"""
Zeta — Обработка изображений.
Отправка фото в LLaVA для анализа.
Поддерживает: фото, скриншоты, аниме, арт.
"""

import os
import sys
import base64
import logging
import re
import shutil
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))


def _log(msg: str) -> None:
    logging.info(f"[IMAGE] {msg}")


# ========== КОНСТАНТЫ ==========
OLLAMA_URL = "http://localhost:11434/api/generate"

# Модель зрения (совпадает с ollama list)
MODEL_VISION = "llava:13b"

# Поддерживаемые форматы
SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}

# Максимальный размер (в МБ)
MAX_FILE_SIZE_MB = 20

# Таймаут (в секундах)
TIMEOUT = 300


# ================================================================
#  МЕНЕДЖЕР ИЗОБРАЖЕНИЙ
# ================================================================

class ImageHandler:
    """Обработчик изображений для Zeta"""

    def __init__(self):
        self.last_image_path: Optional[str] = None
        self.last_answer: Optional[str] = None

    # ============================================================
    #  ВАЛИДАЦИЯ
    # ============================================================

    def validate_image(self, path: str) -> Tuple[bool, str]:
        """Проверить, можно ли обработать изображение"""
        if not path:
            return False, "⚠️ Путь к файлу пуст."

        p = Path(path)

        if not p.exists():
            return False, f"⚠️ Файл не найден: {path}"

        if not p.is_file():
            return False, f"⚠️ Это не файл: {path}"

        ext = p.suffix.lower()
        if ext not in SUPPORTED_FORMATS:
            return False, f"⚠️ Неподдерживаемый формат: {ext}\n" \
                          f"Поддерживаются: {', '.join(sorted(SUPPORTED_FORMATS))}"

        size_mb = p.stat().st_size / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB:
            return False, f"⚠️ Файл слишком большой: {size_mb:.1f} МБ\n" \
                          f"Максимум: {MAX_FILE_SIZE_MB} МБ"

        return True, ""

    # ============================================================
    #  КОДИРОВАНИЕ
    # ============================================================

    def _encode_image(self, path: str) -> Optional[str]:
        """Кодировать изображение в base64"""
        try:
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            _log(f"⚠️ Ошибка кодирования: {e}")
            return None

    # ============================================================
    #  ПРОМПТЫ
    # ============================================================

    def _build_prompt(self, question: str = None, custom_prompt: str = None) -> str:
        """Построить промпт для LLaVA"""

        if custom_prompt:
            return custom_prompt

        if question:
            return (
                f"Вопрос: {question}\n\n"
                f"Ответь ТОЛЬКО на русском языке. Кратко, 2-4 предложения."
            )

        return (
            "Ты — Zeta, ИИ-помощник. Отвечай ТОЛЬКО на РУССКОМ языке.\n\n"
            "Опиши это изображение.\n\n"
            "Если это аниме/манга:\n"
            "• Назови персонажа (если знаешь)\n"
            "• Назови сериал/фильм\n"
            "• Опиши внешность (волосы, одежда, глаза)\n"
            "• Опиши окружение и сцену\n\n"
            "Если это фото/скриншот:\n"
            "• Что главное на изображении?\n"
            "• Кто или что?\n"
            "• Где это происходит?\n"
            "• Цвета, атмосфера\n\n"
            "Если есть текст — прочитай его.\n\n"
            "Отвечай кратко: 3-5 предложений. ТОЛЬКО ПО-РУССКИ!"
        )

    # ============================================================
    #  АНАЛИЗ
    # ============================================================

    def analyze_image(self, path: str, question: str = None,
                      custom_prompt: str = None) -> Tuple[bool, str]:
        """
        Проанализировать изображение через LLaVA.
        Возвращает (успех?, ответ).
        """
        is_valid, error = self.validate_image(path)
        if not is_valid:
            return False, error

        image_b64 = self._encode_image(path)
        if not image_b64:
            return False, "⚠️ Не удалось прочитать изображение."

        prompt = self._build_prompt(question, custom_prompt)

        try:
            _log(f"📸 Анализ: {Path(path).name} ({len(image_b64)} base64)")

            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": MODEL_VISION,
                    "prompt": prompt,
                    "images": [image_b64],
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 1024,
                    }
                },
                timeout=TIMEOUT
            )

            if response.status_code != 200:
                _log(f"⚠️ LLaVA вернул {response.status_code}")
                return False, f"⚠️ Ошибка LLaVA: {response.status_code}"

            answer = response.json().get("response", "").strip()

            if not answer:
                return False, "⚠️ LLaVA не дала ответа."

            answer = self._clean_answer(answer)

            self.last_image_path = path
            self.last_answer = answer

            _log(f"✅ Ответ получен ({len(answer)} символов)")

            return True, answer

        except requests.exceptions.Timeout:
            _log(f"⏱️ Таймаут LLaVA ({TIMEOUT} сек)")
            return False, f"⚠️ LLaVA думает слишком долго (>{TIMEOUT // 60} минут)."
        except requests.exceptions.ConnectionError:
            _log(f"❌ Ollama не отвечает")
            return False, "⚠️ Ollama не запущена. Запустите: ollama serve"
        except Exception as e:
            _log(f"⚠️ Ошибка: {e}")
            return False, f"⚠️ Ошибка анализа: {e}"

    # ============================================================
    #  УТИЛИТЫ
    # ============================================================

    def _clean_answer(self, answer: str) -> str:
        """Очистить ответ от лишнего"""
        if not answer:
            return ""

        answer = re.sub(r"\s+", " ", answer)
        answer = answer.strip()

        if len(answer) > 2000:
            answer = answer[:2000] + "..."

        return answer

    def get_last_image(self) -> Optional[str]:
        return self.last_image_path

    def get_last_answer(self) -> Optional[str]:
        return self.last_answer

    def save_to_cache(self, path: str) -> str:
        """Сохранить копию изображения в data/images/"""
        try:
            cache_dir = Path("data/images")
            cache_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            ext = Path(path).suffix.lower()
            new_name = f"image_{timestamp}{ext}"
            new_path = cache_dir / new_name

            shutil.copy2(path, new_path)

            _log(f"📁 Сохранено: {new_path}")
            return str(new_path)
        except Exception as e:
            _log(f"⚠️ Ошибка сохранения: {e}")
            return path

    # ============================================================
    #  ПРОВЕРКА МОДЕЛЕЙ
    # ============================================================

    def check_models(self) -> dict:
        """Проверить доступные vision-модели в Ollama"""
        try:
            r = requests.get("http://localhost:11434/api/tags", timeout=3)
            if r.status_code != 200:
                return {"error": "Ollama не отвечает"}

            data = r.json()
            models = [m.get("name", "") for m in data.get("models", [])]

            vision_models = [
                m for m in models
                if any(v in m.lower() for v in ["llava", "bakllava", "vision"])
            ]

            return {
                "all": models,
                "vision": vision_models,
                "current": MODEL_VISION,
                "current_available": MODEL_VISION in models,
            }
        except Exception as e:
            return {"error": str(e)}


# ========== ГЛОБАЛЬНЫЙ ==========
_image_handler: Optional[ImageHandler] = None


def get_image_handler() -> ImageHandler:
    global _image_handler
    if _image_handler is None:
        _image_handler = ImageHandler()
    return _image_handler


def analyze_image(path: str, question: str = None) -> Tuple[bool, str]:
    return get_image_handler().analyze_image(path, question)


# ========== ТЕСТ ==========
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print("🖼️ Zeta Image Handler — Тест")
    print("=" * 60)

    handler = get_image_handler()

    print("\n📊 Методы:")
    print(f"   analyze_image()  → {hasattr(handler, 'analyze_image')}")
    print(f"   validate_image() → {hasattr(handler, 'validate_image')}")
    print(f"   check_models()   → {hasattr(handler, 'check_models')}")

    print("\n🔍 Vision-модели в Ollama:")
    models = handler.check_models()
    if "error" in models:
        print(f"   ❌ {models['error']}")
    else:
        print(f"   Доступные: {', '.join(models['vision']) or 'нет'}")
        print(f"   Текущая:  {models['current']}")
        print(f"   Готовность: {'✅' if models['current_available'] else '❌ (установите через ollama pull ' + models['current'] + ')'}")

    print("\n🧪 Валидация:")
    test_cases = [
        ("", "Пустой путь"),
        ("D:/not_exists.jpg", "Несуществующий файл"),
        ("D:/test.txt", "Неправильный формат"),
    ]
    for path, description in test_cases:
        ok, err = handler.validate_image(path)
        status = "✅ OK" if not ok else "❌"
        print(f"   {status} {description}: {err[:60] if err else 'прошло'}")

    print("\n📝 Стандартный промпт (первые 100 символов):")
    prompt = handler._build_prompt()
    print(f"   {prompt[:100]}...")

    print("\n" + "=" * 60)
    print("💡 Для теста с реальным изображением:")
    print("   python -c \"from modules.image_handler import analyze_image; ok, msg = analyze_image('D:/test.jpg'); print('OK' if ok else 'FAIL'); print(msg)\"")
    print("\n✅ Тесты пройдены!")