# -*- coding: utf-8 -*-
"""
Модуль для перевода текста.
Поддерживает: 13+ языков, определение языка, умный парсинг команд.
Использует Google Translate API (бесплатный) + MyMemory как резерв.
"""

import re
import time
import requests
from typing import Optional, Tuple, Dict, List

# ========== КОНСТАНТЫ ==========

LANGUAGES: Dict[str, str] = {
    # Русский
    "русский": "ru",
    "русском": "ru",
    "russian": "ru",
    "ru": "ru",
    # Английский
    "английский": "en",
    "английском": "en",
    "english": "en",
    "en": "en",
    # Узбекский
    "узбекский": "uz",
    "узбекском": "uz",
    "uzbek": "uz",
    "uz": "uz",
    "o'zbekcha": "uz",
    "ўзбекча": "uz",
    # Немецкий
    "немецкий": "de",
    "немецком": "de",
    "german": "de",
    "de": "de",
    # Французский
    "французский": "fr",
    "французском": "fr",
    "french": "fr",
    "fr": "fr",
    # Испанский
    "испанский": "es",
    "испанском": "es",
    "spanish": "es",
    "es": "es",
    # Китайский
    "китайский": "zh",
    "китайском": "zh",
    "chinese": "zh",
    "zh": "zh",
    # Японский
    "японский": "ja",
    "японском": "ja",
    "japanese": "ja",
    "ja": "ja",
    # Арабский
    "арабский": "ar",
    "арабском": "ar",
    "arabic": "ar",
    "ar": "ar",
    # Турецкий
    "турецкий": "tr",
    "турецком": "tr",
    "turkish": "tr",
    "tr": "tr",
    # Итальянский
    "итальянский": "it",
    "итальянском": "it",
    "italian": "it",
    "it": "it",
    # Корейский
    "корейский": "ko",
    "корейском": "ko",
    "korean": "ko",
    "ko": "ko",
    # Португальский
    "португальский": "pt",
    "португальском": "pt",
    "portuguese": "pt",
    "pt": "pt",
}

# Обратная карта (код → название)
LANG_NAMES: Dict[str, str] = {v: k for k, v in LANGUAGES.items()}

# API
GOOGLE_API_URL = "https://translate.googleapis.com/translate_a/single"
MYMEMORY_API_URL = "https://api.mymemory.translated.net/get"
TIMEOUT = 10
MAX_TEXT_LENGTH = 5000


# ========== ОСНОВНЫЕ ФУНКЦИИ ==========

def _normalize_lang(lang: str) -> Optional[str]:
    """Нормализует код языка."""
    if not lang:
        return None
    
    lang_lower = lang.lower().strip()
    
    if lang_lower in LANGUAGES.values():
        return lang_lower
    
    for name, code in LANGUAGES.items():
        if name == lang_lower or name in lang_lower or lang_lower in name:
            return code
    
    return None


def _translate_google(text: str, target_lang: str, source_lang: str = "auto") -> Optional[str]:
    """Перевод через Google Translate API (бесплатный, без ключей)."""
    try:
        response = requests.get(
            GOOGLE_API_URL,
            params={
                "client": "gtx",
                "sl": source_lang,
                "tl": target_lang,
                "dt": "t",
                "q": text
            },
            timeout=TIMEOUT
        )
        
        if response.status_code != 200:
            return None
        
        data = response.json()
        
        if not data or not data[0]:
            return None
        
        # Склеиваем сегменты перевода
        translated_text = "".join([segment[0] for segment in data[0] if segment[0]])
        return translated_text if translated_text.strip() else None
    
    except Exception:
        return None


def _translate_mymemory(text: str, target_lang: str, source_lang: str = "auto") -> Optional[str]:
    """Перевод через MyMemory API (резервный)."""
    try:
        response = requests.get(
            MYMEMORY_API_URL,
            params={"q": text, "langpair": f"{source_lang}|{target_lang}"},
            timeout=TIMEOUT
        )
        
        data = response.json()
        
        if data.get("responseStatus") != 200:
            return None
        
        result = data.get("responseData", {}).get("translatedText", "")
        return result if result.strip() else None
    
    except Exception:
        return None


def translate(text: str, target_lang: str, source_lang: str = "auto") -> str:
    """Переводит текст на целевой язык."""
    if not text or not text.strip():
        return "⚠️ Нет текста для перевода."
    
    target_lang = _normalize_lang(target_lang)
    if not target_lang:
        return f"⚠️ Неподдерживаемый язык: {target_lang}"
    
    if source_lang == "auto" or not source_lang:
        source_lang = detect_language(text) or "ru"
    
    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH] + "..."
    
    # Пробуем Google Translate API
    translated = _translate_google(text, target_lang, source_lang)
    if translated:
        return translated
    
    # Пробуем MyMemory как резерв
    translated = _translate_mymemory(text, target_lang, source_lang)
    if translated:
        return translated
    
    return f"⚠️ Не удалось перевести текст (возможно, такой же язык или нет соединения)."


def needs_translation(message: str) -> Tuple[Optional[str], Optional[str]]:
    """Извлекает язык и текст для перевода из команды."""
    if not message or not message.strip():
        return None, None
    
    msg_lower = message.lower()
    
    keywords = ["переведи", "переведите", "translate", "перевод", "на язык"]
    if not any(kw in msg_lower for kw in keywords):
        if re.search(r"на\s+(русский|английский|узбекский|english|russian|uzbek|o'zbek|ўзбек)", msg_lower):
            pass
        else:
            return None, None
    
    target_lang = None
    for lang_name, code in LANGUAGES.items():
        if lang_name in msg_lower:
            target_lang = code
            break
    
    if not target_lang:
        return None, None
    
    text = message
    
    # Удаляем служебные слова
    service_words = [
        "переведи на", "переведите на", "translate to", "перевод на",
        "переведи", "переведите", "translate", "перевод",
        "на язык", "на"
    ]
    
    for sw in service_words:
        if sw in text.lower():
            text = text.replace(sw, "", 1)
            break
    
    # Удаляем названия языков
    for lang_name in LANGUAGES:
        text = re.sub(rf"на\s+{lang_name}", "", text, flags=re.IGNORECASE)
        text = re.sub(rf"{lang_name}", "", text, flags=re.IGNORECASE)
    
    text = text.strip(" ,.:;!?\"'–—")
    text = re.sub(r"\s+", " ", text)
    
    if not text:
        return None, None
    
    return target_lang, text


def detect_language(text: str) -> Optional[str]:
    """Определяет язык текста (русский, английский, узбекский)."""
    if not text:
        return None
    
    text_lower = text.lower()
    
    # Русские слова
    ru_words = [
        "и", "в", "на", "с", "по", "что", "как", "это", "не", "у", "я", "он", "мы", "вы",
        "привет", "здравствуй", "спасибо", "пожалуйста", "извините",
        "хорошо", "плохо", "большой", "маленький", "новый", "старый",
        "работа", "учёба", "писать", "говорить", "видеть", "слышать", "знать",
        "идти", "делать", "быть", "брать", "давать", "говорить",
        "Москва", "Россия", "русский",
    ]
    
    # Английские слова
    en_words = [
        "the", "and", "to", "of", "for", "with", "on", "at", "from", "by", "in",
        "hello", "hi", "thanks", "please", "sorry", "thank", "you", "good", "bad",
        "big", "small", "new", "old", "work", "study", "write", "speak", "see", "hear", "know",
        "go", "do", "be", "take", "give", "say", "tell",
        "London", "USA", "English",
    ]
    
    # Узбекские слова
    uz_words = [
        "va", "bilan", "uchun", "da", "dan", "ga", "ni", "siz", "men", "u", "biz",
        "salom", "qanday", "ishlar", "yaxshi", "rahmat", "iltimos", "kechirasiz",
        "ha", "yoq", "nima", "qayerda", "qachon", "kim", "qanaqa", "nega", "qancha",
        "bugun", "ertaga", "kecha", "hozir", "keyin", "olding", "orqada", "yonida",
        "bu", "shu", "ular", "biz", "men", "sen", "sizlar",
        "katta", "kichik", "yangi", "eski", "yaxshi", "yomon", "chiroyli", "go'zal",
        "ish", "o'qish", "yozish", "gapirish", "ko'rish", "eshitish", "bilish",
        "kelmoq", "ketmoq", "qilmoq", "bo'lmoq", "olmoq", "bermoq", "aytmoq",
        "Toshkent", "Samarqand", "Buxoro", "Xiva", "Farg'ona", "Namangan",
        "O'zbekiston", "o'zbek", "o'zbekcha", "uzbek", "uzb",
    ]
    
    ru_score = sum(1 for w in ru_words if w in text_lower)
    en_score = sum(1 for w in en_words if w in text_lower)
    uz_score = sum(1 for w in uz_words if w in text_lower)
    
    # Если узбекский доминирует
    if uz_score >= ru_score and uz_score >= en_score and uz_score > 0:
        return "uz"
    elif ru_score >= en_score:
        return "ru"
    elif en_score >= ru_score:
        return "en"
    
    return "ru"


def get_supported_languages() -> List[str]:
    """Возвращает список поддерживаемых языков."""
    return sorted(set(LANGUAGES.values()))


def get_language_name(code: str) -> str:
    """Возвращает название языка по коду."""
    return LANG_NAMES.get(code, code)


# ========== ТЕСТ ==========
if __name__ == "__main__":
    print("🧪 Тест translator.py\n")
    
    print("📝 Тест 1: Перевод на узбекский")
    result = translate("Привет, как дела?", "uz")
    print(f"Результат: {result}")
    print("-" * 40)
    
    print("📝 Тест 2: Определение языка")
    texts = ["Привет мир", "Hello world", "Salom dunyo", "O'zbekcha matn"]
    for t in texts:
        lang = detect_language(t)
        print(f"{t} → {lang}")
    print("-" * 40)
    
    print("📝 Тест 3: Перевод с узбекского")
    result = translate("Salom, qandaysiz?", "ru")
    print(f"Результат: {result}")
    print("-" * 40)
    
    print("📝 Тест 4: Поддерживаемые языки")
    langs = get_supported_languages()
    print(f"Всего языков: {len(langs)}")
    print(f"Коды: {', '.join(langs)}")
    print("-" * 40)
    
    print("📝 Тест 5: Перевод длинного текст")
    long_text = "Это длинный текст для проверки работоспособности перевода. Он должен корректно переводиться на английский язык."
    result = translate(long_text, "en")
    print(f"Результат: {result}")
    print("-" * 40)
    
    print("\n✅ Тесты завершены!")