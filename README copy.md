# KnowledgeRAG+

A hybrid RAG (Retrieval-Augmented Generation) backend that extends
[knowledge-rag](https://github.com/lyonzin/knowledge-rag) with **chunk-level
citations** and **entity-aware hybrid search**.

---

## Features

| Feature | Details |
|---|---|
| **Hybrid search** | Semantic (ChromaDB cosine) + BM25 keyword + Entity overlap fused with RRF |
| **Cross-encoder reranking** | `cross-encoder/ms-marco-MiniLM-L-6-v2` re-scores top candidates |
| **Chunk citations** | Every chunk gets a stable 4-char ID (e.g. `a3z1`). LLM answers embed `[xxxx]` markers; the API resolves them to source metadata |
| **Entity extraction** | spaCy NER at ingest time; entity inverted index enables entity-lane retrieval |
| **20 document formats** | `.md .txt .pdf .py .json .csv .docx .xlsx .pptx .ipynb` + URL ingestion |
| **Streaming chat** | SSE endpoint streams tokens, then emits citations at the end |
| **Category routing** | Keyword → category pre-filter; configurable in `config.yaml` |
| **Query expansion** | Synonym injection before BM25 + embedding |
| **LLM providers** | Anthropic (`claude-*`) and OpenAI (`gpt-*`) |

---

## Architecture

```
Upload  →  Parse  →  Chunk (size=1000, overlap=200)
                  →  Embed   (FastEmbed: BAAI/bge-small-en-v1.5)
                  →  NER     (spaCy: en_core_web_sm)
                  →  Store   ChromaDB  +  BM25 index  +  Entity index

Query   →  Expand query (synonym injection)
        →  Route category (keyword→category map)
        │
        ├─ Lane 1: Semantic   ChromaDB cosine similarity
        ├─ Lane 2: BM25       rank-bm25 keyword search
        └─ Lane 3: Entity     in-memory inverted index overlap
        │
        →  RRF fusion (weighted: sem_w · bm25_w · entity_w)
        →  Cross-encoder reranking
        →  LLM prompt with [citation_id]-tagged context
        →  Parse [xxxx] markers → CitationOut objects
        →  Structured JSON response
```

---

## Quick Start

### Local (bare metal)

```bash
# 1. Clone and enter
git clone <this-repo>
cd knowledge-rag-plus/backend

# 2. Install Python deps
pip install -r requirements.txt

# 3. Download spaCy model
python -m spacy download en_core_web_sm

# 4. Configure
cp .env.example .env
# Edit .env — at minimum set ANTHROPIC_API_KEY or OPENAI_API_KEY

# 5. Run
uvicorn main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### Docker

```bash
cp backend/.env.example backend/.env   # add your API key
docker compose up --build
```

---

## Configuration

All settings live in `backend/config.yaml`. Environment variables in `.env`
take precedence over `config.yaml`.

### Key settings

```yaml
# config.yaml
documents:
  chunking:
    chunk_size:    1000   # chars per chunk
    chunk_overlap: 200

models:
  embedding:
    model: BAAI/bge-small-en-v1.5   # change to bge-base for higher quality
  reranker:
    enabled: true
    model:   cross-encoder/ms-marco-MiniLM-L-6-v2

search:
  default_hybrid_alpha: 0.3   # 0.0=BM25 only, 1.0=semantic only

entity:
  entity_weight: 0.25          # fraction of RRF score for entity lane

llm:
  provider: anthropic
  model:    claude-3-5-haiku-20241022
```

---

## API Reference

Base URL: `http://localhost:8000/api/v1`

Interactive docs: `/docs` (Swagger UI) · `/redoc` (ReDoc)

---

### Health

#### `GET /health`

Returns service status and index statistics.

**Response**
```json
{
  "status":          "healthy",
  "total_chunks":    1024,
  "bm25_chunks":     1024,
  "entity_count":    342,
  "entity_chunks":   1024,
  "collection_name": "knowledge_base",
  "embedding_model": "BAAI/bge-small-en-v1.5",
  "reranker_model":  "cross-encoder/ms-marco-MiniLM-L-6-v2"
}
```

---

### Documents

#### `POST /documents/upload`

Upload one or more files for ingestion.

**Form fields**

| Field | Type | Required | Description |
|---|---|---|---|
| `files` | `File[]` | ✅ | One or more files |
| `category` | `string` | — | Category label override |

**Supported formats:** `.md` `.txt` `.pdf` `.py` `.json` `.csv` `.docx` `.xlsx` `.pptx` `.ipynb`

**Response**
```json
{
  "total_added":    47,
  "total_skipped":  3,
  "total_errors":   0,
  "elapsed_seconds": 2.14,
  "files": [
    { "source": "report.pdf", "added": 47, "skipped": 3, "error": null }
  ]
}
```

Each chunk stored in ChromaDB receives:
- A stable **`citation_id`** (4-char, e.g. `a3z1`) derived from SHA-256 of content + source
- Extracted **entities** stored as a pipe-separated string in metadata

---

#### `POST /documents/url`

Fetch a public URL and ingest its main text content.

**Request body**
```json
{
  "url":      "https://example.com/article",
  "category": "research",
  "title":    "Optional display title"
}
```

**Response:** same as single file in `upload`.

---

#### `POST /documents/reindex`

Walk the `documents/` directory and ingest any files not yet indexed.

**Query params**

| Param | Type | Default | Description |
|---|---|---|---|
| `full_rebuild` | `bool` | `false` | Wipe collection first (destructive) |

---

#### `GET /documents/`

List all indexed documents (one entry per source file).

**Query params:** `category` (optional filter)

**Response**
```json
[
  {
    "source":   "research/paper.pdf",
    "filename": "paper.pdf",
    "category": "research",
    "format":   "pdf",
    "chunks":   34
  }
]
```

---

#### `GET /documents/{source}`

Get all chunks for a specific document, sorted by `chunk_index`.

**Response**
```json
[
  {
    "id":           "chunk_a1b2c3d4e5f6g7h8",
    "citation_id":  "a3z1",
    "content":      "The transformer architecture ...",
    "chunk_index":  0,
    "total_chunks": 34,
    "entities":     "Transformer|Attention|BERT",
    "metadata":     { ... }
  }
]
```

---

#### `DELETE /documents/{source}`

Remove all chunks for the given source from ChromaDB, BM25, and entity index.

**Response**
```json
{ "source": "research/paper.pdf", "chunks_deleted": 34 }
```

---

### Search

#### `POST /search/`

**Three-lane hybrid search** — the default and recommended endpoint.

**Request body**
```json
{
  "query":         "How does attention mechanism work?",
  "max_results":   5,
  "category":      null,
  "hybrid_alpha":  0.3,
  "entity_weight": null
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `query` | `string` | — | Search query |
| `max_results` | `int` | `5` | 1–50 |
| `category` | `string` | `null` | Filter to category |
| `hybrid_alpha` | `float` | `0.3` | `0.0`=BM25 · `1.0`=semantic |
| `entity_weight` | `float` | config | Share for entity lane in RRF |

**Response**
```json
{
  "query":         "How does attention mechanism work?",
  "total_found":   5,
  "search_method": "hybrid",
  "results": [
    {
      "citation_id":    "a3z1",
      "content":        "Attention allows the model to focus ...",
      "source":         "research/attention.pdf",
      "filename":       "attention.pdf",
      "category":       "research",
      "format":         "pdf",
      "chunk_index":    3,
      "total_chunks":   22,
      "entities":       "Transformer|Attention|Vaswani",
      "rrf_score":      0.032541,
      "reranker_score": 8.214,
      "search_lanes":   ["semantic", "keyword"],
      "search_method":  "hybrid",
      "routed_by":      null,
      "query_entities": ["attention mechanism"]
    }
  ]
}
```

---

#### `POST /search/semantic`

Pure embedding cosine-similarity search. No BM25 or entity lane.

Same request/response shape as `POST /search/`.

---

#### `POST /search/keyword`

Pure BM25 keyword search with query expansion. No embedding or entity lane.

Same request/response shape as `POST /search/`.

---

#### `POST /search/entity`

Pure entity-overlap search. Extracts entities from the query using spaCy
and finds chunks whose stored entity list overlaps.

Same request/response shape as `POST /search/`.

---

#### `GET /search/stats`

Index statistics (same as `/health`).

---

#### `GET /search/categories`

Returns a sorted list of all category labels in the index.

```json
["general", "hr", "research"]
```

---

### Chat

#### `POST /chat/`

Full RAG pipeline: retrieve → generate with citations → resolve markers.

**Request body**
```json
{
  "query":         "What is the main contribution of the paper?",
  "max_chunks":    5,
  "category":      null,
  "hybrid_alpha":  0.3,
  "entity_weight": null,
  "stream":        false,
  "system_prompt": null,
  "history":       []
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `query` | `string` | — | User question |
| `max_chunks` | `int` | `5` | Chunks to retrieve for context (1–20) |
| `category` | `string` | `null` | Filter retrieval to category |
| `hybrid_alpha` | `float` | `0.3` | Retrieval blend |
| `entity_weight` | `float` | config | Entity lane weight |
| `stream` | `bool` | `false` | Use `/chat/stream` instead for SSE |
| `system_prompt` | `string` | `null` | Override default system prompt |
| `history` | `ChatMessage[]` | `[]` | Previous turns (for context) |

**Response**
```json
{
  "query":   "What is the main contribution?",
  "answer":  "The paper introduces the Transformer architecture [a3z1], which replaces recurrence with self-attention [b7fx].",
  "model":   "claude-3-5-haiku-20241022",
  "search_method": "hybrid",
  "citations": [
    {
      "citation_id":     "a3z1",
      "source":          "research/attention.pdf",
      "filename":        "attention.pdf",
      "category":        "research",
      "chunk_index":     3,
      "total_chunks":    22,
      "content_snippet": "The Transformer architecture relies solely on attention mechanisms ..."
    },
    {
      "citation_id":     "b7fx",
      "source":          "research/attention.pdf",
      "filename":        "attention.pdf",
      "category":        "research",
      "chunk_index":     7,
      "total_chunks":    22,
      "content_snippet": "Self-attention allows each position to attend to all positions ..."
    }
  ],
  "context_chunks": [ ... ]   // full SearchResultChunk objects passed to LLM
}
```

---

#### `POST /chat/stream`

Streaming SSE chat. Connect with `EventSource` or an SSE client.

**Request body:** same as `POST /chat/`

**Event stream**

Each event is a newline-delimited JSON object prefixed with `data: `.

```
data: {"type": "context", "context_chunks": [...]}

data: {"type": "token", "content": "The paper introduces "}
data: {"type": "token", "content": "the Transformer "}
data: {"type": "token", "content": "[a3z1], which "}
...

data: {"type": "citations", "citations": [{...}, {...}]}

data: {"type": "done"}
```

| Event type | Fields | Description |
|---|---|---|
| `context` | `context_chunks` | Retrieved chunks (sent before tokens) |
| `token` | `content` | One streamed token |
| `citations` | `citations` | Resolved citation list (sent after full answer) |
| `error` | `message` | Stream error |
| `done` | — | Stream complete |

**JavaScript example**
```javascript
const es = new EventSource('/api/v1/chat/stream', { method: 'POST' });
// (use fetch + ReadableStream for POST SSE in practice)

es.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  if (msg.type === 'token')     appendToken(msg.content);
  if (msg.type === 'citations') renderCitations(msg.citations);
  if (msg.type === 'done')      es.close();
};
```

---

#### `GET /chat/citation/{citation_id}`

Resolve a 4-char citation ID to its full chunk.

**Path param:** `citation_id` — e.g. `a3z1`

**Response**
```json
{
  "citation_id":  "a3z1",
  "content":      "The Transformer architecture relies solely on ...",
  "source":       "research/attention.pdf",
  "filename":     "attention.pdf",
  "category":     "research",
  "format":       "pdf",
  "chunk_index":  3,
  "total_chunks": 22,
  "entities":     "Transformer|Attention|Vaswani"
}
```

Use this for "jump to source" hyperlink behaviour in a frontend.

---

### Entities

#### `POST /entities/extract`

Run NER on arbitrary text and return detected entities.

**Request body**
```json
{ "text": "Elon Musk founded SpaceX in Hawthorne, California." }
```

**Response**
```json
{
  "count": 3,
  "entities": [
    { "text": "Elon Musk",   "label": "PERSON", "start": 0,  "end": 9  },
    { "text": "SpaceX",      "label": "ORG",    "start": 18, "end": 24 },
    { "text": "Hawthorne",   "label": "GPE",    "start": 28, "end": 37 }
  ]
}
```

---

#### `POST /entities/search`

Find chunks whose stored entity list overlaps with the given entity names.

**Request body**
```json
{
  "entities":    ["SpaceX", "Elon Musk"],
  "max_results": 10
}
```

**Response**
```json
[
  {
    "citation_id":   "c9qq",
    "content":       "SpaceX was founded by Elon Musk ...",
    "source":        "docs/companies.md",
    "filename":      "companies.md",
    "category":      "general",
    "chunk_index":   2,
    "entities":      "SpaceX|Elon Musk|NASA",
    "overlap_score": 1.0
  }
]
```

---

#### `GET /entities/stats`

```json
{ "entity_count": 342, "chunk_count": 1024 }
```

---

#### `GET /entities/list`

Paginated list of all indexed entities, sorted by chunk count.

**Query params:** `skip` (default `0`), `limit` (default `100`, max `1000`)

```json
[
  { "entity": "transformer", "chunk_count": 48 },
  { "entity": "openai",      "chunk_count": 31 }
]
```

---

#### `GET /entities/document/{source}`

All entities extracted from a specific document, grouped by label.

```json
{
  "source":                "research/attention.pdf",
  "chunks":                22,
  "total_unique_entities": 17,
  "entities": {
    "ENTITY": ["Attention", "BERT", "GPT", "Transformer", "Vaswani"]
  }
}
```

---

## Citation ID System

Every chunk stored in ChromaDB is assigned a **stable 4-char citation ID**:

```python
citation_id = sha256(f"{source_path}::{chunk_content}")[:mapped_to_4_chars]
# e.g. "a3z1"
```

- IDs are **stable across restarts** — same content + source always gives the same ID
- IDs are stored in ChromaDB metadata under the key `citation_id`
- The LLM system prompt instructs the model to embed `[xxxx]` markers inline
- The `/chat` endpoint parses those markers and resolves them to full `CitationOut` objects
- Use `GET /chat/citation/{id}` to resolve any ID to its source chunk

---

## Project Structure

```
backend/
├── main.py                  # FastAPI app, lifespan, router mounts
├── config.yaml              # All settings with defaults
├── .env.example             # Environment variable template
├── requirements.txt
├── Dockerfile
│
├── core/
│   ├── config.py            # Settings dataclasses + YAML loader
│   ├── rag_engine.py        # ChromaDB + BM25 + entity index + RRF + reranker
│   ├── ingestion.py         # Parse → chunk → ingest pipeline
│   ├── llm.py               # Anthropic / OpenAI answer generation + streaming
│   ├── citations.py         # Citation ID generation + marker parsing
│   └── entities.py          # spaCy NER + EntityIndex (inverted index)
│
├── routers/
│   ├── documents.py         # /api/v1/documents — upload, list, delete, reindex
│   ├── search.py            # /api/v1/search    — hybrid, semantic, keyword, entity
│   ├── chat.py              # /api/v1/chat      — RAG Q&A + streaming SSE
│   └── entities.py          # /api/v1/entities  — extract, search, list
│
├── models/
│   └── schemas.py           # Pydantic v2 request/response models
│
└── parsers/
    └── document_parser.py   # Per-format parsers (PDF, DOCX, XLSX, PPTX, …)

docker-compose.yml           # Single-service compose with named volumes
```

---

## Adding Documents

### Drop files in `documents/` then reindex

```bash
cp my_report.pdf documents/
curl -X POST http://localhost:8000/api/v1/documents/reindex
```

### Upload via API

```bash
curl -X POST http://localhost:8000/api/v1/documents/upload \
     -F "files=@report.pdf" \
     -F "files=@notes.md" \
     -F "category=research"
```

### Ingest a URL

```bash
curl -X POST http://localhost:8000/api/v1/documents/url \
     -H "Content-Type: application/json" \
     -d '{"url": "https://arxiv.org/abs/1706.03762", "category": "research"}'
```

---

## Extending

### Add a new document format

1. Add a `parse_myformat(path: Path) -> List[str]` function in `parsers/document_parser.py`
2. Register it in the `_PARSERS` dict
3. Add the extension to `documents.supported_formats` in `config.yaml`

### Add a custom entity label

Subclass the spaCy pipeline or add a custom rule-based component in `core/entities.py`
and add your label to `entity.entity_types` in `config.yaml`.

### Change the embedding model

Update `models.embedding.model` in `config.yaml`. The model is downloaded
automatically by FastEmbed on first run. Wipe `data/chroma_db/` and reindex
when changing models (embedding dimensions may differ).

---

## License

MIT
