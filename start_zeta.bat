@echo off
chcp 65001 >nul 2>&1
title Zeta AI Assistant v7.5
cd /d D:\Zeta

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

:: ============================================================
::                 🤖 ZETA AI ASSISTANT
:: ============================================================
echo ╔══════════════════════════════════════════════════════════════╗
echo ║                    🤖 Zeta AI Assistant v7.5               ║
echo ║              Создатель: Samriddin (Самир)                  ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

:: ============================================================
::              1. ПРОВЕРКА PYTHON
:: ============================================================
echo [1/6] 🔍 Проверка Python...

python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python не найден!
    echo.
    echo    Установите Python 3.12 или новее:
    echo    https://www.python.org/downloads/
    echo.
    echo    После установки проверьте, что Python добавлен в PATH.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VER=%%i
echo ✅ Python %PYTHON_VER% найден
echo.

:: ============================================================
::              2. ПРОВЕРКА ФАЙЛОВ ПРОЕКТА
:: ============================================================
echo [2/6] 📁 Проверка файлов проекта...

if not exist "main.py" (
    echo ❌ Файл main.py не найден!
    echo    Убедитесь, что вы находитесь в папке D:\Zeta
    pause
    exit /b 1
)

if not exist "core\ai_engine.py" (
    echo ⚠️ Не найден core\ai_engine.py. Возможно, проект повреждён.
)

if not exist "ui\widget.py" (
    echo ⚠️ Не найден ui\widget.py. Возможно, проект повреждён.
)

echo ✅ Файлы проекта найдены
echo.

:: ============================================================
::              3. ПРОВЕРКА ЗАВИСИМОСТЕЙ
:: ============================================================
echo [3/6] 📦 Проверка зависимостей...

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

python -c "import edge_tts" >nul 2>&1
if errorlevel 1 (
    echo ⚠️ edge-tts не установлен. Установка...
    pip install edge-tts
)

python -c "import dotenv" >nul 2>&1
if errorlevel 1 (
    echo ⚠️ python-dotenv не установлен. Установка...
    pip install python-dotenv
)

python -c "import psutil" >nul 2>&1
if errorlevel 1 (
    echo ⚠️ psutil не установлен. Установка...
    pip install psutil
)

echo ✅ Зависимости проверены
echo.

:: ============================================================
::              4. ПРОВЕРКА И ЗАПУСК OLLAMA
:: ============================================================
echo [4/6] 🔌 Проверка Ollama...

:: Проверяем, запущена ли Ollama
python -c "import requests; requests.get('http://localhost:11434/api/tags', timeout=2)" >nul 2>&1
if errorlevel 1 (
    echo ⚠️ Ollama не запущена!
    echo.
    echo    Пробую запустить Ollama...

    :: Ищем ollama.exe в стандартных местах
    set "OLLAMA_PATH="
    if exist "C:\Users\samir\AppData\Local\Programs\Ollama\ollama.exe" (
        set "OLLAMA_PATH=C:\Users\samir\AppData\Local\Programs\Ollama\ollama.exe"
    )
    if not defined OLLAMA_PATH (
        if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
            set "OLLAMA_PATH=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
        )
    )
    if not defined OLLAMA_PATH (
        if exist "C:\Program Files\Ollama\ollama.exe" (
            set "OLLAMA_PATH=C:\Program Files\Ollama\ollama.exe"
        )
    )

    if defined OLLAMA_PATH (
        start /B "" "%OLLAMA_PATH%" serve
        echo ⏳ Ожидание запуска Ollama...
        timeout /t 5 /nobreak >nul

        python -c "import requests; requests.get('http://localhost:11434/api/tags', timeout=2)" >nul 2>&1
        if errorlevel 1 (
            echo ⚠️ Ollama не запустилась автоматически.
            echo.
            echo    Запустите вручную в новом окне:
            echo    ollama serve
            echo.
            echo    ⚠️ Zeta запустится, но ИИ не будет работать!
            echo.
            choice /C YN /M "Продолжить запуск без Ollama"
            if errorlevel 2 exit /b 1
        ) else (
            echo ✅ Ollama запущена
        )
    ) else (
        echo ❌ Ollama не установлена!
        echo.
        echo    Скачайте и установите Ollama:
        echo    https://ollama.ai/
        echo.
        echo    После установки скачайте модели:
        echo    ollama pull zeta-universal
        echo    ollama pull llava:13b
        echo.
        choice /C YN /M "Продолжить запуск без Ollama"
        if errorlevel 2 exit /b 1
    )
) else (
    echo ✅ Ollama уже запущена
)
echo.

:: ============================================================
::              5. ПРОВЕРКА МОДЕЛЕЙ
:: ============================================================
echo [5/6] 🧠 Проверка моделей...

set "HAS_ZETA="
set "HAS_LLAVA="
set "HAS_ANY="

:: ollama list выводит таблицу, первая строка — заголовок
:: skip=1 — пропускаем заголовок, tokens=1 — берём первое слово (имя модели)
for /f "skip=1 tokens=1" %%m in ('ollama list 2^>nul') do (
    if not "%%m"=="" (
        set "HAS_ANY=1"
        echo %%m | findstr /I "zeta-universal" >nul && set "HAS_ZETA=1"
        echo %%m | findstr /I "llava" >nul && set "HAS_LLAVA=1"
    )
)

if defined HAS_ANY (
    if defined HAS_ZETA (
        echo ✅ zeta-universal: найдена
    ) else (
        echo ⚠️ zeta-universal: НЕ найдена
        echo    Установи: ollama pull zeta-universal
    )

    if defined HAS_LLAVA (
        echo ✅ llava: найдена
    ) else (
        echo ⚠️ llava: НЕ найдена
        echo    Установи: ollama pull llava:13b
    )

    if not defined HAS_ZETA (
        echo.
        choice /C YN /M "Продолжить без zeta-universal (ИИ не будет работать)"
        if errorlevel 2 exit /b 1
    )
) else (
    echo ⚠️ Модели не найдены в Ollama!
    echo.
    echo    Установи основные модели:
    echo    ollama pull zeta-universal
    echo    ollama pull llava:13b
    echo.
    echo    Это может занять 10-20 минут.
    echo.
    choice /C YN /M "Продолжить запуск без моделей"
    if errorlevel 2 exit /b 1
)
echo.

:: ============================================================
::              6. ЗАПУСК ZETA
:: ============================================================
echo [6/6] 🚀 Запуск Zeta...
echo.
echo ══════════════════════════════════════════════════════════════
echo    💡 Горячие клавиши:
echo       Ctrl+Shift+Z  — Показать/скрыть виджет
echo       Ctrl+Shift+S  — Статус системы
echo       Ctrl+Shift+P  — Отправить фото
echo       Ctrl+Shift+V  — Голосовой ввод
echo       Ctrl+Shift+D  — Планировщик
echo       Ctrl+Shift+A  — Автоматизация
echo       Ctrl+Shift+N  — Устройства
echo       Ctrl+L        — Очистить чат
echo ══════════════════════════════════════════════════════════════
echo.

python main.py

if errorlevel 1 (
    echo.
    echo ❌ Zeta завершилась с ошибкой.
    echo    Проверь файл data/zeta.log для подробностей.
    echo.
    pause
)

pause