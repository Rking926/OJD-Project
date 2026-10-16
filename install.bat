@echo off
rem Installation d'OJD sous Windows : Python (si absent), environnement virtuel,
rem dependances des connecteurs, verification d'Ollama, raccourci Bureau.
rem Usage : double-clic sur install.bat
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo.
echo ==^> Python
rem Il faut Python 3.12 ou plus récent (numpy l'exige).
set "PY="
for %%V in (3.13 3.12 3.14) do if not defined PY py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>&1 && set "PY=python"
if not defined PY (
  echo   Pas de Python 3.12+ : installation de Python 3.13 avec winget...
  winget install -e --id Python.Python.3.13 --accept-package-agreements --accept-source-agreements
  echo.
  echo   Python vient d'être installé. Ferme cette fenêtre et relance install.bat.
  pause
  exit /b 1
)
%PY% --version

echo.
echo ==^> Environnement Python (.venv)
if not exist ".venv\Scripts\python.exe" (
  %PY% -m venv .venv || (echo   Échec de création du venv. & pause & exit /b 1)
)
set "VPY=%~dp0.venv\Scripts\python.exe"
set PYTHONUTF8=1

echo.
echo ==^> Dépendances des connecteurs (quelques minutes la première fois)
"%VPY%" -m pip install --quiet --upgrade pip
"%VPY%" -m pip install -r backend\requirements.txt
if errorlevel 1 (
  echo   Échec d'installation de certaines dépendances : voir les messages ci-dessus.
  pause
  exit /b 1
)
echo   OK

echo.
echo ==^> IA locale (Ollama)
where ollama >nul 2>&1
if errorlevel 1 (
  echo   Ollama n'est pas installé. Pour l'IA locale gratuite :
  echo     winget install -e --id Ollama.Ollama
  echo   puis télécharge un modèle :  ollama pull llama3.1
  echo   ^(sinon, mets une clé API Anthropic dans Paramètres^)
) else (
  echo   Ollama présent
)

echo.
echo ==^> Connecteurs
echo   sherlock, maigret, holehe, whois, dns, crtsh, phone, ipinfo : OK sous Windows
echo   theharvester, nmap/recon, metasploit : outils Kali, indisponibles sous Windows

echo.
echo ==^> Raccourci
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0creer-raccourci.ps1"

echo.
echo Terminé. Lance OJD avec le raccourci « OJD OSINT » du Bureau, ou start.bat.
pause
