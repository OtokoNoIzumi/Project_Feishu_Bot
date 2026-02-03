"""
Storage API Router.

Provides internal endpoints for saving Keep and Diet records directly.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from apps.deps import get_current_user_id, require_auth
from apps.settings import BackendSettings
from apps.common.record_service import RecordService
from apps.common.utils import parse_occurred_at  # Local import to avoid circular dependency if any



def build_storage_router(settings: BackendSettings) -> APIRouter:
    router = APIRouter()
    auth_dep = require_auth(settings)

    # --- Keep Storage Request (user_id 已移除，改用 Header 注入) ---
    class SaveKeepEventRequest(BaseModel):
        event_type: str = Field(..., description="scale / sleep / body_measure")
        event_data: Dict[str, Any]
        image_hashes: List[str] = []
        record_id: Optional[str] = None

    class SaveResponse(BaseModel):
        success: bool
        detail: str
        saved_record: Optional[Dict[str, Any]] = None

    @router.post(
        "/api/storage/keep/save",
        response_model=SaveResponse,
        dependencies=[Depends(auth_dep)],
    )
    async def save_keep_event(
        req: SaveKeepEventRequest,
        user_id: str = Depends(get_current_user_id),  # 从 Header 注入
    ):
        """保存 Keep 原子事件 或 Unified 混合事件"""
        def _extract_keep_event_time(d: Dict[str, Any]) -> Optional[datetime]:
            # Priority 1: Explicit occurred_at
            if d.get("occurred_at"):
                dt = parse_occurred_at(d["occurred_at"])
                if dt: return dt

            # Priority 2: measured_at_local (Scale)
            if d.get("measured_at_local"):
                # Usually "YYYY-MM-DD HH:MM"
                dt = parse_occurred_at(d["measured_at_local"])
                if dt: return dt

            # Priority 3: date_str (Sleep)
            if d.get("date_str"):
                ds = d["date_str"]
                # Try combine with sleep_end_time if available
                if d.get("sleep_end_time"):
                    return parse_occurred_at(f"{ds} {d['sleep_end_time']}")
                return parse_occurred_at(f"{ds} 00:00")

            return None

        try:
            if req.event_type == "unified":
                # Unified 模式：拆包分别保存
                saved_count = 0

                # 1. Scale
                for item in req.event_data.get("scale_events", []):
                    dt = _extract_keep_event_time(item)
                    await RecordService.save_keep_event(
                        user_id=user_id,
                        event_type="scale",
                        event_data=item,
                        image_hashes=req.image_hashes, # 共用 Image Hashes
                        occurred_at=dt,
                    )
                    saved_count += 1

                # 2. Sleep
                for item in req.event_data.get("sleep_events", []):
                    dt = _extract_keep_event_time(item)
                    await RecordService.save_keep_event(
                        user_id=user_id,
                        event_type="sleep",
                        event_data=item,
                        image_hashes=req.image_hashes,
                        occurred_at=dt,
                    )
                    saved_count += 1

                # 3. Dimensions
                for item in req.event_data.get("body_measure_events", []):
                    dt = _extract_keep_event_time(item)
                    await RecordService.save_keep_event(
                        user_id=user_id,
                        event_type="dimensions",
                        event_data=item,
                        image_hashes=req.image_hashes,
                        occurred_at=dt,
                    )
                    saved_count += 1

                return SaveResponse(
                    success=True,
                    detail=f"Saved {saved_count} unified events",
                    saved_record={"record_id": req.record_id} # 返回主 ID (如果有)
                )

            else:
                # 传统单事件模式
                dt = _extract_keep_event_time(req.event_data)
                result = await RecordService.save_keep_event(
                    user_id=user_id,
                    event_type=req.event_type,
                    event_data=req.event_data,
                    image_hashes=req.image_hashes,
                    record_id=req.record_id,
                    occurred_at=dt,
                )
                return SaveResponse(success=True, detail="Saved", saved_record=result)

        except Exception as e:
            return SaveResponse(success=False, detail=str(e))

    # --- Diet Storage Request (user_id 已移除，改用 Header 注入) ---
    class SaveDietRequest(BaseModel):
        meal_summary: Dict[str, Any]
        dishes: List[Dict[str, Any]]
        captured_labels: List[Dict[str, Any]] = []
        image_hashes: List[str] = []
        record_id: Optional[str] = None
        occurred_at: Optional[str] = Field(default=None, description="ISO format datetime string")
        is_quick_record: bool = False

    @router.post(
        "/api/storage/diet/save",
        response_model=SaveResponse,
        dependencies=[Depends(auth_dep)],
    )
    async def save_diet_record(
        req: SaveDietRequest,
        user_id: str = Depends(get_current_user_id),  # 从 Header 注入
    ):
        """保存饮食记录（会自动拆分存储）"""
        try:
            # 解析 occurred_at 字符串为 datetime
            occurred_dt = None
            if req.occurred_at:
                try:
                    occurred_dt = datetime.fromisoformat(req.occurred_at.replace('Z', '+00:00'))
                except ValueError:
                    pass  # 格式错误则忽略，后端会用当前时间

            result = await RecordService.save_diet_record(
                user_id=user_id,
                meal_summary=req.meal_summary,
                dishes=req.dishes,
                captured_labels=req.captured_labels,
                image_hashes=req.image_hashes,
                record_id=req.record_id,
                occurred_at=occurred_dt,
                is_quick_record=req.is_quick_record,
            )
            return SaveResponse(success=True, detail="Saved to ledger and library", saved_record=result)
        except Exception as e:
            return SaveResponse(success=False, detail=str(e))

    return router
