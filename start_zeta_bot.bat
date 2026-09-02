@echo off
title Zeta Telegram Bot
cd /d D:\Zeta

echo ╔══════════════════════════════════════════════════════════╗
echo ║                    📱 Zeta Telegram Bot                ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

:: Проверяем Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python не найден! Установите Python 3.12+
    pause
    exit /b 1
)

:: Проверяем, что файл существует
if not exist "zeta_bot.py" (
    echo ❌ Файл zeta_bot.py не найден!
    pause
    exit /b 1
)

:: Проверяем установку python-telegram-bot
python -c "import telegram" >nul 2>&1
if errorlevel 1 (
    echo ⚠️ python-telegram-bot не установлен! Устанавливаю...
    pip install python-telegram-bot
)

:: Проверяем наличие токена
python -c "import sys; sys.path.insert(0, '.'); exec(open('zeta_bot.py').read().split('BOT_TOKEN')[1].split('=')[0] if 'BOT_TOKEN' in open('zeta_bot.py').read() else 'print(1)')" >nul 2>&1
if errorlevel 1 (
    echo ⚠️ Проверьте BOT_TOKEN в zeta_bot.py
)

echo 🚀 Запуск Telegram-бота Zeta...
echo 📱 Бот: @ZetaAI_Bot
echo.
echo ⏹️ Нажмите Ctrl+C для остановки
echo.

python zeta_bot.py

pause