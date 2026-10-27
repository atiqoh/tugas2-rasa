"""
train_intent_model.py  -  Fine-tuning model intent (BERT/IndoBERT) DI LUAR Rasa
==============================================================================
Struktur mengikuti fine-tuning.py pada modul bab 6/7 (Dataset class -> train_model ->
evaluate_model -> save_model), dengan perbaikan:
  * teks diproses dengan entity masking + normalisasi yang SAMA dengan app.py
  * split train/validation stratified + test set held-out terpisah (ditulis manual)
  * max_length 64 (bukan 512) karena kalimat chat pendek -> training jauh lebih cepat
  * AdamW + linear warmup, simpan model TERBAIK berdasarkan macro-F1 validasi
  * label disimpan di config model (id2label) -> tidak perlu label_encoder.pkl
  * dukungan GPU Apple Silicon (MPS)

Output:
  models/olshop_intent_model/   (model + tokenizer + training_meta.json)
  reports/                      (metrics.json, classification report, confusion matrix,
                                 kurva loss, daftar salah prediksi)
Jalankan:  python train_intent_model.py
"""
from __future__ import annotations

import json
import os
import random
import time

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import (accuracy_score, classification_report, confusion_matrix,
                             f1_score)
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader, Dataset
from transformers import (AutoModelForSequenceClassification, AutoTokenizer,
                          DataCollatorWithPadding, get_linear_schedule_with_warmup)

import nlu_config as cfg
from entity_extractor import EntityExtractor
from intent_classifier import pick_device


def set_seed(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


class IntentDataset(Dataset):
    def __init__(self, texts, labels, tokenizer, max_len):
        self.texts, self.labels = list(texts), list(labels)
        self.tokenizer, self.max_len = tokenizer, max_len

    def __len__(self):
        return len(self.texts)

    def __getitem__(self, idx):
        enc = self.tokenizer(self.texts[idx], truncation=True, max_length=self.max_len)
        enc["labels"] = int(self.labels[idx])
        return enc


def load_data(extractor: EntityExtractor):
    train_df = pd.read_csv(cfg.TRAIN_CSV)
    test_df = pd.read_csv(cfg.HELDOUT_CSV)
    for df in (train_df, test_df):
        df["model_text"] = [extractor.prepare(t)[0] for t in df["text"]]
    return train_df, test_df


def train_model(model, loader, val_loader, optimizer, scheduler, device, epochs,
                id2label):
    history, best_f1, best_state = [], -1.0, None
    for epoch in range(epochs):
        model.train()
        total_loss, correct, seen = 0.0, 0, 0
        t0 = time.time()
        for batch in loader:
            batch = {k: v.to(device) for k, v in batch.items()}
            optimizer.zero_grad()
            out = model(**batch)
            out.loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            total_loss += out.loss.item() * batch["labels"].size(0)
            correct += (out.logits.argmax(-1) == batch["labels"]).sum().item()
            seen += batch["labels"].size(0)
        val = evaluate_model(model, val_loader, device, id2label)
        history.append({"epoch": epoch + 1, "train_loss": total_loss / seen,
                        "train_acc": correct / seen, "val_loss": val["loss"],
                        "val_acc": val["accuracy"], "val_macro_f1": val["macro_f1"]})
        print(f"Epoch {epoch + 1}/{epochs}  train_loss={total_loss / seen:.4f}  "
              f"train_acc={correct / seen:.4f}  val_loss={val['loss']:.4f}  "
              f"val_acc={val['accuracy']:.4f}  val_macroF1={val['macro_f1']:.4f}  "
              f"({time.time() - t0:.0f}s)")
        if val["macro_f1"] > best_f1:
            best_f1 = val["macro_f1"]
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)
    return history


@torch.no_grad()
def evaluate_model(model, loader, device, id2label):
    model.eval()
    preds, golds, confs, total_loss, n = [], [], [], 0.0, 0
    for batch in loader:
        batch = {k: v.to(device) for k, v in batch.items()}
        out = model(**batch)
        total_loss += out.loss.item() * batch["labels"].size(0)
        n += batch["labels"].size(0)
        p = torch.softmax(out.logits, -1)
        c, i = p.max(-1)
        preds += i.cpu().tolist()
        confs += c.cpu().tolist()
        golds += batch["labels"].cpu().tolist()
    return {"loss": total_loss / n, "accuracy": accuracy_score(golds, preds),
            "macro_f1": f1_score(golds, preds, average="macro"),
            "preds": preds, "golds": golds, "confs": confs}


def save_model(model, tokenizer, meta: dict):
    cfg.MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(cfg.MODEL_DIR)
    tokenizer.save_pretrained(cfg.MODEL_DIR)
    (cfg.MODEL_DIR / "training_meta.json").write_text(json.dumps(meta, indent=2))


def plot_history(history):
    h = pd.DataFrame(history)
    fig, ax = plt.subplots(1, 2, figsize=(10, 4))
    ax[0].plot(h.epoch, h.train_loss, marker="o", label="train loss")
    ax[0].plot(h.epoch, h.val_loss, marker="o", label="validation loss")
    ax[0].set_xlabel("Epoch"); ax[0].set_title("Loss"); ax[0].legend()
    ax[1].plot(h.epoch, h.train_acc, marker="o", label="train acc")
    ax[1].plot(h.epoch, h.val_macro_f1, marker="o", label="val macro-F1")
    ax[1].set_xlabel("Epoch"); ax[1].set_title("Akurasi / F1"); ax[1].legend()
    fig.tight_layout()
    fig.savefig(cfg.REPORT_DIR / "training_curve.png", dpi=150)


def plot_confusion(golds, preds, labels, path, title):
    cm = confusion_matrix(golds, preds, labels=list(range(len(labels))))
    fig, ax = plt.subplots(figsize=(11, 9))
    ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(labels)), labels, rotation=90, fontsize=7)
    ax.set_yticks(range(len(labels)), labels, fontsize=7)
    for i in range(len(labels)):
        for j in range(len(labels)):
            if cm[i, j]:
                ax.text(j, i, cm[i, j], ha="center", va="center", fontsize=6,
                        color="white" if cm[i, j] > cm.max() / 2 else "black")
    ax.set_xlabel("Prediksi"); ax.set_ylabel("Label benar"); ax.set_title(title)
    fig.tight_layout()
    fig.savefig(path, dpi=150)


def main():
    set_seed(cfg.SEED)
    cfg.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    device = pick_device()
    print(f"Device: {device} | base model: {cfg.BASE_MODEL_NAME}")

    extractor = EntityExtractor.from_resources()
    train_df, test_df = load_data(extractor)
    labels = sorted(train_df["intent"].unique())
    label2id = {l: i for i, l in enumerate(labels)}
    id2label = {i: l for l, i in label2id.items()}
    unknown = set(test_df.intent) - set(labels)
    if unknown:
        raise ValueError(f"Intent di test set tidak ada di train: {unknown}")

    tr, va = train_test_split(train_df, test_size=cfg.VAL_SIZE, random_state=cfg.SEED,
                              stratify=train_df["intent"])
    print(f"train={len(tr)}  val={len(va)}  heldout_test={len(test_df)}  "
          f"intents={len(labels)}")

    tokenizer = AutoTokenizer.from_pretrained(cfg.BASE_MODEL_NAME)
    collate = DataCollatorWithPadding(tokenizer)
    mk = lambda df: IntentDataset(df.model_text, df.intent.map(label2id), tokenizer,
                                  cfg.MAX_LEN)
    train_loader = DataLoader(mk(tr), batch_size=cfg.BATCH_SIZE, shuffle=True,
                              collate_fn=collate)
    val_loader = DataLoader(mk(va), batch_size=64, collate_fn=collate)
    test_loader = DataLoader(mk(test_df), batch_size=64, collate_fn=collate)

    model = AutoModelForSequenceClassification.from_pretrained(
        cfg.BASE_MODEL_NAME, num_labels=len(labels), id2label=id2label, label2id=label2id)
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg.LEARNING_RATE,
                                  weight_decay=0.01)
    steps = len(train_loader) * cfg.EPOCHS
    scheduler = get_linear_schedule_with_warmup(optimizer, int(cfg.WARMUP_RATIO * steps),
                                                steps)

    t0 = time.time()
    history = train_model(model, train_loader, val_loader, optimizer, scheduler, device,
                          cfg.EPOCHS, id2label)
    train_minutes = (time.time() - t0) / 60

    val = evaluate_model(model, val_loader, device, id2label)
    test = evaluate_model(model, test_loader, device, id2label)
    fallback_rate = float(np.mean(np.array(test["confs"]) < cfg.FALLBACK_THRESHOLD))
    rep_test = classification_report(test["golds"], test["preds"],
                                      labels=list(range(len(labels))), target_names=labels,
                                      digits=3, zero_division=0)
    rep_val = classification_report(val["golds"], val["preds"],
                                     labels=list(range(len(labels))), target_names=labels,
                                     digits=3, zero_division=0)
    print("\n=== Held-out test (kalimat ditulis terpisah, tidak dipakai training) ===")
    print(rep_test)
    print(f"Proporsi prediksi test di bawah ambang fallback {cfg.FALLBACK_THRESHOLD}: "
          f"{fallback_rate:.1%}")

    metrics = {
        "base_model": cfg.BASE_MODEL_NAME, "device": str(device),
        "train_size": len(tr), "val_size": len(va), "heldout_size": len(test_df),
        "epochs": cfg.EPOCHS, "max_len": cfg.MAX_LEN, "lr": cfg.LEARNING_RATE,
        "batch_size": cfg.BATCH_SIZE, "train_minutes": round(train_minutes, 2),
        "val_accuracy": round(val["accuracy"], 4), "val_macro_f1": round(val["macro_f1"], 4),
        "heldout_accuracy": round(test["accuracy"], 4),
        "heldout_macro_f1": round(test["macro_f1"], 4),
        "heldout_fallback_rate": round(fallback_rate, 4),
        "fallback_threshold": cfg.FALLBACK_THRESHOLD, "history": history,
        "transformers_version": __import__("transformers").__version__,
        "torch_version": torch.__version__,
    }
    save_model(model, tokenizer, {k: v for k, v in metrics.items() if k != "history"})
    (cfg.REPORT_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2))
    (cfg.REPORT_DIR / "classification_report_heldout.txt").write_text(rep_test)
    (cfg.REPORT_DIR / "classification_report_validation.txt").write_text(rep_val)
    wrong = test_df.assign(pred=[id2label[p] for p in test["preds"]],
                           confidence=np.round(test["confs"], 3))
    wrong[wrong.pred != wrong.intent].to_csv(cfg.REPORT_DIR / "heldout_errors.csv",
                                             index=False)
    plot_history(history)
    plot_confusion(test["golds"], test["preds"], labels,
                   cfg.REPORT_DIR / "confusion_matrix_heldout.png",
                   "Confusion matrix - held-out test")
    print(f"\nModel tersimpan di {cfg.MODEL_DIR}\nLaporan di {cfg.REPORT_DIR}")


if __name__ == "__main__":
    main()
