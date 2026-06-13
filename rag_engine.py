"""
rag_engine.py
─────────────
LightRAG (HKUDS editable install) wired to:
  • Docling  – document parsing + entity/structure extraction
  • qwen4b   – indexing / entity-extraction LLM  (via Ollama)
  • phi4-mini – answer LLM                        (via Ollama)
  • nomic-embed-text – embeddings                 (via Ollama)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np

# ── LightRAG (editable install: pip install -e ".[api]") ──────────────────────
from lightrag import LightRAG, QueryParam
from lightrag.llm.ollama import ollama_model_complete, ollama_embed
from lightrag.utils import EmbeddingFunc

# ── Docling ───────────────────────────────────────────────────────────────────
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import PdfFormatOption

log = logging.getLogger(__name__)

# ── Model names ───────────────────────────────────────────────────────────────
INDEXING_MODEL = os.getenv("INDEXING_MODEL",  "qwen2.5:4b")   # entity extraction / graph building
ANSWER_MODEL   = os.getenv("ANSWER_MODEL",    "phi4-mini")     # query answering
EMBED_MODEL    = os.getenv("EMBED_MODEL",     "nomic-embed-text")
OLLAMA_HOST    = os.getenv("OLLAMA_HOST",     "http://localhost:11434")
EMBED_DIM      = int(os.getenv("EMBED_DIM",  "768"))
NUM_CTX        = int(os.getenv("NUM_CTX",    "32768"))          # must be ≥32k for LightRAG


class RAGEngine:
    """Wraps LightRAG with dual-model Ollama setup and Docling pre-processing."""

    def __init__(self, storage_dir: str = "rag_storage"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.rag: LightRAG | None = None
        self._converter = self._build_converter()

    # ── Docling document converter ────────────────────────────────────────────
    @staticmethod
    def _build_converter() -> DocumentConverter:
        pdf_opts = PdfPipelineOptions()
        pdf_opts.do_ocr          = False   # set True if you have scanned PDFs
        pdf_opts.do_table_structure = True
        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_opts),
            }
        )

    # ── Embedding function (nomic-embed-text via Ollama) ──────────────────────
    def _make_embedding_func(self) -> EmbeddingFunc:
        async def _embed(texts: list[str]) -> np.ndarray:
            return await ollama_embed(
                texts,
                embed_model=EMBED_MODEL,
                host=OLLAMA_HOST,
            )

        return EmbeddingFunc(
            embedding_dim=EMBED_DIM,
            max_token_size=8192,
            func=_embed,
        )

    # ── Indexing LLM wrapper (qwen4b) ─────────────────────────────────────────
    @staticmethod
    def _indexing_llm():
        """
        Returns an async callable compatible with LightRAG's llm_model_func
        signature.  Used for graph/entity extraction (heavier context).
        """
        async def _call(prompt: str, system_prompt: str | None = None,
                        history_messages: list | None = None, **kwargs) -> str:
            # Strip keys that LightRAG may inject but ollama_model_complete doesn't accept
            kwargs.pop("model", None)
            return await ollama_model_complete(
                prompt,
                system_prompt=system_prompt,
                history_messages=history_messages or [],
                host=OLLAMA_HOST,
                model=INDEXING_MODEL,
                options={"num_ctx": NUM_CTX},
                **kwargs,
            )
        return _call

    # ── Answer LLM wrapper (phi4-mini) ────────────────────────────────────────
    @staticmethod
    def _answer_llm():
        """Lighter model used only at query time."""
        async def _call(prompt: str, system_prompt: str | None = None,
                        history_messages: list | None = None, **kwargs) -> str:
            kwargs.pop("model", None)
            return await ollama_model_complete(
                prompt,
                system_prompt=system_prompt,
                history_messages=history_messages or [],
                host=OLLAMA_HOST,
                model=ANSWER_MODEL,
                options={"num_ctx": NUM_CTX},
                **kwargs,
            )
        return _call

    # ── Initialise LightRAG ───────────────────────────────────────────────────
    async def initialise(self):
        log.info("Initialising LightRAG  (indexing=%s, answer=%s, embed=%s)",
                 INDEXING_MODEL, ANSWER_MODEL, EMBED_MODEL)

        # Detect which kwargs the installed LightRAG version accepts
        import inspect
        _sig = inspect.signature(LightRAG.__init__).parameters

        init_kwargs = dict(
            working_dir=str(self.storage_dir),
            llm_model_func=self._indexing_llm(),
            embedding_func=self._make_embedding_func(),
        )

        # These params exist in older versions but were removed in newer ones
        if "llm_model_name" in _sig:
            init_kwargs["llm_model_name"] = INDEXING_MODEL
        if "llm_model_max_async" in _sig:
            init_kwargs["llm_model_max_async"] = 2
        if "llm_model_max_token_size" in _sig:
            init_kwargs["llm_model_max_token_size"] = 8192
        if "llm_model_kwargs" in _sig:
            init_kwargs["llm_model_kwargs"] = {
                "host": OLLAMA_HOST,
                "options": {"num_ctx": NUM_CTX},
            }

        log.info("LightRAG init params: %s", list(init_kwargs.keys()))
        self.rag = LightRAG(**init_kwargs)

        # LightRAG >= 1.3 requires async init
        if hasattr(self.rag, "ainit"):
            await self.rag.ainit()
        log.info("LightRAG initialised ✓")

    # ── Docling text + entity extraction ─────────────────────────────────────
    def _docling_extract(self, path: Path) -> tuple[str, list[dict]]:
        """
        Returns (plain_text, entities).
        Docling exports structured markdown; we also pull table/heading entities.
        """
        result = self._converter.convert(str(path))
        doc    = result.document

        # Full text (markdown-flavoured for best entity context)
        text = doc.export_to_markdown()

        # Entity candidates from headings, tables, key-value pairs
        entities: list[dict] = []
        for item, _ in doc.iterate_items():
            label = getattr(item, "label", None)
            if label in ("section_header", "title"):
                entities.append({"type": "HEADING", "text": item.text})
            elif label == "table":
                entities.append({"type": "TABLE", "text": getattr(item, "text", "")})

        log.info("Docling extracted %d chars, %d entity hints from %s",
                 len(text), len(entities), path.name)
        return text, entities

    # ── Ingest a file into the graph ──────────────────────────────────────────
    async def ingest_file(self, path: Path) -> str:
        if self.rag is None:
            raise RuntimeError("Call initialise() first")

        suffix = path.suffix.lower()
        if suffix in (".txt", ".md"):
            text     = path.read_text(encoding="utf-8", errors="replace")
            entities = []
        else:
            text, entities = self._docling_extract(path)

        # Prepend structured entity hints as a header block
        if entities:
            header = "=== DOCUMENT STRUCTURE HINTS ===\n"
            for e in entities[:40]:           # cap to avoid huge preambles
                header += f"[{e['type']}] {e['text']}\n"
            header += "=== END HINTS ===\n\n"
            text = header + text

        # LightRAG >= 1.3 exposes ainsert
        if hasattr(self.rag, "ainsert"):
            await self.rag.ainsert(text)
        else:
            await asyncio.get_event_loop().run_in_executor(
                None, self.rag.insert, text
            )

        return f"Ingested {len(text):,} chars with {len(entities)} Docling entities"

    # ── Query / answer ────────────────────────────────────────────────────────
    async def answer(self, query: str, mode: str = "hybrid",
                     summarise: bool = False) -> str:
        if self.rag is None:
            raise RuntimeError("Call initialise() first")

        # Switch to answer LLM for query time
        self.rag.llm_model_func = self._answer_llm()

        if summarise:
            query = (
                f"Please provide a comprehensive summary answering: {query}\n"
                "Include key entities, relationships, and supporting evidence."
            )

        param = QueryParam(mode=mode)

        if hasattr(self.rag, "aquery"):
            result = await self.rag.aquery(query, param=param)
        else:
            loop   = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, lambda: self.rag.query(query, param=param)
            )

        # Restore indexing LLM for future inserts
        self.rag.llm_model_func = self._indexing_llm()
        return str(result)

    # ── Export knowledge graph ─────────────────────────────────────────────────
    async def export_graph(self) -> dict[str, Any]:
        """Return {nodes, edges} for D3 visualisation."""
        if self.rag is None:
            return {"nodes": [], "edges": []}

        graph_path = self.storage_dir / "graph_chunk_entity_relation.graphml"
        if not graph_path.exists():
            return {"nodes": [], "edges": [], "note": "Graph not yet built"}

        try:
            import networkx as nx
            G = nx.read_graphml(str(graph_path))
            nodes = [{"id": n, **d} for n, d in G.nodes(data=True)]
            edges = [{"source": u, "target": v, **d}
                     for u, v, d in G.edges(data=True)]
            return {"nodes": nodes[:500], "edges": edges[:1000]}   # cap for browser
        except ImportError:
            return {"error": "networkx not installed – run: pip install networkx"}
        except Exception as exc:
            return {"error": str(exc)}