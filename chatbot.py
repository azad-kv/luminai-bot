import json
import os
from typing import Any, Dict, List, Tuple

import faiss
from dotenv import load_dotenv

from conversation_memory import ConversationMemoryIndex, Embedder
from memory_store import MemoryStore

load_dotenv()

INDEX_DIR = "index"
INDEX_PATH = os.path.join(INDEX_DIR, "faiss.index")
CHUNKS_PATH = os.path.join(INDEX_DIR, "chunks.jsonl")

GENERATION_PROVIDER = os.getenv("GENERATION_PROVIDER", "gemini").strip().lower()
DOC_EMBEDDING_PROVIDER = os.getenv("DOC_EMBEDDING_PROVIDER", "gemini").strip().lower()
MEMORY_EMBEDDING_PROVIDER = os.getenv(
    "MEMORY_EMBEDDING_PROVIDER", DOC_EMBEDDING_PROVIDER
).strip().lower()

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

TOP_K_DOCS = int(os.getenv("TOP_K_DOCS", "6"))
TOP_K_MEMORY = int(os.getenv("TOP_K_MEMORY", "3"))
RECENT_TURNS = int(os.getenv("RECENT_TURNS", "6"))
SUMMARY_EVERY_N_MESSAGES = int(os.getenv("SUMMARY_EVERY_N_MESSAGES", "6"))
MAX_DOC_CONTEXT_CHARS = int(os.getenv("MAX_DOC_CONTEXT_CHARS", "10000"))
MAX_MEMORY_CONTEXT_CHARS = int(os.getenv("MAX_MEMORY_CONTEXT_CHARS", "4000"))
SESSION_ID = os.getenv("SESSION_ID", "default")

ACTIVE_SOURCE_FILE = os.getenv("ACTIVE_SOURCE_FILE", "active_sources.json")
FOLLOWUP_MIN_RELEVANCE = float(os.getenv("FOLLOWUP_MIN_RELEVANCE", "0.35"))
FOLLOWUP_EXPANDED_SEARCH_MULTIPLIER = int(
    os.getenv("FOLLOWUP_EXPANDED_SEARCH_MULTIPLIER", "5")
)
ENABLE_QUERY_ROUTING_DEBUG = (
    os.getenv("ENABLE_QUERY_ROUTING_DEBUG", "false").strip().lower() == "true"
)


def load_chunks() -> List[Dict[str, Any]]:
    if not os.path.exists(CHUNKS_PATH):
        raise FileNotFoundError(f"Missing chunk file: {CHUNKS_PATH}")

    chunks: List[Dict[str, Any]] = []
    with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    return chunks


def load_index() -> faiss.Index:
    if not os.path.exists(INDEX_PATH):
        raise FileNotFoundError(f"Missing FAISS index: {INDEX_PATH}")
    return faiss.read_index(INDEX_PATH)


class LLMClient:
    def generate(self, prompt: str) -> str:
        raise NotImplementedError


class GeminiClient(LLMClient):
    def __init__(self) -> None:
        from google import genai

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Missing GEMINI_API_KEY.")
        self.client = genai.Client(api_key=api_key)

    def generate(self, prompt: str) -> str:
        resp = self.client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        return (resp.text or "").strip()


class OpenAIClient(LLMClient):
    def __init__(self) -> None:
        from openai import OpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("Missing OPENAI_API_KEY.")
        self.client = OpenAI(api_key=api_key)

    def generate(self, prompt: str) -> str:
        resp = self.client.responses.create(
            model=OPENAI_MODEL,
            input=prompt,
        )
        return (resp.output_text or "").strip()


def get_llm_client() -> LLMClient:
    if GENERATION_PROVIDER == "gemini":
        return GeminiClient()
    if GENERATION_PROVIDER == "openai":
        return OpenAIClient()
    raise ValueError("GENERATION_PROVIDER must be 'gemini' or 'openai'.")


def retrieve_document_chunks(
    index: faiss.Index,
    chunks: List[Dict[str, Any]],
    embedder: Embedder,
    query: str,
    top_k: int,
) -> List[Tuple[float, Dict[str, Any]]]:
    qv = embedder.embed_query(query)
    if index.d != qv.shape[1]:
        raise ValueError(
            f"Document index dimension mismatch. FAISS index dim={index.d}, "
            f"query embedding dim={qv.shape[1]}. "
            "Check DOC_EMBEDDING_PROVIDER and rebuild the doc index if needed."
        )

    scores, idxs = index.search(qv, top_k)
    hits: List[Tuple[float, Dict[str, Any]]] = []

    for i in range(len(idxs[0])):
        idx = int(idxs[0][i])
        if idx == -1:
            continue
        if 0 <= idx < len(chunks):
            hits.append((float(scores[0][i]), chunks[idx]))

    return hits


def build_recent_history_text(
    recent_messages: List[Tuple[int, str, str]],
) -> str:
    if not recent_messages:
        return "(none)"

    lines: List[str] = []
    for _, role, content in recent_messages:
        role_name = "User" if role == "user" else "Assistant"
        lines.append(f"{role_name}: {content}")
    return "\n".join(lines)


def build_memory_context(
    memory_hits: List[Tuple[float, Dict[str, Any]]],
    max_chars: int,
) -> str:
    if not memory_hits:
        return "(none)"

    parts: List[str] = []
    total = 0
    for score, item in memory_hits:
        block = (
            f"Role: {item['role']}\n"
            f"Message ID: {item['message_id']}\n"
            f"Relevance: {score:.3f}\n"
            f"Content: {item['content']}"
        )
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block) + 6

    return "\n\n---\n\n".join(parts) if parts else "(none)"


def build_doc_context(
    doc_hits: List[Tuple[float, Dict[str, Any]]],
    max_chars: int,
) -> str:
    if not doc_hits:
        return "(none)"

    parts: List[str] = []
    total = 0
    for score, ch in doc_hits:
        block = (
            f"Source: {ch.get('source', 'unknown')}\n"
            f"Chunk ID: {ch.get('id', '')}\n"
            f"Relevance: {score:.3f}\n"
            f"Text:\n{ch.get('text', '')}"
        )
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block) + 10

    return "\n\n---\n\n".join(parts) if parts else "(none)"


def build_answer_prompt(
    user_query: str,
    summary: str,
    facts: List[str],
    recent_history: str,
    memory_context: str,
    doc_context: str,
) -> str:
    facts_text = "\n".join(f"- {f}" for f in facts) if facts else "(none)"
    summary_text = summary.strip() or "(none)"
    source_guidance = build_source_guidance(user_query)

    return f"""
You are a memory-enabled document RAG assistant.

Follow these rules:
- Answer the user's question using the retrieved document context when relevant.
- Use conversation memory to preserve continuity and interpret follow-up questions.
- If the answer is not supported by the documents, say so clearly.
- Do not invent facts.
- Cite source filenames in square brackets when making document-based claims, for example [design_doc.pdf].
- If conversation memory conflicts with document context, prefer document context for factual claims.
- For follow-up questions, prefer continuity with the previously active document set unless the evidence clearly requires switching sources.
- If the answer relies on a different document than the prior turn, explicitly say that you are switching sources.

Durable facts:
{facts_text}

Conversation summary:
{summary_text}

Recent conversation:
{recent_history}

Relevant prior conversation memory:
{memory_context}

Retrieved document context:
{doc_context}

Source continuity guidance:
{source_guidance}

Current user question:
{user_query}
""".strip()


def build_summary_prompt(old_summary: str, new_messages: List[Tuple[int, str, str]]) -> str:
    new_text = "\n".join(
        f"{'User' if role == 'user' else 'Assistant'}: {content}"
        for _, role, content in new_messages
    )

    return f"""
Update the conversation summary.

Existing summary:
{old_summary or "(none)"}

New messages:
{new_text}

Return only the updated summary as plain text.
Keep it concise, factual, and useful for future follow-up questions.
Focus on:
- decisions made
- feature priorities
- architecture choices
- unresolved questions
""".strip()


def maybe_update_summary(
    store: MemoryStore,
    llm: LLMClient,
    session_id: str,
    last_summarized_id: int,
) -> int:
    latest_id = store.get_latest_message_id(session_id)
    if latest_id <= last_summarized_id:
        return last_summarized_id

    new_messages = store.get_messages_after_id(session_id, last_summarized_id)
    if len(new_messages) < SUMMARY_EVERY_N_MESSAGES:
        return last_summarized_id

    old_summary = store.get_summary(session_id)
    prompt = build_summary_prompt(old_summary, new_messages)
    updated_summary = llm.generate(prompt).strip()

    if updated_summary:
        store.upsert_summary(session_id, updated_summary)
        return latest_id

    return last_summarized_id


def maybe_extract_facts(
    store: MemoryStore,
    llm: LLMClient,
    session_id: str,
    recent_messages: List[Tuple[int, str, str]],
) -> None:
    convo = "\n".join(
        f"{'User' if role == 'user' else 'Assistant'}: {content}"
        for _, role, content in recent_messages
    )
    prompt = f"""
Extract durable user/project facts from the conversation below.

Only include facts likely to matter later, such as:
- chosen architecture
- feature priorities
- preferred providers
- important constraints

Return JSON only:
{{"facts":["fact 1","fact 2"]}}

Conversation:
{convo}
""".strip()

    try:
        raw = llm.generate(prompt)
        data = parse_json_object(raw)
        facts = data.get("facts", [])
        if isinstance(facts, list):
            existing = set(store.get_facts(session_id, limit=100))
            for fact in facts:
                if isinstance(fact, str):
                    fact = fact.strip()
                    if fact and fact not in existing:
                        store.add_fact(session_id, fact)
                        existing.add(fact)
    except Exception:
        return


def parse_json_object(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found.")
    return json.loads(text[start : end + 1])


def print_sources(doc_hits: List[Tuple[float, Dict[str, Any]]]) -> None:
    if not doc_hits:
        print("\nRetrieved document sources:\n- none\n")
        return

    print("\nRetrieved document sources:")
    seen = set()
    for score, ch in doc_hits:
        key = (ch.get("source", "unknown"), ch.get("id", ""))
        if key in seen:
            continue
        seen.add(key)
        print(f"- {key[0]} ({key[1]}) score={score:.3f}")
    print()


def load_active_source_state() -> Dict[str, Any]:
    if not os.path.exists(ACTIVE_SOURCE_FILE):
        return {}
    try:
        with open(ACTIVE_SOURCE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def save_active_source_state(state: Dict[str, Any]) -> None:
    with open(ACTIVE_SOURCE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def get_session_active_sources(session_id: str) -> List[str]:
    state = load_active_source_state()
    session_state = state.get(session_id, {})
    sources = session_state.get("active_sources", [])
    if isinstance(sources, list):
        return [str(s) for s in sources if isinstance(s, str)]
    return []


def set_session_active_sources(session_id: str, sources: List[str]) -> None:
    state = load_active_source_state()
    if session_id not in state or not isinstance(state[session_id], dict):
        state[session_id] = {}
    state[session_id]["active_sources"] = sources
    save_active_source_state(state)


def is_follow_up_query(query: str, recent_messages: List[Tuple[int, str, str]]) -> bool:
    q = query.strip().lower()
    if not q:
        return False

    followup_phrases = [
        "what about",
        "how about",
        "tell me more",
        "expand on",
        "expand on that",
        "expand on the steps",
        "mentioned here",
        "summarize that",
        "who owns",
        "when is",
        "when does",
        "what's the timeline",
        "what is the timeline",
        "compare that",
        "explain that",
        "what about the",
    ]

    pronoun_tokens = {
        "it", "that", "this", "those", "they", "them", "these",
        "he", "she", "his", "her", "its", "their",
    }

    if any(phrase in q for phrase in followup_phrases):
        return True

    tokens = q.replace("?", " ").replace(",", " ").split()
    if len(tokens) <= 8 and any(token in pronoun_tokens for token in tokens):
        return True

    if len(tokens) <= 5 and recent_messages:
        return True

    return False


def extract_sources_from_hits(doc_hits: List[Tuple[float, Dict[str, Any]]]) -> List[str]:
    sources: List[str] = []
    seen = set()
    for _, ch in doc_hits:
        source = ch.get("source")
        if isinstance(source, str) and source not in seen:
            seen.add(source)
            sources.append(source)
    return sources


def filter_hits_by_sources(
    doc_hits: List[Tuple[float, Dict[str, Any]]],
    allowed_sources: List[str],
    top_k: int,
) -> List[Tuple[float, Dict[str, Any]]]:
    if not allowed_sources:
        return doc_hits[:top_k]

    allowed = set(allowed_sources)
    filtered: List[Tuple[float, Dict[str, Any]]] = []
    seen_ids = set()

    for score, ch in doc_hits:
        if ch.get("source") not in allowed:
            continue
        chunk_id = ch.get("id")
        if chunk_id in seen_ids:
            continue
        seen_ids.add(chunk_id)
        filtered.append((score, ch))
        if len(filtered) >= top_k:
            break

    return filtered


def retrieve_document_chunks_followup_aware(
    index: faiss.Index,
    chunks: List[Dict[str, Any]],
    embedder: Embedder,
    query: str,
    top_k: int,
    allowed_sources: List[str],
) -> Tuple[List[Tuple[float, Dict[str, Any]]], bool]:
    expanded_k = min(max(top_k * FOLLOWUP_EXPANDED_SEARCH_MULTIPLIER, top_k), len(chunks))
    global_hits = retrieve_document_chunks(index, chunks, embedder, query, expanded_k)
    scoped_hits = filter_hits_by_sources(global_hits, allowed_sources, top_k)

    if scoped_hits:
        best_score = scoped_hits[0][0]
        if best_score >= FOLLOWUP_MIN_RELEVANCE:
            return scoped_hits, False

    return global_hits[:top_k], True


def build_source_guidance(user_query: str) -> str:
    active_sources = get_session_active_sources(SESSION_ID)
    if not active_sources:
        return "No prior active document set is available for this session."

    if is_follow_up_query(user_query, []):
        joined = ", ".join(active_sources)
        return (
            f"This question appears to be a follow-up. "
            f"Prefer interpreting it with respect to these previously active sources first: {joined}. "
            f"If you rely on different sources, say so explicitly."
        )

    return (
        "This question does not appear to require strict source continuity, "
        "but you should still avoid silently switching sources when answering."
    )


def build_query_router_prompt(
    user_query: str,
    recent_history: str,
    active_sources: List[str],
) -> str:
    active_sources_text = ", ".join(active_sources) if active_sources else "(none)"
    return f"""
You are a query router for a document RAG chatbot.

Your job is to decide whether the user's new query is:
1. standalone
2. a follow-up that depends on prior conversation context
3. a follow-up that should remain anchored to the same documents as the previous turn

Return JSON only:
{{
  "is_follow_up": true,
  "standalone_rewrite": "fully rewritten standalone query here",
  "use_prior_sources": true,
  "reason": "brief reason"
}}

Rules:
- "standalone_rewrite" must preserve the user's intent and resolve references like "that", "here", "it", or "those" when possible.
- If the query depends on the previous document context, set "use_prior_sources" to true.
- If the query is already standalone, return it unchanged in "standalone_rewrite".
- Keep "reason" short.

Previously active sources:
{active_sources_text}

Recent conversation:
{recent_history}

New user query:
{user_query}
""".strip()


def determine_query_context(
    llm: LLMClient,
    user_query: str,
    recent_messages: List[Tuple[int, str, str]],
    active_sources: List[str],
) -> Dict[str, Any]:
    recent_history = build_recent_history_text(recent_messages)
    prompt = build_query_router_prompt(user_query, recent_history, active_sources)

    heuristic_follow_up = is_follow_up_query(user_query, recent_messages)

    try:
        raw = llm.generate(prompt)
        data = parse_json_object(raw)

        standalone_rewrite = data.get("standalone_rewrite", user_query)
        if not isinstance(standalone_rewrite, str) or not standalone_rewrite.strip():
            standalone_rewrite = user_query

        result = {
            "is_follow_up": bool(data.get("is_follow_up", heuristic_follow_up)),
            "standalone_query": standalone_rewrite.strip(),
            "use_prior_sources": bool(data.get("use_prior_sources", heuristic_follow_up and bool(active_sources))),
            "reason": str(data.get("reason", "")).strip(),
        }

        return result
    except Exception:
        return {
            "is_follow_up": heuristic_follow_up,
            "standalone_query": user_query,
            "use_prior_sources": bool(heuristic_follow_up and active_sources),
            "reason": "fallback_to_heuristic",
        }


def main() -> None:
    try:
        doc_index = load_index()
        doc_chunks = load_chunks()

        llm = get_llm_client()
        doc_embedder = Embedder(DOC_EMBEDDING_PROVIDER)
        memory_store = MemoryStore("session.db")
        memory_index = ConversationMemoryIndex(
            memory_dir="memory_index",
            embedding_provider=MEMORY_EMBEDDING_PROVIDER,
        )
    except Exception as e:
        print(f"Startup error: {e}")
        return

    print(f"Generation provider: {GENERATION_PROVIDER}")
    print(f"Doc embedding provider: {DOC_EMBEDDING_PROVIDER}")
    print(f"Memory embedding provider: {MEMORY_EMBEDDING_PROVIDER}")
    print(f"Session ID: {SESSION_ID}")
    print("Commands: :quit, :exit, :summary, :facts, :session, :sources")
    print()

    last_summarized_id = 0

    while True:
        try:
            user_query = input("Ask> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not user_query:
            continue

        if user_query in {":quit", ":exit"}:
            break

        if user_query == ":summary":
            print("\nSummary:\n")
            print(memory_store.get_summary(SESSION_ID) or "(none)")
            print()
            continue

        if user_query == ":facts":
            facts = memory_store.get_facts(SESSION_ID, limit=50)
            print("\nFacts:")
            if not facts:
                print("- none")
            else:
                for fact in facts:
                    print(f"- {fact}")
            print()
            continue

        if user_query == ":session":
            print(f"\nCurrent session: {SESSION_ID}\n")
            continue

        if user_query == ":sources":
            sources = get_session_active_sources(SESSION_ID)
            print("\nActive sources:")
            if not sources:
                print("- none")
            else:
                for src in sources:
                    print(f"- {src}")
            print()
            continue

        try:
            user_msg_id = memory_store.add_message(SESSION_ID, "user", user_query)
            memory_index.add_memory(SESSION_ID, user_msg_id, "user", user_query)

            recent_messages = memory_store.get_recent_messages(SESSION_ID, RECENT_TURNS)
            summary = memory_store.get_summary(SESSION_ID)
            facts = memory_store.get_facts(SESSION_ID, limit=20)

            active_sources = get_session_active_sources(SESSION_ID)
            query_context = determine_query_context(
                llm=llm,
                user_query=user_query,
                recent_messages=recent_messages,
                active_sources=active_sources,
            )

            retrieval_query = query_context["standalone_query"]
            follow_up = bool(query_context["is_follow_up"])
            use_prior_sources = bool(query_context["use_prior_sources"])

            if ENABLE_QUERY_ROUTING_DEBUG:
                print("DEBUG routing:", query_context)
                print("DEBUG active_sources(before):", active_sources)
                print("DEBUG retrieval_query:", retrieval_query)

            if follow_up and use_prior_sources and active_sources:
                doc_hits, widened_search = retrieve_document_chunks_followup_aware(
                    doc_index,
                    doc_chunks,
                    doc_embedder,
                    retrieval_query,
                    TOP_K_DOCS,
                    active_sources,
                )
            else:
                doc_hits = retrieve_document_chunks(
                    doc_index, doc_chunks, doc_embedder, retrieval_query, TOP_K_DOCS
                )
                widened_search = False

            memory_hits = memory_index.search(
                session_id=SESSION_ID,
                query=retrieval_query,
                top_k=TOP_K_MEMORY,
            )

            if doc_hits:
                new_active_sources = extract_sources_from_hits(doc_hits)
                if new_active_sources:
                    set_session_active_sources(SESSION_ID, new_active_sources)

            recent_history_text = build_recent_history_text(recent_messages)
            memory_context = build_memory_context(memory_hits, MAX_MEMORY_CONTEXT_CHARS)
            doc_context = build_doc_context(doc_hits, MAX_DOC_CONTEXT_CHARS)

            prompt = build_answer_prompt(
                user_query=user_query,
                summary=summary,
                facts=facts,
                recent_history=recent_history_text,
                memory_context=memory_context,
                doc_context=doc_context,
            )

            prompt += (
                "\n\nQuery interpretation:\n"
                f"- Original user query: {user_query}\n"
                f"- Standalone retrieval query: {retrieval_query}\n"
                f"- Classified as follow-up: {follow_up}\n"
                f"- Prior-source continuity requested: {use_prior_sources}\n"
            )

            if query_context.get("reason"):
                prompt += f"- Routing reason: {query_context['reason']}\n"

            if follow_up and active_sources and widened_search:
                prompt += (
                    "\nAdditional instruction:\n"
                    "This follow-up question could not be answered confidently from the prior active sources alone. "
                    "You may use newly retrieved documents, but you must explicitly mention if you are switching sources."
                )

            answer = llm.generate(prompt)

            assistant_msg_id = memory_store.add_message(SESSION_ID, "assistant", answer)
            memory_index.add_memory(SESSION_ID, assistant_msg_id, "assistant", answer)

            updated_recent = memory_store.get_recent_messages(SESSION_ID, RECENT_TURNS)
            maybe_extract_facts(memory_store, llm, SESSION_ID, updated_recent)
            last_summarized_id = maybe_update_summary(
                memory_store, llm, SESSION_ID, last_summarized_id
            )

            print("\nAnswer:\n")
            print(answer)
            print_sources(doc_hits)

        except Exception as e:
            print(f"\nError: {e}\n")


if __name__ == "__main__":
    main()