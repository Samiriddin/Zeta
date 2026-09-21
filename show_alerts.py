# -*- coding: utf-8 -*-
"""
IDS Viewer — просмотр алертов системы обнаружения вторжений Zeta.

Использование:
    python show_alerts.py                     # показать все алерты
    python show_alerts.py --analyze           # запустить новый анализ
    python show_alerts.py --limit 20          # показать последние 20
    python show_alerts.py --severity critical # только critical
    python show_alerts.py --clear             # очистить историю
    python show_alerts.py --stats             # только статистика

ИСПРАВЛЕНО (2026-09-21):
    - Убран несуществующий ключ 'last_check' из get_stats()
    - Добавлен UTF-8 для консоли
    - Добавлены аргументы командной строки
    - Добавлена обработка ImportError
    - Добавлен KeyboardInterrupt
    - Добавлены ANSI-цвета для severity
    - Показ running и check_interval
    - Обёртка в main()
"""

import sys
import argparse
from pathlib import Path

# UTF-8 для консоли Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Добавляем корень проекта
sys.path.insert(0, str(Path(__file__).parent))


# ========== ANSI ЦВЕТА ==========

class Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"

    @classmethod
    def disable(cls):
        """Отключить цвета (для Windows 7 или перенаправления)."""
        cls.RESET = ""
        cls.BOLD = ""
        cls.DIM = ""
        cls.RED = ""
        cls.GREEN = ""
        cls.YELLOW = ""
        cls.BLUE = ""
        cls.MAGENTA = ""
        cls.CYAN = ""
        cls.WHITE = ""


def _is_ansi_supported() -> bool:
    """Проверка, поддерживает ли терминал ANSI-цвета."""
    if not sys.stdout.isatty():
        return False
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            return True
        except Exception:
            return False
    return True


SEVERITY_COLORS = {
    "critical": Color.RED,
    "high": Color.MAGENTA,
    "medium": Color.YELLOW,
    "warning": Color.YELLOW,
    "low": Color.CYAN,
    "info": Color.BLUE,
}


def _colorize_severity(severity: str) -> str:
    """Раскрасить severity."""
    color = SEVERITY_COLORS.get(severity.lower(), Color.WHITE)
    return f"{color}{severity:10s}{Color.RESET}"


# ========== ФУНКЦИИ ==========

def print_stats(ids) -> None:
    """Печатает статистику IDS."""
    stats = ids.get_stats()

    print(f"\n{Color.BOLD}{Color.CYAN}📊 Статистика:{Color.RESET}")
    print(f"   Всего алертов:       {stats.get('total_alerts', 0)}")
    print(f"   Макс. в истории:     {stats.get('max_alerts', '?')}")
    print(f"   Запущен:             {'✅ да' if stats.get('running') else '❌ нет'}")
    print(f"   Интервал проверки:   {stats.get('check_interval', '?')} сек")
    print(f"   Обработано ключей:   {stats.get('processed_keys', 0)}")

    by_severity = stats.get("by_severity", {})
    if by_severity:
        print(f"   По уровням:")
        for sev, count in sorted(by_severity.items()):
            colored = _colorize_severity(sev)
            print(f"      {colored} — {count}")


def print_alerts(ids, limit: int = 50, severity_filter: str = None) -> None:
    """Печатает алерты."""
    alerts = ids.get_alerts(limit=limit)

    if severity_filter:
        alerts = [
            a for a in alerts
            if a.get("severity", "").lower() == severity_filter.lower()
        ]

    print(f"\n{Color.BOLD}{Color.CYAN}🚨 Алерты:{Color.RESET}")

    if not alerts:
        if severity_filter:
            print(f"   {Color.GREEN}✅ Нет алертов уровня '{severity_filter}'{Color.RESET}")
        else:
            print(f"   {Color.GREEN}✅ Алертов нет{Color.RESET}")
        return

    for i, a in enumerate(alerts, 1):
        severity = a.get("severity", "?")
        message = a.get("message", "?")
        timestamp = a.get("timestamp", "?")[:19]
        recommendation = a.get("recommendation", "—")
        alert_type = a.get("type", "?")
        count = a.get("count", 0)

        colored_sev = _colorize_severity(severity)

        print(f"\n   {Color.BOLD}#{i}{Color.RESET}  [{colored_sev}]  {message}")
        print(f"        {Color.DIM}Тип:      {alert_type}{Color.RESET}")
        print(f"        {Color.DIM}Время:    {timestamp}{Color.RESET}")
        if count:
            print(f"        {Color.DIM}Событий:  {count}{Color.RESET}")
        print(f"        {Color.DIM}Совет:    {recommendation}{Color.RESET}")


def run_analysis(ids) -> int:
    """Запустить новый анализ."""
    print(f"\n{Color.BOLD}{Color.CYAN}🔍 Новый анализ...{Color.RESET}")

    try:
        new_alerts = ids.analyze()
    except Exception as e:
        print(f"   {Color.RED}❌ Ошибка анализа: {e}{Color.RESET}")
        return 0

    if new_alerts:
        print(f"   {Color.YELLOW}⚠️ Обнаружено {len(new_alerts)} новых алертов{Color.RESET}")
        for a in new_alerts:
            sev = a.get("severity", "?")
            msg = a.get("message", "?")
            print(f"      [{_colorize_severity(sev)}] {msg}")
    else:
        print(f"   {Color.GREEN}✅ Ничего нового не обнаружено{Color.RESET}")

    return len(new_alerts)


def clear_alerts(ids) -> None:
    """Очистить историю алертов."""
    try:
        ids.clear_alerts()
        print(f"{Color.GREEN}✅ История алертов очищена{Color.RESET}")
    except Exception as e:
        print(f"{Color.RED}❌ Ошибка очистки: {e}{Color.RESET}")


# ========== MAIN ==========

def main() -> int:
    # ANSI-цвета
    if not _is_ansi_supported():
        Color.disable()

    # Аргументы
    parser = argparse.ArgumentParser(
        description="IDS Viewer — просмотр алертов обнаружения вторжений Zeta",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
    python show_alerts.py                       показать все алерты
    python show_alerts.py --analyze             запустить новый анализ
    python show_alerts.py --limit 20            последние 20
    python show_alerts.py --severity critical   только critical
    python show_alerts.py --stats               только статистика
    python show_alerts.py --clear               очистить историю
        """,
    )
    parser.add_argument("--analyze", action="store_true", help="Запустить новый анализ")
    parser.add_argument("--limit", type=int, default=50, help="Сколько алертов показать (по умолчанию 50)")
    parser.add_argument("--severity", type=str, default=None,
                        help="Фильтр по уровню: critical/high/medium/low/info")
    parser.add_argument("--stats", action="store_true", help="Только статистика")
    parser.add_argument("--clear", action="store_true", help="Очистить историю")
    parser.add_argument("--no-color", action="store_true", help="Отключить цвета")

    args = parser.parse_args()

    if args.no_color:
        Color.disable()

    # Импорт IDS
    try:
        from security.intrusion_detector import get_ids
    except ImportError as e:
        print(f"{Color.RED}❌ Модуль IDS не найден: {e}{Color.RESET}")
        print(f"   Проверь, что файл security/intrusion_detector.py существует")
        return 1

    ids = get_ids()

    # Заголовок
    print(f"{Color.BOLD}{Color.MAGENTA}🚨 Zeta IDS — Алерты{Color.RESET}")
    print("=" * 60)

    # Команды
    if args.clear:
        clear_alerts(ids)
        return 0

    if args.analyze:
        run_analysis(ids)
        print()
        print_stats(ids)
        return 0

    if args.stats:
        print_stats(ids)
        return 0

    # По умолчанию: статистика + алерты
    print_stats(ids)
    print_alerts(ids, limit=args.limit, severity_filter=args.severity)

    print(f"\n{Color.DIM}{'=' * 60}{Color.RESET}")
    print(f"{Color.DIM}💡 Совет: запусти с --analyze, чтобы проверить новые события{Color.RESET}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n\n{Color.YELLOW}⏹️ Прервано пользователем{Color.RESET}")
        sys.exit(130)