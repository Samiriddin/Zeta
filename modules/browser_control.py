# -*- coding: utf-8 -*-
"""
Модуль управления браузером Zeta.
Полная работа с браузером: открытие сайтов, поиск, вкладки, навигация, закладки.

Возможности:
    - Автопоиск установленных браузеров (Edge, Chrome, Firefox, Yandex, Opera, Brave)
    - Выбор браузера через чат (если несколько установлено)
    - Открытие 100+ сайтов по имени (RU/EN/UZ)
    - Поиск в Google/YouTube/Яндекс/Bing/DuckDuckGo
    - Управление вкладками (новая, закрыть, переключение, вернуть)
    - Навигация (назад, вперёд, обновить, домой, стоп)
    - Закладки (data/browser_bookmarks.json)
    - Работа с окнами браузера (фокус, список)

ИСПРАВЛЕНО (2026-09-21):
    - Полностью новый модуль
    - 100+ сайтов, 5 поисковиков
    - Выбор браузера через чат (PENDING-паттерн как в power)
    - Система закладок
    - Работа с окнами через pygetwindow
    - Открытие в конкретном браузере (не только дефолтном)
"""

import os
import re
import json
import time
import logging
import webbrowser
import subprocess
import threading
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

# === ОПЦИОНАЛЬНЫЕ ЗАВИСИМОСТИ ===
try:
    import pyautogui
    pyautogui.FAILSAFE = False   # отключаем "угол = выход"
    pyautogui.PAUSE = 0.05
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False
    pyautogui = None

try:
    import pygetwindow as gw
    HAS_PYGETWINDOW = True
except ImportError:
    HAS_PYGETWINDOW = False
    gw = None


# ========== ЛОГИРОВАНИЕ ==========

def _log(msg: str) -> None:
    logging.info(f"[BROWSER] {msg}")


def _log_warn(msg: str) -> None:
    logging.warning(f"[BROWSER] {msg}")


# ========== КОНСТАНТЫ ==========

BOOKMARKS_FILE = "data/browser_bookmarks.json"
PREFERENCE_FILE = "data/browser_preference.json"

# Названия браузеров (для отображения)
BROWSER_DISPLAY = {
    "edge": "Microsoft Edge",
    "chrome": "Google Chrome",
    "firefox": "Mozilla Firefox",
    "yandex": "Яндекс.Браузер",
    "opera": "Opera",
    "brave": "Brave",
}

# Пути к браузерам (Windows)
BROWSER_PATHS = {
    "edge": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ],
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
    ],
    "firefox": [
        r"C:\Program Files\Mozilla Firefox\firefox.exe",
        r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
    ],
    "yandex": [
        os.path.expanduser(r"~\AppData\Local\Yandex\YandexBrowser\Application\browser.exe"),
        r"C:\Program Files\Yandex\YandexBrowser\Application\browser.exe",
    ],
    "opera": [
        os.path.expanduser(r"~\AppData\Local\Programs\Opera\launcher.exe"),
        r"C:\Program Files\Opera\launcher.exe",
    ],
    "brave": [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
        os.path.expanduser(r"~\AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe"),
    ],
}

# Заголовки окон (для pygetwindow)
BROWSER_TITLES = {
    "edge": ["Microsoft Edge", "Edge"],
    "chrome": ["Google Chrome", "Chrome"],
    "firefox": ["Mozilla Firefox", "Firefox"],
    "yandex": ["Яндекс", "Yandex"],
    "opera": ["Opera"],
    "brave": ["Brave"],
}


# ========== СЛОВАРЬ САЙТОВ (100+) ==========

SITES: Dict[str, str] = {
    # === ГЛОБАЛЬНЫЕ ===
    "youtube": "https://youtube.com",
    "ютуб": "https://youtube.com",
    "you tube": "https://youtube.com",
    "google": "https://google.com",
    "гугл": "https://google.com",
    "gmail": "https://mail.google.com",
    "джимейл": "https://mail.google.com",
    "почта гугл": "https://mail.google.com",
    "github": "https://github.com",
    "гитхаб": "https://github.com",
    "gitlab": "https://gitlab.com",
    "гитлаб": "https://gitlab.com",
    "stackoverflow": "https://stackoverflow.com",
    "stack overflow": "https://stackoverflow.com",
    "стаковерфлоу": "https://stackoverflow.com",
    "wikipedia": "https://ru.wikipedia.org",
    "википедия": "https://ru.wikipedia.org",
    "wiki": "https://ru.wikipedia.org",
    "reddit": "https://reddit.com",
    "реддит": "https://reddit.com",
    "twitter": "https://twitter.com",
    "твиттер": "https://twitter.com",
    "x": "https://x.com",
    "x.com": "https://x.com",
    "facebook": "https://facebook.com",
    "фейсбук": "https://facebook.com",
    "instagram": "https://instagram.com",
    "инстаграм": "https://instagram.com",
    "инста": "https://instagram.com",
    "linkedin": "https://linkedin.com",
    "линкедин": "https://linkedin.com",
    "tiktok": "https://tiktok.com",
    "тикток": "https://tiktok.com",
    "pinterest": "https://pinterest.com",
    "пинтерест": "https://pinterest.com",
    "twitch": "https://twitch.tv",
    "твич": "https://twitch.tv",
    "spotify": "https://open.spotify.com",
    "спотифай": "https://open.spotify.com",
    "netflix": "https://netflix.com",
    "нетфликс": "https://netflix.com",
    "amazon": "https://amazon.com",
    "амазон": "https://amazon.com",
    "ebay": "https://ebay.com",
    "paypal": "https://paypal.com",
    "пейпал": "https://paypal.com",
    "chatgpt": "https://chat.openai.com",
    "чатгпт": "https://chat.openai.com",
    "openai": "https://openai.com",
    "claude": "https://claude.ai",
    "клод": "https://claude.ai",
    "gemini": "https://gemini.google.com",
    "gemini google": "https://gemini.google.com",
    "huggingface": "https://huggingface.co",
    "хаггингфейс": "https://huggingface.co",
    "ollama": "https://ollama.ai",
    "оллама": "https://ollama.ai",

    # === РУССКИЕ ===
    "яндекс": "https://yandex.ru",
    "yandex": "https://yandex.ru",
    "yandex mail": "https://mail.yandex.ru",
    "яндекс почта": "https://mail.yandex.ru",
    "вк": "https://vk.com",
    "vk": "https://vk.com",
    "вконтакте": "https://vk.com",
    "вк видео": "https://vk.com/video",
    "vk video": "https://vk.com/video",
    "одноклассники": "https://ok.ru",
    "ок": "https://ok.ru",
    "ok": "https://ok.ru",
    "телеграм": "https://web.telegram.org",
    "telegram": "https://web.telegram.org",
    "тг веб": "https://web.telegram.org",
    "whatsapp": "https://web.whatsapp.com",
    "ватсап": "https://web.whatsapp.com",
    "хабр": "https://habr.com",
    "habr": "https://habr.com",
    "pikabu": "https://pikabu.ru",
    "пикабу": "https://pikabu.ru",
    "кинопоиск": "https://kinopoisk.ru",
    "kinopoisk": "https://kinopoisk.ru",
    "ivi": "https://ivi.ru",
    "иви": "https://ivi.ru",
    "mail.ru": "https://mail.ru",
    "мейл ру": "https://mail.ru",
    "рутрекер": "https://rutracker.org",
    "rutracker": "https://rutracker.org",
    "кп": "https://www.kp.ru",
    "rutube": "https://rutube.ru",
    "рутуб": "https://rutube.ru",
    "boosty": "https://boosty.to",
    "бусти": "https://boosty.to",
    "steam": "https://store.steampowered.com",
    "стим": "https://store.steampowered.com",
    "steam community": "https://steamcommunity.com",
    "steam store": "https://store.steampowered.com",
    "стим магазин": "https://store.steampowered.com",

    # === МАГАЗИНЫ ===
    "ozon": "https://ozon.ru",
    "озон": "https://ozon.ru",
    "wildberries": "https://wildberries.ru",
    "вайлдберриз": "https://wildberries.ru",
    "вб": "https://wildberries.ru",
    "avito": "https://avito.ru",
    "авито": "https://avito.ru",
    "aliexpress": "https://aliexpress.ru",
    "алиэкспресс": "https://aliexpress.ru",
    "али": "https://aliexpress.ru",
    "yandex market": "https://market.yandex.ru",
    "яндекс маркет": "https://market.yandex.ru",
    "dns": "https://dns-shop.ru",
    "днс": "https://dns-shop.ru",
    "mvideo": "https://mvideo.ru",
    "мвидео": "https://mvideo.ru",
    "eldorado": "https://eldorado.ru",
    "эльдорадо": "https://eldorado.ru",

    # === УЗБЕКСКИЕ ===
    "kun.uz": "https://kun.uz",
    "кун уз": "https://kun.uz",
    "gazeta.uz": "https://gazeta.uz",
    "газета уз": "https://gazeta.uz",
    "daryo.uz": "https://daryo.uz",
    "дарио уз": "https://daryo.uz",
    "uzum": "https://uzum.uz",
    "узум": "https://uzum.uz",
    "uzum market": "https://uzum.uz",
    "sello": "https://sello.uz",
    "селло": "https://sello.uz",
    "olx uz": "https://olx.uz",
    "олх уз": "https://olx.uz",
    "click": "https://click.uz",
    "клик": "https://click.uz",
    "payme": "https://payme.uz",
    "пейми": "https://payme.uz",
    "uzcard": "https://uzcard.uz",
    "узкард": "https://uzcard.uz",
    "beeline uz": "https://beeline.uz",
    "билайн уз": "https://beeline.uz",
    "ucell": "https://ucell.uz",
    "юселл": "https://ucell.uz",
    "ums": "https://ums.uz",
    "it park": "https://it-park.uz",
    "ит парк": "https://it-park.uz",
    "uzbekistan airways": "https://uzairways.com",
    "учкуч": "https://uzairways.com",

    # === DEV-РЕСУРСЫ ===
    "python.org": "https://python.org",
    "питон": "https://python.org",
    "pypi": "https://pypi.org",
    "pip": "https://pypi.org",
    "npm": "https://npmjs.com",
    "docker hub": "https://hub.docker.com",
    "docker": "https://docker.com",
    "докер": "https://docker.com",
    "mongodb": "https://mongodb.com",
    "postgresql": "https://postgresql.org",
    "постгрес": "https://postgresql.org",
    "mysql": "https://mysql.com",
    "codewars": "https://codewars.com",
    "кодварс": "https://codewars.com",
    "leetcode": "https://leetcode.com",
    "литкод": "https://leetcode.com",
    "w3schools": "https://w3schools.com",
    "py docs": "https://docs.python.org/3/",
    "mdn": "https://developer.mozilla.org",
}


# ========== ПОИСКОВИКИ ==========

SEARCH_ENGINES: Dict[str, str] = {
    "google": "https://www.google.com/search?q={}",
    "гугл": "https://www.google.com/search?q={}",
    "youtube": "https://www.youtube.com/results?search_query={}",
    "ютуб": "https://www.youtube.com/results?search_query={}",
    "yandex": "https://yandex.ru/search/?text={}",
    "яндекс": "https://yandex.ru/search/?text={}",
    "bing": "https://www.bing.com/search?q={}",
    "бинг": "https://www.bing.com/search?q={}",
    "duckduckgo": "https://duckduckgo.com/?q={}",
    "дак": "https://duckduckgo.com/?q={}",
    "wikipedia": "https://ru.wikipedia.org/wiki/{}",
    "вики": "https://ru.wikipedia.org/wiki/{}",
}


# ================================================================
#  PENDING ВЫБОР БРАУЗЕРА
# ================================================================

# Если браузеров несколько — ждём выбора пользователя
PENDING_BROWSER_CHOICE: Optional[Dict[str, Any]] = None


def _save_pending(data: Dict[str, Any]) -> None:
    """Сохраняет отложенный выбор браузера."""
    global PENDING_BROWSER_CHOICE
    PENDING_BROWSER_CHOICE = data


def _clear_pending() -> None:
    """Очищает отложенный выбор."""
    global PENDING_BROWSER_CHOICE
    PENDING_BROWSER_CHOICE = None


def has_pending_browser_choice() -> bool:
    """Есть ли отложенный выбор браузера?"""
    return PENDING_BROWSER_CHOICE is not None


# ================================================================
#  ОСНОВНОЙ КЛАСС
# ================================================================

class BrowserController:
    """Контроллер браузера Zeta."""

    def __init__(self):
        self._preferred_browser: Optional[str] = None
        self._browsers_cache: Optional[Dict[str, str]] = None
        self._bookmarks: Optional[Dict[str, str]] = None
        self._ensure_dirs()

    # ============================================================
    #  ВСПОМОГАТЕЛЬНОЕ
    # ============================================================

    def _ensure_dirs(self) -> None:
        os.makedirs("data", exist_ok=True)

    # ============================================================
    #  ПОИСК БРАУЗЕРОВ
    # ============================================================

    def detect_browsers(self, force: bool = False) -> Dict[str, str]:
        """
        Находит все установленные браузеры.
        Возвращает {код: путь}: {"edge": "C:\\...\\msedge.exe", ...}
        """
        if self._browsers_cache is not None and not force:
            return self._browsers_cache

        found = {}
        for code, paths in BROWSER_PATHS.items():
            for path in paths:
                if os.path.exists(path):
                    found[code] = path
                    break

        self._browsers_cache = found
        _log(f"Найдено браузеров: {list(found.keys())}")
        return found

    # ============================================================
    #  ВЫБОР БРАУЗЕРА (сохранение)
    # ============================================================

    def get_preferred_browser(self) -> Optional[str]:
        """Возвращает сохранённый браузер или None."""
        if self._preferred_browser:
            return self._preferred_browser

        if os.path.exists(PREFERENCE_FILE):
            try:
                with open(PREFERENCE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                browser = data.get("browser")
                if browser and browser in BROWSER_PATHS:
                    self._preferred_browser = browser
                    return browser
            except Exception:
                pass
        return None

    def set_preferred_browser(self, code: str) -> bool:
        """Сохраняет выбор браузера."""
        if code not in BROWSER_PATHS:
            return False
        try:
            with open(PREFERENCE_FILE, "w", encoding="utf-8") as f:
                json.dump({"browser": code, "saved_at": datetime.now().isoformat()}, f)
            self._preferred_browser = code
            _log(f"Браузер по умолчанию: {code}")
            return True
        except Exception as e:
            _log_warn(f"Не удалось сохранить выбор: {e}")
            return False

    def clear_preferred_browser(self) -> None:
        """Сбрасывает выбор."""
        self._preferred_browser = None
        try:
            if os.path.exists(PREFERENCE_FILE):
                os.remove(PREFERENCE_FILE)
        except Exception:
            pass

    def _need_browser_choice(self) -> bool:
        """
        Возвращает True, если надо спросить у пользователя.
        False — если браузер уже выбран ИЛИ он один.
        """
        browsers = self.detect_browsers()
        if len(browsers) <= 1:
            return False
        return self.get_preferred_browser() is None

    # ============================================================
    #  ОТКРЫТИЕ
    # ============================================================

    def open_url(self, url: str, browser: Optional[str] = None,
                 new_window: bool = False) -> bool:
        """
        Открывает URL.
        browser — код ("edge", "chrome", ...). Если None — preferred или дефолтный.
        """
        if not url:
            return False

        # Если URL не начинается с http — добавляем
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        # Если браузер не указан — берём сохранённый или первый найденный
        if browser is None:
            browser = self.get_preferred_browser()

        if browser:
            path = self.detect_browsers().get(browser)
            if path:
                try:
                    args = [path]
                    if new_window:
                        args.append("--new-window")
                    args.append(url)
                    subprocess.Popen(args, shell=False)
                    _log(f"Открыт {url} в {browser}")
                    return True
                except Exception as e:
                    _log_warn(f"Не удалось открыть {browser}: {e}")

        # Fallback — системный дефолт
        try:
            webbrowser.open(url)
            _log(f"Открыт {url} в дефолтном браузере")
            return True
        except Exception as e:
            _log_warn(f"Не удалось открыть URL: {e}")
            return False

    def open_site(self, name: str, browser: Optional[str] = None) -> str:
        """
        Открывает сайт по имени.
        Возвращает текст ответа для чата.
        """
        if not name or not name.strip():
            return "⚠️ Не поняла, какой сайт открыть."

        # Нормализация
        key = name.strip().lower()

        # Ищем в словаре
        url = SITES.get(key)

        # Если нет — пробуем как URL
        if not url:
            if re.match(r"^[\w\-]+\.\w+", key):
                url = key
            else:
                # Пробуем найти похожее
                for site_name, site_url in SITES.items():
                    if key in site_name or site_name in key:
                        url = site_url
                        key = site_name
                        break

        if not url:
            return f"⚠️ Сайт «{name}» не найден в моём словаре.\n💡 Попробуй указать точный URL или скажи «найди в гугле {name}»"

        # Определяем браузер
        if browser is None:
            if self._need_browser_choice():
                # Отложенный выбор
                browsers = self.detect_browsers()
                _save_pending({
                    "action": "open_site",
                    "site_name": key,
                    "url": url,
                    "browsers": browsers,
                })
                return self._format_browser_choice(browsers)

            browser = self.get_preferred_browser()

        # Открываем
        ok = self.open_url(url, browser=browser)
        if ok:
            browser_name = BROWSER_DISPLAY.get(browser, "браузере") if browser else "браузере"
            return f"✅ Открываю **{key}** в {browser_name}"
        return f"⚠️ Не удалось открыть {key}"

    def open_multiple(self, sites: List[str], browser: Optional[str] = None) -> str:
        """Открывает несколько сайтов."""
        if not sites:
            return "⚠️ Не указаны сайты."

        opened = []
        failed = []

        for site in sites:
            key = site.strip().lower()
            url = SITES.get(key)
            if not url and re.match(r"^[\w\-]+\.\w+", key):
                url = key
            if url:
                if self.open_url(url, browser=browser):
                    opened.append(key)
                else:
                    failed.append(key)
            else:
                failed.append(key)
            time.sleep(0.5)  # небольшая пауза

        parts = []
        if opened:
            parts.append(f"✅ Открыто: {', '.join(opened)}")
        if failed:
            parts.append(f"⚠️ Не найдено: {', '.join(failed)}")
        return "\n".join(parts)

    # ============================================================
    #  ПОИСК
    # ============================================================

    def search(self, query: str, engine: str = "google",
               browser: Optional[str] = None) -> str:
        """Поиск в указанном поисковике."""
        if not query or not query.strip():
            return "⚠️ Пустой поисковый запрос."

        engine_key = engine.strip().lower()
        template = SEARCH_ENGINES.get(engine_key)
        if not template:
            return f"⚠️ Поисковик «{engine}» не поддерживается."

        # URL-кодирование
        import urllib.parse
        encoded = urllib.parse.quote_plus(query.strip())
        url = template.format(encoded)

        # Открываем
        if browser is None:
            if self._need_browser_choice():
                browsers = self.detect_browsers()
                _save_pending({
                    "action": "search",
                    "query": query,
                    "engine": engine_key,
                    "url": url,
                    "browsers": browsers,
                })
                return self._format_browser_choice(browsers)
            browser = self.get_preferred_browser()

        ok = self.open_url(url, browser=browser)
        if ok:
            return f"🔎 Ищу в **{engine_key}**: «{query}»"
        return f"⚠️ Не удалось выполнить поиск."

    def search_google(self, query: str, browser=None) -> str:
        return self.search(query, "google", browser)

    def search_youtube(self, query: str, browser=None) -> str:
        return self.search(query, "youtube", browser)

    def search_yandex(self, query: str, browser=None) -> str:
        return self.search(query, "yandex", browser)

    def search_bing(self, query: str, browser=None) -> str:
        return self.search(query, "bing", browser)

    def search_duckduckgo(self, query: str, browser=None) -> str:
        return self.search(query, "duckduckgo", browser)

    # ============================================================
    #  ВКЛАДКИ (через pyautogui)
    # ============================================================

    def _send_keys(self, *keys) -> bool:
        """Отправляет клавиши в активное окно."""
        if not HAS_PYAUTOGUI:
            return False
        try:
            self.focus_browser()
            time.sleep(0.2)
            pyautogui.hotkey(*keys)
            return True
        except Exception as e:
            _log_warn(f"Ошибка отправки клавиш {keys}: {e}")
            return False

    def new_tab(self) -> str:
        if self._send_keys("ctrl", "t"):
            return "✅ Новая вкладка"
        return "⚠️ Не удалось открыть вкладку (нужен pyautogui)"

    def close_tab(self) -> str:
        if self._send_keys("ctrl", "w"):
            return "✅ Вкладка закрыта"
        return "⚠️ Не удалось закрыть вкладку"

    def next_tab(self) -> str:
        if self._send_keys("ctrl", "tab"):
            return "➡️ Следующая вкладка"
        return "⚠️ Не удалось переключить вкладку"

    def prev_tab(self) -> str:
        if self._send_keys("ctrl", "shift", "tab"):
            return "⬅️ Предыдущая вкладка"
        return "⚠️ Не удалось переключить вкладку"

    def reopen_tab(self) -> str:
        if self._send_keys("ctrl", "shift", "t"):
            return "🔄 Вкладка восстановлена"
        return "⚠️ Не удалось восстановить вкладку"

    # ============================================================
    #  НАВИГАЦИЯ
    # ============================================================

    def refresh(self) -> str:
        if self._send_keys("f5"):
            return "🔄 Страница обновлена"
        return "⚠️ Не удалось обновить"

    def go_back(self) -> str:
        if self._send_keys("alt", "left"):
            return "⬅️ Назад"
        return "⚠️ Не удалось перейти назад"

    def go_forward(self) -> str:
        if self._send_keys("alt", "right"):
            return "➡️ Вперёд"
        return "⚠️ Не удалось перейти вперёд"

    def go_home(self) -> str:
        if self._send_keys("alt", "home"):
            return "🏠 На главную"
        return "⚠️ Не удалось перейти на главную"

    def stop_loading(self) -> str:
        if self._send_keys("esc"):
            return "⏹️ Загрузка остановлена"
        return "⚠️ Не удалось остановить"

    def fullscreen(self) -> str:
        if self._send_keys("f11"):
            return "🖥️ Полноэкранный режим"
        return "⚠️ Не удалось включить"

    def open_devtools(self) -> str:
        if self._send_keys("f12"):
            return "🛠️ DevTools открыт"
        return "⚠️ Не удалось открыть DevTools"

    def copy_url(self) -> str:
        """Копирует URL текущей вкладки."""
        if not HAS_PYAUTOGUI:
            return "⚠️ Нужен pyautogui"
        try:
            self.focus_browser()
            time.sleep(0.2)
            pyautogui.hotkey("ctrl", "l")   # фокус на адресную строку
            time.sleep(0.1)
            pyautogui.hotkey("ctrl", "c")   # копировать
            pyautogui.press("escape")       # убрать фокус
            return "📋 URL скопирован в буфер"
        except Exception as e:
            _log_warn(f"Ошибка копирования URL: {e}")
            return "⚠️ Не удалось скопировать URL"

    # ============================================================
    #  ФОКУС НА БРАУЗЕРЕ
    # ============================================================

    def focus_browser(self, browser: Optional[str] = None) -> bool:
        """Фокусируется на окне браузера."""
        if not HAS_PYGETWINDOW:
            return False

        if browser is None:
            browser = self.get_preferred_browser()

        titles = BROWSER_TITLES.get(browser, []) if browser else []
        # Если браузер не указан — ищем любой
        if not titles:
            for t_list in BROWSER_TITLES.values():
                titles.extend(t_list)

        try:
            for title in titles:
                windows = gw.getWindowsWithTitle(title)
                for w in windows:
                    if not w.isMinimized:
                        try:
                            w.activate()
                            return True
                        except Exception:
                            pass
            # Если не нашли активных — ищем любые
            for title in titles:
                windows = gw.getWindowsWithTitle(title)
                if windows:
                    try:
                        windows[0].activate()
                        return True
                    except Exception:
                        pass
        except Exception as e:
            _log_warn(f"Ошибка фокуса: {e}")
        return False

    def list_windows(self) -> str:
        """Список открытых окон браузеров."""
        if not HAS_PYGETWINDOW:
            return "⚠️ Нужен pygetwindow"

        try:
            result = []
            for code, titles in BROWSER_TITLES.items():
                for title in titles:
                    for w in gw.getWindowsWithTitle(title):
                        result.append(f"• {BROWSER_DISPLAY.get(code, code)}: {w.title[:80]}")

            if not result:
                return "📋 Открытых окон браузеров не найдено"
            return "🌐 **Открытые окна браузеров:**\n" + "\n".join(result[:20])
        except Exception as e:
            return f"⚠️ Ошибка: {e}"

    # ============================================================
    #  ЗАКЛАДКИ
    # ============================================================

    def _load_bookmarks(self) -> Dict[str, str]:
        """Загружает закладки из файла."""
        if self._bookmarks is not None:
            return self._bookmarks

        if not os.path.exists(BOOKMARKS_FILE):
            self._bookmarks = {}
            return self._bookmarks

        try:
            with open(BOOKMARKS_FILE, "r", encoding="utf-8") as f:
                self._bookmarks = json.load(f)
        except Exception as e:
            _log_warn(f"Ошибка загрузки закладок: {e}")
            self._bookmarks = {}
        return self._bookmarks

    def _save_bookmarks(self) -> bool:
        """Сохраняет закладки."""
        try:
            with open(BOOKMARKS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._bookmarks or {}, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            _log_warn(f"Ошибка сохранения закладок: {e}")
            return False

    def add_bookmark(self, name: str, url: str = None) -> str:
        """
        Добавляет закладку.
        Если url не указан — берём из SITES по имени.
        """
        if not name or not name.strip():
            return "⚠️ Укажи название закладки."

        key = name.strip().lower()

        if url is None:
            url = SITES.get(key)
            if not url:
                return f"⚠️ Не знаю URL сайта «{name}». Скажи: «добавь в закладки {name} как https://...»"

        self._load_bookmarks()
        self._bookmarks[key] = url
        if self._save_bookmarks():
            return f"⭐ Закладка «{key}» добавлена"
        return "⚠️ Не удалось сохранить закладку"

    def remove_bookmark(self, name: str) -> str:
        """Удаляет закладку."""
        if not name:
            return "⚠️ Укажи название."
        key = name.strip().lower()
        self._load_bookmarks()
        if key in self._bookmarks:
            del self._bookmarks[key]
            self._save_bookmarks()
            return f"🗑️ Закладка «{key}» удалена"
        return f"⚠️ Закладка «{key}» не найдена"

    def list_bookmarks(self) -> str:
        """Список всех закладок."""
        self._load_bookmarks()
        if not self._bookmarks:
            return "📑 Закладок пока нет.\n💡 Скажи: «добавь в закладки ютуб»"

        lines = ["📑 **Мои закладки:**", ""]
        for name, url in sorted(self._bookmarks.items()):
            lines.append(f"• **{name}** — {url}")
        return "\n".join(lines)

    def open_bookmark(self, name: str) -> str:
        """Открывает закладку по имени."""
        if not name:
            return "⚠️ Укажи название закладки."
        key = name.strip().lower()
        self._load_bookmarks()
        url = self._bookmarks.get(key)
        if not url:
            return f"⚠️ Закладка «{key}» не найдена.\n💡 Скажи «покажи закладки»"

        # Определяем браузер
        if self._need_browser_choice():
            browsers = self.detect_browsers()
            _save_pending({
                "action": "open_url",
                "url": url,
                "browsers": browsers,
                "label": f"закладка «{key}»",
            })
            return self._format_browser_choice(browsers)

        browser = self.get_preferred_browser()
        if self.open_url(url, browser=browser):
            return f"⭐ Открываю закладку «{key}»"
        return f"⚠️ Не удалось открыть"

    # ============================================================
    #  ДИАЛОГ ВЫБОРА БРАУЗЕРА
    # ============================================================

    def _format_browser_choice(self, browsers: Dict[str, str]) -> str:
        """Форматирует список браузеров для чата."""
        lines = [
            "🔍 Найдено несколько браузеров:",
            "",
        ]
        codes = list(browsers.keys())
        for i, code in enumerate(codes, 1):
            name = BROWSER_DISPLAY.get(code, code)
            lines.append(f"   {i}. {name}")

        lines.append("")
        lines.append("Напиши номер (1-{}) или «отмена».".format(len(codes)))
        lines.append("💡 Выбор сохранится для будущих команд.")
        return "\n".join(lines)

    # ============================================================
    #  ОБРАБОТКА ВЫБОРА
    # ============================================================

    def handle_choice(self, text: str) -> Optional[str]:
        """
        Обрабатывает ответ пользователя на выбор браузера.
        Возвращает ответ для чата или None, если не про нас.
        """
        global PENDING_BROWSER_CHOICE
        if PENDING_BROWSER_CHOICE is None:
            return None

        low = text.strip().lower()

        # Отмена
        if low in ("отмена", "cancel", "нет", "no"):
            _clear_pending()
            return "✅ Отменено."

        # Номер
        if re.match(r"^\d+$", low):
            try:
                idx = int(low) - 1
                browsers = PENDING_BROWSER_CHOICE.get("browsers", {})
                codes = list(browsers.keys())
                if 0 <= idx < len(codes):
                    chosen = codes[idx]
                    self.set_preferred_browser(chosen)
                    return self._execute_pending(chosen)
                return f"⚠️ Неверный номер. Введи 1-{len(codes)}"
            except Exception as e:
                return f"⚠️ Ошибка: {e}"

        # Имя браузера
        for code, display in BROWSER_DISPLAY.items():
            if low in code or low in display.lower():
                if code in PENDING_BROWSER_CHOICE.get("browsers", {}):
                    self.set_preferred_browser(code)
                    return self._execute_pending(code)

        return f"⚠️ Не поняла. Введи номер или название браузера."

    def _execute_pending(self, browser: str) -> str:
        """Выполняет отложенное действие с выбранным браузером."""
        global PENDING_BROWSER_CHOICE
        data = PENDING_BROWSER_CHOICE
        _clear_pending()

        if not data:
            return "⚠️ Что-то пошло не так."

        action = data.get("action")
        browser_name = BROWSER_DISPLAY.get(browser, browser)

        if action == "open_site":
            url = data.get("url")
            site = data.get("site_name", url)
            if self.open_url(url, browser=browser):
                return f"✅ Открываю **{site}** в {browser_name}"
            return f"⚠️ Не удалось открыть {site}"

        if action == "open_url":
            url = data.get("url")
            label = data.get("label", url)
            if self.open_url(url, browser=browser):
                return f"✅ Открываю {label} в {browser_name}"
            return f"⚠️ Не удалось открыть"

        if action == "search":
            url = data.get("url")
            query = data.get("query", "")
            engine = data.get("engine", "google")
            if self.open_url(url, browser=browser):
                return f"🔎 Ищу в **{engine}**: «{query}» (в {browser_name})"
            return f"⚠️ Не удалось выполнить поиск"

        return "⚠️ Неизвестное действие."

    # ============================================================
    #  ИНФО О БРАУЗЕРАХ
    # ============================================================

    def info_browsers(self) -> str:
        """Информация о найденных браузерах."""
        browsers = self.detect_browsers(force=True)
        if not browsers:
            return "🌐 Не найдено ни одного браузера."

        lines = ["🌐 **Найденные браузеры:**", ""]
        for code in browsers:
            name = BROWSER_DISPLAY.get(code, code)
            marker = " ⭐ (по умолчанию)" if self.get_preferred_browser() == code else ""
            lines.append(f"• {name}{marker}")

        if len(browsers) > 1 and not self.get_preferred_browser():
            lines.append("")
            lines.append("💡 При первом открытии я спрошу, какой использовать.")

        return "\n".join(lines)


# ================================================================
#  ГЛОБАЛЬНЫЙ SINGLETON
# ================================================================

_browser: Optional[BrowserController] = None


def get_browser() -> BrowserController:
    """Возвращает глобальный контроллер браузера."""
    global _browser
    if _browser is None:
        _browser = BrowserController()
    return _browser


# ================================================================
#  ЭКСПОРТ
# ================================================================

__all__ = [
    "BrowserController",
    "get_browser",
    "has_pending_browser_choice",
    "PENDING_BROWSER_CHOICE",
    "SITES",
    "SEARCH_ENGINES",
    "BROWSER_DISPLAY",
]


# ================================================================
#  ТЕСТ
# ================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

    print("🌐 Тест BrowserController")
    print("=" * 60)

    b = get_browser()

    print("\n📋 Найденные браузеры:")
    print(b.info_browsers())

    print("\n⭐ Тест закладок:")
    print(b.add_bookmark("ютуб"))
    print(b.add_bookmark("гитхаб"))
    print(b.list_bookmarks())

    print("\n🌐 Тест открытия (Edge):")
    print(b.open_site("ютуб", browser="edge"))

    print("\n🔎 Тест поиска (Edge):")
    print(b.search_google("python tutorial", browser="edge"))

    print("\n📑 Тест закладки (Edge):")
    print(b.open_bookmark("гитхаб"))

    print("\n✅ Тесты завершены!")