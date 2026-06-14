# DocRAG — Local Document Search & Summarisation

Graph-augmented RAG over your own documents, fully offline.

| Component | Role |
|-----------|------|
| **LightRAG** (HKUDS, editable) | RAG + DAG knowledge graph engine |
| **Docling** | PDF/DOCX/HTML parsing + entity/structure extraction |
| **qwen2.5:4b** (Ollama) | Indexing / entity-extraction LLM |
| **phi4-mini** (Ollama) | Query answering LLM |
| **nomic-embed-text** (Ollama) | Embeddings |
| **Flask + Jinja2** | Web UI |

---

## 1 — Prerequisites

```bash
# Ollama must be running
ollama serve

# Pull required models
ollama pull qwen2.5:4b
ollama pull phi4-mini
ollama pull nomic-embed-text
```

---

## 2 — Install LightRAG (editable, new version)

```bash
git clone https://github.com/HKUDS/LightRAG.git
cd LightRAG
pip install -e ".[api]"
cd ..
```

---

## 3 — Install remaining dependencies

```bash
pip install -r requirements.txt
```

---

## 4 — Run

```bash
python app.py
# Open http://localhost:5000
```

---

## 5 — Environment variables (optional overrides)

| Variable | Default | Description |
|----------|---------|-------------|
| `INDEXING_MODEL` | `qwen2.5:4b` | Ollama model for graph/entity indexing |
| `ANSWER_MODEL` | `phi4-mini` | Ollama model for answering queries |
| `EMBED_MODEL` | `nomic-embed-text` | Ollama embedding model |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API base URL |
| `EMBED_DIM` | `768` | Embedding dimension (must match model) |
| `NUM_CTX` | `32768` | Context window (≥ 32 k required by LightRAG) |
| `SECRET_KEY` | `change-me-in-production` | Flask session secret |

---

## 6 — How it works

```
Upload (PDF/DOCX/TXT/MD/HTML)
        │
        ▼
   Docling Parser
   ├─ extracts markdown text
   └─ extracts heading/table entity hints
        │
        ▼
  LightRAG ainsert()
   ├─ text chunking
   ├─ qwen4b → entity/relation extraction → Knowledge Graph (GraphML)
   └─ nomic-embed-text → vector index (nano-vectordb)
        │
  Query ▼
  LightRAG aquery(mode=hybrid|local|global|naive)
   ├─ vector search  (local context)
   ├─ graph traversal (global reasoning)
   └─ phi4-mini → final answer
```

---

## 7 — Supported file types

`.pdf` · `.txt` · `.md` · `.docx` · `.html`

---

## 8 — Query modes

| Mode | Description |
|------|-------------|
| **Hybrid** | Combines local vector + global graph (recommended) |
| **Local** | Nearest-neighbour entity search |
| **Global** | Graph-level community reasoning |
| **Naive** | Simple vector similarity, no graph |
