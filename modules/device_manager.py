# -*- coding: utf-8 -*-
"""Управление устройствами Zeta — клиент (логика)."""

import os
import json
import time
import uuid
import socket
import struct
import threading
import requests
from typing import List, Dict, Any, Optional, Callable

DATA_DIR = r"D:\Zeta\data"
DEVICES_FILE = os.path.join(DATA_DIR, "devices.json")

AGENT_PORT = 5670
HOST_PORT = 5671
DISCOVER_PORT = 5672
DISCOVER_MSG = b"ZETA_DISCOVER_V1"
DISCOVER_REPLY = b"ZETA_HERE_V1"
DISCOVER_TIMEOUT = 2.0
HTTP_TIMEOUT = 10
UPLOAD_TIMEOUT = 120


def _log(msg: str) -> None:
    try:
        from main import log_info
        log_info(f"🌐 [Dev] {msg}")
    except Exception:
        print(f"🌐 [Dev] {msg}")


def _log_err(msg: str) -> None:
    try:
        from main import log_error
        log_error(f"🌐 [Dev] {msg}")
    except Exception:
        print(f"❌ [Dev] {msg}")


# ========== ХРАНИЛИЩЕ УСТРОЙСТВ ==========

class DeviceStorage:
    def __init__(self, path: str = DEVICES_FILE):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def load(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("devices", []) if isinstance(data, dict) else []
        except Exception as e:
            _log_err(f"load: {e}")
            return []

    def save(self, devices: List[Dict[str, Any]]) -> bool:
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"version": 1, "devices": devices}, f,
                          ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
            return True
        except Exception as e:
            _log_err(f"save: {e}")
            return False


# ========== СЕТЕВЫЕ УТИЛИТЫ ==========

def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_broadcast_ip() -> str:
    ip = get_local_ip()
    parts = ip.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.{parts[2]}.255"
    return "255.255.255.255"


def build_magic_packet(mac: str) -> bytes:
    mac_clean = mac.replace(":", "").replace("-", "").replace(".", "")
    if len(mac_clean) != 12:
        raise ValueError(f"Неверный MAC: {mac}")
    mac_bytes = bytes.fromhex(mac_clean)
    return b"\xff" * 6 + mac_bytes * 16


# ========== МЕНЕДЖЕР УСТРОЙСТВ ==========

class DeviceManager:
    def __init__(self):
        self.storage = DeviceStorage()
        self.devices: List[Dict[str, Any]] = []
        self._lock = threading.RLock()
        self._discover_stop = threading.Event()
        self._listeners: List[Callable] = []

    # ----- CRUD -----

    def load(self) -> None:
        with self._lock:
            self.devices = self.storage.load()
        _log(f"Загружено устройств: {len(self.devices)}")

    def save(self) -> bool:
        with self._lock:
            return self.storage.save(self.devices)

    def get_all(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(d) for d in self.devices]

    def get(self, dev_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            for d in self.devices:
                if d.get("id") == dev_id:
                    return dict(d)
        return None

    def add(self, name: str, ip: str, token: str,
            mac: str = "", port: int = AGENT_PORT) -> str:
        dev = {
            "id": uuid.uuid4().hex[:8],
            "name": name,
            "ip": ip,
            "port": port,
            "token": token,
            "mac": mac,
            "added_at": time.time(),
            "last_seen": 0,
            "online": False,
        }
        with self._lock:
            self.devices.append(dev)
        self.save()
        _log(f"Добавлено устройство: {name} ({ip})")
        return dev["id"]

    def update(self, dev_id: str, updates: Dict[str, Any]) -> bool:
        with self._lock:
            for d in self.devices:
                if d.get("id") == dev_id:
                    d.update(updates)
                    self.save()
                    return True
        return False

    def delete(self, dev_id: str) -> bool:
        with self._lock:
            before = len(self.devices)
            self.devices = [d for d in self.devices if d.get("id") != dev_id]
            changed = len(self.devices) != before
        if changed:
            self.save()
        return changed

    # ----- Сканирование LAN -----

    def discover(self, timeout: float = DISCOVER_TIMEOUT) -> List[Dict[str, Any]]:
        """UDP broadcast — найти агентов в сети."""
        found: Dict[str, Dict[str, Any]] = {}
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.5)
        try:
            sock.bind(("", 0))
        except Exception as e:
            _log_err(f"discover bind: {e}")
            sock.close()
            return []

        try:
            sock.sendto(DISCOVER_MSG, (get_broadcast_ip(), DISCOVER_PORT))
        except Exception as e:
            _log_err(f"discover send: {e}")

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except Exception:
                break
            if data.startswith(DISCOVER_REPLY):
                try:
                    info = json.loads(data[len(DISCOVER_REPLY):].decode("utf-8"))
                except Exception:
                    continue
                ip = addr[0]
                found[ip] = {
                    "ip": ip,
                    "name": info.get("name", "Без имени"),
                    "hostname": info.get("hostname", ""),
                    "port": int(info.get("port", AGENT_PORT)),
                    "os": info.get("os", ""),
                    "needs_token": True,
                }
        sock.close()
        _log(f"Найдено устройств: {len(found)}")
        return list(found.values())

    # ----- HTTP-запросы к агенту -----

    def _headers(self, dev: Dict[str, Any]) -> Dict[str, str]:
        return {
            "X-Zeta-Token": dev.get("token", ""),
            "X-Zeta-From": get_local_ip(),
            "User-Agent": "Zeta-Client/1.0",
        }

    def _url(self, dev: Dict[str, Any], path: str) -> str:
        return f"http://{dev['ip']}:{dev.get('port', AGENT_PORT)}{path}"

    def ping(self, dev: Dict[str, Any]) -> bool:
        try:
            r = requests.get(self._url(dev, "/ping"),
                             headers=self._headers(dev),
                             timeout=3)
            if r.status_code == 200:
                self.update(dev["id"], {"online": True,
                                        "last_seen": time.time()})
                return True
        except Exception:
            pass
        self.update(dev["id"], {"online": False})
        return False

    def screenshot(self, dev: Dict[str, Any],
                   save_path: Optional[str] = None) -> Optional[str]:
        try:
            r = requests.post(self._url(dev, "/screenshot"),
                              headers=self._headers(dev),
                              timeout=HTTP_TIMEOUT)
            if r.status_code != 200:
                _log_err(f"screenshot: статус {r.status_code}")
                return None
            if save_path is None:
                os.makedirs(os.path.join(DATA_DIR, "screenshots"), exist_ok=True)
                ts = time.strftime("%Y%m%d_%H%M%S")
                safe = dev.get("name", "device").replace(" ", "_")
                save_path = os.path.join(DATA_DIR, "screenshots",
                                         f"{safe}_{ts}.png")
            with open(save_path, "wb") as f:
                f.write(r.content)
            _log(f"Скриншот с {dev['name']}: {save_path}")
            return save_path
        except Exception as e:
            _log_err(f"screenshot: {e}")
            return None

    def send_file(self, dev: Dict[str, Any], local_path: str) -> bool:
        if not os.path.exists(local_path):
            _log_err(f"send_file: нет файла {local_path}")
            return False
        try:
            with open(local_path, "rb") as f:
                files = {"file": (os.path.basename(local_path), f)}
                r = requests.post(self._url(dev, "/upload"),
                                  headers=self._headers(dev),
                                  files=files,
                                  timeout=UPLOAD_TIMEOUT)
            ok = r.status_code == 200
            _log(f"send_file → {dev['name']}: {'OK' if ok else r.status_code}")
            return ok
        except Exception as e:
            _log_err(f"send_file: {e}")
            return False

    def shutdown(self, dev: Dict[str, Any], delay: int = 30,
                 reboot: bool = False) -> bool:
        try:
            path = "/reboot" if reboot else "/shutdown"
            r = requests.post(self._url(dev, path),
                              headers=self._headers(dev),
                              json={"delay": delay},
                              timeout=HTTP_TIMEOUT)
            ok = r.status_code == 200
            _log(f"{'reboot' if reboot else 'shutdown'} {dev['name']}: {'OK' if ok else r.status_code}")
            return ok
        except Exception as e:
            _log_err(f"shutdown: {e}")
            return False

    def cancel_shutdown(self, dev: Dict[str, Any]) -> bool:
        try:
            r = requests.post(self._url(dev, "/shutdown_cancel"),
                              headers=self._headers(dev),
                              timeout=HTTP_TIMEOUT)
            return r.status_code == 200
        except Exception:
            return False

    def wake_on_lan(self, dev: Dict[str, Any]) -> bool:
        mac = dev.get("mac", "")
        if not mac:
            _log_err("wake_on_lan: нет MAC")
            return False
        try:
            packet = build_magic_packet(mac)
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            broadcast = get_broadcast_ip()
            for _ in range(3):
                s.sendto(packet, (broadcast, 9))
                time.sleep(0.1)
            s.close()
            _log(f"WOL → {mac}")
            return True
        except Exception as e:
            _log_err(f"wake_on_lan: {e}")
            return False

    def get_remote_clipboard(self, dev: Dict[str, Any]) -> Optional[str]:
        try:
            r = requests.get(self._url(dev, "/clipboard"),
                             headers=self._headers(dev),
                             timeout=5)
            if r.status_code == 200:
                return r.json().get("text", "")
        except Exception:
            pass
        return None

    def set_remote_clipboard(self, dev: Dict[str, Any], text: str) -> bool:
        try:
            r = requests.post(self._url(dev, "/clipboard"),
                              headers=self._headers(dev),
                              json={"text": text},
                              timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def system_info(self, dev: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            r = requests.get(self._url(dev, "/info"),
                             headers=self._headers(dev),
                             timeout=5)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None


# ========== СИНГЛТОН ==========

_manager: Optional[DeviceManager] = None
_manager_lock = threading.Lock()


def get_device_manager() -> DeviceManager:
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = DeviceManager()
    return _manager


if __name__ == "__main__":
    dm = get_device_manager()
    dm.load()
    print(f"Устройств: {len(dm.get_all())}")
    print("Сканирование LAN...")
    for d in dm.discover():
        print(f"  • {d['name']} — {d['ip']}:{d['port']}")