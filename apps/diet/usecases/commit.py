from typing import Any, Dict

from libs.user_data.jsonl_store import JSONLStore


class DietCommitUsecase:
    def __init__(self):
        self.store = JSONLStore(namespace="diet")

    def execute(self, user_id: str, record: Dict[str, Any]) -> Dict[str, Any]:
        return self.store.append(user_id=user_id, record=record)


