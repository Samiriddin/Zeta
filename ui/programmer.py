# -*- coding: utf-8 -*-
"""
Окно режима разработчика Zeta — ПОЛНОЦЕННАЯ IDE.
Поддерживает: чат с ИИ, дерево проекта, редактор кода с нумерацией строк,
консоль, терминал, Git-граф, авто-коммит, автодополнение, линтер, запуск файлов,
поиск по проекту, установку пакетов, быстрые команды, авто-сохранение.

ИСПРАВЛЕНО (2026-09-21):
    - QShortcut перенесён из QtWidgets в QtGui (ImportError fix)
    - Переименовано: "Режим программиста" → "Режим разработчика"
    - Добавлена нумерация строк в редакторе
    - Добавлены горячие клавиши: Ctrl+S, Ctrl+R, Ctrl+B, Ctrl+Tab
    - Улучшен линтер: python -m py_compile (точные ошибки)
    - Авто-сохранение каждые 30 сек
    - Контекстное меню в дереве файлов
    - Поиск по файлам проекта
    - Вкладка "Логи" (data/zeta.log)
    - Быстрые команды: start_zeta.bat, start_web.bat, start_all.bat
    - Установка pip-пакетов через UI
    - Индикатор позиции курсора в статус-баре
    - Стиль VS Code / Monaco
"""

import os
import subprocess
import re
import ast
import sys
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QLineEdit, QFrame,
    QListWidget, QSplitter, QTreeWidget, QTreeWidgetItem,
    QProgressBar, QMessageBox, QMenu, QApplication,
    QFileDialog, QPlainTextEdit, QStatusBar, QTextBrowser,
    QScrollArea, QTabWidget, QInputDialog, QCheckBox,
    QComboBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QProcess, QRect, QSize
from PyQt6.QtGui import (
    QTextCursor, QTextCharFormat, QColor, QFont, QAction,
    QSyntaxHighlighter, QTextFormat, QPainter, QKeySequence,
    QFontDatabase, QPalette, QPixmap, QIcon,
    QShortcut
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.ai_engine import ask_zeta
from core.memory import get_setting, save_setting
from voice.tts import speak
from modules.vscode_context import scan_project, get_file_tree, get_current_project_path


# ========== ТЕМА VS CODE (Monaco-inspired) ==========
THEMES = {
    "dark": {
        "frame_bg": "#1e1e1e",
        "frame_border": "#2d2d30",
        "text": "#d4d4d4",
        "text_dim": "#808080",
        "chat_bg": "#252526",
        "input_bg": "#3c3c3c",
        "accent": "#007acc",
        "accent_hover": "#1a8ad4",
        "accent_text": "#ffffff",
        "close_bg": "#f48771",
        "close_hover": "#e06c75",
        "success": "#4ec9b0",
        "warning": "#dcdcaa",
        "danger": "#f48771",
        "info": "#569cd6",
        "code_bg": "#1e1e1e",
        "console_bg": "#1e1e1e",
        "gutter_bg": "#252526",
        "gutter_text": "#858585",
        "line_highlight": "#2a2d2e",
        "sidebar_bg": "#252526",
        "activitybar_bg": "#333333",
        "statusbar_bg": "#007acc",
        "statusbar_text": "#ffffff",
    },
    "light": {
        "frame_bg": "#ffffff",
        "frame_border": "#e0e0e0",
        "text": "#333333",
        "text_dim": "#808080",
        "chat_bg": "#f3f3f3",
        "input_bg": "#e8e8e8",
        "accent": "#007acc",
        "accent_hover": "#1a8ad4",
        "accent_text": "#ffffff",
        "close_bg": "#d20f39",
        "close_hover": "#e64553",
        "success": "#40a02b",
        "warning": "#df8e1d",
        "danger": "#d20f39",
        "info": "#1e66f5",
        "code_bg": "#ffffff",
        "console_bg": "#f5f5f5",
        "gutter_bg": "#f0f0f0",
        "gutter_text": "#999999",
        "line_highlight": "#f0f0f0",
        "sidebar_bg": "#f3f3f3",
        "activitybar_bg": "#e0e0e0",
        "statusbar_bg": "#007acc",
        "statusbar_text": "#ffffff",
    },
}


# ========== ПОДСВЕТКА СИНТАКСИСА ==========
class PythonHighlighter(QSyntaxHighlighter):
    """Подсветка синтаксиса Python (стиль VS Code)."""

    def __init__(self, document, theme):
        super().__init__(document)
        self.theme = theme

        self.keyword_format = QTextCharFormat()
        self.keyword_format.setForeground(QColor("#c586c0"))
        self.keyword_format.setFontWeight(QFont.Weight.Bold)

        self.builtin_format = QTextCharFormat()
        self.builtin_format.setForeground(QColor("#4ec9b0"))

        self.string_format = QTextCharFormat()
        self.string_format.setForeground(QColor("#ce9178"))

        self.comment_format = QTextCharFormat()
        self.comment_format.setForeground(QColor("#6a9955"))
        self.comment_format.setFontItalic(True)

        self.function_format = QTextCharFormat()
        self.function_format.setForeground(QColor("#dcdcaa"))

        self.number_format = QTextCharFormat()
        self.number_format.setForeground(QColor("#b5cea8"))

        self.decorator_format = QTextCharFormat()
        self.decorator_format.setForeground(QColor("#dcdcaa"))
        self.decorator_format.setFontItalic(True)

        self.keywords = [
            "def", "class", "return", "if", "elif", "else", "for", "while",
            "import", "from", "try", "except", "finally", "with", "as", "pass",
            "break", "continue", "lambda", "yield", "global", "nonlocal",
            "True", "False", "None", "async", "await", "in", "is", "not",
            "and", "or", "raise", "del", "assert", "match", "case"
        ]

        self.builtins = [
            "print", "len", "range", "str", "int", "float", "list", "dict",
            "set", "tuple", "type", "isinstance", "hasattr", "getattr",
            "setattr", "open", "input", "int", "bool", "bytes", "sum",
            "min", "max", "abs", "round", "sorted", "reversed", "enumerate",
            "zip", "map", "filter", "any", "all", "repr", "eval", "exec"
        ]

    def highlightBlock(self, text):
        in_string = None
        comment_index = -1
        i = 0
        while i < len(text):
            c = text[i]
            if in_string:
                if c == in_string:
                    in_string = None
            elif c in ('"', "'"):
                in_string = c
            elif c == "#":
                comment_index = i
                break
            i += 1

        if comment_index >= 0:
            self.setFormat(comment_index, len(text) - comment_index, self.comment_format)

        string_pattern = re.compile(r'(["\'])(.*?)\1')
        for match in string_pattern.finditer(text):
            if comment_index >= 0 and match.start() > comment_index:
                continue
            self.setFormat(match.start(), len(match.group()), self.string_format)

        decorator_pattern = re.compile(r'@\w+(\.\w+)*')
        for match in decorator_pattern.finditer(text):
            self.setFormat(match.start(), len(match.group()), self.decorator_format)

        for keyword in self.keywords:
            pattern = re.compile(rf'\b{keyword}\b')
            for match in pattern.finditer(text):
                if comment_index >= 0 and match.start() > comment_index:
                    continue
                self.setFormat(match.start(), len(keyword), self.keyword_format)

        for builtin in self.builtins:
            pattern = re.compile(rf'\b{builtin}\b')
            for match in pattern.finditer(text):
                if comment_index >= 0 and match.start() > comment_index:
                    continue
                self.setFormat(match.start(), len(builtin), self.builtin_format)

        number_pattern = re.compile(r'\b\d+(\.\d+)?\b')
        for match in number_pattern.finditer(text):
            if comment_index >= 0 and match.start() > comment_index:
                continue
            self.setFormat(match.start(), len(match.group()), self.number_format)

        func_pattern = re.compile(r'\b(\w+)(?=\s*\()')
        for match in func_pattern.finditer(text):
            if comment_index >= 0 and match.start() > comment_index:
                continue
            self.setFormat(match.start(), len(match.group(1)), self.function_format)


# ========== РЕДАКТОР С НУМЕРАЦИЕЙ СТРОК ==========
class LineNumberArea(QWidget):
    """Область с номерами строк."""

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)


class CodeEditor(QPlainTextEdit):
    """Редактор кода с нумерацией строк и подсветкой текущей строки."""

    def __init__(self, theme):
        super().__init__()
        self.theme = theme

        font = QFont("Consolas", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)

        self.line_number_area = LineNumberArea(self)

        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)

        self.update_line_number_area_width(0)
        self.highlight_current_line()

        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

    def line_number_area_width(self) -> int:
        digits = 1
        max_num = max(1, self.blockCount())
        while max_num >= 10:
            max_num //= 10
            digits += 1
        space = 15 + self.fontMetrics().horizontalAdvance("9") * digits
        return space

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(
                0, rect.y(), self.line_number_area.width(), rect.height()
            )
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor(self.theme["gutter_bg"]))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        bottom = top + self.blockBoundingRect(block).height()

        painter.setPen(QColor(self.theme["gutter_text"]))
        painter.setFont(self.font())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.drawText(
                    0, int(top),
                    self.line_number_area.width() - 5,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    number,
                )
            block = block.next()
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()
            block_number += 1

    def highlight_current_line(self):
        extra_selections = []

        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            line_color = QColor(self.theme["line_highlight"])
            selection.format.setBackground(line_color)
            selection.format.setProperty(
                QTextFormat.Property.FullWidthSelection, True
            )
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)

        self.setExtraSelections(extra_selections)


# ========== ПОТОКИ ==========
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
            process.waitForFinished(60000)

            output = process.readAllStandardOutput().data().decode('utf-8', errors='replace')
            error = process.readAllStandardError().data().decode('utf-8', errors='replace')

            if output:
                self.output_ready.emit(output)
            if error:
                self.output_ready.emit(f"⚠️ Ошибка: {error}")

            self.finished_process.emit(process.exitCode())
        except Exception as e:
            self.output_ready.emit(f"⚠️ Ошибка: {e}")


class AutoCompleteWorker(QThread):
    result_ready = pyqtSignal(str)

    def __init__(self, code: str, context: str = ""):
        super().__init__()
        self.code = code
        self.context = context

    def run(self):
        try:
            prompt = (
                "Продолжи этот код. Верни ТОЛЬКО код, без объяснений, без ```.\n\n"
                f"Текущий код:\n{self.code}\n\nПродолжение:"
            )
            result = ask_zeta(prompt, mode="programmer")
            result = re.sub(r"```\w*\n?", "", result)
            self.result_ready.emit(result)
        except Exception as e:
            self.result_ready.emit(f"# ⚠️ Ошибка: {e}")


# ========== ГЛАВНОЕ ОКНО ==========
class ProgrammerWindow(QWidget):
    """Окно режима разработчика Zeta — полноценная IDE."""

    def __init__(self, theme_name: str = "dark"):
        super().__init__()
        self.theme_name = theme_name
        self.theme = THEMES.get(theme_name, THEMES["dark"])
        self.worker: Optional[ProgWorker] = None
        self.run_process: Optional[RunProcess] = None
        self.auto_complete_worker: Optional[AutoCompleteWorker] = None
        self._z_block_start = None
        self.project_path = get_current_project_path() or "D:\\Zeta"
        self.current_file_path = None
        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self._auto_save)

        self.setWindowTitle("💻 Z — Режим разработчика")
        self.setGeometry(60, 60, 1500, 900)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowMinimizeButtonHint |
            Qt.WindowType.WindowMaximizeButtonHint
        )
        self.setStyleSheet(f"background-color: {self.theme['frame_bg']}; color: {self.theme['text']};")

        self.init_ui()
        self.setup_hotkeys()
        self.load_project_tree()
        self.greet()

        self._autosave_timer.start(30000)

    # ========== UI ==========

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        btn_save = self._make_toolbar_btn("💾 Сохранить", "Сохранить файл (Ctrl+S)", self.save_current_file)
        toolbar.addWidget(btn_save)

        btn_run = self._make_toolbar_btn("▶️ Запустить", "Запустить файл (Ctrl+R)", self.run_current_file)
        toolbar.addWidget(btn_run)

        btn_open = self._make_toolbar_btn("📂 Открыть", "Открыть файл", self.open_file_dialog)
        toolbar.addWidget(btn_open)

        btn_vscode = self._make_toolbar_btn("🧩 VS Code", "Открыть в VS Code", self.open_in_vscode)
        toolbar.addWidget(btn_vscode)

        btn_lint = self._make_toolbar_btn("🔍 Проверить", "Проверить код (Ctrl+B)", self.lint_code)
        toolbar.addWidget(btn_lint)

        btn_lint_all = self._make_toolbar_btn("🧪 Весь проект", "Проверить весь проект", self.lint_project)
        toolbar.addWidget(btn_lint_all)

        toolbar.addStretch()

        btn_auto_commit = self._make_toolbar_btn("🤖 Авто-коммит", "Git auto-commit", self.auto_commit)
        toolbar.addWidget(btn_auto_commit)

        btn_clear_chat = self._make_toolbar_btn("🗑️ Чат", "Очистить чат", self.clear_chat)
        toolbar.addWidget(btn_clear_chat)

        btn_clear_console = self._make_toolbar_btn("🧹 Консоль", "Очистить консоль", self.clear_console)
        toolbar.addWidget(btn_clear_console)

        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        splitter.addWidget(self._create_left_panel())
        splitter.addWidget(self._create_center_panel())
        splitter.addWidget(self._create_right_panel())

        splitter.setSizes([260, 700, 280])
        layout.addWidget(splitter)

        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet(f"""
            QStatusBar {{
                background-color: {self.theme['statusbar_bg']};
                color: {self.theme['statusbar_text']};
                font-size: 11px;
                padding: 2px;
            }}
        """)
        self.status_bar.showMessage("✅ Готов")

        self.cursor_pos_label = QLabel("Стр 1, Кол 1")
        self.cursor_pos_label.setStyleSheet(f"color: {self.theme['statusbar_text']}; padding-right: 10px;")
        self.status_bar.addPermanentWidget(self.cursor_pos_label)

        self.lint_status = QLabel("")
        self.lint_status.setStyleSheet(f"color: {self.theme['statusbar_text']}; padding-right: 10px;")
        self.status_bar.addPermanentWidget(self.lint_status)

        layout.addWidget(self.status_bar)

    def _make_toolbar_btn(self, text: str, tooltip: str, callback) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(30)
        btn.setToolTip(tooltip)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {self.theme['input_bg']};
                color: {self.theme['text']};
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
                border: none;
            }}
            QPushButton:hover {{
                background: {self.theme['accent']};
                color: {self.theme['accent_text']};
            }}
            QPushButton:pressed {{
                background: {self.theme['accent_hover']};
            }}
        """)
        btn.clicked.connect(callback)
        return btn

    def _create_left_panel(self) -> QFrame:
        frame = QFrame()
        frame.setMinimumWidth(220)
        frame.setMaximumWidth(350)
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {self.theme['sidebar_bg']};
                border-radius: 6px;
                border: 1px solid {self.theme['frame_border']};
            }}
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title = QLabel("📁 ПРОЕКТ")
        title.setStyleSheet(f"color: {self.theme['text_dim']}; font-weight: bold; font-size: 11px;")
        layout.addWidget(title)

        self.path_label = QLabel(self.project_path)
        self.path_label.setStyleSheet(f"color: {self.theme['text']}; font-size: 10px; padding: 2px;")
        self.path_label.setWordWrap(True)
        layout.addWidget(self.path_label)

        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("🔍 Поиск файла...")
        self.search_field.setStyleSheet(f"""
            QLineEdit {{
                background: {self.theme['input_bg']};
                color: {self.theme['text']};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
                border: none;
            }}
        """)
        self.search_field.textChanged.connect(self._filter_tree)
        layout.addWidget(self.search_field)

        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderHidden(True)
        self.file_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_tree.customContextMenuRequested.connect(self._show_tree_context_menu)
        self.file_tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {self.theme['chat_bg']};
                color: {self.theme['text']};
                border-radius: 4px;
                border: none;
                font-size: 12px;
                padding: 4px;
            }}
            QTreeWidget::item {{
                padding: 2px;
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

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)

        for text, tooltip, callback in [
            ("🔄", "Обновить дерево", self.load_project_tree),
            ("➕", "Развернуть всё", self.expand_all),
            ("➖", "Свернуть всё", self.collapse_all),
        ]:
            btn = QPushButton(text)
            btn.setFixedSize(30, 30)
            btn.setToolTip(tooltip)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(self._btn_style())
            btn.clicked.connect(callback)
            btn_layout.addWidget(btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {self.theme['input_bg']};
                border-radius: 3px;
                height: 4px;
                text-align: center;
            }}
            QProgressBar::chunk {{
                background-color: {self.theme['accent']};
                border-radius: 3px;
            }}
        """)
        layout.addWidget(self.progress_bar)

        return frame

    def _create_center_panel(self) -> QFrame:
        frame = QFrame()
        frame.setMinimumWidth(500)
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {self.theme['frame_bg']};
                border-radius: 6px;
                border: 1px solid {self.theme['frame_border']};
            }}
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(False)
        self.tabs.setMovable(True)
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                background: {self.theme['frame_bg']};
                border-radius: 4px;
                border: 1px solid {self.theme['frame_border']};
                padding: 2px;
            }}
            QTabBar::tab {{
                background: {self.theme['input_bg']};
                color: {self.theme['text']};
                padding: 6px 14px;
                border-radius: 4px 4px 0 0;
                margin-right: 2px;
                font-size: 12px;
            }}
            QTabBar::tab:selected {{
                background: {self.theme['accent']};
                color: {self.theme['accent_text']};
            }}
            QTabBar::tab:hover {{
                background: {self.theme['accent_hover']};
            }}
        """)
        layout.addWidget(self.tabs)

        self.tabs.addTab(self._create_chat_tab(), "💬 Чат")
        self.tabs.addTab(self._create_editor_tab(), "📝 Редактор")
        self.tabs.addTab(self._create_console_tab(), "🖥️ Консоль")
        self.tabs.addTab(self._create_terminal_tab(), "⚡ Терминал")
        self.tabs.addTab(self._create_logs_tab(), "📊 Логи")

        return frame

    def _create_chat_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.chat_display.setStyleSheet(f"""
            QTextEdit {{
                background-color: {self.theme['chat_bg']};
                color: {self.theme['text']};
                border-radius: 4px;
                border: none;
                font-size: 13px;
                padding: 8px;
                font-family: 'Segoe UI', sans-serif;
            }}
        """)
        layout.addWidget(self.chat_display, stretch=1)

        self.typing_label = QLabel("🤔 Z думает...")
        self.typing_label.setStyleSheet(f"color: {self.theme['info']}; font-size: 11px; padding: 2px;")
        self.typing_label.hide()
        layout.addWidget(self.typing_label)

        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Напиши задачу, вопрос по коду или просто поговори...")
        self.input_field.setStyleSheet(f"""
            QLineEdit {{
                background-color: {self.theme['input_bg']};
                color: {self.theme['text']};
                border-radius: 4px;
                border: none;
                padding: 8px 12px;
                font-size: 13px;
            }}
        """)
        self.input_field.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.input_field)

        self.send_btn = QPushButton("➤")
        self.send_btn.setFixedSize(36, 36)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setStyleSheet(f"""
            QPushButton {{
                background: {self.theme['accent']};
                color: {self.theme['accent_text']};
                border-radius: 4px;
                font-size: 16px;
                border: none;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {self.theme['accent_hover']};
            }}
        """)
        self.send_btn.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_btn)

        layout.addLayout(input_layout)
        return tab

    def _create_editor_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.file_header = QLabel("📄 Нет открытого файла")
        self.file_header.setStyleSheet(
            f"color: {self.theme['text_dim']}; font-size: 11px; "
            f"padding: 4px 8px; background: {self.theme['input_bg']}; border-radius: 4px;"
        )
        layout.addWidget(self.file_header)

        self.code_editor = CodeEditor(self.theme)
        self.code_editor.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {self.theme['code_bg']};
                color: {self.theme['text']};
                border-radius: 4px;
                border: 1px solid {self.theme['frame_border']};
                font-family: 'Consolas', monospace;
                font-size: 13px;
                padding: 4px;
                selection-background-color: {self.theme['accent']};
            }}
        """)
        self.highlighter = PythonHighlighter(self.code_editor.document(), self.theme)
        self.code_editor.cursorPositionChanged.connect(self._update_cursor_pos)
        layout.addWidget(self.code_editor, stretch=1)

        editor_buttons = QHBoxLayout()
        editor_buttons.setSpacing(4)

        for text, callback in [
            ("💾 Сохранить", self.save_current_file),
            ("▶️ Запустить", self.run_current_file),
            ("✨ Продолжить код", self.auto_complete_code),
            ("🔍 Проверить", self.lint_code),
        ]:
            btn = QPushButton(text)
            btn.setFixedHeight(28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(self._btn_style())
            btn.clicked.connect(callback)
            editor_buttons.addWidget(btn)

        editor_buttons.addStretch()
        layout.addLayout(editor_buttons)
        return tab

    def _create_console_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)

        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet(f"""
            QTextEdit {{
                background-color: {self.theme['console_bg']};
                color: {self.theme['text']};
                border-radius: 4px;
                border: 1px solid {self.theme['frame_border']};
                font-family: 'Consolas', monospace;
                font-size: 12px;
                padding: 8px;
            }}
        """)
        layout.addWidget(self.console)
        return tab

    def _create_terminal_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        quick_layout = QHBoxLayout()
        quick_layout.setSpacing(4)

        quick_label = QLabel("⚡ Быстро:")
        quick_label.setStyleSheet(f"color: {self.theme['text_dim']}; font-size: 11px;")
        quick_layout.addWidget(quick_label)

        for text, cmd in [
            ("🚀 Zeta", "start_zeta.bat"),
            ("🌐 Web", "start_web.bat"),
            ("📱 Bot", "start_zeta_bot.bat"),
            ("🛠️ Все", "start_all.bat"),
        ]:
            btn = QPushButton(text)
            btn.setFixedHeight(26)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(self._btn_style())
            btn.clicked.connect(lambda _, c=cmd: self._run_quick_command(c))
            quick_layout.addWidget(btn)

        quick_layout.addStretch()
        layout.addLayout(quick_layout)

        self.terminal_output = QTextEdit()
        self.terminal_output.setReadOnly(True)
        self.terminal_output.setStyleSheet(f"""
            QTextEdit {{
                background-color: {self.theme['console_bg']};
                color: {self.theme['text']};
                border-radius: 4px;
                border: 1px solid {self.theme['frame_border']};
                font-family: 'Consolas', monospace;
                font-size: 12px;
                padding: 8px;
            }}
        """)
        layout.addWidget(self.terminal_output, stretch=1)

        terminal_input_layout = QHBoxLayout()
        self.terminal_input = QLineEdit()
        self.terminal_input.setPlaceholderText("Введите команду (например: pip install requests)")
        self.terminal_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {self.theme['input_bg']};
                color: {self.theme['text']};
                border-radius: 4px;
                border: none;
                padding: 8px 12px;
                font-size: 13px;
                font-family: 'Consolas', monospace;
            }}
        """)
        self.terminal_input.returnPressed.connect(self.run_terminal_command)
        terminal_input_layout.addWidget(self.terminal_input)

        run_btn = QPushButton("▶️ Выполнить")
        run_btn.setFixedHeight(28)
        run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        run_btn.setStyleSheet(self._btn_style())
        run_btn.clicked.connect(self.run_terminal_command)
        terminal_input_layout.addWidget(run_btn)

        layout.addLayout(terminal_input_layout)
        return tab

    def _create_logs_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)

        for text, callback in [
            ("🔄 Обновить", self._load_logs),
            ("📂 Открыть папку", lambda: subprocess.Popen(f'explorer "{self.project_path}\\data"', shell=True)),
            ("🧹 Очистить UI", lambda: self.logs_display.clear()),
        ]:
            btn = QPushButton(text)
            btn.setFixedHeight(26)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(self._btn_style())
            btn.clicked.connect(callback)
            btn_layout.addWidget(btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.logs_display = QTextEdit()
        self.logs_display.setReadOnly(True)
        self.logs_display.setStyleSheet(f"""
            QTextEdit {{
                background-color: {self.theme['console_bg']};
                color: {self.theme['text']};
                border-radius: 4px;
                border: 1px solid {self.theme['frame_border']};
                font-family: 'Consolas', monospace;
                font-size: 11px;
                padding: 8px;
            }}
        """)
        layout.addWidget(self.logs_display)
        return tab

    def _create_right_panel(self) -> QFrame:
        frame = QFrame()
        frame.setMinimumWidth(220)
        frame.setMaximumWidth(320)
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {self.theme['sidebar_bg']};
                border-radius: 6px;
                border: 1px solid {self.theme['frame_border']};
            }}
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        title = QLabel("🛠️ ИНСТРУМЕНТЫ")
        title.setStyleSheet(f"color: {self.theme['text_dim']}; font-weight: bold; font-size: 11px;")
        layout.addWidget(title)

        tools = [
            ("🌐 Edge", self.open_edge),
            ("📝 VS Code", self.open_vscode),
            ("📁 Проводник", self.open_explorer),
            ("⚙️ Диспетчер", self.open_taskmgr),
            ("🖥️ Терминал", self.open_terminal),
            ("📋 Копировать код", self.copy_code),
            ("📂 Открыть файл", self.open_selected_file),
            ("📦 Установить пакет", self.install_package),
        ]

        for label, callback in tools:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(28)
            btn.setStyleSheet(self._btn_style())
            btn.clicked.connect(callback)
            layout.addWidget(btn)

        layout.addSpacing(8)
        git_title = QLabel("🔧 GIT")
        git_title.setStyleSheet(f"color: {self.theme['text_dim']}; font-weight: bold; font-size: 11px;")
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
            btn.setFixedHeight(26)
            btn.setStyleSheet(self._btn_style())
            btn.clicked.connect(callback)
            layout.addWidget(btn)

        layout.addStretch()

        hint = QLabel(
            "💡 Двойной клик по файлу → открыть\n"
            "💡 ПКМ в дереве → контекстное меню\n"
            "💡 Ctrl+S — сохранить\n"
            "💡 Ctrl+R — запустить\n"
            "💡 Ctrl+B — проверить"
        )
        hint.setStyleSheet(f"color: {self.theme['text_dim']}; font-size: 10px; padding: 4px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        return frame

    def _btn_style(self) -> str:
        return f"""
            QPushButton {{
                background: {self.theme['input_bg']};
                color: {self.theme['text']};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
                border: none;
                text-align: left;
            }}
            QPushButton:hover {{
                background: {self.theme['accent']};
                color: {self.theme['accent_text']};
            }}
            QPushButton:pressed {{
                background: {self.theme['accent_hover']};
            }}
        """

    def setup_hotkeys(self):
        shortcuts = [
            ("Ctrl+S", self.save_current_file),
            ("Ctrl+R", self.run_current_file),
            ("Ctrl+B", self.lint_code),
            ("Ctrl+O", self.open_file_dialog),
            ("Ctrl+Shift+V", self.open_in_vscode),
            ("Ctrl+T", lambda: self.tabs.setCurrentIndex((self.tabs.currentIndex() + 1) % self.tabs.count())),
            ("Ctrl+Shift+T", lambda: self.tabs.setCurrentIndex(3)),
            ("Ctrl+Shift+L", lambda: self.tabs.setCurrentIndex(4)),
            ("Escape", self.close),
        ]
        for key, callback in shortcuts:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(callback)

    def greet(self):
        self._append_colored(
            "Z",
            "💻 **Режим разработчика** активирован.\n"
            "Здесь я знаю Python, JS, C++, Unity, Godot, архитектуру LLM и всё остальное.\n"
            "Можешь задавать вопросы по коду, просить написать функцию или объяснить алгоритм.\n\n"
            "📁 Слева — дерево проекта (с поиском).\n"
            "📝 По центру — чат, редактор, консоль, терминал, логи.\n"
            "🛠️ Справа — инструменты и Git.\n\n"
            "💡 Горячие клавиши:\n"
            "   Ctrl+S — сохранить\n"
            "   Ctrl+R — запустить\n"
            "   Ctrl+B — проверить код\n"
            "   Ctrl+T — след. вкладка\n"
            "   Ctrl+Shift+T — терминал\n"
            "   Ctrl+Shift+L — логи",
            self.theme["accent"]
        )

    def send_message(self):
        text = self.input_field.text().strip()
        if not text:
            return

        self.input_field.clear()
        self._append_colored("Ты", text, "#4ec9b0")

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
            try:
                speak(full_text[:500])
            except Exception:
                pass

    def _on_error(self, error_msg: str):
        self.typing_label.hide()
        self.send_btn.setEnabled(True)
        self.send_btn.setText("➤")
        self._replace_last_z(error_msg)

    def _append_colored(self, sender: str, text: str, color: str):
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        fmt_name = QTextCharFormat()
        fmt_name.setForeground(QColor(color))
        fmt_name.setFontWeight(QFont.Weight.Bold)
        cursor.insertText(f"{sender}: ", fmt_name)

        self._insert_code_or_text(cursor, text)

        cursor.insertText("\n\n")
        self.chat_display.setTextCursor(cursor)
        self._scroll_to_bottom()

    def _replace_last_z(self, text: str):
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

        self._insert_code_or_text(cursor, text)

        cursor.insertText("\n")
        self.chat_display.setTextCursor(cursor)
        self._scroll_to_bottom()

    def _insert_code_or_text(self, cursor, text: str):
        if "```" not in text:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(self.theme["text"]))
            cursor.insertText(text, fmt)
            return

        parts = text.split("```")
        for i, part in enumerate(parts):
            if i % 2 == 1:
                language = "python"
                if "\n" in part:
                    first_line = part.split("\n")[0].strip()
                    if first_line in ["python", "js", "javascript", "html", "css", "bash", "bat", "json"]:
                        language = first_line
                        part = part.split("\n", 1)[1] if "\n" in part else ""

                fmt_code = QTextCharFormat()
                fmt_code.setBackground(QColor(self.theme["code_bg"]))
                fmt_code.setForeground(QColor("#d4d4d4"))
                fmt_code.setFont(QFont("Consolas", 11))
                cursor.insertText(part, fmt_code)

                fmt_break = QTextCharFormat()
                fmt_break.setForeground(QColor(self.theme["text"]))
                cursor.insertText("\n", fmt_break)
            else:
                fmt = QTextCharFormat()
                fmt.setForeground(QColor(self.theme["text"]))
                cursor.insertText(part, fmt)

    def _scroll_to_bottom(self):
        sb = self.chat_display.verticalScrollBar()
        sb.setValue(sb.maximum())

    def clear_chat(self):
        reply = QMessageBox.question(
            self, "Очистить чат",
            "Очистить все сообщения в чате?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.chat_display.clear()
            self.greet()

    def load_project_tree(self):
        self.file_tree.clear()
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
            self.status_bar.showMessage("📁 Дерево проекта загружено", 3000)

    def _populate_tree(self, path: str, parent: Optional[QTreeWidgetItem] = None):
        if not os.path.exists(path):
            return

        try:
            items = sorted(os.listdir(path))
            total = max(len(items), 1)
            processed = 0

            for item in items:
                processed += 1
                self.progress_bar.setValue(int(processed / total * 100))

                full_path = os.path.join(path, item)
                tree_parent = parent if parent else self.file_tree.invisibleRootItem()

                if item.startswith(".") or item.startswith("__"):
                    continue
                if item in ("node_modules", "venv", "__pycache__", ".git", "build", "dist"):
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

        except PermissionError:
            pass

    def _get_file_icon(self, filename: str) -> str:
        ext = os.path.splitext(filename)[1].lower()
        icons = {
            ".py": "🐍", ".js": "📜", ".ts": "📘", ".html": "🌐", ".css": "🎨",
            ".json": "📋", ".md": "📝", ".txt": "📄", ".xml": "📄", ".yaml": "📄",
            ".yml": "📄", ".toml": "📄", ".ini": "⚙️", ".cfg": "⚙️", ".conf": "⚙️",
            ".sh": "💻", ".bat": "💻", ".ps1": "💻", ".exe": "⚡", ".dll": "🔧",
            ".jpg": "🖼️", ".png": "🖼️", ".gif": "🖼️", ".svg": "🖼️",
            ".mp3": "🎵", ".mp4": "🎬", ".zip": "📦", ".rar": "📦",
        }
        return icons.get(ext, "📄")

    def _filter_tree(self, text: str):
        search = text.lower().strip()

        def filter_item(item):
            matches = search in item.text(0).lower()
            child_matches = False
            for i in range(item.childCount()):
                if filter_item(item.child(i)):
                    child_matches = True
            visible = matches or child_matches
            item.setHidden(not visible)
            return visible

        root = self.file_tree.invisibleRootItem()
        for i in range(root.childCount()):
            filter_item(root.child(i))

    def _show_tree_context_menu(self, position):
        item = self.file_tree.itemAt(position)
        if not item:
            return

        menu = QMenu(self)
        path = item.data(0, Qt.ItemDataRole.UserRole)

        if path:
            open_action = menu.addAction("📂 Открыть в редакторе")
            open_action.triggered.connect(lambda: self.on_file_double_click(item, 0))

            vscode_action = menu.addAction("🧩 Открыть в VS Code")
            vscode_action.triggered.connect(
                lambda: subprocess.Popen(["code", path], shell=True)
            )

            menu.addSeparator()

            copy_action = menu.addAction("📋 Копировать путь")
            copy_action.triggered.connect(
                lambda: QApplication.clipboard().setText(path)
            )

            explorer_action = menu.addAction("📁 Открыть в проводнике")
            if os.path.isfile(path):
                explorer_action.triggered.connect(
                    lambda: subprocess.Popen(f'explorer /select,"{path}"', shell=True)
                )
            else:
                explorer_action.triggered.connect(
                    lambda: subprocess.Popen(f'explorer "{path}"', shell=True)
                )

            menu.addSeparator()

            name_action = menu.addAction("📝 Копировать имя")
            name_action.triggered.connect(
                lambda: QApplication.clipboard().setText(os.path.basename(path))
            )

        menu.exec(self.file_tree.viewport().mapToGlobal(position))

    def expand_all(self):
        self.file_tree.expandAll()

    def collapse_all(self):
        self.file_tree.collapseAll()

    def on_file_double_click(self, item: QTreeWidgetItem, column: int):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path and os.path.isfile(path):
            self.current_file_path = path
            self.open_file_in_editor(path)

    def open_file_in_editor(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.code_editor.setPlainText(content)
            self.current_file_path = path
            self.file_header.setText(f"📄 {path}")
            self.tabs.setCurrentIndex(1)
            self.status_bar.showMessage(f"📄 Открыт: {os.path.basename(path)}", 3000)
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось открыть файл: {e}")

    def save_current_file(self):
        if not self.current_file_path:
            path, _ = QFileDialog.getSaveFileName(
                self, "Сохранить файл", "", "Python Files (*.py);;All Files (*)"
            )
            if not path:
                return
            self.current_file_path = path
            self.file_header.setText(f"📄 {path}")

        try:
            content = self.code_editor.toPlainText()
            with open(self.current_file_path, "w", encoding="utf-8") as f:
                f.write(content)
            self.status_bar.showMessage(f"💾 Сохранено: {os.path.basename(self.current_file_path)}", 3000)
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить файл: {e}")

    def _auto_save(self):
        if self.current_file_path and self.code_editor.toPlainText():
            try:
                with open(self.current_file_path, "w", encoding="utf-8") as f:
                    f.write(self.code_editor.toPlainText())
                self.status_bar.showMessage(
                    f"💾 Авто-сохранено: {os.path.basename(self.current_file_path)}", 2000
                )
            except Exception:
                pass

    def _update_cursor_pos(self):
        cursor = self.code_editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        self.cursor_pos_label.setText(f"Стр {line}, Кол {col}")

    def open_edge(self):
        subprocess.Popen("start msedge", shell=True)

    def open_vscode(self):
        subprocess.Popen("code", shell=True)

    def open_explorer(self):
        subprocess.Popen(f'explorer "{self.project_path}"', shell=True)

    def open_taskmgr(self):
        subprocess.Popen("taskmgr", shell=True)

    def open_terminal(self):
        subprocess.Popen(f'start cmd /K "cd /d {self.project_path}"', shell=True)

    def open_file_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Открыть файл", self.project_path, "Все файлы (*)"
        )
        if path:
            self.current_file_path = path
            self.open_file_in_editor(path)

    def open_in_vscode(self):
        if self.current_file_path:
            subprocess.Popen(["code", self.current_file_path], shell=True)
        else:
            subprocess.Popen(["code", self.project_path], shell=True)

    def install_package(self):
        pkg, ok = QInputDialog.getText(
            self, "Установить пакет",
            "Введите имя пакета (например: requests):"
        )
        if ok and pkg.strip():
            self.tabs.setCurrentIndex(3)
            self.terminal_input.setText(f"pip install {pkg.strip()}")
            self.run_terminal_command()

    def lint_code(self):
        code = self.code_editor.toPlainText()
        if not code:
            self._append_colored("Z", "⚠️ Редактор пуст.", self.theme["warning"])
            return

        import tempfile
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as f:
                f.write(code)
                temp_path = f.name

            result = subprocess.run(
                ["python", "-m", "py_compile", temp_path],
                capture_output=True, text=True, encoding="utf-8", errors="replace"
            )
            os.unlink(temp_path)

            if result.returncode == 0:
                self._append_colored("Z", "✅ Синтаксис корректен! Ошибок не найдено.", self.theme["success"])
                self.lint_status.setText("✅ OK")
            else:
                self._append_colored("Z", f"❌ Ошибки:\n{result.stderr}", self.theme["danger"])
                self.lint_status.setText("❌ Ошибки")
        except Exception as e:
            self._append_colored("Z", f"⚠️ Ошибка линтера: {e}", self.theme["danger"])

    def lint_project(self):
        self._append_colored("Z", "🔍 Проверяю весь проект...", self.theme["info"])
        self.tabs.setCurrentIndex(0)

        result = subprocess.run(
            ["python", "-m", "compileall", "-q", self.project_path],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=self.project_path
        )

        if result.returncode == 0:
            self._append_colored("Z", "✅ Весь проект: ошибок не найдено!", self.theme["success"])
        else:
            self._append_colored(
                "Z",
                f"❌ Найдены ошибки:\n{result.stdout[:2000]}\n{result.stderr[:1000]}",
                self.theme["danger"]
            )

    def _git(self, *args) -> str:
        try:
            result = subprocess.run(
                ["git"] + list(args),
                capture_output=True, text=True, shell=False,
                cwd=self.project_path,
                encoding="utf-8", errors="replace", timeout=30
            )
            return result.stdout if result.returncode == 0 else result.stderr
        except Exception as e:
            return f"⚠️ {e}"

    def git_status(self):
        out = self._git("status", "-sb")
        self._append_colored("📊 Git Status", out or "Чисто", self.theme["info"])

    def git_log(self):
        out = self._git("log", "-n5", "--oneline")
        self._append_colored("📈 Git Log", out or "Нет коммитов", self.theme["info"])

    def git_diff(self):
        out = self._git("diff")
        self._append_colored("📝 Git Diff", out or "Нет изменений", self.theme["info"])

    def git_commit(self):
        text, ok = QInputDialog.getText(self, "Git Commit", "Сообщение коммита:")
        if ok and text:
            self._git("add", ".")
            out = self._git("commit", "-m", text)
            self._append_colored("💾 Git Commit", out, self.theme["success"])

    def auto_commit(self):
        diff = self._git("diff", "--stat")
        prompt = f"Сообщение git commit на русском до 50 символов. Изменения: {diff[:200]}"
        try:
            msg = ask_zeta(prompt, mode="programmer").strip().split("\n")[0][:50]
        except Exception:
            msg = "Обновление проекта"

        self._git("add", ".")
        out = self._git("commit", "-m", msg)
        self._append_colored("🤖 Авто-коммит", out or f"Коммит: {msg}", self.theme["success"])

    def git_branch(self):
        out = self._git("branch", "-a")
        self._append_colored("🌿 Git Branches", out, self.theme["info"])

    def git_stash(self):
        out = self._git("stash", "save")
        self._append_colored("📦 Git Stash", out, self.theme["info"])

    def git_pull(self):
        out = self._git("pull")
        self._append_colored("🔄 Git Pull", out, self.theme["info"])

    def run_terminal_command(self):
        command = self.terminal_input.text().strip()
        if not command:
            return

        self.terminal_input.clear()
        self.terminal_output.append(f"<span style='color:#569cd6;'>$ {command}</span>")

        if self.run_process and self.run_process.isRunning():
            self.run_process.quit()
            self.run_process.wait()

        self.run_process = RunProcess(command, self.project_path)
        self.run_process.output_ready.connect(self.terminal_output.append)
        self.run_process.finished_process.connect(self.on_process_finished)
        self.run_process.start()

    def _run_quick_command(self, command: str):
        self.tabs.setCurrentIndex(3)
        self.terminal_output.append(f"<span style='color:#569cd6;'>$ {command}</span>")
        try:
            subprocess.Popen(
                f'start "" cmd /K "cd /d {self.project_path} && {command}"',
                shell=True
            )
            self.terminal_output.append(f"✅ Запущено: {command}")
        except Exception as e:
            self.terminal_output.append(f"⚠️ Ошибка: {e}")

    def on_process_finished(self, exit_code: int):
        color = "#4ec9b0" if exit_code == 0 else "#f48771"
        self.terminal_output.append(
            f"<span style='color:{color};'>✅ Завершено (код {exit_code})</span>\n"
        )

    def _load_logs(self):
        log_path = os.path.join(self.project_path, "data", "zeta.log")
        if not os.path.exists(log_path):
            self.logs_display.setPlainText("⚠️ Файл data/zeta.log не найден")
            return

        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            last = lines[-500:] if len(lines) > 500 else lines
            self.logs_display.setPlainText("".join(last))
            sb = self.logs_display.verticalScrollBar()
            sb.setValue(sb.maximum())
        except Exception as e:
            self.logs_display.setPlainText(f"⚠️ Ошибка чтения: {e}")

    def clear_console(self):
        self.console.clear()

    def auto_complete_code(self):
        code = self.code_editor.toPlainText()
        if not code:
            self._append_colored("Z", "⚠️ Редактор пуст.", self.theme["warning"])
            return

        self.status_bar.showMessage("✨ Zeta дописывает код...", 0)
        self.auto_complete_worker = AutoCompleteWorker(code)
        self.auto_complete_worker.result_ready.connect(self.on_auto_complete_result)
        self.auto_complete_worker.start()

    def on_auto_complete_result(self, result: str):
        if result and not result.startswith("# ⚠️"):
            cursor = self.code_editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText("\n" + result)
            self.status_bar.showMessage("✅ Код дополнен", 3000)
        else:
            self._append_colored("Z", result, self.theme["danger"])
            self.status_bar.showMessage("⚠️ Ошибка дополнения", 3000)

    def run_current_file(self):
        if not self.current_file_path:
            self._append_colored("Z", "⚠️ Откройте файл.", self.theme["warning"])
            return

        ext = os.path.splitext(self.current_file_path)[1].lower()

        if ext == ".py":
            cmd = ["python", self.current_file_path]
        elif ext in (".js", ".ts"):
            cmd = ["node", self.current_file_path]
        elif ext == ".bat":
            cmd = ["cmd", "/c", self.current_file_path]
        else:
            self._append_colored("Z", f"⚠️ Неподдерживаемый формат: {ext}", self.theme["warning"])
            return

        self._append_colored("Z", f"▶️ Запуск: {os.path.basename(self.current_file_path)}", self.theme["info"])
        self.tabs.setCurrentIndex(2)

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60,
                cwd=os.path.dirname(self.current_file_path),
                encoding="utf-8", errors="replace"
            )
            output = result.stdout if result.stdout else result.stderr
            self.console.append(output or "✅ Выполнено без вывода")

            if result.returncode != 0:
                self.console.append(f"❌ Код возврата: {result.returncode}")
        except subprocess.TimeoutExpired:
            self.console.append("⏱️ Таймаут выполнения")
        except Exception as e:
            self.console.append(f"⚠️ Ошибка: {e}")

    def copy_code(self):
        selected = self.chat_display.textCursor().selectedText()
        if selected:
            QApplication.clipboard().setText(selected)
            self._append_colored("Z", "📋 Скопировано", self.theme["success"])
        else:
            self._append_colored("Z", "⚠️ Выделите код", self.theme["warning"])

    def open_selected_file(self):
        selected = self.file_tree.currentItem()
        if not selected:
            self._append_colored("Z", "⚠️ Выберите файл", self.theme["warning"])
            return

        path = selected.data(0, Qt.ItemDataRole.UserRole)
        if path and os.path.isfile(path):
            self.current_file_path = path
            self.open_file_in_editor(path)

    def closeEvent(self, event):
        self._auto_save()

        for worker in (self.worker, self.auto_complete_worker, self.run_process):
            if worker and worker.isRunning():
                worker.quit()
                worker.wait()
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        super().keyPressEvent(event)


# ========== ТЕСТ ==========
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ProgrammerWindow()
    window.show()
    sys.exit(app.exec())