import json
import os
from typing import Dict, List, Set

from workflow_blueprint import (
    find_blueprint_files,
    get_blueprint_workflow_name,
    is_workflow_blueprint,
)


class WorkflowManager:
    """Manages workflows (tags) and their associated documents."""

    def __init__(self, tags_file: str = "document_tags.json", docs_dir: str = "documents"):
        self.tags_file = tags_file
        self.docs_dir = docs_dir

    def load_tags(self) -> Dict[str, str]:
        """Load filename → tag mappings."""
        if not os.path.exists(self.tags_file):
            return {}
        try:
            with open(self.tags_file, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            return {}

    def _load_blueprint_workflow_names(self) -> Set[str]:
        workflows: Set[str] = set()
        for filename in find_blueprint_files(self.docs_dir):
            path = os.path.join(self.docs_dir, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not is_workflow_blueprint(data):
                    continue
                name = get_blueprint_workflow_name(data, fallback="")
                if name:
                    workflows.add(name)
            except Exception:
                continue
        return workflows

    def get_all_workflows(self) -> List[str]:
        """Extract and return unique workflow names (tags) sorted alphabetically."""
        tags = self.load_tags()
        workflows: Set[str] = set()
        
        for tag in tags.values():
            if isinstance(tag, str):
                # Clean up the tag
                tag = tag.strip()
                if tag:
                    workflows.add(tag)

        workflows.update(self._load_blueprint_workflow_names())
        
        return sorted(list(workflows))

    def get_files_for_workflow(self, workflow: str) -> List[str]:
        """Get all document filenames for a specific workflow."""
        tags = self.load_tags()
        workflow = workflow.strip()
        
        files = []
        for filename, tag in tags.items():
            if isinstance(tag, str) and tag.strip() == workflow:
                files.append(filename)

        for filename in find_blueprint_files(self.docs_dir):
            if filename in files:
                continue
            path = os.path.join(self.docs_dir, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                blueprint_name = get_blueprint_workflow_name(data, fallback="")
                tagged_name = tags.get(filename, "").strip() if isinstance(tags.get(filename), str) else ""
                if blueprint_name == workflow or tagged_name == workflow:
                    files.append(filename)
            except Exception:
                continue
        
        return sorted(files)

    def is_valid_workflow(self, workflow: str) -> bool:
        """Check if a workflow name exists."""
        return workflow.strip() in self.get_all_workflows()


def get_workflow_manager() -> WorkflowManager:
    """Factory function to get a WorkflowManager instance."""
    return WorkflowManager()
