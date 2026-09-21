# -*- coding: utf-8 -*-
"""
Модуль для работы с напоминаниями и уведомлениями Windows.
Поддерживает: установка, отмена, список, очистка.
Абсолютное и относительное время, дни недели.

Особенности:
    - Точное время срабатывания (без «-1 минуты»)
    - Корректная отмена (поток завершается)
    - Уведомления через plyer / PowerShell balloon (не блокирует)
    - Логирование и аудит
    - Умная очередь: удаляет самое дальнее по времени
"""

import time
import re
import sys
import logging
import threading
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))


# ========== ЛОГИРОВАНИЕ ==========

def _log(msg: str) -> None:
    logging.info(f"[NOTIF] {msg}")


def _log_warn(msg: str) -> None:
    logging.warning(f"[NOTIF] {msg}")


def _audit(msg: str) -> None:
    """Логировать в аудит, если доступен."""
    try:
        from security.audit import get_audit
        get_audit().log_security("notifications", msg)
    except Exception:
        pass


# ========== КОНСТАНТЫ ==========
MAX_REMINDERS = 20

# ⚠️ ТОЛЬКО эти слова активируют напоминание!
REMINDER_KEYWORDS = [
    "напомни", "напомните", "remind", "не забудь",
    "напоминание", "будильник", "установи напоминание",
    "запомни", "напомни мне",
]

WEEKDAYS = {
    "понедельник": 0, "вторник": 1, "среда": 2, "четверг": 3,
    "пятница": 4, "суббота": 5, "воскресенье": 6,
}

# Глобальное хранилище напоминаний
_reminders: List[Dict[str, Any]] = []
_reminders_lock = threading.RLock()


# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

def _get_time_from_str(text: str) -> Optional[Tuple[int, int]]:
    """Извлекает время (HH, MM) из текста. Возвращает кортеж или None."""
    match = re.search(r"(\d{1,2}):(\d{2})", text)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    return None


def _get_time_delta(text: str) -> Optional[timedelta]:
    """Извлекает временной интервал (например, 'через 5 минут')."""
    patterns = [
        (r"через\s+(\d+)\s*(?:минут|минуту|минуты|мин)\b",
         lambda m: timedelta(minutes=int(m.group(1)))),
        (r"через\s+(\d+)\s*(?:час|часа|часов|ч)\b",
         lambda m: timedelta(hours=int(m.group(1)))),
        (r"через\s+(\d+)\s*(?:день|дня|дней|д)\b",
         lambda m: timedelta(days=int(m.group(1)))),
        (r"через\s+(\d+)\s*(?:секунд|секунду|секунды|сек)\b",
         lambda m: timedelta(seconds=int(m.group(1)))),
        (r"in\s+(\d+)\s*(?:minute|minutes|min)\b",
         lambda m: timedelta(minutes=int(m.group(1)))),
        (r"in\s+(\d+)\s*(?:hour|hours)\b",
         lambda m: timedelta(hours=int(m.group(1)))),
    ]

    for pattern, handler in patterns:
        match = re.search(pattern, text.lower())
        if match:
            return handler(match)
    return None


def _get_day_delta(text: str) -> Optional[timedelta]:
    """Извлекает день (например, 'завтра', 'понедельник')."""
    low = text.lower()
    if "послезавтра" in low:
        return timedelta(days=2)
    if "завтра" in low:
        return timedelta(days=1)
    for day_name, day_num in WEEKDAYS.items():
        if day_name in low:
            current_day = datetime.now().weekday()
            days_ahead = (day_num - current_day) % 7
            if days_ahead == 0:
                days_ahead = 7
            return timedelta(days=days_ahead)
    return None


def _calculate_remind_time(text: str) -> Optional[datetime]:
    """
    Вычисляет время напоминания из текста.
    Приоритет: день+время > абсолютное время > день > относительное.
    """
    now = datetime.now()
    low = text.lower()

    day_delta = _get_day_delta(text)
    time_parts = _get_time_from_str(text)

    # 1. День + время: "завтра в 18:30"
    if day_delta and time_parts:
        h, m = time_parts
        target = (now + day_delta).replace(hour=h, minute=m, second=0, microsecond=0)
        return target

    # 2. Только абсолютное время: "в 18:30"
    if time_parts and not day_delta:
        h, m = time_parts
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return target

    # 3. Только день: "завтра", "в понедельник"
    if day_delta and not time_parts:
        return now + day_delta

    # 4. Относительное время: "через 5 минут"
    delta = _get_time_delta(text)
    if delta:
        return now + delta

    return None


# ========== УВЕДОМЛЕНИЯ ==========

def show_notification(title: str, message: str) -> None:
    """Показывает уведомление (plyer → PowerShell balloon → MessageBox)."""
    _log(f"Уведомление: {title} — {message}")

    # 1. plyer
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="Zeta",
            timeout=10,
        )
        return
    except ImportError:
        pass
    except Exception as e:
        _log_warn(f"plyer упал: {e}")

    # 2. PowerShell balloon (не блокирует)
    if _powershell_balloon(title, message):
        return

    # 3. MessageBox (блокирует — крайний случай)
    _fallback_messagebox(title, message)


def _powershell_balloon(title: str, message: str) -> bool:
    """Balloon через PowerShell — не блокирует."""
    try:
        # Экранируем кавычки для PowerShell
        t = title.replace("'", "''").replace('"', '`"')
        m = message.replace("'", "''").replace('"', '`"')

        ps = (
            '[reflection.assembly]::loadwithpartialname("System.Windows.Forms") | Out-Null;'
            '[reflection.assembly]::loadwithpartialname("System.Drawing") | Out-Null;'
            '$n = New-Object System.Windows.Forms.NotifyIcon;'
            '$n.Icon = [System.Drawing.SystemIcons]::Information;'
            '$n.Visible = $true;'
            f'$n.ShowBalloonTip(8000, "{t}", "{m}", '
            '[System.Windows.Forms.ToolTipIcon]::Info);'
            'Start-Sleep -Seconds 9;'
            '$n.Dispose()'
        )

        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", ps],
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return True
    except Exception as e:
        _log_warn(f"PowerShell balloon упал: {e}")
        return False


def _fallback_messagebox(title: str, message: str) -> None:
    """MessageBox — блокирует. Крайний случай."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x40)
    except Exception as e:
        _log_warn(f"MessageBox упал: {e}")
        print(f"[💬] {title}: {message}")


# ========== УПРАВЛЕНИЕ НАПОМИНАНИЯМИ ==========

def _reminder_thread(text: str, target_time: datetime, cancel_flag: Dict[str, bool]) -> None:
    """
    Поток напоминания.
    - Спит до target_time (проверяет флаг отмены).
    - При срабатывании показывает уведомление.
    - Удаляет себя из _reminders.
    """
    try:
        while True:
            if cancel_flag.get("cancelled"):
                _log(f"Отменено: {text}")
                return

            now = datetime.now()
            seconds_left = (target_time - now).total_seconds()

            if seconds_left <= 0:
                # Время пришло — показываем
                show_notification("⏰ Zeta — Напоминание", text)
                _audit(f"reminder_fired: {text}")

                # Удаляем из списка
                with _reminders_lock:
                    for r in list(_reminders):
                        if r.get("target_time") == target_time and r.get("text") == text:
                            _reminders.remove(r)
                            break
                return

            # Спим разумно: не более 60 секунд за раз
            sleep_time = min(60.0, max(1.0, seconds_left))
            time.sleep(sleep_time)

    except Exception as e:
        _log_warn(f"Ошибка в потоке напоминания: {e}")


def add_reminder(text: str, minutes: int,
                 target_time: Optional[datetime] = None) -> str:
    """
    Добавляет напоминание.
    Если target_time задан — используется он.
    Иначе — now + minutes.
    """
    if not text or not text.strip():
        text = "Напоминание"

    # Защита от None
    if target_time is None:
        if minutes is None:
            minutes = 1
        try:
            minutes = int(minutes)
        except (TypeError, ValueError):
            minutes = 1

        # Точное время: + minutes * 60 секунд
        target_time = datetime.now() + timedelta(minutes=minutes)

    # Проверка очереди (B: удаляем самое дальнее)
    with _reminders_lock:
        while len(_reminders) >= MAX_REMINDERS:
            # Находим самое дальнее по target_time
            farthest_idx = 0
            farthest_time = _reminders[0].get("target_time", datetime.now())
            for i, r in enumerate(_reminders):
                tt = r.get("target_time")
                if tt and tt > farthest_time:
                    farthest_time = tt
                    farthest_idx = i

            removed = _reminders.pop(farthest_idx)
            _log(f"Очередь переполнена, удалено дальнее: {removed.get('text')}")

    # Флаг отмены
    cancel_flag = {"cancelled": False}

    # Запускаем поток
    t = threading.Thread(
        target=_reminder_thread,
        args=(text, target_time, cancel_flag),
        daemon=True,
        name=f"Reminder-{text[:20]}",
    )
    t.start()

    with _reminders_lock:
        _reminders.append({
            "text": text,
            "minutes": minutes,
            "target_time": target_time,
            "time": datetime.now(),
            "thread": t,
            "cancel_flag": cancel_flag,
        })

    _log(f"Добавлено: {text} на {target_time.strftime('%H:%M')}")
    _audit(f"reminder_add: {text}")

    time_str = target_time.strftime("%H:%M")
    return f"⏰ Напомню в {time_str}: {text}"


def get_reminders() -> List[Dict[str, Any]]:
    with _reminders_lock:
        return _reminders.copy()


def cancel_reminder(text: str) -> bool:
    """Отменяет напоминание по тексту. Поток завершается."""
    with _reminders_lock:
        for r in list(_reminders):
            if r.get("text") == text:
                flag = r.get("cancel_flag")
                if flag:
                    flag["cancelled"] = True
                _reminders.remove(r)
                _log(f"Отменено: {text}")
                return True
    return False


def cancel_reminder_by_index(index: int) -> bool:
    """Отменяет по номеру (1-based)."""
    with _reminders_lock:
        if 1 <= index <= len(_reminders):
            r = _reminders[index - 1]
            flag = r.get("cancel_flag")
            if flag:
                flag["cancelled"] = True
            _reminders.pop(index - 1)
            _log(f"Отменено #{index}: {r.get('text')}")
            return True
    return False


def clear_reminders() -> None:
    """Отменяет все напоминания."""
    with _reminders_lock:
        for r in _reminders:
            flag = r.get("cancel_flag")
            if flag:
                flag["cancelled"] = True
        _reminders.clear()
    _log("Все напоминания отменены")


def list_reminders() -> str:
    with _reminders_lock:
        if not _reminders:
            return "📭 Нет активных напоминаний."

        result = "📋 **Активные напоминания:**\n"
        for i, r in enumerate(_reminders, 1):
            target = r.get("target_time")
            if target is None:
                target = datetime.now() + timedelta(minutes=r.get("minutes", 0))

            time_str = target.strftime("%H:%M")
            created = r.get("time", datetime.now()).strftime("%H:%M")
            result += f"  {i}. {r.get('text')} (в {time_str}, создано в {created})\n"

        return result.strip()


def get_reminder_stats() -> Dict[str, int]:
    with _reminders_lock:
        return {"total": len(_reminders), "max": MAX_REMINDERS}


def cancel_reminder_command(message: str) -> bool:
    """Обрабатывает текстовые команды отмены."""
    low = message.lower()

    if "отмен" not in low:
        return False

    if "все" in low:
        clear_reminders()
        return True

    with _reminders_lock:
        # Ищем по тексту
        for r in list(_reminders):
            rtext = (r.get("text") or "").lower()
            if rtext and rtext in low:
                flag = r.get("cancel_flag")
                if flag:
                    flag["cancelled"] = True
                _reminders.remove(r)
                return True

        # Если не нашли по тексту — снимаем первое
        if _reminders:
            r = _reminders.pop(0)
            flag = r.get("cancel_flag")
            if flag:
                flag["cancelled"] = True
            return True

    return False


# ========== СТРОГОЕ РАСПОЗНАВАНИЕ ==========

def needs_reminder(message: str) -> Tuple[Optional[int], Optional[str]]:
    """
    СТРОГОЕ распознавание напоминаний.
    Напоминание создаётся ТОЛЬКО если есть КЛЮЧЕВОЕ СЛОВО + ВРЕМЯ.

    Возвращает (минуты, текст) или (None, None).
    """
    if not message:
        return None, None

    msg = message.lower().strip()

    # 1. Есть ключевое слово?
    has_keyword = any(kw in msg for kw in REMINDER_KEYWORDS)
    if not has_keyword:
        return None, None

    # 2. Вычисляем target_time
    target_time = _calculate_remind_time(msg)
    if not target_time:
        return None, None

    # 3. Извлекаем текст напоминания
    reminder_text = message
    for cmd in REMINDER_KEYWORDS:
        reminder_text = re.sub(cmd, "", reminder_text, flags=re.IGNORECASE)

    # Убираем время из текста
    time_patterns = [
        r"через\s+\d+\s*(?:минут|минуту|минуты|мин|час|часа|часов|сек|секунд|секунды)\b",
        r"завтра\s+в\s+\d{1,2}:\d{2}",
        r"послезавтра\s+в\s+\d{1,2}:\d{2}",
        r"в\s+\d{1,2}:\d{2}",
        r"in\s+\d+\s*(?:minute|minutes|hour|hours)\b",
        r"\d{1,2}:\d{2}",
    ]
    for tp in time_patterns:
        reminder_text = re.sub(tp, "", reminder_text, flags=re.IGNORECASE)

    # Убираем дни недели
    for day in WEEKDAYS:
        reminder_text = re.sub(day, "", reminder_text, flags=re.IGNORECASE)

    # Убираем "завтра" / "послезавтра" из текста
    reminder_text = re.sub(r"\b(?:завтра|послезавтра)\b", "", reminder_text, flags=re.IGNORECASE)

    # Чистим пунктуацию и пробелы
    reminder_text = re.sub(r"\s+", " ", reminder_text).strip(" ,.!?-")
    if not reminder_text or len(reminder_text) < 2:
        reminder_text = "Напоминание"

    # 4. Считаем минуты — округляем ВВЕРХ (round), а не // (был баг: 5 → 4)
    now = datetime.now()
    seconds_left = (target_time - now).total_seconds()
    minutes = int(round(seconds_left / 60.0))

    if minutes < 1:
        minutes = 1

    return minutes, reminder_text


# ========== ТЕСТ ==========

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    print("🧪 Тест notifications.py\n")
    print("=" * 60)

    # --- Тест 1: ДОЛЖНЫ сработать ---
    print("\n📝 Тест 1: ДОЛЖНЫ сработать")
    should_pass = [
        "напомни через 5 минут выпить воды",
        "напомни в 18:30 позвонить маме",
        "напомни завтра в 9:00 пойти на работу",
        "напомни в понедельник купить продукты",
        "напомни через 1 час проверить почту",
    ]
    for msg in should_pass:
        minutes, text = needs_reminder(msg)
        marker = "✅" if minutes else "❌"
        print(f"{marker} {msg!r:50} → {minutes} мин, '{text}'")

    # --- Тест 2: НЕ ДОЛЖНЫ сработать ---
    print("\n📝 Тест 2: НЕ ДОЛЖНЫ сработать")
    should_fail = [
        "что такое атом",
        "привет как дела",
        "расскажи про атом",
        "сколько будет 2+2",
        "напомни",                    # нет времени
        "через 5 минут",              # нет ключевого слова
    ]
    for msg in should_fail:
        minutes, text = needs_reminder(msg)
        marker = "✅" if not minutes else "❌ ОШИБКА"
        print(f"{marker} {msg!r:30} → {minutes}")

    # --- Тест 3: Точность времени ---
    print("\n📝 Тест 3: Точность (5 минут → должно быть 5)")
    minutes, _ = needs_reminder("напомни через 5 минут тест")
    print(f"Получено: {minutes} мин {'✅' if minutes == 5 else '❌ (был баг)'}")

    # --- Тест 4: Добавление и список ---
    print("\n📝 Тест 4: Добавление")
    print(add_reminder("тестовое напоминание", 1))
    print(add_reminder("второе напоминание", 2))
    print(list_reminders())

    # --- Тест 5: Отмена ---
    print("\n📝 Тест 5: Отмена")
    cancel_reminder("тестовое напоминание")
    print(list_reminders())

    # --- Тест 6: Очистка ---
    print("\n📝 Тест 6: Очистка")
    clear_reminders()
    print(f"Активных: {len(get_reminders())}")
    print(f"Статистика: {get_reminder_stats()}")

    print("\n" + "=" * 60)
    print("✅ Тесты завершены!")