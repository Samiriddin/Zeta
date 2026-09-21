# -*- coding: utf-8 -*-
"""
Zeta Agent — запускается на управляемых ПК.
Слушает порт 5670, отвечает на UDP-discovery на 5672.

ИСПРАВЛЕНО (2026-09-21):
    - subprocess без shell=True (защита от инъекций)
    - IP берётся из request.client.host, а не из заголовка
    - Уникальные имена скриншотов (uuid)
    - load_config: битый конфиг → .bak + создание нового
    - Логирование успешных auth
    - Лимит размера загрузки (MAX_UPLOAD_MB)
    - /shutdown_cancel уважает allow_shutdown
    - Маскировка токена в консольном баннере
"""

import os
import sys
import json
import time
import uuid
import socket
import secrets
import logging
import platform
import subprocess
import threading
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import FastAPI, Header, HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse, JSONResponse
import uvicorn
import psutil

try:
    import mss
    from PIL import Image
    HAS_SCREEN = True
except ImportError:
    HAS_SCREEN = False

try:
    import pyperclip
    HAS_CLIP = True
except ImportError:
    HAS_CLIP = False


# ========== КОНСТАНТЫ ==========

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(AGENT_DIR, "agent_config.json")
TOKEN_FILE = os.path.join(AGENT_DIR, "agent_token.txt")
RECEIVED_DIR = os.path.join(AGENT_DIR, "received")
LOG_FILE = os.path.join(AGENT_DIR, "agent.log")

HTTP_PORT = 5670
DISCOVER_PORT = 5672
DISCOVER_MSG = b"ZETA_DISCOVER_V1"
DISCOVER_REPLY = b"ZETA_HERE_V1"

# ИСПРАВЛЕНО: лимит загрузки
MAX_UPLOAD_MB = 500


# ========== КОНФИГ ==========

def load_config() -> dict:
    """
    ИСПРАВЛЕНО: если конфиг битый — бэкапим и создаём новый.
    """
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                # Валидация ключей
                cfg.setdefault("port", HTTP_PORT)
                cfg.setdefault("name", platform.node() or "Zeta-PC")
                cfg.setdefault("whitelist_ips", [])
                cfg.setdefault("allow_shutdown", True)
                cfg.setdefault("allow_clipboard", True)
                cfg.setdefault("allow_files", True)
                cfg.setdefault("received_dir", RECEIVED_DIR)
                return cfg
        except Exception as e:
            # ИСПРАВЛЕНО: сохраняем битый конфиг как .bak
            backup = CONFIG_FILE + ".bak"
            try:
                if os.path.exists(backup):
                    os.remove(backup)
                os.rename(CONFIG_FILE, backup)
                print(f"⚠️ Битый конфиг сохранён: {backup}")
            except Exception:
                pass
            print(f"⚠️ Ошибка загрузки конфига: {e}. Создаю новый.")

    cfg = {
        "port": HTTP_PORT,
        "name": platform.node() or "Zeta-PC",
        "whitelist_ips": [],
        "allow_shutdown": True,
        "allow_clipboard": True,
        "allow_files": True,
        "received_dir": RECEIVED_DIR,
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return cfg


def load_or_create_token() -> str:
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                t = f.read().strip()
                if len(t) >= 16:
                    return t
        except Exception:
            pass

    token = secrets.token_hex(24)
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(token)
    return token


CONFIG = load_config()
TOKEN = load_or_create_token()
os.makedirs(CONFIG.get("received_dir", RECEIVED_DIR), exist_ok=True)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    encoding="utf-8",
)


def log(msg: str) -> None:
    print(f"[Agent] {msg}")
    logging.info(msg)


def log_warn(msg: str) -> None:
    print(f"[Agent] ⚠️ {msg}")
    logging.warning(msg)


# ========== АУТЕНТИФИКАЦИЯ ==========

def get_client_ip(request: Request) -> str:
    """
    ИСПРАВЛЕНО: получаем IP из request.client.host, а не из заголовка.
    """
    try:
        if request.client:
            return request.client.host
    except Exception:
        pass
    return "unknown"


def check_auth(token: str, request: Request) -> str:
    """
    ИСПРАВЛЕНО:
        - IP берётся из request, а не из заголовка
        - Логирование успешных auth
    Возвращает IP клиента.
    """
    client_ip = get_client_ip(request)

    if token != TOKEN:
        log_warn(f"❌ Неверный токен от {client_ip}")
        raise HTTPException(status_code=403, detail="Invalid token")

    wl = CONFIG.get("whitelist_ips", [])
    if wl and client_ip not in wl:
        log_warn(f"❌ IP {client_ip} не в whitelist")
        raise HTTPException(status_code=403, detail="IP not allowed")

    # ИСПРАВЛЕНО: логируем успешный auth
    log(f"✅ Auth OK от {client_ip}")
    return client_ip


# ========== FASTAPI ==========

app = FastAPI(title="Zeta Agent", version="1.1")


@app.get("/ping")
def ping(
    request: Request,
    x_zeta_token: str = Header(default=""),
):
    check_auth(x_zeta_token, request)
    return {"ok": True, "name": CONFIG["name"], "time": time.time()}


@app.get("/info")
def info(
    request: Request,
    x_zeta_token: str = Header(default=""),
):
    check_auth(x_zeta_token, request)
    return {
        "name": CONFIG["name"],
        "hostname": platform.node(),
        "os": f"{platform.system()} {platform.release()}",
        "cpu": psutil.cpu_percent(interval=0.3),
        "ram": psutil.virtual_memory().percent,
        "uptime": time.time() - psutil.boot_time(),
        "port": CONFIG["port"],
    }


@app.post("/screenshot")
def screenshot(
    request: Request,
    x_zeta_token: str = Header(default=""),
):
    check_auth(x_zeta_token, request)
    if not HAS_SCREEN:
        raise HTTPException(status_code=500, detail="mss/Pillow не установлены")

    # ИСПРАВЛЕНО: уникальное имя файла (без race condition)
    filename = f"_screen_{uuid.uuid4().hex[:8]}.png"
    tmp = os.path.join(CONFIG["received_dir"], filename)

    try:
        with mss.mss() as sct:
            sct.shot(output=tmp)
        return FileResponse(
            tmp,
            media_type="image/png",
            filename="screenshot.png",
        )
    except Exception as e:
        log_warn(f"Ошибка скриншота: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload")
async def upload(
    request: Request,
    file: UploadFile = File(...),
    x_zeta_token: str = Header(default=""),
):
    check_auth(x_zeta_token, request)
    if not CONFIG.get("allow_files", True):
        raise HTTPException(status_code=403, detail="Files disabled")

    safe_name = os.path.basename(file.filename or "file.bin")
    dest = os.path.join(CONFIG["received_dir"], safe_name)

    # ИСПРАВЛЕНО: лимит размера
    total = 0
    max_bytes = MAX_UPLOAD_MB * 1024 * 1024

    try:
        with open(dest, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    f.close()
                    try:
                        os.remove(dest)
                    except Exception:
                        pass
                    raise HTTPException(
                        status_code=413,
                        detail=f"Файл больше {MAX_UPLOAD_MB} MB",
                    )
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        log_warn(f"Ошибка загрузки: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    log(f"📁 Получен файл: {safe_name} ({total} байт)")
    return {"ok": True, "saved": dest, "size": total}


# ========== ПИТАНИЕ (без shell=True) ==========

def _run_shutdown(args: list) -> bool:
    """
    ИСПРАВЛЕНО: запуск shutdown без shell=True.
    """
    try:
        if os.name == "nt":
            subprocess.Popen(
                args,
                shell=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            subprocess.Popen(args, shell=False)
        return True
    except Exception as e:
        log_warn(f"Ошибка shutdown: {e}")
        return False


@app.post("/shutdown")
def shutdown(
    request: Request,
    payload: Optional[dict] = None,
    x_zeta_token: str = Header(default=""),
):
    client_ip = check_auth(x_zeta_token, request)

    if not CONFIG.get("allow_shutdown", True):
        raise HTTPException(status_code=403, detail="Shutdown disabled")

    # ИСПРАВЛЕНО: безопасный int
    try:
        delay = int((payload or {}).get("delay", 30))
        delay = max(0, min(delay, 3600))  # 0..3600 сек
    except (ValueError, TypeError):
        delay = 30

    log(f"⚡ Выключение через {delay}с (от {client_ip})")

    # ИСПРАВЛЕНО: без shell=True
    ok = _run_shutdown(["shutdown", "/s", "/t", str(delay)])
    if not ok:
        raise HTTPException(status_code=500, detail="Не удалось выполнить shutdown")

    return {"ok": True, "delay": delay}


@app.post("/reboot")
def reboot(
    request: Request,
    payload: Optional[dict] = None,
    x_zeta_token: str = Header(default=""),
):
    client_ip = check_auth(x_zeta_token, request)

    if not CONFIG.get("allow_shutdown", True):
        raise HTTPException(status_code=403, detail="Shutdown disabled")

    try:
        delay = int((payload or {}).get("delay", 30))
        delay = max(0, min(delay, 3600))
    except (ValueError, TypeError):
        delay = 30

    log(f"🔄 Перезагрузка через {delay}с (от {client_ip})")

    ok = _run_shutdown(["shutdown", "/r", "/t", str(delay)])
    if not ok:
        raise HTTPException(status_code=500, detail="Не удалось выполнить reboot")

    return {"ok": True, "delay": delay}


@app.post("/shutdown_cancel")
def shutdown_cancel(
    request: Request,
    x_zeta_token: str = Header(default=""),
):
    client_ip = check_auth(x_zeta_token, request)

    # ИСПРАВЛЕНО: уважаем allow_shutdown
    if not CONFIG.get("allow_shutdown", True):
        raise HTTPException(status_code=403, detail="Shutdown disabled")

    ok = _run_shutdown(["shutdown", "/a"])
    if not ok:
        raise HTTPException(status_code=500, detail="Не удалось отменить shutdown")

    log(f"🛑 Отмена выключения (от {client_ip})")
    return {"ok": True}


# ========== БУФЕР ОБМЕНА ==========

@app.get("/clipboard")
def get_clipboard(
    request: Request,
    x_zeta_token: str = Header(default=""),
):
    check_auth(x_zeta_token, request)

    if not CONFIG.get("allow_clipboard", True):
        raise HTTPException(status_code=403, detail="Clipboard disabled")

    if not HAS_CLIP:
        return {"text": ""}

    try:
        return {"text": pyperclip.paste() or ""}
    except Exception:
        return {"text": ""}


@app.post("/clipboard")
def set_clipboard(
    request: Request,
    payload: dict,
    x_zeta_token: str = Header(default=""),
):
    client_ip = check_auth(x_zeta_token, request)

    if not CONFIG.get("allow_clipboard", True):
        raise HTTPException(status_code=403, detail="Clipboard disabled")

    if not HAS_CLIP:
        raise HTTPException(status_code=500, detail="pyperclip не установлен")

    try:
        pyperclip.copy(payload.get("text", ""))
        log(f"📋 Буфер обмена обновлён (от {client_ip})")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== UDP DISCOVERY ==========

def discovery_server() -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    try:
        s.bind(("", DISCOVER_PORT))
    except Exception as e:
        log_warn(f"Discovery bind error: {e}")
        return

    log(f"🔍 Discovery сервер на :{DISCOVER_PORT}")

    while True:
        try:
            data, addr = s.recvfrom(1024)
        except Exception:
            continue

        if data.startswith(DISCOVER_MSG):
            reply = {
                "name": CONFIG["name"],
                "hostname": platform.node(),
                "port": CONFIG["port"],
                "os": platform.system(),
            }
            payload = DISCOVER_REPLY + json.dumps(reply).encode("utf-8")
            try:
                s.sendto(payload, addr)
            except Exception as e:
                log_warn(f"Discovery reply error: {e}")


# ========== ЗАПУСК ==========

def _mask_token(token: str) -> str:
    """ИСПРАВЛЕНО: маскировка токена в баннере."""
    if len(token) <= 8:
        return "***"
    return token[:4] + "..." + token[-4:]


def print_banner() -> None:
    print("=" * 60)
    print(f"  🤖 Zeta Agent v1.1")
    print(f"  Имя:    {CONFIG['name']}")
    print(f"  Порт:   {CONFIG['port']}")
    print(f"  Токен:  {_mask_token(TOKEN)}")
    print(f"  Файлы:  {CONFIG['received_dir']}")
    print("=" * 60)
    print("  ⚠️  Полный токен смотри в файле agent_token.txt")
    print("=" * 60)


def main() -> None:
    print_banner()

    t = threading.Thread(target=discovery_server, daemon=True)
    t.start()

    log(f"🚀 HTTP-сервер на 0.0.0.0:{CONFIG['port']}")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=CONFIG["port"],
        log_level="warning",
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nОстановлен.")