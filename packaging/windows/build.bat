@echo off
REM ============================================================
REM  ScanLab - compilacion para Windows
REM  Requisitos previos (una sola vez):
REM    1. Python 3.12 o superior de python.org
REM       (marcar "Add python.exe to PATH" al instalar)
REM    2. Driver Epson Scan del V500 para Windows instalado
REM  Uso: doble clic en este archivo, o ejecutarlo en un cmd.
REM  Resultado: dist\ScanLab\ScanLab.exe
REM ============================================================
setlocal
cd /d "%~dp0..\.."

echo [1/4] Creando entorno virtual...
if not exist .venv-win (
    python -m venv .venv-win || goto :error
)

echo [2/4] Instalando dependencias...
.venv-win\Scripts\python -m pip install --upgrade pip >nul
.venv-win\Scripts\pip install -r requirements.txt pyinstaller || goto :error

echo [3/4] Compilando con PyInstaller...
.venv-win\Scripts\pyinstaller --noconfirm --clean --windowed --name ScanLab launcher.py || goto :error

echo [4/4] Hecho!
echo.
echo   Ejecutable: %CD%\dist\ScanLab\ScanLab.exe
echo.
echo   Para crear el instalador: instala Inno Setup 6
echo   (https://jrsoftware.org/isdl.php) y compila
echo   packaging\windows\installer.iss (boton Compile).
echo.
pause
exit /b 0

:error
echo.
echo *** ERROR: revisa el mensaje de arriba ***
pause
exit /b 1
