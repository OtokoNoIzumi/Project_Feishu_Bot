from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Body
from pydantic import BaseModel, Field

from apps.deps import require_internal_auth
from apps.settings import BackendSettings
from apps.common.record_service import RecordService


def build_storage_router(settings: BackendSettings) -> APIRouter:
    router = APIRouter()
    auth_dep = require_internal_auth(settings)

    # --- Keep Storage Request ---
    class SaveKeepEventRequest(BaseModel):
        user_id: str
        event_type: str = Field(..., description="scale / sleep / body_measure")
        event_data: Dict[str, Any]

    class SaveResponse(BaseModel):
        success: bool
        detail: str

    @router.post(
        "/api/storage/keep/save",
        response_model=SaveResponse,
        dependencies=[Depends(auth_dep)],
    )
    async def save_keep_event(req: SaveKeepEventRequest):
        """保存 Keep 原子事件"""
        try:
            await RecordService.save_keep_event(
                req.user_id, req.event_type, req.event_data
            )
            return SaveResponse(success=True, detail="Saved")
        except Exception as e:
            return SaveResponse(success=False, detail=str(e))

    # --- Diet Storage Request ---
    class SaveDietRequest(BaseModel):
        user_id: str
        meal_summary: Dict[str, Any]
        dishes: List[Dict[str, Any]]
        captured_labels: List[Dict[str, Any]] = []

    @router.post(
        "/api/storage/diet/save",
        response_model=SaveResponse,
        dependencies=[Depends(auth_dep)],
    )
    async def save_diet_record(req: SaveDietRequest):
        """保存饮食记录（会自动拆分存储）"""
        try:
            await RecordService.save_diet_record(
                req.user_id, req.meal_summary, req.dishes, req.captured_labels
            )
            return SaveResponse(success=True, detail="Saved to ledger and library")
        except Exception as e:
            return SaveResponse(success=False, detail=str(e))

    return router
