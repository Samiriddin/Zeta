@echo off
chcp 65001 >nul 2>&1
title Zeta Telegram Bot (личный)
cd /d "%~dp0"

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

echo ╔══════════════════════════════════════════════════════════╗
echo ║              📱 Zeta Telegram Bot (личный)             ║
echo ║              Управление ПК через Telegram              ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

:: ============================================================
::  1. ПРОВЕРКА PYTHON
:: ============================================================
echo [1/6] 🔍 Проверка Python...

python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python не найден!
    echo.
    echo    Установи Python 3.12+:
    echo    https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VER=%%i
echo ✅ Python %PYTHON_VER%
echo.

:: ============================================================
::  2. ПРОВЕРКА ФАЙЛОВ
:: ============================================================
echo [2/6] 📁 Проверка файлов...

if not exist "zeta_bot.py" (
    echo ❌ Файл zeta_bot.py не найден!
    echo    Убедись, что находишься в папке D:\Zeta
    pause
    exit /b 1
)

if not exist "core\ai_engine.py" (
    echo ⚠️ Не найден core\ai_engine.py
    echo    Бот не сможет отвечать без движка!
)

echo ✅ Файлы найдены
echo.

:: ============================================================
::  3. ПРОВЕРКА ЗАВИСИМОСТЕЙ
:: ============================================================
echo [3/6] 📦 Проверка зависимостей...

python -c "import telegram" >nul 2>&1
if errorlevel 1 (
    echo ⚠️ python-telegram-bot не установлен. Установка...
    pip install --upgrade python-telegram-bot
)

python -c "import dotenv" >nul 2>&1
if errorlevel 1 (
    echo ⚠️ python-dotenv не установлен. Установка...
    pip install python-dotenv
)

python -c "import requests" >nul 2>&1
if errorlevel 1 (
    echo ⚠️ requests не установлен. Установка...
    pip install requests
)

python -c "import psutil" >nul 2>&1
if errorlevel 1 (
    echo ⚠️ psutil не установлен. Установка...
    pip install psutil
)

echo ✅ Зависимости проверены
echo.

:: ============================================================
::  4. ПРОВЕРКА .env (ТОКЕН)
:: ============================================================
echo [4/6] 🔑 Проверка токена...

if not exist ".env" (
    echo ❌ Файл .env не найден!
    echo.
    echo    Создай файл D:\Zeta\.env со строкой:
    echo.
    echo    ZETA_BOT_TOKEN=твой_токен_от_BotFather
    echo    ZETA_ADMIN_IDS=твой_telegram_id
    echo.
    echo    Токен получи у @BotFather в Telegram.
    echo    Telegram ID — у @userinfobot.
    echo.
    pause
    exit /b 1
)

:: Проверяем, что в .env есть ZETA_BOT_TOKEN
findstr /I /C:"ZETA_BOT_TOKEN" ".env" >nul 2>&1
if errorlevel 1 (
    echo ⚠️ ZETA_BOT_TOKEN не найден в .env!
    echo.
    echo    Добавь в .env:
    echo    ZETA_BOT_TOKEN=твой_токен
    echo.
    pause
    exit /b 1
)

echo ✅ Токен найден в .env
echo.

:: ============================================================
::  5. ПРОВЕРКА OLLAMA
:: ============================================================
echo [5/6] 🔌 Проверка Ollama...

python -c "import requests; requests.get('http://localhost:11434/api/tags', timeout=2)" >nul 2>&1
if errorlevel 1 (
    echo ⚠️ Ollama не запущена!
    echo.
    echo    Бот запустится, но ИИ не будет отвечать.
    echo    Запусти Ollama в отдельном окне:
    echo    ollama serve
    echo.
    choice /C YN /M "Продолжить запуск без Ollama"
    if errorlevel 2 exit /b 1
) else (
    echo ✅ Ollama запущена
)
echo.

:: ============================================================
::  6. ЗАПУСК БОТА
:: ============================================================
echo [6/6] 🚀 Запуск Telegram-бота...
echo.
echo ══════════════════════════════════════════════════════════
echo    📱 Бот: @ZetaAI_Bot (личный)
echo    ⏹️  Ctrl+C — остановить
echo.
echo    💡 Команды бота:
echo       /start    — приветствие
echo       /status   — статус ПК
echo       /screen   — скриншот
echo       /model    — выбор модели
echo       /voice    — вкл/выкл голос
echo ══════════════════════════════════════════════════════════
echo.

python zeta_bot.py

if errorlevel 1 (
    echo.
    echo ❌ Бот завершился с ошибкой.
    echo    Проверь data/zeta.log для подробностей.
    echo.
)

pause