# -*- coding: utf-8 -*-
"""
Zeta — главный виджет.
Чистый и минималистичный интерфейс + фото + голосовой ввод + Wake Word + Планировщик + Автоматизация + Устройства + Режим разработчика.
Два режима голоса: обычный + диалоговый.
Wake Word по умолчанию ВЫКЛЮЧЕН.

ИСПРАВЛЕНО (2026-09-21):
    - load_chat_history: НЕ удаляет историю из БД, читает последние 20 сообщений
    - toggle_voice_input: блокирует ручной ввод во время диалогового режима
    - ZetaWorker.run: speak() в отдельном daemon-потоке (не блокирует UI)
    - apply_settings: обновляет размер виджета, если изменился в настройках
    - _handle_wake_activation: проверка _voice_mode перед стартом диалога
    - load_position: проверка границ экрана
    - Кнопка "Чат" заменена на "Dev" (открывает ProgrammerWindow)
    - Добавлен хоткей Ctrl+Shift+F для фокуса на поле ввода
"""

import sys
import os
import html
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFrame,
    QSystemTrayIcon, QMenu, QMessageBox, QScrollArea,
    QInputDialog, QGraphicsDropShadowEffect, QSizePolicy,
    QFileDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QRectF
from PyQt6.QtGui import (
    QPixmap, QIcon, QPainter, QColor, QPen, QFont,
    QLinearGradient, QPainterPath, QAction, QKeySequence, QShortcut
)

from core.ai_engine import ask_zeta
from core.memory import get_setting, save_setting, get_history, clear_history
from voice.tts import speak
from ui.settings import SettingsWindow
from ui.programmer import ProgrammerWindow
from ui.voice_menu import VoiceModeMenu
from ui.scheduler_window import SchedulerWindow
from ui.automation_window import AutomationWindow
from ui.devices_window import DevicesWindow

# === ОБРАБОТКА ИЗОБРАЖЕНИЙ ===
try:
    from modules.image_handler import get_image_handler, SUPPORTED_FORMATS
    HAS_IMAGE_HANDLER = True
except ImportError:
    HAS_IMAGE_HANDLER = False
    SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
    print("⚠️ Модуль image_handler не найден.")

# === ГОЛОСОВОЙ ВВОД (STT) ===
try:
    from voice.stt import get_stt, HAS_SOUND
    HAS_STT = HAS_SOUND
except ImportError:
    HAS_STT = False
    get_stt = None
    print("⚠️ Модуль STT не найден.")

# === WAKE WORD ===
try:
    from voice.wake_word import get_wake_word, HAS_WAKEWORD
    HAS_WAKE = HAS_WAKEWORD
except ImportError:
    HAS_WAKE = False
    get_wake_word = None
    print("⚠️ Модуль wake_word не найден.")


# ========== РАЗМЕРЫ ==========
SIZE_MAP = {
    "S": (400, 550),
    "M": (500, 700),
    "L": (650, 900),
    "XL": (800, 1100),
}


# ========== ТЕМА ==========
THEME = {
    "window": "#030817",
    "panel": "#07101f",
    "panel2": "#0a1428",
    "panel3": "#0d1930",
    "border": "#273a69",
    "border_blue": "#2378ff",
    "border_purple": "#a63cff",
    "text": "#f2f4ff",
    "text_secondary": "#8d98b8",
    "text_dim": "#596684",
    "blue": "#3197ff",
    "blue_light": "#56b8ff",
    "purple": "#9c42ff",
    "purple_light": "#c06cff",
    "green": "#2df2a3",
    "red": "#ff5d83",
    "user_bg": "#0c1428",
    "zeta_bg": "#111438",
    "search": "#0b1429",
    "input": "#0a1429",
}


# ========== ИКОНКА ТРЕЯ ==========
def create_app_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(0, 0, 64, 64)
    gradient.setColorAt(0, QColor("#168cff"))
    gradient.setColorAt(1, QColor("#8b36ff"))
    painter.setBrush(gradient)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(2, 2, 60, 60, 17, 17)

    painter.setPen(QColor("#ffffff"))
    font = QFont("Segoe UI", 31)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "Z")
    painter.end()
    return QIcon(pixmap)


# ========== НЕОНОВАЯ РАМКА ==========
class NeonFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("NeonFrame")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(1.5, 1.5, self.width() - 3, self.height() - 3)

        bg_gradient = QLinearGradient(0, 0, self.width(), self.height())
        bg_gradient.setColorAt(0.0, QColor("#030817"))
        bg_gradient.setColorAt(0.45, QColor("#050b19"))
        bg_gradient.setColorAt(1.0, QColor("#08051b"))

        path = QPainterPath()
        path.addRoundedRect(rect, 34, 34)
        painter.fillPath(path, bg_gradient)

        border_gradient = QLinearGradient(0, 0, self.width(), self.height())
        border_gradient.setColorAt(0.00, QColor("#7d38ff"))
        border_gradient.setColorAt(0.22, QColor("#228dff"))
        border_gradient.setColorAt(0.55, QColor("#9d42ff"))
        border_gradient.setColorAt(0.78, QColor("#4a5dff"))
        border_gradient.setColorAt(1.00, QColor("#b63cff"))

        painter.setPen(QPen(border_gradient, 2.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 34, 34)

        inner = rect.adjusted(3, 3, -3, -3)
        painter.setPen(QPen(QColor(50, 100, 220, 70), 1))
        painter.drawRoundedRect(inner, 31, 31)

        painter.end()


# ========== АВАТАР ==========
class AvatarWidget(QWidget):
    def __init__(self, zeta: bool = False, parent=None):
        super().__init__(parent)
        self.zeta = zeta
        self.setFixedSize(48, 48)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(3, 3, self.width() - 6, self.height() - 6)
        gradient = QLinearGradient(0, 0, self.width(), self.height())

        if self.zeta:
            gradient.setColorAt(0, QColor("#2d9dff"))
            gradient.setColorAt(1, QColor("#6239ff"))
        else:
            gradient.setColorAt(0, QColor("#713dff"))
            gradient.setColorAt(1, QColor("#b34cff"))

        painter.setBrush(gradient)
        painter.setPen(QPen(QColor(100, 160, 255, 220), 1.5))
        painter.drawEllipse(rect)

        if self.zeta:
            font = QFont("Segoe UI", 22)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Z")
        else:
            painter.setPen(QColor("#e5c7ff"))
            painter.setBrush(QColor("#c46bff"))
            painter.drawEllipse(QRectF(19, 10, 12, 12))
            painter.drawRoundedRect(QRectF(12, 24, 26, 16), 8, 8)

        painter.end()


# ========== СООБЩЕНИЕ ==========
class MessageWidget(QFrame):
    def __init__(self, sender: str, text: str, time_text: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.sender = sender
        self.message_text = text
        self.is_zeta = sender in ("Z", "Zeta", "Зета")

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 4)
        outer.setSpacing(12)

        self.avatar = AvatarWidget(self.is_zeta, self)
        outer.addWidget(self.avatar, 0, Qt.AlignmentFlag.AlignTop)

        bubble = QFrame()
        bubble.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        if self.is_zeta:
            bubble.setStyleSheet("""
                QFrame {
                    background-color: #111438;
                    border: 1px solid #6745ff;
                    border-radius: 16px;
                }
            """)
        else:
            bubble.setStyleSheet("""
                QFrame {
                    background-color: #0b1428;
                    border: 1px solid #17284c;
                    border-radius: 16px;
                }
            """)

        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(18, 12, 18, 14)
        bubble_layout.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(8)

        name = QLabel("Zeta" if self.is_zeta else "Вы")
        name.setStyleSheet(f"""
            color: {'#65c6ff' if self.is_zeta else '#9d79ff'};
            font-size: 13px;
            font-weight: 700;
            background: transparent;
            border: none;
        """)
        header.addWidget(name)

        current_time = time_text or datetime.now().strftime("%H:%M")
        clock = QLabel(current_time)
        clock.setStyleSheet("""
            color: #7784a5;
            font-size: 11px;
            background: transparent;
            border: none;
        """)
        header.addWidget(clock)
        header.addStretch()
        bubble_layout.addLayout(header)

        self.text_label = QLabel()
        self.text_label.setTextFormat(Qt.TextFormat.RichText)
        self.text_label.setWordWrap(True)
        self.text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.text_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.text_label.setStyleSheet("""
            QLabel {
                color: #f1f4ff;
                font-size: 14px;
                line-height: 140%;
                background: transparent;
                border: none;
            }
        """)
        bubble_layout.addWidget(self.text_label)
        outer.addWidget(bubble, 1)

        self.setText(text)

    def setText(self, text: str):
        self.message_text = text
        safe = html.escape(text)
        safe = safe.replace("**", "<b>", 1) if safe.count("**") >= 2 else safe
        if "<b>" in safe:
            safe = safe.replace("**", "</b>", 1)
        safe = safe.replace("\n", "<br>")
        self.text_label.setText(safe)
        self.updateGeometry()


# ========== ПОТОК ZETA ==========
class ZetaWorker(QThread):
    chunk_ready = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    thinking = pyqtSignal(bool)

    def __init__(self, message: str, mode: str = "default"):
        super().__init__()
        self.message = message
        self.mode = mode
        self._full = ""
        self._is_running = True
        self._voice_enabled = False

    def set_voice_enabled(self, enabled: bool):
        self._voice_enabled = enabled

    def run(self):
        try:
            self.thinking.emit(True)
            for chunk in ask_zeta(self.message, mode=self.mode):
                if not self._is_running:
                    break
                self._full += chunk
                self.chunk_ready.emit(self._full)

            self.thinking.emit(False)

            if self._is_running:
                # ИСПРАВЛЕНО: speak() в отдельном потоке, чтобы не блокировать
                if self._voice_enabled and self._full.strip():
                    full = self._full

                    def _speak_async():
                        try:
                            speak(full)
                        except Exception:
                            pass

                    threading.Thread(target=_speak_async, daemon=True).start()

                self.finished.emit(self._full)
        except Exception as e:
            self.thinking.emit(False)
            self.error.emit(f"⚠️ Ошибка: {e}")

    def stop(self):
        self._is_running = False


# ========== ПОТОК АНАЛИЗА ФОТО ==========
class ImageWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, image_path: str, question: str = None):
        super().__init__()
        self.image_path = image_path
        self.question = question

    def run(self):
        try:
            if not HAS_IMAGE_HANDLER:
                self.error.emit("⚠️ Модуль обработки изображений не найден.")
                return

            handler = get_image_handler()
            ok, answer = handler.analyze_image(self.image_path, self.question)

            if ok:
                self.finished.emit(answer)
            else:
                self.error.emit(answer)
        except Exception as e:
            self.error.emit(f"⚠️ Ошибка анализа фото: {e}")


# ========== ПОТОК ГОЛОСОВОГО ВВОДА ==========
class VoiceWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, wav_path: str):
        super().__init__()
        self.wav_path = wav_path

    def run(self):
        try:
            if not HAS_STT or get_stt is None:
                self.error.emit("⚠️ STT не установлен.")
                return

            stt = get_stt()
            text = stt.recognize_file(self.wav_path)

            if text:
                self.finished.emit(text)
            else:
                self.error.emit("⚠️ Речь не распознана. Попробуйте снова.")
        except Exception as e:
            self.error.emit(f"⚠️ Ошибка STT: {e}")


# ========== ПОТОК ДИАЛОГОВОГО СЛУШАНИЯ ==========
class DialogVoiceWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, max_duration: int = 30, silence_duration: float = 3.0):
        super().__init__()
        self.max_duration = max_duration
        self.silence_duration = silence_duration

    def run(self):
        try:
            if not HAS_STT or get_stt is None:
                self.error.emit("⚠️ STT не установлен.")
                return

            stt = get_stt()
            wav_path = stt.record_until_silence(
                max_duration=self.max_duration,
                silence_duration=self.silence_duration,
                silence_threshold=500
            )

            if wav_path:
                self.finished.emit(wav_path)
            else:
                self.finished.emit("")
        except Exception as e:
            self.error.emit(f"⚠️ Ошибка записи: {e}")


# ========== ГЛАВНЫЙ WIDGET ==========
class ZetaWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._drag_pos = None
        self.settings_window: Optional[SettingsWindow] = None
        self.programmer_window: Optional[ProgrammerWindow] = None
        self.scheduler_window: Optional[SchedulerWindow] = None
        self.automation_window: Optional[AutomationWindow] = None
        self.devices_window: Optional[DevicesWindow] = None
        self.worker: Optional[ZetaWorker] = None
        self.image_worker: Optional[ImageWorker] = None
        self.voice_worker: Optional[VoiceWorker] = None
        self.dialog_worker: Optional[DialogVoiceWorker] = None
        self._stream_message: Optional[MessageWidget] = None
        self._message_count = 0
        self._is_collapsed = False
        self._is_recording = False
        self._voice_mode = None
        self._wake_enabled = False
        self._typing_dots = 0
        self._typing_timer = QTimer(self)
        self._typing_timer.timeout.connect(self._update_typing_animation)
        self._messages = []

        self._load_settings()
        self.init_ui()
        self.load_position()
        self.load_chat_history()
        self.setup_hotkeys()
        self.setup_tray()
        self.apply_opacity()

        self.setAcceptDrops(True)

        self._save_timer = QTimer(self)
        self._save_timer.timeout.connect(self.save_position)
        self._save_timer.start(30000)

        if self._wake_enabled:
            QTimer.singleShot(2000, self.start_wake_word)

    def _load_settings(self):
        self.theme_name = get_setting("theme", "dark")
        size_key = get_setting("widget_size", "M")
        self.widget_width, self.widget_height = SIZE_MAP.get(size_key, SIZE_MAP["M"])
        self.voice_enabled = get_setting("voice_enabled", "true") == "true"
        self.avatar_path = get_setting("avatar_path", "")
        try:
            self.widget_opacity = float(get_setting("widget_opacity", "1.0"))
        except Exception:
            self.widget_opacity = 1.0
        self.auto_focus = get_setting("auto_focus", "true") == "true"

        try:
            self._wake_enabled = get_setting("wake_word_enabled", "false") == "true"
        except Exception:
            self._wake_enabled = False

    def init_ui(self):
        self.setWindowTitle("Zeta")
        self.setFixedSize(self.widget_width, self.widget_height)
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(45)
        shadow.setXOffset(0)
        shadow.setYOffset(0)
        shadow.setColor(QColor(50, 80, 255, 90))
        self.setGraphicsEffect(shadow)

        self.main_frame = NeonFrame(self)
        self.main_frame.setGeometry(0, 0, self.widget_width, self.widget_height)

        main_layout = QVBoxLayout(self.main_frame)
        main_layout.setContentsMargins(20, 14, 20, 14)
        main_layout.setSpacing(8)

        main_layout.addLayout(self._create_header())
        self.section_bar = self._create_section_bar()
        main_layout.addWidget(self.section_bar)
        main_layout.addWidget(self._create_date_divider())

        self.chat_frame = QFrame()
        self.chat_frame.setObjectName("ChatFrame")
        self.chat_frame.setStyleSheet("""
            QFrame#ChatFrame {
                background-color: #050c19;
                border: 1px solid #1b315d;
                border-radius: 20px;
            }
        """)
        chat_layout = QVBoxLayout(self.chat_frame)
        chat_layout.setContentsMargins(14, 14, 14, 10)
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.chat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chat_scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: #070d1b; width: 10px; border-radius: 5px; margin: 2px; }
            QScrollBar::handle:vertical { background: #354a88; border-radius: 5px; min-height: 50px; }
            QScrollBar::handle:vertical:hover { background: #6550c8; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        self.chat_container = QWidget()
        self.chat_container.setStyleSheet("background: transparent;")
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_layout.setSpacing(8)
        self.chat_layout.addStretch()
        self.chat_scroll.setWidget(self.chat_container)
        chat_layout.addWidget(self.chat_scroll)
        main_layout.addWidget(self.chat_frame, 1)

        self.typing_label = QLabel("Zeta печатает...")
        self.typing_label.setStyleSheet("""
            QLabel { color: #6ebaff; font-size: 13px; padding-left: 8px; background: transparent; }
        """)
        self.typing_label.hide()
        main_layout.addWidget(self.typing_label)

        main_layout.addLayout(self._create_input_area())
        main_layout.addWidget(self._create_status_bar())

    # ========== HEADER ==========
    def _create_header(self):
        layout = QHBoxLayout()
        layout.setSpacing(12)

        logo = QFrame()
        logo.setFixedSize(50, 50)
        logo.setStyleSheet("""
            QFrame {
                background-color: #2937e8;
                border: 1px solid #6674ff;
                border-radius: 14px;
            }
        """)
        logo_layout = QVBoxLayout(logo)
        logo_label = QLabel("Z")
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_label.setStyleSheet("color: white; font-size: 28px; font-weight: 800; background: transparent;")
        logo_layout.addWidget(logo_label)
        layout.addWidget(logo)

        divider = QFrame()
        divider.setFixedWidth(1)
        divider.setFixedHeight(36)
        divider.setStyleSheet("background-color: #304267;")
        layout.addWidget(divider)

        name_layout = QVBoxLayout()
        name_layout.setSpacing(1)
        title = QLabel("Zeta")
        title.setStyleSheet("color: #f6f7ff; font-size: 24px; font-weight: 700; background: transparent;")
        name_layout.addWidget(title)
        status = QLabel("●  Онлайн")
        status.setStyleSheet("color: #39f4a8; font-size: 12px; background: transparent;")
        name_layout.addWidget(status)
        layout.addLayout(name_layout)

        layout.addStretch()

        self.collapse_btn = self._window_button("−", "Свернуть")
        self.collapse_btn.clicked.connect(self.toggle_collapse)
        layout.addWidget(self.collapse_btn)

        self.settings_btn = self._window_button("⚙", "Настройки")
        self.settings_btn.clicked.connect(self.open_settings)
        layout.addWidget(self.settings_btn)

        self.close_btn = self._window_button("×", "Закрыть", danger=True)
        self.close_btn.clicked.connect(self.close)
        layout.addWidget(self.close_btn)

        return layout

    def _window_button(self, text, tooltip, danger=False):
        button = QPushButton(text)
        button.setFixedSize(34, 34)
        color = "#ff6c95" if danger else "#c5cee9"
        button.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {color};
                font-size: 20px;
                border-radius: 9px;
            }}
            QPushButton:hover {{
                background-color: rgba(100,120,220,0.15);
            }}
        """)
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    # ========== SECTION BAR ==========
    def _create_section_bar(self):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #071124;
                border: 1px solid #223866;
                border-radius: 16px;
            }
        """)

        outer = QVBoxLayout(frame)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        # ИСПРАВЛЕНО: 💬 Чат → 💻 Dev (открывает Режим разработчика)
        sections = [
            ("💻", "Dev",    self.open_programmer_mode),
            ("📷", "Фото",   self.open_photo),
            ("🖥️", "Экран", self.take_screenshot),
            ("🧠", "Память", self.show_facts),
            ("📁", "Файлы",  self.open_explorer),
            ("📅", "План",   self.open_scheduler),
            ("🤖", "Авто",   self.open_automation),
            ("🌐", "Сеть",   self.open_devices),
            ("⏰", "Буд.",   self.set_reminder),
            ("🎯", "Wake",   self.toggle_wake_word),
        ]

        row1 = QHBoxLayout()
        row1.setSpacing(6)
        row2 = QHBoxLayout()
        row2.setSpacing(6)

        for idx, (icon, name, callback) in enumerate(sections):
            button = QPushButton()
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedHeight(46)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.setText(f"{icon}\n{name}")
            button.setStyleSheet("""
                QPushButton {
                    background-color: #101b35;
                    border: 1px solid #1c2c54;
                    border-radius: 10px;
                    color: #dbe2f7;
                    font-size: 10px;
                    font-weight: 600;
                    padding: 2px;
                    text-align: center;
                }
                QPushButton:hover {
                    background-color: #172755;
                    border: 1px solid #3a5bb8;
                    color: white;
                }
                QPushButton:pressed {
                    background-color: #0c1428;
                }
            """)
            button.clicked.connect(callback)

            if idx < 5:
                row1.addWidget(button)
            else:
                row2.addWidget(button)

        outer.addLayout(row1)
        outer.addLayout(row2)

        return frame

    # ========== DATE ==========
    def _create_date_divider(self):
        frame = QFrame()
        frame.setFixedHeight(26)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)

        line_left = QFrame()
        line_left.setFrameShape(QFrame.Shape.HLine)
        line_left.setStyleSheet("color: #253867;")
        line_right = QFrame()
        line_right.setFrameShape(QFrame.Shape.HLine)
        line_right.setStyleSheet("color: #253867;")

        pill = QLabel("Сегодня")
        pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pill.setFixedWidth(88)
        pill.setStyleSheet("""
            QLabel {
                color: #dbe2ff;
                background-color: #0a1428;
                border: 1px solid #273c6d;
                border-radius: 12px;
                font-size: 12px;
                padding: 1px 8px;
            }
        """)
        layout.addWidget(line_left, 1)
        layout.addWidget(pill)
        layout.addWidget(line_right, 1)
        return frame

    # ========== INPUT ==========
    def _create_input_area(self):
        layout = QHBoxLayout()
        layout.setSpacing(8)

        frame = QFrame()
        frame.setFixedHeight(54)
        frame.setStyleSheet("""
            QFrame {
                background-color: #09142a;
                border: 1px solid #3858b1;
                border-radius: 18px;
            }
        """)
        inner = QHBoxLayout(frame)
        inner.setContentsMargins(8, 6, 6, 6)
        inner.setSpacing(6)

        self.attach_btn = QPushButton("📎")
        self.attach_btn.setFixedSize(34, 34)
        self.attach_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #8b96b6;
                border: none;
                font-size: 17px;
            }
            QPushButton:hover { color: #45aaff; }
        """)
        self.attach_btn.setToolTip("Прикрепить фото")
        self.attach_btn.clicked.connect(self.open_photo)
        inner.addWidget(self.attach_btn)

        self.mic_btn = QPushButton("🎤")
        self.mic_btn.setFixedSize(34, 34)
        self.mic_btn.setStyleSheet(self._mic_btn_style(False))
        self.mic_btn.setToolTip("Голосовой ввод")
        self.mic_btn.clicked.connect(self.toggle_voice_input)
        inner.addWidget(self.mic_btn)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Напиши что-нибудь...")
        self.input_field.setStyleSheet("""
            QLineEdit {
                background: transparent;
                color: #f3f5ff;
                border: none;
                font-size: 15px;
            }
        """)
        self.input_field.returnPressed.connect(self.send_message)
        inner.addWidget(self.input_field)

        self.send_btn = QPushButton("➤")
        self.send_btn.setFixedSize(42, 42)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #4935e8;
                border: 1px solid #735dff;
                border-radius: 21px;
                color: white;
                font-size: 20px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #634cff; }
            QPushButton:disabled {
                background-color: #20294a;
                color: #647091;
                border-color: #2c3758;
            }
        """)
        self.send_btn.clicked.connect(self.send_message)
        inner.addWidget(self.send_btn)

        layout.addWidget(frame)
        return layout

    def _mic_btn_style(self, recording: bool):
        if recording:
            return """
                QPushButton {
                    background: transparent;
                    color: #ff5d83;
                    border: none;
                    font-size: 20px;
                }
                QPushButton:hover { color: #ff7a9a; }
            """
        return """
            QPushButton {
                background: transparent;
                color: #8b96b6;
                border: none;
                font-size: 17px;
            }
            QPushButton:hover { color: #45aaff; }
        """

    def _mic_btn_style_dialog(self):
        return """
            QPushButton {
                background: transparent;
                color: #89b4fa;
                border: none;
                font-size: 18px;
            }
            QPushButton:hover { color: #a8c7ff; }
        """

    # ========== FOOTER ==========
    def _create_status_bar(self):
        bar = QFrame()
        bar.setFixedHeight(26)
        bar.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(6, 0, 6, 0)

        self.status_info = QLabel("✓  Готов")
        self.status_info.setStyleSheet("color: #45eeb0; font-size: 13px; background: transparent;")
        layout.addWidget(self.status_info)
        layout.addStretch()

        self.msg_count_label = QLabel("💬 0")
        self.msg_count_label.setStyleSheet("color: #d4b3ff; font-size: 13px; background: transparent;")
        layout.addWidget(self.msg_count_label)

        separator = QFrame()
        separator.setFixedSize(1, 18)
        separator.setStyleSheet("background-color: #334268;")
        layout.addWidget(separator)

        self.voice_toggle_btn = QPushButton("🔊" if self.voice_enabled else "🔇")
        self.voice_toggle_btn.setFixedSize(32, 24)
        self.voice_toggle_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #cbd4ef;
                border: none;
                font-size: 16px;
            }
            QPushButton:hover { color: #6bb8ff; }
        """)
        self.voice_toggle_btn.clicked.connect(self.toggle_voice)
        layout.addWidget(self.voice_toggle_btn)
        return bar

    # ========== CHAT ==========
    def _insert_message(self, sender: str, text: str, time_text: Optional[str] = None):
        if self.chat_layout.count():
            item = self.chat_layout.takeAt(self.chat_layout.count() - 1)
            if item.widget():
                item.widget().setParent(None)

        message = MessageWidget(sender, text, time_text, self.chat_container)
        self.chat_layout.addWidget(message)
        self.chat_layout.addStretch()
        self._messages.append(message)
        self._message_count += 1
        self.msg_count_label.setText(f"💬 {self._message_count}")
        QTimer.singleShot(50, self._scroll_to_bottom)
        return message

    def _scroll_to_bottom(self):
        scrollbar = self.chat_scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def load_chat_history(self):
        """
        ИСПРАВЛЕНО: НЕ удаляем историю из БД.
        Читаем последние 20 сообщений и выводим их.
        Если истории нет — показываем приветствие.
        """
        self.chat_layout.addStretch()

        history = []
        try:
            history = get_history(limit=20)
        except Exception as e:
            print(f"⚠️ Не удалось загрузить историю: {e}")

        if history:
            for msg in history:
                role = "Zeta" if msg.get("role") == "assistant" else "Вы"
                content = msg.get("content", "")
                if content.strip():
                    self._insert_message(role, content)
            self._message_count = len(history)
            self.msg_count_label.setText(f"💬 {self._message_count}")
        else:
            self._insert_message(
                "Zeta",
                "Привет! Я Zeta. Чем могу помочь? 😊\n\n"
                "💡 Кнопки:\n"
                "   💻 Dev — режим разработчика\n"
                "   📅 План — задачи, встречи, рутины\n"
                "   🤖 Авто — автоматизация\n"
                "   🌐 Сеть — управление устройствами\n"
                "   🎤 — выбор голосового режима\n"
                "   🎯 Wake — активация по слову"
            )

        self._set_status("✓  Готов", "success")

    # ========== STREAMING ==========
    def send_message(self):
        text = self.input_field.text().strip()
        if not text:
            return

        if self._wake_enabled:
            try:
                ww = get_wake_word()
                ww.pause()
            except Exception:
                pass

        self.input_field.clear()
        self._insert_message("Вы", text)
        self._stream_message = self._insert_message("Zeta", "…")

        self.typing_label.show()
        self._typing_dots = 0
        self._typing_timer.start(400)
        self.send_btn.setEnabled(False)
        self.send_btn.setText("…")
        self._set_status("⏳  Z думает...", "warning")

        self.worker = ZetaWorker(text)
        self.worker.set_voice_enabled(self.voice_enabled)

        self.worker.chunk_ready.connect(self._on_chunk)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.thinking.connect(self._on_thinking)
        self.worker.start()

    def _on_chunk(self, full_text: str):
        if self._stream_message:
            self._stream_message.setText(full_text)
        QTimer.singleShot(20, self._scroll_to_bottom)

    def _on_finished(self, full_text: str):
        self._typing_timer.stop()
        self.typing_label.hide()
        self.send_btn.setEnabled(True)
        self.send_btn.setText("➤")
        self._set_status("✓  Готов", "success")
        self._stream_message = None

        if self._wake_enabled:
            try:
                ww = get_wake_word()
                ww.resume()
            except Exception:
                pass

        if self._voice_mode == "dialog":
            self._schedule_dialog_listen()

    def _on_error(self, error_msg: str):
        self._typing_timer.stop()
        self.typing_label.hide()
        self.send_btn.setEnabled(True)
        self.send_btn.setText("➤")
        if self._stream_message:
            self._stream_message.setText(error_msg)
        self._set_status("⚠️  Ошибка", "danger")
        self._stream_message = None

    def _on_thinking(self, is_thinking: bool):
        if is_thinking:
            self._typing_timer.start(400)
            self.typing_label.show()
        else:
            self._typing_timer.stop()
            self.typing_label.hide()

    def _update_typing_animation(self):
        self._typing_dots = (self._typing_dots + 1) % 4
        dots = "." * self._typing_dots
        self.typing_label.setText(f"Zeta печатает{dots}")

    # ========== ФОТО ==========
    def open_photo(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выбери изображение",
            "",
            "Изображения (*.png *.jpg *.jpeg *.gif *.bmp *.webp)"
        )
        if not path:
            return
        self.analyze_photo(path)

    def analyze_photo(self, path: str, question: str = None):
        if not HAS_IMAGE_HANDLER:
            self._insert_message("Zeta", "⚠️ Модуль обработки изображений не установлен.")
            return

        file_name = Path(path).name
        self._insert_message("Вы", f"📷 Отправлено фото: {file_name}")

        self._set_status(f"📸  Смотрю на фото...", "info")
        self.typing_label.setText("Zeta смотрит на фото...")
        self.typing_label.show()
        self._typing_timer.stop()

        self._stream_message = self._insert_message("Zeta", "🖼️ Анализирую...")

        self.image_worker = ImageWorker(path, question)
        self.image_worker.finished.connect(self._on_photo_finished)
        self.image_worker.error.connect(self._on_photo_error)
        self.image_worker.start()

    def _on_photo_finished(self, answer: str):
        self.typing_label.hide()
        self._set_status("✓  Готово", "success")
        if self._stream_message:
            self._stream_message.setText(f"🖼️ {answer}")
            self._stream_message = None

        if self.voice_enabled and answer.strip():
            def speak_async():
                try:
                    speak(answer)
                except Exception:
                    pass
            threading.Thread(target=speak_async, daemon=True).start()

    def _on_photo_error(self, error: str):
        self.typing_label.hide()
        self._set_status("⚠️  Ошибка", "danger")
        if self._stream_message:
            self._stream_message.setText(error)
            self._stream_message = None

    # ========== WAKE WORD ==========
    def toggle_wake_word(self):
        if not HAS_WAKE:
            self._insert_message(
                "Zeta",
                "⚠️ Wake Word не установлен.\n\n"
                "Установите:\n"
                "pip install openwakeword onnxruntime"
            )
            self._set_status("⚠️  Wake Word не установлен", "warning")
            return

        if self._wake_enabled:
            self.stop_wake_word()
        else:
            self.start_wake_word()

    def start_wake_word(self):
        if self._wake_enabled:
            return

        ww = get_wake_word()
        if not ww.start(self._on_wake_word_detected, threshold=0.5):
            self._insert_message(
                "Zeta",
                "⚠️ Не удалось запустить Wake Word.\n"
                "Проверьте микрофон."
            )
            self._set_status("⚠️  Ошибка Wake Word", "danger")
            return

        self._wake_enabled = True
        save_setting("wake_word_enabled", "true")

        self._insert_message(
            "Zeta",
            "🎯 **Wake Word включён**\n"
            "Скажи «Hey Jarvis» — активируюсь."
        )
        self._set_status("🎯  Wake Word слушает...", "info")

    def stop_wake_word(self):
        if not self._wake_enabled:
            return

        ww = get_wake_word()
        ww.stop()

        self._wake_enabled = False
        save_setting("wake_word_enabled", "false")

        self._insert_message("Zeta", "🎯 Wake Word выключен.")
        self._set_status("✓  Готов", "success")

    def _on_wake_word_detected(self, name: str, score: float):
        QTimer.singleShot(0, lambda: self._handle_wake_activation(name, score))

    def _handle_wake_activation(self, name: str, score: float):
        """
        ИСПРАВЛЕНО: если уже в диалоговом режиме — не запускаем заново.
        """
        if self._voice_mode == "dialog":
            return

        self._insert_message("Zeta", "🎯 Услышала активацию! Говорите...")
        self._set_status("🎯  Слушаю...", "info")
        QTimer.singleShot(500, self.start_dialog_mode)

    # ========== ПЛАНИРОВЩИК ==========
    def open_scheduler(self):
        if self.scheduler_window is None or not self.scheduler_window.isVisible():
            self.scheduler_window = SchedulerWindow(self)

        self.scheduler_window.show()
        self.scheduler_window.raise_()
        self.scheduler_window.activateWindow()

    # ========== АВТОМАТИЗАЦИЯ ==========
    def open_automation(self):
        if self.automation_window is None or not self.automation_window.isVisible():
            self.automation_window = AutomationWindow(self)

        self.automation_window.show()
        self.automation_window.raise_()
        self.automation_window.activateWindow()

    # ========== УСТРОЙСТВА ==========
    def open_devices(self):
        if self.devices_window is None or not self.devices_window.isVisible():
            self.devices_window = DevicesWindow(self)

        self.devices_window.show()
        self.devices_window.raise_()
        self.devices_window.activateWindow()

    # ========== ГОЛОСОВОЙ ВВОД (STT) ==========
    def toggle_voice_input(self):
        """
        ИСПРАВЛЕНО: если активен диалоговый режим — корректно выходим и не запускаем меню.
        """
        if not HAS_STT:
            self._insert_message(
                "Zeta",
                "⚠️ Голосовой ввод не установлен.\n\n"
                "Установите:\n"
                "pip install sounddevice soundfile numpy SpeechRecognition"
            )
            self._set_status("⚠️  STT не установлен", "warning")
            return

        if self._voice_mode == "dialog":
            self._exit_dialog_mode("Кнопка 🎤")
            return

        if self._is_recording:
            self.stop_voice_input()
            return

        self.show_voice_menu()

    def show_voice_menu(self):
        menu = VoiceModeMenu(current_mode=self._voice_mode, parent=self)
        menu.mode_selected.connect(self._on_voice_mode_selected)
        menu.exec()

    def _on_voice_mode_selected(self, mode: str):
        self._voice_mode = mode

        if mode == "normal":
            self._set_status("🎤  Обычный режим", "info")
            self.start_normal_recording()
        elif mode == "dialog":
            self._set_status("🔄  Диалоговый режим", "info")
            self.start_dialog_mode()

    def start_normal_recording(self):
        if self._is_recording:
            return

        try:
            stt = get_stt()
            if not stt.start_recording():
                self._insert_message("Zeta", "⚠️ Не удалось начать запись.")
                return
        except Exception as e:
            self._insert_message("Zeta", f"⚠️ Ошибка: {e}")
            return

        self._is_recording = True
        self.mic_btn.setText("⏹️")
        self.mic_btn.setStyleSheet(self._mic_btn_style(True))
        self._set_status("🎤  Говорите... Нажми 🎤 чтобы остановить", "warning")

    def start_dialog_mode(self):
        """
        ИСПРАВЛЕНО: проверка, что диалог не запущен уже.
        """
        if self._voice_mode == "dialog":
            return

        self._voice_mode = "dialog"
        self.mic_btn.setText("🔄")
        self.mic_btn.setStyleSheet(self._mic_btn_style_dialog())
        self._insert_message(
            "Zeta",
            "🔄 **Диалоговый режим включён**\n"
            "Говорите — я слушаю. Молчание 3 сек = выход."
        )
        self._start_dialog_listening()

    def _start_dialog_listening(self):
        if self._voice_mode != "dialog":
            return

        self._set_status("🟢  Слушаю...", "info")
        self._is_recording = True

        self.dialog_worker = DialogVoiceWorker(
            max_duration=30,
            silence_duration=3.0
        )
        self.dialog_worker.finished.connect(self._on_dialog_recorded)
        self.dialog_worker.error.connect(self._on_dialog_error)
        self.dialog_worker.start()

    def _on_dialog_recorded(self, wav_path: str):
        self._is_recording = False

        if self._voice_mode != "dialog":
            return

        if not wav_path:
            self._exit_dialog_mode("Тишина")
            return

        self._set_status("🔄  Распознаю...", "info")

        self.voice_worker = VoiceWorker(wav_path)
        self.voice_worker.finished.connect(self._on_dialog_voice_result)
        self.voice_worker.error.connect(self._on_dialog_voice_error)
        self.voice_worker.start()

    def _on_dialog_voice_result(self, text: str):
        if self._voice_mode != "dialog":
            return

        if text:
            self._insert_message("Вы", f"🎤 {text}")
            self.input_field.setText(text)
            self.send_message()
        else:
            self._exit_dialog_mode("Не распознано")

    def _on_dialog_voice_error(self, error: str):
        if self._voice_mode != "dialog":
            return
        self._insert_message("Zeta", error)
        self._exit_dialog_mode("Ошибка")

    def _on_dialog_error(self, error: str):
        if self._voice_mode != "dialog":
            return
        self._insert_message("Zeta", error)
        self._exit_dialog_mode("Ошибка")

    def _schedule_dialog_listen(self):
        if self._voice_mode != "dialog":
            return
        QTimer.singleShot(2000, self._start_dialog_listening)

    def _exit_dialog_mode(self, reason: str = ""):
        if self._voice_mode != "dialog":
            return

        self._voice_mode = None
        self._is_recording = False
        self.mic_btn.setText("🎤")
        self.mic_btn.setStyleSheet(self._mic_btn_style(False))

        msg = "🔄 Диалог завершён"
        if reason:
            msg += f" ({reason})"

        self._set_status("✓  Готов", "success")
        self._insert_message("Zeta", msg)

    def stop_voice_input(self):
        if not self._is_recording:
            return

        if self._voice_mode == "dialog":
            self._exit_dialog_mode("Вручную")
            return

        self._is_recording = False
        self.mic_btn.setText("⏳")
        self.mic_btn.setEnabled(False)
        self._set_status("🔄  Распознаю...", "info")

        try:
            stt = get_stt()
            wav_path = stt.stop_recording()
        except Exception as e:
            self._insert_message("Zeta", f"⚠️ Ошибка: {e}")
            self._reset_mic_btn()
            return

        if not wav_path:
            self._insert_message("Zeta", "⚠️ Не удалось сохранить запись.")
            self._reset_mic_btn()
            return

        self.voice_worker = VoiceWorker(wav_path)
        self.voice_worker.finished.connect(self._on_voice_result)
        self.voice_worker.error.connect(self._on_voice_error)
        self.voice_worker.start()

    def _reset_mic_btn(self):
        self._is_recording = False
        self._voice_mode = None
        self.mic_btn.setText("🎤")
        self.mic_btn.setEnabled(True)
        self.mic_btn.setStyleSheet(self._mic_btn_style(False))

    def _on_voice_result(self, text: str):
        self._reset_mic_btn()

        if text:
            self._set_status(f"✅  Распознано", "success")
            self._insert_message("Вы", f"🎤 {text}")
            self.input_field.setText(text)
            self.send_message()
        else:
            self._set_status("⚠️  Не распознано", "warning")

    def _on_voice_error(self, error: str):
        self._reset_mic_btn()
        self._set_status("⚠️  Ошибка STT", "danger")
        self._insert_message("Zeta", error)

    # ========== DRAG-AND-DROP ==========
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            for url in urls:
                if url.isLocalFile():
                    ext = Path(url.toLocalFile()).suffix.lower()
                    if ext in SUPPORTED_FORMATS:
                        event.acceptProposedAction()
                        self._set_status("📷  Отпусти для анализа", "info")
                        return
        event.ignore()

    def dragLeaveEvent(self, event):
        self._set_status("✓  Готов", "success")

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = url.toLocalFile()
                ext = Path(path).suffix.lower()
                if ext in SUPPORTED_FORMATS:
                    event.acceptProposedAction()
                    self.analyze_photo(path)
                    return
        self._set_status("⚠️  Неподдерживаемый файл", "warning")

    # ========== STATUS ==========
    def _set_status(self, text: str, level: str = "info"):
        colors = {
            "success": "#45eeb0",
            "warning": "#ffc766",
            "danger": "#ff668b",
            "info": "#55aaff",
        }
        color = colors.get(level, "#8d98b8")
        self.status_info.setText(text)
        self.status_info.setStyleSheet(f"color: {color}; font-size: 13px; background: transparent;")

    # ========== FUNCTIONS ==========
    def focus_chat(self):
        self.input_field.setFocus()

    def take_screenshot(self):
        try:
            from core.screen_capture import take_screenshot
            result = take_screenshot()
            if result:
                self._insert_message("Zeta", "📸 Скриншот сделан. Проверьте папку data/screenshots")
            else:
                self._insert_message("Zeta", "⚠️ Не удалось сделать скриншот")
        except Exception as e:
            self._insert_message("Zeta", f"⚠️ Ошибка: {e}")

    def show_facts(self):
        try:
            from core.memory import get_facts
            facts = get_facts()
            if facts:
                text = "🧠 <b>Факты о вас:</b><br><br>"
                for fact in facts:
                    text += f"• <b>{html.escape(str(fact['key']))}</b>: {html.escape(str(fact['content']))}<br>"
                self._insert_message("Zeta", text)
            else:
                self._insert_message("Zeta", "🧠 У меня пока нет фактов о вас.")
        except Exception as e:
            self._insert_message("Zeta", f"⚠️ Ошибка: {e}")

    def open_explorer(self):
        try:
            os.startfile("D:\\Zeta")
            self._set_status("📁  Проводник открыт", "info")
        except Exception as e:
            self._insert_message("Zeta", f"⚠️ Не удалось открыть Проводник: {e}")

    def set_reminder(self):
        text, ok = QInputDialog.getText(self, "⏰ Напоминание", "Что напомнить?")
        if not ok or not text:
            return
        minutes, ok = QInputDialog.getInt(self, "⏰ Напоминание", "Через сколько минут?", 1, 1, 1440)
        if not ok:
            return
        try:
            from modules.notifications import add_reminder
            result = add_reminder(text, minutes)
            self._insert_message("Zeta", result)
            self._set_status("⏰  Напоминание установлено", "success")
        except Exception as e:
            self._insert_message("Zeta", f"⚠️ Ошибка: {e}")

    # ========== VOICE ==========
    def toggle_voice(self):
        self.voice_enabled = not self.voice_enabled
        save_setting("voice_enabled", "true" if self.voice_enabled else "false")
        self.voice_toggle_btn.setText("🔊" if self.voice_enabled else "🔇")
        self._set_status("🔊  Голос включён" if self.voice_enabled else "🔇  Голос выключен", "info")

    # ========== COLLAPSE ==========
    def toggle_collapse(self):
        self._is_collapsed = not self._is_collapsed
        if self._is_collapsed:
            self.setFixedHeight(120)
            self.section_bar.hide()
            self.chat_frame.hide()
            self.typing_label.hide()
            self.input_field.hide()
            self.send_btn.hide()
            self.attach_btn.hide()
            self.mic_btn.hide()
            self.collapse_btn.setText("+")
        else:
            self.setFixedHeight(self.widget_height)
            self.section_bar.show()
            self.chat_frame.show()
            self.input_field.show()
            self.send_btn.show()
            self.attach_btn.show()
            self.mic_btn.show()
            self.collapse_btn.setText("−")

    # ========== SETTINGS ==========
    def open_settings(self):
        if self.settings_window is None or not self.settings_window.isVisible():
            self.settings_window = SettingsWindow()
            self.settings_window.settings_changed.connect(self.apply_settings)
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def apply_settings(self):
        """
        ИСПРАВЛЕНО: обновляем размер виджета, если пользователь поменял в настройках.
        """
        self.voice_enabled = get_setting("voice_enabled", "true") == "true"
        try:
            self.widget_opacity = float(get_setting("widget_opacity", "1.0"))
        except Exception:
            self.widget_opacity = 1.0

        size_key = get_setting("widget_size", "M")
        new_w, new_h = SIZE_MAP.get(size_key, SIZE_MAP["M"])
        if (new_w, new_h) != (self.widget_width, self.widget_height):
            self.widget_width, self.widget_height = new_w, new_h
            self.setFixedSize(new_w, new_h)
            self.main_frame.setGeometry(0, 0, new_w, new_h)

        self.apply_opacity()
        self.voice_toggle_btn.setText("🔊" if self.voice_enabled else "🔇")

    def apply_opacity(self):
        self.setWindowOpacity(self.widget_opacity)

    # ========== PROGRAMMER MODE (он же DEV) ==========
    def open_programmer_mode(self):
        """Открыть окно режима разработчика (ProgrammerWindow)."""
        if self.programmer_window is None or not self.programmer_window.isVisible():
            self.programmer_window = ProgrammerWindow(self.theme_name)
            self.programmer_window.show()
        else:
            self.programmer_window.raise_()
            self.programmer_window.activateWindow()

    # ========== HOTKEYS ==========
    def setup_hotkeys(self):
        shortcuts = [
            ("Ctrl+Shift+Z", self.show_and_focus),
            ("Ctrl+Shift+S", self.show_system_status),
            ("Ctrl+Shift+P", self.open_photo),
            ("Ctrl+Shift+V", self.toggle_voice_input),
            ("Ctrl+Shift+W", self.toggle_wake_word),
            ("Ctrl+Shift+D", self.open_scheduler),
            ("Ctrl+Shift+A", self.open_automation),
            ("Ctrl+Shift+N", self.open_devices),
            ("Ctrl+Shift+F", self.focus_chat),          # ← НОВЫЙ: фокус на чат
            ("Ctrl+Shift+X", self.open_programmer_mode), # ← НОВЫЙ: режим разработчика
            ("Ctrl+L", self.clear_chat),
            ("Ctrl+W", self.close),
            ("Ctrl+Shift+O", self.open_settings),
        ]
        for key, callback in shortcuts:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(callback)

    # ========== SYSTEM STATUS ==========
    def show_system_status(self):
        try:
            from modules.system_monitor import get_system_status
            status = get_system_status()
            self._insert_message("Zeta", status)
            self._set_status("📊  Статус показан", "info")
        except Exception as e:
            self._insert_message("Zeta", f"⚠️ Ошибка получения статуса: {e}")

    # ========== CLEAR CHAT ==========
    def clear_chat(self):
        while self.chat_layout.count():
            item = self.chat_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._messages.clear()
        self._message_count = 0
        self.msg_count_label.setText("💬 0")
        self.chat_layout.addStretch()

        try:
            clear_history()
        except Exception:
            pass

        self._insert_message("Zeta", "Привет! Я Zeta. Чем могу помочь? 😊")
        self._set_status("🗑️  Чат очищен", "warning")

    # ========== SHOW / FOCUS ==========
    def show_and_focus(self):
        if self._is_collapsed:
            self.toggle_collapse()
        self.show()
        self.raise_()
        self.activateWindow()
        if self.auto_focus:
            self.input_field.setFocus()

    # ========== TRAY ==========
    def setup_tray(self):
        try:
            if not QSystemTrayIcon.isSystemTrayAvailable():
                self.tray_icon = None
                return
            self.tray_icon = QSystemTrayIcon(self)
            self.tray_icon.setIcon(create_app_icon())
            self.tray_icon.setToolTip("Zeta")
            menu = QMenu()
            show_action = QAction("Показать Zeta", self)
            show_action.triggered.connect(self.show_and_focus)
            menu.addAction(show_action)
            menu.addSeparator()
            status_action = QAction("📊 Статус", self)
            status_action.triggered.connect(self.show_system_status)
            menu.addAction(status_action)
            photo_action = QAction("📷 Отправить фото", self)
            photo_action.triggered.connect(self.open_photo)
            menu.addAction(photo_action)
            voice_action = QAction("🎤 Голосовой ввод", self)
            voice_action.triggered.connect(self.toggle_voice_input)
            menu.addAction(voice_action)
            wake_action = QAction("🎯 Wake Word", self)
            wake_action.triggered.connect(self.toggle_wake_word)
            menu.addAction(wake_action)
            plan_action = QAction("📅 Планировщик", self)
            plan_action.triggered.connect(self.open_scheduler)
            menu.addAction(plan_action)
            auto_action = QAction("🤖 Автоматизация", self)
            auto_action.triggered.connect(self.open_automation)
            menu.addAction(auto_action)
            devices_action = QAction("🌐 Устройства", self)
            devices_action.triggered.connect(self.open_devices)
            menu.addAction(devices_action)
            # ИСПРАВЛЕНО: "Режим программиста" → "Режим разработчика"
            programmer_action = QAction("💻 Режим разработчика", self)
            programmer_action.triggered.connect(self.open_programmer_mode)
            menu.addAction(programmer_action)
            menu.addSeparator()
            quit_action = QAction("Выйти", self)
            quit_action.triggered.connect(self.quit_app)
            menu.addAction(quit_action)
            self.tray_icon.setContextMenu(menu)
            self.tray_icon.show()
            self.tray_icon.activated.connect(self._tray_activated)
        except Exception:
            self.tray_icon = None

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_and_focus()

    def quit_app(self):
        reply = QMessageBox.question(
            self, "Выход", "Закрыть Zeta?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            QApplication.quit()

    # ========== POSITION ==========
    def position_widget(self):
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.right() - self.widget_width - 25
        y = screen.bottom() - self.widget_height - 25
        self.move(max(screen.left(), x), max(screen.top(), y))

    def load_position(self):
        try:
            x = int(get_setting("widget_x", ""))
            y = int(get_setting("widget_y", ""))

            screen = QApplication.primaryScreen().availableGeometry()

            in_bounds = (
                screen.left() <= x <= screen.right() - self.widget_width and
                screen.top() <= y <= screen.bottom() - self.widget_height
            )

            if in_bounds:
                self.move(x, y)
            else:
                self.position_widget()
        except (ValueError, TypeError):
            self.position_widget()

    def save_position(self):
        pos = self.pos()
        save_setting("widget_x", str(pos.x()))
        save_setting("widget_y", str(pos.y()))

    # ========== DRAG WINDOW ==========
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
        elif event.button() == Qt.MouseButton.MiddleButton:
            self.close()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        self.save_position()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_collapse()

    # ========== CLOSE ==========
    def closeEvent(self, event):
        if self._is_recording:
            try:
                stt = get_stt()
                stt.cancel_recording()
            except Exception:
                pass

        if self._wake_enabled:
            try:
                ww = get_wake_word()
                ww.stop()
            except Exception:
                pass

        self._voice_mode = None
        self.save_position()

        if getattr(self, "tray_icon", None):
            self.hide()
            event.ignore()
        else:
            event.accept()


# ========== ЗАПУСК ==========
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    window = ZetaWidget()
    window.show()
    sys.exit(app.exec())