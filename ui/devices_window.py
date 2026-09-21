# -*- coding: utf-8 -*-
"""UI управления устройствами — frameless в стиле Zeta."""

import os
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QDialog, QLineEdit, QMessageBox,
    QFormLayout, QDialogButtonBox, QFileDialog, QInputDialog
)
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QColor, QPainter, QPen, QLinearGradient, QPainterPath

from modules.device_manager import get_device_manager

NEON_STYLE = """
QWidget {
    background-color: #0a0a0f;
    color: #d0d0e0;
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
}
QLabel { background: transparent; color: #d0d0e0; }
QLabel#title { font-size: 18px; font-weight: bold; color: #00e5ff; background: transparent; }
QLabel#hint { color: #888; background: transparent; }
QLineEdit {
    background-color: #12121a;
    border: 1px solid #2a2a3a;
    border-radius: 4px;
    padding: 6px 10px;
    color: #e0e0f0;
}
QLineEdit:focus { border: 1px solid #00e5ff; }
QPushButton {
    background-color: #12121a;
    border: 1px solid #00e5ff;
    border-radius: 4px;
    padding: 6px 14px;
    color: #00e5ff;
}
QPushButton:hover { background-color: #1a1a28; }
QPushButton:pressed { background-color: #00e5ff; color: #0a0a0f; }
QPushButton#danger { border-color: #ff3860; color: #ff3860; }
QPushButton#danger:hover { background-color: #2a0a12; }
QPushButton#windowBtn {
    background: transparent; border: none; color: #c5cee9;
    font-size: 18px; padding: 0; border-radius: 8px;
}
QPushButton#windowBtn:hover { background-color: rgba(100,120,220,0.18); }
QPushButton#windowBtnDanger {
    background: transparent; border: none; color: #ff6c95;
    font-size: 18px; padding: 0; border-radius: 8px;
}
QPushButton#windowBtnDanger:hover { background-color: rgba(255,100,150,0.18); }
QListWidget {
    background-color: #12121a;
    border: 1px solid #2a2a3a;
    border-radius: 4px;
    padding: 4px;
}
QListWidget::item {
    padding: 10px;
    border-bottom: 1px solid #1a1a28;
    background: transparent;
}
QListWidget::item:selected {
    background-color: #1a2a3a;
    color: #00e5ff;
}
QScrollBar:vertical {
    background: #0a0a0f; width: 10px;
    border-radius: 5px; margin: 2px;
}
QScrollBar::handle:vertical {
    background: #2a4a6a; border-radius: 5px; min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #00e5ff; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


def _fix_bg(w: QWidget) -> None:
    w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    w.setAutoFillBackground(True)
    p = w.palette()
    p.setColor(w.backgroundRole(), QColor("#0a0a0f"))
    w.setPalette(p)


class DevicesFrame(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(1.5, 1.5, self.width() - 3, self.height() - 3)
        bg = QLinearGradient(0, 0, self.width(), self.height())
        bg.setColorAt(0.0, QColor("#04060f"))
        bg.setColorAt(0.5, QColor("#050b19"))
        bg.setColorAt(1.0, QColor("#08051b"))
        path = QPainterPath()
        path.addRoundedRect(rect, 18, 18)
        p.fillPath(path, bg)
        border = QLinearGradient(0, 0, self.width(), self.height())
        border.setColorAt(0.00, QColor("#7d38ff"))
        border.setColorAt(0.35, QColor("#228dff"))
        border.setColorAt(0.70, QColor("#9d42ff"))
        border.setColorAt(1.00, QColor("#b63cff"))
        p.setPen(QPen(border, 2.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 18, 18)
        inner = rect.adjusted(3, 3, -3, -3)
        p.setPen(QPen(QColor(50, 100, 220, 60), 1))
        p.drawRoundedRect(inner, 15, 15)
        p.end()


class AddDeviceDialog(QDialog):
    def __init__(self, parent=None, ip="", name="", port=5670):
        super().__init__(parent)
        self.setWindowTitle("Добавить устройство")
        self.setMinimumWidth(420)
        _fix_bg(self)
        self.setStyleSheet(NEON_STYLE)
        form = QFormLayout(self)
        self.name_edit = QLineEdit(name)
        self.name_edit.setPlaceholderText("Например: Домашний-ПК")
        form.addRow("Имя:", self.name_edit)
        self.ip_edit = QLineEdit(ip)
        self.ip_edit.setPlaceholderText("192.168.1.5")
        form.addRow("IP:", self.ip_edit)
        self.port_edit = QLineEdit(str(port))
        form.addRow("Порт:", self.port_edit)
        self.token_edit = QLineEdit()
        self.token_edit.setPlaceholderText("Из agent_token.txt")
        form.addRow("Токен:", self.token_edit)
        self.mac_edit = QLineEdit()
        self.mac_edit.setPlaceholderText("AA:BB:CC:DD:EE:FF (для WOL)")
        form.addRow("MAC:", self.mac_edit)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._ok)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def _ok(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Ошибка", "Введите имя")
            return
        if not self.ip_edit.text().strip():
            QMessageBox.warning(self, "Ошибка", "Введите IP")
            return
        if not self.token_edit.text().strip():
            QMessageBox.warning(self, "Ошибка", "Введите токен агента")
            return
        self.accept()

    def get_data(self):
        try:
            port = int(self.port_edit.text())
        except Exception:
            port = 5670
        return {
            "name": self.name_edit.text().strip(),
            "ip": self.ip_edit.text().strip(),
            "port": port,
            "token": self.token_edit.text().strip(),
            "mac": self.mac_edit.text().strip(),
        }


class DevicesWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🌐 Zeta — Устройства")
        self.setMinimumSize(680, 500)
        self.setWindowFlags(Qt.WindowType.Window |
                            Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(NEON_STYLE)
        self._drag_pos = None
        self._centered = False
        self.manager = get_device_manager()
        self.manager.load()
        self._build_ui()
        self.refresh()
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._auto_ping)
        self._status_timer.start(15000)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.frame = DevicesFrame(self)
        outer.addWidget(self.frame)

        root = QVBoxLayout(self.frame)
        root.setContentsMargins(18, 14, 18, 18)
        root.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("🌐 Устройства")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch()
        min_btn = QPushButton("−")
        min_btn.setObjectName("windowBtn")
        min_btn.setFixedSize(32, 32)
        min_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        min_btn.clicked.connect(self.showMinimized)
        header.addWidget(min_btn)
        close_btn = QPushButton("×")
        close_btn.setObjectName("windowBtnDanger")
        close_btn.setFixedSize(32, 32)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.close)
        header.addWidget(close_btn)
        root.addLayout(header)

        hint = QLabel(
            "Сканируй LAN, добавляй ПК по IP. "
            "Управляй скриншотами, файлами, выключением и буфером обмена."
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._on_double)
        root.addWidget(self.list, 1)

        btns = QHBoxLayout()
        btns.setSpacing(6)
        scan_btn = QPushButton("🔍 Сканировать")
        scan_btn.clicked.connect(self._scan)
        btns.addWidget(scan_btn)
        add_btn = QPushButton("➕ По IP")
        add_btn.clicked.connect(self._add_by_ip)
        btns.addWidget(add_btn)
        shot_btn = QPushButton("📸 Скриншот")
        shot_btn.clicked.connect(self._screenshot)
        btns.addWidget(shot_btn)
        file_btn = QPushButton("📤 Файл")
        file_btn.clicked.connect(self._send_file)
        btns.addWidget(file_btn)
        wake_btn = QPushButton("🔌 WOL")
        wake_btn.clicked.connect(self._wol)
        btns.addWidget(wake_btn)
        off_btn = QPushButton("⚡ Выкл")
        off_btn.setObjectName("danger")
        off_btn.clicked.connect(self._shutdown)
        btns.addWidget(off_btn)
        del_btn = QPushButton("🗑️")
        del_btn.setObjectName("danger")
        del_btn.clicked.connect(self._delete)
        btns.addWidget(del_btn)
        btns.addStretch()
        ref_btn = QPushButton("🔄")
        ref_btn.clicked.connect(self.refresh)
        btns.addWidget(ref_btn)
        root.addLayout(btns)

        self.status = QLabel("Готов")
        self.status.setStyleSheet("color: #45eeb0; background: transparent;")
        root.addWidget(self.status)

    def _set_status(self, txt, level="info"):
        colors = {"success": "#45eeb0", "warning": "#ffc766",
                  "danger": "#ff668b", "info": "#55aaff"}
        c = colors.get(level, "#8d98b8")
        self.status.setText(txt)
        self.status.setStyleSheet(f"color: {c}; background: transparent;")

    def showEvent(self, event):
        super().showEvent(event)
        if not self._centered:
            p = self.parent()
            if p is not None:
                pg = p.frameGeometry()
                x = pg.center().x() - self.width() // 2
                y = pg.center().y() - self.height() // 2
                self.move(max(0, x), max(0, y))
            self._centered = True

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag_pos is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)
            e.accept()

    def mouseReleaseEvent(self, e):
        self._drag_pos = None
        e.accept()

    def refresh(self):
        self.list.clear()
        devs = self.manager.get_all()
        if not devs:
            it = QListWidgetItem("— Устройств нет. Нажми 🔍 Сканировать или ➕ По IP —")
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(it)
            return
        for d in devs:
            status = "🟢" if d.get("online") else "⚪"
            mac = d.get("mac", "") or "—"
            txt = (f"{status}  {d.get('name','?')}  |  "
                   f"{d.get('ip','?')}:{d.get('port',5670)}  |  MAC: {mac}")
            it = QListWidgetItem(txt)
            it.setData(Qt.ItemDataRole.UserRole, d.get("id"))
            if not d.get("online"):
                it.setForeground(Qt.GlobalColor.gray)
            self.list.addItem(it)

    def _selected(self):
        it = self.list.currentItem()
        if not it:
            return None
        rid = it.data(Qt.ItemDataRole.UserRole)
        if not rid:
            return None
        return self.manager.get(rid)

    def _on_double(self):
        self._screenshot()

    def _scan(self):
        self._set_status("🔍 Сканирую сеть...", "info")
        try:
            found = self.manager.discover()
        except Exception as e:
            self._set_status(f"Ошибка скана: {e}", "danger")
            return
        existing = {d.get("ip") for d in self.manager.get_all()}
        new_count = 0
        for f in found:
            if f["ip"] in existing:
                continue
            dlg = AddDeviceDialog(self, ip=f["ip"],
                                  name=f.get("name", "Без имени"),
                                  port=f.get("port", 5670))
            if dlg.exec() == QDialog.DialogCode.Accepted:
                data = dlg.get_data()
                self.manager.add(data["name"], data["ip"], data["token"],
                                 mac=data["mac"], port=data["port"])
                new_count += 1
        self.refresh()
        self._set_status(
            f"✅ Найдено {len(found)}, добавлено {new_count}",
            "success" if found else "warning")

    def _add_by_ip(self):
        dlg = AddDeviceDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            self.manager.add(data["name"], data["ip"], data["token"],
                             mac=data["mac"], port=data["port"])
            self.refresh()
            self._set_status(f"✅ Добавлено: {data['name']}", "success")

    def _screenshot(self):
        d = self._selected()
        if not d:
            self._set_status("Выбери устройство", "warning")
            return
        self._set_status(f"📸 Скриншот с {d['name']}...", "info")
        path = self.manager.screenshot(d)
        if path:
            self._set_status(f"✅ Сохранён: {path}", "success")
            try:
                os.startfile(path)
            except Exception:
                pass
        else:
            self._set_status("❌ Не удалось получить скриншот", "danger")

    def _send_file(self):
        d = self._selected()
        if not d:
            self._set_status("Выбери устройство", "warning")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Файл для отправки")
        if not path:
            return
        self._set_status(f"📤 Отправляю {os.path.basename(path)}...", "info")
        ok = self.manager.send_file(d, path)
        self._set_status("✅ Отправлено" if ok else "❌ Ошибка отправки",
                         "success" if ok else "danger")

    def _wol(self):
        d = self._selected()
        if not d:
            self._set_status("Выбери устройство", "warning")
            return
        if not d.get("mac"):
            QMessageBox.warning(self, "Нет MAC",
                                "Для WOL нужен MAC-адрес. "
                                "Отредактируй устройство (двойной клик → MAC).")
            return
        ok = self.manager.wake_on_lan(d)
        self._set_status("🔌 Пакет WOL отправлен" if ok else "❌ Ошибка WOL",
                         "success" if ok else "danger")

    def _shutdown(self):
        d = self._selected()
        if not d:
            self._set_status("Выбери устройство", "warning")
            return
        ans = QMessageBox.question(
            self, "Выключить?",
            f"Выключить «{d['name']}» через 30 секунд?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ans != QMessageBox.StandardButton.Yes:
            return
        ok = self.manager.shutdown(d, delay=30)
        self._set_status("⚡ Команда отправлена" if ok else "❌ Ошибка",
                         "success" if ok else "danger")

    def _delete(self):
        d = self._selected()
        if not d:
            return
        ans = QMessageBox.question(
            self, "Удалить?",
            f"Удалить «{d['name']}» из списка?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ans == QMessageBox.StandardButton.Yes:
            self.manager.delete(d["id"])
            self.refresh()

    def _auto_ping(self):
        devs = self.manager.get_all()
        for d in devs:
            try:
                self.manager.ping(d)
            except Exception:
                pass
        self.refresh()