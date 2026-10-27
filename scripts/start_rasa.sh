#!/usr/bin/env bash
# Terminal 3: Rasa Pro (port 5005). Pakai "inspect" sebagai argumen untuk membuka Rasa Inspector.
#   ./scripts/start_rasa.sh           -> rasa run (dipakai UI chat di localhost:4000)
#   ./scripts/start_rasa.sh inspect   -> rasa inspect (debug tracker/slot di browser)
set -euo pipefail
cd "$(dirname "$0")/../rasa-bot"
source .venv/bin/activate
: "${RASA_LICENSE:?Set dulu: export RASA_LICENSE=<license key dari email Rasa>}"
export OLSHOP_API_URL="${OLSHOP_API_URL:-http://localhost:4000}"
if ! ls models/*.tar.gz >/dev/null 2>&1; then
  rasa data validate || true
  rasa train
fi
if [ "${1:-}" = "inspect" ]; then
  rasa inspect
else
  rasa run --enable-api --cors "*" --endpoints endpoints.yml --credentials credentials.yml
fi
