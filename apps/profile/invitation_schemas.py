from pydantic import BaseModel
from typing import Optional, List, Dict

class InvitationCodeDefinition(BaseModel):
    code: str
    type: str = "activation"  # activation, nid_change
    account_level: Optional[str] = None
    duration_days: int = 30  # 有效期天数（仅 activation 类型）
    whitelist_features: List[str] = []
    target_nid: Optional[int] = None
    max_uses: int = 1
    used_count: int = 0
    note: Optional[str] = None

class BatchCodeManageRequest(BaseModel):
    action: str  # "add", "delete", "update"
    codes: List[InvitationCodeDefinition]
