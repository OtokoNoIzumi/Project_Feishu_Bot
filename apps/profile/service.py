import json
import shutil
from pathlib import Path
from datetime import date, datetime
from typing import Optional, Dict, Any
from apps.profile.schemas import UserProfile
from apps.common.record_service import RecordService
from apps.profile.nid_manager import NIDManager

BASE_DIR = Path("user_data")


def _calculate_age_from_birth_date(birth_date_str: Optional[str]) -> Optional[int]:
    """从 birth_date (yyyy-mm-dd) 计算足岁"""
    if not birth_date_str:
        return None
    try:
        birth = date.fromisoformat(birth_date_str)
        today = date.today()
        age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
        return age
    except ValueError:
        return None


def _birth_date_from_age(age: int) -> str:
    """从年龄反推 birth_date (假设今天是生日)"""
    today = date.today()
    birth_year = today.year - age
    return f"{birth_year}-{today.month:02d}-{today.day:02d}"


class ProfileService:
    @staticmethod
    def get_profile_path(user_id: str) -> Path:
        # user_data/u123/profile.json
        # Placed at the root of user's directory for easy access
        path = BASE_DIR / user_id / "profile.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _ensure_account_info(user_id: str, profile: UserProfile) -> bool:
        """Ensure critical account info exists. Returns True if modified."""
        from datetime import timedelta
        
        modified = False
        
        # 1. 设置注册时间
        if not profile.registered_at:
            profile.registered_at = datetime.now().isoformat()
            modified = True
        
        # 2. 分配 NID
        if not profile.nid:
            profile.nid = NIDManager.allocate_next_nid()
            modified = True
        
        # 3. 自动赠送 3 天 Basic 试用（新用户 or 迁移用户）
        if not profile.subscriptions or "basic" not in profile.subscriptions:
            trial_end = datetime.fromisoformat(profile.registered_at) + timedelta(days=3)
            if not profile.subscriptions:
                profile.subscriptions = {}
            profile.subscriptions["basic"] = trial_end.isoformat()
            modified = True
            
        return modified

    @staticmethod
    def load_profile(user_id: str) -> UserProfile:
        path = ProfileService.get_profile_path(user_id)
        if not path.exists():
            # New user entry point
            p = UserProfile()
            if ProfileService._ensure_account_info(user_id, p):
                 ProfileService.save_profile(user_id, p)
            return p
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            p = UserProfile.model_validate(data)

            # Migration for existing users
            if ProfileService._ensure_account_info(user_id, p):
                ProfileService.save_profile(user_id, p)
            return p
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
        3. Computed Age (from birth_date)
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
        
        # 4. Compute Age (centralized logic)
        profile_dict["age"] = _calculate_age_from_birth_date(profile.birth_date)
        
        return profile_dict

    @staticmethod
    def save_profile(user_id: str, profile: UserProfile):
        """
        保存 Profile。
        如果 profile.age 有值，则自动转换为 birth_date 存储。
        """
        # 如果传入了 age，转换为 birth_date
        if profile.age is not None:
            profile.birth_date = _birth_date_from_age(profile.age)
        
        path = ProfileService.get_profile_path(user_id)
        # Backup existing
        if path.exists():
             try:
                shutil.copy2(path, str(path) + ".bak")
             except Exception: 
                 pass
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(profile.model_dump_json(indent=2))
