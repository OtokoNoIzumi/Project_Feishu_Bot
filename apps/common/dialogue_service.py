import os
import json
import uuid
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
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
        self._ensure_dirs()

    def _ensure_dirs(self):
        self.dialogue_dir.mkdir(parents=True, exist_ok=True)
        self.card_dir.mkdir(parents=True, exist_ok=True)

    # region 对话
    # ========== Dialogue Operations ==========

    def list_dialogues(self, limit: int = 20, offset: int = 0) -> List[Dialogue]:
        """
        List user dialogues, sorted by updated_at desc.
        Note: This reads all files to sort. For large datasets, we might need an index file.
        """
        dialogues = []
        try:
            files = list(self.dialogue_dir.glob("*.json"))
            for f in files:
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    dialogue = Dialogue(**data)
                    dialogues.append(dialogue)
                except Exception as e:
                    logger.warning(f"Failed to load dialogue {f}: {e}")
            
            # Sort by updated_at desc
            dialogues.sort(key=lambda x: x.updated_at, reverse=True)
            return dialogues[offset : offset + limit]
        except Exception as e:
            logger.error(f"Error listing dialogues: {e}")
            return []

    def get_dialogue(self, dialogue_id: str) -> Optional[Dialogue]:
        path = self.dialogue_dir / f"{dialogue_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Dialogue(**data)
        except Exception as e:
            logger.error(f"Failed to read dialogue {dialogue_id}: {e}")
            return None

    def create_dialogue(self, title: str) -> Dialogue:
        now = datetime.now()
        new_id = str(uuid.uuid4())
        dialogue = Dialogue(
            id=new_id,
            user_id=self.user_id,
            title=title,
            messages=[],
            card_ids=[],
            created_at=now,
            updated_at=now
        )
        self._save_dialogue(dialogue)
        return dialogue

    def update_dialogue(self, dialogue: Dialogue) -> Dialogue:
        dialogue.updated_at = datetime.now()
        self._save_dialogue(dialogue)
        return dialogue

    def delete_dialogue(self, dialogue_id: str) -> bool:
        path = self.dialogue_dir / f"{dialogue_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def append_message(self, dialogue_id: str, message: DialogueMessage) -> Optional[Dialogue]:
        dialogue = self.get_dialogue(dialogue_id)
        if not dialogue:
            return None
        
        dialogue.messages.append(message)
        dialogue.updated_at = datetime.now()
        self._save_dialogue(dialogue)
        return dialogue

    def update_message(self, dialogue_id: str, message: DialogueMessage) -> Optional[Dialogue]:
        dialogue = self.get_dialogue(dialogue_id)
        if not dialogue:
            return None
        
        # Find and replace
        found = False
        for i, m in enumerate(dialogue.messages):
            if m.id == message.id:
                dialogue.messages[i] = message
                found = True
                break
        
        if not found:
            return None # Or raise error

        dialogue.updated_at = datetime.now()
        self._save_dialogue(dialogue)
        return dialogue

    def _save_dialogue(self, dialogue: Dialogue):
        path = self.dialogue_dir / f"{dialogue.id}.json"
        path.write_text(
            dialogue.model_dump_json(indent=2),
            encoding="utf-8"
        )

    # endregion

    # region 卡片
    # ========== ResultCard Operations ==========

    def list_cards(self, dialogue_id: str = None) -> List[ResultCard]:
        cards = []
        try:
            files = list(self.card_dir.glob("*.json"))
            for f in files:
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    card = ResultCard(**data)
                    if dialogue_id and card.dialogue_id != dialogue_id:
                        continue
                    cards.append(card)
                except Exception as e:
                    logger.warning(f"Failed to load card {f}: {e}")
            
            cards.sort(key=lambda x: x.created_at, reverse=True)
            return cards
        except Exception as e:
            logger.error(f"Error listing cards: {e}")
            return []

    def get_card(self, card_id: str) -> Optional[ResultCard]:
        path = self.card_dir / f"{card_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return ResultCard(**data)
        except Exception as e:
            logger.error(f"Failed to read card {card_id}: {e}")
            return None

    def save_card(self, card: ResultCard) -> ResultCard:
        card.updated_at = datetime.now()
        path = self.card_dir / f"{card.id}.json"
        path.write_text(
            card.model_dump_json(indent=2),
            encoding="utf-8"
        )
        # Also update dialogue association if needed
        # (Assuming the caller handles adding card_id to dialogue.card_ids, or we do it here)
        return card

    def delete_card(self, card_id: str) -> bool:
        path = self.card_dir / f"{card_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False
        
    # endregion
