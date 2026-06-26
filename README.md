# 🔍 DocSearch — Local AI Document Search

> Graph-augmented RAG over your own documents. Fully offline. No cloud required.

Upload PDFs, DOCX, TXT, Markdown, or HTML files and ask questions in natural language. DocSearch builds a knowledge graph from your documents using LightRAG and answers queries with a triple-fusion pipeline — semantic vectors, BM25 keyword search, and graph traversal — all powered by local LLMs via Ollama.

---

## ✨ Features

- **Fully local & private** — all processing happens on your machine, no data leaves it
- **Triple-fusion retrieval** — semantic (dense vectors) + BM25 keyword + LightRAG knowledge graph
- **Knowledge graph RAG** — entities and relationships extracted into a graph for deep reasoning
- **Multiple search modes** — `semantic`, `keyword`, `hybrid`, `graph`, `full`
- **Re-ranking** — optional CrossEncoder re-ranking for higher precision
- **Multi-format support** — PDF, DOCX, TXT, MD, HTML
- **FastAPI backend** — REST API with streaming LLM responses and citation support
- **Electron desktop UI** — native desktop frontend (DocSearch.exe)
- **SQLite persistence** — documents and embeddings survive restarts

---

## 🧱 Tech Stack

| Component | Role |
|---|---|
| **LightRAG** (HKUDS) | RAG engine + DAG knowledge graph (local+global graph traversal) |
| **Docling** | PDF/DOCX/HTML parsing & structured element extraction |
| **FastAPI + Uvicorn** | REST backend with streaming chat and search endpoints |
| **SQLite** | Persistent storage for documents, chunks, and embeddings |
| **Ollama** | Local LLM and embedding server |
| **qwen2.5:4b** | Indexing & entity-extraction LLM |
| **phi4-mini** | Query answering LLM |
| **nomic-embed-text** | Text embeddings (768-dim) |
| **Electron** | Desktop frontend (DocSearch.exe) |

---

## ⚙️ Prerequisites

- **Python 3.11+**
- **[Ollama](https://ollama.com/download)** installed and running
- **Git**
- **Windows** (for the Electron frontend / compiled launcher)

---

## 🚀 Installation

### 1. Clone the repository

```bash
git clone https://github.com/Ashutosh-Ranjan310106/search_engine_and_document_retrival.git
cd search_engine_and_document_retrival
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install LightRAG (editable install — required)

```bash
git clone https://github.com/HKUDS/LightRAG.git
cd LightRAG
pip install -e ".[api]"
cd ..
```

### 4. Install project dependencies

```bash
pip install -r requirements.txt
```

### 5. Pull required Ollama models

```bash
# Start Ollama first (if not already running)
ollama serve

# Pull the three models used by the app
ollama pull qwen2.5:4b        # indexing & entity extraction
ollama pull phi4-mini          # query answering
ollama pull nomic-embed-text   # embeddings
```

### 6. Configure environment variables

The app reads from a `.env` file in the project root. A default `.env` is already committed. Edit it to override:

```env
OLLAMA_HOST=http://localhost:11434
INDEXING_MODEL=qwen2.5:4b
ANSWER_MODEL=phi4-mini
EMBED_MODEL=nomic-embed-text
EMBED_DIM=768
EMBED_MAX_TOKENS=8192
NUM_CTX=32768
SECRET_KEY=change-me-in-production
UPLOAD_DIR=./uploads
DB_PATH=./docsearch.db
MAX_UPLOAD_MB=50
```

> ⚠️ If you change `EMBED_MODEL` or `EMBED_DIM`, delete the `rag_storage/` folder so LightRAG rebuilds its vector index with the correct dimensions.

---

## ▶️ Running the App

### Option A — Compiled launcher (recommended for Windows)

Build the launcher once (see [Building the EXE](#-building-the-launcher-exe)), then just run:

```bash
run_me.exe
```

This starts Ollama, the FastAPI backend on `http://127.0.0.1:8000`, and the Electron frontend automatically. Close the DocSearch window to shut everything down cleanly.

### Option B — Manual start (development)

Open three terminals:

```bash
# Terminal 1 — Ollama
ollama serve

# Terminal 2 — FastAPI backend
uvicorn backend.knowledge_rag:app --host 127.0.0.1 --port 8000

# Terminal 3 — Electron frontend (or open the built exe directly)
frontend\dist\win-unpacked\DocSearch.exe
```

API docs are available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

---

## 🔍 Search Modes

| Mode | How it works |
|---|---|
| `semantic` | Dense vector cosine similarity only |
| `keyword` | BM25 sparse retrieval only |
| `hybrid` | BM25 + semantic, 50/50 blend (default) |
| `graph` | LightRAG knowledge graph traversal only |
| `full` | BM25 + semantic + graph, weighted fusion *(recommended)* |

In `full` mode, the graph signal weight is controlled by `graph_weight` (0.0–1.0, default `0.3`). The remaining weight is split equally between semantic and BM25.

---

## 📡 Key API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Health check & feature flags |
| `POST` | `/documents/upload` | Upload a document (PDF/DOCX/TXT/MD/HTML) |
| `GET` | `/documents` | List all documents |
| `DELETE` | `/documents/{doc_id}` | Delete a document |
| `GET` | `/documents/{doc_id}/file` | Download the original file |
| `POST` | `/search` | Search across documents |
| `POST` | `/chat` | Streaming chat with citations |

Full interactive docs at `/docs` (Swagger UI).

---

## 📖 How It Works

```
Upload (PDF / DOCX / TXT / MD / HTML)
        │
        ▼
   Docling Parser
   ├─ structured element extraction (headings, tables, paragraphs)
   └─ entity hints from document structure
        │
        ▼
  Chunking + Embedding
   ├─ contextual chunking (1200 chars, 150 overlap)
   ├─ nomic-embed-text → 768-dim vectors → SQLite blob storage
   └─ entity extraction (spaCy NER + rule-based)
        │
        ▼
  LightRAG ainsert()
   ├─ qwen2.5:4b  →  entity & relation extraction  →  Knowledge Graph
   └─ nomic-embed-text  →  LightRAG vector index (rag_storage/)
        │
  Query ▼
  hybrid_search_async(mode="full")
   ├─ semantic leg   →  cosine similarity (768-dim vectors)
   ├─ BM25 leg       →  sparse keyword scoring
   ├─ graph leg      →  LightRAG aquery(mode="mix")
   └─ score fusion   →  weighted merge → top-k chunks
        │
        ▼
  Optional CrossEncoder re-ranking
        │
        ▼
  phi4-mini  →  streaming answer with inline citations
```

---

## 📁 Project Structure

```
├── .gitattributes
├── .gitignore
├── README.md
├── requirements.txt
├── backend/                        # FastAPI backend
│   ├── __init__.py
│   ├── knowledge_rag.py            # Main FastAPI app & RAG pipeline
│   ├── contextual_chunker.py       # Text chunking logic
│   ├── dockling_document_extraction.py  # Docling document parser
│   ├── entity_extractor.py         # Entity extraction (NER + rules)
│   ├── hierarchy_kg.py             # Knowledge graph hierarchy builder
│   └── lightrag_support.py         # LightRAG node/edge converters
└── frontend/                       # Electron + React desktop UI
    ├── index.html
    ├── package.json
    ├── package-lock.json
    ├── vite.config.js
    ├── electron/
    │   └── main.cjs                # Electron main process
    ├── public/
    │   └── favicon.svg
    └── src/
        ├── main.jsx
        ├── App.jsx
        ├── App.css
        ├── index.css
        ├── api.js                  # Backend API client
        └── components/
            ├── ChatBox.jsx / .css
            ├── DocumentList.jsx / .css
            ├── DocumentViewer.jsx / .css
            ├── GraphPage.jsx / .css
            ├── OfflineLoader.jsx / .css
            ├── SearchPanel.jsx / .css
            ├── StatsBar.jsx / .css
            ├── UploadPanel.jsx / .css
            └── ui.jsx / .css
```

> Auto-created at runtime: `rag_storage/` (LightRAG index & graph), `uploads/` (uploaded files), `docsearch.db` (SQLite database)

---

## 🛠️ Building the Launcher EXE

Compile `run_me.py` into a standalone Windows executable:

```bash
pip install pyinstaller
python -m PyInstaller --onefile --console --name run_me --icon=backend.ico run_me.py
```

Output: `dist\run_me.exe`

Place it in the project root (alongside the `Ollama\` folder and `frontend\dist\win-unpacked\`) before running.

---

## 🤝 Contributing

Pull requests are welcome. For major changes please open an issue first.

```bash
git checkout -b feature/my-feature
git commit -m "add my feature"
git push origin feature/my-feature
# then open a Pull Request
```

---

## 📄 License

This project is open source. See [LICENSE](LICENSE) for details.
