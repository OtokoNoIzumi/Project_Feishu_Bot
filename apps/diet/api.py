from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field

from apps.deps import require_internal_auth
from apps.settings import BackendSettings
from apps.diet.usecases.analyze import DietAnalyzeUsecase
from apps.diet.usecases.commit import DietCommitUsecase
from apps.diet.usecases.history import DietHistoryUsecase


class DietAnalyzeRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    user_note: str = ""
    images_b64: List[str] = []


class DietAnalyzeResponse(BaseModel):
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class DietCommitRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    record: Dict[str, Any]


class DietCommitResponse(BaseModel):
    success: bool
    saved_record: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class DietHistoryResponse(BaseModel):
    success: bool
    records: List[Dict[str, Any]] = []
    error: Optional[str] = None


def build_diet_router(settings: BackendSettings) -> APIRouter:
    router = APIRouter()
    auth_dep = require_internal_auth(settings)

    analyze_uc = DietAnalyzeUsecase(gemini_model_name=settings.gemini_model_name)
    commit_uc = DietCommitUsecase()
    history_uc = DietHistoryUsecase()

    @router.post("/api/diet/analyze", response_model=DietAnalyzeResponse, dependencies=[Depends(auth_dep)])
    async def diet_analyze(req: DietAnalyzeRequest):
        result = analyze_uc.execute(user_note=req.user_note, images_b64=req.images_b64)
        if isinstance(result, dict) and result.get("error"):
            return DietAnalyzeResponse(success=False, error=str(result.get("error")))
        return DietAnalyzeResponse(success=True, result=result)

    @router.post("/api/diet/analyze_upload", response_model=DietAnalyzeResponse, dependencies=[Depends(auth_dep)])
    async def diet_analyze_upload(
        user_id: str = Form(...),
        user_note: str = Form(""),
        images: List[UploadFile] = File(default_factory=list),
    ):
        images_bytes: List[bytes] = []
        for f in images or []:
            try:
                images_bytes.append(await f.read())
            except Exception:
                continue

        result = analyze_uc.execute_with_image_bytes(user_note=user_note, images_bytes=images_bytes)
        if isinstance(result, dict) and result.get("error"):
            return DietAnalyzeResponse(success=False, error=str(result.get("error")))
        return DietAnalyzeResponse(success=True, result=result)

    @router.post("/api/diet/commit", response_model=DietCommitResponse, dependencies=[Depends(auth_dep)])
    async def diet_commit(req: DietCommitRequest):
        saved = commit_uc.execute(user_id=req.user_id, record=req.record)
        return DietCommitResponse(success=True, saved_record=saved)

    @router.get("/api/diet/history", response_model=DietHistoryResponse, dependencies=[Depends(auth_dep)])
    async def diet_history(user_id: str, limit: int = 20):
        records = history_uc.execute(user_id=user_id, limit=limit)
        return DietHistoryResponse(success=True, records=records)

    return router


