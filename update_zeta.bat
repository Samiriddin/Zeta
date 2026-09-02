@echo off
chcp 65001 >nul 2>&1
title Zeta — Обновление
cd /d D:\Zeta

echo ╔══════════════════════════════════════════════════════════════╗
echo ║           🔄 Zeta — Обновление проекта                     ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

:: Проверяем Git
git --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Git не найден! Установите Git.
    pause
    exit /b 1
)

echo 📦 Проверка обновлений...
git fetch

:: Проверяем, есть ли обновления
for /f %%i in ('git rev-list HEAD..origin/main --count') do set AHEAD=%%i

if "%AHEAD%"=="0" (
    echo ✅ У вас последняя версия Zeta!
    pause
    exit /b 0
)

echo 📥 Найдено %AHEAD% обновлений. Скачиваю...
git pull

echo.
echo 🔄 Обновление зависимостей...
pip install -r requirements.txt >nul 2>&1

echo.
echo ✅ Zeta обновлена до последней версии!
echo.

pause