
import json
import logging
from pathlib import Path
from typing import Dict, Optional

from libs.core.project_paths import get_project_root

logger = logging.getLogger(__name__)

class UserMapper:
    """
    Handles user ID mapping and resolution.
    Reads from user_data/user_mapping.json to map external IDs (e.g., Clerk) 
    to internal Master IDs (e.g., Feishu OpenID).
    """

    def __init__(self, mapping_file_path: Optional[Path] = None):
        if mapping_file_path:
            self.mapping_file = mapping_file_path
        else:
            # Default to user_data/user_mapping.json if not provided
            self.mapping_file = get_project_root() / "user_data" / "user_mapping.json"
        
        self._mappings: Dict[str, str] = {}
        self._whitelist: Dict[str, dict] = {}
        self.load()

    def load(self):
        """Reloads the mapping configuration from disk."""
        if not self.mapping_file.exists():
            logger.warning(f"User mapping file not found at {self.mapping_file}, creating empty one.")
            self._create_empty_mapping_file()
            return

        try:
            with open(self.mapping_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._mappings = data.get("mappings", {})
                self._whitelist = data.get("whitelist", {})
            logger.info(f"Loaded {len(self._mappings)} user mappings.")
        except Exception as e:
            logger.error(f"Failed to load user mapping file: {e}")
            self._mappings = {}
    
    def _create_empty_mapping_file(self):
        """Creates an empty mapping file structure."""
        try:
            self.mapping_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.mapping_file, "w", encoding="utf-8") as f:
                json.dump({"mappings": {}, "whitelist": {}}, f, indent=2)
        except Exception as e:
             logger.error(f"Failed to create empty mapping file: {e}")

    def resolve_user_id(self, external_id: str) -> str:
        """
        Resolves an external ID to a Master User ID using the mapping table.
        If no mapping exists, returns the external_id itself (pass-through).
        """
        # 1. Direct mapping check
        if external_id in self._mappings:
            mapped_id = self._mappings[external_id]
            logger.info(f"Resolved User: {external_id} -> {mapped_id}")
            return mapped_id
        
        # 2. Return original ID if no mapping found
        return external_id

    def is_whitelisted(self, user_id: str) -> bool:
        """
        Checks if a user ID is in the whitelist.
        Note: Checks the RESOLVED Master ID, not necessarily the login ID.
        """
        # If whitelist is empty, we might default to allow all or allow none.
        # For now, let's assume if whitelist exists, it enforces access.
        # But if whitelist is empty in config, maybe we allow all for dev convenience?
        # Let's stick to: if whitelist defined, must be in it. If whitelist block empty, allow all?
        # Simpler: This is minimal access control. 
        if not self._whitelist:
            return True # Open access if no whitelist configured
            
        return user_id in self._whitelist

# Singleton instance for easy import
# Note: In a real app with reload, this might need lifecycle management, 
# but for file-based config, reloading on init or demand is fine.
user_mapper = UserMapper()
