@echo off
rem Lance OJD sous Windows : Ollama (si installé) + serveur, puis ouvre l'interface.
rem Le serveur tourne dans la fenêtre réduite « OJD serveur » : la fermer arrête l'app.
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PORT=8000
rem UTF-8 partout (sinon Windows décode mal les sorties de sherlock, maigret...)
set PYTHONUTF8=1

if not exist ".venv\Scripts\python.exe" (
  echo OJD n'est pas encore installé : lance d'abord install.bat.
  pause
  exit /b 1
)

rem 1. IA locale (Ollama), si installée et pas déjà lancée
curl -s -o nul http://127.0.0.1:11434/api/version
if errorlevel 1 (
  where ollama >nul 2>&1 && start "Ollama" /min ollama serve
)

rem 2. Serveur de l'app, si pas déjà lancé
curl -s -f -o nul http://127.0.0.1:%PORT%/api/modules
if not errorlevel 1 goto open
start "OJD serveur" /min /d "%~dp0backend" "%~dp0.venv\Scripts\python.exe" -m uvicorn app.main:app --port %PORT%
for /l %%i in (1,1,60) do (
  curl -s -f -o nul http://127.0.0.1:%PORT%/api/modules && goto open
  timeout /t 1 /nobreak >nul
)
echo Le serveur ne répond pas : ouvre la fenêtre « OJD serveur » pour voir l'erreur.
pause
exit /b 1

:open
rem 3. Ouvre l'interface (« ?ojd » : jamais une ancienne copie en cache)
start "" "http://localhost:%PORT%/?ojd"
