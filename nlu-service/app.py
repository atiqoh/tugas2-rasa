"""
app.py  -  External NLU service (pengembangan dari myInterpreter.py, modul bab 6 & 7)
==================================================================================
Rasa memanggil service ini lewat `endpoints.yml -> nlu: url: http://localhost:3000`.
Rasa (RasaNLUHttpInterpreter) mengirim:  POST {url}/model/parse
    {"text": "...", "message_id": "<sender_id>", "token": null}
dan mengharapkan balasan berformat hasil parse Rasa NLU.

Endpoint:
  POST /model/parse   -> intent + confidence + intent_ranking + entities
  GET  /health        -> status service & model
  GET  /model/info    -> label intent, ambang fallback, metrik training

Jalankan:  python app.py      (setelah python train_intent_model.py)
"""
from __future__ import annotations

import json
import logging
import re
import time

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

import nlu_config as cfg
from entity_extractor import PRODUCT_INTENTS, EntityExtractor

log = logging.getLogger("nlu-service")

# "/check_stock" atau '/check_stock{"product": "iPhone X"}' (payload tombol / perintah
# internal Rasa seperti /session_start). Interpreter HTTP Rasa TIDAK menangani format ini
# sendiri, jadi service ini yang harus mengurainya.
SHORTCUT_RE = re.compile(r"^/([A-Za-z_][A-Za-z0-9_]*)(\{.*\})?\s*$", re.DOTALL)


def parse_shortcut(text: str) -> dict | None:
    m = SHORTCUT_RE.match(text.strip())
    if not m:
        return None
    entities = []
    if m.group(2):
        try:
            payload = json.loads(m.group(2))
        except json.JSONDecodeError:
            payload = {}
        for k, v in payload.items():
            for val in (v if isinstance(v, list) else [v]):
                entities.append({"entity": k, "value": val, "start": 0, "end": len(text),
                                 "confidence_entity": 1.0, "extractor": "ShortcutParser"})
    intent = {"name": m.group(1), "confidence": 1.0}
    return {"text": text, "intent": intent, "intent_ranking": [intent], "entities": entities}


def build_parse_result(text: str, extractor: EntityExtractor, classifier,
                       threshold: float) -> dict:
    started = time.perf_counter()
    model_text, entities = extractor.prepare(text[:cfg.MAX_CHARS])
    if not model_text:
        ranking = [("nlu_fallback", 1.0)]
    else:
        ranking = classifier.predict(model_text, top_k=5)
    top_name, top_conf = ranking[0]
    intent_ranking = [{"name": n, "confidence": round(c, 6)} for n, c in ranking]
    if top_name != "nlu_fallback" and top_conf < threshold:
        # Sama seperti FallbackClassifier Rasa: intent diganti nlu_fallback dengan
        # confidence = ambang, ranking asli tetap disertakan untuk debugging.
        intent = {"name": "nlu_fallback", "confidence": threshold}
        intent_ranking = [intent] + intent_ranking
    else:
        intent = {"name": top_name, "confidence": round(top_conf, 6)}
    if intent["name"] in PRODUCT_INTENTS and not any(e["entity"] == "product"
                                                     for e in entities):
        cand = extractor.guess_product_candidate(text[:cfg.MAX_CHARS], entities)
        if cand:
            entities.append(cand)
    return {
        "text": text,
        "intent": intent,
        "intent_ranking": intent_ranking,
        "entities": entities,
        "nlu_debug": {"model_input": model_text,
                      "latency_ms": round((time.perf_counter() - started) * 1000, 1)},
    }


def create_app(classifier=None, extractor: EntityExtractor | None = None,
               threshold: float = cfg.FALLBACK_THRESHOLD) -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.json.sort_keys = False
    extractor = extractor or EntityExtractor.from_resources()
    if classifier is None:
        from intent_classifier import IntentClassifier
        classifier = IntentClassifier(cfg.MODEL_DIR, max_len=cfg.MAX_LEN)

    @app.route("/model/parse", methods=["POST"])
    def parse():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error="Body harus JSON, contoh: {\"text\": \"halo\"}"), 400
        text = data.get("text")
        if not isinstance(text, str):
            return jsonify(error="Field 'text' wajib berupa string"), 400
        result = parse_shortcut(text) if text.strip().startswith("/") else None
        if result is None:
            result = build_parse_result(text, extractor, classifier, threshold)
        log.info("parse text=%r intent=%s conf=%.3f entities=%s", text,
                 result["intent"]["name"], result["intent"]["confidence"],
                 [(e["entity"], e["value"]) for e in result["entities"]])
        return jsonify(result)

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify(status="ok", model_loaded=classifier is not None,
                       n_intents=len(getattr(classifier, "labels", [])))

    @app.route("/model/info", methods=["GET"])
    def info():
        return jsonify(base_model=getattr(classifier, "meta", {}).get("base_model"),
                       intents=list(getattr(classifier, "labels", [])),
                       fallback_threshold=threshold,
                       training_meta=getattr(classifier, "meta", {}))

    @app.errorhandler(HTTPException)
    def http_error(e: HTTPException):
        return jsonify(error=e.description), e.code

    @app.errorhandler(Exception)
    def unhandled(e: Exception):
        log.exception("Kesalahan tak terduga")
        return jsonify(error="Internal error di NLU service"), 500

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    application = create_app()
    print(f"NLU service berjalan di http://localhost:{cfg.PORT}  (POST /model/parse)")
    application.run(host=cfg.HOST, port=cfg.PORT, debug=False)
