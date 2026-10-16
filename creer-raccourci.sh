#!/usr/bin/env bash
# Crée un raccourci « OJD OSINT » sur le Bureau et dans le menu des applications.
# Un double-clic lance start.sh (Ollama + serveur) puis ouvre l'interface.
#
# Usage :  ./creer-raccourci.sh   (à relancer si tu déplaces le dossier du projet)
set -eu

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Bureau")"
APPS_DIR="$HOME/.local/share/applications"
ICON="$PROJECT_DIR/frontend/icon.svg"

mkdir -p "$APPS_DIR" "$DESKTOP_DIR"
chmod +x "$PROJECT_DIR/start.sh"

write_entry() {  # <fichier .desktop>
  cat >"$1" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=OJD OSINT
Comment=Assistant d'investigation OSINT
Exec=bash "$PROJECT_DIR/start.sh"
Path=$PROJECT_DIR
Icon=$ICON
Terminal=false
Categories=Network;Utility;
StartupNotify=false
EOF
  chmod +x "$1"
}

write_entry "$APPS_DIR/ojd-osint.desktop"
DESKTOP_FILE="$DESKTOP_DIR/OJD OSINT.desktop"
write_entry "$DESKTOP_FILE"

# Marque le raccourci comme fiable pour qu'il se lance au double-clic sans
# avertissement (Xfce 4.18+ vérifie une empreinte, GNOME un simple drapeau).
if command -v gio >/dev/null 2>&1; then
  gio set "$DESKTOP_FILE" metadata::xfce-exe-checksum "$(sha256sum "$DESKTOP_FILE" | cut -d' ' -f1)" 2>/dev/null || true
  gio set "$DESKTOP_FILE" metadata::trusted true 2>/dev/null || true
fi
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS_DIR" 2>/dev/null || true

echo "✓ Raccourci créé : $DESKTOP_FILE"
echo "✓ Aussi dans le menu des applications : « OJD OSINT »"
