# -*- coding: utf-8 -*-
"""
Умные уведомления для Zeta.
Мониторит систему и отправляет уведомления при перегрузках.
Поддерживает: CPU, RAM, диск, температуру, сеть.

Особенности:
    - Дедупликация по типу (CPU, RAM, DISK, TEMP — независимо)
    - Мгновенная остановка через Event
    - Логирование в общий data/zeta.log
    - check_interval из настроек Zeta
    - Первая проверка — через 60 сек (не сразу)

ИСПРАВЛЕНО (2026-09-21):
    - show_test_notification() — публичная функция для settings.py
    - Fallback на Windows-уведомление, если нет callbacks
    - Кэш температуры (WMI медленный)
    - Автоопределение системного диска (не хардкод C:\)
    - get_thresholds() — getter порогов
    - is_overloaded_strict() — отдельно для «реальной» перегрузки
"""

import os
import time
import logging
import threading
from datetime import datetime
from typing import Optional, Callable, Dict, List, Any
from dataclasses import dataclass

import psutil


# ========== ЛОГИРОВАНИЕ ==========

logger = logging.getLogger("zeta.smart")


def _log(msg: str) -> None:
    logger.info(f"[SMART] {msg}")


def _log_warn(msg: str) -> None:
    logger.warning(f"[SMART] {msg}")


# ========== СИСТЕМНЫЙ ДИСК ==========

def _get_system_drive() -> str:
    """
    ИСПРАВЛЕНО: определяем системный диск, не хардкодим C:\\.
    """
    if os.name == "nt":
        drive = os.environ.get("SystemDrive", "C:")
        return drive + "\\"
    return "/"


# ========== ДАТАКЛАСС ==========

@dataclass
class SystemStatus:
    """Состояние системы."""
    cpu: float = 0.0
    cpu_cores: int = 0
    ram: float = 0.0
    ram_used_gb: float = 0.0
    ram_total_gb: float = 0.0
    disk: float = 0.0
    disk_used_gb: float = 0.0
    disk_total_gb: float = 0.0
    temperature: Optional[float] = None
    uptime: str = ""
    time: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu": self.cpu,
            "cpu_cores": self.cpu_cores,
            "ram": self.ram,
            "ram_used_gb": self.ram_used_gb,
            "ram_total_gb": self.ram_total_gb,
            "disk": self.disk,
            "disk_used_gb": self.disk_used_gb,
            "disk_total_gb": self.disk_total_gb,
            "temperature": self.temperature,
            "uptime": self.uptime,
            "time": self.time,
        }

    def is_overloaded(self, cpu_threshold: float = 80,
                      ram_threshold: float = 85,
                      disk_threshold: float = 90) -> bool:
        """
        Общая проверка (для совместимости).
        RAM-порог обычно высокий, т.к. RAM 85% — норма.
        """
        return (self.cpu > cpu_threshold or
                self.ram > ram_threshold or
                self.disk > disk_threshold)

    def is_overloaded_strict(self) -> bool:
        """
        ИСПРАВЛЕНО: строгая проверка — CPU 90+, RAM 95+, диск 95+.
        Это «реальная» перегрузка.
        """
        return (self.cpu > 90 or self.ram > 95 or self.disk > 95)


# ========== ОСНОВНОЙ КЛАСС ==========

class SmartNotifier:
    """Фоновый мониторинг системы с отправкой уведомлений."""

    # Кэш температуры: живёт 30 секунд
    TEMP_CACHE_TTL = 30

    def __init__(self):
        self.is_running = False
        self.thread: Optional[threading.Thread] = None
        self.callbacks: List[Callable] = []
        self.last_status: Optional[SystemStatus] = None
        self.last_status_time: float = 0

        # Пороги
        self.cpu_threshold = 80
        self.ram_threshold = 85
        self.disk_threshold = 90
        self.temp_threshold = 80

        # Интервал
        self.check_interval = 60

        # Флаги: уже предупредили о перегрузке?
        self._warned_cpu = False
        self._warned_ram = False
        self._warned_disk = False
        self._warned_temp = False

        # Дедупликация по типу
        self._last_notification_time: Dict[str, float] = {}
        self._notification_cooldown = 60

        # Для мгновенной остановки
        self._stop_event = threading.Event()

        # ИСПРАВЛЕНО: кэш температуры
        self._temp_cache: Optional[float] = None
        self._temp_cache_time: float = 0

    # ========== CALLBACK ==========

    def add_callback(self, callback: Callable) -> None:
        if callback not in self.callbacks:
            self.callbacks.append(callback)
            _log(f"Добавлен callback: {getattr(callback, '__name__', callback)}")

    def remove_callback(self, callback: Callable) -> None:
        if callback in self.callbacks:
            self.callbacks.remove(callback)

    def _notify(self, title: str, message: str, ntype: str = "common",
                force: bool = False) -> bool:
        """
        Отправляет уведомление с дедупликацией по типу.

        ИСПРАВЛЕНО:
            - force=True — обходит кулдаун (для тестов)
            - Возвращает True если уведомление отправлено
            - Если нет callback'ов — fallback на Windows-уведомление
        """
        current_time = time.time()
        last = self._last_notification_time.get(ntype, 0)

        if not force and current_time - last < self._notification_cooldown:
            logger.debug(f"Пропуск уведомления [{ntype}] (кулдаун)")
            return False

        self._last_notification_time[ntype] = current_time

        sent = False

        # 1. Callbacks
        for callback in self.callbacks:
            try:
                callback(title, message)
                sent = True
            except Exception as e:
                _log_warn(f"Ошибка в callback: {e}")

        # 2. ИСПРАВЛЕНО: fallback на Windows-уведомление
        if not sent:
            try:
                from modules.notifications import show_notification
                show_notification(title, message)
                sent = True
            except Exception as e:
                _log_warn(f"Fallback-уведомление не сработало: {e}")

        return sent

    # ========== СИСТЕМА ==========

    def _get_system_status(self) -> SystemStatus:
        """Получает текущий статус системы."""
        try:
            cpu = psutil.cpu_percent(interval=0.5)
            cpu_cores = psutil.cpu_count() or 0

            mem = psutil.virtual_memory()
            ram = mem.percent
            ram_used_gb = mem.used / (1024 ** 3)
            ram_total_gb = mem.total / (1024 ** 3)

            # ИСПРАВЛЕНО: системный диск, не хардкод C:\
            system_drive = _get_system_drive()
            disk = psutil.disk_usage(system_drive)
            disk_percent = disk.percent
            disk_used_gb = disk.used / (1024 ** 3)
            disk_total_gb = disk.total / (1024 ** 3)

            temp = self._get_temperature()
            uptime = self._format_uptime(psutil.boot_time())

            return SystemStatus(
                cpu=cpu,
                cpu_cores=cpu_cores,
                ram=ram,
                ram_used_gb=ram_used_gb,
                ram_total_gb=ram_total_gb,
                disk=disk_percent,
                disk_used_gb=disk_used_gb,
                disk_total_gb=disk_total_gb,
                temperature=temp,
                uptime=uptime,
                time=datetime.now().strftime("%H:%M:%S"),
            )
        except Exception as e:
            _log_warn(f"Ошибка получения статуса: {e}")
            return SystemStatus()

    def _get_temperature(self) -> Optional[float]:
        """
        Температура CPU. Только Windows + OpenHardwareMonitor.

        ИСПРАВЛЕНО: кэш на TEMP_CACHE_TTL секунд (WMI медленный).
        """
        now = time.time()

        # ИСПРАВЛЕНО: возвращаем кэш
        if (self._temp_cache is not None and
                now - self._temp_cache_time < self.TEMP_CACHE_TTL):
            return self._temp_cache

        temp = None
        try:
            import wmi
            w = wmi.WMI(namespace="root\\OpenHardwareMonitor")
            for sensor in w.Sensor():
                if sensor.Name == "CPU Package" and sensor.SensorType == "Temperature":
                    temp = float(sensor.Value)
                    break
        except Exception:
            pass

        # Обновляем кэш
        self._temp_cache = temp
        self._temp_cache_time = now
        return temp

    def _format_uptime(self, boot_time: float) -> str:
        uptime = time.time() - boot_time
        days = int(uptime // 86400)
        hours = int((uptime % 86400) // 3600)
        minutes = int((uptime % 3600) // 60)
        if days > 0:
            return f"{days}д {hours}ч {minutes}м"
        elif hours > 0:
            return f"{hours}ч {minutes}м"
        return f"{minutes}м"

    def _check_system(self) -> Optional[SystemStatus]:
        """Проверяет систему, отправляет уведомления."""
        try:
            status = self._get_system_status()
            self.last_status = status
            self.last_status_time = time.time()

            # CPU
            if status.cpu > self.cpu_threshold and not self._warned_cpu:
                self._warned_cpu = True
                self._notify(
                    "⚠️ Перегрузка CPU",
                    f"Загрузка процессора: {status.cpu:.1f}%\nВремя: {status.time}",
                    ntype="cpu",
                )
            elif status.cpu <= self.cpu_threshold:
                self._warned_cpu = False

            # RAM
            if status.ram > self.ram_threshold and not self._warned_ram:
                self._warned_ram = True
                self._notify(
                    "⚠️ Перегрузка RAM",
                    f"Использование памяти: {status.ram:.1f}%\n"
                    f"Использовано: {status.ram_used_gb:.1f}GB / {status.ram_total_gb:.1f}GB\n"
                    f"Время: {status.time}",
                    ntype="ram",
                )
            elif status.ram <= self.ram_threshold:
                self._warned_ram = False

            # DISK
            if status.disk > self.disk_threshold and not self._warned_disk:
                self._warned_disk = True
                self._notify(
                    "⚠️ Переполнение диска",
                    f"Заполнение системного диска: {status.disk:.1f}%\n"
                    f"Свободно: {status.disk_total_gb - status.disk_used_gb:.1f}GB\n"
                    f"Время: {status.time}",
                    ntype="disk",
                )
            elif status.disk <= self.disk_threshold:
                self._warned_disk = False

            # TEMP
            if (status.temperature and
                    status.temperature > self.temp_threshold and
                    not self._warned_temp):
                self._warned_temp = True
                self._notify(
                    "🌡️ Перегрев CPU",
                    f"Температура процессора: {status.temperature:.1f}°C\n"
                    f"Время: {status.time}",
                    ntype="temp",
                )
            elif status.temperature and status.temperature <= self.temp_threshold:
                self._warned_temp = False

            return status

        except Exception as e:
            _log_warn(f"Ошибка мониторинга: {e}")
            return None

    def _run(self):
        """Основной цикл."""
        _log(f"Умные уведомления запущены (интервал: {self.check_interval}с)")

        # Первая проверка — через check_interval
        if self._stop_event.wait(self.check_interval):
            return

        while self.is_running:
            try:
                self._check_system()
            except Exception as e:
                _log_warn(f"Ошибка в цикле: {e}")

            if self._stop_event.wait(self.check_interval):
                break

    # ========== УПРАВЛЕНИЕ ==========

    def start(self):
        """Запускает мониторинг."""
        if self.is_running:
            _log_warn("Мониторинг уже запущен")
            return

        self.is_running = True
        self._stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True, name="SmartNotifier")
        self.thread.start()
        _log("Умные уведомления запущены")

    def stop(self):
        """Останавливает мониторинг (мгновенно)."""
        if not self.is_running:
            return

        self.is_running = False
        self._stop_event.set()

        if self.thread:
            self.thread.join(timeout=3)

        _log("Умные уведомления остановлены")

    def restart(self):
        """Перезапускает мониторинг."""
        self.stop()
        time.sleep(0.5)
        self.start()

    # ========== ПОЛУЧЕНИЕ ДАННЫХ ==========

    def get_status(self, force_refresh: bool = False) -> SystemStatus:
        """Возвращает статус."""
        now = time.time()
        stale = (now - self.last_status_time) > (self.check_interval * 2)

        if force_refresh or self.last_status is None or stale:
            self.last_status = self._get_system_status()
            self.last_status_time = now

        return self.last_status

    def get_last_status_dict(self) -> Dict[str, Any]:
        return self.get_status().to_dict()

    def get_summary(self) -> str:
        status = self.get_status()
        lines = [
            f"📊 **Состояние системы** ({status.time})",
            "",
            f"💻 **CPU:** {status.cpu:.1f}% ({status.cpu_cores} ядер)",
            f"🧠 **RAM:** {status.ram:.1f}% ({status.ram_used_gb:.1f}GB / {status.ram_total_gb:.1f}GB)",
            f"💾 **Диск:** {status.disk:.1f}% ({status.disk_used_gb:.1f}GB / {status.disk_total_gb:.1f}GB)",
        ]
        if status.temperature:
            lines.append(f"🌡️ **Температура:** {status.temperature:.1f}°C")
        lines.append(f"⏱️ **Время работы:** {status.uptime}")
        return "\n".join(lines)

    def is_overloaded(self) -> bool:
        """Общая проверка (низкий порог)."""
        status = self.get_status()
        return status.is_overloaded(
            self.cpu_threshold,
            self.ram_threshold,
            self.disk_threshold,
        )

    def is_overloaded_strict(self) -> bool:
        """
        ИСПРАВЛЕНО: строгая проверка — реальная перегрузка.
        """
        status = self.get_status()
        return status.is_overloaded_strict()

    # ========== НАСТРОЙКА ==========

    def set_thresholds(self, cpu: int = 80, ram: int = 85,
                       disk: int = 90, temp: int = 80):
        self.cpu_threshold = max(30, min(95, cpu))
        self.ram_threshold = max(30, min(95, ram))
        self.disk_threshold = max(30, min(95, disk))
        self.temp_threshold = max(50, min(100, temp))
        _log(f"Пороги: CPU={cpu}%, RAM={ram}%, DISK={disk}%, TEMP={temp}°C")

    def get_thresholds(self) -> Dict[str, int]:
        """
        ИСПРАВЛЕНО: getter порогов (для настроек).
        """
        return {
            "cpu": self.cpu_threshold,
            "ram": self.ram_threshold,
            "disk": self.disk_threshold,
            "temp": self.temp_threshold,
        }

    def set_interval(self, seconds: int):
        self.check_interval = max(5, min(300, seconds))
        _log(f"Интервал: {self.check_interval}с")

    def get_interval(self) -> int:
        return self.check_interval

    # ========== ТЕСТ ИЗ НАСТРОЕК ==========

    def test_notification(self) -> bool:
        """
        ИСПРАВЛЕНО: публичный метод для теста уведомления.
        """
        return self._notify(
            "🔔 Тест уведомления",
            "Это тестовое уведомление от Zeta!",
            ntype="test",
            force=True,  # обходим кулдаун
        )


# ========== ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР ==========

_notifier = SmartNotifier()


def start_notifier():
    """Запускает умные уведомления."""
    _notifier.start()


def stop_notifier():
    """Останавливает умные уведомления."""
    _notifier.stop()


def restart_notifier():
    """Перезапускает умные уведомления."""
    _notifier.restart()


def get_system_status() -> dict:
    """Статус системы как словарь."""
    return _notifier.get_last_status_dict()


def get_system_summary() -> str:
    """Краткая сводка состояния системы."""
    return _notifier.get_summary()


def is_system_overloaded() -> bool:
    """Проверяет, перегружена ли система (общая)."""
    return _notifier.is_overloaded()


def is_system_overloaded_strict() -> bool:
    """ИСПРАВЛЕНО: строгая проверка — реальная перегрузка."""
    return _notifier.is_overloaded_strict()


def set_thresholds(cpu: int = 80, ram: int = 85, disk: int = 90, temp: int = 80):
    _notifier.set_thresholds(cpu, ram, disk, temp)


def get_thresholds() -> dict:
    """ИСПРАВЛЕНО: getter порогов."""
    return _notifier.get_thresholds()


def set_check_interval(seconds: int = 60):
    _notifier.set_interval(seconds)


def get_check_interval() -> int:
    return _notifier.get_interval()


def add_notification_callback(callback: Callable):
    _notifier.add_callback(callback)


def remove_notification_callback(callback: Callable):
    _notifier.remove_callback(callback)


def show_test_notification() -> bool:
    """
    ИСПРАВЛЕНО: публичная функция для settings.py.
    Возвращает True, если уведомление отправлено.
    """
    return _notifier.test_notification()


# ========== ЭКСПОРТ ==========

__all__ = [
    "SmartNotifier",
    "SystemStatus",
    "start_notifier",
    "stop_notifier",
    "restart_notifier",
    "get_system_status",
    "get_system_summary",
    "is_system_overloaded",
    "is_system_overloaded_strict",
    "set_thresholds",
    "get_thresholds",
    "set_check_interval",
    "get_check_interval",
    "add_notification_callback",
    "remove_notification_callback",
    "show_test_notification",
]


# ========== ТЕСТ ==========

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    def test_callback(title, message):
        print(f"\n🔔 {title}\n{message}\n")

    print("🧪 Тест SmartNotifier\n")
    print("=" * 60)

    add_notification_callback(test_callback)

    print("\n📝 Тест 1: Запуск")
    start_notifier()

    print("\n📝 Тест 2: Статус (сразу)")
    print(get_system_summary())

    print("\n📝 Тест 3: Проверка перегрузки")
    print(f"Перегружена (общая): {is_system_overloaded()}")
    print(f"Перегружена (строгая): {is_system_overloaded_strict()}")

    print("\n📝 Тест 4: Настройка порогов")
    set_thresholds(cpu=10, ram=10, disk=10)
    print(f"Пороги: {get_thresholds()}")

    print("\n📝 Тест 5: Проверка (через 3 сек)")
    time.sleep(3)
    print(get_system_summary())

    print("\n📝 Тест 6: Тестовое уведомление")
    ok = show_test_notification()
    print(f"   Уведомление отправлено: {ok}")

    print("\n📝 Тест 7: Остановка")
    stop_notifier()
    print("✅ Остановлено")

    print("\n" + "=" * 60)
    print("✅ Тесты завершены!")