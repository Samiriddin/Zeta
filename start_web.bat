@echo off
title Zeta Web Server
cd /d D:\Zeta

echo ╔══════════════════════════════════════════════════════════╗
echo ║                    🌐 Zeta Web Server                  ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

:: Проверяем, что Python установлен
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python не найден! Установите Python 3.12+
    pause
    exit /b 1
)

:: Проверяем, что Flask установлен
python -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo ⚠️ Flask не установлен! Устанавливаю...
    pip install flask flask-cors
)

:: Проверяем, что файл web_server.py существует
if not exist "web_server.py" (
    echo ❌ Файл web_server.py не найден!
    pause
    exit /b 1
)

echo 🚀 Запуск веб-сервера Zeta...
echo 📱 Доступ: http://localhost:5000
echo 📱 С телефона: http://[IP-адрес]:5000
echo.
echo ⏹️ Нажмите Ctrl+C для остановки
echo.

python web_server.py

pause