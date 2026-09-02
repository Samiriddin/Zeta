# -*- coding: utf-8 -*-
"""
Умные уведомления для Zeta.
Мониторит систему и отправляет уведомления при перегрузках.
Поддерживает: CPU, RAM, диск, температуру, сеть.
"""

import threading
import time
import logging
from datetime import datetime
from typing import Optional, Callable, Dict, List, Any
from dataclasses import dataclass, field

import psutil

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ========== ДАТАКЛАСС ДЛЯ СОСТОЯНИЯ ==========

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
        """Преобразует в словарь."""
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

    def is_overloaded(self, cpu_threshold: float = 80, ram_threshold: float = 85, disk_threshold: float = 90) -> bool:
        """Проверяет, перегружена ли система."""
        return (self.cpu > cpu_threshold or 
                self.ram > ram_threshold or 
                self.disk > disk_threshold)


# ========== ОСНОВНОЙ КЛАСС ==========

class SmartNotifier:
    """
    Фоновый мониторинг системы с отправкой уведомлений.
    """

    def __init__(self):
        self.is_running = False
        self.thread: Optional[threading.Thread] = None
        self.callbacks: List[Callable] = []
        self.last_status: Optional[SystemStatus] = None
        
        # Пороги срабатывания (в процентах)
        self.cpu_threshold = 80
        self.ram_threshold = 85
        self.disk_threshold = 90
        self.temp_threshold = 80  # Градусы Цельсия
        
        # Интервал проверки (секунды)
        self.check_interval = 30
        
        # Состояния предупреждений (чтобы не спамить)
        self._warned_cpu = False
        self._warned_ram = False
        self._warned_disk = False
        self._warned_temp = False
        
        # Время последнего уведомления (для дедупликации)
        self._last_notification_time = 0
        self._notification_cooldown = 60  # Секунд

    # ========== УПРАВЛЕНИЕ CALLBACK ==========

    def add_callback(self, callback: Callable) -> None:
        """Добавляет callback для уведомлений."""
        if callback not in self.callbacks:
            self.callbacks.append(callback)
            logger.info(f"✅ Добавлен callback: {callback.__name__}")

    def remove_callback(self, callback: Callable) -> None:
        """Удаляет callback."""
        if callback in self.callbacks:
            self.callbacks.remove(callback)

    def _notify(self, title: str, message: str) -> None:
        """Вызывает все callback-функции с защитой от спама."""
        # Дедупликация
        current_time = time.time()
        if current_time - self._last_notification_time < self._notification_cooldown:
            logger.debug(f"⏳ Пропуск уведомления (кулдаун): {title}")
            return
        
        self._last_notification_time = current_time
        
        for callback in self.callbacks:
            try:
                callback(title, message)
            except Exception as e:
                logger.error(f"Ошибка в callback {callback.__name__}: {e}")

    # ========== МОНИТОРИНГ ==========

    def _get_system_status(self) -> SystemStatus:
        """Получает текущий статус системы."""
        try:
            cpu = psutil.cpu_percent(interval=0.5)
            cpu_cores = psutil.cpu_count() or 0
            
            mem = psutil.virtual_memory()
            ram = mem.percent
            ram_used_gb = mem.used / (1024 ** 3)
            ram_total_gb = mem.total / (1024 ** 3)
            
            disk = psutil.disk_usage("C:\\")
            disk_percent = disk.percent
            disk_used_gb = disk.used / (1024 ** 3)
            disk_total_gb = disk.total / (1024 ** 3)
            
            # Температура
            temp = self._get_temperature()
            
            # Время работы
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
                time=datetime.now().strftime("%H:%M:%S")
            )
        except Exception as e:
            logger.error(f"Ошибка получения статуса: {e}")
            return SystemStatus()

    def _get_temperature(self) -> Optional[float]:
        """Получает температуру CPU."""
        try:
            # Пробуем через WMI (Windows)
            import wmi
            w = wmi.WMI(namespace="root\\OpenHardwareMonitor")
            sensors = w.Sensor()
            for sensor in sensors:
                if sensor.Name == "CPU Package" and sensor.SensorType == "Temperature":
                    return float(sensor.Value)
        except Exception:
            pass
        
        try:
            # Пробуем через psutil (если есть)
            temps = psutil.sensors_temperatures()
            if temps:
                for name, entries in temps.items():
                    if entries:
                        return entries[0].current
        except Exception:
            pass
        
        return None

    def _format_uptime(self, boot_time: float) -> str:
        """Форматирует время работы системы."""
        uptime = time.time() - boot_time
        days = int(uptime // 86400)
        hours = int((uptime % 86400) // 3600)
        minutes = int((uptime % 3600) // 60)
        
        if days > 0:
            return f"{days}д {hours}ч {minutes}м"
        elif hours > 0:
            return f"{hours}ч {minutes}м"
        else:
            return f"{minutes}м"

    def _check_system(self) -> Optional[SystemStatus]:
        """Проверяет состояние системы и отправляет уведомления."""
        try:
            status = self._get_system_status()
            self.last_status = status
            
            # === CPU ===
            if status.cpu > self.cpu_threshold and not self._warned_cpu:
                self._warned_cpu = True
                self._notify(
                    "⚠️ Перегрузка CPU",
                    f"Загрузка процессора: {status.cpu:.1f}%\n"
                    f"Время: {status.time}"
                )
            elif status.cpu <= self.cpu_threshold:
                self._warned_cpu = False

            # === RAM ===
            if status.ram > self.ram_threshold and not self._warned_ram:
                self._warned_ram = True
                self._notify(
                    "⚠️ Перегрузка RAM",
                    f"Использование памяти: {status.ram:.1f}%\n"
                    f"Использовано: {status.ram_used_gb:.1f}GB / {status.ram_total_gb:.1f}GB\n"
                    f"Время: {status.time}"
                )
            elif status.ram <= self.ram_threshold:
                self._warned_ram = False

            # === DISK ===
            if status.disk > self.disk_threshold and not self._warned_disk:
                self._warned_disk = True
                self._notify(
                    "⚠️ Переполнение диска",
                    f"Заполнение диска C:: {status.disk:.1f}%\n"
                    f"Свободно: {status.disk_total_gb - status.disk_used_gb:.1f}GB\n"
                    f"Время: {status.time}"
                )
            elif status.disk <= self.disk_threshold:
                self._warned_disk = False

            # === TEMPERATURE ===
            if status.temperature and status.temperature > self.temp_threshold and not self._warned_temp:
                self._warned_temp = True
                self._notify(
                    "🌡️ Перегрев CPU",
                    f"Температура процессора: {status.temperature:.1f}°C\n"
                    f"Время: {status.time}"
                )
            elif status.temperature and status.temperature <= self.temp_threshold:
                self._warned_temp = False

            return status

        except Exception as e:
            logger.error(f"Ошибка мониторинга: {e}")
            return None

    def _run(self):
        """Основной цикл мониторинга."""
        logger.info(f"🟢 Умные уведомления запущены (интервал: {self.check_interval}с)")
        
        while self.is_running:
            try:
                self._check_system()
                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Ошибка в цикле: {e}")
                time.sleep(10)

    # ========== УПРАВЛЕНИЕ ==========

    def start(self):
        """Запускает фоновый мониторинг."""
        if self.is_running:
            logger.warning("Мониторинг уже запущен")
            return

        self.is_running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        logger.info("🚀 Умные уведомления запущены")

    def stop(self):
        """Останавливает мониторинг."""
        if not self.is_running:
            return
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("🛑 Умные уведомления остановлены")

    def restart(self):
        """Перезапускает мониторинг."""
        self.stop()
        time.sleep(1)
        self.start()

    # ========== ПОЛУЧЕНИЕ ДАННЫХ ==========

    def get_status(self) -> SystemStatus:
        """Возвращает текущий статус системы."""
        if self.last_status:
            return self.last_status
        return self._get_system_status()

    def get_last_status_dict(self) -> Dict[str, Any]:
        """Возвращает последний статус как словарь."""
        return self.get_status().to_dict()

    def get_summary(self) -> str:
        """Возвращает краткую сводку состояния системы."""
        status = self.get_status()
        return f"""
📊 **Состояние системы** ({status.time})

💻 **CPU:** {status.cpu:.1f}% ({status.cpu_cores} ядер)
🧠 **RAM:** {status.ram:.1f}% ({status.ram_used_gb:.1f}GB / {status.ram_total_gb:.1f}GB)
💾 **Диск C::** {status.disk:.1f}% ({status.disk_used_gb:.1f}GB / {status.disk_total_gb:.1f}GB)
{"🌡️ **Температура:** " + str(status.temperature) + "°C" if status.temperature else ""}
⏱️ **Время работы:** {status.uptime}
        """.strip()

    def is_overloaded(self) -> bool:
        """Проверяет, перегружена ли система."""
        status = self.get_status()
        return status.is_overloaded(
            self.cpu_threshold,
            self.ram_threshold,
            self.disk_threshold
        )

    # ========== НАСТРОЙКА ==========

    def set_thresholds(self, cpu: int = 80, ram: int = 85, disk: int = 90, temp: int = 80):
        """Устанавливает пороги срабатывания."""
        self.cpu_threshold = max(30, min(95, cpu))
        self.ram_threshold = max(30, min(95, ram))
        self.disk_threshold = max(30, min(95, disk))
        self.temp_threshold = max(50, min(100, temp))
        logger.info(f"✅ Пороги: CPU={cpu}%, RAM={ram}%, DISK={disk}%, TEMP={temp}°C")

    def set_interval(self, seconds: int):
        """Устанавливает интервал проверки."""
        self.check_interval = max(5, min(300, seconds))
        logger.info(f"✅ Интервал: {self.check_interval}с")


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
    """Возвращает статус системы как словарь."""
    return _notifier.get_last_status_dict()


def get_system_summary() -> str:
    """Возвращает краткую сводку статуса системы."""
    return _notifier.get_summary()


def is_system_overloaded() -> bool:
    """Проверяет, перегружена ли система."""
    return _notifier.is_overloaded()


def set_thresholds(cpu: int = 80, ram: int = 85, disk: int = 90, temp: int = 80):
    """Устанавливает пороги срабатывания."""
    _notifier.set_thresholds(cpu, ram, disk, temp)


def set_check_interval(seconds: int = 30):
    """Устанавливает интервал проверки."""
    _notifier.set_interval(seconds)


def add_notification_callback(callback: Callable):
    """Добавляет callback для уведомлений."""
    _notifier.add_callback(callback)


def remove_notification_callback(callback: Callable):
    """Удаляет callback."""
    _notifier.remove_callback(callback)


# ========== ТЕСТ ==========
if __name__ == "__main__":
    def test_callback(title, message):
        print(f"\n🔔 {title}\n{message}\n")

    print("🧪 Тест SmartNotifier\n")
    
    add_notification_callback(test_callback)
    
    print("📝 Тест 1: Запуск")
    start_notifier()
    
    print("📝 Тест 2: Статус (через 5 секунд)")
    time.sleep(5)
    print(get_system_summary())
    
    print("\n📝 Тест 3: Проверка перегрузки")
    print(f"Перегружена: {is_system_overloaded()}")
    
    print("\n📝 Тест 4: Настройка порогов")
    set_thresholds(cpu=50, ram=50, disk=80)
    
    time.sleep(2)
    print(get_system_summary())
    
    print("\n📝 Тест 5: Остановка")
    stop_notifier()
    print("✅ Остановлено")