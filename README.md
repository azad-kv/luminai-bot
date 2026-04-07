# Luminai Documentation RAG Chatbot

A memory-enabled Retrieval-Augmented Generation (RAG) chatbot that intelligently retrieves information from tagged document workflows and maintains conversation context.

## Recent Changes

### New Workflow Selection Feature

This update introduces the ability to select a specific workflow (tag) before querying the chatbot. When you select a workflow, only documents tagged with that workflow are ingested into the search index.

#### What's New

1. **workflow_manager.py** - New module for managing workflows
   - `get_all_workflows()` - Extract unique tags from document_tags.json
   - `get_files_for_workflow(workflow)` - Get all documents for a specific workflow
   - `is_valid_workflow(workflow)` - Validate workflow existence

2. **ingest.py** - Enhanced to support selective ingestion
   - `ingest_documents(workflow_filter="")` - Ingest documents optionally filtered by workflow tag
   - `load_documents(workflow_filter="")` - Load and filter documents by workflow
   - Maintains backward compatibility with full ingestion

3. **app.py** - New API endpoints for workflow management
   - `GET /api/workflows` - List all available workflows
   - `GET /api/workflows/<workflow_name>/files` - Get files for a workflow
   - `POST /api/workflows/select` - Select and ingest a workflow
   - `GET /api/workflow/status` - Check current workflow status

---

## System Architecture

### Core Components

- **Flask Web Server** (`app.py`) - REST API and HTML serving
- **RAG Engine** (`chatbot.py`) - Query routing, retrieval, LLM integration
- **Document Indexing** (`ingest.py`) - PDF/text chunking and embedding
- **Memory System** (`memory_store.py`, `conversation_memory.py`) - Conversation history
- **Workflow Management** (`workflow_manager.py`) - Tag-based document organization

### Data Flow

```
1. User selects workflow → Select API endpoint
   ↓
2. Filter documents by tag → ingest_documents(workflow_filter)
   ↓
3. Chunk & embed documents → FAISS index + chunks.jsonl
   ↓
4. User queries → Retrieve relevant chunks + conversation memory
   ↓
5. LLM generates answer → Store in memory, update active sources
   ↓
6. Response streamed to UI
```

---

## Installation & Setup

### 1. Prerequisites

- Python 3.9+
- pip package manager
- API keys for embeddings and LLM generation

### 2. Clone & Install Dependencies

```bash
cd /home/azad/luminai-documentation-rag

# Create virtual environment (optional but recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration

Create a `.env` file in the project root:

```bash
# LLM Generation Provider (gemini or openai)
GENERATION_PROVIDER=gemini

# Document Embedding Provider (gemini or openai)
DOC_EMBEDDING_PROVIDER=gemini

# Memory Embedding Provider (defaults to DOC_EMBEDDING_PROVIDER)
MEMORY_EMBEDDING_PROVIDER=gemini

# API Keys
GEMINI_API_KEY=your_gemini_api_key_here
OPENAI_API_KEY=your_openai_api_key_here  # If using OpenAI

# Optional: Session Configuration
SESSION_ID=default
ENABLE_QUERY_ROUTING_DEBUG=false
FOLLOWUP_MIN_RELEVANCE=0.35

# Optional: Retrieval Parameters
TOP_K_DOCS=6
TOP_K_MEMORY=3
RECENT_TURNS=6
SUMMARY_EVERY_N_MESSAGES=6
MAX_DOC_CONTEXT_CHARS=10000
MAX_MEMORY_CONTEXT_CHARS=4000
```

### 4. Prepare Documents

Place your documents in the `documents/` directory:

```bash
documents/
  ├── Alma RFL.pdf
  ├── Alma- Invoice Issuing.pdf
  ├── Circle Medical - Medication Refills.pdf
  └── ... (other PDFs and TXT files)
```

### 5. Tag Your Documents

Edit `document_tags.json` to map filenames to workflow tags:

```json
{
  "Alma RFL.pdf": "Alma RFL",
  "Alma- Invoice Issuing.pdf": "Alma Invoice Issuing",
  "Alma-Payment Plan Creation.pdf": "Alma Payment Plan Creation",
  "Circle Chargeback - Disputes.docx.pdf": "Circle Chargeback Disputes",
  ...
}
```

**Note:** Document filenames must match exactly, including extension and case.

---

## Usage

### Starting the Server

```bash
# Option 1: Run Flask development server
python3 app.py

# Option 2: Run with gunicorn (production)
gunicorn --workers 4 --bind 0.0.0.0:5000 app:app
```

The chatbot will be available at: **http://localhost:5000**

### Web Interface

#### 1. Workflow Selection (Initial Step)

When you first open the chatbot, you'll see a workflow selector:

**Steps:**
1. Click the "Workflows" tab or the workflow selector dropdown
2. Choose a workflow from the list (e.g., "Alma RFL", "Circle Medical")
3. Click "Select & Ingest"
4. Wait for the ingestion to complete (you'll see a progress message)
5. Once ready, proceed to the Chat tab

**What happens:**
- Only documents tagged with that workflow are loaded
- A FAISS vector index is built from those documents
- The chatbot is now ready to answer questions about that workflow

#### 2. Chat Tab

**Query the chatbot:**

1. Type your question in the input field
2. Press Enter or click "Send"
3. The chatbot retrieves relevant document chunks and generates an answer
4. Sources are displayed below the response

**Features:**
- **Follow-up Questions:** The chatbot remembers conversation context
- **Source Continuity:** Automatically stays within the workflow unless switching is necessary
- **Phase References:** Use follow-ups like "Tell me more", "Explain that", "What about..."

**Tag Filtering (Advanced):**
- If needed, force a specific tag in your query: `#TagName your question here`
- The chatbot will only search documents with that tag

#### 3. Documents Tab

**View and manage documents:**

1. Click "Refresh list" to update the document list
2. See all documents currently in the active workflow
3. Review which documents are available for retrieval

#### 4. Upload Tab

**Add new documents:**

1. **Drag & drop** a PDF or TXT file, or click to select
2. **Enter a tag** for the document (e.g., "Alma RFL", "Circle Medical")
3. Click **Upload** to save the file
4. Click **Chunk and Ingest** to process all pending documents
5. The chatbot index will be updated

---

## API Reference

### Workflow APIs

#### Get All Workflows
```
GET /api/workflows
```

**Response:**
```json
{
  "workflows": ["Alma RFL", "Circle Medical", "Rothman"],
  "current": "Alma RFL",
  "count": 3
}
```

#### Get Files for a Workflow
```
GET /api/workflows/Alma%20RFL/files
```

**Response:**
```json
{
  "workflow": "Alma RFL",
  "files": ["Alma RFL.pdf", "Alma- Invoice Issuing.pdf"],
  "count": 2
}
```

#### Select and Ingest a Workflow
```
POST /api/workflows/select
Content-Type: application/json

{
  "workflow": "Alma RFL"
}
```

**Response:**
```json
{
  "success": true,
  "workflow": "Alma RFL",
  "files": ["Alma RFL.pdf", "Alma- Invoice Issuing.pdf"],
  "files_count": 2,
  "chunks_count": 245,
  "message": "✓ Ingested 2 documents for workflow 'Alma RFL'"
}
```

#### Get Workflow Status
```
GET /api/workflow/status
```

**Response:**
```json
{
  "current_workflow": "Alma RFL",
  "is_ready": true,
  "files_count": 2,
  "has_index": true,
  "has_chunks": true,
  "has_llm": true
}
```

#### Query the Chatbot
```
POST /api/chat
Content-Type: application/json

{
  "query": "What are the steps for RFL?"
}
```

**Response:**
```json
{
  "answer": "Based on the Alma RFL documentation, the steps are...",
  "sources": ["Alma RFL.pdf"]
}
```

---

## Command Line Usage

### Ingest Documents for a Specific Workflow

```bash
# In Python shell or script
from ingest import ingest_documents

# Ingest all documents
result = ingest_documents()
print(result)  # {'success': True, 'chunks_count': 500, 'docs_count': 10, 'workflow': 'all'}

# Ingest specific workflow
result = ingest_documents(workflow_filter="Alma RFL")
print(result)  # {'success': True, 'chunks_count': 150, 'docs_count': 3, 'workflow': 'Alma RFL'}
```

### Chat Interface (CLI)

```bash
python3 chatbot.py
```

**Commands:**
- `:workflows` - List all available workflows
- `:select "Alma RFL"` - Select a workflow (CLI only)
- `:summary` - Show conversation summary
- `:facts` - List extracted facts
- `:session` - Show session ID
- `:sources` - Show active document sources
- `:quit` or `:exit` - Exit chatbot

**Example:**
```
Ask> :workflows
Available workflows:
- Alma RFL
- Circle Medical
- Rothman

Ask> What are the payment options?
Answer: Based on the documents, payment options include...
[Relevant sources listed]
```

---

## Project Structure

```
luminai-documentation-rag/
├── app.py                          # Flask web server & API endpoints
├── chatbot.py                      # RAG engine & query routing
├── ingest.py                       # Document chunking & indexing
├── workflow_manager.py             # NEW: Workflow/tag management
├── conversation_memory.py          # Memory embeddings & search
├── memory_store.py                 # SQLite conversation storage
├── reindex_memory.py               # Memory index rebuild utility
├── templates/
│   └── index.html                  # Web UI
├── documents/                      # User-uploaded PDFs & TXTs
├── index/
│   ├── faiss.index                 # Vector search index
│   └── chunks.jsonl                # Document chunks metadata
├── memory_index/
│   ├── memory.faiss                # Conversation memory index
│   └── memory_chunks.jsonl         # Message metadata
├── document_tags.json              # Filename → workflow mapping
├── active_sources.json             # Session state & active workflow
├── session.db                      # SQLite message history
├── requirements.txt                # Python dependencies
└── README.md                       # This file
```

---

## Features

### Smart Query Routing
- Automatically detects follow-up questions
- Maintains context across multiple turns
- Intelligently switches document sets when necessary
- Falls back to heuristics if LLM routing fails

### Conversation Memory
- Stores all messages in SQLite
- Embeds messages for semantic search
- Retrieves relevant prior context for each query
- Periodic extraction of key facts
- Automatic conversation summarization

### Document Management
- Tag-based organization of documents
- Selective ingestion by workflow
- Batch embedding for efficiency
- FAISS vector indexing for fast retrieval
- Metadata tracking (source, tag, chunk ID)

### Multi-Provider Support
- Gemini (default) or OpenAI for LLM generation
- Gemini (default) or OpenAI for embeddings
- Flexible configuration via environment variables

---

## Troubleshooting

### "Index or model not available" Error
**Solution:** 
- Select a workflow first using the workflow selector
- Or run ingestion: `python3 ingest.py`

### "Missing GEMINI_API_KEY" Error
**Solution:**
- Add your API key to `.env` file
- Or set environment variable: `export GEMINI_API_KEY=your_key`

### Slow Embedding
**Solution:**
- This is normal for first ingestion (building embeddings from scratch)
- Subsequent queries will be faster (cached embeddings)
- For large workflows, consider batching uploads

### Memory Index Dimension Mismatch
**Solution:**
```bash
# Rebuild memory index
python3 reindex_memory.py
```

### Missing Documents in Workflow
**Solution:**
- Check `document_tags.json` for exact filename matching
- Verify files are in `documents/` directory
- Refresh the page and re-select the workflow

---

## Performance Optimization

### Embedding Batch Size
The system embeds documents in batches of 64. For very large workflows (1000+ documents), you may need to:
- Reduce batch size in `ingest.py`
- Or split workflow into smaller sub-workflows with separate tags

### Memory Cleanup
After many conversations, the memory database grows. To clean up:
```bash
rm session.db
python3 reindex_memory.py
```

### Index Rebuild
To optimize FAISS index performance:
```bash
python3 ingest.py  # or ingest for specific workflow
```

---

## Development

### Adding New Document Types

Edit `ingest.py` to add support for new file types:

```python
def load_documents(workflow_filter: str = ""):
    # ... existing code ...
    
    if name.lower().endswith(".docx"):
        docs.append({"source": name, "text": read_docx(path), "tag": doc_tag})
    
def read_docx(path: str) -> str:
    # Implement DOCX reading logic
    pass
```

### Customizing Prompt Templates

Edit `chatbot.py` functions:
- `build_answer_prompt()` - Main response prompt
- `build_summary_prompt()` - Summarization prompt
- `build_query_router_prompt()` - Query routing logic

### Extending Memory Features

Edit `memory_store.py` to add new storage:
```python
def _init_db(self):
    # Add new table in CREATE TABLE section
    conn.execute("""
        CREATE TABLE IF NOT EXISTS custom_data (
            ...
        )
    """)
```

---

## License & Attribution

This project uses:
- **FAISS** - Facebook AI Similarity Search
- **Gemini/OpenAI** - LLM APIs
- **Flask** - Web framework
- **PyPDF** - PDF text extraction

---

## Support

For issues or questions:
1. Check the Troubleshooting section
2. Review the API Reference
3. Check console output for error messages
4. Enable debug mode: `ENABLE_QUERY_ROUTING_DEBUG=true` in `.env`

---

**Last Updated:** April 7, 2026  
**Version:** 2.0 (Workflow Selection Feature)
