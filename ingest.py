import os, json
import numpy as np
import faiss
from dotenv import load_dotenv
from pypdf import PdfReader
from google import genai

load_dotenv()

DOCS_DIR = "documents"
INDEX_DIR = "index"
INDEX_PATH = os.path.join(INDEX_DIR, "faiss.index")
CHUNKS_PATH = os.path.join(INDEX_DIR, "chunks.jsonl")
TAGS_PATH = "document_tags.json"


def load_tags() -> dict[str, str]:
    if not os.path.exists(TAGS_PATH):
        return {}
    with open(TAGS_PATH, "r", encoding="utf-8") as f:
        return json.load(f) or {}


def save_tags(tags: dict[str, str]) -> None:
    with open(TAGS_PATH, "w", encoding="utf-8") as f:
        json.dump(tags, f, ensure_ascii=False, indent=2)

EMBED_MODEL = "gemini-embedding-001"  # official embeddings example model :contentReference[oaicite:4]{index=4}

def read_txt(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def read_pdf(path: str) -> str:
    reader = PdfReader(path)
    parts = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            parts.append(f"[page {i+1}]\n{text}")
    return "\n\n".join(parts)

def load_documents(workflow_filter: str = ""):
    """Load documents, optionally filtered by workflow tag.
    
    Args:
        workflow_filter: If not empty, only load documents with this tag.
    
    Returns:
        List of documents with source, text, and tag keys.
    """
    tags = load_tags()
    docs = []
    workflow_filter = workflow_filter.strip() if workflow_filter else ""
    
    for name in os.listdir(DOCS_DIR):
        path = os.path.join(DOCS_DIR, name)
        if os.path.isdir(path):
            continue
        
        doc_tag = tags.get(name, "")
        
        # If filtering by workflow, skip documents that don't match
        if workflow_filter and doc_tag.strip() != workflow_filter:
            continue
        
        if name.lower().endswith(".txt"):
            docs.append({"source": name, "text": read_txt(path), "tag": doc_tag})
        elif name.lower().endswith(".pdf"):
            docs.append({"source": name, "text": read_pdf(path), "tag": doc_tag})
    
    return docs

def chunk_text(text: str, chunk_size=1000, chunk_overlap=200):
    # Simple character-based chunking (works well enough to start)
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunks.append(text[start:end])
        start = max(end - chunk_overlap, start + 1)
    return chunks

def embed_texts(client: genai.Client, texts: list[str]) -> np.ndarray:
    # Docs: embed_content supports list-of-strings ("contents") :contentReference[oaicite:5]{index=5}
    res = client.models.embed_content(model=EMBED_MODEL, contents=texts)
    # SDK returns embeddings objects; each has "values" (vector floats)
    vectors = [e.values for e in res.embeddings]
    return np.array(vectors, dtype="float32")

def ingest_documents(workflow_filter: str = "") -> dict:
    """Ingest documents and build FAISS index.
    
    Args:
        workflow_filter: If not empty, only ingest documents with this tag.
    
    Returns:
        Dictionary with ingestion stats.
    """
    os.makedirs(INDEX_DIR, exist_ok=True)

    client = genai.Client()  # auto-picks GEMINI_API_KEY env var

    docs = load_documents(workflow_filter=workflow_filter)
    all_chunks = []

    for d in docs:
        for j, ch in enumerate(chunk_text(d["text"])):
            all_chunks.append({
                "id": f"{d['source']}::chunk{j}",
                "source": d["source"],
                "tag": d.get("tag", ""),
                "text": ch
            })

    if not all_chunks:
        filter_text = f" for workflow '{workflow_filter}'" if workflow_filter else ""
        print(f"No documents found in /documents{filter_text} (supported: .txt, .pdf).")
        return {"success": False, "error": "No documents found"}

    print(f"Processing {len(all_chunks)} chunks from {len(docs)} documents...")

    # Embed in batches
    batch_size = 64
    vecs = []
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i+batch_size]
        print(f"  Embedding batch {i//batch_size + 1}/{(len(all_chunks) + batch_size - 1)//batch_size}...")
        vectors = embed_texts(client, [b["text"] for b in batch])
        vecs.append(vectors)
    
    vecs = np.vstack(vecs)

    dim = vecs.shape[1]
    index = faiss.IndexFlatIP(dim)

    # Normalize to use cosine similarity via inner product
    faiss.normalize_L2(vecs)
    index.add(vecs)

    faiss.write_index(index, INDEX_PATH)

    with open(CHUNKS_PATH, "w", encoding="utf-8") as f:
        for c in all_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    filter_text = f" for workflow '{workflow_filter}'" if workflow_filter else ""
    print(f"✓ Indexed {len(all_chunks)} chunks from {len(docs)} documents{filter_text}.")
    print(f"  Saved: {INDEX_PATH} and {CHUNKS_PATH}")
    
    return {
        "success": True,
        "chunks_count": len(all_chunks),
        "docs_count": len(docs),
        "workflow": workflow_filter or "all"
    }


def main():
    ingest_documents()


if __name__ == "__main__":
    main()