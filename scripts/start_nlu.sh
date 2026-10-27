#!/usr/bin/env bash
# Terminal 2: NLU service Flask + IndoBERT (port 3000). Melatih model bila belum ada.
set -euo pipefail
cd "$(dirname "$0")/../nlu-service"
source .venv/bin/activate
if [ ! -f models/olshop_intent_model/config.json ]; then
  echo ">> Model belum ada, fine-tuning dulu (sekali saja, beberapa menit)..."
  python train_intent_model.py
fi
python app.py
