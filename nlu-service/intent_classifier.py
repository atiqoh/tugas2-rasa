"""Pembungkus model intent hasil fine-tuning (dipakai oleh app.py)."""
from __future__ import annotations

import json
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


def pick_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return torch.device("mps")        # Apple Silicon (M1/M2/M3/M4)
    return torch.device("cpu")


class IntentClassifier:
    def __init__(self, model_dir: Path, max_len: int = 64, device: torch.device | None = None):
        model_dir = Path(model_dir)
        if not (model_dir / "config.json").exists():
            raise FileNotFoundError(
                f"Model tidak ditemukan di {model_dir}. Jalankan dulu: "
                f"python train_intent_model.py")
        self.device = device or pick_device()
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_dir)
        self.model.to(self.device).eval()
        self.max_len = max_len
        self.id2label = {int(k): v for k, v in self.model.config.id2label.items()}
        meta = model_dir / "training_meta.json"
        self.meta = json.loads(meta.read_text()) if meta.exists() else {}

    @property
    def labels(self) -> list[str]:
        return [self.id2label[i] for i in sorted(self.id2label)]

    @torch.no_grad()
    def predict(self, text: str, top_k: int = 5) -> list[tuple[str, float]]:
        enc = self.tokenizer(text, return_tensors="pt", truncation=True,
                             max_length=self.max_len)
        enc = {k: v.to(self.device) for k, v in enc.items()}
        probs = torch.softmax(self.model(**enc).logits, dim=-1)[0].cpu()
        k = min(top_k, probs.numel())
        conf, idx = torch.topk(probs, k)
        return [(self.id2label[int(i)], float(c)) for c, i in zip(conf, idx)]
