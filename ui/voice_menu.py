# -*- coding: utf-8 -*-
"""
Zeta UI — Меню выбора голосового режима (frameless в стиле Zeta).
Показывает всплывающее окно с 2 вариантами:
  1. 🎤 Обычный режим (нажать → говорить → стоп)
  2. 🔄 Диалоговый режим (разговор без нажатий)

ИСПРАВЛЕНО (2026-09-21):
    - Frameless окно с неоновой рамкой (как NeonFrame в widget.py)
    - Drag за любую часть окна
    - Закрытие по Esc
    - Закрытие по клику вне окна (popup-поведение)
    - Единый стиль с виджетом
    - Плавное появление (fade in)
    - Анимация hover/press на кнопках
    - Подсветка активного режима
    - Иконка окна
"""

import sys
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect
)
from PyQt6.QtCore import (
    Qt, pyqtSignal, QPropertyAnimation, QEasingCurve,
    QRectF, QTimer, QPoint
)
from PyQt6.QtGui import (
    QFont, QPainter, QColor, QPen, QLinearGradient,
    QPainterPath, QIcon, QPixmap
)


# ========== РАЗМЕРЫ ==========
MENU_WIDTH = 400
MENU_HEIGHT = 400


# ========== СОЗДАНИЕ ИКОНКИ ==========
def _create_icon() -> QIcon:
    """Иконка окна Z."""
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
    """Рамка с неоновым градиентом — как в widget.py."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("NeonFrame")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(1.5, 1.5, self.width() - 3, self.height() - 3)

        # Фон
        bg_gradient = QLinearGradient(0, 0, self.width(), self.height())
        bg_gradient.setColorAt(0.0, QColor("#030817"))
        bg_gradient.setColorAt(0.45, QColor("#050b19"))
        bg_gradient.setColorAt(1.0, QColor("#08051b"))

        path = QPainterPath()
        path.addRoundedRect(rect, 24, 24)
        painter.fillPath(path, bg_gradient)

        # Рамка (градиент)
        border_gradient = QLinearGradient(0, 0, self.width(), self.height())
        border_gradient.setColorAt(0.00, QColor("#7d38ff"))
        border_gradient.setColorAt(0.22, QColor("#228dff"))
        border_gradient.setColorAt(0.55, QColor("#9d42ff"))
        border_gradient.setColorAt(0.78, QColor("#4a5dff"))
        border_gradient.setColorAt(1.00, QColor("#b63cff"))

        painter.setPen(QPen(border_gradient, 2.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 24, 24)

        # Внутренняя тонкая рамка
        inner = rect.adjusted(3, 3, -3, -3)
        painter.setPen(QPen(QColor(50, 100, 220, 70), 1))
        painter.drawRoundedRect(inner, 21, 21)

        painter.end()


# ================================================================
#  МЕНЮ ВЫБОРА РЕЖИМА
# ================================================================

class VoiceModeMenu(QDialog):
    """Всплывающее меню выбора голосового режима (frameless в стиле Zeta)."""

    mode_selected = pyqtSignal(str)   # "normal" | "dialog"
    cancelled = pyqtSignal()

    def __init__(self, current_mode: str = None, parent=None):
        super().__init__(parent)
        self.current_mode = current_mode
        self._drag_pos: QPoint = None

        # Frameless, всегда сверху, без рамки Windows
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Dialog |
            Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("🎤 Голосовой ввод")
        self.setWindowIcon(_create_icon())
        self.setFixedSize(MENU_WIDTH, MENU_HEIGHT)
        self.setModal(True)

        # Тень окна
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setXOffset(0)
        shadow.setYOffset(0)
        shadow.setColor(QColor(60, 90, 255, 120))
        self.setGraphicsEffect(shadow)

        self._build_ui()

        # Центрирование относительно родителя
        if parent is not None:
            QTimer.singleShot(0, lambda: self._center_on_parent(parent))
        else:
            QTimer.singleShot(0, self._center_on_screen)

        # Плавное появление
        self._fade_in()

    # ========== ПОСТРОЕНИЕ UI ==========

    def _build_ui(self):
        # Внешний layout — рамка
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.frame = NeonFrame(self)
        outer.addWidget(self.frame)

        # Внутренний layout — контент
        layout = QVBoxLayout(self.frame)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # === ЗАГОЛОВОК ===
        title_row = QHBoxLayout()
        title_row.setSpacing(10)

        title_icon = QLabel("🎤")
        title_icon.setStyleSheet("font-size: 22px; background: transparent;")
        title_row.addWidget(title_icon)

        title = QLabel("Голосовой ввод")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: #89b4fa; background: transparent;")
        title_row.addWidget(title)

        title_row.addStretch()

        # Кнопка закрытия
        close_btn = QPushButton("×")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #8d98b8;
                border: none;
                font-size: 20px;
                border-radius: 8px;
            }
            QPushButton:hover {
                background: rgba(255, 100, 130, 0.2);
                color: #ff6c95;
            }
        """)
        close_btn.clicked.connect(self._on_cancel)
        title_row.addWidget(close_btn)

        layout.addLayout(title_row)

        # === ПОДСКАЗКА ===
        if self.current_mode == "normal":
            hint_text = "Активен: обычный режим"
            hint_color = "#89b4fa"
        elif self.current_mode == "dialog":
            hint_text = "Активен: диалоговый режим"
            hint_color = "#c06cff"
        else:
            hint_text = "Выберите режим:"
            hint_color = "#8d98b8"

        hint = QLabel(hint_text)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(
            f"color: {hint_color}; font-size: 12px; background: transparent;"
        )
        layout.addWidget(hint)

        layout.addSpacing(4)

        # === ОБЫЧНЫЙ РЕЖИМ ===
        self.normal_btn = self._create_mode_button(
            icon="🎤",
            title="Обычный",
            description="Нажать → говорить → стоп",
            mode="normal",
        )
        layout.addWidget(self.normal_btn)

        # === ДИАЛОГОВЫЙ РЕЖИМ ===
        self.dialog_btn = self._create_mode_button(
            icon="🔄",
            title="Диалоговый",
            description="Разговор без нажатий · тишина 3с = выход",
            mode="dialog",
        )
        layout.addWidget(self.dialog_btn)

        layout.addStretch()

        # === ОТМЕНА ===
        cancel_btn = QPushButton("✕  Отмена (Esc)")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setFixedHeight(38)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #101b35;
                color: #8d98b8;
                border: 1px solid #1c2c54;
                border-radius: 10px;
                padding: 8px 14px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #1a2842;
                color: #e8eeff;
                border: 1px solid #31417b;
            }
            QPushButton:pressed {
                background-color: #0a1428;
            }
        """)
        cancel_btn.clicked.connect(self._on_cancel)
        layout.addWidget(cancel_btn)

    def _create_mode_button(
        self,
        icon: str,
        title: str,
        description: str,
        mode: str,
    ) -> QPushButton:
        """Создать кнопку режима."""
        is_active = (self.current_mode == mode)

        if is_active:
            border_color = "#89b4fa"
            bg_color = "#1a2a4a"
            title_color = "#b4d0ff"
        else:
            border_color = "#223866"
            bg_color = "#0c1730"
            title_color = "#e8eeff"

        # Контейнер кнопки — QPushButton с двумя QLabel внутри
        button = QPushButton()
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumHeight(84)
        button.setSizePolicy(
            button.sizePolicy().horizontalPolicy(),
            button.sizePolicy().verticalPolicy()
        )

        active_badge = "  ✅" if is_active else ""

        button.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg_color};
                border: 2px solid {border_color};
                border-radius: 14px;
                padding: 12px 16px;
                text-align: left;
            }}
            QPushButton:hover {{
                background-color: #1e3a5f;
                border: 2px solid #89b4fa;
            }}
            QPushButton:pressed {{
                background-color: #172a4a;
                border: 2px solid #a8c7ff;
            }}
        """)

        # Внутренний layout с двумя строками
        inner = QVBoxLayout(button)
        inner.setContentsMargins(18, 10, 18, 10)
        inner.setSpacing(4)

        # Строка 1: иконка + название + бейдж
        row1 = QHBoxLayout()
        row1.setSpacing(10)

        icon_label = QLabel(icon)
        icon_label.setStyleSheet(
            "font-size: 22px; background: transparent; border: none;"
        )
        row1.addWidget(icon_label)

        title_label = QLabel(f"{title}{active_badge}")
        title_label.setStyleSheet(
            f"color: {title_color}; "
            f"font-size: 15px; "
            f"font-weight: 700; "
            f"background: transparent; "
            f"border: none;"
        )
        row1.addWidget(title_label)
        row1.addStretch()
        inner.addLayout(row1)

        # Строка 2: описание
        desc_label = QLabel(description)
        desc_label.setStyleSheet(
            "color: #8d98b8; "
            "font-size: 11px; "
            "background: transparent; "
            "border: none; "
            "padding-left: 32px;"
        )
        desc_label.setWordWrap(True)
        inner.addWidget(desc_label)

        button.clicked.connect(lambda: self._on_select(mode))
        return button

    # ========== ЦЕНТРИРОВАНИЕ ==========

    def _center_on_parent(self, parent):
        """Центрировать относительно родителя."""
        try:
            parent_geo = parent.frameGeometry()
            self.move(
                parent_geo.center().x() - self.width() // 2,
                parent_geo.center().y() - self.height() // 2,
            )
        except Exception:
            self._center_on_screen()

    def _center_on_screen(self):
        """Центрировать на экране."""
        try:
            from PyQt6.QtWidgets import QApplication
            screen = QApplication.primaryScreen().availableGeometry()
            self.move(
                screen.center().x() - self.width() // 2,
                screen.center().y() - self.height() // 2,
            )
        except Exception:
            pass

    # ========== АНИМАЦИЯ ПОЯВЛЕНИЯ ==========

    def _fade_in(self):
        """Плавное появление."""
        self.setWindowOpacity(0.0)
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(180)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_anim.start()

    # ========== DRAG ОКНА ==========

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.pos()
            )
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            self._drag_pos is not None
            and event.buttons() == Qt.MouseButton.LeftButton
        ):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    # ========== ЗАКРЫТИЕ ПО ESC ==========

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._on_cancel()
            return
        super().keyPressEvent(event)

    # ========== ЗАКРЫТИЕ ПО КЛИКУ ВНЕ ==========

    def showEvent(self, event):
        """Взводим фильтр для клика вне после показа."""
        super().showEvent(event)
        # Даём окну отрисоваться и ставим фильтр
        QTimer.singleShot(100, self._install_outside_click_filter)

    def _install_outside_click_filter(self):
        """Устанавливаем event-фильтр на приложение."""
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event):
        """
        Закрывает окно, если клик был вне рамки.
        """
        if event.type() == event.Type.MouseButtonPress:
            try:
                # Позиция клика в глобальных координатах
                pos = event.globalPosition().toPoint()
                if not self.frameGeometry().contains(pos):
                    # Исключаем клик по самому окну
                    self._on_cancel()
                    return True
            except Exception:
                pass
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        """Убираем фильтр при закрытии."""
        try:
            from PyQt6.QtWidgets import QApplication
            QApplication.instance().removeEventFilter(self)
        except Exception:
            pass
        super().closeEvent(event)

    # ========== ВЫБОР ==========

    def _on_select(self, mode: str):
        self.mode_selected.emit(mode)
        self.accept()

    def _on_cancel(self):
        self.cancelled.emit()
        self.reject()


# ========== ТЕСТ ==========
if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    print("🎤 Тест меню выбора режима")
    print("=" * 50)
    print("Esc — закрыть")
    print("Клик вне окна — закрыть")
    print("Перетаскивай мышью за любое место")

    menu = VoiceModeMenu(current_mode=None)

    def on_mode(mode):
        print(f"✅ Выбран режим: {mode}")

    def on_cancel():
        print("❌ Отменено")

    menu.mode_selected.connect(on_mode)
    menu.cancelled.connect(on_cancel)

    result = menu.exec()

    print(f"Результат: {result}")
    sys.exit(0)