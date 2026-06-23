"""
rag_engine.py  –  LightRAG 1.5.3 + Unstructured + Ollama
"""

from __future__ import annotations
import asyncio
import gc
import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any
from dockling_document_extraction import extract_with_dockling
from contextual_chunker import chunk_elements
import aiohttp
import numpy as np
from bs4 import BeautifulSoup


from lightrag import LightRAG, QueryParam
from lightrag.utils import EmbeddingFunc

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("rag_engine")

# ── Config ────────────────────────────────────────────────────────────────────
LLM_MODEL      = os.getenv("LLM_MODEL",      "qwen3-coder:480b-cloud")
EMBED_MODEL    = os.getenv("EMBED_MODEL",    "nomic-embed-text")
OLLAMA_HOST    = os.getenv("OLLAMA_HOST",    "http://localhost:11434")
EMBED_DIM      = int(os.getenv("EMBED_DIM",  "768"))
NUM_CTX        = int(os.getenv("NUM_CTX",    "12288"))
NUM_PREDICT    = int(os.getenv("NUM_PREDICT", "4096"))

_BASE = OLLAMA_HOST.rstrip("/")

# ── Call counters (module-level, lightweight telemetry) ───────────────────────
_llm_call_count   = 0
_embed_call_count = 0


# ── Ollama helpers (direct REST — no lightrag wrappers) ───────────────────────
async def _ollama_chat(
    prompt: str,
    system_prompt: str | None = None,
    history_messages: list | None = None,
    **kwargs,          # absorb everything LightRAG injects
) -> str:
    global _llm_call_count
    _llm_call_count += 1
    call_id = _llm_call_count
    full_prompt = ""
    if system_prompt:
        full_prompt += f"{system_prompt}\n\n"
    for msg in (history_messages or []):
        if isinstance(msg, dict):
            role    = msg.get("role", "user").capitalize()
            content = msg.get("content", "")
            full_prompt += f"{role}: {content}\n"
    full_prompt += prompt

    prompt_tokens_approx = len(full_prompt) // 4
    log.info(
        "[LLM #%d] → %s | prompt ~%d tokens | history=%d msgs",
        call_id, LLM_MODEL, prompt_tokens_approx, len(history_messages or []),
    )
    log.debug("[LLM #%d] Full prompt:\n%s", call_id, full_prompt)

    t0 = time.perf_counter()
    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"{_BASE}/api/generate",
            json={
                "model":  LLM_MODEL,
                "prompt": full_prompt,
                "stream": False,
                "options": {"num_ctx": NUM_CTX, "num_predict": NUM_PREDICT, "stop": ["<|COMPLETE|>"]},
                "think":  False,
            },
            timeout=aiohttp.ClientTimeout(total=1800),
        ) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)

    elapsed       = time.perf_counter() - t0
    response_text = data.get("response", "")
    resp_tokens   = data.get("eval_count",        len(response_text) // 4)
    prompt_eval   = data.get("prompt_eval_count", prompt_tokens_approx)
    tps           = resp_tokens / elapsed if elapsed > 0 else 0

    log.info(
        "[LLM #%d] ← done | %.1fs | prompt=%d tok | response=%d tok | %.1f tok/s",
        call_id, elapsed, prompt_eval, resp_tokens, tps,
    )
    log.debug("[LLM #%d] Response:\n%s", call_id, response_text)
    print(full_prompt)
    print(response_text)
    return response_text


async def _ollama_embed(texts: list[str]) -> np.ndarray:
    """Call /api/embed directly — bypasses LightRAG's EmbeddingFunc validator."""
    global _embed_call_count
    _embed_call_count += 1
    call_id = _embed_call_count

    log.debug("[EMBED #%d] → %s | %d text(s)", call_id, EMBED_MODEL, len(texts))

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

    log.debug("[EMBED #%d] ← shape=%s | %.2fs", call_id, arr.shape, elapsed)

    if arr.shape[1] != EMBED_DIM:
        log.error(
            "[EMBED #%d] Dimension mismatch: model returned %d, expected %d. "
            "Set EMBED_DIM=%d and delete rag_storage/ before restarting.",
            call_id, arr.shape[1], EMBED_DIM, arr.shape[1],
        )
        raise ValueError(
            f"{EMBED_MODEL} returned dim={arr.shape[1]} but EMBED_DIM={EMBED_DIM}. "
            f"Set EMBED_DIM={arr.shape[1]}, delete rag_storage/, restart."
        )
    return arr


def _make_embedding_func() -> EmbeddingFunc:
    return EmbeddingFunc(
        embedding_dim=EMBED_DIM,
        max_token_size=8192,
        func=_ollama_embed,
    )


# ── Ollama connectivity check ─────────────────────────────────────────────────
async def _check_ollama():
    log.info("Checking Ollama connectivity at %s …", _BASE)
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{_BASE}/api/tags",
                timeout=aiohttp.ClientTimeout(total=100),
            ) as resp:
                resp.raise_for_status()
                data   = await resp.json(content_type=None)
                models = [m["name"] for m in data.get("models", [])]
                log.info("Ollama reachable | available models: %s", models)

                req = LLM_MODEL.split(":")[0]
                if not any(m == LLM_MODEL or m.split(":")[0] == req for m in models):
                    log.error(
                        "Required model '%s' not found. Pull it with: ollama pull %s",
                        LLM_MODEL, LLM_MODEL,
                    )
                    raise RuntimeError(
                        f"Model '{LLM_MODEL}' not found. Run: ollama pull {LLM_MODEL}"
                    )
                log.info("Model '%s' confirmed available", LLM_MODEL)
    except aiohttp.ClientConnectorError:
        log.critical("Cannot reach Ollama at %s — is 'ollama serve' running?", _BASE)
        raise RuntimeError(
            f"Cannot reach Ollama at {_BASE}. Run: ollama serve"
        )


# ── Unstructured extraction helpers ──────────────────────────────────────────

def _html_table_to_records(html: str) -> list[dict]:
    """Convert an HTML table string to a list of row dicts."""
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.find_all("tr")
    if len(rows) < 2:
        return []
    headers = [
        cell.get_text(" ", strip=True)
        for cell in rows[0].find_all(["th", "td"])
    ]
    records = []
    for row in rows[1:]:
        values = [
            cell.get_text(" ", strip=True)
            for cell in row.find_all(["th", "td"])
        ]
        if not values:
            continue
        if len(values) < len(headers):
            values.extend([""] * (len(headers) - len(values)))
        records.append({headers[i]: values[i] for i in range(len(headers))})
    return records


def _extract_with_dockling(path: Path) -> list[dict]:
    """
    Run dockling hi_res partition on *path* and return a list of element
    dicts, each with keys ``type`` and ``text`` (tables also carry ``data``).
    """
    log.info("Unstructured extraction: %s", path.name)
    t0 = time.perf_counter()

    elements = partition(
        filename=str(path),
        strategy="hi_res",
        infer_table_structure=True,
    )

    output: list[dict] = []
    for el in elements:
        category = getattr(el, "category", "Unknown")
        text     = getattr(el, "text", "") or ""

        if category == "Table":
            html = None
            if hasattr(el, "metadata"):
                html = getattr(el.metadata, "text_as_html", None)
            if html:
                records = _html_table_to_records(html)
                output.append({"type": "Table", "data": records, "text": str(records)})
            else:
                output.append({"type": "Table", "text": text})
        else:
            if text.strip():
                output.append({"type": category, "text": text})

    log.info(
        "Unstructured done: %d elements in %.1fs — %s",
        len(output), time.perf_counter() - t0, path.name,
    )
    return output


def _chunk_elements(
    elements: list[dict],
    target_size: int = 1200,
    overlap: int = 150,
) -> list[dict]:
    """
    Merge element dicts into larger text chunks, keeping tables as standalone
    chunks.  Returns list of ``{"index": int, "type": str, "text": str}``.
    """
    chunks: list[dict] = []
    current_parts: list[str] = []
    current_size = 0

    def _flush():
        nonlocal current_parts, current_size
        if current_parts:
            chunks.append({"type": "section", "text": "\n\n".join(current_parts)})
            current_parts = []
            current_size  = 0

    for el in elements:
        text    = el.get("text", "").strip()
        el_type = el.get("type", "")

        if not text:
            continue

        # Tables are always standalone chunks
        if el_type == "Table":
            _flush()
            chunks.append(
                {
                    "type": "table",
                    "text": text,
                    "data": el.get("data", [])
                }
            )
            continue

        # Oversized paragraphs get split with overlap
        if len(text) > target_size * 1.5:
            _flush()
            start = 0
            while start < len(text):
                chunks.append({"type": "paragraph", "text": text[start: start + target_size]})
                start += target_size - overlap
            continue

        if current_size + len(text) > target_size:
            overlap_text = current_parts[-1][-overlap:] if current_parts else ""
            _flush()
            current_parts = [overlap_text, text] if overlap_text else [text]
            current_size  = len(overlap_text) + len(text)
        else:
            current_parts.append(text)
            current_size += len(text)

    _flush()

    return [
        {"index": i, "type": c["type"], "text": c["text"],  "data": c.get("data")}
        for i, c in enumerate(chunks)
    ]


# ── RAGEngine ─────────────────────────────────────────────────────────────────
class RAGEngine:

    def __init__(self, storage_dir: str = "rag_storage"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.rag: LightRAG | None = None
        log.info(
            "RAGEngine created | storage=%s | llm=%s | embed=%s | dim=%d | ctx=%d",
            self.storage_dir, LLM_MODEL, EMBED_MODEL, EMBED_DIM, NUM_CTX,
        )

    # ── Chunk metadata ────────────────────────────────────────────────────────
    def _save_chunk_meta(self, path: Path, chunks_meta: list[dict]):
        meta_dir  = self.storage_dir / "chunk_meta"
        meta_dir.mkdir(exist_ok=True)
        meta_file = meta_dir / f"{path.stem}.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(chunks_meta, f, indent=2)
        log.info("Chunk metadata saved: %s (%d chunks)", meta_file, len(chunks_meta))

    def load_all_chunk_meta(self) -> list[dict]:
        meta_dir = self.storage_dir / "chunk_meta"
        if not meta_dir.exists():
            return []
        all_meta = []
        for meta_file in meta_dir.glob("*.json"):
            try:
                with open(meta_file, encoding="utf-8") as f:
                    all_meta.extend(json.load(f))
            except Exception as exc:
                log.warning("Could not load chunk meta %s: %s", meta_file, exc)
        return all_meta

    # ── Storage helpers ───────────────────────────────────────────────────────
    def wipe_storage(self):
        log.warning("Wiping RAG storage at %s", self.storage_dir)
        shutil.rmtree(self.storage_dir, ignore_errors=True)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        log.info("Storage wiped and recreated: %s", self.storage_dir)

    def _check_and_wipe_if_dim_mismatch(self):
        vdb = self.storage_dir / "vdb_entities.json"
        if not vdb.exists():
            log.debug("No existing vector DB found — fresh start")
            return
        try:
            with open(vdb, encoding="utf-8") as f:
                data = json.load(f)
            stored = data.get("embedding_dim")
            if stored is None:
                log.debug("No embedding_dim recorded in vdb_entities.json")
                return
            if int(stored) != EMBED_DIM:
                log.warning(
                    "Embedding dim mismatch: stored=%s, configured=%d — wiping storage",
                    stored, EMBED_DIM,
                )
                self.wipe_storage()
            else:
                log.debug(
                    "Embedding dim OK: stored=%s matches EMBED_DIM=%d", stored, EMBED_DIM,
                )
        except Exception as exc:
            log.warning("Could not read stored embedding_dim: %s", exc)

    # ── Initialise ────────────────────────────────────────────────────────────
    async def initialise(self):
        log.info(
            "Initialising LightRAG 1.5.3 | llm=%s | embed=%s | dim=%d | ctx=%d | num_predict=%d",
            LLM_MODEL, EMBED_MODEL, EMBED_DIM, NUM_CTX, NUM_PREDICT,
        )
        await _check_ollama()
        self._check_and_wipe_if_dim_mismatch()

        log.debug("Creating LightRAG instance …")
        self.rag = LightRAG(
            working_dir=str(self.storage_dir),
            llm_model_func=_ollama_chat,
            embedding_func=_make_embedding_func(),
            max_parallel_insert=4,
            chunk_token_size=1200,
            chunk_overlap_token_size=100
        )
        await self.rag.initialize_storages()
        log.info("LightRAG initialised successfully")

    # ── Extraction: dockling → chunks ─────────────────────────────────────
    def _extract_and_chunk(
        self,
        path: Path,
    ) -> tuple[str, list[dict]]:
        """
        Run dockling on *path*, merge elements into chunks, and return:
          - full_text  : all chunk texts joined (fed to LightRAG)
          - chunks_meta: list of chunk metadata dicts for provenance tracking
        """
        elements = _extract_with_dockling(path)
        chunks   = _chunk_elements(elements)

        chunks_meta: list[dict] = []
        texts: list[str] = []

        for chunk in chunks:
            text = chunk.get("text", "").strip()
            if not text:
                continue
            texts.append(text)
            chunks_meta.append({
                "source":    path.name,
                "file_path": str(path),
                "chunk_idx": chunk["index"],
                "type":      chunk["type"],
                "table_data": chunk.get("data")
                # page info not available from dockling without page_number metadata;
                # add page_start/page_end here if you enable include_page_breaks=True
            })

        full_text = "\n\n".join(texts)
        log.info(
            "Extraction complete: %d elements → %d chunks → %d chars — %s",
            len(elements), len(chunks), len(full_text), path.name,
        )
        return full_text, chunks_meta

    # ── Ingest ────────────────────────────────────────────────────────────────
    async def ingest_file(self, path: Path) -> str:
        if self.rag is None:
            raise RuntimeError("Call initialise() first")

        log.info("Ingesting file: %s", path)
        t0 = time.perf_counter()

        if path.suffix.lower() in (".txt", ".md"):
            log.debug("Plain text file — skipping dockling")
            text = path.read_text(encoding="utf-8", errors="replace")
            chunks_meta = [{"source": path.name, "file_path": str(path),
                            "chunk_idx": 0, "type": "text"}]
        else:
            text, chunks_meta = self._extract_and_chunk(path)

        log.info("Sending %d chars to LightRAG ainsert …", len(text))

        await self.rag.ainsert(text, file_paths=str(path))


        if chunks_meta:
            self._save_chunk_meta(path, chunks_meta)

        elapsed = time.perf_counter() - t0
        summary = (
            f"Ingested {len(text):,} chars, "
            f"{len(chunks_meta)} chunks in {elapsed:.1f}s"
        )
        log.info("Ingest complete — %s | %s", path.name, summary)
        return summary

    # ── Query ─────────────────────────────────────────────────────────────────
    async def answer(self, query: str, mode: str = "hybrid",
                     summarise: bool = False) -> str:
        if self.rag is None:
            raise RuntimeError("Call initialise() first")

        if summarise:
            query = (
                f"Provide a comprehensive summary answering: {query}\n"
                "Include key entities, relationships, and evidence."
            )

        log.info("Query [mode=%s summarise=%s]: %.120s", mode, summarise, query)
        t0     = time.perf_counter()
        result = await self.rag.aquery(query, param=QueryParam(mode=mode, top_k=5))
        elapsed     = time.perf_counter() - t0
        answer_text = str(result)
        log.info(
            "Query answered in %.1fs | response=%d chars", elapsed, len(answer_text),
        )
        log.debug("Answer:\n%s", answer_text)
        return answer_text

    # ── Graph export ──────────────────────────────────────────────────────────
    async def export_graph(self) -> dict[str, Any]:
        if self.rag is None:
            log.warning("export_graph called before initialise()")
            return {"nodes": [], "edges": []}

        graph_path = self.storage_dir / "graph_chunk_entity_relation.graphml"
        if not graph_path.exists():
            log.warning("Graph file not found at %s — graph not yet built", graph_path)
            return {"nodes": [], "edges": [], "note": "Graph not yet built"}

        log.info("Exporting knowledge graph from %s", graph_path)
        try:
            import networkx as nx
            G     = nx.read_graphml(str(graph_path))
            nodes = [{"id": n, **d} for n, d in G.nodes(data=True)]
            edges = [{"source": u, "target": v, **d} for u, v, d in G.edges(data=True)]
            log.info(
                "Graph export: %d/%d nodes, %d/%d edges (caps: 500/1000)",
                len(nodes), G.number_of_nodes(),
                len(edges), G.number_of_edges(),
            )
            return {"nodes": nodes, "edges": edges}
        except ImportError:
            log.error("networkx not installed — run: pip install networkx")
            return {"error": "pip install networkx"}
        except Exception as exc:
            log.error("Graph export failed: %s", exc, exc_info=True)
            return {"error": str(exc)}