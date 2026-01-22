import json
from pathlib import Path

GLOBAL_STATE_FILE = Path("user_data/global_state.json")

class NIDManager:
    @staticmethod
    def _load_state():
        if not GLOBAL_STATE_FILE.exists():
            GLOBAL_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            return {"next_nid": 10000, "reserved_nids": {}}
        try:
            with open(GLOBAL_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
             return {"next_nid": 10000, "reserved_nids": {}}

    @staticmethod
    def _save_state(state):
        GLOBAL_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(GLOBAL_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    @staticmethod
    def allocate_next_nid() -> int:
        """
        Allocate the next available NID starting from 10000.
        Thread-unsafe implementation (assuming single worker for now).
        """
        state = NIDManager._load_state()
        nid = state.get("next_nid", 10000)
        state["next_nid"] = nid + 1
        NIDManager._save_state(state)
        return nid

    @staticmethod
    def is_nid_available(nid: int) -> bool:
        # This is a bit tricky without scanning all users.
        # For now, we assume if it's below next_nid, it's taken unless it was reserved.
        # But the requirement implies users can SWITCH to an Unoccupied NID.
        # To strictly implement "unoccupied", we'd need a registry of all used NIDs.
        # Let's add 'used_nids' registry to global state for tracked special NIDs.
        # Auto-assigned NIDs are just > 10000.
        # If a user buys NID 888, we mark 888 as used.
        # If a user buys NID 10005, we mark 10005 as used (concurrently with auto-assign? conflict risk).
        # Let's simple model: Special NIDs < 10000. Auto NIDs >= 10000.
        # If user wants to swap to a specific NID, we check if it is in 'reserved_nids' map.

        # Simplified: We only track explicitly reserved/assigned special NIDs in the global state.
        # Normal NIDs are just consumed.
        state = NIDManager._load_state()
        reserved = state.get("reserved_nids", {})
        return str(nid) not in reserved

    @staticmethod
    def assign_nid(user_id: str, nid: int) -> bool:
        """
        Force assign a specific NID.
        Returns True if successful.
        """
        state = NIDManager._load_state()
        reserved = state.get("reserved_nids", {})

        # Check collision
        if str(nid) in reserved:
            if reserved[str(nid)] == user_id:
                return True # Already owner
            return False # Taken

        reserved[str(nid)] = user_id
        state["reserved_nids"] = reserved
        NIDManager._save_state(state)
        return True

    @staticmethod
    def release_nid(user_id: str, nid: int) -> None:
        """
        Release a NID previously assigned to this user.
        """
        state = NIDManager._load_state()
        reserved = state.get("reserved_nids", {})

        if str(nid) in reserved and reserved[str(nid)] == user_id:
            del reserved[str(nid)]
            state["reserved_nids"] = reserved
            NIDManager._save_state(state)

    @staticmethod
    def change_nid(user_id: str, profile, new_nid: int) -> tuple[bool, str]:
        """
        Change a user's NID to a new one.

        Args:
            user_id: Current user id
            profile: UserProfile object with current nid
            new_nid: The target NID to switch to

        Returns:
            (success: bool, message: str)
        """
        old_nid = profile.nid

        # Same NID, no-op
        if old_nid == new_nid:
            return True, f"NID 已是 {new_nid}，无需更改"

        # Check if new NID is available
        if not NIDManager.is_nid_available(new_nid):
            return False, f"NID {new_nid} 已被占用"

        # Release old NID if it was a reserved one
        if old_nid is not None:
            NIDManager.release_nid(user_id, old_nid)

        # Assign new NID
        success = NIDManager.assign_nid(user_id, new_nid)
        if not success:
            # Rollback: re-reserve old NID if release succeeded
            if old_nid is not None:
                NIDManager.assign_nid(user_id, old_nid)
            return False, f"NID {new_nid} 分配失败"

        # Update profile
        profile.nid = new_nid
        return True, f"NID 已更换: {old_nid or '无'} → {new_nid}"
