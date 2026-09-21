# -*- coding: utf-8 -*-
"""Тест IDS"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from security.intrusion_detector import get_ids
from security.audit import get_audit
import json


def main():
    print("🚨 Тест IDS Zeta")
    print("=" * 60)
    
    # 1. Статус
    ids = get_ids()
    print("\n📊 Статус IDS:")
    stats = ids.get_stats()
    for k, v in stats.items():
        print(f"   {k}: {v}")
    
    # 2. Анализ логов
    print("\n🔍 Анализ логов...")
    alerts = ids.analyze()
    
    if alerts:
        print(f"   Найдено {len(alerts)} новых алертов:")
        for a in alerts:
            print(f"     [{a['severity']}] {a['message']}")
    else:
        print("   ✅ Подозрительной активности не найдено")
    
    # 3. Чтение security.log
    print("\n📋 Последние события безопасности:")
    entries = get_audit().read_log("security", limit=10)
    
    if entries:
        for e in entries[-5:]:
            event = e.get("event", "?")
            severity = e.get("severity", "?")
            ts = e.get("timestamp", "")[:19]
            print(f"   {ts} [{severity:8s}] {event}")
    else:
        print("   (пусто)")
    
    # 4. Подсчёт IDS-алертов
    print("\n🚨 IDS-алерты в логе:")
    ids_entries = [e for e in entries if e.get("event", "").startswith("ids_")]
    
    if ids_entries:
        for e in ids_entries:
            print(f"   • {e.get('event')}: {e.get('details', '')[:60]}")
    else:
        print("   (пока нет срабатываний)")
    
    print("\n" + "=" * 60)
    print("✅ Проверка завершена")


if __name__ == "__main__":
    main()