@echo off
chcp 65001 >nul 2>&1
title Zeta — Исправление кодировки (UTF-8)
cd /d "%~dp0"

setlocal enabledelayedexpansion

echo ╔══════════════════════════════════════════════════════════╗
echo ║           🔧 Zeta — Исправление кодировки              ║
echo ║              UTF-8 для Python на Windows                ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

:: ============================================================
::  0. ПАРАМЕТРЫ
:: ============================================================
set "MODE=install"
if /I "%~1"=="--unset" set "MODE=unset"
if /I "%~1"=="-u" set "MODE=unset"

if "%MODE%"=="unset" (
    echo ⚠️ РЕЖИМ УДАЛЕНИЯ — переменные будут удалены
    echo.
    goto :unset_vars
)

:: ============================================================
::  1. ПРОВЕРКА PYTHON
:: ============================================================
echo [1/6] 🐍 Проверка Python...

python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python не найден!
    echo    Установи Python 3.12+: https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VER=%%i
echo ✅ Python %PYTHON_VER%
echo.

:: ============================================================
::  2. ПОКАЗ ТЕКУЩИХ ЗНАЧЕНИЙ
:: ============================================================
echo [2/6] 📊 Текущие переменные окружения...

echo    PYTHONIOENCODING:
reg query "HKCU\Environment" /v PYTHONIOENCODING >nul 2>&1
if errorlevel 1 (
    echo       ❌ не установлена
) else (
    for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v PYTHONIOENCODING 2^>nul ^| findstr /I "PYTHONIOENCODING"') do (
        echo       ✅ %%b
    )
)

echo    PYTHONUTF8:
reg query "HKCU\Environment" /v PYTHONUTF8 >nul 2>&1
if errorlevel 1 (
    echo       ❌ не установлена
) else (
    for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v PYTHONUTF8 2^>nul ^| findstr /I "PYTHONUTF8"') do (
        echo       ✅ %%b
    )
)
echo.

:: ============================================================
::  3. УСТАНОВКА ПЕРЕМЕННЫХ
:: ============================================================
echo [3/6] 🔧 Установка переменных...

:: setx — для будущих сессий (постоянно, в реестр пользователя)
setx PYTHONIOENCODING utf-8 >nul 2>&1
if errorlevel 1 (
    echo    ⚠️ PYTHONIOENCODING — ошибка setx
) else (
    echo    ✅ PYTHONIOENCODING=utf-8 (постоянно)
)

setx PYTHONUTF8 1 >nul 2>&1
if errorlevel 1 (
    echo    ⚠️ PYTHONUTF8 — ошибка setx
) else (
    echo    ✅ PYTHONUTF8=1 (постоянно)
)

:: set — для ТЕКУЩЕЙ сессии (чтобы тест ниже работал сразу)
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
echo    ✅ Применено к текущей сессии
echo.

:: ============================================================
::  4. ПРОВЕРКА РЕЕСТРА
:: ============================================================
echo [4/6] 🔍 Проверка записи в реестре...

set "OK=1"

reg query "HKCU\Environment" /v PYTHONIOENCODING 2>nul | findstr /I "utf-8" >nul
if errorlevel 1 (
    echo    ❌ PYTHONIOENCODING НЕ записана
    set "OK=0"
) else (
    echo    ✅ PYTHONIOENCODING записана
)

reg query "HKCU\Environment" /v PYTHONUTF8 2>nul | findstr /I "1" >nul
if errorlevel 1 (
    echo    ❌ PYTHONUTF8 НЕ записана
    set "OK=0"
) else (
    echo    ✅ PYTHONUTF8 записана
)

if "%OK%"=="0" (
    echo.
    echo ⚠️  Что-то пошло не так. Возможные причины:
    echo    - Нет прав на запись в HKCU\Environment (редко)
    echo    - Антивирус блокирует setx
    echo    - Windows Defender Application Control
    echo.
)

echo.

:: ============================================================
::  5. БЫСТРЫЙ ТЕСТ UTF-8
:: ============================================================
echo [5/6] 🧪 Тест UTF-8 в Python...

python -c "import sys; print('✅ UTF-8 OK:', sys.stdout.encoding)" 2>nul
if errorlevel 1 (
    echo    ⚠️ Тест не прошёл. Возможно, нужен перезапуск консоли.
) else (
    echo    ✅ Тест пройден
)

:: Тест эмодзи
python -c "print('🚀 Тест эмодзи: ✅🎯🤖')" 2>nul
if errorlevel 1 (
    echo    ⚠️ Эмодзи не работают — перезапусти консоль
) else (
    echo    ✅ Эмодзи работают
)
echo.

:: ============================================================
::  6. ИТОГИ И ЧТО ДАЛЬШЕ
:: ============================================================
echo [6/6] 📋 Результат
echo.
echo ══════════════════════════════════════════════════════════════
echo    ✅ Переменные окружения установлены
echo ══════════════════════════════════════════════════════════════
echo.
echo    📌 Что теперь работает корректно:
echo       • Эмодзи в консоли Python 🤖 ✅ 🚀
echo       • Русский текст без кракозябр
echo       • Логи с эмодзи (data/zeta.log)
echo       • .bat-файлы Zeta без ошибок кодировки
echo.
echo    📌 Где это было проблемой:
echo       • main.py       — логи с эмодзи
echo       • ui/widget.py  — принты
echo       • modules/*.py  — отладочные выводы
echo       • core/*.py     — ошибки с русским текстом
echo.
echo ══════════════════════════════════════════════════════════════
echo    ⚠️  ВАЖНО: ЗАКРОЙ и ОТКРОЙ заново
echo       PowerShell / CMD / VS Code / терминал
echo.
echo       Иначе переменные НЕ применятся!
echo ══════════════════════════════════════════════════════════════
echo.
echo    💡 Как проверить после перезапуска:
echo       python -c "import sys; print(sys.stdout.encoding)"
echo.
echo       Должно быть: utf-8
echo.
echo    💡 Откатить изменения:
echo       fix_encoding.bat --unset
echo.
echo ══════════════════════════════════════════════════════════════
echo.

:: Спрашиваем, перезапустить ли консоль
choice /C YN /M "Открыть новое окно PowerShell сейчас"
if errorlevel 2 goto :end
if errorlevel 1 (
    echo.
    echo 🚀 Открываю новое окно PowerShell...
    start powershell -NoExit -Command "cd '%CD%'; Write-Host '✅ Новая сессия с UTF-8' -ForegroundColor Green"
)

:end
echo.
echo Готово! Не забудь перезапустить текущую консоль.
echo.
pause
exit /b 0


:: ============================================================
::  РЕЖИМ УДАЛЕНИЯ (--unset)
:: ============================================================
:unset_vars
echo [1/2] 🗑️ Удаление переменных...

reg delete "HKCU\Environment" /v PYTHONIOENCODING /f >nul 2>&1
if errorlevel 1 (
    echo    ⚠️ PYTHONIOENCODING — не найдена или уже удалена
) else (
    echo    ✅ PYTHONIOENCODING удалена
)

reg delete "HKCU\Environment" /v PYTHONUTF8 /f >nul 2>&1
if errorlevel 1 (
    echo    ⚠️ PYTHONUTF8 — не найдена или уже удалена
) else (
    echo    ✅ PYTHONUTF8 удалена
)

echo.
echo [2/2] 📋 Готово
echo.
echo ⚠️ Перезапусти консоль, чтобы удаление применилось.
echo.
pause
exit /b 0