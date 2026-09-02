@echo off
chcp 65001 >nul 2>&1
title Zeta AI Assistant v4.0
cd /d D:\Zeta

:: ============================================================
::                 🤖 ZETA AI ASSISTANT
:: ============================================================
echo ╔══════════════════════════════════════════════════════════════╗
echo ║                    🤖 Zeta AI Assistant v4.0               ║
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

:: Получаем версию Python
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
    
    :: Проверяем, существует ли ollama.exe
    if exist "C:\Users\samir\AppData\Local\Programs\Ollama\ollama.exe" (
        start /B "" "C:\Users\samir\AppData\Local\Programs\Ollama\ollama.exe" serve
        echo ⏳ Ожидание запуска Ollama...
        timeout /t 5 /nobreak >nul
        
        :: Проверяем ещё раз
        python -c "import requests; requests.get('http://localhost:11434/api/tags', timeout=2)" >nul 2>&1
        if errorlevel 1 (
            echo ⚠️ Ollama не запустилась автоматически.
            echo.
            echo    Запустите вручную в новом окне:
            echo    cd D:\ollama_models
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
        echo    ollama pull qwen2.5:7b
        echo    ollama pull llava:latest
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

python -c "import requests; r=requests.get('http://localhost:11434/api/tags'); print('✅ Модели загружены' if r.json().get('models') else '⚠️ Моделей нет')" >nul 2>&1
if errorlevel 1 (
    echo ⚠️ Модели не найдены!
    echo.
    echo    Установите основные модели:
    echo    ollama pull qwen2.5:7b
    echo    ollama pull llava:latest
    echo.
    echo    Это может занять 10-20 минут в зависимости от скорости интернета.
    echo.
    choice /C YN /M "Продолжить запуск без моделей"
    if errorlevel 2 exit /b 1
) else (
    echo ✅ Модели проверены
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
echo       Ctrl+L        — Очистить чат
echo       Ctrl+P        — Режим программиста
echo ══════════════════════════════════════════════════════════════
echo.

:: Запускаем Python с UTF-8
python main.py

:: Если Python завершился с ошибкой
if errorlevel 1 (
    echo.
    echo ❌ Zeta завершилась с ошибкой.
    echo    Проверьте файл data/zeta.log для подробностей.
    echo.
    pause
)

pause