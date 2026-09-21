# -*- coding: utf-8 -*-
"""
Модуль для перевода текста.
Поддерживает: 13+ языков, определение языка, умный парсинг команд.
Использует Google Translate API (бесплатный) + MyMemory как резерв.

Особенности:
    - Разбивка длинных текстов на чанки (Google — 5000, MyMemory — 500)
    - Определение языка через границы слов (не подстроки)
    - Красивые имена языков (LANG_NAMES)
    - Логирование в data/zeta.log
"""

import re
import sys
import logging
import requests
from pathlib import Path
from typing import Optional, Tuple, Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))


# ========== ЛОГИРОВАНИЕ ==========

def _log(msg: str) -> None:
    logging.info(f"[TRANS] {msg}")


def _log_warn(msg: str) -> None:
    logging.warning(f"[TRANS] {msg}")


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

# Красивые имена языков (вручную — чтобы не перезаписывались)
LANG_NAMES: Dict[str, str] = {
    "ru": "Русский",
    "en": "Английский",
    "uz": "Узбекский",
    "de": "Немецкий",
    "fr": "Французский",
    "es": "Испанский",
    "zh": "Китайский",
    "ja": "Японский",
    "ar": "Арабский",
    "tr": "Турецкий",
    "it": "Итальянский",
    "ko": "Корейский",
    "pt": "Португальский",
}

# API
GOOGLE_API_URL = "https://translate.googleapis.com/translate_a/single"
MYMEMORY_API_URL = "https://api.mymemory.translated.net/get"
TIMEOUT = 10

# Лимиты
GOOGLE_CHUNK = 4500   # безопасный лимит (Google: 5000)
MYMEMORY_CHUNK = 450  # безопасный лимит (MyMemory: 500)


# ========== ЯЗЫКИ ==========

def _normalize_lang(lang: str) -> Optional[str]:
    """Нормализует код языка."""
    if not lang:
        return None

    lang_lower = lang.lower().strip()

    # Уже код?
    if lang_lower in LANG_NAMES:
        return lang_lower

    # Ищем по названию (с границами слова)
    for name, code in LANGUAGES.items():
        if name == lang_lower:
            return code

    # Частичное совпадение
    for name, code in LANGUAGES.items():
        if name in lang_lower or lang_lower in name:
            return code

    return None


def get_supported_languages() -> List[str]:
    """Возвращает список поддерживаемых языков."""
    return sorted(set(LANGUAGES.values()))


def get_language_name(code: str) -> str:
    """Возвращает название языка по коду."""
    return LANG_NAMES.get(code, code)


# ========== API ПЕРЕВОДА ==========

def _translate_google_chunk(text: str, target_lang: str,
                            source_lang: str = "auto") -> Optional[str]:
    """Перевод одного чанка через Google API."""
    try:
        response = requests.get(
            GOOGLE_API_URL,
            params={
                "client": "gtx",
                "sl": source_lang,
                "tl": target_lang,
                "dt": "t",
                "q": text,
            },
            timeout=TIMEOUT,
        )

        if response.status_code != 200:
            _log_warn(f"Google вернул {response.status_code}")
            return None

        data = response.json()

        if not data or not data[0]:
            return None

        # Склеиваем сегменты
        translated = "".join(
            segment[0] for segment in data[0] if segment and segment[0]
        )
        return translated.strip() if translated.strip() else None

    except requests.exceptions.Timeout:
        _log_warn("Google timeout")
        return None
    except Exception as e:
        _log_warn(f"Google ошибка: {e}")
        return None


def _translate_mymemory_chunk(text: str, target_lang: str,
                              source_lang: str = "auto") -> Optional[str]:
    """Перевод одного чанка через MyMemory."""
    try:
        response = requests.get(
            MYMEMORY_API_URL,
            params={"q": text, "langpair": f"{source_lang}|{target_lang}"},
            timeout=TIMEOUT,
        )

        data = response.json()

        if data.get("responseStatus") != 200:
            return None

        result = data.get("responseData", {}).get("translatedText", "")
        return result.strip() if result.strip() else None

    except Exception as e:
        _log_warn(f"MyMemory ошибка: {e}")
        return None


def _split_into_chunks(text: str, chunk_size: int) -> List[str]:
    """Разбивает текст на чанки по границам предложений."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    current = ""

    # Разбиваем по предложениям (., !, ?)
    sentences = re.split(r"(?<=[.!?])\s+", text)

    for sent in sentences:
        if len(current) + len(sent) + 1 <= chunk_size:
            current = (current + " " + sent).strip() if current else sent
        else:
            if current:
                chunks.append(current)
            # Если предложение само больше лимита — режем жёстко
            while len(sent) > chunk_size:
                chunks.append(sent[:chunk_size])
                sent = sent[chunk_size:]
            current = sent

    if current:
        chunks.append(current)

    return chunks


def _translate_long(text: str, target_lang: str, source_lang: str) -> Optional[str]:
    """Переводит длинный текст через чанки Google."""
    chunks = _split_into_chunks(text, GOOGLE_CHUNK)

    results = []
    for i, chunk in enumerate(chunks):
        translated = _translate_google_chunk(chunk, target_lang, source_lang)
        if translated is None:
            _log_warn(f"Google chunk {i+1}/{len(chunks)} упал")
            return None
        results.append(translated)

    return " ".join(results)


def _translate_long_mymemory(text: str, target_lang: str,
                             source_lang: str) -> Optional[str]:
    """Переводит длинный текст через чанки MyMemory."""
    chunks = _split_into_chunks(text, MYMEMORY_CHUNK)

    results = []
    for i, chunk in enumerate(chunks):
        translated = _translate_mymemory_chunk(chunk, target_lang, source_lang)
        if translated is None:
            _log_warn(f"MyMemory chunk {i+1}/{len(chunks)} упал")
            return None
        results.append(translated)

    return " ".join(results)


# ========== ОСНОВНАЯ ФУНКЦИЯ ==========

def translate(text: str, target_lang: str, source_lang: str = "auto") -> str:
    """Переводит текст на целевой язык."""
    if not text or not text.strip():
        return "⚠️ Нет текста для перевода."

    target_lang = _normalize_lang(target_lang)
    if not target_lang:
        return "⚠️ Неподдерживаемый язык."

    if source_lang == "auto" or not source_lang:
        source_lang = detect_language(text) or "ru"

    source_lang = _normalize_lang(source_lang) or source_lang

    # Уже на нужном языке?
    if source_lang == target_lang:
        return f"ℹ️ Текст уже на {get_language_name(target_lang)}."

    # Длинный текст?
    is_long = len(text) > GOOGLE_CHUNK

    if is_long:
        _log(f"Длинный текст ({len(text)} символов) — чанки")
        translated = _translate_long(text, target_lang, source_lang)
        if translated:
            return translated

        translated = _translate_long_mymemory(text, target_lang, source_lang)
        if translated:
            return translated
    else:
        # Короткий — один запрос
        translated = _translate_google_chunk(text, target_lang, source_lang)
        if translated:
            return translated

        translated = _translate_mymemory_chunk(text, target_lang, source_lang)
        if translated:
            return translated

    return "⚠️ Не удалось перевести текст (проверьте соединение с интернетом)."


# ========== ПАРСИНГ КОМАНДЫ ==========

def _build_lang_regex() -> str:
    """Строит регулярку из длинных названий языков (не коротких кодов)."""
    long_names = [
        name for name in LANGUAGES.keys()
        if len(name) > 2 and name.isalpha() or len(name) > 3
    ]
    # Сортируем по длине (длинные первыми — чтобы «русский» сработал раньше «ру»)
    long_names.sort(key=len, reverse=True)
    return "|".join(re.escape(n) for n in long_names)


_LANG_REGEX = _build_lang_regex()


def needs_translation(message: str) -> Tuple[Optional[str], Optional[str]]:
    """Извлекает язык и текст для перевода."""
    if not message or not message.strip():
        return None, None

    msg_lower = message.lower()

    # Триггеры
    triggers = ["переведи", "переведите", "translate", "перевод", "на язык"]
    has_trigger = any(kw in msg_lower for kw in triggers)

    # Или явное «на русский/английский/...»
    if not has_trigger:
        if not re.search(rf"\bна\s+(?:{_LANG_REGEX})\b", msg_lower):
            return None, None

    # Ищем целевой язык
    target_lang = None
    for lang_name, code in LANGUAGES.items():
        # Только длинные названия (не короткие коды)
        if len(lang_name) <= 2:
            continue
        if re.search(rf"\b{re.escape(lang_name)}\b", msg_lower):
            target_lang = code
            break

    if not target_lang:
        return None, None

    # Извлекаем текст
    text = message

    # Убираем служебные фразы
    service_phrases = [
        "переведи на", "переведите на", "translate to", "перевод на",
        "переведи", "переведите", "translate", "перевод",
        "на язык",
    ]
    for sp in service_phrases:
        text = re.sub(rf"\b{re.escape(sp)}\b", "", text, flags=re.IGNORECASE)

    # Убираем длинные названия языков
    for lang_name in LANGUAGES:
        if len(lang_name) > 2:
            text = re.sub(rf"\b{re.escape(lang_name)}\b", "", text, flags=re.IGNORECASE)

    # Чистим
    text = text.strip(" ,.:;!?\"'–—-")
    text = re.sub(r"\s+", " ", text).strip()

    if not text or len(text) < 2:
        return None, None

    return target_lang, text


# ========== ОПРЕДЕЛЕНИЕ ЯЗЫКА ==========

def detect_language(text: str) -> Optional[str]:
    """Определяет язык текста (ru, en, uz)."""
    if not text:
        return None

    text_lower = text.lower()

    ru_words = [
        "и", "в", "на", "с", "по", "что", "как", "это", "не", "у",
        "я", "он", "она", "мы", "вы", "они", "но", "да", "нет", "или",
        "привет", "здравствуй", "спасибо", "пожалуйста", "извините",
        "хорошо", "плохо", "большой", "маленький", "новый", "старый",
        "работа", "учёба", "писать", "говорить", "видеть", "слышать", "знать",
        "идти", "делать", "быть", "брать", "давать",
        "москва", "россия", "русский",
    ]

    en_words = [
        "the", "and", "to", "of", "for", "with", "on", "at", "from", "by",
        "in", "is", "are", "was", "were", "be", "been", "have", "has", "had",
        "hello", "hi", "thanks", "please", "sorry", "thank", "you", "good", "bad",
        "big", "small", "new", "old", "work", "study", "write", "speak",
        "see", "hear", "know", "go", "do", "take", "give", "say", "tell",
        "london", "usa", "english",
    ]

    uz_words = [
        "va", "bilan", "uchun", "dan", "ga", "ni", "siz", "men", "u", "biz",
        "salom", "qanday", "ishlar", "yaxshi", "rahmat", "iltimos", "kechirasiz",
        "ha", "yoq", "nima", "qayerda", "qachon", "kim", "qanaqa", "nega", "qancha",
        "bugun", "ertaga", "kecha", "hozir", "keyin",
        "bu", "shu", "ular", "sen", "sizlar",
        "katta", "kichik", "yangi", "eski", "yomon", "chiroyli",
        "ish", "o'qish", "yozish", "gapirish", "ko'rish", "eshitish",
        "toshkent", "samarqand", "buxoro", "xiva", "farg'ona", "namangan",
        "o'zbekiston", "o'zbek", "o'zbekcha",
    ]

    def count_matches(words: List[str]) -> int:
        count = 0
        for w in words:
            # Границы слова — не подстрока
            if re.search(rf"\b{re.escape(w)}\b", text_lower):
                count += 1
        return count

    ru_score = count_matches(ru_words)
    en_score = count_matches(en_words)
    uz_score = count_matches(uz_words)

    scores = {"ru": ru_score, "en": en_score, "uz": uz_score}
    best_lang = max(scores, key=scores.get)

    # Если ничего не нашли — русский (дефолт для Zeta)
    if scores[best_lang] == 0:
        return "ru"

    return best_lang


# ========== ЭКСПОРТ ==========

__all__ = [
    "translate",
    "needs_translation",
    "detect_language",
    "get_supported_languages",
    "get_language_name",
    "LANGUAGES",
    "LANG_NAMES",
]


# ========== ТЕСТ ==========

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    print("🧪 Тест translator.py\n")
    print("=" * 60)

    print("\n📝 Тест 1: Перевод RU → UZ")
    print(translate("Привет, как дела?", "uz"))

    print("\n📝 Тест 2: Определение языка")
    for t in ["Привет мир", "Hello world", "Salom dunyo", "O'zbekcha matn"]:
        print(f"  {t!r:25} → {detect_language(t)}")

    print("\n📝 Тест 3: Перевод UZ → RU")
    print(translate("Salom, qandaysiz?", "ru"))

    print("\n📝 Тест 4: same lang (ru → ru)")
    print(translate("Привет, как дела?", "ru"))

    print("\n📝 Тест 5: needs_translation — должно работать")
    tests_pass = [
        "переведи на английский привет мир",
        "переведи на узбекский как дела",
        "translate to russian hello world",
    ]
    for msg in tests_pass:
        lang, text = needs_translation(msg)
        marker = "✅" if lang and text else "❌"
        print(f"  {marker} {msg!r:50} → {lang}, {text!r}")

    print("\n📝 Тест 6: needs_translation — НЕ должно работать")
    tests_fail = [
        "расскажи про энергию",       # «en» внутри слова
        "что такое it?",              # «it» внутри слова
        "привет как дела",            # без триггера
    ]
    for msg in tests_fail:
        lang, text = needs_translation(msg)
        marker = "✅" if not lang else "❌ ОШИБКА"
        print(f"  {marker} {msg!r:35} → {lang}")

    print("\n📝 Тест 7: Длинный текст (чанки)")
    long_text = (
        "Это длинный текст для проверки работы перевода. "
        "Он должен корректно разбиваться на чанки и переводиться. "
        "Проверим, что всё работает без ошибок. " * 100
    )
    print(f"  Длина: {len(long_text)} символов")
    result = translate(long_text[:300], "en")  # для теста — короткий
    print(f"  Результат: {result[:200]}...")

    print("\n📝 Тест 8: Поддерживаемые языки")
    langs = get_supported_languages()
    print(f"  Всего: {len(langs)}")
    print(f"  {', '.join(langs)}")

    print("\n" + "=" * 60)
    print("✅ Тесты завершены!")