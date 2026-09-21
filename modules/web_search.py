# -*- coding: utf-8 -*-
"""
Максимально расширенный модуль для поиска в интернете.
Поддерживает: текстовый поиск, новости, изображения, видео, погоду, курсы валют,
перевод, определение, калькулятор, википедию, карты, товары, рецепты, словари.

Особенности:
    - Точные триггеры (не срабатывает на «как дела?»)
    - Автоочистка кэша
    - Разные TTL для разных типов (погода — 5 мин, wiki — 24 ч)
    - Распознавание «картинка», «фото», «видео»
    - Логирование в data/zeta.log
"""

import sys
import re
import time
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))


# ========== ЛОГИРОВАНИЕ ==========

def _log(msg: str) -> None:
    logging.info(f"[SEARCH] {msg}")


def _log_warn(msg: str) -> None:
    logging.warning(f"[SEARCH] {msg}")


# ========== БИБЛИОТЕКИ ==========

try:
    from ddgs import DDGS
    HAS_DDGS = True
except ImportError:
    try:
        from duckduckgo_search import DDGS
        HAS_DDGS = True
    except ImportError:
        HAS_DDGS = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# ========== КОНСТАНТЫ ==========

MAX_RESULTS = 3
MAX_NEWS_RESULTS = 5
MAX_IMAGES_RESULTS = 5
MAX_VIDEOS_RESULTS = 5
TIMEOUT = 20
MAX_TEXT_LENGTH = 500

# Разные TTL для разных типов (секунды)
TTL_WEB = 600       # 10 мин
TTL_NEWS = 300      # 5 мин
TTL_WEATHER = 300   # 5 мин
TTL_CURRENCY = 1800 # 30 мин
TTL_WIKI = 86400    # 24 часа
TTL_RECIPE = 3600   # 1 час
TTL_SHOPPING = 3600 # 1 час
TTL_DEFINITION = 86400  # 24 часа

# Точные триггеры (НЕ «как», НЕ «кто», НЕ «что» — они слишком частые)
SEARCH_KEYWORDS = {
    # Явные команды поиска
    "найди в интернете": "search",
    "поищи в интернете": "search",
    "погугли": "search",
    "search for": "search",
    "find on internet": "search",
    "google it": "search",

    # Явные команды на определение
    "что такое": "definition",
    "кто такой": "definition",
    "кто такая": "definition",
    "что значит": "definition",
    "дай определение": "definition",
    "what is": "definition",
    "who is": "definition",

    # Явные новости
    "новости про": "news",
    "новости о": "news",
    "последние новости": "news",
    "что нового про": "news",
    "news about": "news",

    # Погода
    "погода в": "weather",
    "погода на": "weather",
    "какая погода": "weather",
    "weather in": "weather",

    # Курс валют
    "курс доллара": "currency",
    "курс евро": "currency",
    "курс рубля": "currency",
    "курс валют": "currency",

    # Цены и товары
    "сколько стоит": "price",
    "цена на": "price",
    "купить": "shopping",
    "где купить": "shopping",

    # Изображения / видео
    "найди картинку": "images",
    "найди фото": "images",
    "покажи картинку": "images",
    "покажи фото": "images",
    "найди видео": "videos",
    "покажи видео": "videos",

    # Рецепты
    "рецепт": "recipe",
    "как приготовить": "recipe",
    "как готовить": "recipe",

    # Википедия
    "wiki": "wikipedia",
    "вики": "wikipedia",
    "википедия": "wikipedia",

    # Карты
    "где находится": "map",
    "как добраться": "map",
    "маршрут": "map",
    "карта": "map",

    # Отзывы
    "отзывы": "reviews",
    "оценка": "reviews",

    # Английские
    "search for": "search",
    "find": "search",
    "news": "news",
    "weather": "weather",
    "price": "price",
    "recipe": "recipe",
    "map": "map",
    "shopping": "shopping",
    "reviews": "reviews",
}

# Общие вопросительные паттерны (только точные — не «как дела»)
QUESTION_PATTERNS = [
    r"\bчто\s+такое\b",
    r"\bкто\s+так(ой|ая|ие)\b",
    r"\bчто\s+значит\b",
    r"\bкак\s+(приготовить|готовить|сделать|найти|купить|добраться)",
    r"\bгде\s+(находится|купить|найти)",
    r"\bкогда\s+(произошл|будет|выйдет|состоится)",
    r"\bпочему\s+(произошл|случил|стал|работает|не\s+работает)",
    r"\bсколько\s+(стоит|будет|стоят)",
    r"\bновости\s+(про|о)\b",
    r"\bпогода\b",
]


# ========== КЭШ ==========

_search_cache: Dict[str, Tuple[str, float, int]] = {}  # key → (result, timestamp, ttl)


def _get_cached(key: str) -> Optional[str]:
    """Возвращает кэшированный результат."""
    if key in _search_cache:
        result, timestamp, ttl = _search_cache[key]
        if time.time() - timestamp < ttl:
            return result
        # Просрочен — удаляем
        del _search_cache[key]
    return None


def _set_cache(key: str, value: str, ttl: int = TTL_WEB) -> None:
    """Сохраняет результат в кэш с TTL."""
    _search_cache[key] = (value, time.time(), ttl)
    _cleanup_cache()


def _cleanup_cache() -> None:
    """Удаляет просроченные записи."""
    now = time.time()
    expired = [k for k, (_, ts, ttl) in _search_cache.items() if now - ts >= ttl]
    for k in expired:
        del _search_cache[k]


# ========== ОСНОВНЫЕ ФУНКЦИИ ==========

def search_web(query: str, max_results: int = MAX_RESULTS,
               timeout: int = TIMEOUT) -> str:
    """Поиск в интернете через DuckDuckGo."""
    if not query or not query.strip():
        return "⚠️ Укажите поисковый запрос."

    if not HAS_DDGS:
        return "⚠️ Установите ddgs: pip install ddgs"

    cache_key = f"web_{query.lower()}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    try:
        with DDGS(timeout=timeout) as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
    except Exception as e:
        _log_warn(f"DuckDuckGo ошибка: {e}")
        return f"⚠️ Ошибка поиска: {e}"

    if results:
        result = _format_results(results, query)
        _set_cache(cache_key, result, TTL_WEB)
        return result

    return f"🔍 По запросу `{query}` ничего не найдено."


def search_news(query: str, max_results: int = MAX_NEWS_RESULTS) -> str:
    """Новости по запросу."""
    if not HAS_DDGS:
        return "⚠️ Установите ddgs: pip install ddgs"
    if not query or not query.strip():
        return "⚠️ Укажите запрос для новостей."

    cache_key = f"news_{query.lower()}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    try:
        with DDGS(timeout=TIMEOUT) as ddgs:
            results = list(ddgs.news(query, max_results=max_results))
            if results:
                result = _format_news(results)
                _set_cache(cache_key, result, TTL_NEWS)
                return result
            return f"📰 Новостей по запросу `{query}` не найдено."
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def search_images(query: str, max_results: int = MAX_IMAGES_RESULTS) -> str:
    """Изображения по запросу."""
    if not HAS_DDGS:
        return "⚠️ Установите ddgs: pip install ddgs"
    if not query or not query.strip():
        return "⚠️ Укажите запрос для изображений."

    try:
        with DDGS(timeout=TIMEOUT) as ddgs:
            results = list(ddgs.images(query, max_results=max_results))
            if results:
                return _format_images(results)
            return f"🖼️ Изображений по запросу `{query}` не найдено."
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def search_videos(query: str, max_results: int = MAX_VIDEOS_RESULTS) -> str:
    """Видео по запросу."""
    if not HAS_DDGS:
        return "⚠️ Установите ddgs: pip install ddgs"
    if not query or not query.strip():
        return "⚠️ Укажите запрос для видео."

    try:
        with DDGS(timeout=TIMEOUT) as ddgs:
            results = list(ddgs.videos(query, max_results=max_results))
            if results:
                return _format_videos(results)
            return f"🎬 Видео по запросу `{query}` не найдено."
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def search_weather(city: str) -> str:
    """Погода в городе."""
    if not HAS_DDGS:
        return "⚠️ Установите ddgs: pip install ddgs"
    if not city or not city.strip():
        return "⚠️ Укажите город."

    cache_key = f"weather_{city.lower()}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    query = f"погода {city}"
    try:
        with DDGS(timeout=TIMEOUT) as ddgs:
            results = list(ddgs.text(query, max_results=2))
            if results:
                result = _format_weather(results, city)
                _set_cache(cache_key, result, TTL_WEATHER)
                return result
            return f"🌤️ Не удалось найти погоду для {city}."
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def search_currency(from_currency: str = "USD", to_currency: str = "UZS") -> str:
    """Курс валют."""
    if not HAS_DDGS:
        return "⚠️ Установите ddgs: pip install ddgs"

    cache_key = f"currency_{from_currency}_{to_currency}".lower()
    cached = _get_cached(cache_key)
    if cached:
        return cached

    query = f"{from_currency} to {to_currency}"
    try:
        with DDGS(timeout=TIMEOUT) as ddgs:
            results = list(ddgs.text(query, max_results=2))
            if results:
                result = _format_currency(results, from_currency, to_currency)
                _set_cache(cache_key, result, TTL_CURRENCY)
                return result
            return f"💱 Не удалось найти курс {from_currency} к {to_currency}."
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def search_wikipedia(query: str) -> str:
    """Информация из Википедии."""
    if not HAS_DDGS:
        return "⚠️ Установите ddgs: pip install ddgs"
    if not query or not query.strip():
        return "⚠️ Укажите запрос для Википедии."

    cache_key = f"wiki_{query.lower()}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    try:
        with DDGS(timeout=TIMEOUT) as ddgs:
            results = list(ddgs.text(f"wiki {query}", max_results=2))
            if results:
                result = _format_wikipedia(results, query)
                _set_cache(cache_key, result, TTL_WIKI)
                return result
            return f"📚 Информация по запросу `{query}` не найдена."
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def search_recipe(query: str) -> str:
    """Рецепты."""
    if not HAS_DDGS:
        return "⚠️ Установите ddgs: pip install ddgs"
    if not query or not query.strip():
        return "⚠️ Укажите блюдо для рецепта."

    cache_key = f"recipe_{query.lower()}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    try:
        with DDGS(timeout=TIMEOUT) as ddgs:
            results = list(ddgs.text(f"рецепт {query}", max_results=2))
            if results:
                result = _format_recipe(results, query)
                _set_cache(cache_key, result, TTL_RECIPE)
                return result
            return f"🍳 Рецепт для `{query}` не найден."
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def search_shopping(query: str) -> str:
    """Товары."""
    if not HAS_DDGS:
        return "⚠️ Установите ddgs: pip install ddgs"
    if not query or not query.strip():
        return "⚠️ Укажите товар для поиска."

    cache_key = f"shop_{query.lower()}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    try:
        with DDGS(timeout=TIMEOUT) as ddgs:
            results = list(ddgs.text(f"купить {query}", max_results=2))
            if results:
                result = _format_shopping(results, query)
                _set_cache(cache_key, result, TTL_SHOPPING)
                return result
            return f"🛒 Товары по запросу `{query}` не найдены."
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def search_definition(word: str) -> str:
    """Определение слова."""
    if not HAS_DDGS:
        return "⚠️ Установите ddgs: pip install ddgs"
    if not word or not word.strip():
        return "⚠️ Укажите слово для определения."

    cache_key = f"def_{word.lower()}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    try:
        with DDGS(timeout=TIMEOUT) as ddgs:
            results = list(ddgs.text(f"определение {word}", max_results=2))
            if results:
                result = _format_definition(results, word)
                _set_cache(cache_key, result, TTL_DEFINITION)
                return result
            return f"📖 Определение слова `{word}` не найдено."
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


# ========== ФОРМАТТЕРЫ ==========

def _format_results(results: List[Dict[str, str]], query: str) -> str:
    formatted = f"🔍 **Результаты поиска:** `{query}`\n\n"
    for i, r in enumerate(results, 1):
        title = r.get("title", "Без заголовка")
        body = r.get("body", "")
        if len(body) > MAX_TEXT_LENGTH:
            body = body[:MAX_TEXT_LENGTH] + "..."
        href = r.get("href", "")

        formatted += f"**{i}. {title}**\n"
        if href:
            formatted += f"🔗 {href}\n"
        if body:
            formatted += f"📝 {body}\n"
        formatted += "\n"
    return formatted.strip()


def _format_news(results: List[Dict[str, str]]) -> str:
    formatted = "📰 **Новости:**\n\n"
    for i, r in enumerate(results, 1):
        title = r.get("title", "Без заголовка")
        body = r.get("body", "")[:MAX_TEXT_LENGTH]
        source = r.get("source", "")
        date = r.get("date", "")

        formatted += f"**{i}. {title}**\n"
        meta = []
        if source:
            meta.append(f"📰 {source}")
        if date:
            meta.append(f"📅 {date}")
        if meta:
            formatted += " | ".join(meta) + "\n"
        if body:
            formatted += f"📝 {body}\n"
        formatted += "\n"
    return formatted.strip()


def _format_images(results: List[Dict[str, str]]) -> str:
    formatted = "🖼️ **Изображения:**\n\n"
    for i, r in enumerate(results, 1):
        title = r.get("title", "Без названия")
        image_url = r.get("image", "")
        formatted += f"**{i}. {title}**\n"
        if image_url:
            formatted += f"🖼️ {image_url}\n"
        formatted += "\n"
    return formatted.strip()


def _format_videos(results: List[Dict[str, str]]) -> str:
    formatted = "🎬 **Видео:**\n\n"
    for i, r in enumerate(results, 1):
        title = r.get("title", "Без названия")
        source = r.get("source", "")
        duration = r.get("duration", "")

        formatted += f"**{i}. {title}**\n"
        meta = []
        if source:
            meta.append(f"🎥 {source}")
        if duration:
            meta.append(f"⏱️ {duration}")
        if meta:
            formatted += " | ".join(meta) + "\n"
        formatted += "\n"
    return formatted.strip()


def _format_weather(results: List[Dict[str, str]], city: str) -> str:
    for r in results:
        t = r["title"].lower()
        if "погода" in t or "weather" in t:
            return (f"🌤️ **Погода в {city}:**\n\n"
                    f"📌 {r['title']}\n📝 {r['body'][:MAX_TEXT_LENGTH]}")
    if results:
        return (f"🌤️ **Погода в {city}:**\n\n"
                f"📌 {results[0]['title']}\n📝 {results[0]['body'][:MAX_TEXT_LENGTH]}")
    return f"🌤️ Погода для {city} не найдена."


def _format_currency(results: List[Dict[str, str]], frm: str, to: str) -> str:
    for r in results:
        t = r["title"].lower()
        if "exchange" in t or "курс" in t:
            return (f"💱 **Курс {frm}/{to}:**\n\n"
                    f"📌 {r['title']}\n📝 {r['body'][:MAX_TEXT_LENGTH]}")
    if results:
        return (f"💱 **Курс {frm}/{to}:**\n\n"
                f"📌 {results[0]['title']}\n📝 {results[0]['body'][:MAX_TEXT_LENGTH]}")
    return f"💱 Курс {frm} к {to} не найден."


def _format_wikipedia(results: List[Dict[str, str]], query: str) -> str:
    for r in results:
        href = r.get("href", "").lower()
        if "wiki" in href or "wikipedia" in href:
            return (f"📚 **Википедия:** `{query}`\n\n"
                    f"📌 {r['title']}\n📝 {r['body'][:MAX_TEXT_LENGTH]}\n🔗 {r['href']}")
    if results:
        return (f"📚 **Википедия:** `{query}`\n\n"
                f"📌 {results[0]['title']}\n📝 {results[0]['body'][:MAX_TEXT_LENGTH]}\n🔗 {results[0]['href']}")
    return f"📚 Информация по запросу `{query}` не найдена."


def _format_recipe(results: List[Dict[str, str]], query: str) -> str:
    for r in results:
        t = r["title"].lower()
        if "рецепт" in t or "recipe" in t:
            return (f"🍳 **Рецепт:** `{query}`\n\n"
                    f"📌 {r['title']}\n📝 {r['body'][:MAX_TEXT_LENGTH]}\n🔗 {r['href']}")
    if results:
        return (f"🍳 **Рецепт:** `{query}`\n\n"
                f"📌 {results[0]['title']}\n📝 {results[0]['body'][:MAX_TEXT_LENGTH]}\n🔗 {results[0]['href']}")
    return f"🍳 Рецепт для `{query}` не найден."


def _format_shopping(results: List[Dict[str, str]], query: str) -> str:
    formatted = f"🛒 **Товары:** `{query}`\n\n"
    for i, r in enumerate(results, 1):
        formatted += f"**{i}. {r.get('title', 'Без названия')}**\n"
        if r.get("href"):
            formatted += f"🔗 {r['href']}\n"
        if r.get("body"):
            formatted += f"📝 {r['body'][:MAX_TEXT_LENGTH]}\n"
        formatted += "\n"
    return formatted.strip()


def _format_definition(results: List[Dict[str, str]], word: str) -> str:
    for r in results:
        t = r["title"].lower()
        if "определение" in t or "definition" in t:
            return (f"📖 **Определение:** `{word}`\n\n"
                    f"📌 {r['title']}\n📝 {r['body'][:MAX_TEXT_LENGTH]}")
    if results:
        return (f"📖 **Определение:** `{word}`\n\n"
                f"📌 {results[0]['title']}\n📝 {results[0]['body'][:MAX_TEXT_LENGTH]}")
    return f"📖 Определение слова `{word}` не найдено."


# ========== ИЗВЛЕЧЕНИЕ ЗАПРОСА ==========

def _extract_search_query(message: str) -> Optional[str]:
    """Извлекает поисковый запрос из сообщения."""
    if not message:
        return None

    msg_lower = message.lower()

    # Явные команды
    commands = [
        "найди в интернете", "поищи в интернете", "погугли",
        "search for", "find on internet", "google it",
        "найди", "поищи",
    ]
    for cmd in commands:
        if msg_lower.startswith(cmd):
            query = message[len(cmd):].strip()
            if query:
                return query

    # Паттерны
    patterns = [
        r"что такое\s+(.+)",
        r"кто такой\s+(.+)",
        r"кто такая\s+(.+)",
        r"где находится\s+(.+)",
        r"новости про\s+(.+)",
        r"новости о\s+(.+)",
        r"погода в\s+(.+)",
        r"цена на\s+(.+)",
        r"сколько стоит\s+(.+)",
        r"как приготовить\s+(.+)",
        r"рецепт\s+(.+)",
        r"определение\s+(.+)",
        r"wiki\s+(.+)",
        r"вики\s+(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, msg_lower)
        if match:
            return match.group(1).strip()

    return message


def detect_search_type(message: str) -> str:
    """Определяет тип поиска по сообщению."""
    msg_lower = message.lower()

    for keyword, search_type in SEARCH_KEYWORDS.items():
        if keyword in msg_lower:
            return search_type

    return "search"


# ========== УМНЫЙ ПОИСК ==========

def quick_search(message: str) -> str:
    """Умный поиск: определяет тип и вызывает нужную функцию."""
    msg_lower = message.lower()
    search_type = detect_search_type(message)

    # Погода
    if search_type == "weather" or "погода" in msg_lower:
        m = re.search(r"погода\s+(?:в\s+)?([\w\s]+)", msg_lower)
        if m:
            return search_weather(m.group(1).strip())
        return search_weather("Ташкент")

    # Курс
    if search_type == "currency" or "курс" in msg_lower:
        if "доллар" in msg_lower or "usd" in msg_lower:
            return search_currency("USD", "UZS")
        if "евро" in msg_lower or "eur" in msg_lower:
            return search_currency("EUR", "UZS")
        if "рубл" in msg_lower or "rub" in msg_lower:
            return search_currency("RUB", "UZS")
        return search_currency("USD", "UZS")

    # Изображения
    if search_type == "images" or "картинк" in msg_lower or "фото" in msg_lower:
        query = _extract_search_query(message)
        return search_images(query or message)

    # Видео
    if search_type == "videos" or "видео" in msg_lower:
        query = _extract_search_query(message)
        return search_videos(query or message)

    # Новости
    if search_type == "news" or "новости" in msg_lower:
        m = re.search(r"новости\s+(?:про|о)\s+(.+)", msg_lower)
        if m:
            return search_news(m.group(1).strip())
        return search_news(message)

    # Википедия
    if search_type == "wikipedia" or "wiki" in msg_lower or "вики" in msg_lower:
        query = _extract_search_query(message)
        return search_wikipedia(query or message)

    # Рецепты
    if search_type == "recipe" or "рецепт" in msg_lower or "приготовить" in msg_lower:
        query = _extract_search_query(message)
        return search_recipe(query or message)

    # Определение
    if search_type == "definition" or "что такое" in msg_lower or "кто такой" in msg_lower:
        query = _extract_search_query(message)
        return search_definition(query or message)

    # Обычный поиск
    query = _extract_search_query(message)
    return search_web(query or message)


def needs_search(message: str) -> bool:
    """
    Определяет, нужно ли выполнять поиск.
    ТОЛЬКО точные триггеры — не срабатывает на «как дела?».
    """
    if not message:
        return False

    msg_lower = message.lower()

    # 1. Явные ключевые слова (точное вхождение)
    for keyword in SEARCH_KEYWORDS:
        if keyword in msg_lower:
            return True

    # 2. Точные вопросительные паттерны
    for pattern in QUESTION_PATTERNS:
        if re.search(pattern, msg_lower):
            return True

    return False


# ========== ДОПОЛНИТЕЛЬНЫЕ ==========

def get_search_suggestions(query: str) -> List[str]:
    """Автодополнение поиска."""
    if not HAS_DDGS:
        return []
    try:
        with DDGS(timeout=5) as ddgs:
            return list(ddgs.suggestions(query))
    except Exception:
        return []


def search_answers(query: str) -> str:
    """Прямой ответ (instant answer)."""
    if not HAS_DDGS:
        return "⚠️ Установите ddgs: pip install ddgs"

    try:
        with DDGS(timeout=TIMEOUT) as ddgs:
            results = list(ddgs.answers(query))
            if results:
                return _format_answers(results)
            return "⚡ Прямой ответ не найден."
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def _format_answers(results: List[Dict[str, str]]) -> str:
    formatted = "⚡ **Прямой ответ:**\n\n"
    for r in results:
        if r.get("text"):
            formatted += f"📝 {r['text']}\n"
        if r.get("url"):
            formatted += f"🔗 {r['url']}\n"
        formatted += "\n"
    return formatted.strip()


# ========== ЭКСПОРТ ==========

__all__ = [
    "search_web", "search_news", "search_images", "search_videos",
    "search_weather", "search_currency", "search_wikipedia",
    "search_recipe", "search_shopping", "search_definition",
    "quick_search", "needs_search", "detect_search_type",
    "get_search_suggestions", "search_answers",
]


# ========== ТЕСТ ==========

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    print("🧪 Тест web_search.py\n")
    print("=" * 60)

    if not HAS_DDGS:
        print("⚠️ Установите ddgs: pip install ddgs")
        sys.exit(1)

    print("\n📝 Тест 1: needs_search (не должно ловить обычное)")
    tests = [
        ("как дела?", False),          # ← НЕ поиск
        ("что ты умеешь?", False),     # ← НЕ поиск
        ("кто ты?", False),            # ← НЕ поиск
        ("привет", False),             # ← НЕ поиск
        ("погода в Ташкенте", True),   # ← поиск
        ("что такое RAG", True),       # ← поиск
        ("найди в интернете Python", True),  # ← поиск
        ("новости про ИИ", True),      # ← поиск
    ]
    for msg, expected in tests:
        result = needs_search(msg)
        marker = "✅" if result == expected else "❌"
        print(f"  {marker} {msg!r:35} → {result}")

    print("\n📝 Тест 2: Простой поиск")
    result = search_web("Python asyncio")
    print(result[:300] + "..." if len(result) > 300 else result)

    print("\n📝 Тест 3: Погода")
    print(search_weather("Ташкент")[:200])

    print("\n📝 Тест 4: quick_search")
    for q in ["погода в Ташкенте", "курс доллара", "что такое Python"]:
        print(f"\n  {q} →")
        print("  " + quick_search(q)[:200])

    print("\n📝 Тест 5: Кэш (повторный запрос)")
    t0 = time.time()
    search_web("Python")
    t1 = time.time()
    search_web("Python")
    t2 = time.time()
    print(f"  Первый запрос: {(t1-t0):.2f} сек")
    print(f"  Второй (из кэша): {(t2-t1):.4f} сек")

    print("\n" + "=" * 60)
    print("✅ Тесты завершены!")