# -*- coding: utf-8 -*-
"""
Максимально расширенный модуль для управления ПК.
Поддерживает: приложения, окна, громкость, яркость, питание, буфер обмена, скриншоты, таймеры и многое другое.
"""

import os
import re
import time
import json
import socket
import threading
import subprocess
import tempfile
import webbrowser
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from datetime import datetime, timedelta

import psutil

from core.screen_capture import take_screenshot

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

# Карта приложений
APPS: Dict[str, str] = {
    # Браузеры
    "chrome": "start chrome",
    "google chrome": "start chrome",
    "firefox": "start firefox",
    "mozilla": "start firefox",
    "edge": "start msedge",
    "microsoft edge": "start msedge",
    "browser": "start chrome",
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
    "device manager": "devmgmt.msc",
    
    # Медиа
    "spotify": "start spotify",
    "vlc": "start vlc",
    "media player": "start wmplayer",
    "mpc": "start mpc-hc",
    "potplayer": "start potplayer",
    "audacity": "audacity",
    "obs": "obs64",
    "streamlabs": "streamlabs",
    "adobe premiere": "premiere",
    "after effects": "afterfx",
    
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
    "mail": "start mail",
    
    # Офис
    "word": "start winword",
    "excel": "start excel",
    "powerpoint": "start powerpnt",
    "office": "start outlook",
    "wps": "start wps",
    "libreoffice": "start libreoffice",
    "pdf": "start acrobat",
    "reader": "start acrobat",
    
    # Игры
    "minecraft": "start minecraft",
    "csgo": "start steam://run/730",
    "dota": "start steam://run/570",
    "gta5": "start steam://run/271590",
    "cyberpunk": "start steam://run/1091500",
    "epic": "start epicgames",
    "steam": "start steam",
    "battle.net": "start battle.net",
    "origin": "start origin",
    "ubisoft": "start ubisoft",
    
    # Дизайн
    "photoshop": "photoshop",
    "illustrator": "illustrator",
    "indesign": "indesign",
    "lightroom": "lightroom",
    "figma": "figma",
    "blender": "blender",
    "3ds max": "3dsmax",
    "maya": "maya",
    "zbrush": "zbrush",
    "autocad": "autocad",
    
    # Другое
    "speedtest": "start speedtest",
    "ping": "start cmd /k ping google.com",
    "ipconfig": "start cmd /k ipconfig",
    "system info": "start msinfo32",
    "task scheduler": "taskschd.msc",
}


# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========

_system_timers: List[Dict] = []


# ========== УПРАВЛЕНИЕ ПРИЛОЖЕНИЯМИ ==========

def open_app(name: str) -> str:
    """Открывает приложение по имени."""
    if not name or not name.strip():
        return "⚠️ Укажите имя приложения."

    name_clean = _clean_command(name, ["открой", "запусти", "open", "start", "run"])
    name_lower = name_clean.lower().strip()

    cmd = APPS.get(name_lower)
    if not cmd:
        for key, value in APPS.items():
            if name_lower in key or key in name_lower:
                cmd = value
                break

    if not cmd:
        cmd = f"start {name_lower}"

    try:
        subprocess.Popen(cmd, shell=True)
        return f"✅ Открыл: {name}"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def close_app(name: str) -> str:
    """Закрывает приложение по имени."""
    if not name or not name.strip():
        return "⚠️ Укажите имя приложения."

    name_clean = _clean_command(name, ["закрой", "закрыть", "close", "kill", "stop"])
    name_lower = name_clean.lower().strip()

    try:
        result = subprocess.run(
            ['taskkill', '/F', '/IM', f'{name_lower}.exe'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return f"✅ Закрыл: {name}"
        return f"⚠️ Не удалось закрыть: {name}"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def list_running_apps() -> str:
    """Список запущенных приложений."""
    try:
        processes = []
        for proc in psutil.process_iter(['name', 'pid', 'memory_percent', 'cpu_percent']):
            try:
                proc_info = proc.info
                if proc_info['name']:
                    processes.append({
                        'name': proc_info['name'],
                        'pid': proc_info['pid'],
                        'cpu': proc_info.get('cpu_percent', 0),
                        'memory': proc_info.get('memory_percent', 0)
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        processes = sorted(processes, key=lambda x: x['memory'], reverse=True)[:30]
        
        if not processes:
            return "📭 Нет запущенных процессов."

        result = "🔄 **Запущенные процессы:**\n\n"
        for i, p in enumerate(processes, 1):
            result += f"  {i}. {p['name']} (PID: {p['pid']}) — CPU: {p['cpu']:.1f}%, RAM: {p['memory']:.1f}%\n"

        return result
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def kill_process(name: str) -> str:
    """Убивает процесс по имени."""
    if not name or not name.strip():
        return "⚠️ Укажите имя процесса."

    name_clean = _clean_command(name, ["убить", "завершить", "kill", "stop", "terminate"])
    name_lower = name_clean.lower().strip()

    try:
        killed = False
        for proc in psutil.process_iter(['name', 'pid']):
            try:
                if proc.info['name'] and name_lower in proc.info['name'].lower():
                    proc.kill()
                    killed = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if killed:
            return f"✅ Процесс {name} завершён"
        return f"⚠️ Процесс {name} не найден"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


# ========== УПРАВЛЕНИЕ ОКНАМИ ==========

def list_windows() -> str:
    """Список открытых окон."""
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
    """Переключает фокус на окно."""
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
                    return f"✅ Активировано: {w.title}"
                except Exception:
                    try:
                        w.minimize()
                        w.restore()
                        w.activate()
                        return f"✅ Активировано: {w.title}"
                    except Exception:
                        return f"⚠️ Не удалось активировать: {w.title}"
        return f"⚠️ Окно '{title_part}' не найдено"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def minimize_window(title_part: str) -> str:
    """Сворачивает окно."""
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
    """Разворачивает окно."""
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
    """Закрывает окно."""
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


def resize_window(title_part: str, width: int, height: int) -> str:
    """Изменяет размер окна."""
    if not HAS_GW:
        return "⚠️ pygetwindow не установлен"

    title_clean = _clean_command(title_part, ["измени", "resize"])
    title_lower = title_clean.lower().strip()

    try:
        for w in gw.getAllWindows():
            if w.title.strip() and title_lower in w.title.lower():
                w.resizeTo(width, height)
                return f"✅ Размер изменён: {w.title} → {width}x{height}"
        return f"⚠️ Окно '{title_part}' не найдено"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def move_window(title_part: str, x: int, y: int) -> str:
    """Перемещает окно."""
    if not HAS_GW:
        return "⚠️ pygetwindow не установлен"

    title_clean = _clean_command(title_part, ["перемести", "move"])
    title_lower = title_clean.lower().strip()

    try:
        for w in gw.getAllWindows():
            if w.title.strip() and title_lower in w.title.lower():
                w.moveTo(x, y)
                return f"✅ Окно перемещено: {w.title} → ({x}, {y})"
        return f"⚠️ Окно '{title_part}' не найдено"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def make_window_always_on_top(title_part: str) -> str:
    """Делает окно всегда поверх других."""
    if not HAS_WIN32:
        return "⚠️ Установите pywin32: pip install pywin32"

    title_clean = _clean_command(title_part, ["поверх", "on top", "topmost"])
    title_lower = title_clean.lower().strip()

    try:
        def enum_windows_callback(hwnd, hwnds):
            if win32gui.IsWindowVisible(hwnd):
                if title_lower in win32gui.GetWindowText(hwnd).lower():
                    hwnds.append(hwnd)
            return True

        hwnds = []
        win32gui.EnumWindows(enum_windows_callback, hwnds)

        if not hwnds:
            return f"⚠️ Окно '{title_part}' не найдено"

        for hwnd in hwnds:
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                 win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
        return f"✅ Окно '{title_part}' теперь всегда поверх"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


# ========== УПРАВЛЕНИЕ СИСТЕМОЙ ==========

def get_system_info() -> str:
    """Информация о системе."""
    try:
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\")
        boot_time = datetime.fromtimestamp(psutil.boot_time())

        result = f"""
💻 **Информация о системе:**

🖥️ **CPU:** {cpu}% ({psutil.cpu_count()} ядер)
🧠 **RAM:** {ram.used // (1024**3)}GB / {ram.total // (1024**3)}GB ({ram.percent}%)
💾 **Диск C::** {disk.used // (1024**3)}GB / {disk.total // (1024**3)}GB ({disk.percent}%)
⏱️ **Время работы:** {_format_uptime(psutil.boot_time())}
🔄 **Загрузка:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()

        # Температура
        try:
            import wmi
            w = wmi.WMI(namespace="root\\OpenHardwareMonitor")
            sensors = w.Sensor()
            for sensor in sensors:
                if sensor.Name == "CPU Package" and sensor.SensorType == "Temperature":
                    result += f"\n🌡️ **Температура:** {float(sensor.Value):.1f}°C"
                    break
        except:
            pass

        return result
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def get_ip_info() -> str:
    """Информация об IP и сети."""
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)

        result = f"""
🌐 **Сетевая информация:**

📡 **Имя ПК:** {hostname}
🌍 **IP-адрес:** {ip}

🌐 **Интернет-соединение:** {'✅ Есть' if _check_internet() else '❌ Нет'}
        """.strip()

        try:
            import requests
            response = requests.get('http://ip-api.com/json/', timeout=5)
            data = response.json()
            if data.get('status') == 'success':
                result += f"""
🏳️ **Страна:** {data.get('country', 'Неизвестно')}
🏙️ **Город:** {data.get('city', 'Неизвестно')}
📡 **Провайдер:** {data.get('isp', 'Неизвестно')}
                """
        except:
            pass

        return result
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def set_volume(level: int) -> str:
    """Устанавливает громкость (0-100)."""
    if not HAS_PYCAW:
        return "⚠️ Установите pycaw: pip install pycaw"

    try:
        level = max(0, min(100, level))
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = interface.QueryInterface(IAudioEndpointVolume)
        volume.SetMasterVolumeLevelScalar(level / 100.0, None)
        return f"🔊 Громкость: {level}%"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def get_volume() -> str:
    """Возвращает текущую громкость."""
    if not HAS_PYCAW:
        return "⚠️ Установите pycaw: pip install pycaw"

    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = interface.QueryInterface(IAudioEndpointVolume)
        level = volume.GetMasterVolumeLevelScalar() * 100
        is_muted = volume.GetMute()
        status = "🔇 Выключен" if is_muted else "🔊 Включён"
        return f"📢 Громкость: {int(level)}% ({status})"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def mute_volume() -> str:
    """Выключает звук."""
    if not HAS_PYCAW:
        return "⚠️ Установите pycaw: pip install pycaw"

    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = interface.QueryInterface(IAudioEndpointVolume)
        volume.SetMute(True, None)
        return "🔇 Звук выключен"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def unmute_volume() -> str:
    """Включает звук."""
    if not HAS_PYCAW:
        return "⚠️ Установите pycaw: pip install pycaw"

    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = interface.QueryInterface(IAudioEndpointVolume)
        volume.SetMute(False, None)
        return "🔊 Звук включён"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def set_brightness(level: int) -> str:
    """Устанавливает яркость экрана (0-100)."""
    try:
        level = max(0, min(100, level))
        if HAS_WIN32:
            import wmi
            w = wmi.WMI(namespace='wmi')
            brightness = w.WmiMonitorBrightnessMethods()[0]
            brightness.WmiSetBrightness(level, 0)
            return f"☀️ Яркость: {level}%"
        else:
            return "⚠️ Для управления яркостью нужен pywin32 и WMI"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


# ========== УПРАВЛЕНИЕ ПИТАНИЕМ ==========

def shutdown_pc(delay: int = 0) -> str:
    """Выключает ПК."""
    try:
        if delay > 0:
            subprocess.run(f'shutdown /s /t {delay}', shell=True)
            return f"🔄 ПК выключится через {delay} секунд"
        subprocess.run('shutdown /s /t 0', shell=True)
        return "🔄 ПК выключается..."
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def restart_pc(delay: int = 0) -> str:
    """Перезагружает ПК."""
    try:
        if delay > 0:
            subprocess.run(f'shutdown /r /t {delay}', shell=True)
            return f"🔄 ПК перезагрузится через {delay} секунд"
        subprocess.run('shutdown /r /t 0', shell=True)
        return "🔄 ПК перезагружается..."
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def sleep_pc() -> str:
    """Усыпляет ПК."""
    try:
        subprocess.run('rundll32.exe powrprof.dll,SetSuspendState 0,1,0', shell=True)
        return "😴 ПК уходит в сон..."
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def lock_pc() -> str:
    """Блокирует ПК."""
    try:
        subprocess.run('rundll32.exe user32.dll,LockWorkStation', shell=True)
        return "🔒 ПК заблокирован"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def hibernate_pc() -> str:
    """Гибернация ПК."""
    try:
        subprocess.run('shutdown /h', shell=True)
        return "💤 ПК уходит в гибернацию..."
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def cancel_shutdown() -> str:
    """Отменяет выключение."""
    try:
        subprocess.run('shutdown /a', shell=True)
        return "✅ Выключение отменено"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


# ========== БУФЕР ОБМЕНА ==========

def get_clipboard() -> str:
    """Получает текст из буфера обмена."""
    if not HAS_PYPERCLIP:
        return "⚠️ Установите pyperclip: pip install pyperclip"
    try:
        text = pyperclip.paste()
        if not text:
            return "📋 Буфер обмена пуст"
        return f"📋 **Буфер обмена:**\n```\n{text[:500]}{'...' if len(text) > 500 else ''}\n```"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def set_clipboard(text: str) -> str:
    """Устанавливает текст в буфер обмена."""
    if not HAS_PYPERCLIP:
        return "⚠️ Установите pyperclip: pip install pyperclip"
    try:
        pyperclip.copy(text)
        return f"✅ Текст скопирован в буфер обмена:\n```\n{text[:200]}{'...' if len(text) > 200 else ''}\n```"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


# ========== СКРИНШОТЫ ==========

def screenshot_full() -> str:
    """Скриншот всего экрана."""
    result = take_screenshot()
    if result:
        return result
    return "⚠️ Не удалось сделать скриншот"


def screenshot_window(title_part: str) -> str:
    """Скриншот конкретного окна."""
    if not HAS_GW:
        return "⚠️ pygetwindow не установлен"

    title_clean = _clean_command(title_part, ["скриншот", "screenshot"])
    title_lower = title_clean.lower().strip()

    try:
        for w in gw.getAllWindows():
            if w.title.strip() and title_lower in w.title.lower():
                try:
                    import mss
                    import base64
                    import io
                    from PIL import Image

                    with mss.mss() as sct:
                        monitor = {
                            "left": w.left,
                            "top": w.top,
                            "width": w.width,
                            "height": w.height
                        }
                        screenshot = sct.grab(monitor)
                        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

                        max_size = 800
                        if img.width > max_size or img.height > max_size:
                            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

                        buffered = io.BytesIO()
                        img.save(buffered, format="JPEG", quality=70, optimize=True)
                        return base64.b64encode(buffered.getvalue()).decode('utf-8')
                except Exception as e:
                    return f"⚠️ Ошибка скриншота окна: {str(e)}"

        return f"⚠️ Окно '{title_part}' не найдено"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


def screenshot_region(x: int, y: int, width: int, height: int) -> str:
    """Скриншот области экрана."""
    try:
        import mss
        import base64
        import io
        from PIL import Image

        with mss.mss() as sct:
            monitor = {"left": x, "top": y, "width": width, "height": height}
            screenshot = sct.grab(monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

            buffered = io.BytesIO()
            img.save(buffered, format="JPEG", quality=70, optimize=True)
            return base64.b64encode(buffered.getvalue()).decode('utf-8')
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


# ========== ТАЙМЕРЫ ==========

def set_timer(seconds: int, action: str) -> str:
    """Устанавливает таймер."""
    if seconds < 1:
        return "⚠️ Время должно быть больше 0"

    def timer_thread():
        time.sleep(seconds)
        show_notification("⏰ Таймер", f"Время вышло! {action}")
        _system_timers[:] = [t for t in _system_timers if t.get('thread') != threading.current_thread()]

    t = threading.Thread(target=timer_thread, daemon=True)
    t.start()

    _system_timers.append({
        "seconds": seconds,
        "action": action,
        "time": datetime.now(),
        "thread": t
    })

    return f"⏰ Таймер установлен на {seconds} секунд: {action}"


def list_timers() -> str:
    """Список активных таймеров."""
    if not _system_timers:
        return "📭 Нет активных таймеров"

    result = "⏰ **Активные таймеры:**\n"
    for i, t in enumerate(_system_timers, 1):
        elapsed = int((datetime.now() - t['time']).total_seconds())
        remaining = max(0, t['seconds'] - elapsed)
        result += f"  {i}. {t['action']} — осталось {remaining} сек\n"
    return result


def cancel_timer(index: int) -> str:
    """Отменяет таймер по индексу."""
    if 1 <= index <= len(_system_timers):
        _system_timers.pop(index - 1)
        return f"✅ Таймер {index} отменён"
    return f"⚠️ Таймер {index} не найден"


# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

def _clean_command(text: str, commands: List[str]) -> str:
    """Убирает команды из текста."""
    result = text.strip()
    for cmd in commands:
        if result.lower().startswith(cmd):
            result = result[len(cmd):].strip()
            break
    return result


def _format_uptime(boot_time: float) -> str:
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


def _check_internet() -> bool:
    """Проверяет доступ к интернету."""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except Exception:
        return False


def show_notification(title: str, message: str) -> None:
    """Показывает уведомление."""
    try:
        from plyer import notification
        notification.notify(title=title, message=message, app_name="Zeta", timeout=10)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x40)
        except Exception:
            print(f"[Уведомление] {title}: {message}")


# ========== ЭКСПОРТ ==========

__all__ = [
    'open_app', 'close_app', 'list_running_apps', 'kill_process',
    'list_windows', 'focus_window', 'minimize_window', 'maximize_window',
    'close_window', 'resize_window', 'move_window', 'make_window_always_on_top',
    'get_system_info', 'get_ip_info',
    'set_volume', 'get_volume', 'mute_volume', 'unmute_volume', 'set_brightness',
    'shutdown_pc', 'restart_pc', 'sleep_pc', 'lock_pc', 'hibernate_pc', 'cancel_shutdown',
    'get_clipboard', 'set_clipboard',
    'screenshot_full', 'screenshot_window', 'screenshot_region',
    'set_timer', 'list_timers', 'cancel_timer',
]


# ========== ТЕСТ ==========
if __name__ == "__main__":
    print("🧪 Тест pc_control.py\n")
    
    print("📝 Тест 1: Информация о системе")
    print(get_system_info())
    print("-" * 40)
    
    print("📝 Тест 2: Информация об IP")
    print(get_ip_info())
    print("-" * 40)
    
    print("📝 Тест 3: Список окон")
    windows = list_windows()
    print(windows[:200] + "..." if len(windows) > 200 else windows)
    print("-" * 40)
    
    print("📝 Тест 4: Громкость")
    print(get_volume())
    print("-" * 40)
    
    print("📝 Тест 5: Список запущенных процессов")
    apps = list_running_apps()
    print(apps[:200] + "..." if len(apps) > 200 else apps)
    print("-" * 40)
    
    print("\n✅ Тесты завершены!")