import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List
from apps.profile.invitation_schemas import InvitationCodeDefinition
from apps.profile.service import ProfileService
from apps.profile.gatekeeper import Gatekeeper
from apps.profile.nid_manager import NIDManager

INVITATION_FILE = Path("user_data/invitation_codes.json")

class InvitationManager:
    @staticmethod
    def _load_codes() -> Dict[str, dict]:
        if not INVITATION_FILE.exists():
            return {}
        try:
            with open(INVITATION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    @staticmethod
    def _save_codes(codes: Dict[str, dict]):
        INVITATION_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(INVITATION_FILE, "w", encoding="utf-8") as f:
            json.dump(codes, f, indent=2)

    @staticmethod
    def validate_code(code: str) -> Optional[InvitationCodeDefinition]:
        codes = InvitationManager._load_codes()
        if code not in codes:
            return None

        data = codes[code]
        definition = InvitationCodeDefinition(**data)

        if definition.used_count >= definition.max_uses:
            return None

        return definition

    @staticmethod
    def redeem_code(code: str, user_id: str):
        """
        Redeem a code and apply it to the user.
        Logic:
        - If Activation code: Apply subscription extension logic (Parallel Extension).
        - If NID Change code: Apply NID change.
        Returns: feature specific response dict or raises ValueError
        """

        # 1. Validate Code
        codes = InvitationManager._load_codes()
        if code not in codes:
            raise ValueError("Invalid Invitation Code")

        data = codes[code]
        definition = InvitationCodeDefinition(**data)

        if definition.used_count >= definition.max_uses:
            raise ValueError("Invitation Code Exhausted")

        # 2. Check if user already redeemed this code
        used_by = data.get("used_by", [])
        if user_id in used_by:
            raise ValueError("您已使用过此邀请码")

        # 3. Load User
        profile = ProfileService.load_profile(user_id)

        message = "Applied"

        # 3. Apply Effect
        if definition.type == "activation":
            target_level = definition.account_level
            duration = definition.duration_days

            if not target_level or not duration:
                raise ValueError("Invalid Code Configuration")

            # Load Levels Order to determining "Lower or Equal"
            levels = Gatekeeper.get_levels_order() # e.g. [trial, basic, pro, ultra]
            try:
                target_idx = levels.index(target_level)
            except ValueError:
                # If unknown level, maybe it is legacy like 'monthly', treat as basic?
                # For safety, map to basic or skip logic
                return {"success": False, "message": "Unknown Level in Code"}

            # Parallel Extension Logic:
            # Extend target_level AND all levels below it
            now = datetime.now()
            subs = profile.subscriptions or {}

            applied_levels = []

            for i in range(len(levels)):
                lvl = levels[i]

                # Only affect levels <= target_level (index <= target_idx)
                if i <= target_idx:
                    current_expiry_str = subs.get(lvl)
                    current_expiry = now

                    if current_expiry_str:
                        try:
                            dt = datetime.fromisoformat(current_expiry_str)
                            if dt > now:
                                current_expiry = dt
                        except:
                            pass

                    new_expiry = current_expiry + timedelta(days=duration)
                    subs[lvl] = new_expiry.isoformat()
                    applied_levels.append(lvl)

            profile.subscriptions = subs

            if definition.whitelist_features:
                current_wl = set(profile.whitelist_features)
                current_wl.update(definition.whitelist_features)
                profile.whitelist_features = list(current_wl)

            message = f"Subscription Extended: {target_level.upper()} +{duration} days"
            if len(applied_levels) > 1:
                message += f" (and lower tiers)"

        elif definition.type == "nid_change":
            # NID Change Logic
            if not definition.target_nid:
                raise ValueError("Invalid NID Configuration")

            success, msg = NIDManager.change_nid(user_id, profile, definition.target_nid)
            if not success:
                raise ValueError(msg)
            message = msg

        # 4. Save User & Code Usage
        ProfileService.save_profile(user_id, profile)

        # Record this user as having used the code
        definition.used_count += 1
        code_data = definition.model_dump()
        code_data["used_by"] = used_by + [user_id]  # Append to used_by list
        codes[code] = code_data
        InvitationManager._save_codes(codes)

        return {"success": True, "message": message, "profile": profile.model_dump()}

    @staticmethod
    def manage_codes(action: str, target_codes: List[InvitationCodeDefinition]):
        codes = InvitationManager._load_codes()

        for item in target_codes:
            if action == "add" or action == "update":
                codes[item.code] = item.model_dump()
            elif action == "delete":
                if item.code in codes:
                    del codes[item.code]

        InvitationManager._save_codes(codes)
