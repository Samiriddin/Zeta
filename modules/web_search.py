# -*- coding: utf-8 -*-
"""
Максимально расширенный модуль для поиска в интернете.
Поддерживает: текстовый поиск, новости, изображения, видео, погоду, курсы валют,
перевод, определение, калькулятор, википедию, карты, товары, рецепты, словари.
Резервный поиск через Google.
"""

import warnings
import re
import json
import time
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

warnings.filterwarnings("ignore", message="This package.*has been renamed")

# ========== ПРОВЕРКА БИБЛИОТЕК ==========
try:
    # Новая версия библиотеки
    from ddgs import DDGS
    HAS_DDGS = True
except ImportError:
    try:
        # Старая версия (резерв)
        from duckduckgo_search import DDGS
        HAS_DDGS = True
    except ImportError:
        HAS_DDGS = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


# ========== КОНСТАНТЫ ==========

MAX_RESULTS = 3
MAX_NEWS_RESULTS = 5
MAX_IMAGES_RESULTS = 5
MAX_VIDEOS_RESULTS = 5
TIMEOUT = 20
MAX_TEXT_LENGTH = 500
CACHE_TTL = 300  # 5 минут

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

# Ключевые слова для определения необходимости поиска
SEARCH_KEYWORDS = {
    # Русские
    "найди": "search",
    "поищи": "search",
    "погугли": "search",
    "что такое": "definition",
    "кто такой": "definition",
    "что значит": "definition",
    "когда": "search",
    "где находится": "location",
    "где": "search",
    "новости": "news",
    "погода": "weather",
    "курс": "currency",
    "сколько стоит": "price",
    "цена на": "price",
    "переведи": "translate",
    "как переводится": "translate",
    "рецепт": "recipe",
    "как приготовить": "recipe",
    "вики": "wikipedia",
    "определение": "definition",
    "словарь": "dictionary",
    "карта": "map",
    "маршрут": "map",
    "как добраться": "map",
    "товары": "shopping",
    "купить": "shopping",
    "отзывы": "reviews",
    "оценка": "reviews",
    
    # Английские
    "search for": "search",
    "find": "search",
    "what is": "definition",
    "who is": "definition",
    "news": "news",
    "weather": "weather",
    "price": "price",
    "translate": "translate",
    "recipe": "recipe",
    "wiki": "wikipedia",
    "map": "map",
    "shopping": "shopping",
    "reviews": "reviews",
}


# ========== КЭШ ==========

_search_cache: Dict[str, Tuple[str, float]] = {}


def _get_cached(key: str) -> Optional[str]:
    """Возвращает кэшированный результат."""
    if key in _search_cache:
        result, timestamp = _search_cache[key]
        if time.time() - timestamp < CACHE_TTL:
            return result
    return None


def _set_cache(key: str, value: str) -> None:
    """Сохраняет результат в кэш."""
    _search_cache[key] = (value, time.time())


# ========== ПОИСК ЧЕРЕЗ GOOGLE (РЕЗЕРВ) ==========

def search_google(query: str, max_results: int = MAX_RESULTS) -> List[Dict[str, str]]:
    """Поиск через Google (парсинг HTML). Используется как резерв."""
    if not HAS_REQUESTS or not HAS_BS4:
        return []
    
    try:
        url = f"https://www.google.com/search?q={query}&hl=ru"
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            return []
        
        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        for g in soup.find_all("div", class_="g")[:max_results]:
            title = g.find("h3")
            link = g.find("a")
            snippet = g.find("span", class_="aCOpRe")
            if title and link:
                results.append({
                    "title": title.text.strip(),
                    "url": link.get("href", ""),
                    "body": snippet.text.strip() if snippet else ""
                })
        return results
    except Exception:
        return []


# ========== ОСНОВНЫЕ ФУНКЦИИ ==========

def search_web(query: str, max_results: int = MAX_RESULTS, timeout: int = TIMEOUT) -> str:
    """Выполняет поиск в интернете через DuckDuckGo или Google (резерв)."""
    if not query or not query.strip():
        return "⚠️ Укажите поисковый запрос."

    cache_key = f"web_{query.lower()}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    results = []
    
    # Пробуем DuckDuckGo
    if HAS_DDGS:
        try:
            with DDGS(timeout=timeout) as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
        except Exception as e:
            print(f"🔍 Ошибка DuckDuckGo: {e}")
            results = []
    
    # Если DuckDuckGo пуст — пробуем Google
    if not results:
        results = search_google(query, max_results)
    
    if results:
        result = _format_results(results, query)
        _set_cache(cache_key, result)
        return result
    
    return f"🔍 По запросу `{query}` ничего не найдено."


def search_news(query: str, max_results: int = MAX_NEWS_RESULTS) -> str:
    """Ищет новости по запросу."""
    if not HAS_DDGS:
        return "⚠️ Установите duckduckgo-search: pip install duckduckgo-search"
    
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
                _set_cache(cache_key, result)
                return result
            return f"📰 Новостей по запросу `{query}` не найдено."
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def search_images(query: str, max_results: int = MAX_IMAGES_RESULTS) -> str:
    """Ищет изображения по запросу."""
    if not HAS_DDGS:
        return "⚠️ Установите duckduckgo-search: pip install duckduckgo-search"

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
    """Ищет видео по запросу."""
    if not HAS_DDGS:
        return "⚠️ Установите duckduckgo-search: pip install duckduckgo-search"

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
    """Ищет погоду в городе."""
    if not HAS_DDGS:
        return "⚠️ Установите duckduckgo-search: pip install duckduckgo-search"

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
                _set_cache(cache_key, result)
                return result
            return f"🌤️ Не удалось найти погоду для {city}."
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def search_currency(from_currency: str = "USD", to_currency: str = "UZS") -> str:
    """Ищет курс валют."""
    if not HAS_DDGS:
        return "⚠️ Установите duckduckgo-search: pip install duckduckgo-search"

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
                _set_cache(cache_key, result)
                return result
            return f"💱 Не удалось найти курс {from_currency} к {to_currency}."
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def search_wikipedia(query: str) -> str:
    """Ищет информацию в Википедии."""
    if not HAS_DDGS:
        return "⚠️ Установите duckduckgo-search: pip install duckduckgo-search"

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
                _set_cache(cache_key, result)
                return result
            return f"📚 Информация по запросу `{query}` не найдена."
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def search_recipe(query: str) -> str:
    """Ищет рецепты."""
    if not HAS_DDGS:
        return "⚠️ Установите duckduckgo-search: pip install duckduckgo-search"

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
                _set_cache(cache_key, result)
                return result
            return f"🍳 Рецепт для `{query}` не найден."
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def search_shopping(query: str) -> str:
    """Ищет товары."""
    if not HAS_DDGS:
        return "⚠️ Установите duckduckgo-search: pip install duckduckgo-search"

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
                _set_cache(cache_key, result)
                return result
            return f"🛒 Товары по запросу `{query}` не найдены."
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def search_definition(word: str) -> str:
    """Ищет определение слова."""
    if not HAS_DDGS:
        return "⚠️ Установите duckduckgo-search: pip install duckduckgo-search"

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
                _set_cache(cache_key, result)
                return result
            return f"📖 Определение слова `{word}` не найдено."
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

def _format_results(results: List[Dict[str, str]], query: str) -> str:
    """Форматирует результаты поиска."""
    formatted = f"🔍 **Результаты поиска:** `{query}`\n\n"
    for i, r in enumerate(results, 1):
        title = r.get('title', 'Без заголовка')
        body = r.get('body', '')[:MAX_TEXT_LENGTH]
        if len(r.get('body', '')) > MAX_TEXT_LENGTH:
            body += "..."
        href = r.get('href', '')
        
        formatted += f"**{i}. {title}**\n"
        if href:
            formatted += f"🔗 {href}\n"
        if body:
            formatted += f"📝 {body}\n"
        formatted += "\n"
    
    return formatted.strip()


def _format_news(results: List[Dict[str, str]]) -> str:
    """Форматирует результаты новостей."""
    formatted = "📰 **Новости:**\n\n"
    for i, r in enumerate(results, 1):
        title = r.get('title', 'Без заголовка')
        body = r.get('body', '')[:MAX_TEXT_LENGTH]
        source = r.get('source', '')
        date = r.get('date', '')
        
        formatted += f"**{i}. {title}**\n"
        if source:
            formatted += f"📰 {source}"
        if date:
            formatted += f" | 📅 {date}"
        formatted += "\n"
        if body:
            formatted += f"📝 {body}\n"
        formatted += "\n"
    
    return formatted.strip()


def _format_images(results: List[Dict[str, str]]) -> str:
    """Форматирует результаты изображений."""
    formatted = "🖼️ **Изображения:**\n\n"
    for i, r in enumerate(results, 1):
        title = r.get('title', 'Без названия')
        image_url = r.get('image', '')
        thumbnail = r.get('thumbnail', '')
        
        formatted += f"**{i}. {title}**\n"
        if image_url:
            formatted += f"🖼️ {image_url}\n"
        formatted += "\n"
    
    return formatted.strip()


def _format_videos(results: List[Dict[str, str]]) -> str:
    """Форматирует результаты видео."""
    formatted = "🎬 **Видео:**\n\n"
    for i, r in enumerate(results, 1):
        title = r.get('title', 'Без названия')
        source = r.get('source', '')
        duration = r.get('duration', '')
        
        formatted += f"**{i}. {title}**\n"
        if source:
            formatted += f"🎥 {source}"
        if duration:
            formatted += f" | ⏱️ {duration}"
        formatted += "\n"
        formatted += "\n"
    
    return formatted.strip()


def _format_weather(results: List[Dict[str, str]], city: str) -> str:
    """Форматирует погоду."""
    for r in results:
        if "погода" in r['title'].lower() or "weather" in r['title'].lower():
            title = r['title']
            body = r['body'][:MAX_TEXT_LENGTH]
            return f"🌤️ **Погода в {city}:**\n\n📌 {title}\n📝 {body}"
    
    if results:
        return f"🌤️ **Погода в {city}:**\n\n📌 {results[0]['title']}\n📝 {results[0]['body'][:MAX_TEXT_LENGTH]}"
    
    return f"🌤️ Погода для {city} не найдена."


def _format_currency(results: List[Dict[str, str]], from_curr: str, to_curr: str) -> str:
    """Форматирует курс валют."""
    for r in results:
        if "exchange" in r['title'].lower() or "курс" in r['title'].lower():
            return f"💱 **Курс {from_curr}/{to_curr}:**\n\n📌 {r['title']}\n📝 {r['body'][:MAX_TEXT_LENGTH]}"
    
    if results:
        return f"💱 **Курс {from_curr}/{to_curr}:**\n\n📌 {results[0]['title']}\n📝 {results[0]['body'][:MAX_TEXT_LENGTH]}"
    
    return f"💱 Курс {from_curr} к {to_curr} не найден."


def _format_wikipedia(results: List[Dict[str, str]], query: str) -> str:
    """Форматирует Википедию."""
    for r in results:
        if "wiki" in r['href'].lower() or "wikipedia" in r['href'].lower():
            return f"📚 **Википедия:** `{query}`\n\n📌 {r['title']}\n📝 {r['body'][:MAX_TEXT_LENGTH]}\n🔗 {r['href']}"
    
    if results:
        return f"📚 **Википедия:** `{query}`\n\n📌 {results[0]['title']}\n📝 {results[0]['body'][:MAX_TEXT_LENGTH]}\n🔗 {results[0]['href']}"
    
    return f"📚 Информация по запросу `{query}` не найдена."


def _format_recipe(results: List[Dict[str, str]], query: str) -> str:
    """Форматирует рецепт."""
    for r in results:
        if "рецепт" in r['title'].lower() or "recipe" in r['title'].lower():
            return f"🍳 **Рецепт:** `{query}`\n\n📌 {r['title']}\n📝 {r['body'][:MAX_TEXT_LENGTH]}\n🔗 {r['href']}"
    
    if results:
        return f"🍳 **Рецепт:** `{query}`\n\n📌 {results[0]['title']}\n📝 {results[0]['body'][:MAX_TEXT_LENGTH]}\n🔗 {results[0]['href']}"
    
    return f"🍳 Рецепт для `{query}` не найден."


def _format_shopping(results: List[Dict[str, str]], query: str) -> str:
    """Форматирует товары."""
    formatted = f"🛒 **Товары:** `{query}`\n\n"
    for i, r in enumerate(results, 1):
        title = r.get('title', 'Без названия')
        body = r.get('body', '')[:MAX_TEXT_LENGTH]
        href = r.get('href', '')
        
        formatted += f"**{i}. {title}**\n"
        if href:
            formatted += f"🔗 {href}\n"
        if body:
            formatted += f"📝 {body}\n"
        formatted += "\n"
    
    return formatted.strip()


def _format_definition(results: List[Dict[str, str]], word: str) -> str:
    """Форматирует определение."""
    for r in results:
        if "определение" in r['title'].lower() or "definition" in r['title'].lower():
            return f"📖 **Определение:** `{word}`\n\n📌 {r['title']}\n📝 {r['body'][:MAX_TEXT_LENGTH]}"
    
    if results:
        return f"📖 **Определение:** `{word}`\n\n📌 {results[0]['title']}\n📝 {results[0]['body'][:MAX_TEXT_LENGTH]}"
    
    return f"📖 Определение слова `{word}` не найдено."


def _extract_search_query(message: str) -> Optional[str]:
    """Извлекает поисковый запрос из сообщения."""
    if not message:
        return None
    
    msg_lower = message.lower()
    
    commands = [
        "найди в интернете", "поищи в интернете", "погугли",
        "search for", "find on internet", "google it",
        "найди", "поищи"
    ]
    for cmd in commands:
        if msg_lower.startswith(cmd):
            query = message[len(cmd):].strip()
            if query:
                return query
            break
    
    patterns = [
        r"что такое\s+(.+)",
        r"кто такой\s+(.+)",
        r"где находится\s+(.+)",
        r"новости про\s+(.+)",
        r"погода в\s+(.+)",
        r"цена на\s+(.+)",
        r"сколько стоит\s+(.+)",
        r"как приготовить\s+(.+)",
        r"рецепт\s+(.+)",
        r"определение\s+(.+)",
        r"wiki\s+(.+)",
        r"вики\s+(.+)",
        r"курс\s+(\w+)\s+к\s+(\w+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, msg_lower)
        if match:
            if len(match.groups()) == 2:
                return f"{match.group(1)} {match.group(2)}"
            return match.group(1).strip()
    
    return message


def detect_search_type(message: str) -> str:
    """Определяет тип поиска по сообщению."""
    msg_lower = message.lower()
    
    for keyword, search_type in SEARCH_KEYWORDS.items():
        if keyword in msg_lower:
            return search_type
    
    return "search"


# ========== ОСНОВНЫЕ ФУНКЦИИ ДЛЯ ИНТЕГРАЦИИ ==========

def quick_search(message: str) -> str:
    """Умный поиск: определяет тип запроса и выбирает подходящий метод."""
    msg_lower = message.lower()
    search_type = detect_search_type(message)
    
    # Погода
    if search_type == "weather" or "погода" in msg_lower:
        import re
        city_match = re.search(r"погода\s+в\s+([\w\s]+)", msg_lower)
        city_match2 = re.search(r"погода\s+([\w\s]+)", msg_lower)
        if city_match:
            return search_weather(city_match.group(1).strip())
        if city_match2:
            return search_weather(city_match2.group(1).strip())
        return search_weather("Ташкент")
    
    # Курс валют
    if search_type == "currency" or "курс" in msg_lower or "доллар" in msg_lower:
        if "доллар" in msg_lower or "usd" in msg_lower:
            return search_currency("USD", "UZS")
        if "евро" in msg_lower or "eur" in msg_lower:
            return search_currency("EUR", "UZS")
        if "рубль" in msg_lower or "rub" in msg_lower:
            return search_currency("RUB", "UZS")
        return search_currency("USD", "UZS")
    
    # Новости
    if search_type == "news" or "новости" in msg_lower:
        import re
        news_match = re.search(r"новости\s+(?:про|о)\s+(.+)", msg_lower)
        if news_match:
            return search_news(news_match.group(1).strip())
        return search_news(message)
    
    # Википедия
    if search_type == "wikipedia" or "wiki" in msg_lower or "вики" in msg_lower:
        query = _extract_search_query(message)
        if query:
            return search_wikipedia(query)
        return search_wikipedia(message)
    
    # Рецепты
    if search_type == "recipe" or "рецепт" in msg_lower or "приготовить" in msg_lower:
        query = _extract_search_query(message)
        if query:
            return search_recipe(query)
        return search_recipe(message)
    
    # Определение
    if search_type == "definition" or "что такое" in msg_lower or "кто такой" in msg_lower:
        query = _extract_search_query(message)
        if query:
            return search_definition(query)
        return search_definition(message)
    
    # Обычный поиск
    query = _extract_search_query(message)
    if query:
        return search_web(query)
    
    return search_web(message)


def needs_search(message: str) -> bool:
    """Определяет, нужно ли выполнять поиск для данного сообщения."""
    if not message:
        return False
    
    msg_lower = message.lower()
    
    # Проверка на явные команды
    for keyword in SEARCH_KEYWORDS:
        if keyword in msg_lower:
            return True
    
    # Проверка на вопросительные слова
    question_words = ["что", "кто", "где", "когда", "почему", "зачем", "как", "сколько"]
    if any(word in msg_lower for word in question_words) and "?" in message:
        return True
    
    return False


# ========== ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ ==========

def get_search_suggestions(query: str) -> List[str]:
    """Получает предложения поиска (автодополнение)."""
    if not HAS_DDGS:
        return []
    
    try:
        with DDGS(timeout=5) as ddgs:
            return list(ddgs.suggestions(query))
    except Exception:
        return []


def search_answers(query: str) -> str:
    """Ищет прямой ответ (instant answer)."""
    if not HAS_DDGS:
        return "⚠️ Установите duckduckgo-search: pip install duckduckgo-search"
    
    try:
        with DDGS(timeout=TIMEOUT) as ddgs:
            results = list(ddgs.answers(query))
            if results:
                return _format_answers(results)
            return "⚡ Прямой ответ не найден."
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def _format_answers(results: List[Dict[str, str]]) -> str:
    """Форматирует прямой ответ."""
    formatted = "⚡ **Прямой ответ:**\n\n"
    for r in results:
        if r.get('text'):
            formatted += f"📝 {r['text']}\n"
        if r.get('url'):
            formatted += f"🔗 {r['url']}\n"
        formatted += "\n"
    return formatted.strip()


# ========== ЭКСПОРТ ==========

__all__ = [
    'search_web', 'search_news', 'search_images', 'search_videos',
    'search_weather', 'search_currency', 'search_wikipedia',
    'search_recipe', 'search_shopping', 'search_definition',
    'quick_search', 'needs_search', 'detect_search_type',
    'get_search_suggestions', 'search_answers', 'search_google',
]


# ========== ТЕСТ ==========
if __name__ == "__main__":
    import time
    
    print("🧪 Тест web_search.py\n")
    
    if not HAS_DDGS:
        print("⚠️ Установите duckduckgo-search: pip install duckduckgo-search")
    else:
        print("📝 Тест 1: Поиск")
        result = search_web("Zeta ИИ ассистент")
        print(result[:300] + "..." if len(result) > 300 else result)
        print("-" * 40)
        
        print("📝 Тест 2: Погода")
        result = search_weather("Ташкент")
        print(result)
        print("-" * 40)
        
        print("📝 Тест 3: Курс валют")
        result = search_currency("USD", "UZS")
        print(result)
        print("-" * 40)
        
        print("📝 Тест 4: quick_search")
        tests = [
            "погода в Ташкенте",
            "курс доллара",
            "кто такой Samriddin",
            "новости про ИИ",
            "рецепт плова",
        ]
        for t in tests:
            print(f"\n{t} →")
            result = quick_search(t)
            print(result[:200] + "..." if len(result) > 200 else result)
        print("-" * 40)
        
        print("📝 Тест 5: needs_search")
        tests = [
            "погода в Ташкенте",
            "кто такой Samriddin",
            "привет как дела",
            "что такое RAG",
        ]
        for t in tests:
            print(f"{t} → {needs_search(t)}")
        print("-" * 40)
        
        print("📝 Тест 6: Википедия")
        result = search_wikipedia("Искусственный интеллект")
        print(result[:300] + "..." if len(result) > 300 else result)
        print("-" * 40)
        
        print("\n✅ Тесты завершены!")