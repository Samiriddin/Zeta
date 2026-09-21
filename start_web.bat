@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
title Zeta Web Server
cd /d "%~dp0"

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

echo ╔══════════════════════════════════════════════════════════╗
echo ║                    🌐 Zeta Web Server                  ║
echo ║              Мобильная версия + веб-интерфейс          ║
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

if not exist "web_server.py" (
    echo ❌ Файл web_server.py не найден!
    echo    Убедись, что находишься в папке D:\Zeta
    pause
    exit /b 1
)

if not exist "core\ai_engine.py" (
    echo ⚠️ Не найден core\ai_engine.py
    echo    Веб-сервер не сможет отвечать без движка!
)

if not exist "core\memory.py" (
    echo ⚠️ Не найден core\memory.py
    echo    История и факты не будут работать!
)

echo ✅ Файлы найдены
echo.

:: ============================================================
::  3. ПРОВЕРКА ЗАВИСИМОСТЕЙ
:: ============================================================
echo [3/6] 📦 Проверка зависимостей...

python -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo ⚠️ Flask не установлен. Установка...
    pip install flask flask-cors
)

python -c "import flask_cors" >nul 2>&1
if errorlevel 1 (
    echo ⚠️ flask-cors не установлен. Установка...
    pip install flask-cors
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

:: Показываем версию Flask
for /f "tokens=2" %%v in ('python -c "import flask; print(flask.__version__)" 2^>nul') do set FLASK_VER=%%v
if not defined FLASK_VER set FLASK_VER=?
echo ✅ Зависимости проверены ^(Flask %FLASK_VER%^)
echo.

:: ============================================================
::  4. ПРОВЕРКА OLLAMA
:: ============================================================
echo [4/6] 🔌 Проверка Ollama...

python -c "import requests; requests.get('http://localhost:11434/api/tags', timeout=2)" >nul 2>&1
if errorlevel 1 (
    echo ⚠️ Ollama не запущена!
    echo.
    echo    Веб-сервер запустится, но ИИ не будет отвечать.
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
::  5. ПРОВЕРКА ПОРТА 5000
:: ============================================================
echo [5/6] 🔍 Проверка порта 5000...

netstat -ano | findstr ":5000 " | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo ⚠️ Порт 5000 уже занят!
    echo.
    echo    Возможные причины:
    echo    - Другой экземпляр Zeta Web уже запущен
    echo    - Другая программа использует порт 5000
    echo.
    choice /C YN /M "Продолжить (может упасть)"
    if errorlevel 2 exit /b 1
) else (
    echo ✅ Порт 5000 свободен
)
echo.

:: ============================================================
::  6. ПОКАЗ IP ДЛЯ ТЕЛЕФОНА
:: ============================================================
echo [6/6] 🌐 Определение локального IP...
echo.

set "LOCAL_IP=127.0.0.1"
set "LOCAL_IP_SET="

:: Ищем IPv4 адрес
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /C:"IPv4"') do (
    set "TMP_IP=%%a"
    set "TMP_IP=!TMP_IP: =!"
    if not defined LOCAL_IP_SET (
        set "LOCAL_IP=!TMP_IP!"
        set "LOCAL_IP_SET=1"
    )
)

echo ══════════════════════════════════════════════════════════════
echo    🌐 Zeta Web готов к запуску
echo ══════════════════════════════════════════════════════════════
echo.
echo    💻 На ПК:        http://localhost:5000
echo    📱 С телефона:   http://%LOCAL_IP%:5000
echo    🩺 Health-check: http://localhost:5000/health
echo.
echo    ══════════════════════════════════════════════════════════
echo    📱 КАК УСТАНОВИТЬ КАК ПРИЛОЖЕНИЕ НА ТЕЛЕФОН:
echo    ══════════════════════════════════════════════════════════
echo.
echo    1. Открой Chrome/Edge на телефоне
echo    2. Перейди на: http://%LOCAL_IP%:5000
echo    3. Меню ^(⋮^) -^> "Установить приложение"
echo    4. Иконка Zeta появится на главном экране
echo.
echo    ⚠️ Телефон должен быть в ОДНОЙ Wi-Fi сети с ПК!
echo.
echo    ══════════════════════════════════════════════════════════
echo    💡 Если телефон не подключается:
echo    ══════════════════════════════════════════════════════════
echo.
echo    1. Проверь фаервол Windows:
echo       - Разреши Python в "Частных" сетях
echo    2. Проверь, что Wi-Fi НЕ гостевая сеть
echo    3. Проверь, что IP правильный ^(ipconfig^)
echo.
echo ══════════════════════════════════════════════════════════════
echo.
echo    ⏹️  Ctrl+C — остановить сервер
echo.
echo ══════════════════════════════════════════════════════════════
echo.

timeout /t 3 /nobreak >nul

python web_server.py

if errorlevel 1 (
    echo.
    echo ❌ Веб-сервер завершился с ошибкой.
    echo    Проверь data/zeta.log для подробностей.
    echo.
)

pause