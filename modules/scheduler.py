# -*- coding: utf-8 -*-
"""
Zeta — Умный планировщик.
Задачи, события, рутины + парсинг дат.
"""

import re
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple, List

from core.memory import (
    add_task, get_tasks, complete_task, delete_task, get_tasks_stats,
    add_event, get_events, delete_event,
    add_routine, get_routines, delete_routine,
)


def _log(msg: str) -> None:
    logging.info(f"[SCHEDULER] {msg}")


# ================================================================
#  ПАРСЕР ДАТ
# ================================================================

class DateParser:
    """Парсер естественных дат"""

    WEEKDAYS = {
        "понедельник": 0, "пн": 0,
        "вторник": 1, "вт": 1,
        "среда": 2, "ср": 2,
        "четверг": 3, "чт": 3,
        "пятница": 4, "пт": 4,
        "суббота": 5, "сб": 5,
        "воскресенье": 6, "вс": 6,
    }

    @staticmethod
    def parse(text: str) -> Optional[datetime]:
        """Парсит дату из текста."""
        if not text:
            return None

        text = text.lower().strip()
        now = datetime.now()

        # === ВРЕМЯ: "в 15:00" ===
        time_match = re.search(r"(\d{1,2}):(\d{2})", text)
        hour, minute = None, 0
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))

        # === СЕГОДНЯ ===
        if "сегодня" in text:
            base = now
            if hour is not None:
                return base.replace(hour=hour, minute=minute, second=0, microsecond=0)
            return base

        # === ЗАВТРА ===
        if "завтра" in text:
            base = now + timedelta(days=1)
            if hour is not None:
                return base.replace(hour=hour, minute=minute, second=0, microsecond=0)
            return base

        # === ПОСЛЕЗАВТРА ===
        if "послезавтра" in text:
            base = now + timedelta(days=2)
            if hour is not None:
                return base.replace(hour=hour, minute=minute, second=0, microsecond=0)
            return base

        # === ЧЕРЕЗ N ===
        delta_match = re.search(r"через\s+(\d+)\s*(минут|мин|час|часов|день|дней|дня)", text)
        if delta_match:
            amount = int(delta_match.group(1))
            unit = delta_match.group(2)
            if unit.startswith("мин"):
                return now + timedelta(minutes=amount)
            elif unit.startswith("час"):
                return now + timedelta(hours=amount)
            elif unit.startswith("ден") or unit.startswith("дн"):
                return now + timedelta(days=amount)

        # === ДЕНЬ НЕДЕЛИ ===
        for day_name, day_num in DateParser.WEEKDAYS.items():
            if day_name in text:
                days_ahead = day_num - now.weekday()
                if days_ahead <= 0:
                    days_ahead += 7
                base = now + timedelta(days=days_ahead)
                if hour is not None:
                    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)
                return base

        # === ТОЛЬКО ВРЕМЯ ===
        if hour is not None:
            base = now
            if hour < now.hour:
                base = now + timedelta(days=1)
            return base.replace(hour=hour, minute=minute, second=0, microsecond=0)

        return None

    @staticmethod
    def format_dt(dt: datetime) -> str:
        """Красивое форматирование даты."""
        now = datetime.now()
        diff = (dt - now).days
        time_str = dt.strftime("%H:%M")

        if diff == 0:
            return f"сегодня в {time_str}"
        elif diff == 1:
            return f"завтра в {time_str}"
        elif diff == 2:
            return f"послезавтра в {time_str}"
        elif 0 < diff < 7:
            days = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
            return f"{days[dt.weekday()]} в {time_str}"
        else:
            return dt.strftime("%d.%m.%Y в %H:%M")


# ================================================================
#  МЕНЕДЖЕР ПЛАНИРОВЩИКА
# ================================================================

class Scheduler:
    """Умный планировщик"""

    # === ЗАДАЧИ ===

    def create_task(self, text: str) -> str:
        """Создать задачу из текста."""
        priority = 1
        if "важно" in text.lower() or "срочно" in text.lower():
            priority = 3
        elif "потом" in text.lower():
            priority = 0

        due_date = None
        due_match = re.search(r"до\s+(.+)", text.lower())
        if due_match:
            dt = DateParser.parse(due_match.group(1))
            if dt:
                due_date = dt.isoformat()

        title = text
        for phrase in ["добавь задачу", "создай задачу", "новая задача", "задача:"]:
            title = title.lower().replace(phrase, "").strip()
        title = title.capitalize()

        if not title:
            return "⚠️ Не поняла, какую задачу добавить."

        task_id = add_task(title, "", due_date, priority)

        result = f"✅ Задача добавлена:\n   • {title}"
        if due_date:
            dt = datetime.fromisoformat(due_date)
            result += f"\n   📅 Срок: {DateParser.format_dt(dt)}"
        if priority == 3:
            result += "\n   🔥 Приоритет: высокий"

        return result

    def list_tasks(self, status: str = "active") -> str:
        """Показать задачи."""
        tasks = get_tasks(status=status)

        if not tasks:
            return "📋 Задач нет. Отдыхай! 😌"

        result = f"📋 **Задачи ({len(tasks)}):**\n\n"
        for task in tasks:
            icon = "🔥" if task["priority"] == 3 else ("⭐" if task["priority"] == 2 else "•")
            line = f"{icon} [{task['id']}] {task['title']}"
            if task.get("due_date"):
                try:
                    dt = datetime.fromisoformat(task["due_date"])
                    line += f"\n     📅 {DateParser.format_dt(dt)}"
                except Exception:
                    pass
            result += line + "\n"

        return result

    def complete_task(self, task_id: int) -> str:
        """Отметить выполненной."""
        complete_task(task_id)
        return f"✅ Задача #{task_id} выполнена!"

    def delete_task(self, task_id: int) -> str:
        """Удалить задачу."""
        delete_task(task_id)
        return f"🗑️ Задача #{task_id} удалена."

    def get_stats(self) -> str:
        """Статистика."""
        stats = get_tasks_stats()
        return (
            f"📊 **Статистика:**\n"
            f"   • Всего задач: {stats['total']}\n"
            f"   • Активных: {stats['active']}\n"
            f"   • Выполнено: {stats['done']}"
        )

    # === СОБЫТИЯ ===

    def create_event(self, text: str) -> str:
        """Создать событие."""
        dt = DateParser.parse(text)

        if not dt:
            return (
                "⚠️ Не поняла когда.\n"
                "Скажи, например: «встреча завтра в 15:00»"
            )

        title = text
        for phrase in ["создай встречу", "добавь встречу", "новая встреча", "событие:", "встреча"]:
            title = title.lower().replace(phrase, "").strip()
        title = re.sub(r"\d{1,2}:\d{2}", "", title)
        title = re.sub(r"(завтра|сегодня|послезавтра|через\s+\d+\s+\w+)", "", title)
        title = re.sub(r"(в|на|до)\s+", "", title)
        title = title.strip(" ,.").capitalize()

        if not title:
            title = "Событие"

        add_event(title, dt.isoformat())

        return (
            f"✅ Встреча добавлена:\n"
            f"   • {title}\n"
            f"   📅 {DateParser.format_dt(dt)}"
        )

    def list_events(self, date: str = None) -> str:
        """Показать события."""
        events = get_events(date=date)

        if not events:
            if date:
                return f"📅 На {date} ничего нет."
            return "📅 Событий нет."

        result = f"📅 **События ({len(events)}):**\n\n"
        for ev in events:
            if ev.get("start_time"):
                try:
                    dt = datetime.fromisoformat(ev["start_time"])
                    result += f"• [{ev['id']}] {ev['title']}\n     🕐 {DateParser.format_dt(dt)}\n"
                except Exception:
                    result += f"• [{ev['id']}] {ev['title']}\n"
            else:
                result += f"• [{ev['id']}] {ev['title']}\n"

        return result

    def delete_event(self, event_id: int) -> str:
        delete_event(event_id)
        return f"🗑️ Событие #{event_id} удалено."

    # === РУТИНЫ ===

    def create_routine(self, name: str, actions: str, schedule: str) -> str:
        """Создать рутину."""
        add_routine(name, actions, schedule)
        return (
            f"✅ Рутина «{name}» создана:\n"
            f"   ⏰ {schedule}\n"
            f"   📋 {actions}"
        )

    def list_routines(self) -> str:
        """Показать рутины."""
        routines = get_routines()

        if not routines:
            return "🔁 Рутин нет. Хочешь создать?"

        result = "🔁 **Рутины:**\n\n"
        for r in routines:
            status = "✅" if r["enabled"] else "❌"
            result += f"{status} [{r['id']}] **{r['name']}**\n   ⏰ {r['schedule']}\n   📋 {r['actions']}\n"

        return result

    def delete_routine(self, routine_id: int) -> str:
        delete_routine(routine_id)
        return f"🗑️ Рутина #{routine_id} удалена."

    # === ОБЩЕЕ ===

    def show_today(self) -> str:
        """
        Показать всё на сегодня.
        ИСПРАВЛЕНО: проверка due_date на None.
        """
        today = datetime.now().strftime("%Y-%m-%d")

        result = f"📅 **Сегодня, {datetime.now().strftime('%d.%m.%Y')}:**\n\n"

        # === Задачи с сегодняшним дедлайном ===
        tasks = get_tasks(status="active")
        today_tasks = []
        for t in tasks:
            due = t.get("due_date")
            if due and due.startswith(today):
                today_tasks.append(t)

        if today_tasks:
            result += "**✅ Задачи:**\n"
            for t in today_tasks:
                result += f"  • [{t['id']}] {t['title']}\n"
            result += "\n"

        # === События на сегодня ===
        events = get_events(date=today)
        if events:
            result += "**📅 Встречи:**\n"
            for e in events:
                st = e.get("start_time")
                if st:
                    try:
                        dt = datetime.fromisoformat(st)
                        result += f"  • {dt.strftime('%H:%M')} — {e['title']}\n"
                    except Exception:
                        result += f"  • {e['title']}\n"
                else:
                    result += f"  • {e['title']}\n"
            result += "\n"

        if not today_tasks and not events:
            result += "Свободный день! 😎"

        return result


# ========== ГЛОБАЛЬНЫЙ ==========
_scheduler: Optional[Scheduler] = None


def get_scheduler() -> Scheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler


# ========== ТЕСТ ==========
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print("📅 Zeta Scheduler — Тест")
    print("=" * 60)

    sch = get_scheduler()

    # Парсер
    print("\n🔍 Парсер дат:")
    for text in ["завтра в 15:00", "через 30 минут", "в пятницу в 10:00", "в 20:00"]:
        dt = DateParser.parse(text)
        if dt:
            print(f"   '{text}' → {DateParser.format_dt(dt)}")
        else:
            print(f"   '{text}' → не поняла")

    # Создать задачу
    print("\n📝 Создаём задачу:")
    print(sch.create_task("Добавь задачу: отчёт до пятницы"))

    # Создать событие
    print("\n📅 Создаём встречу:")
    print(sch.create_event("Встреча завтра в 15:00"))

    # Список
    print("\n📋 Список задач:")
    print(sch.list_tasks())

    # Сегодня
    print("\n🕐 Сегодня:")
    print(sch.show_today())

    # Статистика
    print("\n📊 Статистика:")
    print(sch.get_stats())

    print("\n✅ Тест завершён!")