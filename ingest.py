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

def load_documents():
    docs = []
    for name in os.listdir(DOCS_DIR):
        path = os.path.join(DOCS_DIR, name)
        if os.path.isdir(path):
            continue
        if name.lower().endswith(".txt"):
            docs.append({"source": name, "text": read_txt(path)})
        elif name.lower().endswith(".pdf"):
            docs.append({"source": name, "text": read_pdf(path)})
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

def main():
    os.makedirs(INDEX_DIR, exist_ok=True)

    client = genai.Client()  # auto-picks GEMINI_API_KEY env var :contentReference[oaicite:6]{index=6}

    docs = load_documents()
    all_chunks = []

    for d in docs:
        for j, ch in enumerate(chunk_text(d["text"])):
            all_chunks.append({
                "id": f"{d['source']}::chunk{j}",
                "source": d["source"],
                "text": ch
            })

    if not all_chunks:
        print("No documents found in /documents (supported: .txt, .pdf).")
        return

    # Embed in batches
    batch_size = 64
    vecs = []
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i+batch_size]
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

    print(f"Indexed {len(all_chunks)} chunks from {len(docs)} documents.")
    print(f"Saved: {INDEX_PATH} and {CHUNKS_PATH}")

if __name__ == "__main__":
    main()