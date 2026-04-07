import json
import os
from typing import Dict, List, Set


class WorkflowManager:
    """Manages workflows (tags) and their associated documents."""

    def __init__(self, tags_file: str = "document_tags.json"):
        self.tags_file = tags_file

    def load_tags(self) -> Dict[str, str]:
        """Load filename → tag mappings."""
        if not os.path.exists(self.tags_file):
            return {}
        try:
            with open(self.tags_file, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            return {}

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
        
        return sorted(list(workflows))

    def get_files_for_workflow(self, workflow: str) -> List[str]:
        """Get all document filenames for a specific workflow."""
        tags = self.load_tags()
        workflow = workflow.strip()
        
        files = []
        for filename, tag in tags.items():
            if isinstance(tag, str) and tag.strip() == workflow:
                files.append(filename)
        
        return sorted(files)

    def is_valid_workflow(self, workflow: str) -> bool:
        """Check if a workflow name exists."""
        return workflow.strip() in self.get_all_workflows()


def get_workflow_manager() -> WorkflowManager:
    """Factory function to get a WorkflowManager instance."""
    return WorkflowManager()
