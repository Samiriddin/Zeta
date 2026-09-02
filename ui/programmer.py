# -*- coding: utf-8 -*-
"""
Окно режима программиста Zeta.
Поддерживает: чат с кодом, дерево проекта, редактор кода, консоль, терминал,
Git-граф, авто-коммит, автодополнение, линтер, запуск файлов.
"""

import os
import subprocess
import re
import ast
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QLineEdit, QFrame,
    QListWidget, QSplitter, QTreeWidget, QTreeWidgetItem,
    QProgressBar, QMessageBox, QMenu, QApplication,
    QFileDialog, QPlainTextEdit, QStatusBar, QTextBrowser,
    QScrollArea, QTabWidget, QInputDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QProcess
from PyQt6.QtGui import (
    QTextCursor, QTextCharFormat, QColor, QFont, QAction,
    QSyntaxHighlighter, QTextFormat, QPainter, QKeySequence
)

from core.ai_engine import ask_zeta
from core.memory import get_setting, save_setting
from voice.tts import speak
from modules.project_context import scan_project, get_file_tree, get_current_project_path

# ========== ТЕМЫ ==========
THEMES = {
    "dark": {
        "frame_bg": "#1e1e2e",
        "frame_border": "#313244",
        "text": "#cdd6f4",
        "chat_bg": "#181825",
        "input_bg": "#313244",
        "accent": "#89b4fa",
        "accent_hover": "#74c7ec",
        "accent_text": "#1e1e2e",
        "close_bg": "#f38ba8",
        "close_hover": "#e06c75",
        "success": "#a6e3a1",
        "warning": "#f9e2af",
        "danger": "#f38ba8",
        "info": "#89b4fa",
        "code_bg": "#1e1e2e",
        "console_bg": "#1e1e2e",
    },
    "light": {
        "frame_bg": "#eff1f5",
        "frame_border": "#ccd0da",
        "text": "#4c4f69",
        "chat_bg": "#e6e9ef",
        "input_bg": "#dce0e8",
        "accent": "#1e66f5",
        "accent_hover": "#04a5e5",
        "accent_text": "#eff1f5",
        "close_bg": "#d20f39",
        "close_hover": "#e64553",
        "success": "#40a02b",
        "warning": "#df8e1d",
        "danger": "#d20f39",
        "info": "#1e66f5",
        "code_bg": "#e0e0e0",
        "console_bg": "#f0f0f0",
    },
}

# ========== ЦВЕТА ПОДСВЕТКИ ==========
SYNTAX_COLORS = {
    "python": {
        "keyword": "#c678dd",
        "string": "#98c379",
        "comment": "#5c6370",
        "function": "#61afef",
        "number": "#d19a66",
    },
    "javascript": {
        "keyword": "#c678dd",
        "string": "#98c379",
        "comment": "#5c6370",
        "function": "#61afef",
        "number": "#d19a66",
    },
    "html": {
        "tag": "#e06c75",
        "attribute": "#d19a66",
        "string": "#98c379",
    },
    "css": {
        "property": "#c678dd",
        "value": "#98c379",
        "selector": "#61afef",
    },
}


# ========== ПОДСВЕТКА СИНТАКСИСА (PYQT) ==========
class PythonHighlighter(QSyntaxHighlighter):
    """Подсветка синтаксиса Python для редактора кода."""

    def __init__(self, document):
        super().__init__(document)
        self.keyword_format = QTextCharFormat()
        self.keyword_format.setForeground(QColor("#c678dd"))
        self.keyword_format.setFontWeight(QFont.Weight.Bold)

        self.string_format = QTextCharFormat()
        self.string_format.setForeground(QColor("#98c379"))

        self.comment_format = QTextCharFormat()
        self.comment_format.setForeground(QColor("#5c6370"))
        self.comment_format.setFontItalic(True)

        self.function_format = QTextCharFormat()
        self.function_format.setForeground(QColor("#61afef"))

        self.number_format = QTextCharFormat()
        self.number_format.setForeground(QColor("#d19a66"))

        self.keywords = [
            "def", "class", "return", "if", "elif", "else", "for", "while",
            "import", "from", "try", "except", "finally", "with", "as", "pass",
            "break", "continue", "lambda", "yield", "global", "nonlocal",
            "True", "False", "None", "async", "await", "in", "is", "not", "and", "or"
        ]

    def highlightBlock(self, text):
        # Комментарии
        self.setCurrentBlockState(0)
        comment_index = text.find("#")
        if comment_index >= 0:
            self.setFormat(comment_index, len(text) - comment_index, self.comment_format)

        # Строки
        string_pattern = re.compile(r'(["\'])(.*?)\1')
        for match in string_pattern.finditer(text):
            self.setFormat(match.start(), len(match.group()), self.string_format)

        # Ключевые слова
        for keyword in self.keywords:
            pattern = re.compile(rf'\b{keyword}\b')
            for match in pattern.finditer(text):
                self.setFormat(match.start(), len(keyword), self.keyword_format)

        # Числа
        number_pattern = re.compile(r'\b\d+\b')
        for match in number_pattern.finditer(text):
            self.setFormat(match.start(), len(match.group()), self.number_format)

        # Функции
        func_pattern = re.compile(r'\b(\w+)(?=\s*\()')
        for match in func_pattern.finditer(text):
            self.setFormat(match.start(), len(match.group(1)), self.function_format)


# ========== ПОТОК ДЛЯ ОТВЕТОВ ==========
class ProgWorker(QThread):
    chunk_ready = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, message: str):
        super().__init__()
        self.message = message
        self._full = ""

    def run(self):
        try:
            for chunk in ask_zeta(self.message, mode="programmer"):
                self._full += chunk
                self.chunk_ready.emit(self._full)
            self.finished.emit(self._full)
        except Exception as e:
            self.error.emit(f"⚠️ Ошибка: {str(e)}")


# ========== ПОТОК ДЛЯ ВЫПОЛНЕНИЯ ==========
class RunProcess(QThread):
    output_ready = pyqtSignal(str)
    finished_process = pyqtSignal(int)

    def __init__(self, command: str, cwd: str = None):
        super().__init__()
        self.command = command
        self.cwd = cwd

    def run(self):
        try:
            process = QProcess()
            process.setWorkingDirectory(self.cwd or os.getcwd())
            process.start("cmd", ["/c", self.command])
            process.waitForFinished()
            
            output = process.readAllStandardOutput().data().decode('utf-8', errors='replace')
            error = process.readAllStandardError().data().decode('utf-8', errors='replace')
            
            if output:
                self.output_ready.emit(output)
            if error:
                self.output_ready.emit(f"⚠️ Ошибка: {error}")
            
            self.finished_process.emit(process.exitCode())
        except Exception as e:
            self.output_ready.emit(f"⚠️ Ошибка: {e}")


# ========== ПОТОК ДЛЯ АВТОДОПОЛНЕНИЯ ==========
class AutoCompleteWorker(QThread):
    result_ready = pyqtSignal(str)

    def __init__(self, code: str, context: str = ""):
        super().__init__()
        self.code = code
        self.context = context

    def run(self):
        try:
            prompt = (
                "Продолжи этот код. Верни только код, без объяснений.\n\n"
                f"Текущий код:\n```python\n{self.code}\n```"
            )
            result = ask_zeta(prompt, mode="programmer")
            self.result_ready.emit(result)
        except Exception as e:
            self.result_ready.emit(f"⚠️ Ошибка: {e}")


# ========== ГЛАВНОЕ ОКНО ==========
class ProgrammerWindow(QWidget):
    """Окно режима программиста Zeta."""

    def __init__(self, theme_name: str = "dark"):
        super().__init__()
        self.theme_name = theme_name
        self.theme = THEMES.get(theme_name, THEMES["dark"])
        self.worker: Optional[ProgWorker] = None
        self.run_process: Optional[RunProcess] = None
        self.auto_complete_worker: Optional[AutoCompleteWorker] = None
        self._z_block_start = None
        self.project_path = get_current_project_path() or "D:\\Zeta"
        self.file_tree_items: Dict[str, QTreeWidgetItem] = {}
        self.current_file_path = None

        self.setWindowTitle("💻 Z — Режим программиста")
        self.setGeometry(100, 80, 1400, 850)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowMinimizeButtonHint |
            Qt.WindowType.WindowMaximizeButtonHint
        )
        self.setStyleSheet(f"background-color: {self.theme['frame_bg']}; color: {self.theme['text']};")

        self.init_ui()
        self.load_project_tree()
        self.greet()

    # ========== UI ==========

    def init_ui(self):
        """Создаёт интерфейс."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Верхняя панель инструментов
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self.btn_save = QPushButton("💾 Сохранить")
        self.btn_save.setFixedSize(100, 30)
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setStyleSheet(self._btn_style())
        self.btn_save.clicked.connect(self.save_current_file)
        toolbar.addWidget(self.btn_save)

        self.btn_run = QPushButton("▶️ Запустить")
        self.btn_run.setFixedSize(100, 30)
        self.btn_run.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_run.setStyleSheet(self._btn_style())
        self.btn_run.clicked.connect(self.run_current_file)
        toolbar.addWidget(self.btn_run)

        self.btn_open = QPushButton("📂 Открыть файл")
        self.btn_open.setFixedSize(120, 30)
        self.btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open.setStyleSheet(self._btn_style())
        self.btn_open.clicked.connect(self.open_file_dialog)
        toolbar.addWidget(self.btn_open)

        self.btn_vscode = QPushButton("🧩 Открыть в VS Code")
        self.btn_vscode.setFixedSize(140, 30)
        self.btn_vscode.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_vscode.setStyleSheet(self._btn_style())
        self.btn_vscode.clicked.connect(self.open_in_vscode)
        toolbar.addWidget(self.btn_vscode)

        self.btn_lint = QPushButton("🔍 Проверить код")
        self.btn_lint.setFixedSize(120, 30)
        self.btn_lint.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_lint.setStyleSheet(self._btn_style())
        self.btn_lint.clicked.connect(self.lint_code)
        toolbar.addWidget(self.btn_lint)

        toolbar.addStretch()

        self.btn_auto_commit = QPushButton("🤖 Авто-коммит")
        self.btn_auto_commit.setFixedSize(120, 30)
        self.btn_auto_commit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_auto_commit.setStyleSheet(self._btn_style())
        self.btn_auto_commit.clicked.connect(self.auto_commit)
        toolbar.addWidget(self.btn_auto_commit)

        self.btn_clear_chat = QPushButton("🗑️ Очистить чат")
        self.btn_clear_chat.setFixedSize(120, 30)
        self.btn_clear_chat.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_chat.setStyleSheet(self._btn_style())
        self.btn_clear_chat.clicked.connect(self.clear_chat)
        toolbar.addWidget(self.btn_clear_chat)

        self.btn_clear_console = QPushButton("🧹 Очистить консоль")
        self.btn_clear_console.setFixedSize(130, 30)
        self.btn_clear_console.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_console.setStyleSheet(self._btn_style())
        self.btn_clear_console.clicked.connect(self.clear_console)
        toolbar.addWidget(self.btn_clear_console)

        layout.addLayout(toolbar)

        # Основной сплиттер
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ===== ЛЕВАЯ ПАНЕЛЬ: Дерево проекта =====
        left_frame = self._create_left_panel()
        splitter.addWidget(left_frame)

        # ===== ЦЕНТР: Чат + Редактор + Консоль + Терминал =====
        center_frame = self._create_center_panel()
        splitter.addWidget(center_frame)

        # ===== ПРАВАЯ ПАНЕЛЬ: Инструменты и Git =====
        right_frame = self._create_right_panel()
        splitter.addWidget(right_frame)

        splitter.setSizes([250, 550, 250])
        layout.addWidget(splitter)

        # Статус-бар
        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet(f"background-color: {self.theme['frame_bg']}; color: {self.theme['text']};")
        self.status_bar.showMessage("✅ Готов")
        layout.addWidget(self.status_bar)

    def _create_left_panel(self) -> QFrame:
        """Создаёт левую панель с деревом проекта."""
        frame = QFrame()
        frame.setMinimumWidth(200)
        frame.setMaximumWidth(320)
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {self.theme['frame_bg']};
                border-radius: 10px;
                border: 1px solid {self.theme['frame_border']};
            }}
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Заголовок
        title_layout = QHBoxLayout()
        title = QLabel("📁 Проект")
        title.setStyleSheet(f"color: {self.theme['text']}; font-weight: bold; font-size: 13px;")
        title_layout.addWidget(title)

        # Путь к проекту
        self.path_label = QLabel(self.project_path)
        self.path_label.setStyleSheet(f"color: {self.theme['text']}; font-size: 10px; opacity: 0.7;")
        self.path_label.setWordWrap(True)
        title_layout.addWidget(self.path_label)
        title_layout.addStretch()

        layout.addLayout(title_layout)

        # Дерево файлов
        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderHidden(True)
        self.file_tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {self.theme['chat_bg']};
                color: {self.theme['text']};
                border-radius: 8px;
                border: none;
                font-size: 12px;
                padding: 4px;
            }}
            QTreeWidget::item:hover {{
                background-color: {self.theme['input_bg']};
            }}
            QTreeWidget::item:selected {{
                background-color: {self.theme['accent']};
                color: {self.theme['accent_text']};
            }}
        """)
        self.file_tree.itemDoubleClicked.connect(self.on_file_double_click)
        layout.addWidget(self.file_tree)

        # Кнопки управления деревом
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)

        self.btn_refresh = QPushButton("🔄")
        self.btn_refresh.setFixedSize(32, 32)
        self.btn_refresh.setToolTip("Обновить дерево")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setStyleSheet(self._btn_style())
        self.btn_refresh.clicked.connect(self.load_project_tree)
        btn_layout.addWidget(self.btn_refresh)

        self.btn_expand = QPushButton("➕")
        self.btn_expand.setFixedSize(32, 32)
        self.btn_expand.setToolTip("Развернуть всё")
        self.btn_expand.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_expand.setStyleSheet(self._btn_style())
        self.btn_expand.clicked.connect(self.expand_all)
        btn_layout.addWidget(self.btn_expand)

        self.btn_collapse = QPushButton("➖")
        self.btn_collapse.setFixedSize(32, 32)
        self.btn_collapse.setToolTip("Свернуть всё")
        self.btn_collapse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_collapse.setStyleSheet(self._btn_style())
        self.btn_collapse.clicked.connect(self.collapse_all)
        btn_layout.addWidget(self.btn_collapse)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Прогресс-бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {self.theme['input_bg']};
                border-radius: 4px;
                height: 6px;
                text-align: center;
            }}
            QProgressBar::chunk {{
                background-color: {self.theme['accent']};
                border-radius: 4px;
            }}
        """)
        layout.addWidget(self.progress_bar)

        return frame

    def _create_center_panel(self) -> QFrame:
        """Создаёт центральную панель с чатом, редактором, консолью и терминалом."""
        frame = QFrame()
        frame.setMinimumWidth(500)
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {self.theme['frame_bg']};
                border-radius: 10px;
                border: 1px solid {self.theme['frame_border']};
            }}
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Вкладки
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                background: {self.theme['frame_bg']};
                border-radius: 8px;
                padding: 4px;
            }}
            QTabBar::tab {{
                background: {self.theme['input_bg']};
                color: {self.theme['text']};
                padding: 6px 12px;
                border-radius: 6px;
                margin-right: 4px;
            }}
            QTabBar::tab:selected {{
                background: {self.theme['accent']};
                color: {self.theme['accent_text']};
            }}
        """)
        layout.addWidget(self.tabs)

        # Вкладка 1: Чат
        chat_tab = QWidget()
        chat_layout = QVBoxLayout(chat_tab)
        chat_layout.setContentsMargins(4, 4, 4, 4)
        chat_layout.setSpacing(6)

        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.chat_display.setStyleSheet(f"""
            QTextEdit {{
                background-color: {self.theme['chat_bg']};
                color: {self.theme['text']};
                border-radius: 8px;
                border: none;
                font-size: 13px;
                padding: 8px;
                font-family: 'Segoe UI', Consolas, monospace;
            }}
        """)
        chat_layout.addWidget(self.chat_display, stretch=1)

        self.typing_label = QLabel("🤔 Z думает...")
        self.typing_label.setStyleSheet(f"color: {self.theme['text']}; font-size: 11px; padding: 4px;")
        self.typing_label.hide()
        chat_layout.addWidget(self.typing_label)

        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Напиши задачу, вопрос по коду или просто поговори...")
        self.input_field.setStyleSheet(f"""
            QLineEdit {{
                background-color: {self.theme['input_bg']};
                color: {self.theme['text']};
                border-radius: 8px;
                border: none;
                padding: 8px 12px;
                font-size: 13px;
            }}
        """)
        self.input_field.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.input_field)

        self.send_btn = QPushButton("➤")
        self.send_btn.setFixedSize(38, 38)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setStyleSheet(f"""
            QPushButton {{
                background: {self.theme['accent']};
                color: {self.theme['accent_text']};
                border-radius: 8px;
                font-size: 16px;
                border: none;
            }}
        """)
        self.send_btn.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_btn)

        chat_layout.addLayout(input_layout)
        self.tabs.addTab(chat_tab, "💬 Чат")

        # Вкладка 2: Редактор кода
        editor_tab = QWidget()
        editor_layout = QVBoxLayout(editor_tab)
        editor_layout.setContentsMargins(4, 4, 4, 4)
        editor_layout.setSpacing(4)

        self.code_editor = QPlainTextEdit()
        self.code_editor.setPlaceholderText("Здесь можно писать код...")
        self.code_editor.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {self.theme['code_bg']};
                color: {self.theme['text']};
                border-radius: 8px;
                border: 1px solid {self.theme['frame_border']};
                font-family: 'Consolas', 'Segoe UI', monospace;
                font-size: 14px;
                padding: 8px;
            }}
        """)
        self.highlighter = PythonHighlighter(self.code_editor.document())
        editor_layout.addWidget(self.code_editor, stretch=1)

        editor_buttons = QHBoxLayout()
        self.btn_editor_save = QPushButton("💾 Сохранить")
        self.btn_editor_save.setFixedSize(100, 28)
        self.btn_editor_save.setStyleSheet(self._btn_style())
        self.btn_editor_save.clicked.connect(self.save_current_file)
        editor_buttons.addWidget(self.btn_editor_save)

        self.btn_editor_run = QPushButton("▶️ Запустить")
        self.btn_editor_run.setFixedSize(100, 28)
        self.btn_editor_run.setStyleSheet(self._btn_style())
        self.btn_editor_run.clicked.connect(self.run_current_file)
        editor_buttons.addWidget(self.btn_editor_run)

        self.btn_auto_complete = QPushButton("✨ Продолжить код")
        self.btn_auto_complete.setFixedSize(120, 28)
        self.btn_auto_complete.setStyleSheet(self._btn_style())
        self.btn_auto_complete.clicked.connect(self.auto_complete_code)
        editor_buttons.addWidget(self.btn_auto_complete)

        editor_buttons.addStretch()
        editor_layout.addLayout(editor_buttons)

        self.tabs.addTab(editor_tab, "📝 Редактор")

        # Вкладка 3: Консоль
        console_tab = QWidget()
        console_layout = QVBoxLayout(console_tab)
        console_layout.setContentsMargins(4, 4, 4, 4)
        console_layout.setSpacing(4)

        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet(f"""
            QTextEdit {{
                background-color: {self.theme['console_bg']};
                color: {self.theme['text']};
                border-radius: 8px;
                border: 1px solid {self.theme['frame_border']};
                font-family: 'Consolas', 'Segoe UI', monospace;
                font-size: 12px;
                padding: 8px;
            }}
        """)
        console_layout.addWidget(self.console, stretch=1)

        self.tabs.addTab(console_tab, "🖥️ Консоль")

        # Вкладка 4: Терминал
        terminal_tab = QWidget()
        terminal_layout = QVBoxLayout(terminal_tab)
        terminal_layout.setContentsMargins(4, 4, 4, 4)
        terminal_layout.setSpacing(4)

        self.terminal_output = QTextEdit()
        self.terminal_output.setReadOnly(True)
        self.terminal_output.setStyleSheet(f"""
            QTextEdit {{
                background-color: {self.theme['console_bg']};
                color: {self.theme['text']};
                border-radius: 8px;
                border: 1px solid {self.theme['frame_border']};
                font-family: 'Consolas', 'Segoe UI', monospace;
                font-size: 12px;
                padding: 8px;
            }}
        """)
        terminal_layout.addWidget(self.terminal_output, stretch=1)

        terminal_input_layout = QHBoxLayout()
        self.terminal_input = QLineEdit()
        self.terminal_input.setPlaceholderText("Введите команду (например: pip install requests)")
        self.terminal_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {self.theme['input_bg']};
                color: {self.theme['text']};
                border-radius: 8px;
                border: none;
                padding: 8px 12px;
                font-size: 13px;
                font-family: 'Consolas', monospace;
            }}
        """)
        self.terminal_input.returnPressed.connect(self.run_terminal_command)
        terminal_input_layout.addWidget(self.terminal_input)

        self.terminal_run_btn = QPushButton("▶️ Выполнить")
        self.terminal_run_btn.setFixedSize(100, 30)
        self.terminal_run_btn.setStyleSheet(self._btn_style())
        self.terminal_run_btn.clicked.connect(self.run_terminal_command)
        terminal_input_layout.addWidget(self.terminal_run_btn)

        terminal_layout.addLayout(terminal_input_layout)

        self.tabs.addTab(terminal_tab, "🖥️ Терминал")

        return frame

    def _create_right_panel(self) -> QFrame:
        """Создаёт правую панель с инструментами и Git."""
        frame = QFrame()
        frame.setMinimumWidth(200)
        frame.setMaximumWidth(280)
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {self.theme['frame_bg']};
                border-radius: 10px;
                border: 1px solid {self.theme['frame_border']};
            }}
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # Инструменты
        title = QLabel("🛠️ Инструменты")
        title.setStyleSheet(f"color: {self.theme['text']}; font-weight: bold; font-size: 13px;")
        layout.addWidget(title)

        tools = [
            ("🌐 Chrome", self.open_chrome),
            ("📝 VS Code", self.open_vscode),
            ("📁 Проводник", self.open_explorer),
            ("⚙️ Диспетчер", self.open_taskmgr),
            ("🖥️ Терминал", self.open_terminal),
            ("📋 Копировать", self.copy_code),
            ("📂 Открыть файл", self.open_selected_file),
        ]

        for label, callback in tools:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(self._btn_style())
            btn.clicked.connect(callback)
            layout.addWidget(btn)

        # Git секция
        layout.addSpacing(10)
        git_title = QLabel("🔧 Git")
        git_title.setStyleSheet(f"color: {self.theme['text']}; font-weight: bold; font-size: 13px;")
        layout.addWidget(git_title)

        git_tools = [
            ("📊 Статус", self.git_status),
            ("📈 Логи", self.git_log),
            ("📝 Дифф", self.git_diff),
            ("💾 Коммит", self.git_commit),
            ("🤖 Авто-коммит", self.auto_commit),
            ("🌿 Ветки", self.git_branch),
            ("📦 Stash", self.git_stash),
            ("🔄 Pull", self.git_pull),
        ]

        for label, callback in git_tools:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(self._btn_style())
            btn.clicked.connect(callback)
            layout.addWidget(btn)

        layout.addStretch()

        # Информация
        info_label = QLabel("💡 Двойной клик по файлу → открыть в редакторе")
        info_label.setStyleSheet(f"color: {self.theme['text']}; font-size: 10px; opacity: 0.7;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        return frame

    # ========== СТИЛИ ==========

    def _btn_style(self) -> str:
        return f"""
            QPushButton {{
                background: {self.theme['input_bg']};
                color: {self.theme['text']};
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 12px;
                border: none;
                text-align: left;
            }}
            QPushButton:hover {{
                background: {self.theme['accent']};
                color: {self.theme['accent_text']};
            }}
            QPushButton:disabled {{
                opacity: 0.5;
            }}
        """

    # ========== ПОДСВЕТКА СИНТАКСИСА ==========

    def _highlight_code(self, text: str, language: str = "python") -> str:
        """Возвращает HTML с подсветкой синтаксиса."""
        if not text:
            return ""

        colors = SYNTAX_COLORS.get(language, SYNTAX_COLORS["python"])
        escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        escaped = re.sub(
            r'(["\'])(.*?)\1',
            lambda m: f'<span style="color:{colors["string"]};">{m.group(0)}</span>',
            escaped
        )

        escaped = re.sub(
            r'(#.*?$)',
            lambda m: f'<span style="color:{colors["comment"]};">{m.group(0)}</span>',
            escaped,
            flags=re.MULTILINE
        )

        keywords = [
            "def", "class", "return", "if", "elif", "else", "for", "while",
            "import", "from", "try", "except", "finally", "with", "as", "pass",
            "break", "continue", "lambda", "yield", "global", "nonlocal",
            "True", "False", "None", "async", "await", "in", "is", "not", "and", "or"
        ]
        for kw in keywords:
            escaped = re.sub(
                rf'\b{kw}\b',
                f'<span style="color:{colors["keyword"]}; font-weight:bold;">{kw}</span>',
                escaped
            )

        escaped = re.sub(
            r'(\w+)(?=\s*\()',
            lambda m: f'<span style="color:{colors["function"]};">{m.group(0)}</span>',
            escaped
        )

        return escaped

    def _append_colored(self, sender: str, text: str, color: str):
        """Добавляет цветное сообщение в чат."""
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        fmt_name = QTextCharFormat()
        fmt_name.setForeground(QColor(color))
        fmt_name.setFontWeight(QFont.Weight.Bold)
        cursor.insertText(f"{sender}: ", fmt_name)

        if "```" in text:
            parts = text.split("```")
            for i, part in enumerate(parts):
                if i % 2 == 1:
                    language = "python"
                    if "\n" in part:
                        first_line = part.split("\n")[0].strip()
                        if first_line in ["python", "js", "javascript", "html", "css"]:
                            language = first_line
                            part = part.split("\n", 1)[1] if "\n" in part else ""

                    fmt_code = QTextCharFormat()
                    fmt_code.setBackground(QColor(self.theme["code_bg"]))
                    fmt_code.setForeground(QColor(self.theme["text"]))
                    cursor.insertText(part, fmt_code)

                    fmt_break = QTextCharFormat()
                    fmt_break.setForeground(QColor(self.theme["text"]))
                    cursor.insertText("\n", fmt_break)
                else:
                    fmt_text = QTextCharFormat()
                    fmt_text.setForeground(QColor(self.theme["text"]))
                    cursor.insertText(part, fmt_text)
        else:
            fmt_text = QTextCharFormat()
            fmt_text.setForeground(QColor(self.theme["text"]))
            cursor.insertText(text, fmt_text)

        cursor.insertText("\n\n")
        self.chat_display.setTextCursor(cursor)
        self._scroll_to_bottom()

    def _replace_last_z(self, text: str):
        """Заменяет последнее сообщение Z с подсветкой."""
        if self._z_block_start is None:
            return

        cursor = self.chat_display.textCursor()
        cursor.setPosition(self._z_block_start)
        cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()

        fmt_name = QTextCharFormat()
        fmt_name.setForeground(QColor(self.theme["accent"]))
        fmt_name.setFontWeight(QFont.Weight.Bold)
        cursor.insertText("Z: ", fmt_name)

        if "```" in text:
            parts = text.split("```")
            for i, part in enumerate(parts):
                if i % 2 == 1:
                    language = "python"
                    if "\n" in part:
                        first_line = part.split("\n")[0].strip()
                        if first_line in ["python", "js", "javascript", "html", "css"]:
                            language = first_line
                            part = part.split("\n", 1)[1] if "\n" in part else ""

                    fmt_code = QTextCharFormat()
                    fmt_code.setBackground(QColor(self.theme["code_bg"]))
                    fmt_code.setForeground(QColor(self.theme["text"]))
                    cursor.insertText(part, fmt_code)

                    fmt_break = QTextCharFormat()
                    fmt_break.setForeground(QColor(self.theme["text"]))
                    cursor.insertText("\n", fmt_break)
                else:
                    fmt_text = QTextCharFormat()
                    fmt_text.setForeground(QColor(self.theme["text"]))
                    cursor.insertText(part, fmt_text)
        else:
            fmt_text = QTextCharFormat()
            fmt_text.setForeground(QColor(self.theme["text"]))
            cursor.insertText(text, fmt_text)

        cursor.insertText("\n")
        self.chat_display.setTextCursor(cursor)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        sb = self.chat_display.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ========== РАБОТА С ЧАТОМ ==========

    def greet(self):
        self._append_colored(
            "Z",
            "💻 Режим программиста активирован.\n"
            "Здесь я знаю Python, JS, C++, Unity, Godot, архитектуру LLM и всё остальное.\n"
            "Можешь задавать вопросы по коду, просить написать функцию или объяснить алгоритм.\n\n"
            "📁 Слева — дерево проекта.\n"
            "🛠️ Справа — инструменты и Git.\n"
            "✨ В редакторе есть кнопка 'Продолжить код' для автодополнения.",
            self.theme["accent"]
        )

    def send_message(self):
        text = self.input_field.text().strip()
        if not text:
            return

        self.input_field.clear()
        self._append_colored("Ты", text, "#a6e3a1")

        self._z_block_start = self.chat_display.textCursor().position()
        self._append_colored("Z", "думает...", self.theme["accent"])

        self.typing_label.show()
        self.send_btn.setEnabled(False)
        self.send_btn.setText("...")

        self.worker = ProgWorker(text)
        self.worker.chunk_ready.connect(self._on_chunk)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _on_chunk(self, full_text: str):
        self._replace_last_z(full_text)

    def _on_finished(self, full_text: str):
        self.typing_label.hide()
        self.send_btn.setEnabled(True)
        self.send_btn.setText("➤")
        self._replace_last_z(full_text)

        if get_setting("voice_enabled", "true") == "true":
            speak(full_text)

    def _on_error(self, error_msg: str):
        self.typing_label.hide()
        self.send_btn.setEnabled(True)
        self.send_btn.setText("➤")
        self._replace_last_z(error_msg)

    def clear_chat(self):
        """Очищает чат."""
        reply = QMessageBox.question(
            self, "Очистить чат",
            "Очистить все сообщения в чате?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.chat_display.clear()
            self.greet()

    # ========== РАБОТА С ДЕРЕВОМ ПРОЕКТА ==========

    def load_project_tree(self):
        """Загружает дерево проекта."""
        self.file_tree.clear()
        self.file_tree_items.clear()
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        try:
            project_path = get_current_project_path() or "D:\\Zeta"
            self.project_path = project_path
            self.path_label.setText(project_path)

            self._populate_tree(project_path)
        except Exception as e:
            self._append_colored("Z", f"⚠️ Ошибка загрузки проекта: {e}", self.theme["danger"])
        finally:
            self.progress_bar.setVisible(False)
            self._append_colored("Z", "📁 Дерево проекта загружено.", self.theme["success"])

    def _populate_tree(self, path: str, parent: Optional[QTreeWidgetItem] = None):
        """Рекурсивно заполняет дерево."""
        if not os.path.exists(path):
            return

        try:
            items = sorted(os.listdir(path))
            total = len(items)
            processed = 0

            for item in items:
                processed += 1
                self.progress_bar.setValue(int(processed / total * 100))

                full_path = os.path.join(path, item)
                tree_parent = parent if parent else self.file_tree.invisibleRootItem()

                if item.startswith(".") or item.startswith("__"):
                    continue

                if os.path.isdir(full_path):
                    dir_item = QTreeWidgetItem(tree_parent)
                    dir_item.setText(0, f"📁 {item}")
                    dir_item.setData(0, Qt.ItemDataRole.UserRole, full_path)

                    try:
                        if len(os.listdir(full_path)) < 100:
                            self._populate_tree(full_path, dir_item)
                    except PermissionError:
                        pass

                    if dir_item.childCount() == 0:
                        child = QTreeWidgetItem(dir_item)
                        child.setText(0, "...")
                        child.setDisabled(True)

                elif os.path.isfile(full_path):
                    file_item = QTreeWidgetItem(tree_parent)
                    icon = self._get_file_icon(item)
                    file_item.setText(0, f"{icon} {item}")
                    file_item.setData(0, Qt.ItemDataRole.UserRole, full_path)

            self.progress_bar.setValue(100)

        except PermissionError:
            pass

    def _get_file_icon(self, filename: str) -> str:
        """Возвращает иконку для файла."""
        ext = os.path.splitext(filename)[1].lower()
        icons = {
            ".py": "🐍", ".js": "📜", ".ts": "📘", ".html": "🌐", ".css": "🎨",
            ".json": "📋", ".md": "📝", ".txt": "📄", ".xml": "📄", ".yaml": "📄",
            ".yml": "📄", ".toml": "📄", ".ini": "⚙️", ".cfg": "⚙️", ".conf": "⚙️",
            ".sh": "💻", ".bat": "💻", ".ps1": "💻", ".exe": "⚡", ".dll": "🔧",
            ".so": "🔧", ".dylib": "🔧", ".jpg": "🖼️", ".jpeg": "🖼️", ".png": "🖼️",
            ".gif": "🖼️", ".svg": "🖼️", ".ico": "🖼️", ".mp3": "🎵", ".mp4": "🎬",
            ".wav": "🎵", ".zip": "📦", ".tar": "📦", ".gz": "📦", ".rar": "📦", ".7z": "📦",
        }
        return icons.get(ext, "📄")

    def expand_all(self):
        self.file_tree.expandAll()

    def collapse_all(self):
        self.file_tree.collapseAll()

    def on_file_double_click(self, item: QTreeWidgetItem, column: int):
        """Обработка двойного клика по файлу."""
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path and os.path.isfile(path):
            self.current_file_path = path
            self.open_file_in_editor(path)
            self._append_colored("Z", f"📄 Открыт файл: {os.path.basename(path)}", self.theme["success"])

    def open_file_in_editor(self, path: str):
        """Открывает файл в редакторе кода."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.code_editor.setPlainText(content)
            self.tabs.setCurrentIndex(1)
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось открыть файл: {e}")

    def save_current_file(self):
        """Сохранение текущего файла в редакторе."""
        if not self.current_file_path:
            path, _ = QFileDialog.getSaveFileName(self, "Сохранить файл", "", "Python Files (*.py);;All Files (*)")
            if path:
                self.current_file_path = path
            else:
                return

        try:
            content = self.code_editor.toPlainText()
            with open(self.current_file_path, "w", encoding="utf-8") as f:
                f.write(content)
            QMessageBox.information(self, "Сохранено", f"Файл сохранён: {self.current_file_path}")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить файл: {e}")

    # ========== ИНСТРУМЕНТЫ ==========

    def open_chrome(self):
        subprocess.Popen("start chrome", shell=True)

    def open_vscode(self):
        subprocess.Popen("code", shell=True)

    def open_explorer(self):
        subprocess.Popen("explorer", shell=True)

    def open_taskmgr(self):
        subprocess.Popen("taskmgr", shell=True)

    def open_terminal(self):
        subprocess.Popen("start cmd", shell=True)

    def open_file_dialog(self):
        """Открывает файл через диалог."""
        path, _ = QFileDialog.getOpenFileName(self, "Открыть файл", "", "Все файлы (*)")
        if path:
            self.current_file_path = path
            self.open_file_in_editor(path)

    def open_in_vscode(self):
        """Открывает текущий проект или файл в VS Code."""
        if self.current_file_path:
            subprocess.Popen(["code", self.current_file_path], shell=True)
        else:
            subprocess.Popen(["code", self.project_path], shell=True)

    def lint_code(self):
        """Проверяет код на синтаксические ошибки."""
        code = self.code_editor.toPlainText()
        if not code:
            self._append_colored("Z", "⚠️ Редактор пуст.", self.theme["warning"])
            return

        try:
            ast.parse(code)
            self._append_colored("Z", "✅ Синтаксис корректен! Ошибок не найдено.", self.theme["success"])
        except SyntaxError as e:
            self._append_colored("Z", f"❌ Синтаксическая ошибка: {e}", self.theme["danger"])

    # ========== GIT ==========

    def git_status(self):
        try:
            result = subprocess.run(
                ["git", "status", "-sb"],
                capture_output=True,
                text=True,
                shell=True,
                cwd=self.project_path,
                encoding='utf-8',
                errors='replace'
            )
            output = result.stdout if result.returncode == 0 else result.stderr
            self._append_colored("📊 Git Status", output or "Рабочая директория чиста", self.theme["info"])
        except Exception as e:
            self._append_colored("⚠️ Git", f"Ошибка: {e}", self.theme["danger"])

    def git_log(self, n: int = 5):
        try:
            result = subprocess.run(
                ["git", "log", f"-n{n}", "--oneline"],
                capture_output=True,
                text=True,
                shell=True,
                cwd=self.project_path,
                encoding='utf-8',
                errors='replace'
            )
            output = result.stdout if result.returncode == 0 else result.stderr
            self._append_colored("📈 Git Log", output or "Нет коммитов", self.theme["info"])
        except Exception as e:
            self._append_colored("⚠️ Git", f"Ошибка: {e}", self.theme["danger"])

    def git_diff(self):
        try:
            result = subprocess.run(
                ["git", "diff"],
                capture_output=True,
                text=True,
                shell=True,
                cwd=self.project_path,
                encoding='utf-8',
                errors='replace'
            )
            output = result.stdout if result.returncode == 0 else result.stderr
            self._append_colored("📝 Git Diff", output or "Нет изменений", self.theme["info"])
        except Exception as e:
            self._append_colored("⚠️ Git", f"Ошибка: {e}", self.theme["danger"])

    def git_commit(self):
        """Создаёт коммит."""
        text, ok = QInputDialog.getText(self, "Git Commit", "Введите сообщение коммита:")
        if ok and text:
            try:
                result = subprocess.run(
                    ["git", "add", ".", "&&", "git", "commit", "-m", text],
                    capture_output=True,
                    text=True,
                    shell=True,
                    cwd=self.project_path,
                    encoding='utf-8',
                    errors='replace'
                )
                output = result.stdout if result.returncode == 0 else result.stderr
                self._append_colored("💾 Git Commit", output or "Коммит создан", self.theme["success"])
            except Exception as e:
                self._append_colored("⚠️ Git", f"Ошибка: {e}", self.theme["danger"])

    def auto_commit(self):
        """Авто-коммит с генерацией сообщения от Зеты."""
        try:
            diff_result = subprocess.run(
                ["git", "diff", "--stat"],
                capture_output=True,
                text=True,
                shell=True,
                cwd=self.project_path,
                encoding='utf-8',
                errors='replace'
            )
            changes = diff_result.stdout if diff_result.returncode == 0 else ""

            prompt = (
                f"Напиши короткое сообщение для git commit (до 50 символов) на русском. "
                f"Изменения: {changes[:200] if changes else 'Обновление проекта'}"
            )
            commit_message = ask_zeta(prompt, mode="programmer").strip().split("\n")[0][:50]

            result = subprocess.run(
                ["git", "add", ".", "&&", "git", "commit", "-m", commit_message],
                capture_output=True,
                text=True,
                shell=True,
                cwd=self.project_path,
                encoding='utf-8',
                errors='replace'
            )
            output = result.stdout if result.returncode == 0 else result.stderr
            self._append_colored("🤖 Авто-коммит", output or f"Коммит создан: {commit_message}", self.theme["success"])
        except Exception as e:
            self._append_colored("⚠️ Git", f"Ошибка: {e}", self.theme["danger"])

    def git_branch(self):
        try:
            result = subprocess.run(
                ["git", "branch", "-a"],
                capture_output=True,
                text=True,
                shell=True,
                cwd=self.project_path,
                encoding='utf-8',
                errors='replace'
            )
            output = result.stdout if result.returncode == 0 else result.stderr
            self._append_colored("🌿 Git Branches", output or "Нет веток", self.theme["info"])
        except Exception as e:
            self._append_colored("⚠️ Git", f"Ошибка: {e}", self.theme["danger"])

    def git_stash(self):
        """Сохраняет изменения в stash."""
        try:
            result = subprocess.run(
                ["git", "stash", "save"],
                capture_output=True,
                text=True,
                shell=True,
                cwd=self.project_path,
                encoding='utf-8',
                errors='replace'
            )
            output = result.stdout if result.returncode == 0 else result.stderr
            self._append_colored("📦 Git Stash", output or "Изменения сохранены в stash", self.theme["info"])
        except Exception as e:
            self._append_colored("⚠️ Git", f"Ошибка: {e}", self.theme["danger"])

    def git_pull(self):
        """Обновляет проект из удалённого репозитория."""
        try:
            result = subprocess.run(
                ["git", "pull"],
                capture_output=True,
                text=True,
                shell=True,
                cwd=self.project_path,
                encoding='utf-8',
                errors='replace'
            )
            output = result.stdout if result.returncode == 0 else result.stderr
            self._append_colored("🔄 Git Pull", output or "Обновлений нет", self.theme["info"])
        except Exception as e:
            self._append_colored("⚠️ Git", f"Ошибка: {e}", self.theme["danger"])

    # ========== ТЕРМИНАЛ ==========

    def run_terminal_command(self):
        """Выполняет команду в терминале."""
        command = self.terminal_input.text().strip()
        if not command:
            return

        self.terminal_input.clear()
        self.terminal_output.append(f"$ {command}")

        if self.run_process and self.run_process.isRunning():
            self.run_process.quit()
            self.run_process.wait()

        self.run_process = RunProcess(command, self.project_path)
        self.run_process.output_ready.connect(self.terminal_output.append)
        self.run_process.finished_process.connect(self.on_process_finished)
        self.run_process.start()

    def on_process_finished(self, exit_code: int):
        self.terminal_output.append(f"✅ Завершено с кодом {exit_code}\n")

    # ========== АВТОДОПОЛНЕНИЕ ==========

    def auto_complete_code(self):
        """Продолжает текущий код с помощью ИИ."""
        code = self.code_editor.toPlainText()
        if not code:
            self._append_colored("Z", "⚠️ Редактор пуст. Напишите код для продолжения.", self.theme["warning"])
            return

        self.status_bar.showMessage("✨ Зета дописывает код...")
        self.auto_complete_worker = AutoCompleteWorker(code)
        self.auto_complete_worker.result_ready.connect(self.on_auto_complete_result)
        self.auto_complete_worker.start()

    def on_auto_complete_result(self, result: str):
        """Вставляет продолжение кода в редактор."""
        self.code_editor.appendPlainText(result)
        self.status_bar.showMessage("✅ Код дополнен")

    # ========== ЗАПУСК ФАЙЛА ==========

    def run_current_file(self):
        """Запускает текущий файл."""
        if not self.current_file_path:
            self._append_colored("Z", "⚠️ Выберите файл в дереве проекта или в редакторе.", self.theme["warning"])
            return

        ext = os.path.splitext(self.current_file_path)[1].lower()

        if ext == ".py":
            self._append_colored("Z", f"▶️ Запуск Python: {os.path.basename(self.current_file_path)}", self.theme["info"])
            try:
                result = subprocess.run(
                    ["python", self.current_file_path],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=os.path.dirname(self.current_file_path),
                    encoding='utf-8',
                    errors='replace'
                )
                output = result.stdout if result.stdout else result.stderr
                self._append_colored("📤 Вывод", output or "✅ Выполнено без вывода", self.theme["success"])
                self.console.append(output)
            except subprocess.TimeoutExpired:
                self._append_colored("⚠️", "⏱️ Таймаут выполнения", self.theme["danger"])
            except Exception as e:
                self._append_colored("⚠️", f"Ошибка: {e}", self.theme["danger"])

        elif ext in [".js", ".ts"]:
            self._append_colored("Z", f"▶️ Запуск JavaScript: {os.path.basename(self.current_file_path)}", self.theme["info"])
            try:
                result = subprocess.run(
                    ["node", self.current_file_path],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=os.path.dirname(self.current_file_path),
                    encoding='utf-8',
                    errors='replace'
                )
                output = result.stdout if result.stdout else result.stderr
                self._append_colored("📤 Вывод", output or "✅ Выполнено без вывода", self.theme["success"])
                self.console.append(output)
            except subprocess.TimeoutExpired:
                self._append_colored("⚠️", "⏱️ Таймаут выполнения", self.theme["danger"])
            except Exception as e:
                self._append_colored("⚠️", f"Ошибка: {e}", self.theme["danger"])

        else:
            self._append_colored("Z", f"⚠️ Неподдерживаемый формат: {ext}", self.theme["warning"])

    def clear_console(self):
        """Очищает консоль."""
        self.console.clear()

    def copy_code(self):
        """Копирует выделенный код из чата."""
        selected = self.chat_display.textCursor().selectedText()
        if selected:
            QApplication.clipboard().setText(selected)
            self._append_colored("Z", "📋 Код скопирован в буфер обмена", self.theme["success"])
        else:
            self._append_colored("Z", "⚠️ Выделите код для копирования", self.theme["warning"])

    def open_selected_file(self):
        """Открывает выбранный файл в VS Code."""
        selected = self.file_tree.currentItem()
        if not selected:
            self._append_colored("Z", "⚠️ Выберите файл в дереве проекта.", self.theme["warning"])
            return

        path = selected.data(0, Qt.ItemDataRole.UserRole)
        if path and os.path.isfile(path):
            self.current_file_path = path
            self.open_file_in_editor(path)
            self._append_colored("Z", f"📄 Открыт файл: {os.path.basename(path)}", self.theme["success"])
        else:
            self._append_colored("Z", "⚠️ Это папка, выберите файл.", self.theme["warning"])

    # ========== СОБЫТИЯ ==========

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait()
        if self.auto_complete_worker and self.auto_complete_worker.isRunning():
            self.auto_complete_worker.quit()
            self.auto_complete_worker.wait()
        if self.run_process and self.run_process.isRunning():
            self.run_process.quit()
            self.run_process.wait()
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        super().keyPressEvent(event)


# ========== ТЕСТ ==========
if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    window = ProgrammerWindow()
    window.show()
    sys.exit(app.exec())