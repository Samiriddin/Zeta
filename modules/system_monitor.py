# -*- coding: utf-8 -*-
"""
Мониторинг системы для Zeta.
Показывает загрузку CPU, RAM, диска, температуру, сеть, процессы.
"""

import platform
import time
import socket
from typing import Dict, Optional, List, Any
from datetime import datetime

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


# ========== ОСНОВНОЙ КЛАСС ==========

class SystemMonitor:
    """Сбор информации о системе."""

    def __init__(self):
        self.os_name = platform.system()
        self._last_cpu = 0
        self._last_ram = 0
        self._last_disk = 0

    # ========== CPU ==========

    def get_cpu(self, interval: float = 0.5) -> Dict[str, Any]:
        """Возвращает загрузку CPU."""
        if not HAS_PSUTIL:
            return {"percent": 0, "cores": 0, "physical_cores": 0, "per_cpu": []}
        
        cpu_percent = psutil.cpu_percent(interval=interval)
        self._last_cpu = cpu_percent
        
        return {
            "percent": cpu_percent,
            "cores": psutil.cpu_count(logical=True) or 0,
            "physical_cores": psutil.cpu_count(logical=False) or 0,
            "per_cpu": psutil.cpu_percent(interval=interval, percpu=True) if interval > 0 else [],
            "frequency": psutil.cpu_freq().current if psutil.cpu_freq() else 0,
            "load_avg": psutil.getloadavg() if hasattr(psutil, 'getloadavg') else (0, 0, 0),
        }

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

    def get_disk(self, path: str = "C:\\") -> Dict[str, float]:
        """Возвращает информацию о диске."""
        if not HAS_PSUTIL:
            return {"total": 0, "used": 0, "free": 0, "percent": 0}
        
        if self.os_name == "Windows":
            path = "C:\\"
        else:
            path = "/"
        
        try:
            disk = psutil.disk_usage(path)
            self._last_disk = disk.percent
            return {
                "total": disk.total / (1024 ** 3),
                "used": disk.used / (1024 ** 3),
                "free": disk.free / (1024 ** 3),
                "percent": disk.percent,
            }
        except Exception:
            return {"total": 0, "used": 0, "free": 0, "percent": 0}

    def get_all_disks(self) -> List[Dict[str, Any]]:
        """Возвращает информацию о всех дисках."""
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

    def get_temperature(self) -> Optional[float]:
        """Возвращает температуру CPU."""
        if self.os_name == "Windows":
            return self._get_temp_windows()
        elif self.os_name == "Linux":
            return self._get_temp_linux()
        elif self.os_name == "Darwin":
            return self._get_temp_mac()
        return None

    def _get_temp_windows(self) -> Optional[float]:
        """Получает температуру через WMI на Windows."""
        if not HAS_WMI:
            return None
        try:
            w = wmi.WMI(namespace="root\\OpenHardwareMonitor")
            sensors = w.Sensor()
            for sensor in sensors:
                if sensor.Name == "CPU Package" and sensor.SensorType == "Temperature":
                    return float(sensor.Value)
        except Exception:
            pass
        return None

    def _get_temp_linux(self) -> Optional[float]:
        """Получает температуру через /sys/class/thermal на Linux."""
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                return int(f.read().strip()) / 1000.0
        except Exception:
            return None

    def _get_temp_mac(self) -> Optional[float]:
        """Получает температуру на MacOS."""
        try:
            import subprocess
            result = subprocess.run(
                ['sysctl', '-n', 'hw.temperature'],
                capture_output=True,
                text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip()) / 1000.0
        except Exception:
            pass
        return None

    # ========== GPU ==========

    def get_gpu(self) -> Dict[str, Any]:
        """Возвращает информацию о GPU."""
        if not HAS_GPUTIL:
            return {"available": False, "message": "Установите GPUtil: pip install gputil"}
        
        try:
            gpus = GPUtil.getGPUs()
            if not gpus:
                return {"available": False, "message": "GPU не найден"}
            
            gpu = gpus[0]
            return {
                "available": True,
                "name": gpu.name,
                "load": gpu.load * 100,
                "memory_used": gpu.memoryUsed,
                "memory_total": gpu.memoryTotal,
                "memory_percent": gpu.memoryUtil * 100,
                "temperature": gpu.temperature,
                "power_usage": gpu.powerDraw if hasattr(gpu, 'powerDraw') else None,
            }
        except Exception as e:
            return {"available": False, "message": str(e)}

    # ========== NETWORK ==========

    def get_network(self) -> Dict[str, Any]:
        """Возвращает информацию о сети."""
        if not HAS_PSUTIL:
            return {"ip": "N/A", "upload": 0, "download": 0}
        
        try:
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            
            net_io = psutil.net_io_counters()
            return {
                "ip": ip,
                "hostname": hostname,
                "upload": net_io.bytes_sent / (1024 ** 2),  # MB
                "download": net_io.bytes_recv / (1024 ** 2),  # MB
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv,
                "connections": len(psutil.net_connections()),
            }
        except Exception:
            return {"ip": "N/A", "upload": 0, "download": 0}

    # ========== PROCESSES ==========

    def get_top_processes(self, n: int = 10) -> List[Dict[str, Any]]:
        """Возвращает топ процессов по CPU."""
        if not HAS_PSUTIL:
            return []
        
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                proc_info = proc.info
                processes.append({
                    'pid': proc_info['pid'],
                    'name': proc_info['name'] or 'Unknown',
                    'cpu': proc_info['cpu_percent'] or 0,
                    'memory': proc_info['memory_percent'] or 0,
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        processes.sort(key=lambda x: x['cpu'], reverse=True)
        return processes[:n]

    # ========== UPTIME ==========

    def get_uptime(self) -> str:
        """Возвращает время работы системы."""
        if not HAS_PSUTIL:
            return "N/A"
        
        uptime_seconds = int(time.time() - psutil.boot_time())
        days = uptime_seconds // 86400
        hours = (uptime_seconds % 86400) // 3600
        minutes = (uptime_seconds % 3600) // 60
        
        if days > 0:
            return f"{days}д {hours}ч {minutes}м"
        elif hours > 0:
            return f"{hours}ч {minutes}м"
        else:
            return f"{minutes}м"

    # ========== ВСЁ ВМЕСТЕ ==========

    def get_all(self, include_gpu: bool = False) -> Dict[str, Any]:
        """Возвращает всю информацию о системе."""
        cpu = self.get_cpu()
        ram = self.get_ram()
        disk = self.get_disk()
        temp = self.get_temperature()
        network = self.get_network()
        uptime = self.get_uptime()
        
        result = {
            "cpu": cpu,
            "ram": ram,
            "disk": disk,
            "temperature": temp,
            "network": network,
            "uptime": uptime,
            "os": self.os_name,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        
        if include_gpu:
            result["gpu"] = self.get_gpu()
        
        return result

    # ========== ФОРМАТИРОВАНИЕ ==========

    def format_status(self, data: Dict) -> str:
        """Форматирует информацию о системе в читаемый текст."""
        cpu = data["cpu"]
        ram = data["ram"]
        disk = data["disk"]
        temp = data.get("temperature")
        network = data.get("network", {})
        uptime = data.get("uptime", "N/A")
        
        def status_color(value: float, warning: int = 70, danger: int = 90) -> str:
            if value >= danger:
                return "🔴"
            elif value >= warning:
                return "🟡"
            return "🟢"

        cpu_status = status_color(cpu["percent"])
        ram_status = status_color(ram["percent"])
        disk_status = status_color(disk["percent"])

        # ИСПРАВЛЕНО: Убрано лишнее двоеточие в "Диск C::"
        result = f"""
📊 **Состояние системы**

💻 **CPU:** {cpu_status} {cpu['percent']:.1f}%  ({cpu['cores']} ядер)
🧠 **RAM:** {ram_status} {ram['percent']:.1f}%  ({ram['used']:.1f}GB / {ram['total']:.1f}GB)
💾 **Диск C:** {disk_status} {disk['percent']:.1f}%  ({disk['used']:.1f}GB / {disk['total']:.1f}GB)
"""

        if temp:
            temp_status = "🟢" if temp < 60 else "🟡" if temp < 80 else "🔴"
            result += f"🌡️ **Температура:** {temp_status} {temp:.1f}°C\n"

        if network:
            result += f"🌐 **Сеть:** {network.get('ip', 'N/A')}  |  📥 {network.get('download', 0):.1f}MB  |  📤 {network.get('upload', 0):.1f}MB\n"

        result += f"⏱️ **Время работы:** {uptime}\n"
        result += f"🖥️ **ОС:** {data['os']}\n"
        result += f"🕐 **Время:** {data.get('time', 'N/A')}"

        return result

    # ========== ПРОВЕРКИ ==========

    def is_overloaded(self) -> bool:
        """Проверяет, перегружена ли система."""
        if not HAS_PSUTIL:
            return False
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory().percent
        return cpu > 90 or ram > 90

    def get_warning_level(self) -> str:
        """Возвращает уровень предупреждения."""
        if not HAS_PSUTIL:
            return "ok"
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory().percent
        
        if cpu > 90 or ram > 90:
            return "danger"
        elif cpu > 70 or ram > 70:
            return "warning"
        return "ok"


# ========== ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР ==========

monitor = SystemMonitor()


def get_system_status() -> str:
    """Возвращает форматированную строку со статусом системы."""
    if not HAS_PSUTIL:
        return "⚠️ psutil не установлен: pip install psutil"
    data = monitor.get_all()
    return monitor.format_status(data)


def get_system_data(include_gpu: bool = False) -> Dict[str, Any]:
    """Возвращает данные о системе."""
    return monitor.get_all(include_gpu=include_gpu)


def check_system_overload() -> bool:
    """Проверяет, перегружена ли система."""
    return monitor.is_overloaded()


def get_warning_level() -> str:
    """Возвращает уровень предупреждения."""
    return monitor.get_warning_level()


def get_top_processes(n: int = 10) -> List[Dict[str, Any]]:
    """Возвращает топ процессов по CPU."""
    return monitor.get_top_processes(n)


# ========== ТЕСТ ==========
if __name__ == "__main__":
    print("📊 Тест мониторинга системы:\n")
    if HAS_PSUTIL:
        print(get_system_status())
        print(f"\n⚠️ Перегрузка: {check_system_overload()}")
        print(f"⚠️ Уровень: {get_warning_level()}")
        print("\n📋 Топ процессов:")
        for p in get_top_processes(5):
            print(f"  {p['name']} — CPU: {p['cpu']:.1f}%, RAM: {p['memory']:.1f}%")
    else:
        print("⚠️ Установите psutil: pip install psutil")