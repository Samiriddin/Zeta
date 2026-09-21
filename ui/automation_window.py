# -*- coding: utf-8 -*-
"""
UI управления автоматизацией Zeta.
Создание, редактирование, удаление правил.
Frameless-окно в стиле Zeta.

Возможности:
  - Горячие клавиши: Ctrl+N (добавить), Delete (удалить),
    Enter (изменить), Escape (закрыть)
  - Контекстное меню по правому клику
  - Двойное подтверждение при удалении активного правила
  - Центрирование над родителем
"""

import logging
import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QDialog, QLineEdit, QComboBox,
    QSpinBox, QCheckBox, QMessageBox, QFormLayout, QDialogButtonBox,
    QGroupBox, QTimeEdit, QTextEdit, QFileDialog, QMenu
)
from PyQt6.QtCore import Qt, QTime, QTimer
from PyQt6.QtGui import (
    QColor, QPainter, QPen, QLinearGradient, QPainterPath,
    QAction, QShortcut, QKeySequence
)
from PyQt6.QtCore import QRectF

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.automation import get_automation


# ========== ЛОГИРОВАНИЕ ==========

logger = logging.getLogger("zeta.automation_ui")


def _log(msg: str) -> None:
    logger.info(msg)


def _log_warn(msg: str) -> None:
    logger.warning(msg)


# ========== СТИЛЬ ==========

NEON_STYLE = """
QWidget {
    background-color: #0a0a0f;
    color: #d0d0e0;
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
}
QDialog, QMainWindow { background-color: #0a0a0f; }
QLabel { background: transparent; color: #d0d0e0; }
QLabel#title { font-size: 18px; font-weight: bold; color: #00e5ff; background: transparent; }
QLabel#hint { color: #888; background: transparent; }
QGroupBox {
    background-color: #0a0a0f;
    border: 1px solid #00e5ff;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 12px;
    color: #00e5ff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #00e5ff;
    font-weight: bold;
    background: transparent;
}
QLineEdit, QComboBox, QSpinBox, QTimeEdit, QTextEdit {
    background-color: #12121a;
    border: 1px solid #2a2a3a;
    border-radius: 4px;
    padding: 5px 8px;
    color: #e0e0f0;
    selection-background-color: #00e5ff;
    selection-color: #0a0a0f;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
QTimeEdit:focus, QTextEdit:focus { border: 1px solid #00e5ff; }
QComboBox QAbstractItemView {
    background-color: #12121a;
    color: #e0e0f0;
    border: 1px solid #2a2a3a;
    selection-background-color: #1a2a3a;
    selection-color: #00e5ff;
}
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
QPushButton#windowBtn:hover { background-color: rgba(100, 120, 220, 0.18); }
QPushButton#windowBtnDanger {
    background: transparent; border: none; color: #ff6c95;
    font-size: 18px; padding: 0; border-radius: 8px;
}
QPushButton#windowBtnDanger:hover { background-color: rgba(255, 100, 150, 0.18); }
QListWidget {
    background-color: #12121a;
    border: 1px solid #2a2a3a;
    border-radius: 4px;
    padding: 4px;
    color: #d0d0e0;
}
QListWidget::item { padding: 8px; border-bottom: 1px solid #1a1a28; background: transparent; }
QListWidget::item:selected { background-color: #1a2a3a; color: #00e5ff; }
QScrollBar:vertical {
    background: #0a0a0f; width: 10px; border-radius: 5px; margin: 2px;
}
QScrollBar::handle:vertical {
    background: #2a4a6a; border-radius: 5px; min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #00e5ff; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: #0a0a0f; height: 10px; border-radius: 5px; margin: 2px;
}
QScrollBar::handle:horizontal {
    background: #2a4a6a; border-radius: 5px; min-width: 30px;
}
QScrollBar::handle:horizontal:hover { background: #00e5ff; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QCheckBox { spacing: 8px; background: transparent; color: #d0d0e0; }
QCheckBox::indicator {
    width: 16px; height: 16px;
    border: 1px solid #00e5ff;
    border-radius: 3px;
    background: #12121a;
}
QCheckBox::indicator:checked { background: #00e5ff; }
QDialogButtonBox { background: transparent; }
QDialogButtonBox QPushButton { min-width: 80px; }
QSpinBox::up-button, QSpinBox::down-button,
QTimeEdit::up-button, QTimeEdit::down-button {
    background-color: #1a1a28;
    border: 1px solid #2a2a3a;
    width: 16px;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QTimeEdit::up-button:hover, QTimeEdit::down-button:hover {
    background-color: #2a4a6a;
}
QMenu {
    background-color: #12121a;
    border: 1px solid #2a4a6a;
    border-radius: 4px;
    padding: 4px;
    color: #e0e0f0;
}
QMenu::item { padding: 6px 20px; border-radius: 3px; }
QMenu::item:selected { background-color: #1a2a3a; color: #00e5ff; }
QMenu::separator { height: 1px; background: #2a2a3a; margin: 4px 8px; }
"""


# ========== ХЕЛПЕР ==========

def _fix_background(widget: QWidget) -> None:
    widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    widget.setAutoFillBackground(True)
    pal = widget.palette()
    pal.setColor(widget.backgroundRole(), QColor("#0a0a0f"))
    widget.setPalette(pal)


# ========== СЛОВАРИ ==========

TRIGGER_TYPES = [
    ("time",      "🕐 Время"),
    ("weekday",   "📅 День недели"),
    ("cpu",       "🔥 CPU выше порога"),
    ("ram",       "💾 RAM выше порога"),
    ("startup",   "🚀 При запуске Zeta"),
    ("shutdown",  "🛑 При выключении Zeta"),
]

ACTION_TYPES = [
    ("notify",        "🔔 Уведомление"),
    ("speak",         "🔊 Сказать голосом"),
    ("open_file",     "📂 Открыть файл"),
    ("run_command",   "⚡ Выполнить команду"),
    ("backup",        "💾 Бэкап"),
    ("screenshot",    "📸 Скриншот"),
    ("system_status", "📊 Статус системы"),
]

WEEKDAYS = [
    ("Пн", 0), ("Вт", 1), ("Ср", 2), ("Чт", 3),
    ("Пт", 4), ("Сб", 5), ("Вс", 6),
]

TRIGGER_LABELS = dict(TRIGGER_TYPES)
ACTION_LABELS = dict(ACTION_TYPES)


# ========== РАМКА ==========

class AutomationFrame(QWidget):
    """Кастомный фон для frameless-окна."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(1.5, 1.5, self.width() - 3, self.height() - 3)

        bg = QLinearGradient(0, 0, self.width(), self.height())
        bg.setColorAt(0.0, QColor("#04060f"))
        bg.setColorAt(0.5, QColor("#050b19"))
        bg.setColorAt(1.0, QColor("#08051b"))

        path = QPainterPath()
        path.addRoundedRect(rect, 18, 18)
        painter.fillPath(path, bg)

        border = QLinearGradient(0, 0, self.width(), self.height())
        border.setColorAt(0.00, QColor("#7d38ff"))
        border.setColorAt(0.35, QColor("#228dff"))
        border.setColorAt(0.70, QColor("#9d42ff"))
        border.setColorAt(1.00, QColor("#b63cff"))

        painter.setPen(QPen(border, 2.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 18, 18)

        inner = rect.adjusted(3, 3, -3, -3)
        painter.setPen(QPen(QColor(50, 100, 220, 60), 1))
        painter.drawRoundedRect(inner, 15, 15)

        painter.end()


# ========== ДИАЛОГ ПРАВИЛА ==========

class RuleDialog(QDialog):
    """Диалог создания/редактирования правила."""

    def __init__(self, parent=None, rule: dict = None):
        super().__init__(parent)
        self.rule = dict(rule) if rule else None
        self.result_rule = {}
        self.setWindowTitle("Правило автоматизации")
        self.setMinimumWidth(560)
        _fix_background(self)
        self.setStyleSheet(NEON_STYLE)
        self._build_ui()
        if self.rule:
            self._load_rule(self.rule)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        top = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Например: Утренний бэкап")
        top.addRow("Название:", self.name_edit)
        root.addLayout(top)

        trig_box = QGroupBox("Триггер")
        trig_form = QFormLayout(trig_box)

        self.trigger_combo = QComboBox()
        for key, label in TRIGGER_TYPES:
            self.trigger_combo.addItem(label, key)
        self.trigger_combo.currentIndexChanged.connect(self._on_trigger_changed)
        trig_form.addRow("Тип:", self.trigger_combo)

        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setTime(QTime(7, 0))
        self.time_row_label = QLabel("Время:")
        trig_form.addRow(self.time_row_label, self.time_edit)

        self.weekdays_widget = QWidget()
        wd_layout = QHBoxLayout(self.weekdays_widget)
        wd_layout.setContentsMargins(0, 0, 0, 0)
        self.weekday_checks = []
        for name, idx in WEEKDAYS:
            cb = QCheckBox(name)
            cb.setProperty("day", idx)
            self.weekday_checks.append(cb)
            wd_layout.addWidget(cb)
        self.weekdays_row_label = QLabel("Дни:")
        trig_form.addRow(self.weekdays_row_label, self.weekdays_widget)

        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(1, 100)
        self.threshold_spin.setValue(90)
        self.threshold_spin.setSuffix(" %")
        self.threshold_row_label = QLabel("Порог:")
        trig_form.addRow(self.threshold_row_label, self.threshold_spin)

        root.addWidget(trig_box)

        act_box = QGroupBox("Действия")
        act_layout = QVBoxLayout(act_box)

        self.actions_list = QListWidget()
        self.actions_list.setMinimumHeight(140)
        act_layout.addWidget(self.actions_list)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("➕ Добавить действие")
        add_btn.clicked.connect(self._add_action)
        edit_btn = QPushButton("✏️ Изменить")
        edit_btn.clicked.connect(self._edit_action)
        del_btn = QPushButton("🗑️ Удалить")
        del_btn.setObjectName("danger")
        del_btn.clicked.connect(self._delete_action)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(edit_btn)
        btn_row.addWidget(del_btn)
        act_layout.addLayout(btn_row)

        root.addWidget(act_box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._on_trigger_changed()

    def _on_trigger_changed(self) -> None:
        ttype = self.trigger_combo.currentData()
        show_time = ttype in ("time", "weekday")
        show_days = (ttype == "weekday")
        show_threshold = ttype in ("cpu", "ram")

        self.time_row_label.setVisible(show_time)
        self.time_edit.setVisible(show_time)
        self.weekdays_row_label.setVisible(show_days)
        self.weekdays_widget.setVisible(show_days)
        self.threshold_row_label.setVisible(show_threshold)
        self.threshold_spin.setVisible(show_threshold)

    def _load_rule(self, rule: dict) -> None:
        self.name_edit.setText(rule.get("name", ""))

        ttype = rule.get("trigger", "time")
        for i in range(self.trigger_combo.count()):
            if self.trigger_combo.itemData(i) == ttype:
                self.trigger_combo.setCurrentIndex(i)
                break

        if rule.get("time"):
            try:
                h, m = rule["time"].split(":")
                self.time_edit.setTime(QTime(int(h), int(m)))
            except Exception:
                pass

        days = set(rule.get("weekdays", []) or [])
        for cb in self.weekday_checks:
            cb.setChecked(cb.property("day") in days)

        if rule.get("threshold") is not None:
            try:
                self.threshold_spin.setValue(int(rule["threshold"]))
            except Exception:
                pass

        self.actions_list.clear()
        for a in rule.get("actions", []):
            self._append_action_item(a)

    def _append_action_item(self, action: dict) -> None:
        atype = action.get("type", "")
        label = ACTION_LABELS.get(atype, atype)
        params = action.get("params", {}) or {}
        preview = self._preview_params(atype, params)
        item = QListWidgetItem(f"{label}  —  {preview}")
        item.setData(Qt.ItemDataRole.UserRole, dict(action))
        self.actions_list.addItem(item)

    @staticmethod
    def _preview_params(atype: str, params: dict) -> str:
        if atype == "notify":
            return params.get("message", "")[:60]
        if atype == "speak":
            return params.get("text", "")[:60]
        if atype == "open_file":
            return params.get("path", "")[:60]
        if atype == "run_command":
            return params.get("command", "")[:60]
        if atype == "screenshot":
            return params.get("path", "по умолчанию")[:60]
        if atype == "system_status":
            return "notify" if params.get("notify") else ""
        return ""

    def _add_action(self) -> None:
        dlg = ActionDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._append_action_item(dlg.get_action())

    def _edit_action(self) -> None:
        item = self.actions_list.currentItem()
        if not item:
            return
        action = item.data(Qt.ItemDataRole.UserRole)
        dlg = ActionDialog(self, action)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_action = dlg.get_action()
            item.setData(Qt.ItemDataRole.UserRole, new_action)
            atype = new_action.get("type", "")
            label = ACTION_LABELS.get(atype, atype)
            preview = self._preview_params(atype, new_action.get("params", {}))
            item.setText(f"{label}  —  {preview}")

    def _delete_action(self) -> None:
        item = self.actions_list.currentItem()
        if not item:
            return
        row = self.actions_list.row(item)
        self.actions_list.takeItem(row)

    def _on_ok(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Ошибка", "Введите название правила.")
            return

        ttype = self.trigger_combo.currentData()

        if self.actions_list.count() == 0:
            QMessageBox.warning(self, "Ошибка", "Добавьте хотя бы одно действие.")
            return

        if ttype in ("time", "weekday"):
            t = self.time_edit.time()
            time_str = f"{t.hour():02d}:{t.minute():02d}"
        else:
            time_str = ""

        days = []
        if ttype == "weekday":
            for cb in self.weekday_checks:
                if cb.isChecked():
                    days.append(cb.property("day"))
            if not days:
                QMessageBox.warning(self, "Ошибка", "Выберите хотя бы один день.")
                return

        threshold = None
        if ttype in ("cpu", "ram"):
            threshold = self.threshold_spin.value()

        actions = []
        for i in range(self.actions_list.count()):
            item = self.actions_list.item(i)
            actions.append(item.data(Qt.ItemDataRole.UserRole))

        self.result_rule = {
            "name": name,
            "trigger": ttype,
            "time": time_str,
            "weekdays": days,
            "threshold": threshold,
            "actions": actions,
            "enabled": True,
        }
        if self.rule and "id" in self.rule:
            self.result_rule["id"] = self.rule["id"]

        self.accept()

    def get_rule(self) -> dict:
        return self.result_rule


# ========== ДИАЛОГ ДЕЙСТВИЯ ==========

class ActionDialog(QDialog):
    """Диалог настройки одного действия."""

    def __init__(self, parent=None, action: dict = None):
        super().__init__(parent)
        self.action = dict(action) if action else None
        self.result_action = {}
        self.setWindowTitle("Действие")
        self.setMinimumWidth(480)
        _fix_background(self)
        self.setStyleSheet(NEON_STYLE)
        self._build_ui()
        if self.action:
            self._load_action(self.action)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        form = QFormLayout()

        self.type_combo = QComboBox()
        for key, label in ACTION_TYPES:
            self.type_combo.addItem(label, key)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("Тип:", self.type_combo)

        self.title_edit = QLineEdit("Zeta")
        self.title_label = QLabel("Заголовок:")
        form.addRow(self.title_label, self.title_edit)

        self.message_edit = QTextEdit()
        self.message_edit.setMaximumHeight(70)
        self.message_label = QLabel("Сообщение:")
        form.addRow(self.message_label, self.message_edit)

        self.text_edit = QTextEdit()
        self.text_edit.setMaximumHeight(70)
        self.text_label = QLabel("Текст:")
        form.addRow(self.text_label, self.text_edit)

        self.path_edit = QLineEdit()
        self.path_btn = QPushButton("📂 Обзор")
        self.path_btn.clicked.connect(self._pick_path)
        path_row = QHBoxLayout()
        path_row.addWidget(self.path_edit)
        path_row.addWidget(self.path_btn)
        self.path_container = QWidget()
        self.path_container.setLayout(path_row)
        self.path_label = QLabel("Путь:")
        form.addRow(self.path_label, self.path_container)

        self.command_edit = QLineEdit()
        self.command_label = QLabel("Команда:")
        form.addRow(self.command_label, self.command_edit)

        self.notify_check = QCheckBox("Показать уведомление")
        form.addRow("", self.notify_check)

        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._on_type_changed()

    def _on_type_changed(self) -> None:
        t = self.type_combo.currentData()

        for w in (
            self.title_label, self.title_edit,
            self.message_label, self.message_edit,
            self.text_label, self.text_edit,
            self.path_label, self.path_container,
            self.command_label, self.command_edit,
            self.notify_check,
        ):
            w.setVisible(False)

        self.path_label.setText("Путь:")

        if t == "notify":
            self.title_label.setVisible(True); self.title_edit.setVisible(True)
            self.message_label.setVisible(True); self.message_edit.setVisible(True)
        elif t == "speak":
            self.text_label.setVisible(True); self.text_edit.setVisible(True)
        elif t == "open_file":
            self.path_label.setVisible(True); self.path_container.setVisible(True)
        elif t == "run_command":
            self.command_label.setVisible(True); self.command_edit.setVisible(True)
        elif t == "screenshot":
            self.path_label.setText("Папка (необязательно):")
            self.path_label.setVisible(True); self.path_container.setVisible(True)
        elif t == "system_status":
            self.notify_check.setVisible(True)

    def _pick_path(self) -> None:
        t = self.type_combo.currentData()
        if t == "open_file":
            p, _ = QFileDialog.getOpenFileName(self, "Выберите файл")
        elif t == "screenshot":
            p = QFileDialog.getExistingDirectory(self, "Выберите папку")
        else:
            p = ""
        if p:
            self.path_edit.setText(p)

    def _load_action(self, action: dict) -> None:
        atype = action.get("type", "")
        for i in range(self.type_combo.count()):
            if self.type_combo.itemData(i) == atype:
                self.type_combo.setCurrentIndex(i)
                break
        p = action.get("params", {}) or {}
        self.title_edit.setText(p.get("title", "Zeta"))
        self.message_edit.setPlainText(p.get("message", ""))
        self.text_edit.setPlainText(p.get("text", ""))
        self.path_edit.setText(p.get("path", ""))
        self.command_edit.setText(p.get("command", ""))
        self.notify_check.setChecked(bool(p.get("notify", False)))
        self._on_type_changed()

    def _on_ok(self) -> None:
        atype = self.type_combo.currentData()
        params = {}
        if atype == "notify":
            params["title"] = self.title_edit.text() or "Zeta"
            params["message"] = self.message_edit.toPlainText()
            if not params["message"]:
                QMessageBox.warning(self, "Ошибка", "Введите сообщение.")
                return
        elif atype == "speak":
            params["text"] = self.text_edit.toPlainText()
            if not params["text"]:
                QMessageBox.warning(self, "Ошибка", "Введите текст.")
                return
        elif atype == "open_file":
            params["path"] = self.path_edit.text()
            if not params["path"]:
                QMessageBox.warning(self, "Ошибка", "Выберите файл.")
                return
        elif atype == "run_command":
            params["command"] = self.command_edit.text()
            if not params["command"]:
                QMessageBox.warning(self, "Ошибка", "Введите команду.")
                return
        elif atype == "screenshot":
            params["path"] = self.path_edit.text()
        elif atype == "system_status":
            params["notify"] = self.notify_check.isChecked()

        self.result_action = {"type": atype, "params": params}
        self.accept()

    def get_action(self) -> dict:
        return self.result_action


# ========== ГЛАВНОЕ ОКНО ==========

class AutomationWindow(QWidget):
    """Главное окно автоматизации (frameless)."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("🤖 Zeta — Автоматизация")
        self.setMinimumSize(720, 520)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(NEON_STYLE)

        self._drag_pos = None
        self._centered = False

        self.engine = get_automation()
        self._build_ui()
        self._setup_shortcuts()
        self._setup_context_menu()

        _log("AutomationWindow инициализировано")

    # ----- UI -----

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.frame = AutomationFrame(self)
        outer.addWidget(self.frame)

        root = QVBoxLayout(self.frame)
        root.setContentsMargins(18, 14, 18, 18)
        root.setSpacing(10)

        # Шапка
        header = QHBoxLayout()
        header.setSpacing(8)

        title = QLabel("🤖 Автоматизация")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch()

        self.min_btn = QPushButton("−")
        self.min_btn.setObjectName("windowBtn")
        self.min_btn.setFixedSize(32, 32)
        self.min_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.min_btn.setToolTip("Свернуть")
        self.min_btn.clicked.connect(self.showMinimized)
        header.addWidget(self.min_btn)

        self.close_btn = QPushButton("×")
        self.close_btn.setObjectName("windowBtnDanger")
        self.close_btn.setFixedSize(32, 32)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setToolTip("Закрыть (Esc)")
        self.close_btn.clicked.connect(self.close)
        header.addWidget(self.close_btn)

        root.addLayout(header)

        hint = QLabel(
            "Правила: триггер + действия. "
            "Например: «в 07:00 сказать 'Доброе утро' и открыть музыку».\n"
            "💡 Ctrl+N — добавить, Delete — удалить, Enter — изменить, Esc — закрыть"
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        # Список
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._edit_selected)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._show_context_menu)
        root.addWidget(self.list, 1)

        # Кнопки
        btns = QHBoxLayout()
        btns.setSpacing(8)

        add_btn = QPushButton("➕ Добавить")
        add_btn.setToolTip("Ctrl+N")
        add_btn.clicked.connect(self._add_rule)
        btns.addWidget(add_btn)

        edit_btn = QPushButton("✏️ Изменить")
        edit_btn.setToolTip("Enter")
        edit_btn.clicked.connect(self._edit_selected)
        btns.addWidget(edit_btn)

        toggle_btn = QPushButton("⏯️ Вкл/Выкл")
        toggle_btn.setToolTip("Пробел")
        toggle_btn.clicked.connect(self._toggle_selected)
        btns.addWidget(toggle_btn)

        del_btn = QPushButton("🗑️ Удалить")
        del_btn.setObjectName("danger")
        del_btn.setToolTip("Delete")
        del_btn.clicked.connect(self._delete_selected)
        btns.addWidget(del_btn)

        btns.addStretch()

        refresh_btn = QPushButton("🔄 Обновить")
        refresh_btn.setToolTip("F5")
        refresh_btn.clicked.connect(self.refresh)
        btns.addWidget(refresh_btn)

        root.addLayout(btns)

        self.refresh()

    # ----- Горячие клавиши -----

    def _setup_shortcuts(self) -> None:
        """Ctrl+N / Delete / Enter / Esc / F5 / Space."""
        shortcuts = [
            ("Ctrl+N", self._add_rule),
            ("Delete", self._delete_selected),
            ("Return", self._edit_selected),
            ("Enter", self._edit_selected),
            ("Escape", self.close),
            ("F5", self.refresh),
            ("Space", self._toggle_selected),
        ]
        for key, cb in shortcuts:
            try:
                sc = QShortcut(QKeySequence(key), self)
                sc.activated.connect(cb)
            except Exception as e:
                _log_warn(f"Shortcut {key}: {e}")

    # ----- Контекстное меню -----

    def _setup_context_menu(self) -> None:
        """Настраивается в _build_ui через setContextMenuPolicy."""
        pass

    def _show_context_menu(self, pos) -> None:
        """Показать контекстное меню по правому клику."""
        item = self.list.itemAt(pos)
        if not item:
            return

        rid = item.data(Qt.ItemDataRole.UserRole)
        if not rid:
            return

        rule = self.engine.get_rule(rid)
        if not rule:
            return

        menu = QMenu(self)

        edit_action = QAction("✏️ Изменить", self)
        edit_action.triggered.connect(self._edit_selected)
        menu.addAction(edit_action)

        toggle_action = QAction(
            "⏸️ Выключить" if rule.get("enabled", True) else "▶️ Включить",
            self
        )
        toggle_action.triggered.connect(self._toggle_selected)
        menu.addAction(toggle_action)

        menu.addSeparator()

        del_action = QAction("🗑️ Удалить", self)
        del_action.triggered.connect(self._delete_selected)
        menu.addAction(del_action)

        menu.exec(self.list.mapToGlobal(pos))

    # ----- Показ -----

    def showEvent(self, event):
        super().showEvent(event)
        if not self._centered:
            QTimer.singleShot(0, self._do_center)

    def _do_center(self):
        if self._centered:
            return
        self._center_on_parent()
        self._centered = True

    def _center_on_parent(self):
        parent = self.parent()
        if parent is None:
            return
        try:
            pg = parent.frameGeometry()
            x = pg.center().x() - self.width() // 2
            y = pg.center().y() - self.height() // 2
            self.move(max(0, x), max(0, y))
        except Exception as e:
            _log_warn(f"center: {e}")

    # ----- Drag -----

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        event.accept()

    # ----- Список -----

    def refresh(self) -> None:
        self.list.clear()
        rules = self.engine.get_all()
        if not rules:
            item = QListWidgetItem("— Правил пока нет. Добавь первое! (Ctrl+N) —")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(item)
            return
        for r in rules:
            self.list.addItem(self._make_item(r))

    def _make_item(self, rule: dict) -> QListWidgetItem:
        enabled = rule.get("enabled", True)
        status = "🟢" if enabled else "⚪"
        ttype = rule.get("trigger", "?")
        tlabel = TRIGGER_LABELS.get(ttype, ttype)

        detail = ""
        if ttype in ("time", "weekday"):
            detail = f" {rule.get('time', '')}"
            if ttype == "weekday":
                days = rule.get("weekdays", []) or []
                names = [n for n, i in WEEKDAYS if i in days]
                if names:
                    detail += f" [{','.join(names)}]"
        elif ttype in ("cpu", "ram"):
            detail = f" порог {rule.get('threshold', '?')}%"

        actions_count = len(rule.get("actions", []))
        text = (
            f"{status}  {rule.get('name', '?')}  "
            f"({tlabel}{detail})  —  действий: {actions_count}"
        )
        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, rule.get("id"))
        if not enabled:
            item.setForeground(Qt.GlobalColor.gray)
        return item

    def _selected_id(self) -> str:
        item = self.list.currentItem()
        if not item:
            return ""
        rid = item.data(Qt.ItemDataRole.UserRole)
        return rid or ""

    # ----- Действия -----

    def _add_rule(self) -> None:
        dlg = RuleDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.engine.add_rule(dlg.get_rule())
            self.refresh()
            _log("Правило добавлено")

    def _edit_selected(self) -> None:
        rid = self._selected_id()
        if not rid:
            return
        rule = self.engine.get_rule(rid)
        if not rule:
            return
        dlg = RuleDialog(self, rule)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.engine.update_rule(rid, dlg.get_rule())
            self.refresh()
            _log(f"Правило изменено: {rid}")

    def _toggle_selected(self) -> None:
        rid = self._selected_id()
        if not rid:
            return
        rule = self.engine.get_rule(rid)
        if not rule:
            return
        rule["enabled"] = not rule.get("enabled", True)
        self.engine.update_rule(rid, {"enabled": rule["enabled"]})
        self.refresh()
        _log(f"Правило {'включено' if rule['enabled'] else 'выключено'}: {rid}")

    def _delete_selected(self) -> None:
        rid = self._selected_id()
        if not rid:
            return
        rule = self.engine.get_rule(rid)
        name = rule.get("name", rid) if rule else rid

        # Двойное подтверждение для активных правил
        enabled = rule.get("enabled", True) if rule else False

        if enabled:
            ans = QMessageBox.question(
                self,
                "Удалить активное правило?",
                f"Правило «{name}» активно!\n\nУдалить его?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
        else:
            ans = QMessageBox.question(
                self,
                "Удалить правило?",
                f"Удалить «{name}»?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )

        if ans == QMessageBox.StandardButton.Yes:
            self.engine.delete_rule(rid)
            self.refresh()
            _log(f"Правило удалено: {rid}")


# ========== ЭКСПОРТ ==========

__all__ = ["AutomationWindow", "RuleDialog", "ActionDialog"]