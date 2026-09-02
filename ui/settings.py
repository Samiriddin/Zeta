# -*- coding: utf-8 -*-
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QCheckBox, QFileDialog,
    QMessageBox, QScrollArea, QLineEdit, QSpinBox,
    QDoubleSpinBox, QTabWidget, QGroupBox, QSlider
)
from PyQt6.QtCore import Qt, pyqtSignal

from core.memory import save_setting, get_setting, clear_history, get_db_stats
from modules.notifications import add_reminder, clear_reminders


# ========== КАРТА ГОЛОСОВ ==========
VOICE_MAP = {
    "Светлана (женский, RU)": "ru-RU-SvetlanaNeural",
    "Дарья (женский, RU)": "ru-RU-DariyaNeural",
    "Дмитрий (мужской, RU)": "ru-RU-DmitryNeural",
    "Поліна (женский, UA)": "uk-UA-PolinaNeural",
    "Ария (женский, EN)": "en-US-AriaNeural",
    "Гай (мужской, EN)": "en-US-GuyNeural",
}

# ========== КАРТА МОДЕЛЕЙ ==========
MODEL_MAP = {
    "zeta-universal (ТВОЯ МОДЕЛЬ!)": "zeta-universal",
}

# ========== КАРТА ТЕМ ==========
THEMES = {
    "dark": {
        "bg": "#1e1e2e",
        "text": "#cdd6f4",
        "text_secondary": "#a6adc8",
        "input": "#313244",
        "accent": "#89b4fa",
        "border": "#313244",
    },
    "light": {
        "bg": "#eff1f5",
        "text": "#4c4f69",
        "text_secondary": "#6c6f85",
        "input": "#dce0e8",
        "accent": "#1e66f5",
        "border": "#ccd0da",
    },
}


class SettingsWindow(QWidget):
    """Окно настроек Zeta с вкладками и моментальным применением."""

    settings_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.Window)
        self.setWindowTitle("⚙️ Настройки Z")
        self.setFixedSize(550, 750)
        self.avatar_path = get_setting("avatar_path", "")
        self.theme_name = get_setting("theme", "dark")
        self.theme = THEMES.get(self.theme_name, THEMES["dark"])
        self.setStyleSheet(f"background-color: {self.theme['bg']}; color: {self.theme['text']};")

        self.init_ui()
        self.apply_theme()

    def apply_theme(self):
        """Применяет тему к окну."""
        self.setStyleSheet(f"background-color: {self.theme['bg']}; color: {self.theme['text']};")

    # ========== UI ==========

    def init_ui(self):
        """Создаёт интерфейс с вкладками."""
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"border: none; background: {self.theme['bg']};")
        scroll.setFixedSize(550, 750)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        title = QLabel("⚙️ Настройки Z")
        title.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {self.theme['accent']};")
        layout.addWidget(title)

        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                background: {self.theme['bg']};
                border: 1px solid {self.theme['border']};
                border-radius: 8px;
                padding: 10px;
            }}
            QTabBar::tab {{
                background: {self.theme['input']};
                color: {self.theme['text']};
                padding: 8px 16px;
                border-radius: 8px 8px 0 0;
                margin-right: 4px;
            }}
            QTabBar::tab:selected {{
                background: {self.theme['accent']};
                color: {self.theme['bg']};
            }}
            QTabBar::tab:hover {{
                background: {self.theme['input']};
            }}
        """)

        tabs.addTab(self._create_ui_tab(), "🎨 Внешний вид")
        tabs.addTab(self._create_voice_tab(), "🔊 Голос")
        tabs.addTab(self._create_ai_tab(), "🧠 ИИ")
        tabs.addTab(self._create_notifications_tab(), "🔔 Уведомления")
        tabs.addTab(self._create_animations_tab(), "✨ Анимации")
        tabs.addTab(self._create_security_tab(), "🔒 Безопасность")
        tabs.addTab(self._create_tools_tab(), "🛠️ Инструменты")
        tabs.addTab(self._create_rag_tab(), "📄 RAG")
        tabs.addTab(self._create_data_tab(), "🗄️ Данные")

        layout.addWidget(tabs)

        note = QLabel("Все изменения сохраняются автоматически! Нажмите 'Сохранить' для применения.")
        note.setStyleSheet(f"color: {self.theme['text_secondary']}; font-size: 11px;")
        note.setWordWrap(True)
        layout.addWidget(note)

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("💾 Сохранить")
        save_btn.setStyleSheet(self._btn_primary())
        save_btn.clicked.connect(self.save_settings)

        close_btn = QPushButton("✕ Закрыть")
        close_btn.setStyleSheet(self._btn_secondary())
        close_btn.clicked.connect(self.close)

        reset_btn = QPushButton("↩️ Сбросить")
        reset_btn.setStyleSheet(self._btn_danger())
        reset_btn.clicked.connect(self.reset_settings)

        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(reset_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        # Автор и версия
        footer = QLabel("Zeta v3.0 — Создатель: Samriddin (Самир) 🇺🇿")
        footer.setStyleSheet(f"color: {self.theme['text_secondary']}; font-size: 10px;")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(footer)

        scroll.setWidget(container)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    # ========== ВКЛАДКА: ВНЕШНИЙ ВИД ==========

    def _create_ui_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        layout.addWidget(self._section("🎨 Внешний вид"))

        layout.addWidget(self._label("Тема:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["dark", "light"])
        self.theme_combo.setCurrentText(get_setting("theme", "dark"))
        self.theme_combo.setStyleSheet(self._combo_style())
        self.theme_combo.currentTextChanged.connect(self.on_theme_changed)
        layout.addWidget(self.theme_combo)

        layout.addWidget(self._label("Размер виджета:"))
        self.size_combo = QComboBox()
        self.size_combo.addItems(["S", "M", "L", "XL"])
        self.size_combo.setCurrentText(get_setting("widget_size", "M"))
        self.size_combo.setStyleSheet(self._combo_style())
        self.size_combo.currentTextChanged.connect(self.on_size_changed)
        layout.addWidget(self.size_combo)

        layout.addWidget(self._label("Аватарка:"))
        av_layout = QHBoxLayout()
        self.avatar_label = QLabel(
            self.avatar_path.split("/")[-1].split("\\")[-1] if self.avatar_path else "Не выбрана"
        )
        self.avatar_label.setStyleSheet(f"color: {self.theme['text_secondary']}; font-size: 12px;")
        av_btn = QPushButton("📁 Выбрать")
        av_btn.setStyleSheet(self._btn_secondary())
        av_btn.clicked.connect(self.choose_avatar)
        av_layout.addWidget(self.avatar_label)
        av_layout.addWidget(av_btn)
        layout.addLayout(av_layout)

        pos_label = QLabel("Виджет всегда в правом нижнем углу (перетаскивается мышью)")
        pos_label.setStyleSheet(f"color: {self.theme['text_secondary']}; font-size: 11px;")
        pos_label.setWordWrap(True)
        layout.addWidget(pos_label)

        layout.addWidget(self._label("Прозрачность виджета:"))
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(50, 100)
        self.opacity_slider.setValue(int(float(get_setting("widget_opacity", "1.0")) * 100))
        self.opacity_slider.setStyleSheet(self._slider_style())
        self.opacity_slider.valueChanged.connect(self.on_opacity_changed)
        layout.addWidget(self.opacity_slider)

        self.opacity_label = QLabel(f"{self.opacity_slider.value()}%")
        self.opacity_label.setStyleSheet(f"color: {self.theme['text_secondary']}; font-size: 12px;")
        layout.addWidget(self.opacity_label)

        layout.addStretch()
        return widget

    def _slider_style(self):
        return f"""
            QSlider::groove:horizontal {{
                height: 6px;
                background: {self.theme['input']};
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {self.theme['accent']};
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }}
            QSlider::sub-page:horizontal {{
                background: {self.theme['accent']};
                border-radius: 3px;
            }}
        """

    def on_theme_changed(self, value: str):
        save_setting("theme", value)
        self.settings_changed.emit()
        self.theme_name = value
        self.theme = THEMES.get(value, THEMES["dark"])
        self.apply_theme()
        self.refresh_style()

    def refresh_style(self):
        """Обновляет стили после смены темы."""
        self.setStyleSheet(f"background-color: {self.theme['bg']}; color: {self.theme['text']};")
        self.title_label.setStyleSheet(f"color: {self.theme['accent']};")
        # Можно добавить обновление остальных элементов

    def on_size_changed(self, value: str):
        save_setting("widget_size", value)
        self.settings_changed.emit()

    def on_opacity_changed(self, value: int):
        self.opacity_label.setText(f"{value}%")
        save_setting("widget_opacity", str(value / 100))
        self.settings_changed.emit()

    # ========== ВКЛАДКА: ГОЛОС ==========

    def _create_voice_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        layout.addWidget(self._section("🔊 Голос"))

        self.voice_check = QCheckBox("Голос включён")
        self.voice_check.setChecked(get_setting("voice_enabled", "true") == "true")
        self.voice_check.setStyleSheet(f"color: {self.theme['text']}; font-size: 13px;")
        self.voice_check.toggled.connect(self.on_voice_toggled)
        layout.addWidget(self.voice_check)

        layout.addWidget(self._label("Голос TTS:"))
        self.tts_voice_combo = QComboBox()
        self.tts_voice_combo.addItems(list(VOICE_MAP.keys()))
        saved_voice_code = get_setting("tts_voice", "ru-RU-SvetlanaNeural")
        for name, code in VOICE_MAP.items():
            if code == saved_voice_code:
                self.tts_voice_combo.setCurrentText(name)
                break
        self.tts_voice_combo.setStyleSheet(self._combo_style())
        self.tts_voice_combo.currentTextChanged.connect(self.on_voice_changed)
        layout.addWidget(self.tts_voice_combo)

        layout.addWidget(self._label("Скорость речи (1-10):"))
        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(1, 10)
        self.speed_spin.setValue(int(get_setting("tts_speed", "5")))
        self.speed_spin.setStyleSheet(self._spin_style())
        self.speed_spin.valueChanged.connect(self.on_speed_changed)
        layout.addWidget(self.speed_spin)

        test_btn = QPushButton("🔊 Тест голоса")
        test_btn.setStyleSheet(self._btn_secondary())
        test_btn.clicked.connect(self.test_voice)
        layout.addWidget(test_btn)

        layout.addStretch()
        return widget

    def on_voice_toggled(self, checked: bool):
        save_setting("voice_enabled", "true" if checked else "false")
        self.settings_changed.emit()

    def on_voice_changed(self, value: str):
        voice_code = VOICE_MAP.get(value, "ru-RU-SvetlanaNeural")
        save_setting("tts_voice", voice_code)

    def on_speed_changed(self, value: int):
        save_setting("tts_speed", str(value))

    def test_voice(self):
        try:
            from voice.tts import speak
            voice_name = self.tts_voice_combo.currentText()
            voice_code = VOICE_MAP.get(voice_name, "ru-RU-SvetlanaNeural")
            speed = self.speed_spin.value()
            speak(f"Привет! Это тест голоса {voice_name}. Как слышно?", voice=voice_code, speed=speed)
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось воспроизвести голос: {e}")

    # ========== ВКЛАДКА: ИИ ==========

    def _create_ai_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        layout.addWidget(self._section("🧠 ИИ"))

        layout.addWidget(self._label("Модель ИИ (чат):"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(list(MODEL_MAP.keys()))
        saved_model = get_setting("ai_model", "qwen2.5:7b")
        for name, code in MODEL_MAP.items():
            if code == saved_model:
                self.model_combo.setCurrentText(name)
                break
        self.model_combo.setStyleSheet(self._combo_style())
        self.model_combo.currentTextChanged.connect(self.on_model_changed)
        layout.addWidget(self.model_combo)

        layout.addWidget(self._label("Длина истории (токенов):"))
        self.context_spin = QSpinBox()
        self.context_spin.setRange(500, 8000)
        self.context_spin.setSingleStep(500)
        self.context_spin.setValue(int(get_setting("context_tokens", "2000")))
        self.context_spin.setStyleSheet(self._spin_style())
        self.context_spin.valueChanged.connect(self.on_context_changed)
        layout.addWidget(self.context_spin)

        layout.addWidget(self._label("Креативность (0.1-2.0):"))
        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(0.1, 2.0)
        self.temp_spin.setSingleStep(0.1)
        self.temp_spin.setValue(float(get_setting("ai_temperature", "0.7")))
        self.temp_spin.setStyleSheet(self._spin_style())
        self.temp_spin.valueChanged.connect(self.on_temperature_changed)
        layout.addWidget(self.temp_spin)

        layout.addWidget(self._label("Макс. длина ответа (токенов):"))
        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(100, 4000)
        self.max_tokens_spin.setSingleStep(100)
        self.max_tokens_spin.setValue(int(get_setting("max_tokens", "1024")))
        self.max_tokens_spin.setStyleSheet(self._spin_style())
        self.max_tokens_spin.valueChanged.connect(self.on_max_tokens_changed)
        layout.addWidget(self.max_tokens_spin)

        layout.addStretch()
        return widget

    def on_model_changed(self, value: str):
        model_code = MODEL_MAP.get(value, "qwen2.5:7b")
        save_setting("ai_model", model_code)
        self.settings_changed.emit()

    def on_temperature_changed(self, value: float):
        save_setting("ai_temperature", str(value))

    def on_context_changed(self, value: int):
        save_setting("context_tokens", str(value))

    def on_max_tokens_changed(self, value: int):
        save_setting("max_tokens", str(value))

    # ========== ВКЛАДКА: УВЕДОМЛЕНИЯ ==========

    def _create_notifications_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        layout.addWidget(self._section("🔔 Умные уведомления"))

        self.notif_check = QCheckBox("Умные уведомления включены")
        self.notif_check.setChecked(get_setting("smart_notifications", "true") == "true")
        self.notif_check.setStyleSheet(f"color: {self.theme['text']}; font-size: 13px;")
        self.notif_check.toggled.connect(self.on_notif_toggled)
        layout.addWidget(self.notif_check)

        layout.addWidget(self._label("CPU порог (%):"))
        self.cpu_threshold_spin = QSpinBox()
        self.cpu_threshold_spin.setRange(50, 95)
        self.cpu_threshold_spin.setValue(int(get_setting("cpu_threshold", "80")))
        self.cpu_threshold_spin.setStyleSheet(self._spin_style())
        self.cpu_threshold_spin.valueChanged.connect(self.on_cpu_threshold_changed)
        layout.addWidget(self.cpu_threshold_spin)

        layout.addWidget(self._label("RAM порог (%):"))
        self.ram_threshold_spin = QSpinBox()
        self.ram_threshold_spin.setRange(50, 95)
        self.ram_threshold_spin.setValue(int(get_setting("ram_threshold", "85")))
        self.ram_threshold_spin.setStyleSheet(self._spin_style())
        self.ram_threshold_spin.valueChanged.connect(self.on_ram_threshold_changed)
        layout.addWidget(self.ram_threshold_spin)

        layout.addWidget(self._label("Диск порог (%):"))
        self.disk_threshold_spin = QSpinBox()
        self.disk_threshold_spin.setRange(50, 95)
        self.disk_threshold_spin.setValue(int(get_setting("disk_threshold", "90")))
        self.disk_threshold_spin.setStyleSheet(self._spin_style())
        self.disk_threshold_spin.valueChanged.connect(self.on_disk_threshold_changed)
        layout.addWidget(self.disk_threshold_spin)

        layout.addWidget(self._label("Интервал проверки (сек):"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(10, 300)
        self.interval_spin.setSingleStep(10)
        self.interval_spin.setValue(int(get_setting("notif_interval", "30")))
        self.interval_spin.setStyleSheet(self._spin_style())
        self.interval_spin.valueChanged.connect(self.on_interval_changed)
        layout.addWidget(self.interval_spin)

        test_btn = QPushButton("🔔 Тест уведомления")
        test_btn.setStyleSheet(self._btn_secondary())
        test_btn.clicked.connect(self.test_notification)
        layout.addWidget(test_btn)

        layout.addStretch()
        return widget

    def on_notif_toggled(self, checked: bool):
        save_setting("smart_notifications", "true" if checked else "false")

    def on_cpu_threshold_changed(self, value: int):
        save_setting("cpu_threshold", str(value))

    def on_ram_threshold_changed(self, value: int):
        save_setting("ram_threshold", str(value))

    def on_disk_threshold_changed(self, value: int):
        save_setting("disk_threshold", str(value))

    def on_interval_changed(self, value: int):
        save_setting("notif_interval", str(value))

    def test_notification(self):
        """Тест уведомления."""
        try:
            from modules.smart_notifier import _notifier
            _notifier._notify("🔔 Тест уведомления", "Это тестовое уведомление от Zeta!")
            QMessageBox.information(self, "Готово", "Тестовое уведомление отправлено!")
        except ImportError:
            QMessageBox.warning(self, "Ошибка", "Модуль smart_notifier не найден.")
        except AttributeError:
            QMessageBox.warning(self, "Ошибка", "Ошибка в модуле smart_notifier. Проверьте установку.")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось отправить уведомление: {e}")

    # ========== ВКЛАДКА: АНИМАЦИИ ==========

    def _create_animations_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        layout.addWidget(self._section("✨ Анимации"))

        self.anim_check = QCheckBox("Плавные анимации включены")
        self.anim_check.setChecked(get_setting("animations_enabled", "true") == "true")
        self.anim_check.setStyleSheet(f"color: {self.theme['text']}; font-size: 13px;")
        self.anim_check.toggled.connect(self.on_animations_toggled)
        layout.addWidget(self.anim_check)

        layout.addWidget(self._label("Скорость анимаций (мс):"))
        self.anim_speed_spin = QSpinBox()
        self.anim_speed_spin.setRange(100, 2000)
        self.anim_speed_spin.setSingleStep(100)
        self.anim_speed_spin.setValue(int(get_setting("anim_speed", "300")))
        self.anim_speed_spin.setStyleSheet(self._spin_style())
        self.anim_speed_spin.valueChanged.connect(self.on_anim_speed_changed)
        layout.addWidget(self.anim_speed_spin)

        layout.addWidget(self._label("Эффект появления:"))
        self.anim_effect_combo = QComboBox()
        self.anim_effect_combo.addItems(["Fade In", "Slide Up", "Bounce", "None"])
        self.anim_effect_combo.setCurrentText(get_setting("anim_effect", "Fade In"))
        self.anim_effect_combo.setStyleSheet(self._combo_style())
        self.anim_effect_combo.currentTextChanged.connect(self.on_anim_effect_changed)
        layout.addWidget(self.anim_effect_combo)

        layout.addStretch()
        return widget

    def on_animations_toggled(self, checked: bool):
        save_setting("animations_enabled", "true" if checked else "false")
        self.settings_changed.emit()

    def on_anim_speed_changed(self, value: int):
        save_setting("anim_speed", str(value))
        self.settings_changed.emit()

    def on_anim_effect_changed(self, value: str):
        save_setting("anim_effect", value)
        self.settings_changed.emit()

    # ========== ВКЛАДКА: БЕЗОПАСНОСТЬ ==========

    def _create_security_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        layout.addWidget(self._section("🔒 Безопасность"))

        self.safety_check = QCheckBox("Защита от токсичных ответов")
        self.safety_check.setChecked(get_setting("safety_enabled", "true") == "true")
        self.safety_check.setStyleSheet(f"color: {self.theme['text']}; font-size: 13px;")
        self.safety_check.toggled.connect(self.on_safety_toggled)
        layout.addWidget(self.safety_check)

        self.git_protection_check = QCheckBox("Защита от опасных Git-команд")
        self.git_protection_check.setChecked(get_setting("git_protection_enabled", "true") == "true")
        self.git_protection_check.setStyleSheet(f"color: {self.theme['text']}; font-size: 13px;")
        self.git_protection_check.toggled.connect(self.on_git_protection_toggled)
        layout.addWidget(self.git_protection_check)

        layout.addWidget(self._label("Максимальная длина запроса (символов):"))
        self.max_query_spin = QSpinBox()
        self.max_query_spin.setRange(100, 5000)
        self.max_query_spin.setSingleStep(100)
        self.max_query_spin.setValue(int(get_setting("max_query_length", "2000")))
        self.max_query_spin.setStyleSheet(self._spin_style())
        self.max_query_spin.valueChanged.connect(self.on_max_query_changed)
        layout.addWidget(self.max_query_spin)

        layout.addStretch()
        return widget

    def on_safety_toggled(self, checked: bool):
        save_setting("safety_enabled", "true" if checked else "false")

    def on_git_protection_toggled(self, checked: bool):
        save_setting("git_protection_enabled", "true" if checked else "false")

    def on_max_query_changed(self, value: int):
        save_setting("max_query_length", str(value))

    # ========== ВКЛАДКА: ИНСТРУМЕНТЫ ==========

    def _create_tools_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        layout.addWidget(self._section("🛠️ Инструменты"))

        # Очистка кеша
        self.clear_cache_btn = QPushButton("🧹 Очистить кеш")
        self.clear_cache_btn.setStyleSheet(self._btn_secondary())
        self.clear_cache_btn.clicked.connect(self.clear_cache)
        layout.addWidget(self.clear_cache_btn)

        # Резервное копирование
        self.backup_btn = QPushButton("💾 Создать резервную копию БД")
        self.backup_btn.setStyleSheet(self._btn_secondary())
        self.backup_btn.clicked.connect(self.backup_db)
        layout.addWidget(self.backup_btn)

        # Очистка напоминаний
        self.clear_reminders_btn = QPushButton("🗑️ Очистить напоминания")
        self.clear_reminders_btn.setStyleSheet(self._btn_danger())
        self.clear_reminders_btn.clicked.connect(self.clear_reminders)
        layout.addWidget(self.clear_reminders_btn)

        layout.addStretch()
        return widget

    def clear_cache(self):
        """Очищает кеш."""
        try:
            import sqlite3
            from core.ai_engine import CACHE_DB
            conn = sqlite3.connect(CACHE_DB)
            conn.execute("DELETE FROM cache")
            conn.commit()
            conn.close()
            QMessageBox.information(self, "Готово", "Кеш очищен.")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось очистить кеш: {e}")

    def backup_db(self):
        """Создаёт резервную копию БД."""
        try:
            from core.memory import DB_PATH
            import shutil
            from datetime import datetime

            backup_name = f"zeta_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            backup_path, _ = QFileDialog.getSaveFileName(
                self, "Сохранить резервную копию", backup_name, "База данных (*.db)"
            )
            if backup_path:
                shutil.copy2(DB_PATH, backup_path)
                QMessageBox.information(self, "Готово", f"Резервная копия сохранена в {backup_path}")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось создать копию: {e}")

    def clear_reminders(self):
        """Очищает напоминания."""
        try:
            clear_reminders()
            QMessageBox.information(self, "Готово", "Напоминания очищены.")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось очистить напоминания: {e}")

    # ========== ВКЛАДКА: RAG ==========

    def _create_rag_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        layout.addWidget(self._section("📄 RAG (Работа с документами)"))

        self.rag_check = QCheckBox("RAG включён")
        self.rag_check.setChecked(get_setting("rag_enabled", "true") == "true")
        self.rag_check.setStyleSheet(f"color: {self.theme['text']}; font-size: 13px;")
        self.rag_check.toggled.connect(self.on_rag_toggled)
        layout.addWidget(self.rag_check)

        layout.addWidget(self._label("Максимум результатов поиска:"))
        self.rag_results_spin = QSpinBox()
        self.rag_results_spin.setRange(1, 10)
        self.rag_results_spin.setValue(int(get_setting("rag_max_results", "5")))
        self.rag_results_spin.setStyleSheet(self._spin_style())
        self.rag_results_spin.valueChanged.connect(self.on_rag_results_changed)
        layout.addWidget(self.rag_results_spin)

        self.clear_rag_btn = QPushButton("🗑️ Очистить документы")
        self.clear_rag_btn.setStyleSheet(self._btn_danger())
        self.clear_rag_btn.clicked.connect(self.clear_rag_documents)
        layout.addWidget(self.clear_rag_btn)

        layout.addStretch()
        return widget

    def on_rag_toggled(self, checked: bool):
        save_setting("rag_enabled", "true" if checked else "false")
        self.settings_changed.emit()

    def on_rag_results_changed(self, value: int):
        save_setting("rag_max_results", str(value))

    def clear_rag_documents(self):
        """Очищает документы RAG."""
        try:
            from modules.rag import clear_all_documents
            clear_all_documents()
            QMessageBox.information(self, "Готово", "Документы RAG очищены.")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось очистить документы: {e}")

    # ========== ВКЛАДКА: ДАННЫЕ ==========

    def _create_data_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        layout.addWidget(self._section("🗄️ Данные"))

        stats = get_db_stats()
        self.stats_label = QLabel(
            f"💬 Сообщений: {stats.get('messages', 0)}  |  🧠 Фактов: {stats.get('facts', 0)}  |  ⚙️ Настроек: {stats.get('settings', 0)}"
        )
        self.stats_label.setStyleSheet(f"color: {self.theme['text_secondary']}; font-size: 12px; padding: 4px;")
        layout.addWidget(self.stats_label)

        refresh_btn = QPushButton("🔄 Обновить статистику")
        refresh_btn.setStyleSheet(self._btn_secondary())
        refresh_btn.clicked.connect(self.refresh_stats)
        layout.addWidget(refresh_btn)

        clear_btn = QPushButton("🗑️ Очистить историю чата")
        clear_btn.setStyleSheet(self._btn_danger())
        clear_btn.clicked.connect(self.clear_chat_history)
        layout.addWidget(clear_btn)

        clear_facts_btn = QPushButton("🧠 Очистить факты о пользователе")
        clear_facts_btn.setStyleSheet(self._btn_danger())
        clear_facts_btn.clicked.connect(self.clear_facts)
        layout.addWidget(clear_facts_btn)

        export_btn = QPushButton("💾 Экспортировать настройки")
        export_btn.setStyleSheet(self._btn_secondary())
        export_btn.clicked.connect(self.export_settings)
        layout.addWidget(export_btn)

        layout.addWidget(self._label("Путь к проектам:"))
        self.project_path_input = QLineEdit()
        self.project_path_input.setPlaceholderText("D:\\Projects")
        self.project_path_input.setText(get_setting("project_path", "D:\\Zeta"))
        self.project_path_input.setStyleSheet(self._input_style())
        self.project_path_input.textChanged.connect(self.on_project_path_changed)
        layout.addWidget(self.project_path_input)

        layout.addStretch()
        return widget

    def on_project_path_changed(self, value: str):
        save_setting("project_path", value)

    # ========== СТИЛИ ==========

    def _section(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {self.theme['accent']}; margin-top: 4px;")
        return lbl

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {self.theme['text_secondary']}; font-size: 12px; margin-top: 4px;")
        return lbl

    def _combo_style(self):
        return f"""
            QComboBox {{
                background: {self.theme['input']};
                color: {self.theme['text']};
                border-radius: 8px;
                padding: 6px;
                border: none;
            }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background: {self.theme['input']};
                color: {self.theme['text']};
                selection-background-color: {self.theme['accent']};
            }}
        """

    def _spin_style(self):
        return f"""
            QSpinBox, QDoubleSpinBox {{
                background: {self.theme['input']};
                color: {self.theme['text']};
                border-radius: 8px;
                padding: 6px;
                border: none;
            }}
            QSpinBox::up-button, QSpinBox::down-button,
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
                background: {self.theme['input']};
                border-radius: 4px;
                width: 16px;
            }}
        """

    def _input_style(self):
        return f"""
            QLineEdit {{
                background: {self.theme['input']};
                color: {self.theme['text']};
                border-radius: 8px;
                padding: 8px;
                border: none;
            }}
        """

    def _btn_primary(self):
        return f"""
            QPushButton {{
                background: {self.theme['accent']};
                color: {self.theme['bg']};
                border-radius: 8px;
                padding: 10px 16px;
                border: none;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {self.theme['accent']}; }}
        """

    def _btn_secondary(self):
        return f"""
            QPushButton {{
                background: {self.theme['input']};
                color: {self.theme['text']};
                border-radius: 8px;
                padding: 8px 14px;
                border: none;
            }}
            QPushButton:hover {{ background: {self.theme['input']}; }}
        """

    def _btn_danger(self):
        return f"""
            QPushButton {{
                background: {self.theme['input']};
                color: {self.theme['accent']};
                border-radius: 8px;
                padding: 8px 14px;
                border: 1px solid {self.theme['accent']};
            }}
            QPushButton:hover {{
                background: {self.theme['accent']};
                color: {self.theme['bg']};
            }}
        """

    # ========== МЕТОДЫ ==========

    def choose_avatar(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбери аватарку", "", "Изображения (*.png *.jpg *.jpeg *.gif *.bmp)"
        )
        if path:
            self.avatar_path = path
            self.avatar_label.setText(path.replace("\\", "/").split("/")[-1])
            save_setting("avatar_path", self.avatar_path)
            self.settings_changed.emit()

    def refresh_stats(self):
        stats = get_db_stats()
        self.stats_label.setText(
            f"💬 Сообщений: {stats.get('messages', 0)}  |  🧠 Фактов: {stats.get('facts', 0)}  |  ⚙️ Настроек: {stats.get('settings', 0)}"
        )

    def clear_chat_history(self):
        reply = QMessageBox.question(
            self, "Подтверждение",
            "Удалить всю историю сообщений?\nФакты о пользователе останутся.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            clear_history()
            self.refresh_stats()
            QMessageBox.information(self, "Готово", "История чата очищена.")

    def clear_facts(self):
        reply = QMessageBox.question(
            self, "Подтверждение",
            "Удалить все факты о пользователе?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                import sqlite3
                from core.memory import DB_PATH
                conn = sqlite3.connect(DB_PATH)
                conn.execute("DELETE FROM facts")
                conn.commit()
                conn.close()
                self.refresh_stats()
                QMessageBox.information(self, "Готово", "Факты очищены.")
            except Exception as e:
                QMessageBox.warning(self, "Ошибка", f"Не удалось очистить факты: {e}")

    def export_settings(self):
        try:
            import json
            settings = {}
            keys = [
                "theme", "voice_enabled", "tts_voice", "tts_speed", "widget_size",
                "avatar_path", "ai_model", "context_tokens", "project_path",
                "widget_opacity", "ai_temperature", "max_tokens",
                "cpu_threshold", "ram_threshold", "disk_threshold", "notif_interval",
                "smart_notifications", "animations_enabled", "anim_speed", "anim_effect",
                "safety_enabled", "git_protection_enabled", "max_query_length",
                "rag_enabled", "rag_max_results"
            ]
            for key in keys:
                settings[key] = get_setting(key, "")

            path, _ = QFileDialog.getSaveFileName(
                self, "Сохранить настройки", "zeta_settings.json", "JSON (*.json)"
            )
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(settings, f, indent=2, ensure_ascii=False)
                QMessageBox.information(self, "Готово", f"Настройки сохранены в {path}")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось экспортировать: {e}")

    def reset_settings(self):
        reply = QMessageBox.question(
            self, "Подтверждение",
            "Сбросить все настройки к значениям по умолчанию?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.theme_combo.setCurrentText("dark")
            self.size_combo.setCurrentText("M")
            self.voice_check.setChecked(True)
            self.tts_voice_combo.setCurrentText("Светлана (женский, RU)")
            self.speed_spin.setValue(5)
            self.model_combo.setCurrentText("qwen2.5:7b (рекомендуется)")
            self.context_spin.setValue(2000)
            self.project_path_input.setText("D:\\Zeta")
            self.opacity_slider.setValue(100)
            self.avatar_path = ""
            self.avatar_label.setText("Не выбрана")
            self.temp_spin.setValue(0.7)
            self.max_tokens_spin.setValue(1024)
            self.cpu_threshold_spin.setValue(80)
            self.ram_threshold_spin.setValue(85)
            self.disk_threshold_spin.setValue(90)
            self.interval_spin.setValue(30)
            self.anim_check.setChecked(True)
            self.anim_speed_spin.setValue(300)
            self.anim_effect_combo.setCurrentText("Fade In")
            self.safety_check.setChecked(True)
            self.git_protection_check.setChecked(True)
            self.max_query_spin.setValue(2000)
            self.rag_check.setChecked(True)
            self.rag_results_spin.setValue(5)
            QMessageBox.information(self, "Готово", "Настройки сброшены. Нажмите 'Сохранить', чтобы применить.")

    def save_settings(self):
        save_setting("theme", self.theme_combo.currentText())
        save_setting("voice_enabled", "true" if self.voice_check.isChecked() else "false")
        save_setting("widget_size", self.size_combo.currentText())
        save_setting("avatar_path", self.avatar_path)
        save_setting("widget_opacity", str(self.opacity_slider.value() / 100))

        voice_display = self.tts_voice_combo.currentText()
        voice_code = VOICE_MAP.get(voice_display, "ru-RU-SvetlanaNeural")
        save_setting("tts_voice", voice_code)
        save_setting("tts_speed", str(self.speed_spin.value()))

        model_display = self.model_combo.currentText()
        model_code = MODEL_MAP.get(model_display, "qwen2.5:7b")
        save_setting("ai_model", model_code)
        save_setting("context_tokens", str(self.context_spin.value()))
        save_setting("ai_temperature", str(self.temp_spin.value()))
        save_setting("max_tokens", str(self.max_tokens_spin.value()))

        save_setting("project_path", self.project_path_input.text())

        save_setting("smart_notifications", "true" if self.notif_check.isChecked() else "false")
        save_setting("cpu_threshold", str(self.cpu_threshold_spin.value()))
        save_setting("ram_threshold", str(self.ram_threshold_spin.value()))
        save_setting("disk_threshold", str(self.disk_threshold_spin.value()))
        save_setting("notif_interval", str(self.interval_spin.value()))

        save_setting("animations_enabled", "true" if self.anim_check.isChecked() else "false")
        save_setting("anim_speed", str(self.anim_speed_spin.value()))
        save_setting("anim_effect", self.anim_effect_combo.currentText())

        save_setting("safety_enabled", "true" if self.safety_check.isChecked() else "false")
        save_setting("git_protection_enabled", "true" if self.git_protection_check.isChecked() else "false")
        save_setting("max_query_length", str(self.max_query_spin.value()))

        save_setting("rag_enabled", "true" if self.rag_check.isChecked() else "false")
        save_setting("rag_max_results", str(self.rag_results_spin.value()))

        self.settings_changed.emit()
        QMessageBox.information(self, "Готово", "Настройки сохранены!\nПерезапустите Z для применения.")
        self.close()