@echo off
title Zeta - Development Mode
cd /d D:\Zeta

echo ╔══════════════════════════════════════════════════════════╗
echo ║                    🛠️ Zeta Dev Mode                    ║
echo ║                Режим разработки                        ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

:: Устанавливаем переменные окружения
set OLLAMA_MODELS=D:\ollama_models
set PYTHONPATH=D:\Zeta

:: Запускаем с отладкой
echo 🐛 Запуск в режиме отладки...
python main.py

pause