"""
rag_engine.py  –  LightRAG 1.5.3 + Docling + Ollama
"""

from __future__ import annotations

import asyncio
import gc
import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any

import aiohttp
import numpy as np

from lightrag import LightRAG, QueryParam
from lightrag.utils import EmbeddingFunc

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("rag_engine")

# ── Config ────────────────────────────────────────────────────────────────────
LLM_MODEL      = os.getenv("LLM_MODEL",      "phi4-mini:latest")
EMBED_MODEL    = os.getenv("EMBED_MODEL",    "nomic-embed-text")
OLLAMA_HOST    = os.getenv("OLLAMA_HOST",    "http://localhost:11434")
EMBED_DIM      = int(os.getenv("EMBED_DIM",  "768"))
NUM_CTX        = int(os.getenv("NUM_CTX",    "4096"))
PDF_PAGE_BATCH = int(os.getenv("PDF_PAGE_BATCH", "3"))
NUM_PREDICT    = int(os.getenv("NUM_PREDICT", "-1"))

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

    prompt_tokens_approx = len(full_prompt) // 4   # rough char→token estimate
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
                "options": {"num_ctx": NUM_CTX, "num_predict": NUM_PREDICT},
                "think":  False,
            },
            timeout=aiohttp.ClientTimeout(total=300),
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
            timeout=aiohttp.ClientTimeout(total=60),
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
                timeout=aiohttp.ClientTimeout(total=10),
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


# ── RAGEngine ─────────────────────────────────────────────────────────────────
class RAGEngine:

    def __init__(self, storage_dir: str = "rag_storage"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.rag: LightRAG | None = None
        self._converter = self._build_converter()
        log.info(
            "RAGEngine created | storage=%s | llm=%s | embed=%s | dim=%d | ctx=%d",
            self.storage_dir, LLM_MODEL, EMBED_MODEL, EMBED_DIM, NUM_CTX,
        )

    # ── Docling ───────────────────────────────────────────────────────────────
    @staticmethod
    def _build_converter() -> DocumentConverter:
        log.debug("Building Docling DocumentConverter (OCR=off, tables=off)")
        pdf_opts = PdfPipelineOptions()
        pdf_opts.do_ocr             = False
        pdf_opts.do_table_structure = False
        for attr in ("generate_picture_images", "generate_page_images"):
            if hasattr(pdf_opts, attr):
                setattr(pdf_opts, attr, False)
        return DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_opts)}
        )
    def _save_chunk_meta(self, path: Path, chunks_meta: list[dict]):
        """Save chunk→page mapping next to the graph storage."""
        meta_dir  = self.storage_dir / "chunk_meta"
        meta_dir.mkdir(exist_ok=True)
        meta_file = meta_dir / f"{path.stem}.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(chunks_meta, f, indent=2)
        log.info("Chunk metadata saved: %s (%d chunks)", meta_file, len(chunks_meta))

    def load_all_chunk_meta(self) -> list[dict]:
        """Load all chunk metadata for all ingested files."""
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
            max_parallel_insert=1,
        )
        await self.rag.initialize_storages()
        log.info("LightRAG initialised successfully")

    # ── PDF helpers ───────────────────────────────────────────────────────────
    @staticmethod
    def _count_pdf_pages(path: Path) -> int | None:
        try:
            import pypdf
            with open(path, "rb") as fh:
                n = len(pypdf.PdfReader(fh).pages)
            log.debug("Page count via pypdf: %d — %s", n, path.name)
            return n
        except Exception:
            pass
        try:
            import pymupdf
            doc = pymupdf.open(str(path))
            n = doc.page_count; doc.close()
            log.debug("Page count via pymupdf: %d — %s", n, path.name)
            return n
        except Exception:
            pass
        log.warning("Could not determine page count for %s", path.name)
        return None

    @staticmethod
    def _fallback_pdf_text(path: Path) -> str:
        log.warning("Using fallback text extraction for %s", path.name)
        try:
            import pypdf
            text = "\n\n".join(
                p.extract_text() or "" for p in pypdf.PdfReader(str(path)).pages
            )
            log.info("Fallback (pypdf) extracted %d chars from %s", len(text), path.name)
            return text
        except Exception as exc:
            log.debug("pypdf fallback failed: %s", exc)
        try:
            import pymupdf
            doc = pymupdf.open(str(path))
            text = "\n\n".join(doc[i].get_text() for i in range(doc.page_count))
            doc.close()
            log.info("Fallback (pymupdf) extracted %d chars from %s", len(text), path.name)
            return text
        except Exception as exc:
            log.debug("pymupdf fallback failed: %s", exc)
        log.error("All extraction methods failed for %s", path.name)
        return f"[Could not extract text from {path.name}]"

    @staticmethod
    def _collect_entities(doc, entities: list[dict]):
        try:
            before = len(entities)
            for item, _ in doc.iterate_items():
                label = getattr(item, "label", None)
                txt   = getattr(item, "text",  "") or ""
                if label in ("section_header", "title") and txt.strip():
                    entities.append({"type": "HEADING", "text": txt.strip()})
            added = len(entities) - before
            if added:
                log.debug("Collected %d heading entities from doc chunk", added)
        except Exception as exc:
            log.debug("Entity collection skipped: %s", exc)

    # ── Docling extraction ────────────────────────────────────────────────────
    def _docling_extract(self, path: Path) -> tuple[str, list[dict], list[dict]]:
        log.info("Starting Docling extraction: %s", path.name)
        entities:    list[dict] = []
        chunks_meta: list[dict] = []   # ← new
        t0    = time.perf_counter()
        total = (
            self._count_pdf_pages(path) if path.suffix.lower() == ".pdf" else None
        )

        if total is None:
            try:
                result = self._converter.convert(str(path))
                text   = result.document.export_to_markdown()
                self._collect_entities(result.document, entities)
                chunks_meta.append({"source": path.name, "page_start": 1, "page_end": 1})
                log.info("Docling done: %d chars, %d entities, %.1fs — %s",
                        len(text), len(entities), time.perf_counter() - t0, path.name)
                return text, entities, chunks_meta
            except Exception as exc:
                log.warning("Docling single-pass failed (%s) — using fallback", exc)
                return self._fallback_pdf_text(path), [], []

        n_batches = (total + PDF_PAGE_BATCH - 1) // PDF_PAGE_BATCH
        log.info("%s: %d pages | batch_size=%d | %d batches",
                path.name, total, PDF_PAGE_BATCH, n_batches)
        chunks: list[str] = []

        for batch_idx, start in enumerate(range(0, total, PDF_PAGE_BATCH), 1):
            end     = min(start + PDF_PAGE_BATCH, total)
            t_batch = time.perf_counter()
            log.info("Batch %d/%d — pages %d–%d | %s",
                    batch_idx, n_batches, start + 1, end, path.name)
            try:
                result = self._converter.convert(str(path), page_range=(start + 1, end))
                chunk  = result.document.export_to_markdown()
                if chunk.strip():
                    chunks.append(chunk)
                    chunks_meta.append({          # ← record page range
                        "source":     path.name,
                        "file_path":  str(path),
                        "page_start": start + 1,
                        "page_end":   end,
                        "chunk_idx":  batch_idx,
                    })
                    log.debug("Batch %d/%d — %d chars in %.1fs",
                            batch_idx, n_batches, len(chunk), time.perf_counter() - t_batch)
                self._collect_entities(result.document, entities)
                del result; gc.collect()
            except Exception as exc:
                log.warning("Batch %d/%d failed: %s — pypdf fallback", batch_idx, n_batches, exc)
                try:
                    import pypdf
                    reader = pypdf.PdfReader(str(path))
                    pages  = [reader.pages[i].extract_text() or ""
                            for i in range(start, min(end, len(reader.pages)))]
                    fallback_text = "\n\n".join(pages)
                    chunks.append(fallback_text)
                    chunks_meta.append({
                        "source":     path.name,
                        "file_path":  str(path),
                        "page_start": start + 1,
                        "page_end":   end,
                        "chunk_idx":  batch_idx,
                        "fallback":   True,
                    })
                    log.info("Batch %d/%d pypdf fallback: %d chars", batch_idx, n_batches, len(fallback_text))
                except Exception as fb_exc:
                    log.error("Batch %d/%d all extraction failed: %s", batch_idx, n_batches, fb_exc)
                gc.collect()

        text = "\n\n".join(chunks) or self._fallback_pdf_text(path)
        log.info("Docling complete: %d chars, %d entities, %.1fs — %s",
                len(text), len(entities), time.perf_counter() - t0, path.name)
        return text, entities, chunks_meta

    # ── Ingest ────────────────────────────────────────────────────────────────
    async def ingest_file(self, path: Path) -> str:
        if self.rag is None:
            raise RuntimeError("Call initialise() first")

        log.info("Ingesting file: %s", path)
        t0 = time.perf_counter()

        if path.suffix.lower() in (".txt", ".md"):
            log.debug("Plain text file — skipping Docling")
            text, entities = path.read_text(encoding="utf-8", errors="replace"), []
            chunks_meta = [{"content": text, "source": path.name, "page": 1}]
        else:
            text, entities, chunks_meta = self._docling_extract(path)

        if entities:
            header  = "=== DOCUMENT STRUCTURE ===\n"
            header += "\n".join(f"[{e['type']}] {e['text']}" for e in entities[:40])
            header += "\n=== END ===\n\n"
            text = header + text

        log.info("Sending %d chars to LightRAG ainsert …", len(text))
        await self.rag.ainsert(text, file_paths=str(path))
        if chunks_meta:
            self._save_chunk_meta(path, chunks_meta)
        elapsed = time.perf_counter() - t0
        summary = f"Ingested {len(text):,} chars, {len(entities)} entities in {elapsed:.1f}s"
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
        result = await self.rag.aquery(query, param=QueryParam(mode=mode))
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
                min(len(nodes), 500), G.number_of_nodes(),
                min(len(edges), 1000), G.number_of_edges(),
            )
            return {"nodes": nodes[:500], "edges": edges[:1000]}
        except ImportError:
            log.error("networkx not installed — run: pip install networkx")
            return {"error": "pip install networkx"}
        except Exception as exc:
            log.error("Graph export failed: %s", exc, exc_info=True)
            return {"error": str(exc)}