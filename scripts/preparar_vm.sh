#!/usr/bin/env bash
# Preparación única de la VM (Ubuntu 24.04) — docs/despliegue_nube.md. Corre EN la VM:
#   ssh -i ~/.ssh/amate_oracle ubuntu@<dominio> 'bash -s' < scripts/preparar_vm.sh
set -euo pipefail

# 1. Solo en Oracle: sus imágenes de Ubuntu rechazan en iptables todo menos el 22. Va ANTES de instalar Docker:
#    guardar las reglas después guardaría también las de Docker (se duplicarían al reiniciar). En Azure el
#    firewall es el NSG del portal y este paso no aplica.
if command -v netfilter-persistent >/dev/null; then
  for puerto in 443 80; do
    sudo iptables -C INPUT -p tcp --dport "$puerto" -j ACCEPT 2>/dev/null \
      || sudo iptables -I INPUT 5 -p tcp -m state --state NEW --dport "$puerto" -j ACCEPT
  done
  sudo netfilter-persistent save
fi

# 2. Swap de 4 GB: holgura para compilar la imagen del backend con 12 GB de RAM.
if [ ! -f /swapfile ]; then
  sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

# 3. Docker de los repositorios de Ubuntu (Compose ≥ 2.24 para !reset/!override de docker-compose.nube.yml).
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 rsync
sudo usermod -aG docker ubuntu
docker compose version
