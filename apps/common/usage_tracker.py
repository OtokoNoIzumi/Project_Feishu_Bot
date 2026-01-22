import json
from pathlib import Path
from datetime import date

BASE_DIR = Path("user_data")

class UsageTracker:
    @staticmethod
    def _get_usage_path(user_id: str) -> Path:
        return BASE_DIR / user_id / "usage_stats.json"

    @staticmethod
    def get_today_usage(user_id: str) -> dict:
        path = UsageTracker._get_usage_path(user_id)
        if not path.exists():
            return {}
            
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            today_str = date.today().isoformat()
            if data.get("date") != today_str:
                return {} # Reset if new day
                
            return data.get("counts", {})
        except Exception:
            return {}

    @staticmethod
    def increment_usage(user_id: str, feature: str):
        path = UsageTracker._get_usage_path(user_id)
        today_str = date.today().isoformat()
        
        data = {"date": today_str, "counts": {}}
        
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                    if existing.get("date") == today_str:
                        data = existing
            except Exception:
                pass
        
        current_count = data["counts"].get(feature, 0)
        data["counts"][feature] = current_count + 1
        
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
