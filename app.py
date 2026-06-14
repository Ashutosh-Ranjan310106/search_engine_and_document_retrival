"""
DocRAG - Local Document Search & Summarization
Flask + LightRAG (HKUDS, editable install) + Docling + Ollama
  Indexing LLM  : qwen4b  (via Ollama)
  Answer LLM    : phi4-mini (via Ollama)
  Embedding     : nomic-embed-text (via Ollama)
  Entity extract: Docling pipeline
"""

import os
import asyncio
import logging
import threading
from pathlib import Path
from datetime import datetime

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from werkzeug.utils import secure_filename

from rag_engine import RAGEngine
# Persistent async loop
ASYNC_LOOP = asyncio.new_event_loop()

def _run_loop():
    asyncio.set_event_loop(ASYNC_LOOP)
    ASYNC_LOOP.run_forever()

threading.Thread(
    target=_run_loop,
    daemon=True
).start()
# ── patch event loop so async LightRAG works inside Flask ──────────────────────
Path("logs").mkdir(exist_ok=True)      # ← add this line
Path("uploads").mkdir(exist_ok=True)   # good to do this here too
Path("rag_storage").mkdir(exist_ok=True)
# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/app.log"),
    ],
)
log = logging.getLogger(__name__)
logging.getLogger("lightrag").setLevel(logging.INFO)
logging.getLogger("nano-vectordb").setLevel(logging.INFO)
# No extra handler needed — they'll inherit the root handler
# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-me-in-production")

UPLOAD_FOLDER = Path("uploads")
ALLOWED_EXT   = {".pdf", ".txt", ".md", ".docx", ".html"}
MAX_MB        = 50
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["MAX_CONTENT_LENGTH"] = MAX_MB * 1024 * 1024

# ── RAG engine (singleton, lazy init) ─────────────────────────────────────────
_rag_engine: RAGEngine | None = None
_rag_lock = threading.Lock()
_init_status = {"ready": False, "error": None, "progress": "Not started"}


def get_engine() -> RAGEngine:
    global _rag_engine
    if _rag_engine is None:
        raise RuntimeError("RAG engine not yet initialised")
    return _rag_engine
def run_async(coro):
    future = asyncio.run_coroutine_threadsafe(
        coro,
        ASYNC_LOOP
    )
    return future.result()

def _background_init():
    global _rag_engine
    _init_status["progress"] = "Initialising LightRAG + Ollama models…"
    try:
        engine = RAGEngine(storage_dir="rag_storage")
        future = asyncio.run_coroutine_threadsafe(
            engine.initialise(),
            ASYNC_LOOP
        )

        future.result()
        with _rag_lock:
            _rag_engine = engine
        _init_status["ready"] = True
        _init_status["progress"] = "Ready"
        log.info("RAG engine ready")
    except Exception as exc:
        _init_status["error"] = str(exc)
        _init_status["progress"] = f"Error: {exc}"
        log.exception("RAG engine init failed")


threading.Thread(target=_background_init, daemon=True).start()


# ── helpers ───────────────────────────────────────────────────────────────────
def allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXT


def _list_uploads():
    items = []
    for p in sorted(UPLOAD_FOLDER.iterdir()):
        if p.is_file():
            items.append({
                "name": p.name,
                "size_kb": round(p.stat().st_size / 1024, 1),
                "modified": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            })
    return items


# ── routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template(
        "index.html",
        uploads=_list_uploads(),
        status=_init_status,
    )


@app.route("/status")
def status():
    """Polled by the frontend to detect engine readiness."""
    return jsonify(_init_status)


@app.route("/upload", methods=["POST"])
def upload():
    if not _init_status["ready"]:
        return jsonify({"error": "Engine not ready yet. Please wait."}), 503

    if "files" not in request.files:
        return jsonify({"error": "No files provided"}), 400

    files = request.files.getlist("files")
    results = []

    for f in files:
        if f.filename == "":
            continue
        if not allowed_file(f.filename):
            results.append({"file": f.filename, "status": "rejected – unsupported type"})
            continue

        fname  = secure_filename(f.filename)
        fpath  = UPLOAD_FOLDER / fname
        f.save(str(fpath))

        try:
            engine = get_engine()
            msg = run_async(
                engine.ingest_file(fpath)
            )
            results.append({"file": fname, "status": "indexed", "detail": msg})
            log.info("Indexed: %s", fname)
        except Exception as exc:
            log.exception("Ingest failed for %s", fname)
            results.append({"file": fname, "status": "error", "detail": str(exc)})

    return jsonify({"results": results})


@app.route("/delete/<filename>", methods=["POST"])
def delete_file(filename: str):
    fpath = UPLOAD_FOLDER / secure_filename(filename)
    if fpath.exists():
        fpath.unlink()
        flash(f"Deleted {filename}", "info")
    return redirect(url_for("index"))


@app.route("/query", methods=["POST"])
def query():
    if not _init_status["ready"]:
        return jsonify({"error": "Engine not ready yet."}), 503

    data  = request.get_json(force=True)
    q     = (data.get("query") or "").strip()
    mode  = data.get("mode", "hybrid")          # local | global | hybrid | naive
    summarise = data.get("summarise", False)

    if not q:
        return jsonify({"error": "Empty query"}), 400

    try:
        engine = get_engine()
        answer = answer = run_async(engine.answer(q, mode=mode, summarise=summarise))
        return jsonify({"answer": answer, "mode": mode, "query": q})
    except Exception as exc:
        log.exception("Query failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/graph")
def graph():
    """Return the knowledge graph as JSON (nodes + edges)."""
    if not _init_status["ready"]:
        return jsonify({"error": "Not ready"}), 503
    try:
        engine = get_engine()
        data   = run_async(engine.export_graph())
        return jsonify(data)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@app.route("/citations")
def citations():
    """Return all chunk→page citations for the frontend."""
    if not _init_status["ready"]:
        return jsonify({"error": "Not ready"}), 503
    try:
        engine = get_engine()
        meta   = engine.load_all_chunk_meta()
        return jsonify({"citations": meta})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)
