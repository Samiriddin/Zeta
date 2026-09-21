# -*- coding: utf-8 -*-
"""
Мониторинг системы для Zeta.
Показывает загрузку CPU, RAM, диска, температуру, сеть, процессы.

Особенности:
    - Быстрый get_cpu (один замер вместо двух)
    - Кэш температуры (30 сек) — WMI медленный
    - Без net_connections (медленный на Windows)
    - Логирование в data/zeta.log
"""

import sys
import time
import socket
import logging
from pathlib import Path
from typing import Dict, Optional, List, Any
from datetime import datetime
from platform import system as os_name

sys.path.insert(0, str(Path(__file__).parent.parent))


# ========== ЛОГИРОВАНИЕ ==========

def _log(msg: str) -> None:
    logging.info(f"[SYS] {msg}")


def _log_warn(msg: str) -> None:
    logging.warning(f"[SYS] {msg}")


# ========== ПРОВЕРКА БИБЛИОТЕК ==========

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import wmi
    HAS_WMI = True
except ImportError:
    HAS_WMI = False

try:
    import GPUtil
    HAS_GPUTIL = True
except ImportError:
    HAS_GPUTIL = False


# ========== КОНСТАНТЫ ==========

TEMP_CACHE_TTL = 30  # секунд


# ========== ОСНОВНОЙ КЛАСС ==========

class SystemMonitor:
    """Сбор информации о системе."""

    def __init__(self):
        self.os_name = os_name()
        self._last_cpu = 0
        self._last_ram = 0
        self._last_disk = 0

        # Кэш температуры
        self._temp_cache: Optional[float] = None
        self._temp_cache_time: float = 0

    # ========== CPU ==========

    def get_cpu(self, interval: float = 0.5) -> Dict[str, Any]:
        """Возвращает загрузку CPU (один замер, быстро)."""
        if not HAS_PSUTIL:
            return {"percent": 0, "cores": 0, "physical_cores": 0,
                    "per_cpu": [], "frequency": 0}

        # Один блокирующий замер
        cpu_percent = psutil.cpu_percent(interval=interval)
        self._last_cpu = cpu_percent

        # Per-CPU — без блокировки (использует последние данные)
        try:
            per_cpu = psutil.cpu_percent(interval=0, percpu=True)
        except Exception:
            per_cpu = []

        # Частота
        freq = 0
        try:
            f = psutil.cpu_freq()
            if f:
                freq = f.current
        except Exception:
            pass

        result = {
            "percent": cpu_percent,
            "cores": psutil.cpu_count(logical=True) or 0,
            "physical_cores": psutil.cpu_count(logical=False) or 0,
            "per_cpu": per_cpu,
            "frequency": freq,
        }

        # load_avg — только Unix
        if self.os_name != "Windows" and hasattr(psutil, "getloadavg"):
            try:
                result["load_avg"] = psutil.getloadavg()
            except Exception:
                result["load_avg"] = None

        return result

    # ========== RAM ==========

    def get_ram(self) -> Dict[str, float]:
        """Возвращает информацию о RAM."""
        if not HAS_PSUTIL:
            return {"total": 0, "used": 0, "free": 0, "available": 0, "percent": 0}

        mem = psutil.virtual_memory()
        self._last_ram = mem.percent

        return {
            "total": mem.total / (1024 ** 3),
            "used": mem.used / (1024 ** 3),
            "free": mem.free / (1024 ** 3),
            "available": mem.available / (1024 ** 3),
            "percent": mem.percent,
        }

    # ========== DISK ==========

    def get_disk(self, path: Optional[str] = None) -> Dict[str, float]:
        """Возвращает информацию о диске."""
        if not HAS_PSUTIL:
            return {"total": 0, "used": 0, "free": 0, "percent": 0}

        if path is None:
            path = "C:\\" if self.os_name == "Windows" else "/"

        try:
            disk = psutil.disk_usage(path)
            self._last_disk = disk.percent
            return {
                "total": disk.total / (1024 ** 3),
                "used": disk.used / (1024 ** 3),
                "free": disk.free / (1024 ** 3),
                "percent": disk.percent,
            }
        except Exception as e:
            _log_warn(f"Ошибка get_disk({path}): {e}")
            return {"total": 0, "used": 0, "free": 0, "percent": 0}

    def get_all_disks(self) -> List[Dict[str, Any]]:
        """Информация о всех дисках."""
        if not HAS_PSUTIL:
            return []

        result = []
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                result.append({
                    "device": partition.device,
                    "mountpoint": partition.mountpoint,
                    "fstype": partition.fstype,
                    "total": usage.total / (1024 ** 3),
                    "used": usage.used / (1024 ** 3),
                    "free": usage.free / (1024 ** 3),
                    "percent": usage.percent,
                })
            except Exception:
                continue
        return result

    # ========== TEMPERATURE ==========

    def get_temperature(self, use_cache: bool = True) -> Optional[float]:
        """Температура CPU. Кэш 30 сек."""
        # Кэш
        if use_cache and self._temp_cache is not None:
            if time.time() - self._temp_cache_time < TEMP_CACHE_TTL:
                return self._temp_cache

        temp = None
        if self.os_name == "Windows":
            temp = self._get_temp_windows()
        elif self.os_name == "Linux":
            temp = self._get_temp_linux()
        elif self.os_name == "Darwin":
            temp = self._get_temp_mac()

        if temp is not None:
            self._temp_cache = temp
            self._temp_cache_time = time.time()

        return temp

    def _get_temp_windows(self) -> Optional[float]:
        """Температура через WMI (нужен OpenHardwareMonitor)."""
        if not HAS_WMI:
            return None
        try:
            w = wmi.WMI(namespace="root\\OpenHardwareMonitor")
            sensors = w.Sensor()
            for sensor in sensors:
                if sensor.Name == "CPU Package" and sensor.SensorType == "Temperature":
                    return float(sensor.Value)
        except Exception:
            # OHM не запущен / нет доступа — молча
            pass
        return None

    def _get_temp_linux(self) -> Optional[float]:
        """Температура через /sys/class/thermal."""
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                return int(f.read().strip()) / 1000.0
        except Exception:
            return None

    def _get_temp_mac(self) -> Optional[float]:
        """Температура на MacOS."""
        try:
            import subprocess
            result = subprocess.run(
                ["sysctl", "-n", "hw.temperature"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip()) / 1000.0
        except Exception:
            pass
        return None

    # ========== GPU ==========

    def get_gpu(self) -> Dict[str, Any]:
        """Информация о GPU (только NVIDIA)."""
        if not HAS_GPUTIL:
            return {
                "available": False,
                "message": "Установите GPUtil: pip install gputil",
            }

        try:
            gpus = GPUtil.getGPUs()
            if not gpus:
                return {"available": False, "message": "NVIDIA GPU не найден"}

            gpu = gpus[0]
            return {
                "available": True,
                "name": gpu.name,
                "load": gpu.load * 100,
                "memory_used": gpu.memoryUsed,
                "memory_total": gpu.memoryTotal,
                "memory_percent": gpu.memoryUtil * 100,
                "temperature": gpu.temperature,
                "power_usage": getattr(gpu, "powerDraw", None),
            }
        except Exception as e:
            return {"available": False, "message": str(e)}

    # ========== NETWORK ==========

    def get_network(self) -> Dict[str, Any]:
        """Информация о сети (без net_connections — он медленный)."""
        if not HAS_PSUTIL:
            return {"ip": "N/A", "upload": 0, "download": 0}

        try:
            hostname = socket.gethostname()
            try:
                ip = socket.gethostbyname(hostname)
            except Exception:
                ip = "N/A"

            net_io = psutil.net_io_counters()
            return {
                "ip": ip,
                "hostname": hostname,
                "upload": net_io.bytes_sent / (1024 ** 2),    # MB
                "download": net_io.bytes_recv / (1024 ** 2),  # MB
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv,
            }
        except Exception:
            return {"ip": "N/A", "upload": 0, "download": 0}

    # ========== PROCESSES ==========

    def get_top_processes(self, n: int = 10) -> List[Dict[str, Any]]:
        """Топ процессов по CPU."""
        if not HAS_PSUTIL:
            return []

        processes = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                info = proc.info
                processes.append({
                    "pid": info["pid"],
                    "name": info["name"] or "Unknown",
                    "cpu": info["cpu_percent"] or 0,
                    "memory": info["memory_percent"] or 0,
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        processes.sort(key=lambda x: x["cpu"], reverse=True)
        return processes[:n]

    # ========== UPTIME ==========

    def get_uptime(self) -> str:
        """Время работы системы."""
        if not HAS_PSUTIL:
            return "N/A"

        try:
            uptime_seconds = int(time.time() - psutil.boot_time())
            days = uptime_seconds // 86400
            hours = (uptime_seconds % 86400) // 3600
            minutes = (uptime_seconds % 3600) // 60

            if days > 0:
                return f"{days}д {hours}ч {minutes}м"
            elif hours > 0:
                return f"{hours}ч {minutes}м"
            return f"{minutes}м"
        except Exception:
            return "N/A"

    # ========== ВСЁ ВМЕСТЕ ==========

    def get_all(self, include_gpu: bool = False,
                include_all_disks: bool = False) -> Dict[str, Any]:
        """Вся информация о системе."""
        result = {
            "cpu": self.get_cpu(),
            "ram": self.get_ram(),
            "disk": self.get_disk(),
            "temperature": self.get_temperature(),
            "network": self.get_network(),
            "uptime": self.get_uptime(),
            "os": self.os_name,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        if include_gpu:
            result["gpu"] = self.get_gpu()

        if include_all_disks:
            result["all_disks"] = self.get_all_disks()

        return result

    # ========== ФОРМАТИРОВАНИЕ ==========

    @staticmethod
    def _status_icon(value: float, warning: int = 70, danger: int = 90) -> str:
        """Иконка статуса."""
        if value >= danger:
            return "🔴"
        elif value >= warning:
            return "🟡"
        return "🟢"

    def format_status(self, data: Dict) -> str:
        """Форматирует данные в читаемый текст."""
        cpu = data["cpu"]
        ram = data["ram"]
        disk = data["disk"]
        temp = data.get("temperature")
        network = data.get("network", {})
        uptime = data.get("uptime", "N/A")

        cpu_icon = self._status_icon(cpu["percent"])
        ram_icon = self._status_icon(ram["percent"])
        disk_icon = self._status_icon(disk["percent"])

        result = (
            f"📊 **Состояние системы**\n\n"
            f"💻 **CPU:** {cpu_icon} {cpu['percent']:.1f}%  ({cpu['cores']} ядер)\n"
            f"🧠 **RAM:** {ram_icon} {ram['percent']:.1f}%  "
            f"({ram['used']:.1f}GB / {ram['total']:.1f}GB)\n"
            f"💾 **Диск C:** {disk_icon} {disk['percent']:.1f}%  "
            f"({disk['used']:.1f}GB / {disk['total']:.1f}GB)\n"
        )

        if temp:
            temp_icon = "🟢" if temp < 60 else "🟡" if temp < 80 else "🔴"
            result += f"🌡️ **Температура:** {temp_icon} {temp:.1f}°C\n"

        if network:
            result += (
                f"🌐 **Сеть:** {network.get('ip', 'N/A')}  |  "
                f"📥 {network.get('download', 0):.1f}MB  |  "
                f"📤 {network.get('upload', 0):.1f}MB\n"
            )

        result += (
            f"⏱️ **Время работы:** {uptime}\n"
            f"🖥️ **ОС:** {data['os']}\n"
            f"🕐 **Время:** {data.get('time', 'N/A')}"
        )

        # GPU
        gpu = data.get("gpu")
        if gpu and gpu.get("available"):
            result += (
                f"\n🎮 **GPU:** {gpu['name']}  |  "
                f"загрузка {gpu['load']:.1f}%  |  "
                f"temp {gpu['temperature']}°C"
            )

        return result

    # ========== ПРОВЕРКИ ==========

    def is_overloaded(self) -> bool:
        """Перегружена ли система."""
        if not HAS_PSUTIL:
            return False
        try:
            cpu = psutil.cpu_percent(interval=0.5)
            ram = psutil.virtual_memory().percent
            return cpu > 90 or ram > 90
        except Exception:
            return False

    def get_warning_level(self) -> str:
        """Уровень предупреждения."""
        if not HAS_PSUTIL:
            return "ok"
        try:
            cpu = psutil.cpu_percent(interval=0.5)
            ram = psutil.virtual_memory().percent

            if cpu > 90 or ram > 90:
                return "danger"
            elif cpu > 70 or ram > 70:
                return "warning"
            return "ok"
        except Exception:
            return "ok"


# ========== ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР ==========

monitor = SystemMonitor()


def get_system_status() -> str:
    """Форматированная строка со статусом системы."""
    if not HAS_PSUTIL:
        return "⚠️ psutil не установлен: pip install psutil"
    data = monitor.get_all()
    return monitor.format_status(data)


def get_system_data(include_gpu: bool = False,
                    include_all_disks: bool = False) -> Dict[str, Any]:
    """Данные о системе."""
    return monitor.get_all(include_gpu=include_gpu,
                           include_all_disks=include_all_disks)


def check_system_overload() -> bool:
    """Перегружена ли система."""
    return monitor.is_overloaded()


def get_warning_level() -> str:
    """Уровень предупреждения."""
    return monitor.get_warning_level()


def get_top_processes(n: int = 10) -> List[Dict[str, Any]]:
    """Топ процессов по CPU."""
    return monitor.get_top_processes(n)


# ========== ЭКСПОРТ ==========

__all__ = [
    "SystemMonitor",
    "monitor",
    "get_system_status",
    "get_system_data",
    "check_system_overload",
    "get_warning_level",
    "get_top_processes",
]


# ========== ТЕСТ ==========

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    print("📊 Тест system_monitor.py\n")
    print("=" * 60)

    if not HAS_PSUTIL:
        print("⚠️ Установите psutil: pip install psutil")
        sys.exit(1)

    print("\n📝 Тест 1: Быстрый статус (get_cpu + get_ram)")
    t0 = time.time()
    cpu = monitor.get_cpu(interval=0.5)
    ram = monitor.get_ram()
    dt = time.time() - t0
    print(f"CPU: {cpu['percent']:.1f}% ({cpu['cores']} ядер)")
    print(f"RAM: {ram['percent']:.1f}%")
    print(f"Замер занял: {dt:.2f} сек")

    print("\n📝 Тест 2: Температура (кэш)")
    t0 = time.time()
    temp1 = monitor.get_temperature()
    dt1 = time.time() - t0

    t0 = time.time()
    temp2 = monitor.get_temperature()
    dt2 = time.time() - t0

    print(f"Первая: {temp1}°C ({dt1:.3f} сек)")
    print(f"Вторая: {temp2}°C ({dt2:.3f} сек) ← из кэша" if dt2 < 0.01 else f"Вторая: {temp2}°C ({dt2:.3f} сек)")

    print("\n📝 Тест 3: Полный статус")
    t0 = time.time()
    status = get_system_status()
    dt = time.time() - t0
    print(status)
    print(f"\nЗамер занял: {dt:.2f} сек")

    print("\n📝 Тест 4: Топ процессов (5)")
    for p in get_top_processes(5):
        print(f"  • {p['name']:<25} CPU: {p['cpu']:>5.1f}%  RAM: {p['memory']:>5.1f}%")

    print("\n📝 Тест 5: Все диски")
    disks = monitor.get_all_disks()
    for d in disks:
        print(f"  • {d['device']}: {d['percent']:.1f}% ({d['used']:.1f}/{d['total']:.1f}GB)")

    print("\n📝 Тест 6: Перегрузка")
    print(f"Перегружена: {check_system_overload()}")
    print(f"Уровень: {get_warning_level()}")

    print("\n📝 Тест 7: GPU")
    gpu = monitor.get_gpu()
    if gpu.get("available"):
        print(f"  • {gpu['name']}: загрузка {gpu['load']:.1f}%")
    else:
        print(f"  ⚠️ {gpu.get('message')}")

    print("\n" + "=" * 60)
    print("✅ Тесты завершены!")