# -*- coding: utf-8 -*-
"""
Окно чата для Zeta (резервное/отдельное окно).
Используется как отдельное окно для общения с Zeta.
Поддерживает: историю, факты, Markdown, горячие клавиши, быстрые команды.
"""

import os
import sys
import threading
from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLineEdit, QPushButton, QLabel, QFrame, QSplitter,
    QScrollArea, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QTextCursor, QKeySequence, QShortcut, QColor, QTextCharFormat

from core.ai_engine import ask_zeta
from core.memory import get_history, save_message, get_facts, get_db_stats
from voice.tts import speak
from ui.widget import ZetaWorker

# Темы
THEMES = {
    "dark": {
        "frame_bg": "#1e1e2e",
        "frame_border": "#313244",
        "text": "#cdd6f4",
        "text_secondary": "#a6adc8",
        "chat_bg": "#181825",
        "input_bg": "#313244",
        "accent": "#89b4fa",
        "accent_hover": "#74c7ec",
        "accent_text": "#1e1e2e",
        "success": "#a6e3a1",
        "warning": "#f9e2af",
        "danger": "#f38ba8",
        "info": "#89b4fa",
    },
    "light": {
        "frame_bg": "#eff1f5",
        "frame_border": "#ccd0da",
        "text": "#4c4f69",
        "text_secondary": "#6c6f85",
        "chat_bg": "#e6e9ef",
        "input_bg": "#dce0e8",
        "accent": "#1e66f5",
        "accent_hover": "#04a5e5",
        "accent_text": "#eff1f5",
        "success": "#40a02b",
        "warning": "#df8e1d",
        "danger": "#d20f39",
        "info": "#1e66f5",
    },
}


class ChatWindow(QWidget):
    """
    Отдельное окно чата для Zeta.
    """

    def __init__(self, theme_name: str = "dark"):
        super().__init__()
        self.theme_name = theme_name
        self.theme = THEMES.get(theme_name, THEMES["dark"])
        self.worker: Optional[ZetaWorker] = None
        self.is_dark = theme_name == "dark"
        self.voice_enabled = True
        self._z_start_pos = 0
        self._message_count = 0
        
        self.setWindowTitle("💬 Чат Zeta")
        self.setGeometry(100, 100, 700, 750)
        
        self.init_ui()
        self.setup_hotkeys()
        self.load_chat_history()  # Загружаем историю
        self.greet()

    # ========== UI ==========

    def init_ui(self):
        """Создаёт интерфейс окна чата."""
        # Основной контейнер
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Заголовок
        self.header = self._create_header()
        main_layout.addWidget(self.header)

        # Быстрые команды
        self.quick_actions = self._create_quick_actions()
        main_layout.addWidget(self.quick_actions)

        # Чат
        self.chat_display = self._create_chat_display()
        main_layout.addWidget(self.chat_display)

        # Индикатор печати
        self.typing_label = QLabel("Z печатает...")
        self.typing_label.setStyleSheet(f"color: {self.theme['text_secondary']}; font-size: 12px; padding: 4px 12px; background-color: {self.theme['chat_bg']};")
        self.typing_label.hide()
        main_layout.addWidget(self.typing_label)

        # Ввод
        self.input_area = self._create_input_area()
        main_layout.addWidget(self.input_area)

        # Статус бар
        self.status_bar = self._create_status_bar()
        main_layout.addWidget(self.status_bar)

        # Применяем тему
        self.apply_theme()

    def _create_header(self) -> QFrame:
        """Создаёт заголовок окна."""
        header = QFrame()
        header.setFixedHeight(50)
        header.setStyleSheet(f"background-color: {self.theme['frame_bg']}; border-bottom: 1px solid {self.theme['frame_border']};")

        layout = QHBoxLayout(header)
        layout.setContentsMargins(12, 8, 12, 8)

        # Заголовок
        self.title_label = QLabel("💬 Чат с Zeta")
        self.title_label.setStyleSheet(f"color: {self.theme['text']}; font-size: 16px; font-weight: bold;")
        layout.addWidget(self.title_label)

        # Статус
        self.status_dot = QLabel("🟢")
        layout.addWidget(self.status_dot)
        self.status_text = QLabel("Онлайн")
        self.status_text.setStyleSheet(f"color: {self.theme['text_secondary']}; font-size: 12px;")
        layout.addWidget(self.status_text)

        layout.addStretch()

        # Кнопка очистки
        self.clear_btn = QPushButton("🗑️")
        self.clear_btn.setFixedSize(30, 30)
        self.clear_btn.setStyleSheet(self._get_button_style())
        self.clear_btn.setToolTip("Очистить чат")
        self.clear_btn.clicked.connect(self.clear_chat)
        layout.addWidget(self.clear_btn)

        # Кнопка закрытия
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(30, 30)
        self.close_btn.setStyleSheet(self._get_close_style())
        self.close_btn.setToolTip("Закрыть")
        self.close_btn.clicked.connect(self.close)
        layout.addWidget(self.close_btn)

        return header

    def _create_quick_actions(self) -> QFrame:
        """Создаёт панель быстрых команд."""
        frame = QFrame()
        frame.setFixedHeight(40)
        frame.setStyleSheet(f"background-color: {self.theme['frame_bg']}; border-bottom: 1px solid {self.theme['frame_border']};")

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(6)

        # Кнопки быстрых команд
        quick_buttons = [
            ("📊 Статус", self.show_status),
            ("📸 Скрин", self.take_screenshot),
            ("🧠 Факты", self.show_facts),
            ("🗑️ Очистить", self.clear_chat),
        ]

        for label, callback in quick_buttons:
            btn = QPushButton(label)
            btn.setFixedSize(100, 28)
            btn.setStyleSheet(self._get_quick_button_style())
            btn.clicked.connect(callback)
            layout.addWidget(btn)

        layout.addStretch()

        return frame

    def _create_chat_display(self) -> QTextEdit:
        """Создаёт поле для отображения чата."""
        chat = QTextEdit()
        chat.setReadOnly(True)
        chat.setStyleSheet(f"""
            QTextEdit {{
                background-color: {self.theme['chat_bg']};
                color: {self.theme['text']};
                border: none;
                font-size: 13px;
                padding: 12px;
                font-family: 'Segoe UI', Arial, sans-serif;
            }}
        """)
        return chat

    def _create_input_area(self) -> QFrame:
        """Создаёт область ввода."""
        frame = QFrame()
        frame.setFixedHeight(60)
        frame.setStyleSheet(f"background-color: {self.theme['frame_bg']}; border-top: 1px solid {self.theme['frame_border']};")

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        # Поле ввода
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Напиши что-нибудь...")
        self.input_field.setStyleSheet(f"""
            QLineEdit {{
                background-color: {self.theme['input_bg']};
                color: {self.theme['text']};
                border-radius: 8px;
                border: none;
                padding: 8px 14px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 1px solid {self.theme['accent']};
            }}
        """)
        self.input_field.returnPressed.connect(self.send_message)
        layout.addWidget(self.input_field)

        # Кнопка отправки
        self.send_btn = QPushButton("➤")
        self.send_btn.setFixedSize(40, 40)
        self.send_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.theme['accent']};
                color: {self.theme['accent_text']};
                border-radius: 8px;
                border: none;
                font-size: 18px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {self.theme['accent_hover']};
            }}
            QPushButton:disabled {{
                background-color: {self.theme['frame_border']};
                color: {self.theme['text_secondary']};
            }}
        """)
        self.send_btn.clicked.connect(self.send_message)
        layout.addWidget(self.send_btn)

        return frame

    def _create_status_bar(self) -> QFrame:
        """Создаёт статус-бар."""
        bar = QFrame()
        bar.setFixedHeight(28)
        bar.setStyleSheet(f"background-color: {self.theme['frame_bg']}; border-top: 1px solid {self.theme['frame_border']};")

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 12, 0)

        self.status_label = QLabel("Готов к работе")
        self.status_label.setStyleSheet(f"color: {self.theme['text_secondary']}; font-size: 11px;")
        layout.addWidget(self.status_label)

        layout.addStretch()

        # Голос
        self.voice_btn = QPushButton("🔊")
        self.voice_btn.setFixedSize(24, 24)
        self.voice_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {self.theme['text_secondary']};
                border: none;
                font-size: 14px;
            }}
            QPushButton:hover {{
                color: {self.theme['accent']};
            }}
        """)
        self.voice_btn.setToolTip("Включить/выключить голос")
        self.voice_btn.clicked.connect(self.toggle_voice)
        layout.addWidget(self.voice_btn)

        # Количество сообщений
        self.msg_count = QLabel("💬 0")
        self.msg_count.setStyleSheet(f"color: {self.theme['text_secondary']}; font-size: 11px;")
        layout.addWidget(self.msg_count)

        return bar

    # ========== СТИЛИ ==========

    def _get_button_style(self) -> str:
        return f"""
            QPushButton {{
                background: transparent;
                color: {self.theme['text_secondary']};
                border: none;
                font-size: 14px;
            }}
            QPushButton:hover {{
                color: {self.theme['danger']};
            }}
        """

    def _get_close_style(self) -> str:
        return f"""
            QPushButton {{
                background: transparent;
                color: {self.theme['text_secondary']};
                border: none;
                font-size: 14px;
            }}
            QPushButton:hover {{
                color: {self.theme['danger']};
                background-color: rgba(243, 139, 168, 0.2);
                border-radius: 4px;
            }}
        """

    def _get_quick_button_style(self) -> str:
        return f"""
            QPushButton {{
                background: {self.theme['input_bg']};
                color: {self.theme['text']};
                border-radius: 6px;
                border: none;
                font-size: 11px;
                padding: 4px 8px;
            }}
            QPushButton:hover {{
                background: {self.theme['accent']};
                color: {self.theme['accent_text']};
            }}
        """

    def apply_theme(self):
        """Применяет тему."""
        self.setStyleSheet(f"background-color: {self.theme['frame_bg']};")

    # ========== ГОРЯЧИЕ КЛАВИШИ ==========

    def setup_hotkeys(self):
        """Настраивает горячие клавиши."""
        # Ctrl+Enter для отправки
        shortcut_send = QShortcut(QKeySequence("Ctrl+Enter"), self)
        shortcut_send.activated.connect(self.send_message)

        # Ctrl+L для очистки
        shortcut_clear = QShortcut(QKeySequence("Ctrl+L"), self)
        shortcut_clear.activated.connect(self.clear_chat)

        # Ctrl+S для статуса
        shortcut_status = QShortcut(QKeySequence("Ctrl+Shift+S"), self)
        shortcut_status.activated.connect(self.show_status)

    # ========== ИСТОРИЯ ==========

    def load_chat_history(self):
        """Загружает историю чата из базы данных."""
        try:
            history = get_history(limit=20)
            for msg in history:
                if msg["role"] == "user":
                    self._insert_message("user", msg["content"])
                else:
                    self._insert_message("zeta", msg["content"])
            self._message_count = len(history)
            self.msg_count.setText(f"💬 {self._message_count}")
        except Exception:
            pass

    # ========== ФУНКЦИИ ЧАТА ==========

    def greet(self):
        """Приветственное сообщение."""
        self._insert_message("system", "🤖 Добро пожаловать в чат Zeta!")
        self._insert_message("system", "💡 Напиши что-нибудь внизу...")

    def send_message(self):
        """Отправляет сообщение."""
        text = self.input_field.text().strip()
        if not text:
            return

        self.input_field.clear()
        self._insert_message("user", text)

        # Сохраняем позицию для ответа Z
        self._z_start_pos = self.chat_display.textCursor().position()

        # Показываем индикатор печати
        self.typing_label.show()
        self.send_btn.setEnabled(False)
        self.status_label.setText("⏳ Z думает...")
        self.status_text.setText("Печатает...")

        # Запускаем поток
        self.worker = ZetaWorker(text, mode="default")
        self.worker.chunk_ready.connect(self._on_chunk)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _on_chunk(self, full_text: str):
        """Обновляет ответ Zeta по кусочкам."""
        self._update_last_z(full_text)

    def _on_finished(self, full_text: str):
        """Завершение ответа."""
        self.typing_label.hide()
        self.send_btn.setEnabled(True)
        self.status_label.setText("Готов")
        self.status_text.setText("Онлайн")
        self._update_last_z(full_text)

        # Обновляем счётчик
        self._update_msg_count()

        # Голос
        if self.voice_enabled:
            speak(full_text)

    def _on_error(self, error_msg: str):
        """Обработка ошибки."""
        self.typing_label.hide()
        self.send_btn.setEnabled(True)
        self.status_label.setText("⚠️ Ошибка")
        self.status_text.setText("Ошибка")
        self._update_last_z(error_msg)

    def _insert_message(self, sender: str, text: str):
        """Вставляет сообщение в чат."""
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.chat_display.setTextCursor(cursor)

        colors = {
            "user": self.theme["success"],
            "zeta": self.theme["accent"],
            "system": self.theme["text_secondary"]
        }
        names = {
            "user": "👤 Вы",
            "zeta": "🤖 Zeta",
            "system": "ℹ️ Система"
        }

        color = colors.get(sender, self.theme["text"])
        name = names.get(sender, sender)

        # Форматирование Markdown
        text_html = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text_html = text_html.replace("\n", "<br>")
        # Обработка кода
        if "```" in text:
            parts = text_html.split("```")
            text_html = ""
            for i, part in enumerate(parts):
                if i % 2 == 1:
                    text_html += f'<pre style="background:rgba(0,0,0,0.3);padding:8px;border-radius:6px;font-family:monospace;">{part}</pre>'
                else:
                    text_html += part
        else:
            # Обработка жирного
            text_html = text_html.replace("**", "<b>")

        html = f'<span style="color:{color};font-weight:bold;">{name}:</span> '
        html += f'<span style="color:{self.theme["text"]};">{text_html}</span><br>'

        self.chat_display.insertHtml(html)
        self._scroll_to_bottom()

        self._message_count += 1
        self.msg_count.setText(f"💬 {self._message_count}")

    def _update_last_z(self, text: str):
        """Обновляет последнее сообщение Zeta."""
        cursor = self.chat_display.textCursor()
        cursor.setPosition(self._z_start_pos)
        cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()

        # Форматирование Markdown
        text_html = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text_html = text_html.replace("\n", "<br>")
        if "```" in text:
            parts = text_html.split("```")
            text_html = ""
            for i, part in enumerate(parts):
                if i % 2 == 1:
                    text_html += f'<pre style="background:rgba(0,0,0,0.3);padding:8px;border-radius:6px;font-family:monospace;">{part}</pre>'
                else:
                    text_html += part
        else:
            text_html = text_html.replace("**", "<b>")

        html = f'<span style="color:{self.theme["accent"]};font-weight:bold;">🤖 Zeta:</span> '
        html += f'<span style="color:{self.theme["text"]};">{text_html}</span><br>'

        cursor.insertHtml(html)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        """Прокручивает чат вниз."""
        sb = self.chat_display.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _update_msg_count(self):
        """Обновляет счётчик сообщений."""
        try:
            stats = get_db_stats()
            self.msg_count.setText(f"💬 {stats.get('messages', 0)}")
        except Exception:
            self.msg_count.setText(f"💬 {self._message_count}")

    # ========== БЫСТРЫЕ КОМАНДЫ ==========

    def show_status(self):
        """Показывает статус системы."""
        try:
            from modules.system_monitor import get_system_status
            status = get_system_status()
            self._insert_message("zeta", status)
            self.status_label.setText("📊 Статус показан")
        except Exception as e:
            self._insert_message("system", f"⚠️ Ошибка: {e}")

    def take_screenshot(self):
        """Делает скриншот."""
        try:
            from core.screen_capture import take_screenshot
            screenshot = take_screenshot()
            if screenshot:
                self._insert_message("zeta", "📸 Скриншот готов. Откройте папку data/screenshots")
            else:
                self._insert_message("system", "⚠️ Не удалось сделать скриншот")
        except Exception as e:
            self._insert_message("system", f"⚠️ Ошибка: {e}")

    def show_facts(self):
        """Показывает факты о пользователе."""
        try:
            facts = get_facts()
            if facts:
                text = "🧠 **Факты о вас:**\n"
                for fact in facts:
                    text += f"• {fact['key']}: {fact['content']}\n"
                self._insert_message("zeta", text)
            else:
                self._insert_message("zeta", "🧠 У меня пока нет фактов о вас.")
        except Exception as e:
            self._insert_message("system", f"⚠️ Ошибка: {e}")

    # ========== УПРАВЛЕНИЕ ==========

    def clear_chat(self):
        """Очищает чат."""
        self.chat_display.clear()
        self.greet()
        self._update_msg_count()

    def toggle_voice(self):
        """Включает/выключает голос."""
        self.voice_enabled = not self.voice_enabled
        self.voice_btn.setText("🔊" if self.voice_enabled else "🔇")
        self.voice_btn.setToolTip("Голос выключен" if not self.voice_enabled else "Голос включён")

    # ========== СОБЫТИЯ ==========

    def closeEvent(self, event):
        """Закрытие окна."""
        if self.worker and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait()
        event.accept()

    def keyPressEvent(self, event):
        """Обработка клавиш."""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        super().keyPressEvent(event)


# ========== ТЕСТ ==========
if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    window = ChatWindow()
    window.show()
    sys.exit(app.exec())