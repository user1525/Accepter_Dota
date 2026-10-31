@echo off
cd /d "%~dp0"
chcp 65001 >nul
echo Запуск Dota 2 Accepter...
echo.

python main.py

echo.
echo Программа завершена.
pause
