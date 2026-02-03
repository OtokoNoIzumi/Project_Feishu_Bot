"""对话服务，处理对话的增删改查"""

import json
import uuid
import logging
from datetime import datetime
from typing import List, Optional
from pathlib import Path

from apps.common.models.dialogue import Dialogue, ResultCard, DialogueMessage

# 配置
USER_DATA_DIR = Path("user_data")
logger = logging.getLogger("dialogue_service")


class DialogueService:
    """
    Handle persistence for Dialogues and ResultCards.
    Stored as individual JSON files in:
    - user_data/{user_id}/dialogues/{dialogue_id}.json
    - user_data/{user_id}/cards/{card_id}.json
    """

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.dialogue_dir = USER_DATA_DIR / user_id / "dialogues"
        self.card_dir = USER_DATA_DIR / user_id / "cards"
        self.dialogue_index_path = self.dialogue_dir / "index.json"
        self.card_index_path = self.card_dir / "index.json"

        self.dialogue_index = []
        self.card_index = []

        self._ensure_dirs()
        self._load_index()
        self._load_card_index()

    def _ensure_dirs(self):
        self.dialogue_dir.mkdir(parents=True, exist_ok=True)
        self.card_dir.mkdir(parents=True, exist_ok=True)

    def _load_index(self):
        if self.dialogue_index_path.exists():
            try:
                self.dialogue_index = json.loads(
                    self.dialogue_index_path.read_text(encoding="utf-8")
                )
            except Exception as e:
                logger.error("Failed to load dialogue index: %s", e)
                self._rebuild_index()
        else:
            self._rebuild_index()

    def _rebuild_index(self):
        self.dialogue_index = []
        files = list(self.dialogue_dir.glob("*.json"))
        for f in files:
            if f.name == "index.json":
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                self.dialogue_index.append(
                    {
                        "id": data["id"],
                        "updated_at": data.get("updated_at", data["created_at"]),
                        "title": data.get("title", ""),
                    }
                )
            except Exception:
                pass
        self._save_index()

    def _save_index(self):
        try:
            self.dialogue_index_path.write_text(
                json.dumps(self.dialogue_index, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            logger.error("Failed to save index: %s", e)

    def _update_index(self, dialogue: Dialogue):
        # Remove existing if any
        self.dialogue_index = [d for d in self.dialogue_index if d["id"] != dialogue.id]
        # Add new
        self.dialogue_index.append(
            {
                "id": dialogue.id,
                "updated_at": dialogue.updated_at.isoformat(),
                "title": dialogue.title,
            }
        )
        self._save_index()

    def _remove_from_index(self, dialogue_id: str):
        self.dialogue_index = [d for d in self.dialogue_index if d["id"] != dialogue_id]
        self._save_index()

    def _generate_id(self, prefix: str) -> str:
        date_str = datetime.now().strftime("%Y%m%d")
        short_uuid = uuid.uuid4().hex[:8]
        return f"{prefix}_{date_str}_{short_uuid}"

    # ========== Card Indexing ==========

    def _load_card_index(self):
        if self.card_index_path.exists():
            try:
                self.card_index = json.loads(
                    self.card_index_path.read_text(encoding="utf-8")
                )
            except Exception as e:
                logger.error("Failed to load card index: %s", e)
                self._rebuild_card_index()
        else:
            self._rebuild_card_index()

    def _extract_card_search_info(self, data: dict) -> dict:
        def _normalize_dt(val):
            if isinstance(val, datetime):
                return val.isoformat()
            return val

        info = {
            "user_title": data.get("user_title"),
            "meal_name": "",
            "dish_names": [],
            "dish_count": 0,
            "first_dish_name": "",
            "mode": data.get("mode"),
            "diet_time": "",
            "total_energy_kj": 0,
            "total_weight_g": 0,
            "occurred_at": _normalize_dt(data.get("occurred_at")),
            "created_at": _normalize_dt(data.get("created_at")),
        }

        # Extract from latest version
        versions = data.get("versions", [])
        if versions:
            latest = versions[-1]
            raw = latest.get("raw_result", {})

            # Meal Name
            summary = raw.get("meal_summary", {})
            if summary:
                info["meal_name"] = summary.get("meal_name", "")
                info["diet_time"] = summary.get("diet_time", "") or summary.get(
                    "diet_time_label", ""
                )
                info["total_energy_kj"] = summary.get("total_energy_kj", 0) or 0
                info["total_weight_g"] = (
                    summary.get("total_weight_g", summary.get("total_weight", 0)) or 0
                )

            # Dish Names
            dishes = raw.get("dishes", [])
            names = []
            for d in dishes:
                name = d.get("standard_name") or d.get("name")
                if name:
                    names.append(name)
            info["dish_names"] = names
            info["dish_count"] = len(names)
            info["first_dish_name"] = names[0] if names else ""

        return info

    def _rebuild_card_index(self):
        self.card_index = []
        files = list(self.card_dir.glob("*.json"))
        for f in files:
            if f.name == "index.json":
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                search_info = self._extract_card_search_info(data)

                entry = {
                    "id": data["id"],
                    "updated_at": data.get("updated_at", data.get("created_at")),
                    "status": data.get("status", "draft"),
                    **search_info,
                }
                self.card_index.append(entry)
            except Exception:
                pass
        self._save_card_index()

    def _save_card_index(self):
        try:
            self.card_index_path.write_text(
                json.dumps(self.card_index, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            logger.error("Failed to save card index: %s", e)

    def _update_card_index(self, card: ResultCard):
        self.card_index = [c for c in self.card_index if c["id"] != card.id]

        # Convert model to dict to reuse extraction logic
        card_data = card.model_dump()
        search_info = self._extract_card_search_info(card_data)

        self.card_index.append(
            {
                "id": card.id,
                "updated_at": card.updated_at.isoformat(),
                "status": card.status,
                **search_info,
            }
        )
        self._save_card_index()

    def _remove_from_card_index(self, card_id: str):
        self.card_index = [c for c in self.card_index if c["id"] != card_id]
        self._save_card_index()

    # region 对话
    # ========== Dialogue Operations ==========

    def list_dialogues(self, limit: int = 20, offset: int = 0) -> List[Dialogue]:
        """
        List user dialogues, sorted by updated_at desc using index.
        """
        try:
            # Sort by updated_at desc
            sorted_index = sorted(
                self.dialogue_index, key=lambda x: x["updated_at"], reverse=True
            )
            target_entries = sorted_index[offset : offset + limit]

            dialogues = []
            for entry in target_entries:
                d = self.get_dialogue(entry["id"])
                if d:
                    # Update title if index is stale (optional, but good for consistency)
                    if d.title != entry.get("title"):
                        entry["title"] = d.title
                    dialogues.append(d)

            return dialogues
        except Exception as e:
            logger.error("Error listing dialogues: %s", e)
            return []

    def get_dialogue(self, dialogue_id: str) -> Optional[Dialogue]:
        """根据ID获取对话详情"""
        path = self.dialogue_dir / f"{dialogue_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Dialogue(**data)
        except Exception as e:
            logger.error("Failed to read dialogue %s: %s", dialogue_id, e)
            return None

    def create_dialogue(self, title: str) -> Dialogue:
        """创建一个新的对话"""
        now = datetime.now()
        new_id = self._generate_id("dialogue")
        dialogue = Dialogue(
            id=new_id,
            user_id=self.user_id,
            title=title,
            messages=[],
            card_ids=[],
            created_at=now,
            updated_at=now,
        )
        self._save_dialogue(dialogue)
        return dialogue

    def update_dialogue(self, dialogue: Dialogue) -> Dialogue:
        """更新对话的基本信息"""
        dialogue.updated_at = datetime.now()
        self._save_dialogue(dialogue)
        return dialogue

    def delete_dialogue(self, dialogue_id: str) -> bool:
        """删除指定的对话"""
        path = self.dialogue_dir / f"{dialogue_id}.json"
        if path.exists():
            path.unlink()
            self._remove_from_index(dialogue_id)
            return True
        return False

    def append_message(
        self, dialogue_id: str, message: DialogueMessage
    ) -> Optional[Dialogue]:
        """向指定对话追加一条消息"""
        dialogue = self.get_dialogue(dialogue_id)
        if not dialogue:
            return None

        # pylint: disable=no-member
        dialogue.messages.append(message)
        dialogue.updated_at = datetime.now()
        self._save_dialogue(dialogue)
        return dialogue

    def update_message(
        self, dialogue_id: str, message: DialogueMessage
    ) -> Optional[Dialogue]:
        """更新指定对话中的某条消息"""
        dialogue = self.get_dialogue(dialogue_id)
        if not dialogue:
            return None

        # Find and replace
        found = False
        for i, m in enumerate(dialogue.messages):
            if m.id == message.id:
                # pylint: disable=unsupported-assignment-operation
                dialogue.messages[i] = message
                found = True
                break

        if not found:
            return None  # Or raise error

        dialogue.updated_at = datetime.now()
        self._save_dialogue(dialogue)
        return dialogue

    def _save_dialogue(self, dialogue: Dialogue):
        path = self.dialogue_dir / f"{dialogue.id}.json"
        path.write_text(dialogue.model_dump_json(indent=2), encoding="utf-8")
        self._update_index(dialogue)

    # endregion

    # region 分析结果卡片
    # ========== ResultCard Operations ==========

    def list_cards(self, dialogue_id: str = None) -> List[ResultCard]:
        """列出分析结果卡片，支持按对话ID筛选"""
        cards = []
        try:
            files = list(self.card_dir.glob("*.json"))
            for f in files:
                if f.name == "index.json":
                    continue
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    card = ResultCard(**data)
                    if dialogue_id and card.dialogue_id != dialogue_id:
                        continue
                    cards.append(card)
                except Exception as e:
                    logger.warning("Failed to load card %s: %s", f, e)

            cards.sort(key=lambda x: x.updated_at or x.created_at, reverse=True)
            return cards
        except Exception as e:
            logger.error("Error listing cards: %s", e)
            return []

    def get_card(self, card_id: str) -> Optional[ResultCard]:
        path = self.card_dir / f"{card_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return ResultCard(**data)
        except Exception as e:
            logger.error("Failed to read card %s: %s", card_id, e)
            return None

    def save_card(self, card: ResultCard) -> ResultCard:
        # Enforce user_id
        if not card.user_id:
            card.user_id = self.user_id

        # Ensure ID format if missing (internal safeguard)
        if not card.id:
            card.id = self._generate_id("card")

        card.updated_at = datetime.now()
        path = self.card_dir / f"{card.id}.json"
        path.write_text(card.model_dump_json(indent=2), encoding="utf-8")
        self._update_card_index(card)
        return card

    def delete_card(self, card_id: str) -> bool:
        path = self.card_dir / f"{card_id}.json"
        if path.exists():
            path.unlink()
            self._remove_from_card_index(card_id)
            return True
        return False

    def get_sidebar_recent_cards(self) -> List[ResultCard]:
        """
        Logic:
        1. Get recent updated cards.
        2. Take top 2.
        3. If either is 'saved', 3rd is next recent updated.
        4. Else, try to find latest 'saved' card in last 7 days.
        5. Fallback to 3rd recent updated.
        """
        try:
            sorted_cards = sorted(
                self.card_index, key=lambda x: x["updated_at"], reverse=True
            )
            if not sorted_cards:
                return []

            result_ids = []

            # Top 2
            candidates = sorted_cards[:3]  # Get top 3 first to have pool

            if len(candidates) < 3:
                result_ids = [c["id"] for c in candidates]
            else:
                top1 = candidates[0]
                top2 = candidates[1]
                top3 = candidates[2]

                result_ids = [top1["id"], top2["id"]]

                has_saved = (top1["status"] == "saved") or (top2["status"] == "saved")

                if has_saved:
                    result_ids.append(top3["id"])
                else:
                    # Search for saved in last 7 days (excluding top1, top2)
                    seven_days_ago = datetime.now().timestamp() - 7 * 86400
                    found_saved = None

                    for c in sorted_cards[2:]:
                        if c["status"] == "saved":
                            try:
                                ts = datetime.fromisoformat(c["updated_at"]).timestamp()
                                if ts > seven_days_ago:
                                    found_saved = c
                                    break
                            except Exception:
                                pass

                    if found_saved:
                        result_ids.append(found_saved["id"])
                    else:
                        result_ids.append(top3["id"])

            # Fetch actual objects
            results = []
            for cid in result_ids:
                card = self.get_card(cid)
                if card:
                    results.append(card)
            return results

        except Exception as e:
            logger.error("Error getting recent cards: %s", e)
            return []

    # endregion
