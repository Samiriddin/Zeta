@echo off
title Zeta - All Services
cd /d D:\Zeta

echo ╔══════════════════════════════════════════════════════════╗
echo ║                    🚀 Zeta Full Stack                  ║
echo ║            Запуск всех сервисов Zeta                   ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

:: Проверяем Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python не найден! Установите Python 3.12+
    pause
    exit /b 1
)

:: Создаём папки
if not exist "data" mkdir data
if not exist "generated" mkdir generated
if not exist "data\avatar" mkdir data\avatar

echo 📱 Запуск сервисов...
echo.

:: Запускаем Ollama (если не запущена)
echo 🔌 Запуск Ollama...
start "Ollama" /B "" "C:\Users\samir\AppData\Local\Programs\Ollama\ollama.exe" serve
timeout /t 3 /nobreak >nul

:: Запускаем Zeta
echo 🤖 Запуск Zeta...
start "Zeta" python main.py

:: Ждём 5 секунд перед запуском ботов
timeout /t 5 /nobreak >nul

:: Запускаем Telegram-ботов
echo 📱 Запуск Telegram-ботов...
start "Zeta Bot" python zeta_bot.py
timeout /t 2 /nobreak >nul
start "Zeta Public" python zeta_public_bot.py

:: Запускаем веб-сервер
echo 🌐 Запуск веб-сервера...
start "Zeta Web" python web_server.py

echo.
echo ╔══════════════════════════════════════════════════════════╗
echo ║                    ✅ ВСЕ СЕРВИСЫ ЗАПУЩЕНЫ!           ║
echo ╠══════════════════════════════════════════════════════════╣
echo ║  🤖 Zeta         →  Ctrl+Shift+Z                      ║
echo ║  📱 Telegram Bot →  @ZetaAI_Bot                       ║
echo ║  🌐 Веб-сервер   →  http://localhost:5000            ║
echo ║  📊 Логи         →  data/zeta.log                    ║
echo ╚══════════════════════════════════════════════════════════╝
echo.
echo ⏹️ Нажмите любую клавишу для закрытия этого окна...
echo    (Сервисы продолжат работать в фоне)

pause