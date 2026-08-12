@echo off
REM ---------------------------------------------------------------------------
REM  Genera dist\recorridos\ con recorridos.exe adentro.
REM  Requiere Python instalado en ESTA maquina (solo para compilar).
REM  --onedir (no --onefile): mucho menos falso positivo de antivirus,
REM  arranque mas rapido y actualizar = reemplazar la carpeta.
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"

python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

python -m PyInstaller ^
  --noconfirm ^
  --onedir ^
  --windowed ^
  --name recorridos ^
  --exclude-module numpy ^
  --exclude-module pandas ^
  --exclude-module matplotlib ^
  --exclude-module PIL ^
  --exclude-module pytest ^
  app.py

echo.
echo Listo. Copia la carpeta  dist\recorridos\  al disco compartido.
pause
