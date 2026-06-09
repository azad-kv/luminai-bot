"""Parse RPA workflow blueprint JSON files into searchable text for RAG indexing."""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict, deque
from typing import Any


NODE_LIST_KEYS = ("nodes", "steps", "blocks", "actions")
CONNECTION_LIST_KEYS = ("connections", "edges", "links", "transitions")
FROM_KEYS = ("from", "source", "sourceId", "source_id", "start")
TO_KEYS = ("to", "target", "targetId", "target_id", "end")
ID_KEYS = ("id", "key", "nodeId", "node_id", "stepId", "step_id")
LABEL_KEYS = ("label", "name", "title")
TYPE_KEYS = ("type", "nodeType", "node_type", "stepType", "step_type")
DESCRIPTION_KEYS = ("description", "summary", "details", "notes", "comment")

SENSITIVE_KEYS = frozenset({
    "secrets",
    "encryptedPayload",
    "encryptionKeyVersion",
    "value",
    "_iv",
})

LUMINAI_STEP_LABELS = {
    "start": "Start",
    "finish": "Finish",
    "integration": "Integration",
    "integration_v1": "Integration",
    "compute": "Compute",
    "interaction": "UI Interaction",
    "branch": "Branch",
    "loop": "Loop",
    "virtual": "Virtual Step",
}


def _first_value(data: dict[str, Any], keys: tuple[str, ...], default: str = "") -> str:
    for key in keys:
        value = data.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def is_luminai_export(data: Any) -> bool:
    """Return True if the JSON matches a Luminai workflow export."""
    if not isinstance(data, dict):
        return False
    workflow = data.get("workflow")
    if not isinstance(workflow, dict):
        return False
    state = workflow.get("state")
    if not isinstance(state, dict):
        return False
    return bool(_extract_luminai_graph(workflow))


def is_workflow_blueprint(data: Any) -> bool:
    """Return True if the parsed JSON looks like an RPA workflow blueprint."""
    if is_luminai_export(data):
        return True
    if not isinstance(data, dict):
        return False

    has_nodes = any(isinstance(data.get(key), list) and data.get(key) for key in NODE_LIST_KEYS)
    has_connections = any(
        isinstance(data.get(key), list) and data.get(key) for key in CONNECTION_LIST_KEYS
    )
    return has_nodes or (has_connections and bool(_first_value(data, ("name", "workflow", "title"))))


def _extract_luminai_graph(workflow: dict[str, Any]) -> dict[str, Any] | None:
    state = workflow.get("state") or {}
    tree_root = state.get("treeRoot")
    if isinstance(tree_root, list) and tree_root:
        first = tree_root[0]
        if isinstance(first, dict):
            obj = ((first.get("state") or {}).get("obj") or {})
            if isinstance(obj.get("nodes"), list):
                return obj

    main = state.get("main") or {}
    obj = (main.get("obj") or {})
    if isinstance(obj.get("nodes"), list):
        return obj
    return None


def _extract_nodes(data: dict[str, Any]) -> list[dict[str, Any]]:
    for key in NODE_LIST_KEYS:
        nodes = data.get(key)
        if isinstance(nodes, list):
            return [node for node in nodes if isinstance(node, dict)]
    return []


def _extract_connections(data: dict[str, Any]) -> list[dict[str, Any]]:
    for key in CONNECTION_LIST_KEYS:
        connections = data.get(key)
        if isinstance(connections, list):
            return [conn for conn in connections if isinstance(conn, dict)]
    return []


def _node_id(node: dict[str, Any], index: int) -> str:
    node_id = _first_value(node, ID_KEYS)
    if node_id:
        return node_id
    label = _first_value(node, LABEL_KEYS)
    if label:
        return label
    return f"node_{index + 1}"


def _format_config(config: Any, indent: int = 0, skip_sensitive: bool = True) -> list[str]:
    if not config:
        return []

    lines: list[str] = []
    prefix = "  " * indent

    if isinstance(config, dict):
        for key, value in config.items():
            if skip_sensitive and key in SENSITIVE_KEYS:
                continue
            if isinstance(value, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.extend(_format_config(value, indent + 1, skip_sensitive=skip_sensitive))
            else:
                lines.append(f"{prefix}{key}: {value}")
    elif isinstance(config, list):
        for item in config:
            if isinstance(item, (dict, list)):
                lines.extend(_format_config(item, indent, skip_sensitive=skip_sensitive))
            else:
                lines.append(f"{prefix}- {item}")
    else:
        lines.append(f"{prefix}{config}")

    return lines


def _build_adjacency(
    connections: list[dict[str, Any]],
) -> tuple[dict[str, list[tuple[str, str]]], dict[str, int]]:
    graph: dict[str, list[tuple[str, str]]] = defaultdict(list)
    indegree: dict[str, int] = defaultdict(int)

    for conn in connections:
        source = _first_value(conn, FROM_KEYS)
        target = _first_value(conn, TO_KEYS)
        if not source or not target:
            continue
        label = _first_value(conn, ("label", "condition", "name", "type", "sourceHandle"))
        graph[source].append((target, label))
        indegree[target] += 1
        indegree.setdefault(source, indegree.get(source, 0))

    return graph, indegree


def _topological_order(
    node_ids: list[str],
    graph: dict[str, list[tuple[str, str]]],
    indegree: dict[str, int],
) -> list[str]:
    queue = deque([node_id for node_id in node_ids if indegree.get(node_id, 0) == 0])
    if not queue and node_ids:
        queue.append(node_ids[0])

    visited: list[str] = []
    seen = set()

    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        visited.append(current)
        for target, _ in graph.get(current, []):
            if target not in seen:
                queue.append(target)

    for node_id in node_ids:
        if node_id not in seen:
            visited.append(node_id)

    return visited


def _summarize_grounding_code(content: str, max_lines: int = 12) -> str:
    content = (content or "").strip()
    if not content:
        return ""

    lines = content.splitlines()
    if len(lines) <= max_lines:
        return content

    trimmed = "\n".join(lines[:max_lines])
    return f"{trimmed}\n# ... ({len(lines) - max_lines} more lines)"


def _group_groundings(groundings: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in groundings:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("nodeReference", "")).strip()
        if not ref:
            continue
        base = ref.split(".")[0] if "." in ref else ref
        grouped[base].append(item)
    return grouped


def _luminai_node_label(node: dict[str, Any]) -> str:
    form_data = (node.get("data") or {}).get("formData") or {}
    title = _clean_text(str(form_data.get("title") or ""))
    if title:
        return title

    step_type = (node.get("data") or {}).get("type", "")
    if step_type == "virtual":
        return _clean_text(str(form_data.get("name") or "virtual step"))

    objective = _clean_text(str(form_data.get("objective") or ""))
    if objective:
        return objective[:120]

    return f"Node {node.get('id', '')}"


def _luminai_node_lines(
    node: dict[str, Any],
    groundings_by_base: dict[str, list[dict[str, Any]]],
    child_map: dict[str, list[str]],
) -> list[str]:
    node_id = str(node.get("id", ""))
    data = node.get("data") or {}
    step_type = str(data.get("type") or node.get("type") or "step")
    form_data = data.get("formData") or {}
    graph_type = str(node.get("type") or "")
    label = _luminai_node_label(node)

    lines = [f"Node ID: {node_id}", f"Step type: {step_type}"]
    if graph_type and graph_type != "dynamicNode":
        lines.append(f"Graph type: {graph_type}")

    parent_id = node.get("parentId")
    if parent_id:
        lines.append(f"Parent scope: {parent_id}")

    if child_map.get(node_id):
        lines.append(f"Contains substeps: {', '.join(child_map[node_id])}")

    if label:
        lines.append(f"Label: {label}")

    objective = _clean_text(str(form_data.get("objective") or ""))
    if objective and objective != label:
        lines.append(f"Objective: {objective}")

    field_labels = {
        "integration": "Integration",
        "integration_action": "Integration action",
        "interactionType": "Interaction type",
        "termination_type": "Termination type",
    }
    for key, field_label in field_labels.items():
        value = form_data.get(key)
        if value:
            lines.append(f"{field_label}: {value}")

    output = form_data.get("output")
    if isinstance(output, dict):
        output_name = output.get("name")
        output_type = output.get("dtype")
        if output_name:
            if output_type:
                lines.append(f"Output: {output_name} ({output_type})")
            else:
                lines.append(f"Output: {output_name}")

    if step_type == "loop":
        for key in ("loopType", "loopElementName", "loopIndexName", "iterableType"):
            value = form_data.get(key)
            if value:
                lines.append(f"{key}: {value}")

    if step_type == "branch":
        branches = form_data.get("branches") or []
        if branches:
            lines.append("Branches:")
            for branch in branches:
                if not isinstance(branch, dict):
                    continue
                branch_id = branch.get("id", "")
                branch_objective = _clean_text(str(branch.get("objective") or ""))
                if branch_id and branch_objective:
                    lines.append(f"  - {branch_id}: {branch_objective}")
                elif branch_objective:
                    lines.append(f"  - {branch_objective}")

    if step_type == "virtual":
        virtual_data = form_data.get("virtualFormData") or {}
        if virtual_data:
            lines.append("Virtual configuration:")
            lines.extend(_format_config(virtual_data, indent=1))

    if step_type in ("integration", "integration_v1"):
        input_data = form_data.get("input")
        if isinstance(input_data, dict):
            safe_input = {
                key: value
                for key, value in input_data.items()
                if key not in SENSITIVE_KEYS and key != "auth"
            }
            if safe_input:
                lines.append("Integration input:")
                lines.extend(_format_config(safe_input, indent=1))

    variables = (data.get("dataflow") or {}).get("variables") or {}
    created_vars = []
    for var_key, var_info in variables.items():
        if not isinstance(var_info, dict) or not var_info.get("isCreator"):
            continue
        var_name = var_info.get("name")
        var_type = var_info.get("dtype")
        if var_name:
            if var_type:
                created_vars.append(f"{var_name} ({var_type})")
            else:
                created_vars.append(str(var_name))
    if created_vars:
        lines.append(f"Creates variables: {', '.join(created_vars)}")

    direct_groundings = groundings_by_base.get(node_id, [])
    if direct_groundings and step_type not in ("start",):
        lines.append("Automation implementation:")
        seen_snippets = set()
        for grounding in direct_groundings[:3]:
            snippet = _summarize_grounding_code(str(grounding.get("content") or ""))
            if snippet and snippet not in seen_snippets:
                seen_snippets.add(snippet)
                lines.append(snippet)
        if len(direct_groundings) > 3:
            lines.append(f"... and {len(direct_groundings) - 3} more grounded implementations")

    return lines


def _luminai_blueprint_to_text(data: dict[str, Any], source_name: str = "") -> str:
    workflow = data["workflow"]
    graph = _extract_luminai_graph(workflow) or {"nodes": [], "edges": []}
    nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
    edges = [edge for edge in graph.get("edges", []) if isinstance(edge, dict)]
    groundings = data.get("groundings") if isinstance(data.get("groundings"), list) else []
    connections = data.get("activePiecesConnections") if isinstance(data.get("activePiecesConnections"), list) else []

    workflow_name = _first_value(workflow, ("name",), default=source_name or "Workflow")
    description = _clean_text(str(workflow.get("description") or ""))
    contract_workflow = _clean_text(str(workflow.get("contractWorkflow") or ""))
    build_status = _clean_text(str(workflow.get("workflowBuildStatus") or ""))

    node_lookup = {str(node.get("id")): node for node in nodes if node.get("id") is not None}
    node_ids = list(node_lookup.keys())
    child_map: dict[str, list[str]] = defaultdict(list)
    for node in nodes:
        parent_id = node.get("parentId")
        if parent_id:
            child_map[str(parent_id)].append(str(node.get("id")))

    groundings_by_base = _group_groundings(groundings)
    graph_adj, indegree = _build_adjacency(edges)
    execution_order = _topological_order(node_ids, graph_adj, indegree)

    lines = [f"# Luminai Workflow Blueprint: {workflow_name}"]
    if build_status:
        lines.append(f"Build status: {build_status}")
    if contract_workflow:
        lines.append(f"Contract workflow: {contract_workflow}")
    if description:
        lines.append(f"\n## Overview\n{description}")
    if source_name:
        lines.append(f"\nSource file: {source_name}")

    if connections:
        lines.append("\n## Integrations")
        for conn in connections:
            if not isinstance(conn, dict):
                continue
            name = conn.get("name")
            integration_name = conn.get("integrationName")
            conn_type = conn.get("type")
            if name and integration_name:
                lines.append(f"- {name} ({integration_name}, {conn_type})")
            elif name:
                lines.append(f"- {name}")

    lines.append(f"\n## Workflow Steps ({len(nodes)} total)")
    for position, node_id in enumerate(execution_order, start=1):
        node = node_lookup.get(node_id)
        if not node:
            continue
        step_type = (node.get("data") or {}).get("type", "step")
        step_label = LUMINAI_STEP_LABELS.get(str(step_type), str(step_type))
        title = _luminai_node_label(node)
        lines.append(f"\n### Step {position}: {title}")
        lines.append(f"Category: {step_label}")
        lines.extend(_luminai_node_lines(node, groundings_by_base, child_map))

    if edges:
        lines.append(f"\n## Connections ({len(edges)} total)")
        for edge in edges:
            source = _first_value(edge, FROM_KEYS)
            target = _first_value(edge, TO_KEYS)
            if not source or not target:
                continue
            source_label = _luminai_node_label(node_lookup[source]) if source in node_lookup else source
            target_label = _luminai_node_label(node_lookup[target]) if target in node_lookup else target
            handle = _first_value(edge, ("sourceHandle",))
            if handle:
                lines.append(f"- {source_label} ({source}) -> {target_label} ({target}) [{handle}]")
            else:
                lines.append(f"- {source_label} ({source}) -> {target_label} ({target})")

    if execution_order:
        lines.append("\n## Execution Order")
        for position, node_id in enumerate(execution_order, start=1):
            node = node_lookup.get(node_id, {})
            lines.append(f"{position}. {_luminai_node_label(node)} ({node_id})")

    anchored_groundings = {
        base: items
        for base, items in groundings_by_base.items()
        if base not in node_lookup or (node_lookup[base].get("data") or {}).get("type") == "start"
    }
    if anchored_groundings:
        lines.append("\n## Grounded Automation Details")
        for base in sorted(anchored_groundings, key=lambda value: (len(anchored_groundings[value]), value), reverse=True):
            items = anchored_groundings[base]
            lines.append(f"\n### Grounding group: {base} ({len(items)} scripts)")
            seen_snippets = set()
            for grounding in items[:5]:
                snippet = _summarize_grounding_code(str(grounding.get("content") or ""), max_lines=8)
                if snippet and snippet not in seen_snippets:
                    seen_snippets.add(snippet)
                    lines.append(snippet)
            if len(items) > 5:
                lines.append(f"... and {len(items) - 5} more scripts in this group")

    return "\n".join(lines)


def _generic_blueprint_to_text(data: dict[str, Any], source_name: str = "") -> str:
    workflow_name = _first_value(data, ("name", "workflow", "title"), default=source_name or "Workflow")
    description = _first_value(data, ("description", "summary", "overview"))
    version = _first_value(data, ("version",))

    nodes = _extract_nodes(data)
    connections = _extract_connections(data)

    node_lookup: dict[str, dict[str, Any]] = {}
    node_ids: list[str] = []
    for index, node in enumerate(nodes):
        node_id = _node_id(node, index)
        node_lookup[node_id] = node
        node_ids.append(node_id)

    graph, indegree = _build_adjacency(connections)
    execution_order = _topological_order(node_ids, graph, indegree)

    lines = [f"# Workflow Blueprint: {workflow_name}"]
    if version:
        lines.append(f"Version: {version}")
    if description:
        lines.append(f"\n## Overview\n{description}")
    if source_name:
        lines.append(f"\nSource file: {source_name}")

    lines.append(f"\n## Steps ({len(nodes)} total)")
    for position, node_id in enumerate(execution_order, start=1):
        node = node_lookup.get(node_id, {})
        label = _first_value(node, LABEL_KEYS, default=node_id)
        node_type = _first_value(node, TYPE_KEYS, default="step")
        node_description = _first_value(node, DESCRIPTION_KEYS)

        lines.append(f"\n### Step {position}: {label}")
        lines.append(f"Node ID: {node_id}")
        lines.append(f"Type: {node_type}")
        if node_description:
            lines.append(f"Description: {node_description}")

        for field in ("action", "selector", "url", "input", "output", "tool", "app", "portal"):
            if field in node and node[field]:
                lines.append(f"{field.title()}: {node[field]}")

        config = node.get("config") or node.get("parameters") or node.get("params") or node.get("settings")
        config_lines = _format_config(config)
        if config_lines:
            lines.append("Configuration:")
            lines.extend(config_lines)

        for key, value in node.items():
            if key in ID_KEYS or key in LABEL_KEYS or key in TYPE_KEYS or key in DESCRIPTION_KEYS:
                continue
            if key in ("config", "parameters", "params", "settings"):
                continue
            if key in ("action", "selector", "url", "input", "output", "tool", "app", "portal"):
                continue
            if isinstance(value, (dict, list)):
                nested_lines = _format_config(value, indent=1)
                if nested_lines:
                    lines.append(f"{key}:")
                    lines.extend(nested_lines)
            elif value not in (None, ""):
                lines.append(f"{key}: {value}")

    if connections:
        lines.append(f"\n## Connections ({len(connections)} total)")
        for conn in connections:
            source = _first_value(conn, FROM_KEYS)
            target = _first_value(conn, TO_KEYS)
            label = _first_value(conn, ("label", "condition", "name", "type"))
            if not source or not target:
                continue
            if label:
                lines.append(f"- {source} -> {target} [{label}]")
            else:
                lines.append(f"- {source} -> {target}")

    if execution_order:
        lines.append("\n## Execution Order")
        for position, node_id in enumerate(execution_order, start=1):
            node = node_lookup.get(node_id, {})
            label = _first_value(node, LABEL_KEYS, default=node_id)
            lines.append(f"{position}. {label} ({node_id})")

    metadata = data.get("metadata") or data.get("meta")
    if isinstance(metadata, dict) and metadata:
        lines.append("\n## Metadata")
        lines.extend(_format_config(metadata))

    return "\n".join(lines)


def blueprint_to_text(data: dict[str, Any], source_name: str = "") -> str:
    """Convert a workflow blueprint dict into human-readable text for chunking."""
    if is_luminai_export(data):
        return _luminai_blueprint_to_text(data, source_name=source_name)
    return _generic_blueprint_to_text(data, source_name=source_name)


def read_blueprint_file(path: str) -> tuple[dict[str, Any], str]:
    """Load and validate a workflow blueprint JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("Workflow blueprint must be a JSON object")

    if not is_workflow_blueprint(data):
        raise ValueError("JSON file does not contain a recognizable workflow blueprint")

    return data, blueprint_to_text(data, source_name=os.path.basename(path))


def get_blueprint_workflow_name(data: dict[str, Any], fallback: str = "") -> str:
    """Extract the workflow name from a blueprint."""
    if is_luminai_export(data):
        workflow = data.get("workflow") or {}
        return _first_value(workflow, ("name",), default=fallback)
    return _first_value(data, ("name", "workflow", "title"), default=fallback)


def get_blueprint_stats(data: dict[str, Any]) -> dict[str, int]:
    """Return node and connection counts for a workflow blueprint."""
    if is_luminai_export(data):
        workflow = data.get("workflow") or {}
        graph = _extract_luminai_graph(workflow) or {}
        nodes = graph.get("nodes") or []
        edges = graph.get("edges") or []
        groundings = data.get("groundings") or []
        return {
            "nodes_count": len(nodes),
            "connections_count": len(edges),
            "groundings_count": len(groundings) if isinstance(groundings, list) else 0,
        }

    nodes = _extract_nodes(data)
    connections = _extract_connections(data)
    return {
        "nodes_count": len(nodes),
        "connections_count": len(connections),
        "groundings_count": 0,
    }


def find_blueprint_files(docs_dir: str) -> list[str]:
    """Return blueprint JSON filenames found in the documents directory."""
    if not os.path.isdir(docs_dir):
        return []

    blueprint_files: list[str] = []
    for name in sorted(os.listdir(docs_dir)):
        if not name.lower().endswith(".json"):
            continue
        path = os.path.join(docs_dir, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if is_workflow_blueprint(data):
                blueprint_files.append(name)
        except Exception:
            continue
    return blueprint_files
