# Workflow Selection Feature - Quick Reference

## What Changed?

You can now select a **workflow** (document tag) before querying the chatbot. Only documents tagged with that workflow will be indexed and searchable.

---

## Quick Start

### 1. Start the Server
```bash
python3 app.py
```
Open [http://localhost:5000](http://localhost:5000)

### 2. Select a Workflow
- Look for the workflow selector (UI to be added)
- Or use API: `POST /api/workflows/select`
- Available workflows are extracted from `document_tags.json`

### 3. Query
- Chat with documents from that workflow only
- Switch workflows anytime

---

## New API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/workflows` | GET | List all workflows |
| `/api/workflows/<name>/files` | GET | Get files in a workflow |
| `/api/workflows/select` | POST | Select & ingest a workflow |
| `/api/workflow/status` | GET | Check current workflow status |

---

## How Workflows Work

### Before
```
All documents ingested → FAISS contains 48 documents → Tag filtering via #tag
```

### After
```
User selects workflow → Only matching documents ingested → FAISS optimized → Faster queries
```

---

## Setting Up Workflows

### File: `document_tags.json`

Maps document filenames to workflow tags:

```json
{
  "Alma RFL.pdf": "Alma RFL",
  "Alma- Invoice Issuing.pdf": "Alma Invoice Issuing",
  "Circle Medical - Medication Refills.pdf": "Circle Medical",
  "Circle Medical - Email Queue.docx.pdf": "Circle Medical"
}
```

**Rules:**
- Key = exact filename (case-sensitive)
- Value = workflow/tag name
- Documents with same tag = same workflow
- Different tags = different workflows

---

## Implementation Details

### New Files

**`workflow_manager.py`**
```python
from workflow_manager import WorkflowManager

wm = WorkflowManager()

# Get all workflows
workflows = wm.get_all_workflows()
# → ['Alma Invoice Issuing', 'Alma RFL', 'Circle Medical', ...]

# Get files for a workflow
files = wm.get_files_for_workflow('Alma RFL')
# → ['Alma RFL.pdf', 'Alma- Invoice Issuing.pdf']

# Validate workflow
if wm.is_valid_workflow('Alma RFL'):
    print("Valid workflow")
```

### Modified Files

**`ingest.py`**
```python
from ingest import ingest_documents

# Ingest all documents (backward compatible)
result = ingest_documents()

# Ingest specific workflow (NEW)
result = ingest_documents(workflow_filter="Alma RFL")
# → {'success': True, 'chunks_count': 150, 'docs_count': 2, 'workflow': 'Alma RFL'}
```

**`app.py`**
- Added 4 new API endpoints
- Integrated WorkflowManager
- Workflow ingestion on select

**`chatbot.py`**
- No changes (uses session tags transparently)

---

## Usage Scenarios

### Scenario 1: Single Workflow per Session
```
1. User selects "Alma RFL"
2. Only Alma docs ingested
3. All queries search Alma docs
4. Can switch workflows anytime
```

### Scenario 2: API Integration
```python
import requests

# Get workflows
workflows = requests.get('http://localhost:5000/api/workflows').json()

# Select one
result = requests.post('http://localhost:5000/api/workflows/select', 
                       json={'workflow': 'Alma RFL'})

# Query
answer = requests.post('http://localhost:5000/api/chat',
                       json={'query': 'What are payment plans?'}).json()
```

### Scenario 3: Multi-Tenant System
```
# Each user session has own active workflow
User A: Alma RFL selected
User B: Circle Medical selected
User C: Rothman selected
# Each scoped to their workflow
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Unknown workflow" error | Check `document_tags.json` for exact tag name |
| No documents loading | Ensure filenames in `document_tags.json` exist in `documents/` folder |
| Slow ingestion | Normal for first run; subsequent queries are fast |
| Index not updating | Refresh page after selecting workflow |
| API returns 404 | Workflow name is case-sensitive; must match exactly |

---

## Advanced: CLI Usage

```bash
# Select and ingest a workflow programmatically
python3 -c "
from ingest import ingest_documents
result = ingest_documents(workflow_filter='Circle Medical')
print(f'Ingested {result[\"chunks_count\"]} chunks')
"
```

```bash
# List all workflows
python3 -c "
from workflow_manager import WorkflowManager
wm = WorkflowManager()
for wf in wm.get_all_workflows():
    files = wm.get_files_for_workflow(wf)
    print(f'{wf}: {len(files)} files')
"
```

---

## Files Reference

| File | Purpose | Status |
|------|---------|--------|
| `workflow_manager.py` | Workflow management | ✅ Created |
| `ingest.py` | Updated for selective ingestion | ✅ Modified |
| `app.py` | New API endpoints | ✅ Modified |
| `chatbot.py` | Uses sessions transparently | ✅ Compatible |
| `templates/index.html` | UI selector (frontend ready) | ⏳ To be added |

---

## Performance Tips

1. **Smaller Workflows** = Faster queries
   - Split large workflows into sub-workflows if needed
   
2. **Batch Operations** = Faster ingestion
   - Upload multiple files, then ingest once

3. **Caching** = Faster retrieval
   - FAISS indices are cached; re-selection rebuilds

4. **API Rate Limits** = Consider batching
   - Embedding API has rate limits; batch size 64 by default

---

## Next: Frontend Integration

To add workflow selection to the UI:

```javascript
// Fetch workflows
fetch('/api/workflows')
  .then(r => r.json())
  .then(data => {
    // Display dropdown with data.workflows
  });

// On workflow selection
fetch('/api/workflows/select', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({workflow: selectedWorkflow})
})
  .then(r => r.json())
  .then(result => {
    if (result.success) {
      console.log(`Ingested ${result.chunks_count} chunks`);
      // Enable chat
    }
  });

// Check status
fetch('/api/workflow/status')
  .then(r => r.json())
  .then(status => {
    console.log(`Current: ${status.current_workflow}, Ready: ${status.is_ready}`);
  });
```

---

## Questions?

Refer to:
- **Full Setup:** `README.md`
- **API Details:** `README.md` (API Reference section)
- **Technical Changes:** `CHANGELOG.md`
- **Code:** `workflow_manager.py`, `ingest.py`, `app.py`

