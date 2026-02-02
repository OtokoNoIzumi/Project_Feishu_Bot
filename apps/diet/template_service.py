import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

BASE_DIR = Path("user_data")

class DietTemplate(BaseModel):
    id: str
    title: str
    summary: Dict[str, Any]
    templateData: Dict[str, Any]
    addedAt: int

class DietTemplateService:
    @staticmethod
    def get_path(user_id: str) -> Path:
        path = BASE_DIR / user_id / "diet_templates.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def load_templates(user_id: str) -> List[DietTemplate]:
        path = DietTemplateService.get_path(user_id)
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [DietTemplate(**item) for item in data]
        except Exception:
            return []

    @staticmethod
    def save_templates(user_id: str, templates: List[DietTemplate]):
        path = DietTemplateService.get_path(user_id)
        data = [t.model_dump() for t in templates]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def add_template(user_id: str, template: DietTemplate):
        templates = DietTemplateService.load_templates(user_id)
        # Remove existing if any (update override) or duplicate ID
        templates = [t for t in templates if t.id != template.id]
        templates.insert(0, template) # Recent first
        DietTemplateService.save_templates(user_id, templates)

    @staticmethod
    def remove_template(user_id: str, template_id: str):
        templates = DietTemplateService.load_templates(user_id)
        new_templates = [t for t in templates if t.id != template_id]
        if len(new_templates) != len(templates):
            DietTemplateService.save_templates(user_id, new_templates)

    @staticmethod
    def update_template(user_id: str, template_id: str, updates: Dict[str, Any]):
        templates = DietTemplateService.load_templates(user_id)
        modified = False
        for t in templates:
            if t.id == template_id:
                if "title" in updates:
                    t.title = updates["title"]
                    modified = True
                # Add other fields if needed
        if modified:
            DietTemplateService.save_templates(user_id, templates)
