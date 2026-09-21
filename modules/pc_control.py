# -*- coding: utf-8 -*-
"""
Максимально расширенный модуль для управления ПК.
Поддерживает: приложения, окна, громкость, яркость, питание, буфер обмена, скриншоты, таймеры.

Безопасность:
    - Защита от shell-инъекций (валидация имён приложений)
    - Чёрный список системных процессов
    - Логирование в data/zeta.log
    - Универсальная работа с pycaw (любая версия)
"""

import os
import re
import sys
import time
import socket
import logging
import threading
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

import psutil

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.screen_capture import take_screenshot, take_screenshot_region


# ========== ЛОГИРОВАНИЕ ==========

def _log(msg: str) -> None:
    logging.info(f"[PC] {msg}")


def _log_warn(msg: str) -> None:
    logging.warning(f"[PC] {msg}")


def _audit(msg: str) -> None:
    try:
        from security.audit import get_audit
        get_audit().log_security("pc_control", msg)
    except Exception:
        pass


# ========== ПРОВЕРКА БИБЛИОТЕК ==========

try:
    import pygetwindow as gw
    HAS_GW = True
except ImportError:
    HAS_GW = False

try:
    import pyautogui
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False

try:
    import keyboard
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False

try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
    HAS_PYCAW = True
except ImportError:
    HAS_PYCAW = False

try:
    import win32api
    import win32con
    import win32gui
    import win32process
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

try:
    import pyperclip
    HAS_PYPERCLIP = True
except ImportError:
    HAS_PYPERCLIP = False


# ========== КОНСТАНТЫ ==========

APPS: Dict[str, str] = {
    # Браузеры (browser → Edge, потому что у пользователя Edge)
    "edge": "start msedge",
    "microsoft edge": "start msedge",
    "browser": "start msedge",
    "браузер": "start msedge",
    "chrome": "start chrome",
    "google chrome": "start chrome",
    "firefox": "start firefox",
    "mozilla": "start firefox",
    "opera": "start opera",
    "brave": "start brave",
    "vivaldi": "start vivaldi",
    "tor": "start tor",

    # Разработка
    "code": "code",
    "vscode": "code",
    "visual studio code": "code",
    "pycharm": "pycharm64",
    "idea": "idea64",
    "intellij": "idea64",
    "android studio": "android-studio",
    "eclipse": "eclipse",
    "sublime": "sublime_text",
    "notepad++": "notepad++",
    "vim": "vim",
    "git": "start git bash",
    "github desktop": "github",
    "docker": "start docker",

    # Системные
    "explorer": "explorer",
    "проводник": "explorer",
    "cmd": "start cmd",
    "command": "start cmd",
    "terminal": "start wt",
    "powershell": "start powershell",
    "taskmgr": "taskmgr",
    "диспетчер": "taskmgr",
    "notepad": "notepad",
    "блокнот": "notepad",
    "calc": "calc",
    "калькулятор": "calc",
    "control": "control",
    "панель управления": "control",
    "snippingtool": "snippingtool",
    "snip": "snippingtool",
    "regedit": "regedit",
    "msconfig": "msconfig",
    "services": "services.msc",
    "eventvwr": "eventvwr",
    "diskmgmt": "diskmgmt.msc",
    "devmgmt": "devmgmt.msc",

    # Медиа
    "spotify": "start spotify",
    "vlc": "start vlc",
    "media player": "start wmplayer",
    "audacity": "audacity",
    "obs": "obs64",

    # Соцсети и общение
    "steam": "start steam",
    "discord": "start discord",
    "telegram": "start telegram",
    "whatsapp": "start whatsapp",
    "zoom": "start zoom",
    "skype": "start skype",
    "teams": "start teams",
    "slack": "start slack",
    "outlook": "start outlook",

    # Офис
    "word": "start winword",
    "excel": "start excel",
    "powerpoint": "start powerpnt",
    "libreoffice": "start libreoffice",

    # Игры
    "minecraft": "start minecraft",
    "epic": "start epicgames",
    "battle.net": "start battle.net",

    # Дизайн
    "photoshop": "photoshop",
    "illustrator": "illustrator",
    "figma": "figma",
    "blender": "blender",
}

# Системные процессы — НЕ убивать
PROTECTED_PROCESSES = {
    "system", "system idle process", "registry", "memory compression",
    "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe",
    "services.exe", "lsass.exe", "svchost.exe", "fontdrvhost.exe",
    "dwm.exe", "explorer.exe", "sihost.exe", "taskhostw.exe",
    "ctfmon.exe", "runtimebroker.exe", "searchindexer.exe",
    "spoolsv.exe", "audiodg.exe", "conhost.exe", "dllhost.exe",
}

# Кэш интерфейса громкости
_volume_interface = None

# Таймеры
_system_timers: List[Dict[str, Any]] = []
_timers_lock = threading.RLock()
_timers_cancelled: Dict[int, bool] = {}


# ========== УНИВЕРСАЛЬНАЯ ГРОМКОСТЬ ==========

def _get_volume_interface():
    """
    Универсальная функция получения интерфейса громкости.
    Работает с разными версиями pycaw:
        - Старой: AudioDevice.Activate(...)
        - Новой: AudioDevice._dev.Activate(...)
    """
    global _volume_interface
    if _volume_interface is not None:
        return _volume_interface

    if not HAS_PYCAW:
        return None

    try:
        devices = AudioUtilities.GetSpeakers()
    except Exception as e:
        _log_warn(f"GetSpeakers упал: {e}")
        return None

    # Способ 1: новый API через _dev
    try:
        if hasattr(devices, "_dev"):
            interface = devices._dev.Activate(
                IAudioEndpointVolume._iid_, CLSCTX_ALL, None
            )
            _volume_interface = interface.QueryInterface(IAudioEndpointVolume)
            _log("pycaw: интерфейс через _dev")
            return _volume_interface
    except Exception as e:
        _log_warn(f"pycaw _dev failed: {e}")

    # Способ 2: старый API через Activate
    try:
        if hasattr(devices, "Activate"):
            interface = devices.Activate(
                IAudioEndpointVolume._iid_, CLSCTX_ALL, None
            )
            _volume_interface = interface.QueryInterface(IAudioEndpointVolume)
            _log("pycaw: интерфейс через Activate")
            return _volume_interface
    except Exception as e:
        _log_warn(f"pycaw Activate failed: {e}")

    # Способ 3: fallback через comtypes напрямую
    try:
        import comtypes
        from ctypes import cast, POINTER
        from pycaw.pycaw import AudioUtilities

        speakers = AudioUtilities.GetSpeakers()
        if hasattr(speakers, "_dev"):
            dev = speakers._dev
        else:
            dev = speakers

        interface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        _volume_interface = cast(interface, POINTER(IAudioEndpointVolume))
        _log("pycaw: интерфейс через fallback")
        return _volume_interface
    except Exception as e:
        _log_warn(f"pycaw fallback failed: {e}")

    return None


# ========== ВСПОМОГАТЕЛЬНЫЕ ==========

def _clean_command(text: str, commands: List[str]) -> str:
    result = text.strip()
    for cmd in commands:
        if result.lower().startswith(cmd):
            result = result[len(cmd):].strip()
            break
    return result


def _is_safe_app_name(name: str) -> bool:
    """Проверяет, что имя безопасно для shell."""
    if not name:
        return False
    return bool(re.fullmatch(r"[\w\s\-\.]+", name, re.UNICODE))


def _format_uptime(boot_time: float) -> str:
    uptime = time.time() - boot_time
    days = int(uptime // 86400)
    hours = int((uptime % 86400) // 3600)
    minutes = int((uptime % 3600) // 60)
    if days > 0:
        return f"{days}д {hours}ч {minutes}м"
    elif hours > 0:
        return f"{hours}ч {minutes}м"
    return f"{minutes}м"


def _check_internet() -> bool:
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except Exception:
        return False


def show_notification(title: str, message: str) -> None:
    """Уведомление через plyer / PowerShell balloon."""
    _log(f"Уведомление: {title} — {message}")

    try:
        from plyer import notification
        notification.notify(title=title, message=message,
                            app_name="Zeta", timeout=10)
        return
    except ImportError:
        pass
    except Exception as e:
        _log_warn(f"plyer упал: {e}")

    try:
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
            'Start-Sleep -Seconds 9;$n.Dispose()'
        )
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", ps],
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception as e:
        _log_warn(f"PowerShell balloon упал: {e}")
        print(f"[💬] {title}: {message}")


# ========== ПРИЛОЖЕНИЯ ==========

def open_app(name: str) -> str:
    if not name or not name.strip():
        return "⚠️ Укажите имя приложения."

    name_clean = _clean_command(name, ["открой", "запусти", "open", "start", "run"])
    name_lower = name_clean.lower().strip()

    if not _is_safe_app_name(name_lower):
        _log_warn(f"Небезопасное имя: {name_lower}")
        _audit(f"open_denied: {name_lower}")
        return f"⚠️ Недопустимое имя приложения: {name}"

    cmd = APPS.get(name_lower)
    if not cmd:
        for key, value in APPS.items():
            if name_lower in key or key in name_lower:
                cmd = value
                break

    if not cmd:
        if not re.fullmatch(r"[a-zA-Z0-9_\-]+", name_lower):
            return f"⚠️ Не знаю такое приложение: {name}"
        cmd = f"start {name_lower}"

    try:
        _log(f"Открываю: {name_lower} → {cmd}")
        _audit(f"open_app: {name_lower}")
        subprocess.Popen(cmd, shell=True)
        return f"✅ Открыл: {name}"
    except Exception as e:
        _log_warn(f"Ошибка open_app: {e}")
        return f"⚠️ Ошибка: {str(e)}"


def close_app(name: str) -> str:
    if not name or not name.strip():
        return "⚠️ Укажите имя приложения."

    name_clean = _clean_command(name, ["закрой", "закрыть", "close", "kill", "stop"])
    name_lower = name_clean.lower().strip()

    if not _is_safe_app_name(name_lower):
        return f"⚠️ Недопустимое имя: {name}"

    if name_lower.endswith(".exe"):
        exe_name = name_lower
    else:
        exe_name = f"{name_lower}.exe"

    try:
        _log(f"Закрываю: {exe_name}")
        _audit(f"close_app: {exe_name}")
        result = subprocess.run(
            ["taskkill", "/F", "/IM", exe_name],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return f"✅ Закрыл: {name}"
        return f"⚠️ Не удалось закрыть: {name}"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def list_running_apps() -> str:
    try:
        processes = []
        for proc in psutil.process_iter(["name", "pid", "memory_percent", "cpu_percent"]):
            try:
                info = proc.info
                if info["name"]:
                    processes.append({
                        "name": info["name"],
                        "pid": info["pid"],
                        "cpu": info.get("cpu_percent", 0) or 0,
                        "memory": info.get("memory_percent", 0) or 0,
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        processes = sorted(processes, key=lambda x: x["memory"], reverse=True)[:30]

        if not processes:
            return "📭 Нет запущенных процессов."

        result = "🔄 **Запущенные процессы:**\n\n"
        for i, p in enumerate(processes, 1):
            result += (f"  {i}. {p['name']} (PID: {p['pid']}) — "
                       f"CPU: {p['cpu']:.1f}%, RAM: {p['memory']:.1f}%\n")
        return result
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def kill_process(name: str) -> str:
    if not name or not name.strip():
        return "⚠️ Укажите имя процесса."

    name_clean = _clean_command(name, ["убить", "завершить", "kill", "stop", "terminate"])
    name_lower = name_clean.lower().strip()

    if not _is_safe_app_name(name_lower):
        return f"⚠️ Недопустимое имя: {name}"

    for protected in PROTECTED_PROCESSES:
        if protected in name_lower:
            _log_warn(f"Попытка убить системный: {name_lower}")
            _audit(f"kill_denied: {name_lower}")
            return f"🛡️ Процесс `{name}` системный. Убийство запрещено."

    try:
        killed = []
        for proc in psutil.process_iter(["name", "pid"]):
            try:
                pname = proc.info["name"] or ""
                if name_lower in pname.lower():
                    proc.kill()
                    killed.append(pname)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if killed:
            _log(f"Убито: {killed}")
            _audit(f"kill: {killed}")
            return f"✅ Завершено: {', '.join(killed)}"
        return f"⚠️ Процесс `{name}` не найден"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


# ========== ОКНА ==========

def list_windows() -> str:
    if not HAS_GW:
        return "⚠️ Установите pygetwindow: pip install pygetwindow"
    try:
        windows = [w for w in gw.getAllWindows() if w.title.strip()]
        if not windows:
            return "📭 Открытых окон нет."

        result = "🪟 **Открытые окна:**\n\n"
        for i, w in enumerate(windows[:30], 1):
            title = w.title[:60] + "..." if len(w.title) > 60 else w.title
            result += f"  {i}. {title}\n"

        if len(windows) > 30:
            result += f"\n... и ещё {len(windows) - 30} окон"
        return result
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def focus_window(title_part: str) -> str:
    if not HAS_GW:
        return "⚠️ pygetwindow не установлен"
    if not title_part:
        return "⚠️ Укажите часть заголовка"

    title_clean = _clean_command(title_part, ["фокус", "переключи", "активируй", "focus", "activate"])
    title_lower = title_clean.lower().strip()

    try:
        for w in gw.getAllWindows():
            if w.title.strip() and title_lower in w.title.lower():
                try:
                    w.activate()
                except Exception:
                    try:
                        w.minimize()
                        w.restore()
                        w.activate()
                    except Exception:
                        return f"⚠️ Не удалось активировать: {w.title}"
                return f"✅ Активировано: {w.title}"
        return f"⚠️ Окно '{title_part}' не найдено"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def minimize_window(title_part: str) -> str:
    if not HAS_GW:
        return "⚠️ pygetwindow не установлен"
    title_clean = _clean_command(title_part, ["сверни", "минимизировать", "minimize"])
    title_lower = title_clean.lower().strip()
    try:
        for w in gw.getAllWindows():
            if w.title.strip() and title_lower in w.title.lower():
                w.minimize()
                return f"✅ Свёрнуто: {w.title}"
        return f"⚠️ Окно '{title_part}' не найдено"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def maximize_window(title_part: str) -> str:
    if not HAS_GW:
        return "⚠️ pygetwindow не установлен"
    title_clean = _clean_command(title_part, ["разверни", "максимизировать", "maximize"])
    title_lower = title_clean.lower().strip()
    try:
        for w in gw.getAllWindows():
            if w.title.strip() and title_lower in w.title.lower():
                w.maximize()
                return f"✅ Развёрнуто: {w.title}"
        return f"⚠️ Окно '{title_part}' не найдено"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def close_window(title_part: str) -> str:
    if not HAS_GW:
        return "⚠️ pygetwindow не установлен"
    title_clean = _clean_command(title_part, ["закрой", "закрыть", "close"])
    title_lower = title_clean.lower().strip()
    try:
        for w in gw.getAllWindows():
            if w.title.strip() and title_lower in w.title.lower():
                w.close()
                return f"✅ Закрыто: {w.title}"
        return f"⚠️ Окно '{title_part}' не найдено"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def make_window_always_on_top(title_part: str) -> str:
    if not HAS_WIN32:
        return "⚠️ Установите pywin32: pip install pywin32"
    title_clean = _clean_command(title_part, ["поверх", "on top", "topmost"])
    title_lower = title_clean.lower().strip()

    try:
        def cb(hwnd, hwnds):
            if win32gui.IsWindowVisible(hwnd):
                if title_lower in win32gui.GetWindowText(hwnd).lower():
                    hwnds.append(hwnd)
            return True

        hwnds = []
        win32gui.EnumWindows(cb, hwnds)

        if not hwnds:
            return f"⚠️ Окно '{title_part}' не найдено"

        for hwnd in hwnds:
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
        return f"✅ Окно '{title_part}' теперь всегда поверх"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


# ========== СИСТЕМА ==========

def get_system_info() -> str:
    try:
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\")

        result = (
            f"💻 **Информация о системе:**\n\n"
            f"🖥️ **CPU:** {cpu}% ({psutil.cpu_count()} ядер)\n"
            f"🧠 **RAM:** {ram.used // (1024**3)}GB / {ram.total // (1024**3)}GB ({ram.percent}%)\n"
            f"💾 **Диск C:** {disk.used // (1024**3)}GB / {disk.total // (1024**3)}GB ({disk.percent}%)\n"
            f"⏱️ **Время работы:** {_format_uptime(psutil.boot_time())}"
        )

        try:
            import wmi
            w = wmi.WMI(namespace="root\\OpenHardwareMonitor")
            sensors = w.Sensor()
            for sensor in sensors:
                if sensor.Name == "CPU Package" and sensor.SensorType == "Temperature":
                    result += f"\n🌡️ **Температура:** {float(sensor.Value):.1f}°C"
                    break
        except Exception:
            pass

        return result
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def get_ip_info() -> str:
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)

        result = (
            f"🌐 **Сетевая информация:**\n\n"
            f"📡 **Имя ПК:** {hostname}\n"
            f"🌍 **IP-адрес:** {ip}\n"
            f"🌐 **Интернет:** {'✅ Есть' if _check_internet() else '❌ Нет'}"
        )

        try:
            import requests
            response = requests.get("http://ip-api.com/json/", timeout=5)
            data = response.json()
            if data.get("status") == "success":
                result += (
                    f"\n🏳️ **Страна:** {data.get('country', '?')}"
                    f"\n🏙️ **Город:** {data.get('city', '?')}"
                    f"\n📡 **Провайдер:** {data.get('isp', '?')}"
                )
        except Exception:
            pass

        return result
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


# ========== ГРОМКОСТЬ ==========

def set_volume(level: int) -> str:
    if not HAS_PYCAW:
        return "⚠️ Установите pycaw: pip install pycaw"

    volume = _get_volume_interface()
    if volume is None:
        return "⚠️ Не удалось получить доступ к громкости"

    try:
        level = max(0, min(100, int(level)))
        volume.SetMasterVolumeLevelScalar(level / 100.0, None)
        _log(f"Громкость: {level}%")
        return f"🔊 Громкость: {level}%"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def get_volume() -> str:
    if not HAS_PYCAW:
        return "⚠️ Установите pycaw: pip install pycaw"

    volume = _get_volume_interface()
    if volume is None:
        return "⚠️ Не удалось получить доступ к громкости"

    try:
        level = volume.GetMasterVolumeLevelScalar() * 100
        is_muted = volume.GetMute()
        status = "🔇 Выключен" if is_muted else "🔊 Включён"
        return f"📢 Громкость: {int(level)}% ({status})"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def mute_volume() -> str:
    if not HAS_PYCAW:
        return "⚠️ Установите pycaw: pip install pycaw"

    volume = _get_volume_interface()
    if volume is None:
        return "⚠️ Не удалось получить доступ к громкости"

    try:
        volume.SetMute(True, None)
        return "🔇 Звук выключен"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def unmute_volume() -> str:
    if not HAS_PYCAW:
        return "⚠️ Установите pycaw: pip install pycaw"

    volume = _get_volume_interface()
    if volume is None:
        return "⚠️ Не удалось получить доступ к громкости"

    try:
        volume.SetMute(False, None)
        return "🔊 Звук включён"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def set_brightness(level: int) -> str:
    try:
        level = max(0, min(100, int(level)))
        import wmi
        w = wmi.WMI(namespace="wmi")
        methods = w.WmiMonitorBrightnessMethods()
        if not methods:
            return "⚠️ Яркость не поддерживается (возможно, это ПК)"
        methods[0].WmiSetBrightness(level, 0)
        return f"☀️ Яркость: {level}%"
    except ImportError:
        return "⚠️ Для яркости нужен: pip install WMI"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


# ========== ПИТАНИЕ ==========

def shutdown_pc(delay: int = 0) -> str:
    try:
        _log(f"Выключение через {delay}с")
        _audit(f"shutdown: {delay}с")
        subprocess.run(f"shutdown /s /t {int(delay)}", shell=True)
        if delay > 0:
            return f"🔄 ПК выключится через {delay} секунд"
        return "🔄 ПК выключается..."
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def restart_pc(delay: int = 0) -> str:
    try:
        _log(f"Перезагрузка через {delay}с")
        _audit(f"restart: {delay}с")
        subprocess.run(f"shutdown /r /t {int(delay)}", shell=True)
        if delay > 0:
            return f"🔄 ПК перезагрузится через {delay} секунд"
        return "🔄 ПК перезагружается..."
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def sleep_pc() -> str:
    try:
        _audit("sleep")
        subprocess.run("rundll32.exe powrprof.dll,SetSuspendState 0,1,0", shell=True)
        return "😴 ПК уходит в сон..."
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def lock_pc() -> str:
    try:
        _audit("lock")
        subprocess.run("rundll32.exe user32.dll,LockWorkStation", shell=True)
        return "🔒 ПК заблокирован"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def hibernate_pc() -> str:
    try:
        _audit("hibernate")
        subprocess.run("shutdown /h", shell=True)
        return "💤 ПК уходит в гибернацию..."
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def cancel_shutdown() -> str:
    try:
        _audit("cancel_shutdown")
        subprocess.run("shutdown /a", shell=True)
        return "✅ Выключение отменено"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


# ========== БУФЕР ==========

def get_clipboard() -> str:
    if not HAS_PYPERCLIP:
        return "⚠️ Установите pyperclip: pip install pyperclip"
    try:
        text = pyperclip.paste()
        if not text:
            return "📋 Буфер обмена пуст"
        preview = text[:500] + ("..." if len(text) > 500 else "")
        return f"📋 **Буфер обмена:**\n```\n{preview}\n```"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def set_clipboard(text: str) -> str:
    if not HAS_PYPERCLIP:
        return "⚠️ Установите pyperclip: pip install pyperclip"
    try:
        pyperclip.copy(text)
        preview = text[:200] + ("..." if len(text) > 200 else "")
        return f"✅ Скопировано:\n```\n{preview}\n```"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


# ========== СКРИНШОТЫ ==========

def screenshot_full() -> str:
    result = take_screenshot()
    return result if result else "⚠️ Не удалось сделать скриншот"


def screenshot_region(x: int, y: int, width: int, height: int) -> str:
    result = take_screenshot_region(x, y, width, height)
    return result if result else "⚠️ Не удалось сделать скриншот области"


# ========== ТАЙМЕРЫ ==========

def set_timer(seconds: int, action: str) -> str:
    if seconds < 1:
        return "⚠️ Время должно быть больше 0"

    def timer_thread():
        elapsed = 0
        while elapsed < seconds:
            if _timers_cancelled.get(id(threading.current_thread())):
                return
            time.sleep(min(1, seconds - elapsed))
            elapsed += 1

        show_notification("⏰ Таймер", f"Время вышло! {action}")
        with _timers_lock:
            _system_timers[:] = [
                t for t in _system_timers
                if t.get("thread") != threading.current_thread()
            ]

    t = threading.Thread(target=timer_thread, daemon=True)
    t.start()

    with _timers_lock:
        _system_timers.append({
            "seconds": seconds,
            "action": action,
            "time": datetime.now(),
            "thread": t,
        })

    return f"⏰ Таймер на {seconds} секунд: {action}"


def list_timers() -> str:
    with _timers_lock:
        if not _system_timers:
            return "📭 Нет активных таймеров"
        result = "⏰ **Активные таймеры:**\n"
        for i, t in enumerate(_system_timers, 1):
            elapsed = int((datetime.now() - t["time"]).total_seconds())
            remaining = max(0, t["seconds"] - elapsed)
            result += f"  {i}. {t['action']} — осталось {remaining} сек\n"
        return result


def cancel_timer(index: int) -> str:
    with _timers_lock:
        if 1 <= index <= len(_system_timers):
            t = _system_timers.pop(index - 1)
            thread_obj = t.get("thread")
            if thread_obj:
                _timers_cancelled[id(thread_obj)] = True
            return f"✅ Таймер {index} отменён"
    return f"⚠️ Таймер {index} не найден"


# ========== ЭКСПОРТ ==========

__all__ = [
    "open_app", "close_app", "list_running_apps", "kill_process",
    "list_windows", "focus_window", "minimize_window", "maximize_window",
    "close_window", "make_window_always_on_top",
    "get_system_info", "get_ip_info",
    "set_volume", "get_volume", "mute_volume", "unmute_volume", "set_brightness",
    "shutdown_pc", "restart_pc", "sleep_pc", "lock_pc", "hibernate_pc", "cancel_shutdown",
    "get_clipboard", "set_clipboard",
    "screenshot_full", "screenshot_region",
    "set_timer", "list_timers", "cancel_timer",
]