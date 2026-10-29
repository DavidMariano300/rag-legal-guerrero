#!/usr/bin/env bash
# Copia el código local a la VM de la nube y reconstruye los servicios (docs/despliegue_nube.md).
# No pasa por GitHub: sube lo que hay en esta carpeta, sin .git, node_modules ni el .env local.
# Uso: scripts/desplegar.sh <dominio-o-ip-de-la-vm>
set -euo pipefail

IP="${1:?Uso: scripts/desplegar.sh <dominio-o-ip-de-la-vm>}"
SSH=(ssh -i ~/.ssh/amate_oracle -o StrictHostKeyChecking=accept-new "ubuntu@$IP")

cd "$(dirname "$0")/.."
rsync -az --delete -e "ssh -i $HOME/.ssh/amate_oracle" \
  --exclude .git --exclude node_modules --exclude dist --exclude .env --exclude .claude \
  --exclude graphify-out --exclude __pycache__ \
  ./ "ubuntu@$IP:~/amate/"
"${SSH[@]}" 'cd ~/amate && docker compose up -d --build && docker compose ps'
