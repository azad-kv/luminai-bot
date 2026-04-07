# Testing Markdown & Streaming Feature

## Quick Start
1. Start the server:
   ```bash
   python3 app.py
   ```

2. Open browser to `http://localhost:5000`

3. Select a workflow and ingest documents

## What to Look For

### Streaming Behavior
- **Messages appear incrementally** - You should see text appearing word-by-word/chunk-by-chunk rather than all at once
- **Auto-scroll** - The conversation automatically scrolls down as new content arrives

### Markdown Formatting Examples
To test markdown support, the LLM response should include markdown. Look for:

#### Headers
```
# Main Header
## Sub Header
### Smaller Header
```
Should display with appropriate font sizes and weights.

#### Bold & Italic
```
**This is bold** and *this is italic*
```

#### Code Inline
```
Use the `print()` function to output.
```
Should show with background color.

#### Code Blocks
```
Here's a Python example:
```python
def hello():
    print("Hello, World!")
```
```
Should display with background and monospace font.

#### Lists
```
Benefits:
- Item 1
- Item 2
- Item 3

Steps:
1. First
2. Second
3. Third
```

#### Blockquotes
```
> This is a blockquote
> It can span multiple lines
```

#### Links
```
Visit [OpenAI](https://openai.com) for more info.
```
Should be clickable and styled in green.

#### Tables
```
| Name | Value |
|------|-------|
| A    | 100   |
| B    | 200   |
```

## Technical Details

### SSE Stream Format
Each chunk arrives as:
```
data: {"chunk": "some text here"}

```

### Frontend Processing
1. EventSource not used (using Fetch API)
2. Manual SSE parsing with line-based detection
3. Chunks accumulated into complete response
4. Markdown rendered with `marked.parse()`

### Chunk Size
- Default: 50 characters per chunk
- This creates smooth streaming while keeping network efficient
- Adjust `chunk_size = 50` in `app.py` line ~310 if desired

## Troubleshooting

### Text appears all at once
- Clear browser cache (Ctrl+Shift+Delete)
- Ensure server was restarted after code changes
- Check browser console for errors (F12)

### Markdown not rendering
- Check marked.js loaded in Network tab (F12)
- Verify MDN content includes markdown syntax
- Check browser console for parsing errors

### Streaming stops midway
- Check server console for errors
- Verify network is stable
- Try shorter query to reduce response size

### Styling looks off
- CSS rules may need `!important` if conflicting with other styles
- Check `.bubble` class CSS in DevTools
- Clear cache and hard refresh (Ctrl+F5)

## CSS Customization

To adjust markdown styling, edit the `.bubble` classes in `templates/index.html`:

```css
.bubble code {
  background: rgba(0, 0, 0, 0.2);  /* Change code bg color */
  padding: 2px 4px;
  border-radius: 3px;
  font-family: 'Courier New', monospace;
  font-size: 0.9em;
}

.bubble pre {
  background: rgba(0, 0, 0, 0.3);  /* Change code block bg */
  padding: 10px;
  border-radius: 5px;
  overflow-x: auto;
}
```

## Performance Notes
- Streaming provides immediate visual feedback
- Markdown parsing happens in browser (very fast for typical responses)
- No external API calls for markdown rendering
- Works offline for markdown (requires marked.js CDN)

## Browser Compatibility
- Chrome/Edge: ✓ Full support
- Firefox: ✓ Full support  
- Safari: ✓ Full support (iOS 13+)
- IE11: ✗ Not supported (Fetch API required)
