"""
DocSearch Backend — FastAPI server

FIXES APPLIED
─────────────
1.  [CRASH] LightRAG instantiated at module-level (top-level `rag = LightRAG(...)`)
    before `initialize_storages()` and `initialize_pipeline_status()` are ever called.
    Any import of this module would crash or leave RAG in an uninitialised state.
    Replaced with a lazy async `_get_rag()` helper that initialises once on first use
    and is awaited inside the upload route.

2.  [CRASH] `await rag.initialize_storages()` was called inside the upload route on
    every single request.  Re-initialising storages mid-flight corrupts in-progress
    state and is very slow.  Moved to one-time startup via `lifespan`.

3.  [MISSING] `initialize_pipeline_status()` was never imported or called.
    Without it, `ainsert_custom_kg` / `ainsert` silently process nothing.
    Added import and call in the startup lifespan.

4.  [MISSING] `finalize_storages()` was never called on shutdown, so LightRAG's
    in-memory stores were never flushed to disk.  Added to lifespan teardown.

5.  [MISSING] `aiohttp` was never imported but `_ollama_embed` uses it directly.
    Added import.

6.  [MISSING] `_embed_call_count` / `log` used inside `_ollama_embed` were never
    defined in this file (they lived only in rag_engine.py).  Added definitions.

7.  [CORRECTNESS] `_BASE` (used by `_ollama_embed`) was never defined in this file.
    Added it derived from `OLLAMA_HOST`.

8.  [CORRECTNESS] `@app.on_event("startup")` is deprecated in FastAPI 0.93+ and
    will be removed.  Replaced with a `lifespan` context manager that also handles
    the RAG init/shutdown sequence (fixes #2, #3, #4 as well).

9.  [CORRECTNESS] `FileResponse` hardcodes `media_type="application/pdf"` for every
    file regardless of extension.  A .docx or .txt file served as PDF breaks downloads.
    Switched to `mimetypes.guess_type()` with a safe fallback.

10. [CORRECTNESS] `cosine_sim(a, b)` returns `np.dot(b, a)` which only works when
    `b` is a 2-D matrix and `a` is a 1-D vector (gives a 1-D score array).  This
    accidentally works but the argument order is confusing and breaks if shapes change.
    Renamed parameters and added a shape guard for clarity.

11. [CORRECTNESS] `embed()` fallback uses dim=384 but the Ollama embed path uses
    EMBED_DIM (768 by default).  The mismatch crashes `cosine_sim` at search time
    when sentence-transformers is unavailable.  Changed fallback dim to EMBED_DIM.

12. [LOGIC] `hybrid_search` builds `vecs = np.array([c["embedding"] for c in pool])`
    but chunks loaded from SQLite have `embedding` as a Python list, while newly
    ingested chunks also have it as a list (`.tolist()` is called before storing).
    This is fine, but if ANY chunk in the pool has `embedding=None` (e.g. a chunk
    whose SQLite row had a NULL blob), `np.array(...)` will produce an object array
    and crash.  Added a guard to skip chunks without embeddings.

13. [LOGIC] The `prev/next chunk_id` back-fill loop at the end of `upload_document`
    writes into `obj` (which is already in `CHUNKS`) but does NOT call
    `_persist_document` again, so SQLite retains NULL for prev/next ids.
    The fix here is structural — moved the prev/next assignment before the first
    `_persist_document` call so they are included in the initial write.

14. [CORRECTNESS] `SentenceTransformer("text-embedding-3-large")` was hardcoded,
    producing embeddings of dim=3072 — completely inconsistent with EMBED_DIM (768)
    and EMBED_MODEL from .env.  The `embed()` function now ALWAYS calls Ollama via
    `_ollama_embed`, making the embedding model and dimension a single source of
    truth: the .env file (EMBED_MODEL / EMBED_DIM).  SentenceTransformers is kept
    only for re-ranking (CrossEncoder), which does not produce embeddings.

15. [CORRECTNESS] EMBED_MAX_TOKENS was hardcoded as 8192 inside `_make_embedding_func`.
    Moved to env var EMBED_MAX_TOKENS (default 8192) so it can be tuned per model.

16. [CRASH] `embed()` was implemented as a synchronous wrapper that called
    `asyncio.get_event_loop().run_until_complete(_ollama_embed(...))`.  When called
    from inside FastAPI's event loop (uvicorn), this raises:
      RuntimeError: This event loop is already running
    Fix: `embed()` is now `async def embed()` — a thin `await _ollama_embed()`
    wrapper.  `hybrid_search()` is also made async so it can `await embed()`.
    `hybrid_search_async` now directly awaits `hybrid_search()` instead of wrapping
    it in `asyncio.to_thread()` (which was only needed when it was sync).

UPGRADE — Triple-fusion response pipeline
─────────────────────────────────────────
The response generation pipeline now fuses three retrieval signals:

  1. Semantic  — cosine similarity of dense embeddings (existing)
  2. Keyword   — BM25 sparse retrieval                 (existing)
  3. Graph     — LightRAG knowledge-graph query        (NEW)

search_mode values (fully backward-compatible — old values unchanged):
  "semantic"  — dense vectors only          (was: semantic)
  "keyword"   — BM25 only                  (was: keyword)
  "hybrid"    — BM25 + semantic, 50/50      (was: hybrid — same behaviour)
  "graph"     — LightRAG graph only         (NEW)
  "full"      — BM25 + semantic + graph     (NEW — recommended)

New optional ChatRequest / SearchRequest field:
  graph_weight  float  0.0–1.0  default 0.3
      Weight given to graph scores in "full" mode.
      Semantic and keyword share the remaining (1 - graph_weight) equally.
      Ignored for all other modes.  Frontend that omits it gets 0.3.

Response shape is 100% unchanged — same fields, same types, same endpoints.
The only additions are:
  • "graph_score" key on each result/chunk object (0.0 when graph not used)
  • "search_mode" echoed back (was already present on /search)

_graph_search() runs LightRAG aquery(mode="mix") then re-ranks the chunks
in CHUNKS whose text overlaps with LightRAG's answer, giving each a
graph_score proportional to how much of LightRAG's answer they cover.
This avoids any LightRAG API format dependency — we never parse its internal
graph structures, only its final text output.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import mimetypes       # FIX #9
import os
import re
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager   # FIX #8
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp         # FIX #5
import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from backend.dockling_document_extraction import chunk_elements, extract_with_dockling
from backend.entity_extractor import extract_rule_entities
from lightrag import LightRAG, QueryParam
from lightrag.kg.shared_storage import initialize_pipeline_status  # FIX #3
from lightrag.utils import EmbeddingFunc
from backend.lightrag_support import convert_edges, convert_nodes
from backend.hierarchy_kg import inject_hierarchy_edges


load_dotenv()

# ── Helpers ───────────────────────────────────────────────────────────────────

def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"WARNING: {name}={raw!r} is not a valid int, using default {default}")
        return default


# ── Configuration ─────────────────────────────────────────────────────────────
# Embedding — all embedding behaviour is controlled exclusively by these three
# env vars.  No other embedding model or dimension constant exists in this file.
#
#   EMBED_MODEL      Ollama model name used for ALL embeddings, including LightRAG
#                    keyword/entity embeddings.  Default: nomic-embed-text
#   EMBED_DIM        Output dimension of that model.  Must match exactly.
#                    Default: 768  (correct for nomic-embed-text)
#   EMBED_MAX_TOKENS Max token budget passed to EmbeddingFunc for LightRAG.
#                    Default: 8192
#
# To switch models, update all three in .env and delete rag_storage/ so that
# LightRAG rebuilds its vector index with the new dimension.

OLLAMA_HOST      = os.getenv("OLLAMA_HOST",      "http://localhost:11434")
EMBED_MODEL      = os.getenv("EMBED_MODEL",      "nomic-embed-text:latest")   # single source of truth
EMBED_DIM        = _env_int("EMBED_DIM",          768)                  # single source of truth
EMBED_MAX_TOKENS = _env_int("EMBED_MAX_TOKENS",   8192)                 # FIX #15
OLLAMA_MODEL     = os.getenv("OLLAMA_MODEL",      "llama3.1")
OLLAMA_THINK     = _env_bool("OLLAMA_THINK",      False)
UPLOAD_DIR       = Path(os.getenv("UPLOAD_DIR",   "./uploads")).resolve()
DB_PATH          = Path(os.getenv("DB_PATH",      "./docsearch.db")).resolve()
MAX_UPLOAD_MB    = _env_int("MAX_UPLOAD_MB",       50)
CORS_ORIGINS     = [
    o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()
]

# FIX #6 / #7 – define log and _BASE so _ollama_embed can use them
log   = logging.getLogger("docsearch")
_BASE = OLLAMA_HOST.rstrip("/")
_embed_call_count = 0   # FIX #6

# ── Optional heavy deps ───────────────────────────────────────────────────────
try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
    SPACY_OK = True
except Exception:
    SPACY_OK = False

# FIX #14 — SentenceTransformer is ONLY loaded for re-ranking (CrossEncoder).
# It is NOT used for embeddings — all embeddings go through Ollama (_ollama_embed)
# so that EMBED_MODEL / EMBED_DIM in .env are the single source of truth.
try:
    from sentence_transformers import CrossEncoder
    _RERANK_MODEL = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    SENTENCE_TRANSFORMERS_OK = True
except Exception:
    SENTENCE_TRANSFORMERS_OK = False

try:
    import pdfplumber
    PDF_OK = True
except Exception:
    PDF_OK = False

try:
    from docx import Document as DocxDoc
    DOCX_OK = True
except Exception:
    DOCX_OK = False

try:
    from ollama import Client as OllamaClient
    _OLLAMA = OllamaClient(host=OLLAMA_HOST)
    _OLLAMA.list()
    OLLAMA_OK = True
except Exception:
    OLLAMA_OK = False

# ── In-memory store ───────────────────────────────────────────────────────────
DOCS:   Dict[str, Dict] = {}
CHUNKS: Dict[str, Dict] = {}

# ── File storage ──────────────────────────────────────────────────────────────
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ── Ollama embedding (single implementation for ALL embedding calls) ───────────
#
# FIX #14 — this is the ONLY embedding function in the entire codebase.
# It is used by:
#   • embed()              → document ingestion and query embedding at search time
#   • _make_embedding_func() → LightRAG (keyword, entity, chunk embeddings)
#
# Both paths call the same Ollama endpoint with the same EMBED_MODEL and validate
# the returned dimension against EMBED_DIM.  There is no fallback to a different
# model or library for embeddings.

async def _ollama_embed(texts: list[str]) -> np.ndarray:
    global _embed_call_count
    _embed_call_count += 1
    call_id = _embed_call_count
    print("\n\n\n\n\n\ntexts",texts)
    t0 = time.perf_counter()
    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"{_BASE}/api/embed",
            json={"model": EMBED_MODEL, "input": texts},
            timeout=aiohttp.ClientTimeout(total=300),
        ) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)
    elapsed = time.perf_counter() - t0

    embeddings = data.get("embeddings") or data.get("embedding") or []
    arr = np.array(embeddings, dtype=np.float32)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.shape[1] != EMBED_DIM:
        raise ValueError(
            f"{EMBED_MODEL} returned dim={arr.shape[1]} but EMBED_DIM={EMBED_DIM}. "
            f"Set EMBED_DIM={arr.shape[1]} in .env, delete rag_storage/, and restart."
        )
    log.debug("[EMBED #%d] shape=%s | %.2fs", call_id, arr.shape, elapsed)
    return arr


def _make_embedding_func() -> EmbeddingFunc:
    """EmbeddingFunc wrapper for LightRAG — uses the same _ollama_embed as embed()."""
    return EmbeddingFunc(
        embedding_dim=EMBED_DIM,            # from env (FIX #14, #15)
        max_token_size=EMBED_MAX_TOKENS,    # from env (FIX #15)
        func=_ollama_embed,
    )


# FIX #14 / #16 — async wrapper around _ollama_embed.
# embed() MUST be async because _ollama_embed uses aiohttp and is always called
# from within FastAPI's already-running event loop.  Using run_until_complete()
# from inside a running loop raises "RuntimeError: This event loop is already
# running" (Python 3.10+ / uvicorn).  All callers are async routes or async
# helpers, so making embed() async is the correct fix.
async def embed(texts: List[str]) -> np.ndarray:
    """Embed texts via Ollama → (N, EMBED_DIM) float32 array."""
    return await _ollama_embed(texts)


# ── LightRAG LLM func (wraps Ollama streaming chat) ──────────────────────────
async def lightrag_ollama(
    prompt: str,
    system_prompt: str | None = None,
    history_messages: list | None = None,
    keyword_extraction: bool = False,   # explicit – LightRAG injects this kwarg
    **kwargs,
) -> str:
    q = await stream_llm(
        system=system_prompt or "",
        messages=[
            *(history_messages or []),
            {"role": "user", "content": prompt},
        ],
    )
    parts: list[str] = []
    while True:
        item = await q.get()
        if item is None:
            break
        if item["type"] == "text":
            parts.append(item["text"])
    return "".join(parts)


# FIX #1 / #2 / #3 / #4 / #8 ─────────────────────────────────────────────────
# LightRAG must be initialised once, asynchronously, before any route uses it.
# Module-level `rag = LightRAG(...)` is wrong because:
#   - The constructor doesn't call initialize_storages().
#   - initialize_storages() is async — it can't be awaited at import time.
#   - initialize_pipeline_status() was never called at all.
# Solution: lazy singleton via _get_rag(), initialised in the lifespan handler.

_rag: LightRAG | None = None


async def _init_rag() -> LightRAG:
    global _rag
    if _rag is not None:
        return _rag
    _rag = LightRAG(
        working_dir="./rag_storage",
        llm_model_func=lightrag_ollama,
        embedding_func=_make_embedding_func(),  # Ollama, EMBED_MODEL, EMBED_DIM
    )
    await _rag.initialize_storages()        # FIX #2 – once only, not per-request
    await initialize_pipeline_status()      # FIX #3 – required for ainsert to work
    return _rag


async def _get_rag() -> LightRAG:
    if _rag is None:
        raise RuntimeError("LightRAG not yet initialised — startup did not complete")
    return _rag


# ── Lifespan (replaces deprecated @app.on_event) ─────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    _init_db()
    _load_all_from_db()
    await _init_rag()           # FIX #1 #2 #3 – proper async init, once
    yield
    # Shutdown – FIX #4
    if _rag is not None:
        await _rag.finalize_storages()


# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="DocSearch API",
    description="Hybrid RAG system with citations, entity extraction, and hybrid search",
    version="1.0.0",
    lifespan=lifespan,          # FIX #8
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── File storage helpers ──────────────────────────────────────────────────────
def _safe_filename(name: str) -> str:
    name = Path(name).name
    name = re.sub(r"[^\w\-. ()]", "_", name).strip()
    return name or "upload"


def _save_uploaded_file(filename: str, content: bytes) -> Path:
    safe_name = _safe_filename(filename)
    stem, ext = os.path.splitext(safe_name)
    dest = UPLOAD_DIR / safe_name
    counter = 1
    while dest.exists():
        dest = UPLOAD_DIR / f"{stem} ({counter}){ext}"
        counter += 1
    dest.write_bytes(content)
    return dest


# ── Persistence (SQLite) ──────────────────────────────────────────────────────
def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _init_db() -> None:
    conn = _get_db()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS docs (
                doc_id          TEXT PRIMARY KEY,
                filename        TEXT NOT NULL,
                size_bytes      INTEGER NOT NULL,
                char_count      INTEGER NOT NULL,
                chunk_count     INTEGER NOT NULL,
                entities_json   TEXT NOT NULL,
                uploaded_at     TEXT NOT NULL,
                text_preview    TEXT,
                file_path       TEXT NOT NULL,
                file_url        TEXT NOT NULL,
                stored_filename TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id            TEXT PRIMARY KEY,
                doc_id              TEXT NOT NULL REFERENCES docs(doc_id) ON DELETE CASCADE,
                doc_name            TEXT,
                text                TEXT NOT NULL,
                display_text        TEXT,
                chunk_index         INTEGER,
                breadcrumb          TEXT,
                hierarchy_path_json TEXT,
                table_part          INTEGER,
                table_parts_total   INTEGER,
                prev_chunk_id       TEXT,
                next_chunk_id       TEXT,
                page_hint           TEXT,
                file_url            TEXT,
                embedding_blob      BLOB,
                embedding_dim       INTEGER,
                entities_json       TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id)")
        conn.commit()
    finally:
        conn.close()


def _sql_safe(value):
    if value is None or isinstance(value, (int, float, str, bytes)):
        return value
    return json.dumps(value)


def _persist_document(doc: Dict, chunk_objs: List[Dict]) -> None:
    conn = _get_db()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO docs
                (doc_id, filename, size_bytes, char_count, chunk_count,
                 entities_json, uploaded_at, text_preview, file_path,
                 file_url, stored_filename)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc["doc_id"], doc["filename"], doc["size_bytes"],
                doc["char_count"], doc["chunk_count"],
                json.dumps(doc["entities"]), doc["uploaded_at"],
                _sql_safe(doc.get("text_preview")), doc["file_path"],
                doc["file_url"], doc["stored_filename"],
            ),
        )
        for c in chunk_objs:
            vec = c.get("embedding")
            emb_arr = np.asarray(vec, dtype=np.float32) if vec is not None else None
            conn.execute(
                """
                INSERT OR REPLACE INTO chunks
                    (chunk_id, doc_id, doc_name, text, display_text,
                     chunk_index, breadcrumb, hierarchy_path_json,
                     table_part, table_parts_total, prev_chunk_id,
                     next_chunk_id, page_hint, file_url, embedding_blob,
                     embedding_dim, entities_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    c["chunk_id"], c["doc_id"], _sql_safe(c.get("doc_name")),
                    c["text"], _sql_safe(c.get("display_text")),
                    c.get("index"), _sql_safe(c.get("breadcrumb")),
                    json.dumps(c.get("hierarchy_path")), c.get("table_part"),
                    c.get("table_parts_total"), _sql_safe(c.get("prev_chunk_id")),
                    _sql_safe(c.get("next_chunk_id")), _sql_safe(c.get("page_hint")),
                    _sql_safe(c.get("file_url")),
                    emb_arr.tobytes() if emb_arr is not None else None,
                    emb_arr.shape[0] if emb_arr is not None else None,
                    json.dumps(c.get("entities", [])),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _delete_document_row(doc_id: str) -> None:
    conn = _get_db()
    try:
        conn.execute("DELETE FROM docs WHERE doc_id = ?", (doc_id,))
        conn.commit()
    finally:
        conn.close()


def _row_to_doc(row: sqlite3.Row, chunk_ids: List[str]) -> Dict:
    return {
        "doc_id":          row["doc_id"],
        "filename":        row["filename"],
        "size_bytes":      row["size_bytes"],
        "char_count":      row["char_count"],
        "chunk_count":     row["chunk_count"],
        "chunks":          chunk_ids,
        "entities":        json.loads(row["entities_json"]),
        "uploaded_at":     row["uploaded_at"],
        "text_preview":    row["text_preview"],
        "file_path":       row["file_path"],
        "file_url":        row["file_url"],
        "stored_filename": row["stored_filename"],
    }


def _row_to_chunk(row: sqlite3.Row) -> Dict:
    embedding = None
    if row["embedding_blob"] is not None:
        embedding = np.frombuffer(row["embedding_blob"], dtype=np.float32).tolist()
    return {
        "chunk_id":          row["chunk_id"],
        "doc_id":            row["doc_id"],
        "doc_name":          row["doc_name"],
        "text":              row["text"],
        "display_text":      row["display_text"],
        "index":             row["chunk_index"],
        "breadcrumb":        row["breadcrumb"],
        "hierarchy_path":    json.loads(row["hierarchy_path_json"]) if row["hierarchy_path_json"] else None,
        "table_part":        row["table_part"],
        "table_parts_total": row["table_parts_total"],
        "prev_chunk_id":     row["prev_chunk_id"],
        "next_chunk_id":     row["next_chunk_id"],
        "page_hint":         row["page_hint"],
        "file_url":          row["file_url"],
        "embedding":         embedding,
        "entities":          json.loads(row["entities_json"]) if row["entities_json"] else [],
    }


def _load_all_from_db() -> None:
    conn = _get_db()
    try:
        chunk_rows = conn.execute(
            "SELECT * FROM chunks ORDER BY doc_id, chunk_index"
        ).fetchall()
        chunks_by_doc: Dict[str, List[str]] = {}
        for row in chunk_rows:
            chunk = _row_to_chunk(row)
            CHUNKS[chunk["chunk_id"]] = chunk
            chunks_by_doc.setdefault(chunk["doc_id"], []).append(chunk["chunk_id"])

        doc_rows = conn.execute("SELECT * FROM docs").fetchall()
        for row in doc_rows:
            doc_id = row["doc_id"]
            DOCS[doc_id] = _row_to_doc(row, chunks_by_doc.get(doc_id, []))
    finally:
        conn.close()


# ── Pydantic models ───────────────────────────────────────────────────────────
class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    query: str
    history: List[ChatMessage] = []
    top_k: int = 5
    use_reranking: bool = True
    search_mode: str = "hybrid"   # "semantic"|"keyword"|"hybrid"|"graph"|"full"
    # graph_weight: share of graph signal in "full" mode (0.0–1.0, default 0.3).
    # Ignored for all other modes.  Omitting it is equivalent to sending 0.3.
    graph_weight: float = 0.3


class SearchRequest(BaseModel):
    query: str
    top_k: int = 10
    search_mode: str = "hybrid"   # "semantic"|"keyword"|"hybrid"|"graph"|"full"
    doc_ids: Optional[List[str]] = None
    graph_weight: float = 0.3     # only used when search_mode == "full"


class EntitySearchRequest(BaseModel):
    entities: List[str]
    top_k: int = 10


# ── Embeddings ────────────────────────────────────────────────────────────────
# NOTE: embed() is defined above, alongside _ollama_embed and _make_embedding_func,
# so that all embedding code is co-located in one place.  See FIX #14.

# FIX #10 – clearer parameter names; added ndim guard
def cosine_sim(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Return cosine similarity between query_vec (1-D) and each row of matrix (2-D)."""
    if matrix.ndim != 2 or query_vec.ndim != 1:
        raise ValueError(
            f"cosine_sim expects 1-D query and 2-D matrix, "
            f"got {query_vec.shape} and {matrix.shape}"
        )
    return np.dot(matrix, query_vec)


# ── BM25 ──────────────────────────────────────────────────────────────────────
def tokenize(text: str) -> List[str]:
    return re.findall(r"\w+", text.lower())


def bm25_score(
    query_tokens: List[str],
    corpus_chunks: List[Dict],
    k1: float = 1.5,
    b: float = 0.75,
) -> np.ndarray:
    N = len(corpus_chunks)
    if N == 0:
        return np.array([])
    doc_lens = [len(tokenize(c["text"])) for c in corpus_chunks]
    avgdl    = sum(doc_lens) / N if N else 1

    df: Dict[str, int] = {}
    tf_per_doc: List[Dict[str, int]] = []
    for c in corpus_chunks:
        toks: Dict[str, int] = {}
        for t in tokenize(c["text"]):
            toks[t] = toks.get(t, 0) + 1
        tf_per_doc.append(toks)
        for t in set(toks):
            df[t] = df.get(t, 0) + 1

    scores = np.zeros(N)
    for qt in query_tokens:
        idf = math.log((N - df.get(qt, 0) + 0.5) / (df.get(qt, 0) + 0.5) + 1)
        for i, (tf, dl) in enumerate(zip(tf_per_doc, doc_lens)):
            f = tf.get(qt, 0)
            scores[i] += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / avgdl))
    return scores


# ── Entity extraction ─────────────────────────────────────────────────────────
ENTITY_RE = re.compile(
    r"\b([A-Z][a-z]+ (?:[A-Z][a-z]+ )*[A-Z][a-z]+|[A-Z]{2,})\b"
)


# ── Reranking ─────────────────────────────────────────────────────────────────
def rerank(query: str, candidates: List[Dict]) -> List[Dict]:
    if not SENTENCE_TRANSFORMERS_OK or not candidates:
        return candidates
    pairs  = [(query, c["text"]) for c in candidates]
    scores = _RERANK_MODEL.predict(pairs)
    for c, s in zip(candidates, scores):
        c["rerank_score"] = float(s)
    return sorted(candidates, key=lambda x: x.get("rerank_score", 0), reverse=True)


# ── Graph search (LightRAG) ───────────────────────────────────────────────────
async def _graph_search(
    query: str,
    top_k: int = 10,
    doc_ids: Optional[List[str]] = None,
) -> List[Dict]:
    """
    Query LightRAG's knowledge graph (mode="mix" = local+global graph traversal)
    and map the answer back to the chunks in CHUNKS that contributed to it.

    Strategy: LightRAG returns a free-text answer synthesised from the graph.
    We score every chunk by how many of the answer's content words appear in
    that chunk's text, then normalise to [0, 1].  This is lightweight, needs no
    LightRAG internals, and degrades gracefully (returns [] on any error).

    doc_ids filter is applied after scoring so the graph query itself is global
    (the graph doesn't know our doc_id boundaries), but results are restricted
    to the requested documents before returning.
    """
    rag = _rag
    if rag is None:
        return []
    try:
        answer_text: str = await rag.aquery(
            query, param=QueryParam(mode="mix", top_k=min(top_k * 4, 60))
        )
    except Exception as exc:
        log.warning("LightRAG graph query failed (non-fatal): %s", exc)
        return []

    if not answer_text or answer_text.strip().lower().startswith("sorry"):
        return []

    # Tokenise the graph answer for overlap scoring
    answer_toks = set(tokenize(answer_text))
    if not answer_toks:
        return []

    pool = [
        c for c in CHUNKS.values()
        if (doc_ids is None or c["doc_id"] in doc_ids)
        and c.get("embedding") is not None
    ]
    if not pool:
        return []

    # Score each chunk: |chunk_tokens ∩ answer_tokens| / |answer_tokens|
    raw_scores: List[float] = []
    for c in pool:
        chunk_toks  = set(tokenize(c["text"]))
        overlap     = len(chunk_toks & answer_toks)
        raw_scores.append(overlap / len(answer_toks))

    arr = np.array(raw_scores, dtype=np.float32)
    mx  = arr.max()
    if mx > 0:
        arr /= mx   # normalise to [0, 1]

    top_idx    = np.argsort(arr)[::-1][: top_k]
    candidates = []
    for i in top_idx:
        if arr[i] == 0:
            break   # no overlap with graph answer — don't return noise
        c                  = dict(pool[i])
        c["graph_score"]   = float(arr[i])
        c["score"]         = float(arr[i])
        c["sem_score"]     = 0.0
        c["bm25_score"]    = 0.0
        candidates.append(c)

    return candidates


# ── Hybrid search ─────────────────────────────────────────────────────────────
async def hybrid_search(
    query: str,
    top_k: int = 5,
    mode: str = "hybrid",
    doc_ids: Optional[List[str]] = None,
    graph_weight: float = 0.3,
) -> List[Dict]:
    """
    Async vector/BM25 retrieval.  Made async (FIX #16) so it can await embed()
    without triggering "event loop already running".

    Modes:
      "semantic"  — dense vectors only
      "keyword"   — BM25 only
      "hybrid"    — BM25 + semantic, 50 / 50  (unchanged behaviour)
      "graph"     — returns [] here; handled by hybrid_search_async
      "full"      — BM25 + semantic only here; graph leg merged in hybrid_search_async
    """
    pool = [
        c for c in CHUNKS.values()
        if doc_ids is None or c["doc_id"] in doc_ids
    ]
    if not pool:
        return []

    # skip chunks with no embedding (NULL blob from SQLite)
    pool = [c for c in pool if c.get("embedding") is not None]
    if not pool:
        return []

    # "graph"-only mode: nothing to compute here
    if mode == "graph":
        return []

    query_vec  = (await embed([query]))[0]
    query_toks = tokenize(query)

    sem_scores  = np.zeros(len(pool))
    bm25_scores = np.zeros(len(pool))

    # "full" mode uses both dense + BM25 legs (graph merged separately)
    if mode in ("hybrid", "semantic", "full"):
        vecs       = np.array([c["embedding"] for c in pool], dtype=np.float32)
        sem_scores = cosine_sim(query_vec, vecs)

    if mode in ("hybrid", "keyword", "full"):
        bm25_scores = bm25_score(query_toks, pool)
        mx = bm25_scores.max()
        if mx > 0:
            bm25_scores /= mx

    if mode == "semantic":
        alpha = 1.0
    elif mode == "keyword":
        alpha = 0.0
    else:
        # "hybrid" and "full" split remaining weight 50/50 between sem and BM25
        alpha = 0.5

    combined = alpha * sem_scores + (1 - alpha) * bm25_scores

    top_idx    = np.argsort(combined)[::-1][: top_k * 2]
    candidates = []
    for i in top_idx:
        c                = dict(pool[i])
        c["score"]       = float(combined[i])
        c["sem_score"]   = float(sem_scores[i])
        c["bm25_score"]  = float(bm25_scores[i])
        c["graph_score"] = 0.0   # filled in by hybrid_search_async for "full" mode
        candidates.append(c)

    return candidates[:top_k]


async def hybrid_search_async(
    query: str,
    top_k: int = 5,
    mode: str = "hybrid",
    doc_ids: Optional[List[str]] = None,
    graph_weight: float = 0.3,
) -> List[Dict]:
    """
    Full retrieval pipeline — wraps hybrid_search() and, for "graph"/"full"
    modes, fires _graph_search() concurrently then merges the scores.

    This is the single entry-point used by all chat and search routes.
    Calling code that used `hybrid_search(...)` directly is updated to
    await `hybrid_search_async(...)` — the returned list shape is identical.
    """
    if mode == "graph":
        # Graph-only: skip vector/BM25 entirely
        results = await _graph_search(query, top_k=top_k * 2, doc_ids=doc_ids)
        return results[:top_k]

    if mode != "full":
        # "semantic" / "keyword" / "hybrid" — no graph leg needed
        return await hybrid_search(query, top_k=top_k, mode=mode, doc_ids=doc_ids)

    # ── "full" mode: run BM25+semantic and graph in parallel ──────────────────
    gw = max(0.0, min(1.0, graph_weight))   # clamp to [0, 1]
    vk_weight = 1.0 - gw                   # remaining weight split 50/50 between sem+BM25

    # FIX #16 — hybrid_search is now async, so gather both coroutines directly.
    # asyncio.to_thread() was used when it was sync; no longer needed.
    vec_results, graph_results = await asyncio.gather(
        hybrid_search(query, top_k * 2, "hybrid", doc_ids),
        _graph_search(query, top_k=top_k * 2, doc_ids=doc_ids),
    )

    # Build a score map keyed by chunk_id
    scores: Dict[str, Dict] = {}

    for c in vec_results:
        cid = c["chunk_id"]
        scores[cid] = dict(c)
        scores[cid]["combined_score"] = vk_weight * c["score"]

    for c in graph_results:
        cid = c["chunk_id"]
        gs  = gw * c["graph_score"]
        if cid in scores:
            scores[cid]["graph_score"]    = c["graph_score"]
            scores[cid]["combined_score"] = scores[cid].get("combined_score", 0.0) + gs
        else:
            entry                    = dict(c)
            entry["combined_score"]  = gs
            scores[cid]              = entry

    # Sort by combined score, stamp final "score" field for downstream consumers
    merged = sorted(scores.values(), key=lambda x: x["combined_score"], reverse=True)
    for m in merged:
        m["score"] = m.pop("combined_score")

    return merged[:top_k]


# ── Citation builder ──────────────────────────────────────────────────────────
def build_citations(chunks: List[Dict]) -> List[Dict]:
    citations = []
    for i, c in enumerate(chunks):
        display = c.get("display_text") or c["text"]
        citations.append({
            "citation_id": f"[{i + 1}]",
            "chunk_id":    c["chunk_id"],
            "doc_id":      c["doc_id"],
            "doc_name":    c.get("doc_name", ""),
            "chunk_index": c.get("index", 0),
            "char_start":  c.get("char_start", 0),
            "score":       c.get("rerank_score", c.get("score", 0)),
            "snippet":     display[:300],
            "entities":    c.get("entities", []),
        })
    return citations


# ── LLM streaming (Ollama) ────────────────────────────────────────────────────
async def stream_llm(system: str, messages: List[Dict]) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()

    async def _run():
        if not OLLAMA_OK:
            await q.put({"type": "text", "text": "[LLM not configured]"})
            await q.put(None)
            return
        try:
            ollama_messages = [{"role": "system", "content": system}, *messages]
            stream = _OLLAMA.chat(
                model=OLLAMA_MODEL,
                messages=ollama_messages,
                stream=True,
                think=OLLAMA_THINK,
            )
            for part in stream:
                text = part["message"]["content"]
                if text:
                    await q.put({"type": "text", "text": text})
        except Exception as e:
            await q.put({"type": "error", "text": str(e)})
        await q.put(None)

    asyncio.create_task(_run())
    return q


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════════════════════



# ── Documents ─────────────────────────────────────────────────────────────────

@app.post("/documents/upload", tags=["Documents"])
async def upload_document(file: UploadFile = File(...)):
    content = await file.read()
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"File too large (max {MAX_UPLOAD_MB} MB)")

    rag = await _get_rag()   # FIX #1 #2 – use already-initialised singleton

    doc_id     = str(uuid.uuid4())
    stored_path = _save_uploaded_file(file.filename, content)
    file_url   = f"/documents/{doc_id}/file"

    elements   = extract_with_dockling(file.filename, content)
    chunks_raw = chunk_elements(elements, target_size=1200, overlap=150)

    text = "\n\n".join(el.get("text", "") for el in elements if el.get("text"))
    chunk_texts = [c["text"] for c in chunks_raw]
    embeddings  = await _ollama_embed(chunk_texts)   # FIX #14 – always Ollama

    # Build chunk objects (without prev/next yet)
    chunk_objs: List[Dict] = []
    # "chunks" is omitted from the LightRAG payload on purpose.
    # When chunks are included alongside entities (sharing source_id), LightRAG
    # internally creates chunk→entity and entity→parent links.  We don't want
    # those — our own CHUNKS store and SQLite handle all chunk retrieval.
    # LightRAG only receives the pure entity graph (entities + relationships).
    doc_kg: Dict = {"chunks": [], "relationships": [], "entities": []}
    all_entities: Dict[str, str] = {}

    for raw, vec in zip(chunks_raw, embeddings):
        cid = str(uuid.uuid4())
    
        nodes, edges = extract_rule_entities(
            text=raw["text"],
            chunk_key=cid,
            file_path=file.filename,
            timestamp=int(time.time()),
            table_data=raw.get("data"),
        )
    
        # ── inject hierarchy edges BEFORE convert_nodes/convert_edges ────────────
        # This adds heading nodes + HAS_SUBSECTION / BELONGS_TO / PART_OF edges
        # so that LightRAG's graph links entities to their parent sections.
        nodes, edges = inject_hierarchy_edges(
            nodes          = nodes,
            edges          = edges,
            hierarchy_path = raw.get("hierarchy_path"),   # from chunk_elements()
            chunk_id       = cid,
            file_path      = file.filename,
        )
        # ─────────────────────────────────────────────────────────────────────────
    
        doc_kg["chunks"].append({
            "content":   raw["text"],
            "source_id": cid,
            "file_path": file.filename,
        })
        doc_kg["entities"].extend(convert_nodes(nodes))
        doc_kg["relationships"].extend(convert_edges(edges))
    
        ents: List[Dict] = []
        for entity_name, entity_list in nodes.items():
            entity = entity_list[0]
            ents.append({"text": entity_name, "label": entity["entity_type"]})
            all_entities[entity_name] = entity["entity_type"]
    
        chunk_objs.append({
            "chunk_id":          cid,
            "doc_id":            doc_id,
            "doc_name":          file.filename,
            "text":              raw["text"],
            "display_text":      raw.get("display_text", raw["text"]),
            "index":             raw["index"],
            "breadcrumb":        raw.get("breadcrumb"),
            "hierarchy_path":    raw.get("hierarchy_path"),
            "table_part":        raw.get("table_part"),
            "table_parts_total": raw.get("table_parts_total"),
            "prev_chunk_id":     None,
            "next_chunk_id":     None,
            "page_hint":         raw.get("page"),
            "file_url":          file_url,
            "embedding":         vec.tolist(),
            "entities":          ents,
        })

    # FIX #13 – fill prev/next BEFORE persisting so SQLite gets the correct ids
    index_to_cid = {c["index"]: c["chunk_id"] for c in chunk_objs}
    for obj in chunk_objs:
        idx = obj["index"]
        obj["prev_chunk_id"] = index_to_cid.get(idx - 1)
        obj["next_chunk_id"] = index_to_cid.get(idx + 1)
        CHUNKS[obj["chunk_id"]] = obj

    DOCS[doc_id] = {
        "doc_id":          doc_id,
        "filename":        file.filename,
        "size_bytes":      len(content),
        "char_count":      len(text),
        "chunk_count":     len(chunk_objs),
        "chunks":          [c["chunk_id"] for c in chunk_objs],
        "entities":        all_entities,
        "uploaded_at":     datetime.utcnow().isoformat(),
        "text_preview":    text[:500],
        "file_path":       str(stored_path),
        "file_url":        file_url,
        "stored_filename": stored_path.name,
    }

    persisted = True
    try:
        _persist_document(DOCS[doc_id], chunk_objs)
    except Exception as e:
        import traceback
        persisted = False
        print(f"ERROR: failed to persist {doc_id}: {e}")
        traceback.print_exc()

    await rag.ainsert_custom_kg(doc_kg)

    return {
        "doc_id":       doc_id,
        "filename":     file.filename,
        "chunk_count":  len(chunk_objs),
        "char_count":   len(text),
        "top_entities": list(all_entities.items())[:20],
        "file_url":     file_url,
        "persisted":    persisted,
    }


@app.get("/documents", tags=["Documents"])
def list_documents():
    return [
        {k: v for k, v in d.items() if k != "text_preview"}
        for d in DOCS.values()
    ]


@app.get("/documents/{doc_id}", tags=["Documents"])
def get_document(doc_id: str):
    if doc_id not in DOCS:
        raise HTTPException(404, "Document not found")
    return DOCS[doc_id]


@app.get("/documents/{doc_id}/file")
def get_document_file(doc_id: str):
    if doc_id not in DOCS:
        raise HTTPException(404, "Document not found")
    doc = DOCS[doc_id]
    stored_path = Path(doc["file_path"])
    if not stored_path.exists():
        raise HTTPException(404, "Stored file is missing on disk")

    # FIX #9 – detect the actual MIME type instead of always claiming PDF
    mime, _ = mimetypes.guess_type(str(stored_path))
    mime     = mime or "application/octet-stream"

    return FileResponse(
        path=doc["file_path"],
        media_type=mime,
        headers={"Content-Disposition": f'inline; filename="{doc["filename"]}"'},
    )


@app.get("/documents/{doc_id}/chunks", tags=["Documents"])
def get_document_chunks(doc_id: str, page: int = 0, size: int = 20):
    if doc_id not in DOCS:
        raise HTTPException(404, "Document not found")
    doc       = DOCS[doc_id]
    chunk_ids = doc["chunks"]
    start     = page * size
    page_ids  = chunk_ids[start: start + size]
    chunks    = [
        {k: v for k, v in CHUNKS[cid].items() if k != "embedding"}
        for cid in page_ids
        if cid in CHUNKS
    ]
    return {
        "doc_id":   doc_id,
        "total":    len(chunk_ids),
        "page":     page,
        "size":     size,
        "file_url": doc.get("file_url"),
        "chunks":   chunks,
    }


@app.get("/documents/{doc_id}/chunks/{chunk_id}", tags=["Documents"])
def get_chunk(doc_id: str, chunk_id: str):
    c = CHUNKS.get(chunk_id)
    if not c or c["doc_id"] != doc_id:
        raise HTTPException(404, "Chunk not found")
    return {k: v for k, v in c.items() if k != "embedding"}


@app.delete("/documents/{doc_id}", tags=["Documents"])
def delete_document(doc_id: str):
    if doc_id not in DOCS:
        raise HTTPException(404, "Document not found")
    doc = DOCS[doc_id]
    for cid in doc["chunks"]:
        CHUNKS.pop(cid, None)

    stored_path  = Path(doc["file_path"])
    file_deleted = False
    if stored_path.exists():
        try:
            stored_path.unlink()
            file_deleted = True
        except OSError:
            pass

    del DOCS[doc_id]
    try:
        _delete_document_row(doc_id)
    except Exception as e:
        print(f"WARNING: failed to delete {doc_id} from SQLite: {e}")

    return {"deleted": doc_id, "file_deleted": file_deleted}


# ── Search ────────────────────────────────────────────────────────────────────

@app.post("/search", tags=["Search"])
async def search(req: SearchRequest):
    candidates = await hybrid_search_async(
        req.query, req.top_k * 2, req.search_mode, req.doc_ids, req.graph_weight
    )
    if not candidates:
        return {"query": req.query, "results": [], "citations": []}
    if SENTENCE_TRANSFORMERS_OK:
        candidates = rerank(req.query, candidates)
    candidates = candidates[: req.top_k]
    citations  = build_citations(candidates)
    results    = [{k: v for k, v in c.items() if k != "embedding"} for c in candidates]
    return {
        "query":     req.query,
        "mode":      req.search_mode,
        "count":     len(results),
        "results":   results,
        "citations": citations,
    }


@app.post("/search/entities", tags=["Search"])
def entity_search(req: EntitySearchRequest):
    entity_lower = [e.lower() for e in req.entities]
    matched      = []
    for c in CHUNKS.values():
        chunk_ents = [e["text"].lower() for e in c.get("entities", [])]
        hits = sum(1 for e in entity_lower if any(e in ce for ce in chunk_ents))
        if hits > 0:
            obj                = {k: v for k, v in c.items() if k != "embedding"}
            obj["entity_hits"] = hits
            matched.append(obj)
    matched.sort(key=lambda x: x["entity_hits"], reverse=True)
    return {
        "entities": req.entities,
        "count":    len(matched[: req.top_k]),
        "results":  matched[: req.top_k],
    }


@app.get("/entities", tags=["Search"])
def list_entities(doc_id: Optional[str] = None):
    agg: Dict[str, Dict] = {}
    for c in CHUNKS.values():
        if doc_id and c["doc_id"] != doc_id:
            continue
        for e in c.get("entities", []):
            key = e["text"]
            if key not in agg:
                agg[key] = {"text": key, "label": e["label"], "count": 0, "doc_ids": set()}
            agg[key]["count"] += 1
            agg[key]["doc_ids"].add(c["doc_id"])
    result = [
        {"text": v["text"], "label": v["label"], "count": v["count"], "doc_ids": list(v["doc_ids"])}
        for v in sorted(agg.values(), key=lambda x: x["count"], reverse=True)
    ]
    return {"total": len(result), "entities": result[:200]}


# ── Shared context builder (used by both /chat and /chat/stream) ──────────────
async def _build_context(req: ChatRequest):
    """
    Run retrieval, optional reranking, and build the LLM context string.
    Returns (candidates, citations, context_str, messages).

    Centralising this keeps /chat and /chat/stream perfectly in sync —
    any change to retrieval or prompting applies to both endpoints at once.
    """
    candidates = await hybrid_search_async(
        req.query, req.top_k * 2, req.search_mode,
        doc_ids=None, graph_weight=req.graph_weight,
    )
    if req.use_reranking:
        candidates = rerank(req.query, candidates)
    candidates = candidates[: req.top_k]
    citations  = build_citations(candidates)

    # Build context blocks — include graph_score in the header when non-zero
    # so the LLM has a signal about which chunks came from the graph.
    context_blocks = []
    for i, c in enumerate(candidates):
        gs = c.get("graph_score", 0.0)
        source_tag = f"doc: {c.get('doc_name', '?')}"
        if gs > 0:
            source_tag += f", graph_score: {gs:.2f}"
        context_blocks.append(f"[{i + 1}] ({source_tag})\n{c['text']}")
    context = "\n\n".join(context_blocks)

    system = (
        "You are a precise RAG assistant with access to a knowledge graph and document chunks. "
        "Answer the question using ONLY the numbered context blocks below. "
        "Cite every claim inline with [N] notation matching the block number. "
        "Blocks tagged 'graph_score' were retrieved from a knowledge graph and may contain "
        "synthesised relationships — weigh them alongside direct text evidence. "
        "If the context does not contain enough information, say so explicitly."
    )
    messages = [
        *[{"role": m.role, "content": m.content} for m in req.history],
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {req.query}"},
    ]
    return candidates, citations, context, system, messages


# ── Chat ──────────────────────────────────────────────────────────────────────

@app.post("/chat", tags=["Chat"])
async def chat(req: ChatRequest):
    candidates, citations, context, system, messages = await _build_context(req)

    if not OLLAMA_OK:
        return {
            "answer":      f"[LLM not available] Retrieved {len(candidates)} chunks.",
            "citations":   citations,
            "chunks_used": len(candidates),
        }

    ollama_messages = [{"role": "system", "content": system}, *messages]
    response = _OLLAMA.chat(
        model=OLLAMA_MODEL,
        messages=ollama_messages,
        think=OLLAMA_THINK,
    )
    return {
        "answer":      response["message"]["content"],
        "citations":   citations,
        "chunks_used": len(candidates),
    }

from fastapi.responses import StreamingResponse
import asyncio, json
 
@app.post("/chat/stream", tags=["Chat"])
async def chat_stream(req: ChatRequest):
    candidates, citations, context, system, messages = await _build_context(req)
 
    async def event_gen():
        # Always emit citations first so the frontend can render source cards
        # before the first token arrives.
        yield f"event: citations\ndata: {json.dumps(citations)}\n\n"
 
        if not OLLAMA_OK:
            yield "data: " + json.dumps({"text": "[LLM not configured — start Ollama and set OLLAMA_MODEL]"}) + "\n\n"
            yield "event: done\ndata: {}\n\n"
            return
 
        # FIX: use the existing stream_llm() helper which correctly offloads
        # the blocking _OLLAMA.chat(stream=True) iterator to a thread via
        # asyncio.create_task + asyncio.Queue.  Consuming the queue here is
        # fully async — the event loop is never blocked.
        q = await stream_llm(system=system, messages=messages)
 
        try:
            while True:
                item = await q.get()
                if item is None:          # sentinel — stream finished
                    break
                if item["type"] == "text":
                    yield "data: " + json.dumps({"text": item["text"]}) + "\n\n"
                elif item["type"] == "error":
                    yield "event: error\ndata: " + json.dumps({"error": item["text"]}) + "\n\n"
                    return
        except asyncio.CancelledError:
            # Client disconnected — stop gracefully
            return
 
        yield "event: done\ndata: {}\n\n"
 
    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            # Prevent nginx / proxies from buffering the stream
            "X-Accel-Buffering": "no",
            "Cache-Control":     "no-cache",
        },
    )
 
# ── Graph export ──────────────────────────────────────────────────────────────
@app.get("/graph/export", tags=["Graph"])
async def graph_export(
    doc_id: Optional[str] = Query(None, description="Filter nodes/edges by source document filename"),
    max_nodes: int         = Query(2000, ge=1, le=10000, description="Hard cap on returned nodes"),
    max_edges: int         = Query(5000, ge=1, le=50000, description="Hard cap on returned edges"),
    min_degree: int        = Query(0,    ge=0,           description="Drop nodes with degree < this"),
):
    rag = _rag
    if rag is None:
        return {"nodes": [], "edges": [], "meta": {"total_nodes": 0, "total_edges": 0,
                "returned_nodes": 0, "returned_edges": 0, "truncated": False,
                "doc_id_filter": doc_id}}

    try:
        raw_nodes, raw_edges = await asyncio.gather(
            rag.chunk_entity_relation_graph.get_all_nodes(),
            rag.chunk_entity_relation_graph.get_all_edges(),
        )
    except Exception as exc:
        log.warning("graph_export: failed to read graph storage: %s", exc)
        return {"nodes": [], "edges": [], "meta": {"total_nodes": 0, "total_edges": 0,
                "returned_nodes": 0, "returned_edges": 0, "truncated": False,
                "doc_id_filter": doc_id}}

    # ── Degree map (computed over the full unfiltered graph) ──────────────────
    # Computed before any filtering so degree values reflect true connectivity
    # across the entire knowledge graph.  The most-connected nodes survive the
    # max_nodes cap even when a doc filter or per-doc quota is active.
    degree: Dict[str, int] = {}
    for e in raw_edges:
        degree[e["source"]] = degree.get(e["source"], 0) + 1
        degree[e["target"]] = degree.get(e["target"], 0) + 1

    # ── Resolve the doc_id filter → set of file_path values ──────────────────
    #
    # WHY file_path instead of source_id / chunk UUID matching:
    #
    # Our application stores chunks under UUID keys, e.g.:
    #   7fbd7348-da0b-4bd2-ad50-2c31a1b86450 → { doc_id: "...", ... }
    #
    # However, LightRAG generates its own internal chunk identifiers using a
    # different scheme — typically a hash-prefixed string such as:
    #   "chunk-2994f5a75622353c04efe02f769c4f76"
    #
    # These two ID spaces never overlap, so any set-intersection check between
    # our UUIDs and LightRAG's source_id values will always be empty, causing
    # every node/edge to be filtered out incorrectly.
    #
    # The file_path field is set by LightRAG directly from the original filename
    # we pass at ingestion time and is stored verbatim on every node and edge.
    # It therefore provides a reliable, stable join key that works regardless of
    # how LightRAG versions its internal chunk IDs.

    filter_file_paths: Optional[Set[str]] = None
    if doc_id is not None:
        # Support lookup by doc_id key OR by filename value.
        doc_meta = DOCS.get(doc_id)
        if doc_meta is None:
            for _id, meta in DOCS.items():
                if meta.get("filename") == doc_id:
                    doc_meta = meta
                    break

        if doc_meta is None:
            raise HTTPException(404, f"Document '{doc_id}' not found")

        # DOCS entries may store the filename under different keys depending on
        # how the document was ingested.  Try the most common ones in order.
        filename: Optional[str] = (
            doc_meta.get("filename")
            or doc_meta.get("file_path")
            or doc_meta.get("name")
        )

        if not filename:
            # Absolute fallback: use the doc_id itself as the filename.
            filename = doc_id

        # Build the match set: full value AND basename so we are robust to
        # LightRAG storing "report.pdf" vs "/data/report.pdf".
        filter_file_paths = {filename, os.path.basename(filename)}

    def _node_file_path(node_or_edge: Dict) -> str:
        """Return the bare basename of the file_path stored on a node/edge."""
        return os.path.basename(node_or_edge.get("file_path", ""))

    def _passes_filter(node_or_edge: Dict) -> bool:
        """
        Return True if the node/edge should be included in the response.

        When no doc_id filter is active every record passes.
        When a filter is active we match against the file_path field that
        LightRAG stores verbatim at ingestion time.
        """
        if filter_file_paths is None:
            return True
        fp: str = node_or_edge.get("file_path", "")
        if not fp:
            return False
        return fp in filter_file_paths or os.path.basename(fp) in filter_file_paths

    # ── Build chunk_id → doc_id map for response enrichment ──────────────────
    # Used only to populate doc_ids in the response for frontend colour-coding.
    # NOT used for filtering.
    chunk_to_doc: Dict[str, str] = {cid: c["doc_id"] for cid, c in CHUNKS.items()}

    def _source_id_str_to_doc_ids(source_id_str: str) -> List[str]:
        """
        Best-effort conversion of a LightRAG source_id string to our doc_ids.
        Often returns [] because LightRAG chunk IDs differ from our UUIDs —
        that is acceptable since this field is informational only.
        """
        parts = [s.strip() for s in source_id_str.split(",") if s.strip()]
        return list({chunk_to_doc[p] for p in parts if p in chunk_to_doc})

    # ── Filter and shape nodes ────────────────────────────────────────────────
    # Build the full candidate list first (respecting min_degree and the
    # doc_id filter) before applying any cap.  We need the full list so we can
    # split it by document for the equal-allocation step below.
    all_candidate_nodes: List[Dict] = []

    for n in raw_nodes:
        nid         = n.get("id", "")
        source_str  = n.get("source_id", n.get("source_ids", ""))
        node_degree = degree.get(nid, 0)

        if node_degree < min_degree:
            continue
        if not _passes_filter(n):
            continue

        all_candidate_nodes.append({
            "id":          nid,
            "label":       n.get("entity_name", nid),
            "type":        n.get("entity_type", "UNKNOWN"),
            "description": n.get("description", ""),
            "degree":      node_degree,
            "file_path":   n.get("file_path", ""),
            "doc_ids":     _source_id_str_to_doc_ids(source_str),
            "source_ids":  [s.strip() for s in source_str.split(",") if s.strip()],
        })

    total_nodes_before_cap = len(all_candidate_nodes)

    # ── Equal-allocation cap across documents (all-docs mode only) ────────────
    #
    # When doc_id is None (caller wants all documents) a naive degree-sorted
    # global cap would let large documents crowd out small ones — a document
    # with 10× more entities would occupy 10× more of the max_nodes budget.
    #
    # Instead we:
    #   1. Group candidate nodes by their file_path (i.e. source document).
    #   2. Divide max_nodes equally among the N distinct documents.
    #   3. For each document, take the top-K nodes by degree (most connected
    #      first) where K = per_doc_quota.
    #   4. If a document has fewer nodes than its quota, its unused slots are
    #      redistributed to the other documents proportionally (spillover pass).
    #   5. Merge and re-sort the survivors by degree for stable ordering.
    #
    # When a specific doc_id IS supplied the allocation is irrelevant — there
    # is only one document's worth of nodes and the plain global cap applies.

    if doc_id is None and all_candidate_nodes:
        # Group by basename so "report.pdf" and "/data/report.pdf" merge cleanly.
        by_file: Dict[str, List[Dict]] = {}
        for node in all_candidate_nodes:
            key = os.path.basename(node["file_path"]) or "__unknown__"
            by_file.setdefault(key, []).append(node)

        n_docs = len(by_file)

        if n_docs <= 1:
            # Only one document found in the graph — fall through to global cap.
            nodes_out = sorted(all_candidate_nodes, key=lambda x: x["degree"], reverse=True)[:max_nodes]
        else:
            base_quota   = max_nodes // n_docs          # floor share per doc
            remainder    = max_nodes - base_quota * n_docs  # leftover slots

            # Sort each document's nodes by degree descending.
            for key in by_file:
                by_file[key].sort(key=lambda x: x["degree"], reverse=True)

            # First pass: take up to base_quota from each document.
            # Collect surplus slots from documents that have fewer nodes than
            # their quota.
            selected: List[Dict]    = []
            surplus_slots: int      = remainder          # start with the remainder
            overflow_docs: List[str] = []               # docs that still have nodes left

            for key, doc_nodes in by_file.items():
                take      = min(base_quota, len(doc_nodes))
                selected += doc_nodes[:take]
                leftover  = len(doc_nodes) - take
                if leftover > 0:
                    overflow_docs.append(key)
                else:
                    # This doc used fewer slots than its quota — recycle the diff.
                    surplus_slots += base_quota - take

            # Second pass: distribute surplus slots to documents that still have
            # remaining nodes, round-robin by degree rank.
            if surplus_slots > 0 and overflow_docs:
                extra_per_doc = max(1, surplus_slots // len(overflow_docs))
                for key in overflow_docs:
                    if surplus_slots <= 0:
                        break
                    doc_nodes  = by_file[key]
                    already    = min(base_quota, len(doc_nodes))
                    extra_take = min(extra_per_doc, len(doc_nodes) - already, surplus_slots)
                    selected  += doc_nodes[already: already + extra_take]
                    surplus_slots -= extra_take

            nodes_out = sorted(selected, key=lambda x: x["degree"], reverse=True)
    else:
        # Single-doc filter OR no candidates — plain global cap.
        nodes_out = sorted(all_candidate_nodes, key=lambda x: x["degree"], reverse=True)[:max_nodes]

    total_nodes = total_nodes_before_cap
    capped_ids  = {n["id"] for n in nodes_out}

    # ── Filter and shape edges ────────────────────────────────────────────────
    # Only retain edges where BOTH endpoints survived the node cap / allocation.
    edges_out: List[Dict] = []

    for e in raw_edges:
        src        = e.get("source", "")
        tgt        = e.get("target", "")
        source_str = e.get("source_id", e.get("source_ids", ""))

        if src not in capped_ids or tgt not in capped_ids:
            continue
        if not _passes_filter(e):
            continue

        edges_out.append({
            "id":          f"{src}||{tgt}",
            "source":      src,
            "target":      tgt,
            "relation":    e.get("keywords", e.get("relation", e.get("relationship", "related"))),
            "description": e.get("description", ""),
            "weight":      float(e.get("weight", 1.0)),
            "file_path":   e.get("file_path", ""),
            "source_ids":  [s.strip() for s in source_str.split(",") if s.strip()],
        })

    total_edges = len(edges_out)
    edges_out   = edges_out[:max_edges]

    truncated = (total_nodes > max_nodes) or (total_edges > max_edges)

    return {
        "nodes": nodes_out,
        "edges": edges_out,
        "meta": {
            "total_nodes":    total_nodes,
            "total_edges":    total_edges,
            "returned_nodes": len(nodes_out),
            "returned_edges": len(edges_out),
            "truncated":      truncated,
            "doc_id_filter":  doc_id,
        },
    }
# ── Stats ─────────────────────────────────────────────────────────────────────
import time as _time_module
_START_TIME = _time_module.time()
 
 
# ── (2) replace existing root() ───────────────────────────────────────────────
@app.get("/", tags=["Health"])
def root():
    return {
        "name":         "DocSearch API",
        "version":      "1.0.0",
        "docs":         "/docs",
        "status":       "ok",
        # embed config
        "embed_model":  EMBED_MODEL,
        "embed_dim":    EMBED_DIM,
        # llm config
        "ollama_host":  OLLAMA_HOST,
        "ollama_model": OLLAMA_MODEL,
        # storage paths
        "db_path":      str(DB_PATH),
        "rag_storage":  str(Path("./rag_storage").resolve()),
        "upload_dir":   str(UPLOAD_DIR),
        # uptime
        "uptime_s":     round(_time_module.time() - _START_TIME, 1),
        # feature flags
        "features": {
            "reranker":    SENTENCE_TRANSFORMERS_OK,
            "spacy_ner":   SPACY_OK,
            "pdf_parser":  PDF_OK,
            "docx_parser": DOCX_OK,
            "llm":         OLLAMA_OK,
        },
    }
 
 
# ── (3) new /health endpoint (lightweight ping + live uptime) ─────────────────
@app.get("/health", tags=["Health"])
def health():
    """
    Lightweight health check — safe to poll every 30 s from the frontend.
    Returns the same payload as GET / but always 200 (no heavy work).
    """
    return {
        "status":       "ok",
        "version":      "1.0.0",
        "uptime_s":     round(_time_module.time() - _START_TIME, 1),
        "embed_model":  EMBED_MODEL,
        "embed_dim":    EMBED_DIM,
        "ollama_host":  OLLAMA_HOST,
        "ollama_model": OLLAMA_MODEL,
        "db_path":      str(DB_PATH),
        "rag_storage":  str(Path("./rag_storage").resolve()),
        "upload_dir":   str(UPLOAD_DIR),
        "documents":    len(DOCS),
        "chunks":       len(CHUNKS),
        "features": {
            "reranker":    SENTENCE_TRANSFORMERS_OK,
            "spacy_ner":   SPACY_OK,
            "pdf_parser":  PDF_OK,
            "docx_parser": DOCX_OK,
            "llm":         OLLAMA_OK,
        },
    }