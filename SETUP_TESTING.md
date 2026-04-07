# Workflow Selector - Setup & Testing Guide

## Quick Start

### 1. Start the Server

```bash
cd /home/azad/luminai-documentation-rag
python3 app.py
```

**Expected output:**
```
 * Serving Flask app 'app'
 * Debug mode: off
 * Running on http://127.0.0.1:5000
```

### 2. Open in Browser

Visit: **http://localhost:5000**

### 3. Expected First Screen

You should see a centered card with:
- Title: "Select a Workflow"
- Dropdown: (populated with workflow names)
- Button: "Select & Ingest" (disabled until selection)

---

## Complete User Journey

### Step 1: Workflow Selection Screen
```
Screen loads → 
  Shows "Select a Workflow" card
  Dropdown populated with 50+ workflows
  Button disabled (greyed out)
```

### Step 2: Select a Workflow
```
User actions:
  1. Click dropdown
  2. Select "Alma RFL" (or any workflow)
  
Expected:
  - Button becomes enabled (turns green)
  - Can click or press Enter
```

### Step 3: Ingestion Process
```
User clicks "Select & Ingest"
  ↓
Spinner appears with "Ingesting documents..."
  ↓
Backend processes:
  - Loads documents tagged "Alma RFL"
  - Chunks documents
  - Embeds with Gemini/OpenAI
  - Builds FAISS index
  ↓
Complete (1-5 seconds typical)
  ↓
Success message: "✓ Ingested X chunks from Y documents"
```

### Step 4: Chat Interface Appears
```
After 1.5 seconds:
  - Workflow selector disappears
  - Chat tabs appear (Chat, Documents, Upload)
  - Chat conversation area shows (empty)
  - Query input field is visible and focused
  
User can now type and ask questions
```

---

## System Requirements Verification

### Check Python Version
```bash
python3 --version
# Expected: Python 3.9 or higher
```

### Check Dependencies
```bash
pip list | grep -E "flask|faiss|google-genai|openai|pypdf"
```

**Expected output:**
```
faiss-cpu
google-genai
openai
pypdf
flask
```

### Check Environment Variables
```bash
echo $GEMINI_API_KEY
# Should output your API key (masked in console is fine)
```

### Check Key Files Exist
```bash
ls -1 | grep -E "document_tags.json|templates/index.html|workflow_manager.py"
```

**Expected:**
```
document_tags.json
workflow_manager.py
templates/
```

---

## API Testing (cURL Commands)

### Test 1: Get Workflows
```bash
curl http://localhost:5000/api/workflows | python3 -m json.tool
```

**Expected response:**
```json
{
  "count": 50,
  "current": "",
  "workflows": [
    "Alma - Member Lifecycle Rebuild",
    "Circle Medical - Email Queue",
    ...
  ]
}
```

### Test 2: Get Files for Workflow
```bash
curl "http://localhost:5000/api/workflows/Alma%20RFL/files" | python3 -m json.tool
```

**Expected response:**
```json
{
  "count": 2,
  "files": [
    "Alma RFL.pdf",
    "Alma- Invoice Issuing.pdf"
  ],
  "workflow": "Alma RFL"
}
```

### Test 3: Select Workflow (Full Test)
```bash
curl -X POST http://localhost:5000/api/workflows/select \
  -H "Content-Type: application/json" \
  -d '{"workflow": "Alma RFL"}' | python3 -m json.tool
```

**Expected response:**
```json
{
  "chunks_count": 150,
  "files": ["Alma RFL.pdf", "..."],
  "files_count": 2,
  "message": "✓ Ingested 2 documents for workflow 'Alma RFL'",
  "success": true,
  "workflow": "Alma RFL"
}
```

### Test 4: Check Status
```bash
curl http://localhost:5000/api/workflow/status | python3 -m json.tool
```

**Expected response:**
```json
{
  "current_workflow": "Alma RFL",
  "files_count": 2,
  "has_chunks": true,
  "has_index": true,
  "has_llm": true,
  "is_ready": true
}
```

---

## Browser Console Testing (F12 → Console Tab)

### Check Workflows Loaded
```javascript
document.getElementById('workflow-dropdown').options.length
// Should show: 51 (50 workflows + 1 placeholder)
```

### Manually Trigger workflow Load
```javascript
loadWorkflows()
// Check console for: "Loaded 50 workflows"
```

### Check Current Workflow State
```javascript
document.getElementById('workflow-selector').classList.contains('workflow-selector-hidden')
// Should show: false (selector is visible initially)

document.getElementById('main-content').classList.contains('hidden')
// Should show: true (chat is hidden initially)
```

### Simulate Selection
```javascript
document.getElementById('workflow-dropdown').value = 'Alma RFL'
selectWorkflow()
// Watch as:
// 1. Loading spinner appears
// 2. Request is sent to backend
// 3. Success message appears
// 4. UI transitions to chat interface
```

---

## Error Cases & Solutions

### Case 1: No Workflows in Dropdown
**Symptom:** Dropdown shows only "-- Loading workflows --"
**Causes:**
- document_tags.json missing or empty
- /api/workflows endpoint failing
- Network error

**Fix:**
```bash
# Check if document_tags.json exists and has content
cat document_tags.json | head -20

# If empty, check file in documents/
ls documents/ | head -10
```

### Case 2: "Select & Ingest" Button Stays Disabled
**Symptom:** Button greyed out, can't select
**Causes:**
- No workflows loaded
- JavaScript error
- API call failed

**Fix:**
```javascript
// In console, check:
document.getElementById('workflow-select-btn').disabled
// Should be false if workflows exist

// Manually enable and try:
document.getElementById('workflow-select-btn').disabled = false
```

### Case 3: Loading Spinner Doesn't Start
**Symptom:** Click button, nothing happens
**Causes:**
- JavaScript error
- Button click not firing

**Fix:**
```javascript
// In console:
selectWorkflow()
// Should log errors if any

// Check network tab (F12 → Network) for POST request
// Should see /api/workflows/select request
```

### Case 4: Ingestion Fails (Red Error Message)
**Symptom:** "Failed to ingest workflow" error shown
**Causes:**
- Documents don't exist
- FAISS index write failed
- Embedding API failed

**Fix:**
```bash
# Check backend console for detailed error
# Look for lines like:
# "Error: [specific error message]"

# Try direct API call:
curl -X POST http://localhost:5000/api/workflows/select \
  -H "Content-Type: application/json" \
  -d '{"workflow": "Alma RFL"}' \
  2>&1
```

### Case 5: Chat Interface Doesn't Appear
**Symptom:** Ingestion succeeds, but no chat
**Causes:**
- CSS visibility issue
- JavaScript error on transition
- Timing issue

**Fix:**
```javascript
// In console, manually show chat:
document.getElementById('main-content').classList.remove('hidden')
document.getElementById('workflow-selector').classList.add('workflow-selector-hidden')

// Try asking a question - see if chat works
```

---

## Performance Benchmarks

### Expected Times (First Selection)
```
Load page:           ~500ms
Load workflows:      ~100ms
Select workflow:     ~2000-5000ms total:
  - Network:        ~200ms
  - Embedding:      ~1500-4000ms (depends on doc size)
  - FAISS build:    ~300ms
  - Response:       ~100ms
```

### Expected Times (Subsequent Queries)
```
Submit query:        ~2000-3000ms total:
  - Network:        ~100ms
  - Query time:     ~1900-2900ms:
    - Embed query:  ~200ms
    - Search FAISS: ~50ms
    - LLM generate: ~1650-2650ms
```

---

## Logs & Debugging

### Enable Debug Mode
```bash
export FLASK_ENV=development
export FLASK_DEBUG=1
python3 app.py
```

### Check Flask Logs
```
INFO - Listening on http://127.0.0.1:5000
POST /api/workflows/select - 200 OK
```

### Enable Query Routing Debug
```bash
export ENABLE_QUERY_ROUTING_DEBUG=true
python3 app.py
```

### Check Ingestion Logs
```bash
# In another terminal, watch for ingestion messages
# Look for output like:
# "Processing 150 chunks from 2 documents..."
# "Embedding batch 1/3..."
# "✓ Indexed 150 chunks from 2 documents."
```

---

## Common Questions

### Q: How do I switch workflows?
**A:** Refresh the page and select a different workflow from the dropdown.

### Q: Why does ingestion take so long?
**A:** First-time embedding generation takes time. Subsequent queries use cached embeddings.

### Q: Can I skip the workflow selector?
**A:** Not currently - it's required to scope queries to specific documents.

### Q: What if I don't have a workflow_tags.json?
**A:** The API will still work but show no workflows. Populate document_tags.json first.

### Q: Can I cancel ingestion?
**A:** Currently no - let it complete. You can refresh page to restart.

---

## Verification Checklist

Run through these to verify everything works:

- [ ] Server starts without errors: `python3 app.py`
- [ ] Workflow selector appears on page load
- [ ] Dropdown has 50+ workflows
- [ ] Button is disabled initially
- [ ] Selecting workflow enables button
- [ ] Click loads spinner
- [ ] Ingestion completes (1-5 sec)
- [ ] Success message shows chunk count
- [ ] Chat interface appears
- [ ] Input field is focused (cursor visible)
- [ ] Can type in chat box
- [ ] Can send query and get response
- [ ] Query references correct documents

---

## Support & Troubleshooting

### Get Detailed Logs
```bash
python3 app.py 2>&1 | tee chatbot.log
# Opens two terminals:
# 1. Run above command
# 2. Run: tail -f chatbot.log
```

### Test in Incognito Mode
```
If you get cache issues, open incognito/private browser window
This bypasses cached HTML/CSS/JS
```

### Reset Everything
```bash
# Clear cache and restart
rm -f active_sources.json session.db
rm -rf index/ memory_index/
python3 app.py
```

---

## Next Steps

After verification:
1. ✅ Share with team for testing
2. ✅ Gather feedback on UI/UX
3. ✅ Make adjustments as needed
4. ✅ Deploy to production

---

**Version:** 2.0  
**Last Updated:** April 7, 2026  
**Status:** Ready for Testing ✓
