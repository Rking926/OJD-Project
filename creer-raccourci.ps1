# Crée le raccourci « OJD OSINT » sur le Bureau et dans le menu Démarrer.
# Lancé par install.bat ; à relancer si tu déplaces le dossier du projet :
#   powershell -ExecutionPolicy Bypass -File creer-raccourci.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$shell = New-Object -ComObject WScript.Shell
$targets = @(
  [Environment]::GetFolderPath('Desktop'),   # suit OneDrive / « Bureau » si besoin
  [Environment]::GetFolderPath('Programs')   # menu Démarrer
)
foreach ($dir in $targets) {
  $path = Join-Path $dir 'OJD OSINT.lnk'
  $lnk = $shell.CreateShortcut($path)
  $lnk.TargetPath = Join-Path $root 'start.bat'
  $lnk.WorkingDirectory = $root
  $lnk.IconLocation = (Join-Path $root 'frontend\icon.ico') + ',0'
  $lnk.WindowStyle = 7   # fenêtre de lancement réduite
  $lnk.Description = "Assistant d'investigation OSINT"
  $lnk.Save()
  Write-Host "  Raccourci créé : $path"
}
