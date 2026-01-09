import asyncio
import base64
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field

from apps.deps import require_internal_auth
from apps.llm_runtime import get_global_semaphore, get_model_limiter
from apps.settings import BackendSettings
from apps.diet.usecases.advice import DietAdviceUsecase
from apps.diet.usecases.analyze import DietAnalyzeUsecase

from apps.common.record_service import RecordService
from libs.utils.rate_limiter import AsyncRateLimiter

logger = logging.getLogger(__name__)


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
    auto_save: bool = False  # 新增控制开关，默认为 False


class DietAnalyzeResponse(BaseModel):
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    saved_status: Optional[Dict[str, Any]] = None  # 返回保存状态


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


    # 创建闭包函数，捕获 settings
    def _get_model_limiter() -> AsyncRateLimiter:
        return get_model_limiter(settings)

    # --- Helper: 统一处理分析与自动保存逻辑 ---


    async def _process_analysis(
        user_id: str,
        user_note: str,
        images_bytes: List[bytes],
        auto_save: bool,
        semaphore: asyncio.Semaphore,
        limiter: AsyncRateLimiter,
    ) -> DietAnalyzeResponse:
        """
        核心业务逻辑：并发控制 -> 调用 LLM 分析 -> (可选) 自动入库 -> 返回结果
        """
        # [Usage Log] Request Entrance
        access_log = f"[Request] User:{user_id} | Images:{len(images_bytes)} | Note:{bool(user_note)} | AutoSave:{auto_save}"
        logger.info(access_log)

        if (not user_note or not user_note.strip()) and not images_bytes:
            return DietAnalyzeResponse(success=False, error="user_note 与 images 不能同时为空")

        async with semaphore:
            await limiter.check_and_wait()
            # 统一使用的是 bytes 版本，因为 Base64 在入口处已被解码
            result = await analyze_uc.execute_with_image_bytes_async(user_note=user_note, images_bytes=images_bytes)
            
            if isinstance(result, dict) and result.get("error"):
                return DietAnalyzeResponse(success=False, error=str(result.get("error")))

            # 自动保存逻辑
            saved_status = None
            if auto_save:
                try:
                    saved_status = await RecordService.save_diet_record(
                        user_id=user_id,
                        meal_summary=result.get("meal_summary", {}),
                        dishes=result.get("dishes", []),
                        captured_labels=result.get("captured_labels", [])
                    )
                except Exception as e:
                    saved_status = {"status": "error", "detail": str(e)}

            return DietAnalyzeResponse(success=True, result=result, saved_status=saved_status)

    @router.post("/api/diet/analyze", response_model=DietAnalyzeResponse, dependencies=[Depends(auth_dep)])
    async def diet_analyze(
        req: DietAnalyzeRequest,
        semaphore: asyncio.Semaphore = Depends(get_global_semaphore),
        limiter: AsyncRateLimiter = Depends(_get_model_limiter),
    ):
        """
        异步饮食分析接口（JSON/Base64）
        """
        # A. 预处理：Base64 -> Bytes
        # 注意：这里需要引入 base64 模块或者复用 usecase 里的解码逻辑
        # 为了保持 controller干净，我们这里简单解码，或者最好复用 private helper
        # 但 analyze_uc.execute_async 是接受 b64 的。
        # 为了复用 _process_analysis (它接受 bytes)，我们需要在这里解码。

        images_bytes = []
        for s in req.images_b64 or []:
            if s:
                try:
                    images_bytes.append(base64.b64decode(s))
                except:
                    continue

        return await _process_analysis(
            user_id=req.user_id,
            user_note=req.user_note,
            images_bytes=images_bytes,
            auto_save=req.auto_save,
            semaphore=semaphore,
            limiter=limiter,
        )

    @router.post("/api/diet/analyze_upload", response_model=DietAnalyzeResponse, dependencies=[Depends(auth_dep)])
    async def diet_analyze_upload(
        user_id: str = Form(...),
        user_note: str = Form(""),
        auto_save: bool = Form(False),
        images: List[UploadFile] = File(default=[], description="食品照片"),
        semaphore: asyncio.Semaphore = Depends(get_global_semaphore),
        limiter: AsyncRateLimiter = Depends(_get_model_limiter),
    ):
        """
        异步饮食分析接口（文件上传版本）
        """
        # A. 预处理：UploadFile -> Bytes
        images_bytes: List[bytes] = []
        for f in images or []:
            try:
                images_bytes.append(await f.read())
            except Exception:
                continue

        return await _process_analysis(
            user_id=user_id,
            user_note=user_note,
            images_bytes=images_bytes,
            auto_save=auto_save,
            semaphore=semaphore,
            limiter=limiter,
        )


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
        # Flatten the structure if needed or pass as is if RecordService supports it.
        # RecordService.save_diet_record expects unpacked args.
        saved = await RecordService.save_diet_record(
            user_id=req.user_id,
            meal_summary=req.record.get("meal_summary", {}),
            dishes=req.record.get("dishes", []),
            captured_labels=req.record.get("labels_snapshot", [])
        )
        return DietCommitResponse(success=True, saved_record=saved)

    @router.get("/api/diet/history", response_model=DietHistoryResponse, dependencies=[Depends(auth_dep)])
    async def diet_history(user_id: str, limit: int = 20):
        records = RecordService.get_recent_diet_records(user_id=user_id, limit=limit)
        return DietHistoryResponse(success=True, records=records)

    return router


