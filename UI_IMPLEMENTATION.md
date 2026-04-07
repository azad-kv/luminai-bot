# Workflow Selector UI - Implementation Guide

## What's New

The chatbot UI now displays a **Workflow Selector** as the first screen before users can access the chat interface.

### User Flow

```
1. User visits http://localhost:5000
   ↓
2. Page loads → Workflow selector screen appears
   ↓
3. Dropdown shows all available workflows from document_tags.json
   ↓
4. User selects a workflow (e.g., "Alma RFL")
   ↓
5. User clicks "Select & Ingest" button
   ↓
6. Loading spinner shows "Ingesting documents..."
   ↓
7. Backend ingests only docs tagged with "Alma RFL"
   ↓
8. Success message: "✓ Ingested X chunks from Y documents"
   ↓
9. Workflow selector disappears → Chat interface appears
   ↓
10. User can now ask questions about that workflow's documents
```

---

## UI Components

### Workflow Selector Screen (Initial)

**Location:** Center of screen before tabs appear

**Elements:**
- Title: "Select a Workflow"
- Subtitle: "Choose a workflow to get started with the chatbot"
- Dropdown: Shows all available workflows
- Button: "Select & Ingest" (disabled until workflow selected)
- Loading indicator: Spinner + text (hidden until selection)
- Error message area: Shows any ingestion errors
- Success message area: Shows confirmation after ingestion

**Styling:**
- Dark theme matching rest of UI
- Gradient background
- Rounded card container
- Green accent colors (#10a37f)

### Chat Interface (After Selection)

**When Introduced:** After workflow ingestion completes

**Elements:**
- Tabs: Chat, Documents, Upload (all tabs now available)
- Chat area: Conversation history
- Query input: Text field for questions
- Send button: Trigger query

---

## Features

### 1. Workflow Discovery
```
On page load:
  → Fetch /api/workflows
  → Parse response.workflows array
  → Populate dropdown
```

### 2. Dropdown Selection
```
When user selects from dropdown:
  → "Select & Ingest" button becomes enabled
  → User can press Enter or click button
```

### 3. Ingestion Process
```
When "Select & Ingest" clicked:
  → Show loading spinner
  → Disable dropdown and button
  → POST /api/workflows/select with selected workflow
  → Wait for response
  → If success:
    - Show success message (1.5 seconds)
    - Hide workflow selector
    - Show chat interface
  → If error:
    - Show error message
    - Re-enable controls
```

### 4. Error Handling
```
Errors include:
  - No workflows available
  - Network errors during load
  - Invalid workflow selection
  - Ingestion failures
  
Each displays in .workflow-error div with red styling
```

---

## Backend Endpoints Used

### GET /api/workflows
Returns list of all available workflows

**Response:**
```json
{
  "workflows": ["Alma RFL", "Circle Medical", "Rothman"],
  "current": "",
  "count": 3
}
```

### POST /api/workflows/select
Ingests documents for selected workflow

**Request:**
```json
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
  "chunks_count": 150,
  "message": "✓ Ingested 2 documents for workflow 'Alma RFL'"
}
```

---

## Testing

### Local Testing

1. **Start the server:**
   ```bash
   python3 app.py
   ```

2. **Open browser:**
   Visit `http://localhost:5000`

3. **Expected behavior:**
   - Workflow selector screen appears (not tabs)
   - Dropdown shows workflows (e.g., "Alma RFL", "Circle Medical")
   - Button is disabled until workflow selected

4. **Select a workflow:**
   - Click dropdown
   - Select "Alma RFL" (or any workflow)
   - Button becomes enabled
   - Click "Select & Ingest"
   - Loading spinner appears (1-3 seconds depending on documents)
   - Success message shown
   - Chat interface appears
   - Query input is focused (ready to type)

5. **Verify ingestion:**
   - Server logs show ingestion progress
   - FAISS index is rebuilt with only selected workflow's docs
   - Chunks count matches message

### Debugging

**Enable Chrome DevTools Console (F12):**

```javascript
// Check if workflows loaded
console.log(document.getElementById('workflow-dropdown').options);

// Manually select a workflow
document.getElementById('workflow-dropdown').value = 'Alma RFL';
selectWorkflow();

// Check current state
document.getElementById('workflow-selector').classList;
document.getElementById('main-content').classList;
```

**Server logs:**

```bash
# Watch ingestion progress
tail -f output.log | grep "Ingesting\|Embedding\|Saved"
```

---

## CSS Classes

### Visibility Control
- `.workflow-selector-hidden` - Hides workflow selector
- `.hidden` - Hides main content (chat interface)

### Loading State
- `.spinner` - Rotating animation
- `#loading-indicator` - Container with spinner + text

### Messages
- `.workflow-error` - Red error box
- `.workflow-info` - Green success box

---

## JavaScript Functions

### Main Functions

**`loadWorkflows()`**
- Calls GET /api/workflows
- Populates dropdown with workflow names
- Enables button if workflows exist

**`selectWorkflow()`**
- Validates workflow selection
- Shows loading spinner
- Calls POST /api/workflows/select
- On success: hides selectorand shows chat
- On error: shows error message

**`showWorkflowError(message)`**
- Displays error in red box
- Auto-called on failures

**`showWorkflowInfo(message)`**
- Displays info in green box
- Shows after successful ingestion

### Helper Functions

**`hideWorkflowError()` / `hideWorkflowInfo()`**
- Clears error/info messages

---

## User Experience Enhancements

### Current
- ✅ Workflow selector appears first
- ✅ Visual feedback (spinner during ingestion)
- ✅ Success/error messages
- ✅ Button state management
- ✅ Keyboard support (Enter key)

### Possible Future Enhancements
- [ ] Progress bar showing embedding progress
- [ ] File browser showing which files will be ingested
- [ ] Workflow descriptions/metadata
- [ ] Recently used workflows
- [ ] Workflow switching without page reload
- [ ] Preview of workflow documents

---

## Troubleshooting

### Dropdown is empty
**Problem:** No workflows appear in dropdown
**Solution:**
1. Check `document_tags.json` exists
2. Ensure it has entries: `{"filename.pdf": "Workflow Name"}`
3. Check that filename matches actual file in `documents/`
4. Refresh page

### Button stays disabled
**Problem:** "Select & Ingest" button won't enable
**Solution:**
1. Open DevTools Console (F12)
2. Check: `document.getElementById('workflow-dropdown').value`
3. Ensure dropdown value is set: `document.getElementById('workflow-dropdown').value = 'Alma RFL'`
4. Check server logs for API errors

### Ingestion hangs
**Problem:** Loading spinner doesn't go away
**Solution:**
1. Check backend console for errors
2. Check network tab in DevTools (F12) for failed requests
3. Try refreshing page
4. Check document embedding service (Gemini/OpenAI) credentials

### Chat doesn't appear after ingestion
**Problem:** Workflow selector hidden but chat not shown
**Solution:**
1. Check DevTools Console for JavaScript errors
2. Scroll page (chat interface might be below fold)
3. Check: `document.getElementById('main-content').classList`
4. Manually show: `document.getElementById('main-content').classList.remove('hidden')`

---

## Implementation Files

### Modified Files

**`templates/index.html`**
- Added `#workflow-selector` div
- Added workflow selector styles
- Added `loadWorkflows()`, `selectWorkflow()`, error/info display functions
- Updated window.onload to initialize workflow selector
- Added DOMContentLoaded listener for dropdown events

**`app.py`**
- Added WorkflowManager import
- Added 4 new API endpoints:
  - GET /api/workflows
  - GET /api/workflows/<name>/files
  - POST /api/workflows/select
  - GET /api/workflow/status

**`workflow_manager.py`**
- Created new module for workflow management

**`ingest.py`**
- Added `ingest_documents(workflow_filter="")` function
- Made ingestion callable from API

### Unchanged Files
- `chatbot.py` - Works transparently with session tags
- All other files - No changes needed

---

## Architecture

```
User visits /
    ↓
HTML loads → window.onload fires
    ↓
loadWorkflows() called
    ↓
GET /api/workflows
    ↓
Populate dropdown, enable button
    ↓
User selects workflow
    ↓
selectWorkflow() called
    ↓
POST /api/workflows/select {workflow: "..."}
    ↓
app.py calls ingest.ingest_documents(workflow_filter)
    ↓
Rebuilds FAISS index with filtered documents
    ↓
Returns success response
    ↓
JavaScript hides workflow-selector, shows main-content
    ↓
Chat interface ready
```

---

## Performance Considerations

### First Load Time
- Workflow list fetch: ~100ms
- No ingestion happens on load (lazy)

### Workflow Selection Time
- Network request: ~200ms
- Document ingestion: 1-5 seconds (depends on document count and size)
- In-memory operations: <50ms

### Subsequent Queries
- FAISS search: ~100ms (fast - only selected workflow docs)
- LLM generation: 1-3 seconds (depends on token count)

---

## Deployment

### Production Checklist
- [ ] document_tags.json populated with all documents
- [ ] Documents in `documents/` folder match tags.json
- [ ] ENV variables set (GEMINI_API_KEY, etc.)
- [ ] Test workflow selection end-to-end
- [ ] Test error cases (invalid workflow, missing docs)
- [ ] SSL certificates configured (if using HTTPS)
- [ ] CORS headers configured (if cross-origin)

### Load Testing
```bash
# Test concurrent workflow selections
ab -n 100 -c 10 -p '{"workflow":"Alma RFL"}' \
   -T application/json \
   http://localhost:5000/api/workflows/select
```

---

## Version

**UI Version:** 2.0  
**Date:** April 7, 2026  
**Status:** Complete & Ready for Production
