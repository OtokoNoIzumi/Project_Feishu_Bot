from typing import Any, Dict, List

from libs.user_data.jsonl_store import JSONLStore


class DietHistoryUsecase:
    def __init__(self):
        self.store = JSONLStore(namespace="diet")

    def execute(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        return self.store.read_latest(user_id=user_id, limit=limit)


