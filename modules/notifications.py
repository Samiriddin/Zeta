# -*- coding: utf-8 -*-
"""
Модуль для работы с напоминаниями и уведомлениями Windows.
Поддерживает: установка, отмена, список, очистка.
Абсолютное и относительное время, дни недели.
"""

import threading
import time
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict, Any

# ========== КОНСТАНТЫ ==========
MAX_REMINDERS = 20

# ⚠️ КРИТИЧНО: ТОЛЬКО эти слова активируют напоминание!
# Если слова нет в списке — напоминание НЕ создаётся!
REMINDER_KEYWORDS = [
    "напомни", "напомните", "remind", "не забудь", 
    "напоминание", "будильник", "установи напоминание",
    "запомни", "напомни мне"
]

WEEKDAYS = {
    "понедельник": 0, "вторник": 1, "среда": 2, "четверг": 3,
    "пятница": 4, "суббота": 5, "воскресенье": 6
}

# Глобальное хранилище напоминаний
_reminders: List[Dict[str, Any]] = []


# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

def _get_time_from_str(text: str) -> Optional[datetime]:
    """Извлекает время из текста (например, 'в 18:30')."""
    match = re.search(r"(\d{1,2}):(\d{2})", text)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
    return None


def _get_time_delta(text: str) -> Optional[timedelta]:
    """Извлекает временной интервал (например, 'через 5 минут')."""
    # Минуты
    patterns = [
        (r"через\s+(\d+)\s*(?:минут|минуту|минуты|мин|м\.)", lambda m: timedelta(minutes=int(m.group(1)))),
        (r"через\s+(\d+)\s*(?:час|часа|часов|ч)", lambda m: timedelta(hours=int(m.group(1)))),
        (r"через\s+(\d+)\s*(?:день|дня|дней|д)", lambda m: timedelta(days=int(m.group(1)))),
        (r"in\s+(\d+)\s*(?:minute|minutes|min)", lambda m: timedelta(minutes=int(m.group(1)))),
        (r"in\s+(\d+)\s*(?:hour|hours)", lambda m: timedelta(hours=int(m.group(1)))),
    ]
    
    for pattern, handler in patterns:
        match = re.search(pattern, text.lower())
        if match:
            return handler(match)
    return None


def _get_day_delta(text: str) -> Optional[timedelta]:
    """Извлекает день (например, 'завтра', 'понедельник')."""
    if re.search(r"завтра", text.lower()):
        return timedelta(days=1)
    if re.search(r"послезавтра", text.lower()):
        return timedelta(days=2)
    for day_name, day_num in WEEKDAYS.items():
        if day_name in text.lower():
            current_day = datetime.now().weekday()
            days_ahead = (day_num - current_day) % 7
            if days_ahead == 0:
                days_ahead = 7
            return timedelta(days=days_ahead)
    return None


def _calculate_remind_time(text: str) -> Optional[datetime]:
    """Вычисляет время напоминания из текста."""
    now = datetime.now()
    
    # Сначала проверяем абсолютное время (в 18:30)
    absolute_time = _get_time_from_str(text)
    if absolute_time:
        if absolute_time <= now:
            absolute_time += timedelta(days=1)
        return absolute_time
    
    # Потом проверяем относительное время (через 5 минут)
    delta = _get_time_delta(text)
    if delta:
        return now + delta
    
    # Потом проверяем день + время (завтра в 18:30)
    day_delta = _get_day_delta(text)
    if day_delta:
        absolute_time = _get_time_from_str(text)
        if absolute_time:
            target_date = (now + day_delta).replace(
                hour=absolute_time.hour, 
                minute=absolute_time.minute, 
                second=0, 
                microsecond=0
            )
            return target_date
        return now + day_delta
    
    return None


# ========== ОСНОВНЫЕ ФУНКЦИИ ==========

def add_reminder(text: str, minutes: int, target_time: Optional[datetime] = None) -> str:
    """Добавляет напоминание."""
    if target_time is None:
        target_time = datetime.now() + timedelta(minutes=minutes)
    
    def remind():
        while True:
            now = datetime.now()
            if now >= target_time:
                show_notification("⏰ Z — Напоминание", text)
                break
            time.sleep(5)
    
    t = threading.Thread(target=remind, daemon=True)
    t.start()
    
    if len(_reminders) >= MAX_REMINDERS:
        _reminders.pop(0)
    
    _reminders.append({
        "text": text,
        "minutes": minutes,
        "target_time": target_time,
        "time": datetime.now(),
        "thread": t
    })
    
    time_str = target_time.strftime("%H:%M")
    return f"⏰ Напомню в {time_str}: {text}"


def show_notification(title: str, message: str) -> None:
    """Показывает уведомление."""
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="Zeta",
            timeout=10
        )
        print(f"[✅ Уведомление] {title}: {message}")
    except ImportError:
        _fallback_notification(title, message)
    except Exception as e:
        print(f"[❌ Ошибка уведомления (plyer)]: {e}")
        _fallback_notification(title, message)


def _fallback_notification(title: str, message: str) -> None:
    """Резервное уведомление через MessageBox."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x40)
        print(f"[✅ MessageBox] {title}: {message}")
    except Exception as e:
        print(f"[❌ Ошибка уведомления (MessageBox)]: {e}")
        print(f"[💬] {title}: {message}")


def needs_reminder(message: str) -> Tuple[Optional[int], Optional[str]]:
    """
    СТРОГОЕ распознавание напоминаний.
    Напоминание создаётся ТОЛЬКО если есть КЛЮЧЕВОЕ СЛОВО + ВРЕМЯ.
    """
    if not message:
        return None, None

    msg = message.lower().strip()

    # ⚠️ ТОЛЬКО ЭТИ СЛОВА АКТИВИРУЮТ НАПОМИНАНИЕ!
    REMINDER_KEYWORDS = [
        "напомни", "напомните", "remind", "не забудь",
        "напоминание", "будильник", "установи напоминание"
    ]

    has_keyword = any(kw in msg for kw in REMINDER_KEYWORDS)
    if not has_keyword:
        return None, None

    # Проверяем наличие времени
    target_time = _calculate_remind_time(msg)
    if not target_time:
        return None, None

    # Извлекаем текст напоминания
    reminder_text = message
    for cmd in REMINDER_KEYWORDS:
        reminder_text = re.sub(cmd, "", reminder_text, flags=re.IGNORECASE)

    time_patterns = [
        r"через\s+\d+\s*(минут|минуту|минуты|мин|час|часа|часов)",
        r"в\s+\d{1,2}:\d{2}",
        r"завтра\s+в\s+\d{1,2}:\d{2}",
        r"in\s+\d+\s*(minute|minutes|hour|hours)",
    ]
    for tp in time_patterns:
        reminder_text = re.sub(tp, "", reminder_text, flags=re.IGNORECASE)

    reminder_text = reminder_text.strip()
    if not reminder_text:
        reminder_text = "Напоминание"

    now = datetime.now()
    minutes = int((target_time - now).total_seconds() // 60)
    if minutes < 1:
        minutes = 1

    return minutes, reminder_text


# ========== УПРАВЛЕНИЕ НАПОМИНАНИЯМИ ==========

def get_reminders() -> List[Dict[str, Any]]:
    return _reminders.copy()


def cancel_reminder(text: str) -> bool:
    for r in _reminders:
        if r.get("text") == text:
            _reminders.remove(r)
            return True
    return False


def cancel_reminder_by_index(index: int) -> bool:
    if 1 <= index <= len(_reminders):
        _reminders.pop(index - 1)
        return True
    return False


def clear_reminders() -> None:
    _reminders.clear()


def list_reminders() -> str:
    if not _reminders:
        return "📭 Нет активных напоминаний."
    
    result = "📋 **Активные напоминания:**\n"
    for i, r in enumerate(_reminders, 1):
        target = r.get("target_time", datetime.now() + timedelta(minutes=r.get("minutes", 0)))
        time_str = target.strftime("%H:%M")
        created = r.get("time", datetime.now()).strftime("%H:%M")
        result += f"  {i}. {r.get('text')} (в {time_str}, создано в {created})\n"
    
    return result.strip()


def get_reminder_stats() -> Dict[str, int]:
    return {
        "total": len(_reminders),
        "max": MAX_REMINDERS,
    }


def cancel_reminder_command(message: str) -> bool:
    if "отмени" in message.lower() or "отмена" in message.lower():
        if "все" in message.lower():
            clear_reminders()
            return True
        for r in _reminders:
            if r.get("text").lower() in message.lower():
                _reminders.remove(r)
                return True
        if _reminders:
            _reminders.pop(0)
            return True
    return False


# ========== ТЕСТ ==========
if __name__ == "__main__":
    print("🧪 Тест notifications.py\n")
    
    print("📝 Тест 1: Парсинг напоминаний (ДОЛЖНЫ СРАБОТАТЬ)")
    test_messages_pass = [
        "напомни через 5 минут выпить воды",
        "напомни в 18:30 позвонить маме",
        "напомни завтра в 9:00 пойти на работу",
        "напомни в понедельник купить продукты",
    ]
    for msg in test_messages_pass:
        minutes, text = needs_reminder(msg)
        if minutes:
            print(f"✅ {msg} → {minutes} мин: {text}")
        else:
            print(f"❌ {msg} → НЕ РАСПОЗНАНО (ошибка!)")
    print("-" * 40)
    
    print("📝 Тест 2: Парсинг напоминаний (НЕ ДОЛЖНЫ СРАБОТАТЬ)")
    test_messages_fail = [
        "что такое атом",          # ← НЕ ДОЛЖНО СРАБОТАТЬ!
        "привет как дела",         # ← НЕ ДОЛЖНО СРАБОТАТЬ!
        "расскажи про атом",       # ← НЕ ДОЛЖНО СРАБОТАТЬ!
        "сколько будет 2+2",       # ← НЕ ДОЛЖНО СРАБОТАТЬ!
    ]
    for msg in test_messages_fail:
        minutes, text = needs_reminder(msg)
        if minutes:
            print(f"❌ {msg} → {minutes} мин: {text} (ОШИБКА! Не должно было сработать!)")
        else:
            print(f"✅ {msg} → не распознано (правильно)")
    print("-" * 40)
    
    print("📝 Тест 3: Добавление напоминания")
    result = add_reminder("тестовое напоминание", 1)
    print(result)
    print("-" * 40)
    
    print("📝 Тест 4: Список напоминаний")
    print(list_reminders())
    print("-" * 40)
    
    print("📝 Тест 5: Отмена напоминания")
    cancel_reminder_command("отмени напоминание")
    print(list_reminders())
    print("-" * 40)
    
    print("📝 Тест 6: Статистика")
    stats = get_reminder_stats()
    print(f"Активных: {stats['total']}, Максимум: {stats['max']}")
    print("-" * 40)
    
    print("📝 Тест 7: Очистка")
    clear_reminders()
    print(f"Очищено. Активных: {len(get_reminders())}")
    print("-" * 40)
    
    print("\n✅ Тесты завершены!")