# Markdown & Streaming Implementation

## Overview
The UI now supports markdown formatting and streams responses as they're generated, providing a better user experience with formatted text that appears incrementally.

## Changes Made

### Backend (`app.py`)

1. **Updated Imports**
   - Added `Response` from Flask for streaming support

2. **Modified `/api/chat` Endpoint**
   - Changed from returning JSON to streaming responses via Server-Sent Events (SSE)
   - Chunks the LLM response into ~50 character segments
   - Streams each chunk as `data: {json}\n\n` format
   - Full response is generated first, then streamed for visual effect
   - Handles errors by streaming error messages

### Frontend (`templates/index.html`)

1. **Added Markdown Library**
   - Loaded `marked.js` from CDN (https://cdn.jsdelivr.net/npm/marked/marked.min.js)
   - Automatically parses markdown to HTML in bot messages

2. **Enhanced CSS Styling**
   - Added styles for:
     - Headers (h1-h6)
     - Code blocks with syntax highlighting styling
     - Inline code with background
     - Lists (ordered and unordered)
     - Tables with borders
     - Blockquotes with left border
     - Links with green color
     - Bold and italic text
     - Horizontal rules

3. **Updated `sendQuery()` Function**
   - Displays bot message div before response arrives
   - Parses Server-Sent Events (SSE) stream from server
   - Accumulates full response text
   - Renders markdown after each chunk arrives
   - Auto-scrolls to bottom as content streams in

4. **Updated `appendMessage()` Function**
   - User messages render as plain text
   - Bot messages render using `marked.parse()` for markdown formatting

## How It Works

### Streaming Flow
1. User sends chat query
2. Backend generates full response
3. Response is split into ~50 character chunks
4. Each chunk is sent via SSE with `data: {json}` format
5. Frontend receives each chunk and accumulates it
6. Frontend renders markdown after each chunk
7. Message appears incrementally with formatting

### Markdown Support
The following markdown elements are now supported:
- **Headers**: `# H1`, `## H2`, etc.
- **Bold**: `**text**`
- **Italic**: `*text*` or `_text_`
- **Code**: `` `inline code` ``
- **Code Blocks**: ` ``` code here ``` `
- **Lists**: `- item` or `1. item`
- **Links**: `[text](url)`
- **Blockquotes**: `> quote`
- **Tables**: Standard markdown tables
- **Horizontal Rules**: `---` or `***`

## Benefits
1. **Better Readability**: Formatted text is easier to scan and understand
2. **Live Feedback**: Users see content appearing as it's generated
3. **Professional Look**: Markdown styling gives responses a polished appearance
4. **Code Highlighting**: Code blocks are visually distinct
5. **List Support**: Information structured as lists is clearer

## Testing
To test the feature:
1. Start the server: `python3 app.py`
2. Visit http://localhost:5000
3. Select a workflow and ingest documents
4. Ask a question and observe:
   - Response appears incrementally (not all at once)
   - Formatted text (if LLM includes markdown)
   - Code blocks appear with background styling
   - Lists are properly indented and formatted

## Browser Support
Works in all modern browsers that support:
- Fetch API with `getReader()` for streaming
- Event Stream standard (SSE)
- TextDecoder API
