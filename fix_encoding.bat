@echo off
chcp 65001 >nul 2>&1
title Zeta — Исправление кодировки
cd /d D:\Zeta

echo 🔧 Устанавливаем правильную кодировку для Python...
echo.

:: Устанавливаем PYTHONIOENCODING
setx PYTHONIOENCODING utf-8

:: Устанавливаем PYTHONUTF8
setx PYTHONUTF8 1

echo ✅ Переменные окружения установлены.
echo.
echo ⚠️ Перезапустите командную строку, чтобы изменения вступили в силу.
echo.

pause