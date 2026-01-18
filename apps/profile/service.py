import json
import shutil
from pathlib import Path
from typing import Optional, Dict, Any
from apps.profile.schemas import UserProfile
from apps.common.record_service import RecordService

BASE_DIR = Path("user_data")

class ProfileService:
    @staticmethod
    def get_profile_path(user_id: str) -> Path:
        # user_data/u123/profile.json
        # Placed at the root of user's directory for easy access
        path = BASE_DIR / user_id / "profile.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def load_profile(user_id: str) -> UserProfile:
        path = ProfileService.get_profile_path(user_id)
        if not path.exists():
            return UserProfile()  # Return default profile
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return UserProfile.model_validate(data)
        except Exception as e:
            # Fallback to default if corrupted
            print(f"Error loading profile for {user_id}: {e}")
            return UserProfile()

    @staticmethod
    def get_profile_view(user_id: str) -> Dict[str, Any]:
        """
        Loads the 'Complete View' of the profile.
        Combines:
        1. Stored Settings (UserProfile)
        2. Latest Observed Metrics (Weight/Height from Keep Records)
        """
        # 1. Load Settings
        profile = ProfileService.load_profile(user_id)
        profile_dict = profile.model_dump()
        
        # 2. Fetch Latest State
        metrics = RecordService.get_latest_body_metrics(user_id)
        
        # 3. Merge
        # Note: 'current_weight_kg' and 'height_cm' are injected into the view
        # The frontend/LLM expects these to know the user's current status.
        profile_dict["height_cm"] = metrics.get("height_cm")
        profile_dict["current_weight_kg"] = metrics.get("weight_kg")
        
        return profile_dict

    @staticmethod
    def save_profile(user_id: str, profile: UserProfile):
        path = ProfileService.get_profile_path(user_id)
        # Backup existing
        if path.exists():
             try:
                shutil.copy2(path, str(path) + ".bak")
             except Exception: 
                 pass
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(profile.model_dump_json(indent=2))
