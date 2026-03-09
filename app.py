import os
from flask import (
    Flask,
    request,
    jsonify,
    send_from_directory,
    render_template,
)
from typing import List

import ingest
from chatbot import (
    SESSION_ID,
    load_index,
    load_chunks,
    get_llm_client,
    retrieve_document_chunks,
    retrieve_document_chunks_followup_aware,
    build_doc_context,
    build_answer_prompt,
    get_session_active_sources,
    set_session_active_sources,
    determine_query_context,
    MAX_DOC_CONTEXT_CHARS,
    TOP_K_DOCS as TOP_K_RETRIEVE,
    TOP_K_MEMORY as TOP_K_RERANK,
    DOC_EMBEDDING_PROVIDER,
)
from conversation_memory import Embedder, ConversationMemoryIndex
from memory_store import MemoryStore

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "documents"

# resources that get reloaded every time the index is rebuilt
index = None
chunks = None
llm = None

# memory objects (persist in server runtime)
memory_store: MemoryStore | None = None
memory_index: ConversationMemoryIndex | None = None

SESSION_ID = os.getenv("SESSION_ID", "default")


def load_resources():
    global index, chunks, llm, memory_store, memory_index
    try:
        index = load_index()
        chunks = load_chunks()
        llm = get_llm_client()
        # initialize memory components only once
        if memory_store is None:
            memory_store = MemoryStore("session.db")
        if memory_index is None:
            memory_index = ConversationMemoryIndex(
                memory_dir="memory_index",
                embedding_provider=os.getenv("MEMORY_EMBEDDING_PROVIDER", DOC_EMBEDDING_PROVIDER),
            )
    except Exception as e:
        # we keep them as None in case of failure
        index = None
        chunks = None
        llm = None
        print(f"Warning while loading resources: {e}")


load_resources()


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "Empty query"}), 400

    if index is None or chunks is None or llm is None:
        return jsonify({"error": "Index or model not available. Run ingest first."}), 500

    try:
        # record user message in memory if available
        memory_context = ""
        if memory_store is not None and memory_index is not None:
            user_msg_id = memory_store.add_message(SESSION_ID, "user", query)
            memory_index.add_memory(SESSION_ID, user_msg_id, "user", query)
            mem_hits = memory_index.search(SESSION_ID, query, TOP_K_RERANK)
            from chatbot import build_memory_context, MAX_MEMORY_CONTEXT_CHARS
            memory_context = build_memory_context(mem_hits, MAX_MEMORY_CONTEXT_CHARS)

        # determine follow-up / routing
        active_sources = get_session_active_sources(SESSION_ID)
        routing = determine_query_context(
            llm=llm,
            user_query=query,
            recent_messages=[],  # could pass recent from memory_store if desired
            active_sources=active_sources,
        )
        retrieval_query = routing["standalone_query"]
        follow_up = bool(routing.get("is_follow_up"))
        use_prior_sources = bool(routing.get("use_prior_sources"))

        doc_embedder = Embedder(DOC_EMBEDDING_PROVIDER)
        if follow_up and use_prior_sources and active_sources:
            hits, widened = retrieve_document_chunks_followup_aware(
                index, chunks, doc_embedder, retrieval_query, TOP_K_RETRIEVE, active_sources
            )
        else:
            hits = retrieve_document_chunks(index, chunks, doc_embedder, retrieval_query, TOP_K_RETRIEVE)
            widened = False

        if not hits:
            return jsonify({"answer": "I don't know based on the documents."})

        # record new active sources
        new_sources = [h[1].get("source") for h in hits if h[1].get("source")]
        if new_sources:
            set_session_active_sources(SESSION_ID, new_sources)

        # take top results for context
        top_hits = hits[:TOP_K_RERANK]
        context = build_doc_context(top_hits, MAX_DOC_CONTEXT_CHARS)
        prompt = build_answer_prompt(
            user_query=query,
            summary="",
            facts=[],
            recent_history="",
            memory_context=memory_context,
            doc_context=context,
        )
        answer = llm.generate(prompt)

        # store assistant reply
        if memory_store is not None and memory_index is not None:
            assistant_id = memory_store.add_message(SESSION_ID, "assistant", answer)
            memory_index.add_memory(SESSION_ID, assistant_id, "assistant", answer)

        return jsonify({"answer": answer})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _get_all_documents() -> List[str]:
    docs: List[str] = []
    folder = app.config["UPLOAD_FOLDER"]
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            docs.append(name)
    return docs


def _get_chunked_sources() -> List[str]:
    # read the chunks file to see which sources have been processed
    try:
        chunks = load_chunks()
    except Exception:
        return []
    seen = set()
    for ch in chunks:
        src = ch.get("source")
        if src:
            seen.add(src)
    return list(seen)


@app.route("/api/documents", methods=["GET"])
def list_docs():
    docs = _get_all_documents()
    return jsonify({"documents": docs})


@app.route("/api/documents/unchunked", methods=["GET"])
def list_unchunked():
    all_docs = set(_get_all_documents())
    chunked = set(_get_chunked_sources())
    pending = sorted(list(all_docs - chunked))
    return jsonify({"documents": pending})


@app.route("/documents/<path:filename>")
def download_doc(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename, as_attachment=True)


@app.route("/api/documents/upload", methods=["POST"])
def upload_doc():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400
    filename = file.filename
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)
    return jsonify({"message": "Uploaded", "filename": filename})


@app.route("/api/documents/ingest", methods=["POST"])
def ingest_docs():
    try:
        ingest.main()
        load_resources()
        return jsonify({"message": "Ingested documents"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/documents/<filename>", methods=["DELETE"])
def delete_doc(filename):
    path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    if os.path.exists(path):
        os.remove(path)
        return jsonify({"message": "Deleted"})
    else:
        return jsonify({"error": "File not found"}), 404


if __name__ == "__main__":
    app.run(debug=True)
    print("Loaded chatbot.py from:", os.path.abspath(__file__))
    print("Session ID:", SESSION_ID)
