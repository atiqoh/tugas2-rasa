#!/usr/bin/env bash
# Setup satu kali di macOS: venv NLU, venv Rasa, dan dependensi Node.
# Prasyarat: MAMP, Node.js >= 18 (disarankan 22 LTS), koneksi internet.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo ">> Memasang uv (package manager Python)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

echo ">> [1/3] NLU service (Python 3.11 + PyTorch + Transformers)"
cd "$ROOT/nlu-service"
uv venv --python 3.11 .venv
source .venv/bin/activate
if [ "$(uname -m)" = "x86_64" ]; then
  echo "   Mac Intel terdeteksi -> torch 2.2.2 (wheel terakhir untuk macOS x86_64)"
  uv pip install "torch==2.2.2" "numpy<2"
fi
uv pip install -r requirements.txt
deactivate

echo ">> [2/3] Rasa Pro (venv terpisah)"
cd "$ROOT/rasa-bot"
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install "rasa-pro[nlu]" requests
# TEDPolicy uses TensorFlow, but the optional Metal plugin can be incompatible with its wheel.
uv pip uninstall tensorflow-metal || true
rasa --version || true
deactivate

echo ">> [3/3] API service (Node.js)"
cd "$ROOT/api-service"
npm install

echo
echo "Selesai. Langkah berikutnya: import database/olshop_db.sql di phpMyAdmin MAMP,"
echo "lalu jalankan scripts/start_api.sh, scripts/start_nlu.sh, scripts/start_rasa.sh"
echo "di tiga jendela Terminal terpisah."
