import json
from pathlib import Path
from datetime import datetime
from apps.profile.service import ProfileService
from apps.common.usage_tracker import UsageTracker

CONFIG_PATH = Path(__file__).parent / "config" / "feature_config.json"

class Gatekeeper:
    _config = None

    @classmethod
    def load_config(cls):
        if cls._config:
            return cls._config
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                    cls._config = json.load(f)
            except Exception:
                cls._config = {}
        else:
            cls._config = {}
        return cls._config

    @classmethod
    def get_limits(cls):
        """
        Returns limits config.
        New format: { "feature": { "level": limit_number } }
        -1 means unlimited.
        """
        cfg = cls.load_config()
        return cfg.get("limits", {})

    @classmethod
    def get_locked_features(cls):
        """Returns list of features that require whitelist_features."""
        cfg = cls.load_config()
        return cfg.get("locked_features", [])

    @classmethod
    def get_levels_order(cls):
        cfg = cls.load_config()
        # Default order: Low -> High
        return cfg.get("levels", ["basic", "pro", "ultra"])

    @staticmethod
    def get_current_effective_level(profile):
        """
        Determine the current highest effective level based on subscriptions.
        Returns: (level_code, expiry_datetime_obj_or_None)
        """
        config_levels = Gatekeeper.get_levels_order()
        
        now = datetime.now()
        subs = profile.subscriptions or {}

        # Check Subscriptions from highest to lowest
        for lvl in reversed(config_levels):
            expiry_str = subs.get(lvl)
            if expiry_str:
                try:
                    expiry_dt = datetime.fromisoformat(expiry_str)
                    if expiry_dt > now:
                        return lvl, expiry_dt
                except:
                    pass
        
        return "expired", None

    @staticmethod
    def check_access(user_id: str, feature: str, amount: int = 1) -> dict:
        """
        Check if user can access feature.
        
        Logic:
        1. Locked Features (in locked_features list):
           - Requires feature in user's whitelist_features
        2. Standard Features:
           - Check per-level daily limit from config
           - -1 = unlimited
        """
        profile = ProfileService.load_profile(user_id)
        current_level, expiry = Gatekeeper.get_current_effective_level(profile)
        
        # --- 1. Check if feature is locked (requires whitelist) ---
        locked_features = Gatekeeper.get_locked_features()
        if feature in locked_features:
            if feature in profile.whitelist_features:
                return {"allowed": True, "reason": "Feature Unlocked"}
            return {
                "allowed": False,
                "code": "FEATURE_LOCKED",
                "reason": f"此功能需要单独解锁"
            }
        
        # --- 2. Check expiry ---
        if current_level == "expired":
            return {
                "allowed": False,
                "code": "SUBSCRIPTION_EXPIRED",
                "reason": "订阅已过期，请续费"
            }
        
        # --- 3. Check per-level daily limit ---
        limits = Gatekeeper.get_limits()
        feature_limits = limits.get(feature, {})
        
        # Get limit for current level (default: 5 for basic, 10 for pro, -1 for ultra)
        default_limits = {"basic": 5, "pro": 10, "ultra": -1}
        limit = feature_limits.get(current_level, default_limits.get(current_level, 5))
        
        # -1 means unlimited
        if limit == -1:
            return {"allowed": True, "reason": f"Unlimited ({current_level})"}
        
        # Check usage
        usage = UsageTracker.get_today_usage(user_id)
        current = usage.get(feature, 0)
        
        if current + amount > limit:
            return {
                "allowed": False,
                "code": "DAILY_LIMIT_REACHED",
                "limit": limit,
                "current": current,
                "reason": f"今日次数已用完 ({current}/{limit})"
            }
        
        remaining = limit - current
        return {
            "allowed": True,
            "reason": f"剩余 {remaining}/{limit}",
            "remaining": remaining,
            "limit": limit
        }

    @staticmethod
    def record_usage(user_id: str, feature: str, amount: int = 1):
        UsageTracker.increment_usage(user_id, feature, amount)
