import json
import logging
from pathlib import Path
from typing import List, Optional

from libs.core.project_paths import get_project_root

logger = logging.getLogger(__name__)

class UserBioService:
    """
    Service for managing User Bio (User Memory).
    Stores explicit user facts (e.g., "I don't cook", "I am a programmer") in a JSON file.
    """

    @staticmethod
    def _get_bio_file(user_id: str) -> Path:
        root = get_project_root()
        safe_user = user_id.strip() if user_id and user_id.strip() else "no_user_id"
        return root / "user_data" / safe_user / "user_bio.json"

    @classmethod
    def load_bio(cls, user_id: str) -> List[str]:
        """Load user bio list."""
        file_path = cls._get_bio_file(user_id)
        if not file_path.exists():
            return []
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                return []
        except Exception as e:
            logger.error(f"Failed to load user bio for {user_id}: {e}")
            return []

    @classmethod
    def save_bio(cls, user_id: str, bio_list: List[str]) -> bool:
        """Save user bio list."""
        file_path = cls._get_bio_file(user_id)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(bio_list, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save user bio for {user_id}: {e}")
            return False

    @classmethod
    def update_bio(cls, user_id: str, add: Optional[List[str]] = None, remove: Optional[List[str]] = None) -> List[str]:
        """
        Update user bio by adding or removing items.
        Returns the updated user bio.
        """
        current_bio = cls.load_bio(user_id)
        
        # Helper for loose matching if needed, but for now exact match or containment
        # We'll use simple string matching for now.
        
        updated = False
        
        if remove:
            # removing logic: exact match
            initial_len = len(current_bio)
            current_bio = [x for x in current_bio if x not in remove]
            if len(current_bio) != initial_len:
                updated = True
                
        if add:
            for item in add:
                if item not in current_bio:
                    current_bio.append(item)
                    updated = True
        
        if updated:
            cls.save_bio(user_id, current_bio)
            
        return current_bio
