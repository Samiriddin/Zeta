# -*- coding: utf-8 -*-
"""
Модуль автоматизации Zeta.
Правила: триггер + действия.

Триггеры:
    - time      : срабатывает в HH:MM
    - weekday   : срабатывает в HH:MM в определённые дни недели
    - cpu       : CPU выше порога N% (устойчиво M секунд)
    - ram       : RAM выше порога N%
    - startup   : при запуске Zeta
    - shutdown  : при выключении Zeta

Действия:
    - notify        : уведомление Windows
    - speak         : озвучка через Zeta TTS
    - open_file     : открыть файл/папку
    - run_command   : выполнить команду
    - backup        : запустить бэкап
    - screenshot    : сделать скриншот
    - system_status : получить статус системы

Хранение: data/automation.json
"""

import os
import json
import time
import uuid
import threading
import subprocess
from datetime import datetime
from typing import List, Dict, Any, Optional

# ========== КОНСТАНТЫ ==========

AUTOMATION_FILE = r"D:\Zeta\data\automation.json"

# Интервал проверки триггеров (сек)
CHECK_INTERVAL = 30

# Сколько секунд CPU/RAM должен держаться выше порога (антидребезг)
SUSTAINED_SECONDS = 60

# Максимум срабатываний одного правила в час (защита от спама)
MAX_FIRES_PER_HOUR = 3


# ========== ЛОГИРОВАНИЕ ==========

def _log(msg: str) -> None:
    try:
        from main import log_info
        log_info(f"🤖 [Auto] {msg}")
    except Exception:
        print(f"🤖 [Auto] {msg}")


def _log_err(msg: str) -> None:
    try:
        from main import log_error
        log_error(f"🤖 [Auto] {msg}")
    except Exception:
        print(f"❌ [Auto] {msg}")


# ========== ХРАНИЛИЩЕ ==========

class AutomationStorage:
    """Загрузка/сохранение правил в JSON"""

    def __init__(self, path: str = AUTOMATION_FILE):
        self.path = path
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)

    def load(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data.get("rules", [])
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            _log_err(f"Не удалось загрузить правила: {e}")
            return []

    def save(self, rules: List[Dict[str, Any]]) -> bool:
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(
                    {"version": 1, "rules": rules},
                    f,
                    ensure_ascii=False,
                    indent=2
                )
            os.replace(tmp, self.path)
            return True
        except Exception as e:
            _log_err(f"Не удалось сохранить правила: {e}")
            return False


# ========== ДЕЙСТВИЯ ==========

class ActionRunner:
    """Выполнение действий"""

    @staticmethod
    def notify(params: Dict[str, Any]) -> bool:
        title = params.get("title", "Zeta")
        message = params.get("message", "")
        try:
            from modules.notifications import show_notification
            show_notification(title, message)
            return True
        except Exception:
            try:
                ps = (
                    f'[reflection.assembly]::loadwithpartialname("System.Windows.Forms") | Out-Null;'
                    f'$n=New-Object System.Windows.Forms.NotifyIcon;'
                    f'$n.Icon=[System.Drawing.SystemIcons]::Information;'
                    f'$n.Visible=$true;'
                    f'$n.ShowBalloonTip(5000,"{title}","{message}",'
                    f'[System.Windows.Forms.ToolTipIcon]::Info);'
                    f'Start-Sleep -Seconds 6;$n.Dispose()'
                )
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-Command", ps],
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                return True
            except Exception as e2:
                _log_err(f"notify (fallback): {e2}")
                return False

    @staticmethod
    def speak(params: Dict[str, Any]) -> bool:
        text = params.get("text", "")
        voice = params.get("voice")
        if not text:
            return False
        try:
            from voice.tts import speak as tts_speak
            try:
                if voice:
                    tts_speak(text, voice=voice)
                else:
                    tts_speak(text)
            except TypeError:
                tts_speak(text)
            return True
        except Exception as e:
            _log_err(f"speak: {e}")
            return False

    @staticmethod
    def open_file(params: Dict[str, Any]) -> bool:
        path = params.get("path", "")
        if not path or not os.path.exists(path):
            _log_err(f"open_file: путь не найден — {path}")
            return False
        try:
            os.startfile(path)  # type: ignore[attr-defined]
            return True
        except Exception as e:
            _log_err(f"open_file: {e}")
            return False

    @staticmethod
    def run_command(params: Dict[str, Any]) -> bool:
        cmd = params.get("command", "")
        if not cmd:
            return False
        try:
            subprocess.Popen(
                cmd,
                shell=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            return True
        except Exception as e:
            _log_err(f"run_command: {e}")
            return False

    @staticmethod
    def backup(params: Dict[str, Any]) -> bool:
        try:
            from security.backup import create_backup
            ok = create_backup(manual=True)
            return bool(ok)
        except Exception as e:
            _log_err(f"backup: {e}")
            return False

    @staticmethod
    def screenshot(params: Dict[str, Any]) -> bool:
        save_path = params.get("path")
        try:
            from core.screen_capture import capture_screen
            result = capture_screen(save_path) if save_path else capture_screen()
            return bool(result)
        except Exception as e:
            _log_err(f"screenshot: {e}")
            return False

    @staticmethod
    def system_status(params: Dict[str, Any]) -> bool:
        try:
            from modules.system_monitor import get_status
            status = get_status()
            if isinstance(status, dict):
                cpu = status.get("cpu", "?")
                ram = status.get("ram", "?")
                msg = f"CPU: {cpu}%  RAM: {ram}%"
            else:
                msg = str(status)
            _log(f"system_status: {msg}")

            if params.get("notify", False):
                ActionRunner.notify({
                    "title": "📊 Zeta — статус",
                    "message": msg
                })
            return True
        except Exception as e:
            _log_err(f"system_status: {e}")
            return False

    @classmethod
    def run(cls, action_type: str, params: Dict[str, Any]) -> bool:
        handler = getattr(cls, action_type, None)
        if handler is None:
            _log_err(f"Неизвестное действие: {action_type}")
            return False
        try:
            return handler(params)
        except Exception as e:
            _log_err(f"Действие {action_type} упало: {e}")
            return False


# ========== ТРИГГЕРЫ ==========

class TriggerChecker:
    """Проверка условий триггеров"""

    def __init__(self):
        self._cpu_high_since: Optional[float] = None
        self._ram_high_since: Optional[float] = None

    def _now(self) -> datetime:
        return datetime.now()

    def _matches_time(self, rule: Dict[str, Any], now: datetime) -> bool:
        target = rule.get("time", "")
        if not target:
            return False
        try:
            hh, mm = target.split(":")
            h, m = int(hh), int(mm)
        except Exception:
            return False
        return now.hour == h and now.minute == m

    def _matches_weekday(self, rule: Dict[str, Any], now: datetime) -> bool:
        if not self._matches_time(rule, now):
            return False
        days = rule.get("weekdays", [])
        if not days:
            return True
        return now.weekday() in days

    def _matches_threshold(
        self,
        rule: Dict[str, Any],
        kind: str,
        sustain_attr: str,
        now_ts: float
    ) -> bool:
        threshold = rule.get("threshold")
        if threshold is None:
            return False
        try:
            threshold = float(threshold)
        except Exception:
            return False

        try:
            import psutil
            if kind == "cpu":
                current = psutil.cpu_percent(interval=None)
            else:
                current = psutil.virtual_memory().percent
        except Exception as e:
            _log_err(f"{kind} check: {e}")
            return False

        if current < threshold:
            setattr(self, sustain_attr, None)
            return False

        since = getattr(self, sustain_attr)
        if since is None:
            setattr(self, sustain_attr, now_ts)
            return False

        if now_ts - since >= SUSTAINED_SECONDS:
            return True
        return False

    def check(
        self,
        rule: Dict[str, Any],
        fired_keys: set,
        now_ts: float
    ) -> Optional[str]:
        ttype = rule.get("trigger", "")
        now = self._now()
        key = None

        if ttype == "time":
            if self._matches_time(rule, now):
                key = f"{rule['id']}:time:{now.strftime('%Y%m%d%H%M')}"

        elif ttype == "weekday":
            if self._matches_weekday(rule, now):
                key = f"{rule['id']}:wd:{now.strftime('%Y%m%d%H%M')}"

        elif ttype == "cpu":
            if self._matches_threshold(rule, "cpu", "_cpu_high_since", now_ts):
                key = f"{rule['id']}:cpu:{int(now_ts // 3600)}"

        elif ttype == "ram":
            if self._matches_threshold(rule, "ram", "_ram_high_since", now_ts):
                key = f"{rule['id']}:ram:{int(now_ts // 3600)}"

        if key and key in fired_keys:
            return None
        return key


# ========== ОСНОВНОЙ ДВИЖОК ==========

class AutomationEngine:
    """Движок автоматизации"""

    def __init__(self, storage: Optional[AutomationStorage] = None):
        self.storage = storage or AutomationStorage()
        self.rules: List[Dict[str, Any]] = []
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()

        self._fired_keys: set = set()
        self._fire_log: Dict[str, List[float]] = {}

        self.trigger_checker = TriggerChecker()

    # ----- CRUD -----

    def load(self) -> None:
        with self._lock:
            self.rules = self.storage.load()
        _log(f"Загружено правил: {len(self.rules)}")

    def save(self) -> bool:
        with self._lock:
            return self.storage.save(self.rules)

    def add_rule(self, rule: Dict[str, Any]) -> str:
        if "id" not in rule:
            rule["id"] = uuid.uuid4().hex[:8]
        rule.setdefault("enabled", True)
        rule.setdefault("name", "Без названия")
        with self._lock:
            self.rules.append(rule)
        self.save()
        return rule["id"]

    def update_rule(self, rule_id: str, updates: Dict[str, Any]) -> bool:
        with self._lock:
            for r in self.rules:
                if r.get("id") == rule_id:
                    r.update(updates)
                    self.save()
                    return True
        return False

    def delete_rule(self, rule_id: str) -> bool:
        with self._lock:
            before = len(self.rules)
            self.rules = [r for r in self.rules if r.get("id") != rule_id]
            changed = len(self.rules) != before
        if changed:
            self.save()
        return changed

    def get_rule(self, rule_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            for r in self.rules:
                if r.get("id") == rule_id:
                    return dict(r)
        return None

    def get_all(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self.rules]

    # ----- Запуск/остановка -----

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            _log("Уже запущено")
            return

        self.load()
        self._stop_event.clear()

        self._fire_startup_or_shutdown("startup")

        self._thread = threading.Thread(
            target=self._loop,
            name="ZetaAutomation",
            daemon=True
        )
        self._thread.start()
        _log(f"Движок запущен (правил: {len(self.rules)})")

    def stop(self) -> None:
        self._fire_startup_or_shutdown("shutdown")

        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        _log("Движок остановлен")

    # ----- Основной цикл -----

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception as e:
                _log_err(f"Ошибка в цикле: {e}")

            if len(self._fired_keys) > 5000:
                self._fired_keys.clear()

            self._stop_event.wait(CHECK_INTERVAL)

    def _tick(self) -> None:
        now_ts = time.time()
        with self._lock:
            rules = [dict(r) for r in self.rules]

        for rule in rules:
            if not rule.get("enabled", True):
                continue

            ttype = rule.get("trigger", "")
            if ttype in ("startup", "shutdown"):
                continue

            try:
                key = self.trigger_checker.check(rule, self._fired_keys, now_ts)
            except Exception as e:
                _log_err(f"Проверка правила {rule.get('name')}: {e}")
                continue

            if not key:
                continue

            if not self._allow_fire(rule["id"], now_ts):
                continue

            self._fired_keys.add(key)
            self._fire_rule(rule, reason=ttype)

    # ----- Срабатывание -----

    def _allow_fire(self, rule_id: str, now_ts: float) -> bool:
        log = self._fire_log.setdefault(rule_id, [])
        log[:] = [t for t in log if now_ts - t < 3600]
        if len(log) >= MAX_FIRES_PER_HOUR:
            _log(f"Правило {rule_id}: лимит {MAX_FIRES_PER_HOUR}/час")
            return False
        log.append(now_ts)
        return True

    def _fire_rule(self, rule: Dict[str, Any], reason: str = "") -> None:
        name = rule.get("name", rule.get("id", "?"))
        _log(f"🔥 Сработало: «{name}» (reason={reason})")

        actions = rule.get("actions", [])
        if not isinstance(actions, list):
            return

        for action in actions:
            atype = action.get("type", "")
            params = action.get("params", {}) or {}
            ok = ActionRunner.run(atype, params)
            if not ok:
                _log_err(f"Действие {atype} не выполнено для «{name}»")

        try:
            from security.audit import get_audit
            get_audit().log_command(f"[AUTO] {name} ({reason})")
        except Exception:
            pass

    def _fire_startup_or_shutdown(self, ttype: str) -> None:
        with self._lock:
            rules = [dict(r) for r in self.rules]

        for rule in rules:
            if not rule.get("enabled", True):
                continue
            if rule.get("trigger") != ttype:
                continue
            self._fire_rule(rule, reason=ttype)


# ========== СИНГЛТОН ==========

_engine: Optional[AutomationEngine] = None
_engine_lock = threading.Lock()


def get_automation() -> AutomationEngine:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = AutomationEngine()
    return _engine


# ========== РУЧНОЙ ЗАПУСК ДЛЯ ТЕСТА ==========

if __name__ == "__main__":
    eng = get_automation()
    eng.start()
    print("Движок запущен. Ctrl+C для выхода.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        eng.stop()
        print("Выход.")