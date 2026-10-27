"""
baseline_tfidf.py  -  Pembanding klasik (TF-IDF + Logistic Regression)
=====================================================================
Dipakai untuk menjawab Q1b secara empiris: seberapa besar keuntungan model BERT eksternal
dibanding pendekatan bag-of-words (yang mirip CountVectorsFeaturizer pada pipeline
bawaan Rasa). Input teks diproses dengan entity masking + normalisasi yang sama.
Tidak butuh GPU / PyTorch.  Jalankan: python baseline_tfidf.py
"""
import json

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import FeatureUnion, make_pipeline

import nlu_config as cfg
from entity_extractor import EntityExtractor


def main():
    ex = EntityExtractor.from_resources()
    train = pd.read_csv(cfg.TRAIN_CSV)
    test = pd.read_csv(cfg.HELDOUT_CSV)
    train["model_text"] = [ex.prepare(t)[0] for t in train.text]
    test["model_text"] = [ex.prepare(t)[0] for t in test.text]
    tr, va = train_test_split(train, test_size=cfg.VAL_SIZE, random_state=cfg.SEED,
                              stratify=train.intent)

    clf = make_pipeline(
        FeatureUnion([
            ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True)),
            ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5),
                                     sublinear_tf=True)),
        ]),
        LogisticRegression(max_iter=3000, C=10),
    )
    clf.fit(tr.model_text, tr.intent)
    out = {}
    for name, df in [("validation", va), ("heldout", test)]:
        pred = clf.predict(df.model_text)
        conf = clf.predict_proba(df.model_text).max(axis=1)
        out[name] = {"accuracy": round(accuracy_score(df.intent, pred), 4),
                     "macro_f1": round(f1_score(df.intent, pred, average="macro"), 4),
                     "below_threshold": round(float((conf < cfg.FALLBACK_THRESHOLD).mean()), 4)}
        if name == "heldout":
            rep = classification_report(df.intent, pred, digits=3, zero_division=0)
            errors = df.assign(pred=pred, confidence=conf.round(3))
            errors = errors[errors.pred != errors.intent]
    cfg.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (cfg.REPORT_DIR / "baseline_tfidf_metrics.json").write_text(json.dumps(out, indent=2))
    (cfg.REPORT_DIR / "baseline_tfidf_report_heldout.txt").write_text(rep)
    errors.to_csv(cfg.REPORT_DIR / "baseline_tfidf_heldout_errors.csv", index=False)
    print(json.dumps(out, indent=2))
    print(rep)
    print(errors[["text", "intent", "pred", "confidence"]].to_string(index=False))


if __name__ == "__main__":
    main()
