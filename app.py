import json
import os
from flask import (
    Flask,
    request,
    jsonify,
    send_from_directory,
    render_template,
    Response,
)
from typing import List

import ingest
from workflow_manager import WorkflowManager
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
    get_session_tag,
    set_session_tag,
    determine_query_context,
    extract_tag_from_query,
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

# workflow manager
workflow_manager = WorkflowManager()

SESSION_ID = os.getenv("SESSION_ID", "default")

TAGS_PATH = "document_tags.json"


def load_tags() -> dict:
    if not os.path.exists(TAGS_PATH):
        return {}
    with open(TAGS_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f) or {}
        except Exception:
            return {}


def save_tags(tags: dict) -> None:
    with open(TAGS_PATH, "w", encoding="utf-8") as f:
        json.dump(tags, f, ensure_ascii=False, indent=2)


@app.route("/api/tags", methods=["GET"])
def list_tags():
    prefix = (request.args.get("prefix") or "").strip().lower()
    tags = set(
        t.strip()
        for t in load_tags().values()
        if isinstance(t, str) and t.strip()
    )
    if prefix:
        tags = {t for t in tags if t.lower().startswith(prefix)}
    return jsonify({"tags": sorted(tags)})


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


@app.route("/api/workflows", methods=["GET"])
def list_workflows():
    """Get all available workflows (tags)."""
    try:
        workflows = workflow_manager.get_all_workflows()
        current = get_session_tag(SESSION_ID)
        return jsonify({
            "workflows": workflows,
            "current": current,
            "count": len(workflows)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/workflows/<workflow_name>/files", methods=["GET"])
def get_workflow_files(workflow_name):
    """Get files for a specific workflow."""
    try:
        workflow_name = workflow_name.strip()
        if not workflow_manager.is_valid_workflow(workflow_name):
            return jsonify({"error": f"Unknown workflow: {workflow_name}"}), 404
        
        files = workflow_manager.get_files_for_workflow(workflow_name)
        return jsonify({
            "workflow": workflow_name,
            "files": files,
            "count": len(files)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/workflows/select", methods=["POST"])
def select_workflow():
    """Select a workflow and ingest its documents."""
    try:
        data = request.get_json(force=True)
        workflow = data.get("workflow", "").strip()
        
        if not workflow:
            return jsonify({"error": "Workflow name required"}), 400
        
        if not workflow_manager.is_valid_workflow(workflow):
            all_workflows = workflow_manager.get_all_workflows()
            return jsonify({
                "error": f"Unknown workflow: {workflow}",
                "available": all_workflows
            }), 404
        
        # Ingest documents for this workflow
        result = ingest.ingest_documents(workflow_filter=workflow)
        
        if not result["success"]:
            return jsonify(result), 500
        
        # Reload resources with newly ingested index
        load_resources()
        
        # Set session tag to the selected workflow
        set_session_tag(SESSION_ID, workflow)
        
        # Get the files for this workflow
        files = workflow_manager.get_files_for_workflow(workflow)
        
        return jsonify({
            "success": True,
            "workflow": workflow,
            "files": files,
            "files_count": len(files),
            "chunks_count": result.get("chunks_count", 0),
            "message": f"✓ Ingested {result.get('docs_count', 0)} documents for workflow '{workflow}'"
        })
    except Exception as e:
        return jsonify({"error": str(e), "details": str(e)}), 500


@app.route("/api/workflow/status", methods=["GET"])
def get_workflow_status():
    """Get current workflow status."""
    try:
        current_workflow = get_session_tag(SESSION_ID)
        is_ready = index is not None and chunks is not None and llm is not None
        
        if current_workflow:
            files = workflow_manager.get_files_for_workflow(current_workflow)
        else:
            files = []
        
        return jsonify({
            "current_workflow": current_workflow,
            "is_ready": is_ready,
            "files_count": len(files),
            "has_index": index is not None,
            "has_chunks": chunks is not None,
            "has_llm": llm is not None
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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

    # allow the user to scope retrieval using a tag (e.g. "#sales")
    tag, cleaned_query = extract_tag_from_query(query)
    if not tag:
        tag = get_session_tag(SESSION_ID)
    else:
        # if user explicitly supplied a tag, make it sticky
        set_session_tag(SESSION_ID, tag)

    query_for_processing = cleaned_query or query

    try:
        # record user message in memory if available
        memory_context = ""
        if memory_store is not None and memory_index is not None:
            user_msg_id = memory_store.add_message(SESSION_ID, "user", query_for_processing)
            memory_index.add_memory(SESSION_ID, user_msg_id, "user", query_for_processing)
            mem_hits = memory_index.search(SESSION_ID, query_for_processing, TOP_K_RERANK)
            from chatbot import build_memory_context, MAX_MEMORY_CONTEXT_CHARS
            memory_context = build_memory_context(mem_hits, MAX_MEMORY_CONTEXT_CHARS)

        # determine follow-up / routing
        active_sources = get_session_active_sources(SESSION_ID)
        routing = determine_query_context(
            llm=llm,
            user_query=query_for_processing,
            recent_messages=[],  # could pass recent from memory_store if desired
            active_sources=active_sources,
        )
        retrieval_query = routing["standalone_query"]
        follow_up = bool(routing.get("is_follow_up"))
        use_prior_sources = bool(routing.get("use_prior_sources"))

        doc_embedder = Embedder(DOC_EMBEDDING_PROVIDER)
        if follow_up and use_prior_sources and active_sources:
            hits, widened = retrieve_document_chunks_followup_aware(
                index,
                chunks,
                doc_embedder,
                retrieval_query,
                TOP_K_RETRIEVE,
                active_sources,
                tag=tag,
            )
        else:
            hits = retrieve_document_chunks(
                index,
                chunks,
                doc_embedder,
                retrieval_query,
                TOP_K_RETRIEVE,
                tag=tag,
            )
            widened = False

        if not hits:
            answer = "I don't know based on the documents."
        else:
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

        # Stream the response in chunks
        def generate_stream():
            # Stream in chunks of ~50 characters for visual streaming effect
            chunk_size = 50
            for i in range(0, len(answer), chunk_size):
                chunk = answer[i:i+chunk_size]
                # Escape newlines and quotes for JSON
                chunk_json = json.dumps({"chunk": chunk})
                yield f"data: {chunk_json}\n\n"
        
        return Response(generate_stream(), mimetype="text/event-stream")
    except Exception as e:
        def error_stream():
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        return Response(error_stream(), mimetype="text/event-stream")


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
    tags = load_tags()
    docs = _get_all_documents()
    return jsonify({
        "documents": [
            {"name": name, "tag": tags.get(name, "")} for name in docs
        ]
    })


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

    # preserve any existing tag; allow client to override via optional field
    tags = load_tags()
    tag = request.form.get("tag", "").strip()
    if tag:
        tags[filename] = tag
        save_tags(tags)

    return jsonify({"message": "Uploaded", "filename": filename, "tag": tags.get(filename, "")})


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
        # also remove any tag association for this file
        tags = load_tags()
        if filename in tags:
            tags.pop(filename)
            save_tags(tags)
        return jsonify({"message": "Deleted"})
    else:
        return jsonify({"error": "File not found"}), 404


@app.route("/api/documents/<filename>/tag", methods=["PUT"])
def update_doc_tag(filename):
    data = request.get_json(force=True)
    tag = (data.get("tag") or "").strip()

    docs = _get_all_documents()
    if filename not in docs:
        return jsonify({"error": "File not found"}), 404

    tags = load_tags()
    if tag:
        tags[filename] = tag
    else:
        tags.pop(filename, None)
    save_tags(tags)

    return jsonify({"message": "Tag updated", "tag": tags.get(filename, "")})


if __name__ == "__main__":
    app.run(debug=True)
    print("Loaded chatbot.py from:", os.path.abspath(__file__))
    print("Session ID:", SESSION_ID)
