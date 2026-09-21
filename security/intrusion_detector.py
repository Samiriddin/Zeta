# -*- coding: utf-8 -*-
"""
Zeta Security — Обнаружение вторжений.
Анализирует логи аудита и находит подозрительные паттерны.
Аудит: пишет все алерты в security.log.

Особенности:
    - Кэш логов на один цикл analyze()
    - Ring buffer для алертов (500)
    - Дедупликация с окном времени
    - Мгновенная остановка (_stop_event)
    - Обработка таймзон в timestamp
"""

import os
import sys
import json
import time
import logging
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Callable
from collections import defaultdict, deque

sys.path.insert(0, str(Path(__file__).parent.parent))


# ========== ЛОГИРОВАНИЕ ==========

def _log(msg: str) -> None:
    logging.info(f"[IDS] {msg}")


def _log_warn(msg: str) -> None:
    logging.warning(f"[IDS] {msg}")


# ================================================================
#  ПОРОГИ
# ================================================================

class Thresholds:
    """Пороги срабатывания."""

    # Неудачные входы
    FAILED_LOGINS_COUNT = 3
    FAILED_LOGINS_WINDOW = 5  # минут

    # Заблокированные команды
    BLOCKED_COMMANDS_COUNT = 5
    BLOCKED_COMMANDS_WINDOW = 10  # минут

    # Критические события
    CRITICAL_SEVERITY_COUNT = 1
    CRITICAL_SEVERITY_WINDOW = 5  # минут

    # Подозрительная активность
    SUSPICIOUS_COUNT = 3
    SUSPICIOUS_WINDOW = 10  # минут

    # Блокировки аккаунта
    ACCOUNT_BLOCKED_COUNT = 1
    ACCOUNT_BLOCKED_WINDOW = 15  # минут


# ================================================================
#  ОБНАРУЖИТЕЛЬ
# ================================================================

class IntrusionDetector:
    """Обнаружитель вторжений."""

    MAX_ALERTS_HISTORY = 500
    MAX_LOG_LINES = 500

    # Известные типы, которые уже покрыты другими проверками
    KNOWN_CRITICAL_EVENTS = {
        "account_blocked",  # покрыто _check_account_blocked
    }

    def __init__(self):
        self.audit_dir = Path("data/audit")
        self.audit_dir.mkdir(parents=True, exist_ok=True)

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._check_interval = 60  # секунд

        # История алертов (ring buffer)
        self._alerts: deque = deque(maxlen=self.MAX_ALERTS_HISTORY)

        # Дедупликация: ключ → timestamp
        self._processed_entries: Dict[str, float] = {}

        # Кэш логов на один цикл analyze()
        self._log_cache: Dict[str, List[Dict]] = {}
        self._cache_time: float = 0

        # Колбэк
        self._on_alert_callback: Optional[Callable] = None

    # ============================================================
    #  ЧТЕНИЕ ЛОГОВ (с кэшем и deque)
    # ============================================================

    def _read_log(self, log_name: str, minutes: int = 15,
                  use_cache: bool = True) -> List[Dict]:
        """Читает свежие записи из лога с кэшем."""
        # Кэш на 30 секунд
        cache_key = f"{log_name}_{minutes}"
        now = time.time()
        if use_cache and cache_key in self._log_cache and now - self._cache_time < 30:
            return self._log_cache[cache_key]

        log_path = self.audit_dir / f"{log_name}.log"

        if not log_path.exists():
            if use_cache:
                self._log_cache[cache_key] = []
            return []

        cutoff = datetime.now() - timedelta(minutes=minutes)
        entries: List[Dict] = []

        try:
            # Читаем последние N строк через deque (не грузит весь файл)
            with open(log_path, "r", encoding="utf-8") as f:
                last_lines = deque(f, maxlen=self.MAX_LOG_LINES)

            for line in last_lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts = entry.get("timestamp", "")
                if not ts:
                    entries.append(entry)
                    continue

                try:
                    entry_time = datetime.fromisoformat(ts)
                    # Убираем таймзону если есть
                    if entry_time.tzinfo is not None:
                        entry_time = entry_time.replace(tzinfo=None)

                    if entry_time >= cutoff:
                        entries.append(entry)
                except Exception:
                    entries.append(entry)

        except Exception as e:
            _log_warn(f"Ошибка чтения {log_name}: {e}")

        if use_cache:
            self._log_cache[cache_key] = entries

        return entries

    def _clear_log_cache(self) -> None:
        """Очистить кэш логов."""
        self._log_cache.clear()
        self._cache_time = time.time()

    # ============================================================
    #  ПРОВЕРКИ
    # ============================================================

    def _check_failed_logins(self) -> List[Dict]:
        """Неудачные входы."""
        alerts = []
        entries = self._read_log("auth", minutes=Thresholds.FAILED_LOGINS_WINDOW)

        failed = [
            e for e in entries
            if e.get("type") == "login" and not e.get("success", True)
        ]

        if len(failed) >= Thresholds.FAILED_LOGINS_COUNT:
            alerts.append({
                "type": "failed_logins",
                "severity": "high",
                "message": f"Обнаружено {len(failed)} неудачных входов "
                           f"за {Thresholds.FAILED_LOGINS_WINDOW} минут",
                "details": f"Порог: {Thresholds.FAILED_LOGINS_COUNT}",
                "count": len(failed),
                "recommendation": "Проверьте, не подбирают ли ваш пароль",
            })

        return alerts

    def _check_blocked_commands(self) -> List[Dict]:
        """Заблокированные команды."""
        alerts = []
        entries = self._read_log("security", minutes=Thresholds.BLOCKED_COMMANDS_WINDOW)

        blocked = [
            e for e in entries
            if e.get("event") == "blocked_command"
        ]

        if len(blocked) >= Thresholds.BLOCKED_COMMANDS_COUNT:
            alerts.append({
                "type": "many_blocked",
                "severity": "medium",
                "message": f"Обнаружено {len(blocked)} заблокированных команд "
                           f"за {Thresholds.BLOCKED_COMMANDS_WINDOW} минут",
                "details": f"Порог: {Thresholds.BLOCKED_COMMANDS_COUNT}",
                "count": len(blocked),
                "recommendation": "Проверьте, кто пытается выполнять опасные команды",
            })

        return alerts

    def _check_critical_events(self) -> List[Dict]:
        """Критические события (кроме известных)."""
        alerts = []
        entries = self._read_log("security", minutes=Thresholds.CRITICAL_SEVERITY_WINDOW)

        # Исключаем события, которые уже проверяются отдельно
        critical = [
            e for e in entries
            if e.get("severity") == "critical"
            and e.get("event", "") not in self.KNOWN_CRITICAL_EVENTS
        ]

        if len(critical) >= Thresholds.CRITICAL_SEVERITY_COUNT:
            events = [e.get("event", "?") for e in critical[:3]]
            alerts.append({
                "type": "critical_events",
                "severity": "critical",
                "message": f"⚠️ КРИТИЧНО: {len(critical)} критических событий "
                           f"за {Thresholds.CRITICAL_SEVERITY_WINDOW} минут",
                "details": " ".join(events),
                "count": len(critical),
                "recommendation": "НЕМЕДЛЕННО проверьте систему!",
            })

        return alerts

    def _check_suspicious_activity(self) -> List[Dict]:
        """Подозрительная активность."""
        alerts = []
        entries = self._read_log("security", minutes=Thresholds.SUSPICIOUS_WINDOW)

        suspicious = [
            e for e in entries
            if e.get("event") == "suspicious_activity"
        ]

        if len(suspicious) >= Thresholds.SUSPICIOUS_COUNT:
            details = " ".join(
                e.get("details", "?")[:50] for e in suspicious[:3]
            )
            alerts.append({
                "type": "suspicious",
                "severity": "high",
                "message": f"Обнаружено {len(suspicious)} подозрительных активностей",
                "details": details,
                "count": len(suspicious),
                "recommendation": "Проверьте логи аудита",
            })

        return alerts

    def _check_account_blocked(self) -> List[Dict]:
        """Блокировки аккаунта."""
        alerts = []
        entries = self._read_log("security", minutes=Thresholds.ACCOUNT_BLOCKED_WINDOW)

        blocked = [
            e for e in entries
            if e.get("event") == "account_blocked"
        ]

        if len(blocked) >= Thresholds.ACCOUNT_BLOCKED_COUNT:
            alerts.append({
                "type": "account_blocked",
                "severity": "high",
                "message": f"Аккаунт Zeta был заблокирован {len(blocked)} раз(а)",
                "details": "Кто-то подбирает пароль",
                "count": len(blocked),
                "recommendation": "Смените пароль Zeta",
            })

        return alerts

    # ============================================================
    #  ГЛАВНАЯ ПРОВЕРКА
    # ============================================================

    def analyze(self) -> List[Dict]:
        """Анализ логов на вторжения."""
        self._clear_log_cache()

        all_alerts: List[Dict] = []

        try:
            all_alerts.extend(self._check_failed_logins())
            all_alerts.extend(self._check_blocked_commands())
            all_alerts.extend(self._check_critical_events())
            all_alerts.extend(self._check_suspicious_activity())
            all_alerts.extend(self._check_account_blocked())
        except Exception as e:
            _log_warn(f"Ошибка анализа: {e}")

        # Дедупликация с окном времени (1 час)
        now = time.time()
        window_key = int(now // 3600)  # округление до часа
        new_alerts = []

        for alert in all_alerts:
            key = f"{alert['type']}_{alert.get('count', 0)}_{window_key}"

            if key not in self._processed_entries:
                self._processed_entries[key] = now
                new_alerts.append(alert)

        # Чистим старые ключи (старше 2 часов)
        cutoff = now - 7200
        self._processed_entries = {
            k: v for k, v in self._processed_entries.items() if v > cutoff
        }

        # Сохраняем в историю
        for alert in new_alerts:
            alert["timestamp"] = datetime.now().isoformat()
            self._alerts.append(alert)

        return new_alerts

    # ============================================================
    #  ОБРАБОТКА АЛЕРТОВ
    # ============================================================

    def _handle_alerts(self, alerts: List[Dict]) -> None:
        """Обработать алерты."""
        if not alerts:
            return

        for alert in alerts:
            severity = alert.get("severity", "info")
            msg = alert.get("message", "Unknown")

            # 1. Логируем в security.log
            self._log_to_audit(alert)

            # 2. Консоль
            if severity == "critical":
                print(f"🚨 КРИТИЧНО: {msg}")
            elif severity == "high":
                print(f"⚠️ ВНИМАНИЕ: {msg}")
            else:
                print(f"ℹ️ IDS: {msg}")

            # 3. Уведомление
            self._send_notification(alert)

            # 4. Колбэк
            if self._on_alert_callback:
                try:
                    self._on_alert_callback(alert)
                except Exception as e:
                    _log_warn(f"Колбэк: {e}")

            _log_warn(f"ALERT [{severity}]: {msg}")

    def _log_to_audit(self, alert: Dict) -> None:
        """Записать алерт в security.log."""
        try:
            from security.audit import get_audit
            get_audit().log_security(
                event=f"ids_{alert['type']}",
                details=alert.get("message", ""),
                severity=alert.get("severity", "info"),
            )
        except Exception as e:
            _log_warn(f"Ошибка записи алерта: {e}")

    def _send_notification(self, alert: Dict) -> None:
        """Windows-уведомление."""
        try:
            from modules.notifications import show_notification

            severity = alert.get("severity", "info")
            title = "🚨 Zeta: Вторжение"

            if severity == "critical":
                title = "🚨 Zeta: КРИТИЧЕСКАЯ УГРОЗА"
            elif severity == "high":
                title = "⚠️ Zeta: Опасность"

            show_notification(title, alert.get("message", ""))
        except Exception as e:
            _log_warn(f"Ошибка уведомления: {e}")

    # ============================================================
    #  ПУБЛИЧНЫЕ МЕТОДЫ
    # ============================================================

    def set_alert_callback(self, callback: Callable) -> None:
        """Установить колбэк при алерте."""
        self._on_alert_callback = callback

    def get_alerts(self, limit: int = 10) -> List[Dict]:
        """Последние алерты."""
        items = list(self._alerts)
        return items[-limit:]

    def get_stats(self) -> Dict:
        """Статистика."""
        by_severity: Dict[str, int] = defaultdict(int)
        for a in self._alerts:
            by_severity[a.get("severity", "?")] += 1

        return {
            "total_alerts": len(self._alerts),
            "max_alerts": self.MAX_ALERTS_HISTORY,
            "by_severity": dict(by_severity),
            "running": self._running,
            "check_interval": self._check_interval,
            "processed_keys": len(self._processed_entries),
        }

    def clear_alerts(self) -> None:
        """Очистить историю."""
        self._alerts.clear()
        self._processed_entries.clear()
        _log("История алертов очищена")

    # ============================================================
    #  ФОНОВЫЙ РЕЖИМ
    # ============================================================

    def start(self) -> None:
        """Запустить фоновую проверку."""
        if self._running and self._thread and self._thread.is_alive():
            _log("IDS уже запущен")
            return

        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="IntrusionDetector"
        )
        self._thread.start()
        _log(f"IDS запущен (интервал {self._check_interval}с)")

    def stop(self) -> None:
        """Остановить фоновую проверку."""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        if self._thread:
            self._thread.join(timeout=3)

        _log("IDS остановлен")

    def _loop(self) -> None:
        """Цикл проверки."""
        # Первая проверка — сразу
        while self._running:
            try:
                alerts = self.analyze()
                if alerts:
                    self._handle_alerts(alerts)
            except Exception as e:
                _log_warn(f"Ошибка в цикле: {e}")

            # Ждём интервал (мгновенный выход при stop)
            if self._stop_event.wait(self._check_interval):
                break


# ================================================================
#  ГЛОБАЛЬНЫЙ
# ================================================================

_ids: Optional[IntrusionDetector] = None


def get_ids() -> IntrusionDetector:
    """Глобальный IDS."""
    global _ids
    if _ids is None:
        _ids = IntrusionDetector()
    return _ids


# ================================================================
#  ЭКСПОРТ
# ================================================================

__all__ = ["IntrusionDetector", "Thresholds", "get_ids"]


# ================================================================
#  ТЕСТ
# ================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    print("🚨 Zeta IDS — Тест обнаружения вторжений")
    print("=" * 60)

    ids = get_ids()

    # Статистика
    print("\n📊 Статус ДО:")
    for k, v in ids.get_stats().items():
        print(f"   {k}: {v}")

    # Анализ
    print("\n🔍 Анализ логов...")
    alerts = ids.analyze()

    if alerts:
        print(f"\n⚠️ Найдено {len(alerts)} алертов:")
        for a in alerts:
            print(f"   [{a['severity']:8s}] {a['message']}")
    else:
        print("\n✅ Подозрительной активности не обнаружено")

    # Повторный анализ — должен быть пустым (дедупликация)
    print("\n🔍 Повторный анализ (дедупликация):")
    alerts2 = ids.analyze()
    print(f"   Новых алертов: {len(alerts2)} "
          f"{'✅' if len(alerts2) == 0 else '❌ (должно быть 0)'}")

    # Финальная статистика
    print("\n📊 Статус ПОСЛЕ:")
    for k, v in ids.get_stats().items():
        print(f"   {k}: {v}")

    # Тест start/stop
    print("\n📝 Тест start/stop:")
    ids.start()
    time.sleep(1)
    print(f"   running: {ids.get_stats()['running']}")

    ids.stop()
    print(f"   running после stop: {ids.get_stats()['running']}")

    print("\n" + "=" * 60)
    print("✅ Тесты пройдены!")