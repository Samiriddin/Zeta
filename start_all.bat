@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
title Zeta - All Services
cd /d "%~dp0"

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set OLLAMA_MODELS=D:\ollama_models

:: ============================================================
::  ПАРАМЕТРЫ
:: ============================================================
set "MODE=start"
if /I "%~1"=="--stop" set "MODE=stop"
if /I "%~1"=="-s" set "MODE=stop"

if "%MODE%"=="stop" goto :stop_all

:: ============================================================
::  ШАПКА (эмодзи тут работают — вне if)
:: ============================================================
echo.
echo ================================================================
echo                     Zeta Full Stack
echo              Запуск всех сервисов Zeta
echo ================================================================
echo.

:: ============================================================
::  1. ПРОВЕРКА PYTHON
:: ============================================================
echo [1/7] Проверка Python...

python --version >nul 2>&1
if errorlevel 1 goto :no_python

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VER=%%i
echo       [OK] Python %PYTHON_VER%
echo.

:: ============================================================
::  2. СОЗДАНИЕ ПАПОК
:: ============================================================
echo [2/7] Проверка папок...

for %%d in (data data\avatar data\backups data\backups\auto data\backups\manual data\security data\audit data\screenshots generated logs) do (
    if not exist "%%d" mkdir "%%d" 2>nul
)
echo       [OK] Папки готовы
echo.

:: ============================================================
::  3. ПРОВЕРКА ФАЙЛОВ ПРОЕКТА
:: ============================================================
echo [3/7] Проверка файлов...

if not exist "main.py" goto :no_main

set "HAS_ZETA_BOT="
if exist "zeta_bot.py" set "HAS_ZETA_BOT=1"

set "HAS_PUBLIC_BOT="
if exist "zeta_public_bot.py" set "HAS_PUBLIC_BOT=1"

set "HAS_WEB="
if exist "web_server.py" set "HAS_WEB=1"

echo       [OK] main.py
if defined HAS_ZETA_BOT echo       [OK] zeta_bot.py
if defined HAS_PUBLIC_BOT echo       [OK] zeta_public_bot.py
if defined HAS_WEB echo       [OK] web_server.py
echo.

:: ============================================================
::  4. ПРОВЕРКА .env
:: ============================================================
echo [4/7] Проверка .env...

set "HAS_ENV="
if exist ".env" set "HAS_ENV=1"

if not defined HAS_ENV goto :no_env

findstr /I /C:"ZETA_BOT_TOKEN" ".env" >nul 2>&1
if errorlevel 1 goto :no_bot_token

echo       [OK] ZETA_BOT_TOKEN найден

findstr /I /C:"ZETA_PUBLIC_BOT_TOKEN" ".env" >nul 2>&1
if errorlevel 1 goto :no_public_token

echo       [OK] ZETA_PUBLIC_BOT_TOKEN найден
echo.
goto :env_done

:no_bot_token
echo       [!] В .env нет ZETA_BOT_TOKEN
set "SKIP_ZETA_BOT=1"
goto :check_public

:no_public_token
echo       [!] В .env нет ZETA_PUBLIC_BOT_TOKEN
set "SKIP_PUBLIC_BOT=1"
echo.
goto :env_done

:check_public
findstr /I /C:"ZETA_PUBLIC_BOT_TOKEN" ".env" >nul 2>&1
if errorlevel 1 (
    set "SKIP_PUBLIC_BOT=1"
    echo       [!] В .env нет ZETA_PUBLIC_BOT_TOKEN
)
echo.
goto :env_done

:no_env
echo       [!] Файл .env НЕ найден!
echo.
echo       Боты НЕ запустятся без .env.
echo       Создай файл .env в D:\Zeta\
echo.
echo          ZETA_BOT_TOKEN=токен_личного_бота
echo          ZETA_PUBLIC_BOT_TOKEN=токен_публичного_бота
echo          ZETA_ADMIN_IDS=твой_telegram_id
echo.
echo       Токены получи у @BotFather и СМЕНИ старые!
echo.
choice /C YN /M "Продолжить без ботов"
if errorlevel 2 exit /b 1
set "SKIP_BOTS=1"
echo.

:env_done

:: ============================================================
::  5. ПРОВЕРКА OLLAMA
:: ============================================================
echo [5/7] Проверка Ollama...

python -c "import requests; requests.get('http://localhost:11434/api/tags', timeout=2)" >nul 2>&1
if not errorlevel 1 goto :ollama_ok

echo       Ollama не запущена, ищу путь...

set "OLLAMA_EXE="
if exist "C:\Users\samir\AppData\Local\Programs\Ollama\ollama.exe" set "OLLAMA_EXE=C:\Users\samir\AppData\Local\Programs\Ollama\ollama.exe"
if not defined OLLAMA_EXE if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
if not defined OLLAMA_EXE if exist "C:\Program Files\Ollama\ollama.exe" set "OLLAMA_EXE=C:\Program Files\Ollama\ollama.exe"

if not defined OLLAMA_EXE goto :no_ollama

echo       [OK] Найдена: %OLLAMA_EXE%
echo       Запускаю Ollama...

start "Ollama Server" /MIN cmd /c ""%OLLAMA_EXE%" serve"
timeout /t 5 /nobreak >nul

python -c "import requests; requests.get('http://localhost:11434/api/tags', timeout=2)" >nul 2>&1
if errorlevel 1 (
    echo       [!] Ollama не отвечает, продолжаем...
) else (
    echo       [OK] Ollama запущена
)
echo.
goto :ollama_done

:ollama_ok
echo       [OK] Ollama уже запущена
echo.
goto :ollama_done

:no_ollama
echo       [X] Ollama не найдена!
echo          Установи: https://ollama.ai/
echo.
choice /C YN /M "Продолжить без Ollama (ИИ не работает)"
if errorlevel 2 exit /b 1

:ollama_done

:: ============================================================
::  6. ПРОВЕРКА ПОРТА 5000
:: ============================================================
echo [6/7] Проверка порта 5000...

if not defined HAS_WEB goto :web_skip

netstat -ano | findstr ":5000 " | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
    echo       [OK] Порт 5000 свободен
) else (
    echo       [!] Порт 5000 занят - веб-сервер может упасть
    set "SKIP_WEB=1"
)
echo.
goto :web_done

:web_skip
echo       (веб-сервер не найден - пропускаем)
echo.

:web_done

:: ============================================================
::  7. ИНФО ПЕРЕД ЗАПУСКОМ
:: ============================================================
echo [7/7] Что будет запущено:
echo.
echo       Zeta Widget    - main.py

if not defined SKIP_BOTS (
    if not defined SKIP_ZETA_BOT if defined HAS_ZETA_BOT echo       Личный бот    - zeta_bot.py
    if not defined SKIP_PUBLIC_BOT if defined HAS_PUBLIC_BOT echo       Публичный бот - zeta_public_bot.py
)
if not defined SKIP_WEB if defined HAS_WEB echo       Веб-сервер    - web_server.py (порт 5000)
echo.

echo ================================================================
echo    ВНИМАНИЕ:
echo ================================================================
echo.
echo    * Каждый сервис откроется в ОТДЕЛЬНОМ окне
echo    * Не закрывай их, пока не закончишь работу
echo    * Для остановки всех: start_all.bat --stop
echo.
echo ================================================================
echo.

choice /C YN /M "Запустить всё"
if errorlevel 2 exit /b 0
echo.

:: ============================================================
::  ЗАПУСК СЕРВИСОВ
:: ============================================================
echo Запуск сервисов...
echo.

echo       [1] Zeta Widget...
start "Zeta Widget" cmd /k "cd /d %~dp0 && python main.py"
timeout /t 3 /nobreak >nul

if not defined SKIP_BOTS (
    if not defined SKIP_ZETA_BOT if defined HAS_ZETA_BOT (
        echo       [2] Личный Telegram-бот...
        start "Zeta Bot" cmd /k "cd /d %~dp0 && python zeta_bot.py"
        timeout /t 2 /nobreak >nul
    )
)

if not defined SKIP_BOTS (
    if not defined SKIP_PUBLIC_BOT if defined HAS_PUBLIC_BOT (
        echo       [3] Публичный Telegram-бот...
        start "Zeta Public Bot" cmd /k "cd /d %~dp0 && python zeta_public_bot.py"
        timeout /t 2 /nobreak >nul
    )
)

if not defined SKIP_WEB if defined HAS_WEB (
    echo       [4] Веб-сервер...
    start "Zeta Web" cmd /k "cd /d %~dp0 && python web_server.py"
    timeout /t 2 /nobreak >nul
)

echo.
echo Все сервисы запущены!
echo.

:: ============================================================
::  IP ДЛЯ ТЕЛЕФОНА
:: ============================================================
set "LOCAL_IP=127.0.0.1"
set "LOCAL_IP_SET="
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /C:"IPv4"') do (
    set "TMP_IP=%%a"
    set "TMP_IP=!TMP_IP: =!"
    if not defined LOCAL_IP_SET (
        set "LOCAL_IP=!TMP_IP!"
        set "LOCAL_IP_SET=1"
    )
)

echo ================================================================
echo                     Все сервисы запущены!
echo ================================================================
echo.
echo   Как пользоваться:
echo.
echo   Zeta Widget   -^>  Ctrl+Shift+Z  (показать/скрыть)

if not defined SKIP_BOTS (
    if not defined SKIP_ZETA_BOT if defined HAS_ZETA_BOT echo   Личный бот    -^>  @ZetaAI_Bot
)
echo   Веб (ПК)      -^>  http://localhost:5000
if defined HAS_WEB echo   Веб (телефон) -^>  http://%LOCAL_IP%:5000
echo   Логи          -^>  data/zeta.log
echo.
echo ================================================================
echo   Остановка:  start_all.bat --stop
echo ================================================================
echo.
echo    Не закрывай окна сервисов вручную -
echo    используй start_all.bat --stop
echo.
pause
exit /b 0


:: ============================================================
::  ОШИБКИ
:: ============================================================
:no_python
echo       [X] Python не найден!
echo          Установи Python 3.12+: https://www.python.org/downloads/
pause
exit /b 1

:no_main
echo       [X] main.py не найден!
echo          Убедись, что находишься в папке D:\Zeta
pause
exit /b 1


:: ============================================================
::  STOP ALL
:: ============================================================
:stop_all
echo.
echo ================================================================
echo              Остановка сервисов Zeta
echo ================================================================
echo.

echo    Остановка Zeta Widget...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq Zeta Widget" >nul 2>&1

echo    Остановка Telegram-ботов...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq Zeta Bot" >nul 2>&1
taskkill /F /IM python.exe /FI "WINDOWTITLE eq Zeta Public Bot" >nul 2>&1

echo    Остановка веб-сервера...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq Zeta Web" >nul 2>&1

echo.
echo    Готово. Также можно закрыть окна вручную.
echo.
pause
exit /b 0