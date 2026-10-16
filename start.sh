#!/usr/bin/env bash
# Lance OJD : Ollama (IA locale) + serveur de l'app, puis ouvre l'interface.
set -u

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
OLLAMA_BIN="$HOME/.local/ollama/bin/ollama"
PORT=8000
LOG_DIR="$PROJECT_DIR/backend/data/logs"
mkdir -p "$LOG_DIR"

# Les modèles IA vivent sur le disque Windows (partition Linux trop petite).
export OLLAMA_MODELS="/mnt/windows/ollama-models"
if ! mountpoint -q /mnt/windows; then
  echo "ATTENTION : /mnt/windows n'est pas monté — les modèles IA sont indisponibles." >&2
  echo "  Monte-le avec : sudo mount /mnt/windows   (ou vérifie /etc/fstab), puis relance." >&2
fi

# 1. IA locale (Ollama), si pas déjà lancée
if ! curl -s localhost:11434/api/version >/dev/null 2>&1; then
  if [ -x "$OLLAMA_BIN" ]; then
    nohup "$OLLAMA_BIN" serve >"$LOG_DIR/ollama.log" 2>&1 &
  fi
fi

# 2. Serveur de l'app, si pas déjà lancé
if ! curl -s "localhost:$PORT/api/modules" >/dev/null 2>&1; then
  cd "$PROJECT_DIR/backend" || exit 1
  nohup "$PROJECT_DIR/.venv/bin/uvicorn" app.main:app --port "$PORT" >"$LOG_DIR/server.log" 2>&1 &
  for _ in $(seq 1 30); do
    curl -s "localhost:$PORT/api/modules" >/dev/null 2>&1 && break
    sleep 0.5
  done
fi

# 3. Ouvre l'interface (« ?ojd » : adresse jamais mise en cache par une
#    ancienne version ; le serveur interdit ensuite le cache périmé)
xdg-open "http://localhost:$PORT/?ojd" >/dev/null 2>&1 &
