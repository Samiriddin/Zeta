# -*- coding: utf-8 -*-
"""
Zeta UI — Окно планировщика.
Задачи, встречи, рутины.

Особенности:
    - Неоновый стиль Zeta
    - Горячие клавиши: Esc, Ctrl+N, Delete, Enter
    - Валидация времени рутины
    - Пустые состояния
    - Логирование
"""

import os
import re
import sys
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QTabWidget, QWidget,
    QListWidget, QListWidgetItem, QMessageBox,
    QInputDialog, QComboBox, QSpinBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QShortcut, QKeySequence, QIcon

from modules.scheduler import get_scheduler, DateParser


# ========== ЛОГИРОВАНИЕ ==========

logger = logging.getLogger("zeta.scheduler_ui")


def _log(msg: str) -> None:
    logger.info(msg)


def _log_warn(msg: str) -> None:
    logger.warning(msg)


# ========== СТИЛЬ ==========

STYLE = """
QDialog {
    background-color: #0a0a0f;
    color: #d0d0e0;
    font-family: 'Segoe UI', sans-serif;
}
QLabel {
    color: #d0d0e0;
    background: transparent;
}
QLabel#title {
    font-size: 18px;
    font-weight: bold;
    color: #00e5ff;
    background: transparent;
}
QLineEdit, QListWidget, QComboBox, QSpinBox {
    background-color: #12121a;
    color: #e0e0f0;
    border: 1px solid #2a2a3a;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 1px solid #00e5ff;
}
QPushButton {
    background-color: #12121a;
    color: #00e5ff;
    border: 1px solid #00e5ff;
    border-radius: 6px;
    padding: 8px 14px;
    font-size: 13px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #1a1a28;
}
QPushButton:pressed {
    background-color: #00e5ff;
    color: #0a0a0f;
}
QPushButton#danger {
    border-color: #ff3860;
    color: #ff3860;
}
QPushButton#danger:hover {
    background-color: #2a0a12;
}
QTabWidget::pane {
    background: #0a0a0f;
    border: 1px solid #00e5ff;
    border-radius: 8px;
    padding: 10px;
}
QTabBar::tab {
    background: #12121a;
    color: #d0d0e0;
    padding: 8px 16px;
    border: 1px solid #2a2a3a;
    border-bottom: none;
    border-radius: 8px 8px 0 0;
    margin-right: 4px;
    font-weight: 600;
}
QTabBar::tab:selected {
    background: #00e5ff;
    color: #0a0a0f;
    border-color: #00e5ff;
}
QTabBar::tab:hover:!selected {
    background: #1a1a28;
    color: #00e5ff;
}
QListWidget {
    background-color: #12121a;
    border: 1px solid #2a2a3a;
    border-radius: 6px;
    padding: 4px;
    color: #e0e0f0;
}
QListWidget::item {
    padding: 8px;
    border-bottom: 1px solid #1a1a28;
    background: transparent;
}
QListWidget::item:selected {
    background-color: #1a2a3a;
    color: #00e5ff;
}
QScrollBar:vertical {
    background: #0a0a0f;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #2a4a6a;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #00e5ff;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
"""


# ========== ОКНО ПЛАНИРОВЩИКА ==========

class SchedulerWindow(QDialog):
    """Окно планировщика."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📅 Планировщик Zeta")
        self.setFixedSize(640, 640)
        self.setStyleSheet(STYLE)

        # Флаги окна — как у Zeta, не мешает панели задач
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowMinimizeButtonHint
        )

        # Иконка как у Zeta
        try:
            from ui.widget import create_app_icon
            self.setWindowIcon(create_app_icon())
        except Exception:
            pass

        self.scheduler = get_scheduler()

        self._build_ui()
        self._setup_hotkeys()
        self.refresh_all()

        _log("SchedulerWindow открыто")

    # ============================================================
    #  UI
    # ============================================================

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("📅 Планировщик")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._tab_tasks(), "✅ Задачи")
        self.tabs.addTab(self._tab_events(), "📅 Встречи")
        self.tabs.addTab(self._tab_routines(), "🔁 Рутины")
        self.tabs.addTab(self._tab_today(), "🕐 Сегодня")

        layout.addWidget(self.tabs)

        # Кнопка закрытия
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("✕ Закрыть")
        close_btn.clicked.connect(self.close)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

    # ========== ВКЛАДКА: ЗАДАЧИ ==========

    def _tab_tasks(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(8)

        input_layout = QHBoxLayout()
        self.task_input = QLineEdit()
        self.task_input.setPlaceholderText("Например: отчёт до пятницы")
        self.task_input.returnPressed.connect(self.add_task)
        input_layout.addWidget(self.task_input)

        add_btn = QPushButton("➕ Добавить")
        add_btn.setToolTip("Ctrl+N")
        add_btn.clicked.connect(self.add_task)
        input_layout.addWidget(add_btn)

        layout.addLayout(input_layout)

        self.tasks_list = QListWidget()
        layout.addWidget(self.tasks_list, 1)

        btn_layout = QHBoxLayout()

        complete_btn = QPushButton("✅ Выполнить")
        complete_btn.setToolTip("Enter")
        complete_btn.clicked.connect(self.complete_task)
        btn_layout.addWidget(complete_btn)

        delete_btn = QPushButton("🗑️ Удалить")
        delete_btn.setObjectName("danger")
        delete_btn.setToolTip("Delete")
        delete_btn.clicked.connect(self.delete_task)
        btn_layout.addWidget(delete_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        return widget

    # ========== ВКЛАДКА: ВСТРЕЧИ ==========

    def _tab_events(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(8)

        input_layout = QHBoxLayout()
        self.event_input = QLineEdit()
        self.event_input.setPlaceholderText("Например: встреча завтра в 15:00")
        self.event_input.returnPressed.connect(self.add_event)
        input_layout.addWidget(self.event_input)

        add_btn = QPushButton("➕ Добавить")
        add_btn.clicked.connect(self.add_event)
        input_layout.addWidget(add_btn)

        layout.addLayout(input_layout)

        self.events_list = QListWidget()
        layout.addWidget(self.events_list, 1)

        btn_layout = QHBoxLayout()
        delete_btn = QPushButton("🗑️ Удалить выбранное")
        delete_btn.setObjectName("danger")
        delete_btn.setToolTip("Delete")
        delete_btn.clicked.connect(self.delete_event)
        btn_layout.addWidget(delete_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        return widget

    # ========== ВКЛАДКА: РУТИНЫ ==========

    def _tab_routines(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(8)

        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Название:"))
        self.routine_name = QLineEdit()
        self.routine_name.setPlaceholderText("Утренняя")
        name_layout.addWidget(self.routine_name)
        layout.addLayout(name_layout)

        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("Время:"))
        self.routine_time = QLineEdit()
        self.routine_time.setPlaceholderText("07:00")
        time_layout.addWidget(self.routine_time)
        layout.addLayout(time_layout)

        layout.addWidget(QLabel("Действия (через запятую):"))
        self.routine_actions = QLineEdit()
        self.routine_actions.setPlaceholderText("зарядка, душ, завтрак")
        layout.addWidget(self.routine_actions)

        add_btn = QPushButton("➕ Создать рутину")
        add_btn.clicked.connect(self.add_routine)
        layout.addWidget(add_btn)

        self.routines_list = QListWidget()
        layout.addWidget(self.routines_list, 1)

        btn_layout = QHBoxLayout()
        delete_btn = QPushButton("🗑️ Удалить выбранную")
        delete_btn.setObjectName("danger")
        delete_btn.setToolTip("Delete")
        delete_btn.clicked.connect(self.delete_routine)
        btn_layout.addWidget(delete_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        return widget

    # ========== ВКЛАДКА: СЕГОДНЯ ==========

    def _tab_today(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(8)

        self.today_label = QLabel("Загрузка...")
        self.today_label.setWordWrap(True)
        self.today_label.setTextFormat(Qt.TextFormat.RichText)
        self.today_label.setStyleSheet(
            "font-size: 14px; padding: 10px; "
            "background: #12121a; border: 1px solid #2a2a3a; "
            "border-radius: 8px; color: #e0e0f0;"
        )
        layout.addWidget(self.today_label, 1)

        refresh_btn = QPushButton("🔄 Обновить")
        refresh_btn.clicked.connect(self.refresh_today)
        layout.addWidget(refresh_btn)

        return widget

    # ============================================================
    #  ГОРЯЧИЕ КЛАВИШИ
    # ============================================================

    def _setup_hotkeys(self):
        """Esc, Ctrl+N, Delete, Enter."""
        shortcuts = [
            ("Ctrl+N", self.add_task),
            ("Delete", self._delete_current),
            ("Return", self._enter_current),
            ("Enter", self._enter_current),
            ("Escape", self.close),
        ]
        for key, cb in shortcuts:
            try:
                sc = QShortcut(QKeySequence(key), self)
                sc.activated.connect(cb)
            except Exception as e:
                _log_warn(f"Shortcut {key}: {e}")

    def _delete_current(self):
        """Delete в зависимости от вкладки."""
        idx = self.tabs.currentIndex()
        if idx == 0:
            self.delete_task()
        elif idx == 1:
            self.delete_event()
        elif idx == 2:
            self.delete_routine()

    def _enter_current(self):
        """Enter в зависимости от вкладки."""
        idx = self.tabs.currentIndex()
        if idx == 0:
            self.complete_task()
        elif idx == 1:
            pass  # встречи — только удалить
        elif idx == 2:
            pass  # рутины — только удалить

    # ============================================================
    #  ДЕЙСТВИЯ — ЗАДАЧИ
    # ============================================================

    def add_task(self):
        text = self.task_input.text().strip()
        if not text:
            return
        try:
            result = self.scheduler.create_task(text)
            self.task_input.clear()
            _log(f"Задача: {text[:50]}")
            QMessageBox.information(self, "Задача", result)
            self.refresh_all()
        except Exception as e:
            _log_warn(f"add_task: {e}")
            QMessageBox.warning(self, "Ошибка", f"Не удалось добавить: {e}")

    def complete_task(self):
        item = self.tasks_list.currentItem()
        if not item:
            return
        task_id = item.data(Qt.ItemDataRole.UserRole)
        try:
            result = self.scheduler.complete_task(task_id)
            _log(f"Задача #{task_id} выполнена")
            QMessageBox.information(self, "Готово", result)
            self.refresh_all()
        except Exception as e:
            _log_warn(f"complete_task: {e}")

    def delete_task(self):
        item = self.tasks_list.currentItem()
        if not item:
            return
        task_id = item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self, "Удалить задачу?",
            "Удалить выбранную задачу?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                result = self.scheduler.delete_task(task_id)
                _log(f"Задача #{task_id} удалена")
                QMessageBox.information(self, "Готово", result)
                self.refresh_all()
            except Exception as e:
                _log_warn(f"delete_task: {e}")

    # ============================================================
    #  ДЕЙСТВИЯ — ВСТРЕЧИ
    # ============================================================

    def add_event(self):
        text = self.event_input.text().strip()
        if not text:
            return
        try:
            result = self.scheduler.create_event(text)
            self.event_input.clear()
            _log(f"Встреча: {text[:50]}")
            QMessageBox.information(self, "Встреча", result)
            self.refresh_all()
        except Exception as e:
            _log_warn(f"add_event: {e}")
            QMessageBox.warning(self, "Ошибка", f"Не удалось добавить: {e}")

    def delete_event(self):
        item = self.events_list.currentItem()
        if not item:
            return
        event_id = item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self, "Удалить встречу?",
            "Удалить выбранную встречу?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                result = self.scheduler.delete_event(event_id)
                _log(f"Встреча #{event_id} удалена")
                QMessageBox.information(self, "Готово", result)
                self.refresh_all()
            except Exception as e:
                _log_warn(f"delete_event: {e}")

    # ============================================================
    #  ДЕЙСТВИЯ — РУТИНЫ
    # ============================================================

    def add_routine(self):
        name = self.routine_name.text().strip()
        time_str = self.routine_time.text().strip()
        actions = self.routine_actions.text().strip()

        if not name or not actions:
            QMessageBox.warning(self, "Ошибка", "Заполни название и действия")
            return

        # Валидация времени HH:MM
        if time_str:
            if not re.match(r"^\d{1,2}:\d{2}$", time_str):
                QMessageBox.warning(
                    self, "Ошибка",
                    "Время должно быть в формате HH:MM (например 07:00)"
                )
                return
            hh, mm = map(int, time_str.split(":"))
            if not (0 <= hh <= 23 and 0 <= mm <= 59):
                QMessageBox.warning(
                    self, "Ошибка",
                    "Некорректное время: 00:00–23:59"
                )
                return

        try:
            result = self.scheduler.create_routine(
                name, actions, time_str or "не задано"
            )
            self.routine_name.clear()
            self.routine_time.clear()
            self.routine_actions.clear()
            _log(f"Рутина: {name}")
            QMessageBox.information(self, "Рутина", result)
            self.refresh_all()
        except Exception as e:
            _log_warn(f"add_routine: {e}")
            QMessageBox.warning(self, "Ошибка", f"Не удалось создать: {e}")

    def delete_routine(self):
        item = self.routines_list.currentItem()
        if not item:
            return
        routine_id = item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self, "Удалить рутину?",
            "Удалить выбранную рутину?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                result = self.scheduler.delete_routine(routine_id)
                _log(f"Рутина #{routine_id} удалена")
                QMessageBox.information(self, "Готово", result)
                self.refresh_all()
            except Exception as e:
                _log_warn(f"delete_routine: {e}")

    # ============================================================
    #  ОБНОВЛЕНИЕ
    # ============================================================

    def refresh_today(self):
        try:
            text = self.scheduler.show_today()
            # Преобразуем **жирный** в <b> для QLabel RichText
            text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
            text = text.replace("\n", "<br>")
            self.today_label.setText(text)
        except Exception as e:
            self.today_label.setText(f"⚠️ Ошибка: {e}")
            _log_warn(f"refresh_today: {e}")

    def refresh_all(self):
        """Обновляет все вкладки."""
        self._refresh_tasks()
        self._refresh_events()
        self._refresh_routines()
        self.refresh_today()

    def _refresh_tasks(self):
        try:
            from core.memory import get_tasks
            self.tasks_list.clear()
            tasks = get_tasks(status="active")

            if not tasks:
                item = QListWidgetItem("— Задач пока нет —")
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                self.tasks_list.addItem(item)
                return

            for task in tasks:
                priority = task.get("priority", 1)
                if priority == 3:
                    icon = "🔥 "
                elif priority == 2:
                    icon = "⭐ "
                else:
                    icon = ""

                text = f"{icon}[{task['id']}] {task['title']}"

                due = task.get("due_date")
                if due:
                    try:
                        dt = datetime.fromisoformat(due)
                        text += f"  📅 {DateParser.format_dt(dt)}"
                    except Exception:
                        pass

                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, task["id"])
                self.tasks_list.addItem(item)
        except Exception as e:
            _log_warn(f"Задачи: {e}")

    def _refresh_events(self):
        try:
            from core.memory import get_events
            self.events_list.clear()
            events = get_events()

            if not events:
                item = QListWidgetItem("— Встреч пока нет —")
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                self.events_list.addItem(item)
                return

            for ev in events:
                text = f"[{ev['id']}] {ev['title']}"

                st = ev.get("start_time")
                if st:
                    try:
                        dt = datetime.fromisoformat(st)
                        text += f"  🕐 {DateParser.format_dt(dt)}"
                    except Exception:
                        pass

                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, ev["id"])
                self.events_list.addItem(item)
        except Exception as e:
            _log_warn(f"Встречи: {e}")

    def _refresh_routines(self):
        try:
            from core.memory import get_routines
            self.routines_list.clear()
            routines = get_routines()

            if not routines:
                item = QListWidgetItem("— Рутин пока нет —")
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                self.routines_list.addItem(item)
                return

            for r in routines:
                icon = "✅" if r.get("enabled") else "❌"
                text = f"{icon} [{r['id']}] {r['name']} ({r['schedule']})"
                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, r["id"])
                self.routines_list.addItem(item)
        except Exception as e:
            _log_warn(f"Рутины: {e}")


# ========== ЭКСПОРТ ==========

__all__ = ["SchedulerWindow"]


# ========== ТЕСТ ==========

if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    app = QApplication(sys.argv)
    window = SchedulerWindow()
    window.show()
    sys.exit(app.exec())