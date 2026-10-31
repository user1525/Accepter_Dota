@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if errorlevel 1 exit /b 1

echo Dota Accepter - Windows 10/11 x64 build
python -c "import sys, struct; sys.exit(0 if sys.platform == 'win32' and struct.calcsize('P') == 8 and sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
    echo [ERROR] Требуется 64-битный Python 3.10+ для Windows.
    exit /b 1
)
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Установите зависимости: python -m pip install -r requirements.txt
    exit /b 1
)
python -m PyInstaller --noconfirm --clean --distpath "%~dp0dist\portable" --workpath "%~dp0build" "%~dp0accepter.spec"
if errorlevel 1 exit /b 1
if not exist "%~dp0dist\portable\Accepter.exe" exit /b 1
echo [SUCCESS] %~dp0dist\portable\Accepter.exe
echo Ресурсы встроены в EXE. При первом запуске рядом создаётся config.json.
echo Токены зашифрованы для текущего пользователя Windows.
echo На другом ПК подключите Telegram и Яндекс заново.
endlocal
