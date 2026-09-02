@echo off
chcp 65001 >nul 2>&1
title Zeta — Установка зависимостей
cd /d D:\Zeta

echo ╔══════════════════════════════════════════════════════════════╗
echo ║           📦 Zeta — Установка зависимостей                 ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

echo 📦 Установка основных зависимостей...
echo.

pip install PyQt6 requests pillow mss edge-tts playsound
if errorlevel 1 (
    echo ❌ Ошибка установки основных зависимостей
)

echo.
echo 📦 Установка Telegram...
pip install python-telegram-bot
if errorlevel 1 (
    echo ❌ Ошибка установки python-telegram-bot
)

echo.
echo 📦 Установка системного мониторинга...
pip install psutil wmi
if errorlevel 1 (
    echo ❌ Ошибка установки psutil/wmi
)

echo.
echo 📦 Установка веб-интерфейса...
pip install Flask flask-cors
if errorlevel 1 (
    echo ❌ Ошибка установки Flask
)

echo.
echo 📦 Установка RAG (документы)...
pip install PyPDF2 python-docx openpyxl chardet
if errorlevel 1 (
    echo ❌ Ошибка установки RAG
)

echo.
echo 📦 Установка дополнительных...
pip install chromadb pygetwindow
if errorlevel 1 (
    echo ⚠️ ChromaDB не установлена (опционально)
)

echo.
echo ══════════════════════════════════════════════════════════════
echo    ✅ Установка завершена!
echo.
echo    ⚠️ Не забудьте установить Ollama:
echo    https://ollama.ai/
echo.
echo    ⚠️ И скачать модели:
echo    ollama pull qwen2.5:7b
echo    ollama pull llava:latest
echo ══════════════════════════════════════════════════════════════
echo.

pause