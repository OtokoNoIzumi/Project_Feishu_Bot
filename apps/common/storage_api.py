"""
Storage API Router.

Provides internal endpoints for saving Keep and Diet records directly.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from apps.deps import get_current_user_id, require_internal_auth
from apps.settings import BackendSettings
from apps.common.record_service import RecordService


def build_storage_router(settings: BackendSettings) -> APIRouter:
    router = APIRouter()
    auth_dep = require_internal_auth(settings)

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
        """保存 Keep 原子事件"""
        try:
            result = await RecordService.save_keep_event(
                user_id=user_id,
                event_type=req.event_type,
                event_data=req.event_data,
                image_hashes=req.image_hashes,
                record_id=req.record_id,
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
            result = await RecordService.save_diet_record(
                user_id=user_id,
                meal_summary=req.meal_summary,
                dishes=req.dishes,
                captured_labels=req.captured_labels,
                image_hashes=req.image_hashes,
                record_id=req.record_id,
            )
            return SaveResponse(success=True, detail="Saved to ledger and library", saved_record=result)
        except Exception as e:
            return SaveResponse(success=False, detail=str(e))

    return router
