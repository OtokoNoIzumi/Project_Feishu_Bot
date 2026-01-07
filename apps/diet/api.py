import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field

from apps.deps import require_internal_auth
from apps.llm_runtime import get_global_semaphore, get_model_limiter
from apps.settings import BackendSettings
from apps.diet.usecases.advice import DietAdviceUsecase
from apps.diet.usecases.analyze import DietAnalyzeUsecase
from apps.diet.usecases.commit import DietCommitUsecase
from apps.diet.usecases.history import DietHistoryUsecase
from libs.utils.rate_limiter import AsyncRateLimiter


def _has_any_input(user_note: str, images_b64: List[str]) -> bool:
    if user_note and user_note.strip():
        return True
    for s in images_b64 or []:
        if s and str(s).strip():
            return True
    return False


class DietAnalyzeRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    user_note: str = ""
    images_b64: List[str] = []


class DietAnalyzeResponse(BaseModel):
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class DietAdviceRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    facts: Dict[str, Any]
    user_note: str = Field(default="", description="用户输入（可选，用于理解用户意图）")


class DietAdviceResponse(BaseModel):
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
    advice_uc = DietAdviceUsecase(gemini_model_name=settings.gemini_model_name)
    commit_uc = DietCommitUsecase()
    history_uc = DietHistoryUsecase()

    # 创建闭包函数，捕获 settings
    def _get_model_limiter() -> AsyncRateLimiter:
        return get_model_limiter(settings)

    @router.post("/api/diet/analyze", response_model=DietAnalyzeResponse, dependencies=[Depends(auth_dep)])
    async def diet_analyze(
        req: DietAnalyzeRequest,
        semaphore: asyncio.Semaphore = Depends(get_global_semaphore),
        limiter: AsyncRateLimiter = Depends(_get_model_limiter),
    ):
        """
        异步饮食分析接口（支持多用户并发 + 并发限制 + 频率限制）

        - 使用 Semaphore 控制全局并发数
        - 使用 RateLimiter 控制不同模型的 RPM
        """
        if not _has_any_input(req.user_note, req.images_b64):
            return DietAnalyzeResponse(success=False, error="user_note 与 images_b64 不能同时为空")

        async with semaphore:
            await limiter.check_and_wait()
            result = await analyze_uc.execute_async(user_note=req.user_note, images_b64=req.images_b64)
            if isinstance(result, dict) and result.get("error"):
                return DietAnalyzeResponse(success=False, error=str(result.get("error")))
            return DietAnalyzeResponse(success=True, result=result)

    @router.post("/api/diet/analyze_upload", response_model=DietAnalyzeResponse, dependencies=[Depends(auth_dep)])
    async def diet_analyze_upload(
        user_id: str = Form(...),
        user_note: str = Form(""),
        images: List[UploadFile] = File(default=[], description="食品照片"),
        semaphore: asyncio.Semaphore = Depends(get_global_semaphore),
        limiter: AsyncRateLimiter = Depends(_get_model_limiter),
    ):
        """
        异步饮食分析接口（文件上传版本，支持多用户并发 + 并发限制 + 频率限制）
        """
        # B. 读取文件（异步）
        images_bytes: List[bytes] = []
        for f in images or []:
            try:
                images_bytes.append(await f.read())
            except Exception:
                continue

        if (not user_note or not user_note.strip()) and not images_bytes:
            return DietAnalyzeResponse(success=False, error="user_note 与 images 不能同时为空")

        async with semaphore:
            await limiter.check_and_wait()
            result = await analyze_uc.execute_with_image_bytes_async(user_note=user_note, images_bytes=images_bytes)
            if isinstance(result, dict) and result.get("error"):
                return DietAnalyzeResponse(success=False, error=str(result.get("error")))
            return DietAnalyzeResponse(success=True, result=result)

    @router.post("/api/diet/advice", response_model=DietAdviceResponse, dependencies=[Depends(auth_dep)])
    async def diet_advice(
        req: DietAdviceRequest,
        semaphore: asyncio.Semaphore = Depends(get_global_semaphore),
        limiter: AsyncRateLimiter = Depends(_get_model_limiter),
    ):
        async with semaphore:
            await limiter.check_and_wait()
            advice = await advice_uc.execute_async(user_id=req.user_id, facts=req.facts, user_note=req.user_note)
            if isinstance(advice, dict) and advice.get("error"):
                return DietAdviceResponse(success=False, error=str(advice.get("error")))
            return DietAdviceResponse(success=True, result=advice)

    @router.post("/api/diet/commit", response_model=DietCommitResponse, dependencies=[Depends(auth_dep)])
    async def diet_commit(req: DietCommitRequest):
        saved = commit_uc.execute(user_id=req.user_id, record=req.record)
        return DietCommitResponse(success=True, saved_record=saved)

    @router.get("/api/diet/history", response_model=DietHistoryResponse, dependencies=[Depends(auth_dep)])
    async def diet_history(user_id: str, limit: int = 20):
        records = history_uc.execute(user_id=user_id, limit=limit)
        return DietHistoryResponse(success=True, records=records)

    return router


