# -*- coding: utf-8 -*-
"""
Zeta UI — Окно входа.
Простой вход по паролю.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont


STYLE = """
QDialog {
    background-color: #1e1e2e;
    color: #cdd6f4;
}
QLabel {
    color: #cdd6f4;
    font-family: 'Segoe UI';
}
QLineEdit {
    background-color: #313244;
    color: #cdd6f4;
    border: 2px solid #45475a;
    border-radius: 8px;
    padding: 10px;
    font-size: 14px;
    font-family: 'Segoe UI';
}
QLineEdit:focus {
    border: 2px solid #89b4fa;
}
QPushButton {
    background-color: #89b4fa;
    color: #1e1e2e;
    border: none;
    border-radius: 8px;
    padding: 10px;
    font-size: 14px;
    font-weight: bold;
    font-family: 'Segoe UI';
}
QPushButton:hover {
    background-color: #b4befe;
}
QPushButton:pressed {
    background-color: #74c7ec;
}
QPushButton#cancel {
    background-color: #45475a;
    color: #cdd6f4;
}
QPushButton#cancel:hover {
    background-color: #585b70;
}
"""


class LoginWindow(QDialog):
    """Простое окно входа по паролю"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔐 Zeta — Вход")
        self.setFixedSize(400, 340)
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet(STYLE)
        
        self._build_ui()
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)
        
        # Заголовок
        title = QLabel("🤖 Zeta")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Segoe UI", 26, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # Подзаголовок
        subtitle = QLabel("Введите пароль для входа")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #a6adc8; font-size: 13px;")
        layout.addWidget(subtitle)
        
        layout.addSpacing(20)
        
        # Поле пароля
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Пароль")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.returnPressed.connect(self._try_login)
        layout.addWidget(self.password_input)
        
        # Ошибка
        self.error_label = QLabel("")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setStyleSheet("color: #f38ba8; font-size: 12px;")
        self.error_label.hide()
        layout.addWidget(self.error_label)
        
        layout.addStretch()
        
        # Кнопки
        btn_layout = QHBoxLayout()
        
        btn_cancel = QPushButton("Отмена")
        btn_cancel.setObjectName("cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        
        btn_login = QPushButton("Войти")
        btn_login.clicked.connect(self._try_login)
        btn_layout.addWidget(btn_login)
        
        layout.addLayout(btn_layout)
        
        self.password_input.setFocus()
    
    def _try_login(self):
        """Попытка входа"""
        from security.auth import get_auth
        
        password = self.password_input.text()
        
        if not password:
            self._show_error("Введите пароль")
            return
        
        auth = get_auth()
        ok, msg = auth.login(password)
        
        if ok:
            self.accept()
        else:
            self._show_error(msg)
            self.password_input.clear()
            self.password_input.setFocus()
    
    def _show_error(self, message: str):
        """Показать ошибку"""
        self.error_label.setText(message)
        self.error_label.show()
        QTimer.singleShot(5000, self.error_label.hide)


# ========== ТЕСТ ==========
if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    from security.auth import get_auth
    
    app = QApplication(sys.argv)
    
    auth = get_auth()
    if not auth.has_password():
        auth.set_password("test123")
        print("✅ Пароль установлен: test123")
    
    login = LoginWindow()
    if login.exec() == QDialog.DialogCode.Accepted:
        print("✅ Вход выполнен")
    else:
        print("❌ Вход отменён")
    
    sys.exit(0)