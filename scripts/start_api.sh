#!/usr/bin/env bash
# Terminal 1: external service Node.js (port 4000) + UI chat di http://localhost:4000
set -euo pipefail
cd "$(dirname "$0")/../api-service"
[ -d node_modules ] || npm install
if [ -f .env ]; then npm run start:env; else npm start; fi
