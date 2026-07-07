# Luminai Documentation RAG Chatbot

A memory-enabled Retrieval-Augmented Generation (RAG) chatbot for Luminai workflow documentation. It ingests PDFs, text files, and Luminai workflow blueprint JSON files, indexes them with embeddings, and answers questions with conversation context.

---

## Installation

### Prerequisites

- Python 3.9+
- pip
- API keys for your chosen LLM/embedding provider (see [LLMs Supported](#llms-supported))

### Setup

```bash
cd luminai-documentation-rag

python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

Use the project virtualenv for all commands below (`venv/bin/python` or an activated shell).

### Environment configuration

Create a `.env` file in the project root:

```bash
# Generation (gemini | openai | lite)
GENERATION_PROVIDER=lite

# Embeddings for documents and memory (gemini | openai | lite)
DOC_EMBEDDING_PROVIDER=lite
MEMORY_EMBEDDING_PROVIDER=lite

# Lite LLM (KeyValue Systems gateway)
LITE_LLM_KEY=your_lite_llm_key_here
KV_LLM_LITE_MODEL=gpt-4o-mini
LITE_EMBEDDING_MODEL=text-embedding-3-small
LITE_LLM_BASE_URL=https://llm.keyvalue.systems

# Optional: direct provider keys if not using lite
GEMINI_API_KEY=your_gemini_key_here
OPENAI_API_KEY=your_openai_key_here

SESSION_ID=default
TOP_K_DOCS=6
TOP_K_MEMORY=3
```

**Important:** Do not define the same variable twice in `.env`. If `MEMORY_EMBEDDING_PROVIDER` appears more than once, the last value wins.

### Prepare documents

Place files in `documents/` and map them to workflows in `document_tags.json`:

```text
documents/
  ├── Alma RFL.pdf
  ├── Hazel - Document Call from Zendesk.json
  └── ...
```

```json
{
  "Alma RFL.pdf": "Alma RFL",
  "Hazel - Document Call from Zendesk.json": "Hazel - Document Call from Zendesk"
}
```

Supported file types: `.pdf`, `.txt`, and workflow blueprint `.json`.

---

## Web UI Walkthrough

### 1. Start the server

```bash
python3 app.py
```

Open **http://localhost:5000**

### 2. Select a workflow

On first load you see the **workflow selector**:

1. Choose a workflow from the dropdown (e.g. `Hazel - Document Call from Zendesk`)
2. Click **Select & Ingest**
3. Wait for ingestion to finish — only documents tagged with that workflow are indexed

This builds `index/faiss.index` and `index/chunks.jsonl` for the selected workflow.

### 3. Chat

1. Open the **Chat** tab
2. Type a question, e.g. `Explain the Hazel Document Call from Zendesk workflow`
3. Press Enter — the answer streams in with retrieved document context

The chatbot remembers conversation context and supports follow-up questions.

### 4. Documents tab

- Click **Refresh list** to see documents in the active workflow
- Review which files are available for retrieval

### 5. Upload tab

Add new files without leaving the UI:

1. Drag and drop or select a `.pdf`, `.txt`, or blueprint `.json`
2. Enter a workflow tag (optional for blueprints with a `name` field)
3. Click **Upload**
4. Click **Chunk and Ingest** to rebuild the index

Blueprint JSON files are auto-detected and tagged from their internal workflow name when no tag is provided.

### 6. Change workflow

Click **← Change Workflow** in the header to return to the selector and ingest a different workflow.

---

## Architecture

### Data flow

```text
1. User selects workflow (web UI or API)
        ↓
2. Documents + blueprint JSON filtered by tag
        ↓
3. Text extracted → chunked → embedded → FAISS index
        ↓
4. User query → embed → retrieve top chunks + conversation memory
        ↓
5. LLM generates answer → stored in session memory
        ↓
6. Response streamed to UI
```

### Core components

| File | Role |
|------|------|
| `app.py` | Flask server, REST API, web UI |
| `chatbot.py` | RAG engine, query routing, LLM clients |
| `ingest.py` | Document loading, chunking, indexing |
| `workflow_manager.py` | Workflow/tag discovery |
| `workflow_blueprint.py` | Luminai JSON → searchable text |
| `conversation_memory.py` | Embedding providers + memory FAISS index |
| `memory_store.py` | SQLite conversation history |
| `reindex_memory.py` | Rebuild memory index after provider changes |

### Project structure

```text
luminai-documentation-rag/
├── app.py                     # Web server + API
├── chatbot.py                 # RAG + LLM logic
├── ingest.py                  # Document indexing
├── workflow_manager.py        # Workflow/tag management
├── workflow_blueprint.py      # JSON blueprint parser
├── conversation_memory.py     # Memory embeddings
├── memory_store.py            # SQLite message store
├── reindex_memory.py          # Rebuild memory index
├── templates/index.html       # Web UI
├── documents/                 # Source files (PDF, TXT, JSON)
├── index/                     # Document FAISS index
├── memory_index/              # Conversation memory index
├── examples/                  # Sample blueprint JSON
├── document_tags.json         # Filename → workflow mapping
├── session.db                 # Message history
├── requirements.txt
└── README.md
```

### Workflow blueprint JSON

Luminai exports (e.g. `Hazel - Document Call from Zendesk.json`) are parsed into searchable text:

- Workflow name, description, and build status
- Steps: integrations, UI interactions, branches, loops
- Connections between nodes
- Grounded automation scripts (secrets stripped)

Upload via the **Upload** tab or API:

```bash
curl -X POST http://localhost:5000/api/workflows/blueprint/ingest \
  -F "file=@documents/Hazel - Document Call from Zendesk.json"
```

See `examples/sample_workflow_blueprint.json` for a simplified generic schema.

---

## LLMs Supported

Three providers are supported for **generation** and **embeddings**, configured independently in `.env`.

| Provider | Env value | Generation | Embeddings | API key |
|----------|-----------|------------|------------|---------|
| **Lite LLM** | `lite` | `gpt-4o-mini` via KeyValue gateway | `text-embedding-3-small` | `LITE_LLM_KEY` |
| **Gemini** | `gemini` | `GEMINI_MODEL` (default `gemini-2.0-flash`) | `gemini-embedding-001` | `GEMINI_API_KEY` |
| **OpenAI** | `openai` | `OPENAI_MODEL` (default `gpt-4o-mini`) | `text-embedding-3-small` | `OPENAI_API_KEY` |

### Configuration variables

| Variable | Values | Purpose |
|----------|--------|---------|
| `GENERATION_PROVIDER` | `gemini`, `openai`, `lite` | Answer generation |
| `DOC_EMBEDDING_PROVIDER` | `gemini`, `openai`, `lite` | Document retrieval embeddings |
| `MEMORY_EMBEDDING_PROVIDER` | `gemini`, `openai`, `lite` | Conversation memory embeddings |

### Lite LLM-specific variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `LITE_LLM_KEY` | — | API key for KeyValue gateway |
| `LITE_LLM_BASE_URL` | `https://llm.keyvalue.systems` | Gateway base URL |
| `KV_LLM_LITE_MODEL` | `gpt-4o-mini` | Chat model |
| `LITE_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model |

### Provider switching notes

- Document and memory indexes must be built with the **same** embedding provider
- After changing providers, rebuild both indexes:

```bash
python3 ingest.py              # or select workflow in UI
python3 reindex_memory.py      # rebuild conversation memory
```

- Typical embedding dimensions: Gemini ≈ 3072, Lite/OpenAI = 1536

---

## Dependencies

Installed via `pip install -r requirements.txt`:

| Package | Purpose |
|---------|---------|
| `flask` | Web server and REST API |
| `pypdf` | PDF text extraction |
| `python-dotenv` | `.env` configuration loading |
| `google-genai` | Gemini generation and embeddings |
| `openai` | OpenAI and Lite LLM embeddings |
| `langchain-openai` | Lite LLM chat client (`ChatOpenAI`) |
| `faiss-cpu` | Vector similarity search |
| `numpy` | Embedding array operations |

SQLite is used for conversation storage (stdlib, no extra install).

---

## Additional usage

### CLI chat

```bash
python3 chatbot.py
```

| Command | Description |
|---------|-------------|
| `:summary` | Show conversation summary |
| `:facts` | List extracted facts |
| `:session` | Show session ID |
| `:sources` | Show active document sources |
| `:quit` / `:exit` | Exit |

### API reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/workflows` | GET | List workflows |
| `/api/workflows/<name>/files` | GET | Files in a workflow |
| `/api/workflows/select` | POST | Select and ingest a workflow |
| `/api/workflows/blueprint/ingest` | POST | Upload/ingest a blueprint JSON |
| `/api/workflow/status` | GET | Current workflow status |
| `/api/chat` | POST | Send a query (SSE stream) |
| `/api/documents` | GET | List all documents |
| `/api/documents/upload` | POST | Upload a file |
| `/api/documents/ingest` | POST | Ingest all documents |

```bash
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the steps in this workflow?"}'
```

### Command-line ingestion

```bash
# Ingest all documents
python3 ingest.py

# Ingest one workflow
python3 -c "from ingest import ingest_documents; print(ingest_documents(workflow_filter='Alma RFL'))"
```

---

## Troubleshooting

### `Missing LITE_LLM_KEY for Lite LLM embeddings`

Confirm `LITE_LLM_KEY` is set in `.env`, restart the app, and run from the project venv.

### `Memory index dimension mismatch. Existing=3072, new=1536`

Embedding provider changed without rebuilding memory. Run `python3 reindex_memory.py`.

### Memory provider shows `gemini` but `.env` says `lite`

Check for duplicate `MEMORY_EMBEDDING_PROVIDER` lines in `.env` — only keep one.

### `429 RESOURCE_EXHAUSTED` (Gemini)

Gemini credits depleted. Switch to `lite` or `openai` and rebuild indexes.

### `Index or model not available`

Select a workflow in the UI or run `python3 ingest.py` first.

### No documents found for a workflow

Verify exact filename in `document_tags.json` and that the file exists in `documents/`.

---

**Last updated:** July 2026
