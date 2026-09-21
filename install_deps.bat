@echo off
chcp 65001 >nul 2>&1
title Zeta — Установка зависимостей
cd /d "%~dp0"

setlocal enabledelayedexpansion

echo ╔══════════════════════════════════════════════════════════════╗
echo ║           📦 Zeta — Установка зависимостей                 ║
echo ║                                                              ║
echo ║           Это займёт 5-15 минут. Наберись терпения.        ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

:: ============================================================
::  ПРОВЕРКА PYTHON
:: ============================================================
echo [0/8] 🐍 Проверка Python...

python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python не найден!
    echo.
    echo    Установи Python 3.12+:
    echo    https://www.python.org/downloads/
    echo.
    echo    ⚠️ При установке отметь "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VER=%%i
echo ✅ Python %PYTHON_VER%
echo.

:: ============================================================
::  ОБНОВЛЕНИЕ PIP
:: ============================================================
echo [0/8] 🔧 Обновление pip...

python -m pip install --upgrade pip >nul 2>&1
if errorlevel 1 (
    echo ⚠️ Не удалось обновить pip — продолжаем со старой версией
) else (
    echo ✅ pip обновлён
)
echo.

:: ============================================================
::  СЧЁТЧИКИ
:: ============================================================
set "OK_COUNT=0"
set "FAIL_COUNT=0"
set "FAIL_LIST="

:: Лог установки
set "PIP_LOG=%~dp0pip_install.log"
echo. > "%PIP_LOG%"
echo === Zeta install log === >> "%PIP_LOG%"
echo Date: %DATE% %TIME% >> "%PIP_LOG%"
echo. >> "%PIP_LOG%"

:: ============================================================
::  1. ОСНОВНЫЕ (UI + HTTP)
:: ============================================================
echo ══════════════════════════════════════════════════════════════
echo [1/8] 📦 Основные: PyQt6, requests, pillow, mss
echo ══════════════════════════════════════════════════════════════
echo.

pip install PyQt6 requests pillow mss >> "%PIP_LOG%" 2>&1
if errorlevel 1 (
    echo ❌ Ошибка установки основных
    set /a FAIL_COUNT+=1
    set "FAIL_LIST=!FAIL_LIST! основные,"
) else (
    echo ✅ Основные установлены
    set /a OK_COUNT+=1
)
echo.

:: ============================================================
::  2. ГОЛОС (TTS + STT)
:: ============================================================
echo ══════════════════════════════════════════════════════════════
echo [2/8] 🎤 Голос: edge-tts, pygame-ce, sounddevice, SpeechRecognition
echo ══════════════════════════════════════════════════════════════
echo.

:: pygame-ce (замена pygame для Python 3.14)
pip install edge-tts pygame-ce sounddevice soundfile SpeechRecognition >> "%PIP_LOG%" 2>&1
if errorlevel 1 (
    echo ❌ Ошибка установки голосовых
    set /a FAIL_COUNT+=1
    set "FAIL_LIST=!FAIL_LIST! голос,"
) else (
    echo ✅ Голосовые установлены
    set /a OK_COUNT+=1
)
echo.

:: ============================================================
::  3. СИСТЕМА (мониторинг)
:: ============================================================
echo ══════════════════════════════════════════════════════════════
echo [3/8] 💻 Система: psutil, wmi
echo ══════════════════════════════════════════════════════════════
echo.

pip install psutil wmi >> "%PIP_LOG%" 2>&1
if errorlevel 1 (
    echo ⚠️ wmi не установлена (только Windows) — не критично
    set /a FAIL_COUNT+=1
    set "FAIL_LIST=!FAIL_LIST! wmi,"
) else (
    echo ✅ Системные установлены
    set /a OK_COUNT+=1
)
echo.

:: ============================================================
::  4. ВЕБ (Flask)
:: ============================================================
echo ══════════════════════════════════════════════════════════════
echo [4/8] 🌐 Веб-интерфейс: Flask, flask-cors
echo ══════════════════════════════════════════════════════════════
echo.

pip install Flask flask-cors >> "%PIP_LOG%" 2>&1
if errorlevel 1 (
    echo ❌ Ошибка установки Flask
    set /a FAIL_COUNT+=1
    set "FAIL_LIST=!FAIL_LIST! Flask,"
) else (
    echo ✅ Flask установлен
    set /a OK_COUNT+=1
)
echo.

:: ============================================================
::  5. БЕЗОПАСНОСТЬ
:: ============================================================
echo ══════════════════════════════════════════════════════════════
echo [5/8] 🔐 Безопасность: cryptography, bcrypt, pyotp, qrcode
echo ══════════════════════════════════════════════════════════════
echo.

pip install cryptography bcrypt pyotp qrcode[pil] python-dotenv >> "%PIP_LOG%" 2>&1
if errorlevel 1 (
    echo ❌ Ошибка установки безопасности
    set /a FAIL_COUNT+=1
    set "FAIL_LIST=!FAIL_LIST! безопасность,"
) else (
    echo ✅ Безопасность установлена
    set /a OK_COUNT+=1
)
echo.

:: ============================================================
::  6. RAG (документы)
:: ============================================================
echo ══════════════════════════════════════════════════════════════
echo [6/8] 📄 RAG: PyPDF2, python-docx, openpyxl, chardet
echo ══════════════════════════════════════════════════════════════
echo.

pip install PyPDF2 python-docx openpyxl chardet >> "%PIP_LOG%" 2>&1
if errorlevel 1 (
    echo ❌ Ошибка установки RAG
    set /a FAIL_COUNT+=1
    set "FAIL_LIST=!FAIL_LIST! RAG,"
) else (
    echo ✅ RAG установлен
    set /a OK_COUNT+=1
)
echo.

:: ============================================================
::  7. ДОПОЛНИТЕЛЬНЫЕ (Telegram, поиск, корзина)
:: ============================================================
echo ══════════════════════════════════════════════════════════════
echo [7/8] 📱 Telegram + поиск + файлы
echo ══════════════════════════════════════════════════════════════
echo.

pip install python-telegram-bot ddgs send2trash >> "%PIP_LOG%" 2>&1
if errorlevel 1 (
    echo ❌ Ошибка установки дополнительных
    set /a FAIL_COUNT+=1
    set "FAIL_LIST=!FAIL_LIST! telegram/ddgs/trash,"
) else (
    echo ✅ Дополнительные установлены
    set /a OK_COUNT+=1
)
echo.

:: ============================================================
::  8. ОПЦИОНАЛЬНЫЕ (ChromaDB, Wake Word)
:: ============================================================
echo ══════════════════════════════════════════════════════════════
echo [8/8] 🧠 Опциональные: chromadb, openwakeword
echo ══════════════════════════════════════════════════════════════
echo.

echo    Установка ChromaDB (векторный поиск, RAG)...
pip install chromadb >> "%PIP_LOG%" 2>&1
if errorlevel 1 (
    echo    ⚠️ ChromaDB не установлена (RAG будет на ключевых словах)
) else (
    echo    ✅ ChromaDB установлена
    set /a OK_COUNT+=1
)

echo.
echo    Установка openwakeword (активация по слову)...
pip install openwakeword onnxruntime >> "%PIP_LOG%" 2>&1
if errorlevel 1 (
    echo    ⚠️ openwakeword не установлен (Wake Word не будет работать)
) else (
    echo    ✅ Wake Word установлен
    set /a OK_COUNT+=1
)
echo.

:: ============================================================
::  ИТОГИ
:: ============================================================
echo ══════════════════════════════════════════════════════════════
echo    📊 ИТОГИ УСТАНОВКИ
echo ══════════════════════════════════════════════════════════════
echo.
echo    ✅ Групп успешно:  %OK_COUNT% из 10
echo    ❌ Групп с ошибкой: %FAIL_COUNT%

if not "%FAIL_LIST%"=="" (
    echo.
    echo    ⚠️ Проблемные группы:%FAIL_LIST%
    echo.
    echo    Полный лог: pip_install.log
)

echo.
echo ══════════════════════════════════════════════════════════════
echo    🚀 СЛЕДУЮЩИЕ ШАГИ
echo ══════════════════════════════════════════════════════════════
echo.
echo    1. Установи Ollama (если ещё нет):
echo       https://ollama.ai/
echo.
echo    2. Скачай модели:
echo       ollama pull zeta-universal
echo       ollama pull llava:13b
echo.
echo    3. Запусти Zeta:
echo       start_zeta.bat
echo.
echo    4. Или web-версию:
echo       start_web.bat
echo.
echo ══════════════════════════════════════════════════════════════
echo.
echo 💡 Полный лог pip: %PIP_LOG%
echo.

pause