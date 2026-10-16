#!/usr/bin/env bash
# Installation complète d'OJD : venv + toutes les dépendances Python des
# connecteurs + vérification des outils système, pour que TOUS les connecteurs
# soient opérationnels après installation.
#
# Usage :  ./install.sh
set -u

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$PROJECT_DIR/.venv"
PY_BIN="$(command -v python3 || command -v python)"

say() { printf "\n\033[1;36m==> %s\033[0m\n" "$*"; }
ok()  { printf "  \033[1;32m✓\033[0m %s\n" "$*"; }
no()  { printf "  \033[1;31m✗\033[0m %s\n" "$*"; }
warn(){ printf "  \033[1;33m!\033[0m %s\n" "$*"; }

# 1. venv -------------------------------------------------------------------
say "Environnement Python (venv)"
if [ ! -x "$VENV/bin/python" ]; then
  "$PY_BIN" -m venv "$VENV" && ok "venv créé : $VENV"
else
  ok "venv déjà présent"
fi
PY="$VENV/bin/python"

# 2. dépendances Python (connecteurs) ---------------------------------------
say "Dépendances Python des connecteurs"
"$PY" -m pip install --quiet --upgrade pip
if "$PY" -m pip install --quiet -r "$PROJECT_DIR/backend/requirements.txt"; then
  ok "requirements.txt installé"
else
  no "échec d'installation de certaines dépendances (voir ci-dessus)"
fi

# 3. outils système (binaires) ----------------------------------------------
say "Outils système requis par certains connecteurs"
APT_MISSING=()
check_bin() {  # <cmd> <paquet-apt> <connecteur>
  if command -v "$1" >/dev/null 2>&1; then
    ok "$3 : $1 présent"
  else
    no "$3 : $1 ABSENT (paquet: $2)"
    APT_MISSING+=("$2")
  fi
}
check_bin theHarvester theharvester "theharvester"
check_bin nmap nmap "recon/lab"
check_bin msfconsole metasploit-framework "metasploit (labo)"

if [ "${#APT_MISSING[@]}" -gt 0 ]; then
  PKGS="$(printf '%s ' "${APT_MISSING[@]}")"
  if command -v apt >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    warn "installation des paquets manquants : $PKGS"
    sudo DEBIAN_FRONTEND=noninteractive apt install -y $PKGS && ok "paquets installés"
  else
    warn "Installe les paquets manquants avec : sudo apt install -y $PKGS"
  fi
fi

# 4. Ollama (IA locale) -----------------------------------------------------
say "IA locale (Ollama)"
if curl -s localhost:11434/api/version >/dev/null 2>&1; then
  ok "Ollama en marche"
else
  warn "Ollama ne répond pas sur localhost:11434 — lance-le (ex: 'ollama serve')."
fi

# 5. Récapitulatif des connecteurs -----------------------------------------
say "État des connecteurs"
ok "sherlock, maigret, holehe, whois, dns, crtsh, phone, ipinfo, xposedornot : opérationnels (aucune clé requise)"
ok "theharvester, recon_tool, metasploit : opérationnels si les binaires ci-dessus sont présents"
warn "hibp : optionnel — nécessite une clé API HIBP payante (xposedornot couvre les fuites gratuitement)"
warn "toutatis : optionnel — nécessite TON sessionid Instagram (hors CGU, désactivé par défaut)"

# 6. Raccourci Bureau + menu des applications ------------------------------
say "Raccourci"
"$PROJECT_DIR/creer-raccourci.sh" || warn "raccourci non créé (lance ./creer-raccourci.sh)"

say "Terminé. Lance l'app avec le raccourci « OJD OSINT » ou :  ./start.sh"
