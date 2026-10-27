"""Konfigurasi terpusat NLU service. Semua nilai bisa ditimpa lewat environment variable."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

# Model dasar. IndoBERT (BERT-base, dilatih pada korpus Indonesia Indo4B) dipilih karena
# chatbot berbahasa Indonesia. Alternatif DistilBERT: "distilbert-base-multilingual-cased".
BASE_MODEL_NAME = os.getenv("NLU_BASE_MODEL", "indobenchmark/indobert-base-p1")
MODEL_DIR = Path(os.getenv("NLU_MODEL_DIR", BASE_DIR / "models" / "olshop_intent_model"))
REPORT_DIR = Path(os.getenv("NLU_REPORT_DIR", BASE_DIR / "reports"))

TRAIN_CSV = Path(os.getenv("NLU_TRAIN_CSV", PROJECT_DIR / "datasets" / "nlu_train.csv"))
HELDOUT_CSV = Path(os.getenv("NLU_HELDOUT_CSV",
                             PROJECT_DIR / "datasets" / "nlu_test_heldout.csv"))

MAX_LEN = int(os.getenv("NLU_MAX_LEN", 64))          # kalimat chat pendek; 512 boros memori
EPOCHS = int(os.getenv("NLU_EPOCHS", 6))
BATCH_SIZE = int(os.getenv("NLU_BATCH_SIZE", 16))
LEARNING_RATE = float(os.getenv("NLU_LR", 3e-5))
WARMUP_RATIO = 0.1
VAL_SIZE = 0.15
SEED = 42

# Di bawah ambang ini intent diganti "nlu_fallback" (meniru FallbackClassifier Rasa,
# karena saat memakai NLU eksternal komponen pipeline Rasa tidak dijalankan).
FALLBACK_THRESHOLD = float(os.getenv("NLU_FALLBACK_THRESHOLD", 0.5))

HOST = os.getenv("NLU_HOST", "0.0.0.0")
PORT = int(os.getenv("NLU_PORT", 3000))
MAX_CHARS = 500   # sama dengan batas default user_input.max_characters Rasa (420) + margin
