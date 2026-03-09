import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import faiss
import numpy as np


class Embedder:
    def __init__(self, provider: str = "gemini") -> None:
        self.provider = provider.strip().lower()
        if self.provider not in {"gemini", "openai"}:
            raise ValueError("Embedding provider must be 'gemini' or 'openai'.")

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 0), dtype="float32")

        if self.provider == "gemini":
            return self._embed_with_gemini(texts)
        return self._embed_with_openai(texts)

    def embed_query(self, text: str) -> np.ndarray:
        vectors = self.embed_texts([text])
        if vectors.size == 0:
            raise ValueError("Failed to embed query.")
        return vectors

    def _embed_with_gemini(self, texts: List[str]) -> np.ndarray:
        from google import genai

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Missing GEMINI_API_KEY for Gemini embeddings.")

        client = genai.Client(api_key=api_key)
        res = client.models.embed_content(
            model="gemini-embedding-001",
            contents=texts,
        )
        vectors = np.array([e.values for e in res.embeddings], dtype="float32")
        faiss.normalize_L2(vectors)
        return vectors

    def _embed_with_openai(self, texts: List[str]) -> np.ndarray:
        from openai import OpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("Missing OPENAI_API_KEY for OpenAI embeddings.")

        client = OpenAI(api_key=api_key)
        res = client.embeddings.create(
            model="text-embedding-3-small",
            input=texts,
        )
        vectors = np.array([d.embedding for d in res.data], dtype="float32")
        faiss.normalize_L2(vectors)
        return vectors


class ConversationMemoryIndex:
    def __init__(
        self,
        memory_dir: str = "memory_index",
        embedding_provider: str = "gemini",
    ) -> None:
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        self.index_path = self.memory_dir / "memory.faiss"
        self.meta_path = self.memory_dir / "memory_chunks.jsonl"

        self.embedder = Embedder(embedding_provider)
        self.index: Optional[faiss.Index] = None
        self.metadata: List[Dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if self.index_path.exists() and self.meta_path.exists():
            self.index = faiss.read_index(str(self.index_path))
            with open(self.meta_path, "r", encoding="utf-8") as f:
                self.metadata = [json.loads(line) for line in f if line.strip()]
        else:
            self.index = None
            self.metadata = []

    def _save(self) -> None:
        if self.index is None:
            return
        faiss.write_index(self.index, str(self.index_path))
        with open(self.meta_path, "w", encoding="utf-8") as f:
            for item in self.metadata:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

    def add_memory(
        self,
        session_id: str,
        message_id: int,
        role: str,
        content: str,
    ) -> None:
        content = content.strip()
        if not content:
            return

        vector = self.embedder.embed_query(content)
        dim = vector.shape[1]

        if self.index is None:
            self.index = faiss.IndexFlatIP(dim)
        elif self.index.d != dim:
            raise ValueError(
                f"Memory index dimension mismatch. Existing={self.index.d}, new={dim}. "
                "Delete memory_index/ and rebuild if you changed embedding providers."
            )

        self.index.add(vector)
        self.metadata.append(
            {
                "session_id": session_id,
                "message_id": message_id,
                "role": role,
                "content": content,
            }
        )
        self._save()

    def search(
        self,
        session_id: str,
        query: str,
        top_k: int = 3,
    ) -> List[Tuple[float, Dict[str, Any]]]:
        if self.index is None or not self.metadata:
            return []

        qv = self.embedder.embed_query(query)
        scores, idxs = self.index.search(qv, min(top_k * 3, len(self.metadata)))

        hits: List[Tuple[float, Dict[str, Any]]] = []
        seen_message_ids = set()

        for i in range(len(idxs[0])):
            idx = int(idxs[0][i])
            if idx == -1:
                continue
            meta = self.metadata[idx]
            if meta["session_id"] != session_id:
                continue
            message_id = meta["message_id"]
            if message_id in seen_message_ids:
                continue
            seen_message_ids.add(message_id)
            hits.append((float(scores[0][i]), meta))
            if len(hits) >= top_k:
                break

        return hits