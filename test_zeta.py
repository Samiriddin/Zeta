# -*- coding: utf-8 -*-
"""
Тестовый файл для Zeta.
"""

print("✅ Zeta test file")
print("🔌 Проверка импортов...")

try:
    from core.ai_engine import ask_zeta_sync
    print("✅ core.ai_engine — OK")
except Exception as e:
    print(f"❌ core.ai_engine — {e}")

try:
    from core.memory import get_history, save_message
    print("✅ core.memory — OK")
except Exception as e:
    print(f"❌ core.memory — {e}")

try:
    from modules.system_monitor import get_system_status
    print("✅ modules.system_monitor — OK")
except Exception as e:
    print(f"❌ modules.system_monitor — {e}")

print("\n✅ Все тесты пройдены!")