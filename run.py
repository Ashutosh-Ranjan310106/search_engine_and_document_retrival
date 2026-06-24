"""
run.py — Entry point for the compiled backend.exe
PyInstaller wraps this file. It starts uvicorn programmatically
so no subprocess / shell is needed.
"""
import sys
import os
import multiprocessing

# ── Fix: PyInstaller sets sys.frozen; tell libraries where to find data ───────
if getattr(sys, 'frozen', False):
    # The folder that contains backend.exe
    BASE_DIR = os.path.dirname(sys.executable)
    # Tell spacy / huggingface / docling where bundled data lives
    os.environ.setdefault('TRANSFORMERS_CACHE', os.path.join(BASE_DIR, 'hf_cache'))
    os.environ.setdefault('HF_HOME',            os.path.join(BASE_DIR, 'hf_cache'))
    os.environ.setdefault('TORCH_HOME',          os.path.join(BASE_DIR, 'torch_cache'))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Required for torch multiprocessing on Windows ─────────────────────────────
multiprocessing.freeze_support()

# ── Load .env from same folder as the exe ─────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, '.env'))

# ── Start uvicorn ─────────────────────────────────────────────────────────────
import uvicorn
from backend.knowledge_rag import app

if __name__ == "__main__":
    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        log_level="info",
    )