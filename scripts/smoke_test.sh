#!/usr/bin/env bash
# Cek cepat semua service setelah dijalankan (butuh curl).
set -u
echo "== API service (Node + MySQL MAMP)"
curl -s http://localhost:4000/api/health; echo
curl -s "http://localhost:4000/api/products/search?q=iphone%20x&limit=1"; echo
echo "== NLU service (Flask + IndoBERT)"
curl -s -X POST http://localhost:3000/model/parse -H 'Content-Type: application/json' \
     -d '{"text":"kak iphone x ready ga?"}'; echo
echo "== Rasa (REST channel)"
curl -s -X POST http://localhost:5005/webhooks/rest/webhook -H 'Content-Type: application/json' \
     -d '{"sender":"smoke","message":"stok iphone x ada?"}'; echo
