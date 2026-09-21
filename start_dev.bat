@echo off
chcp 65001 >nul 2>&1
title Zeta - Development Mode (DEBUG)
cd /d "%~dp0"

:: ============================================================
::  ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ
:: ============================================================
set OLLAMA_MODELS=D:\ollama_models
set PYTHONPATH=%~dp0
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set PYTHONUNBUFFERED=1
set ZETA_DEBUG=1

echo ╔══════════════════════════════════════════════════════════╗
echo ║                    🛠️ Zeta Dev Mode                    ║
echo ║                Режим разработки                        ║
echo ╚══════════════════════════════════════════════════════════╝
echo.
echo    ⚠️ Это НЕ для повседневного использования!
echo    Для обычного запуска используй start_zeta.bat
echo.

:: ============================================================
::  1. ПРОВЕРКА PYTHON
:: ============================================================
echo [1/6] 🔍 Проверка Python...

python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python не найден!
    echo    Установи Python 3.12+:
    echo    https://www.python.org/downloads/
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

if not exist "main.py" (
    echo ❌ Файл main.py не найден!
    echo    Убедись, что находишься в папке D:\Zeta
    pause
    exit /b 1
)

if not exist "core\ai_engine.py" (
    echo ❌ Не найден core\ai_engine.py
    echo    Проект повреждён!
    pause
    exit /b 1
)

echo ✅ Файлы найдены
echo.

:: ============================================================
::  3. ПРОВЕРКА ПАПКИ МОДЕЛЕЙ
:: ============================================================
echo [3/6] 📦 Проверка папки моделей...

if not exist "%OLLAMA_MODELS%" (
    echo ⚠️ Папка моделей не найдена: %OLLAMA_MODELS%
    echo    Ollama будет использовать дефолтную папку.
    mkdir "%OLLAMA_MODELS%" 2>nul
) else (
    echo ✅ Папка моделей: %OLLAMA_MODELS%
)
echo.

:: ============================================================
::  4. ПРОВЕРКА ЗАВИСИМОСТЕЙ (только основные)
:: ============================================================
echo [4/6] 📦 Проверка зависимостей...

python -c "import PyQt6" >nul 2>&1
if errorlevel 1 (
    echo ⚠️ PyQt6 не установлен. Установка...
    pip install PyQt6
)

python -c "import requests" >nul 2>&1
if errorlevel 1 (
    echo ⚠️ requests не установлен. Установка...
    pip install requests
)

echo ✅ Зависимости проверены
echo.

:: ============================================================
::  5. ПРОВЕРКА OLLAMA
:: ============================================================
echo [5/6] 🔌 Проверка Ollama...

python -c "import requests; requests.get('http://localhost:11434/api/tags', timeout=2)" >nul 2>&1
if errorlevel 1 (
    echo ⚠️ Ollama не запущена!
    echo    Запусти в отдельном окне: ollama serve
    echo.
    choice /C YN /M "Продолжить без Ollama"
    if errorlevel 2 exit /b 1
) else (
    echo ✅ Ollama запущена
)
echo.

:: ============================================================
::  6. СОЗДАНИЕ ПАПКИ ЛОГОВ
:: ============================================================
echo [6/6] 📝 Подготовка логов...

if not exist "logs" mkdir "logs"
if not exist "data" mkdir "data"

echo ✅ Логи: logs\
echo.

:: ============================================================
::  ИНФО О РЕЖИМЕ
:: ============================================================
echo ══════════════════════════════════════════════════════════════
echo    🛠️ РЕЖИМ РАЗРАБОТКИ АКТИВЕН
echo ══════════════════════════════════════════════════════════════
echo.
echo    Переменные окружения:
echo       OLLAMA_MODELS = %OLLAMA_MODELS%
echo       PYTHONPATH    = %PYTHONPATH%
echo       PYTHONUTF8    = %PYTHONUTF8%
echo       ZETA_DEBUG    = %ZETA_DEBUG%
echo.
echo    Python-флаги:
echo       -u   — unbuffered (логи сразу)
echo       -X dev  — dev-режим (warnings)
echo.
echo    Логи пишутся в:
echo       data\zeta.log
echo.
echo    ⏹️  Ctrl+C — остановить
echo.
echo ══════════════════════════════════════════════════════════════
echo.

timeout /t 3 /nobreak >nul

:: ============================================================
::  ЗАПУСК С ОТЛАДКОЙ
:: ============================================================
:: -u        = unbuffered (логи сразу в консоль)
:: -X dev    = dev mode (warnings наверху)
:: -W default = показывать warning'и

python -u -X dev main.py

:: ============================================================
::  ПОСЛЕ ЗАВЕРШЕНИЯ
:: ============================================================
if errorlevel 1 (
    echo.
    echo ══════════════════════════════════════════════════════════════
    echo ❌ Zeta завершилась с ошибкой (код %errorlevel%)
    echo ══════════════════════════════════════════════════════════════
    echo.
    echo    Проверь логи:
    echo       data\zeta.log
    echo.
    echo    Последние 20 строк:
    echo ══════════════════════════════════════════════════════════════
    echo.
    if exist "data\zeta.log" (
        powershell -Command "Get-Content 'data\zeta.log' -Tail 20"
    ) else (
        echo    (лог не найден)
    )
    echo.
    echo ══════════════════════════════════════════════════════════════
) else (
    echo.
    echo ✅ Zeta корректно завершилась.
)

pause