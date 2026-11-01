#!/usr/bin/env bash
# Prepare the Laya training data and fine-tune a checkpoint.
# Run from the repository root: ./train_laya_checkpoint.sh
set -euo pipefail
cd "$(dirname "$0")"

if command -v laya-train >/dev/null 2>&1 || python3 -c "import laya.train_cli" >/dev/null 2>&1; then
  exec python3 scripts/train_laya_checkpoint.py "$@"
fi

case " $* " in
  *" --prepare-only "*)
    exec python3 scripts/train_laya_checkpoint.py "$@"
    ;;
esac

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  echo "Laya não está instalado no host; executando dentro do container..."
  INSTALL_LAYA="${INSTALL_LAYA:-true}" \
    docker compose run --rm smat bash -lc \
    "cd /app && python3 scripts/train_laya_checkpoint.py $*"
  exit $?
fi

cat <<'EOF'
Laya não está instalado no host e o Docker não está disponível.

Opções:
1. Instale as dependências no host:
     python3 -m pip install -r SMAT/requirements-laya.txt
     ./train_laya_checkpoint.sh

2. Construa/execute pelo Docker (com Laya):
     INSTALL_LAYA=true USER_ID=$(id -u) GROUP_ID=$(id -g) \
       docker compose build smat
     INSTALL_LAYA=true ./train_laya_checkpoint.sh

O script gera os dados primeiro em laya_training_data/ e depois salva o
checkpoint em laya_checkpoints/laya_finetuned_smat_multilingual/.
EOF
exit 1
