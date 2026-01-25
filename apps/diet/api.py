"""
Diet API Router.

Provides endpoints for diet analysis, advice generation, and record management.
"""

import asyncio
import hashlib
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, Header, UploadFile, HTTPException
from pydantic import BaseModel, Field

from apps.profile.gatekeeper import Gatekeeper
from apps.common.record_service import RecordService
from apps.common.utils import (
    decode_images_b64,
    parse_occurred_at,
    read_upload_files,
)
from apps.deps import get_current_user_id, require_auth
from apps.diet.context_provider import get_context_bundle
from apps.diet.usecases.advice import DietAdviceUsecase
from apps.diet.usecases.analyze import DietAnalyzeUsecase
from apps.llm_runtime import get_global_semaphore, get_model_limiter
from apps.settings import BackendSettings
from libs.utils.rate_limiter import AsyncRateLimiter

logger = logging.getLogger(__name__)


# --- Request Models (user_id 已移除，改用 Header 注入) ---

class DietAnalyzeRequest(BaseModel):
    """Request model for diet analysis."""

    user_note: str = ""
    images_b64: List[str] = []
    auto_save: bool = False


class DietAnalyzeResponse(BaseModel):
    """Response model for diet analysis."""

    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    saved_status: Optional[Dict[str, Any]] = None


class DietAdviceRequest(BaseModel):
    """Request model for diet advice."""

    facts: Dict[str, Any]
    user_note: str = Field(default="", description="用户输入（可选，用于理解用户意图）")


class DietAdviceResponse(BaseModel):
    """Response model for diet advice."""

    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class DietHistoryResponse(BaseModel):
    """Response model for fetching diet history."""

    success: bool
    records: List[Dict[str, Any]] = []
    error: Optional[str] = None


def build_diet_router(settings: BackendSettings) -> APIRouter:
    """Build and return the diet API router."""
    router = APIRouter()
    auth_dep = require_auth(settings)

    analyze_uc = DietAnalyzeUsecase(gemini_model_name=settings.gemini_model_name)
    advice_uc = DietAdviceUsecase(gemini_model_name=settings.gemini_model_name)

    def _get_model_limiter() -> AsyncRateLimiter:
        return get_model_limiter(settings)

    # --- Helper: 统一处理分析与自动保存逻辑 ---

    async def _process_analysis(
        user_id: str,  # 已经过 deps 解析的 resolved ID
        user_note: str,
        images_bytes: List[bytes],
        auto_save: bool,
        semaphore: asyncio.Semaphore,
        limiter: AsyncRateLimiter,
    ) -> DietAnalyzeResponse:
        """
        核心业务逻辑：并发控制 -> 调用 LLM 分析 -> (可选) 自动入库 -> 返回结果
        """
        # pylint: disable=too-many-arguments
        if (not user_note or not user_note.strip()) and not images_bytes:
            return DietAnalyzeResponse(
                success=False, error="user_note 与 images 不能同时为空"
            )

        # [Access Check]
        access = Gatekeeper.check_access(user_id, "analyze")
        if not access["allowed"]:
             raise HTTPException(
                 status_code=403, 
                 detail={
                     "code": access.get("code", "FORBIDDEN"),
                     "message": access["reason"],
                     "metadata": {k: v for k, v in access.items() if k not in ["allowed", "reason", "code"]}
                 }
             )

        # [Usage Log] Request Entrance
        access_log = (
            f"[Request] User:{user_id} | Images:{len(images_bytes)} | "
            f"Note:{bool(user_note)} | AutoSave:{auto_save}"
        )
        logger.info(access_log)

        async with semaphore:
            await limiter.check_and_wait()
            result = await analyze_uc.execute_with_image_bytes_async(
                user_note=user_note, images_bytes=images_bytes, user_id=user_id
            )
            
            # Record Usage on Success
            if isinstance(result, dict) and not result.get("error"):
                 Gatekeeper.record_usage(user_id, "analyze")

            if isinstance(result, dict) and result.get("error"):
                return DietAnalyzeResponse(
                    success=False, error=str(result.get("error"))
                )

            # 自动保存逻辑
            saved_status = None
            if auto_save:
                image_hashes = [hashlib.sha256(b).hexdigest() for b in images_bytes]
                occurred_dt = parse_occurred_at(result.get("occurred_at"))

                try:
                    saved_status = await RecordService.save_diet_record(
                        user_id=user_id,
                        meal_summary=result.get("meal_summary", {}),
                        dishes=result.get("dishes", []),
                        captured_labels=result.get("captured_labels", []),
                        image_hashes=image_hashes,
                        occurred_at=occurred_dt,
                    )
                # pylint: disable=broad-exception-caught
                except Exception as e:
                    saved_status = {"status": "error", "detail": str(e)}

            # 附带 context_bundle（today_so_far + user_target）供前端图表使用
            # 优先使用识别出的 occurred_at 日期获取当天的上下文
            target_date_str = None
            occurred_at_raw = result.get("occurred_at")
            if occurred_at_raw:
                dt = parse_occurred_at(occurred_at_raw)
                if dt:
                    target_date_str = dt.strftime("%Y-%m-%d")

            context_bundle = get_context_bundle(user_id=user_id, target_date=target_date_str)
            result["context"] = context_bundle

            return DietAnalyzeResponse(
                success=True, result=result, saved_status=saved_status
            )

    # --- Endpoints ---

    @router.post(
        "/api/diet/analyze",
        response_model=DietAnalyzeResponse,
        dependencies=[Depends(auth_dep)],
    )
    async def diet_analyze(
        req: DietAnalyzeRequest,
        user_id: str = Depends(get_current_user_id),  # 从 Header 注入
        semaphore: asyncio.Semaphore = Depends(get_global_semaphore),
        limiter: AsyncRateLimiter = Depends(_get_model_limiter),
    ):
        """异步饮食分析接口（JSON/Base64）"""
        images_bytes = decode_images_b64(req.images_b64)

        return await _process_analysis(
            user_id=user_id,
            user_note=req.user_note,
            images_bytes=images_bytes,
            auto_save=req.auto_save,
            semaphore=semaphore,
            limiter=limiter,
        )

    @router.post(
        "/api/diet/analyze_upload",
        response_model=DietAnalyzeResponse,
        dependencies=[Depends(auth_dep)],
    )
    async def diet_analyze_upload(
        user_note: str = Form(""),
        auto_save: bool = Form(False),
        images: List[UploadFile] = File(default=[], description="食品照片"),
        user_id: str = Depends(get_current_user_id),  # 从 Header 注入
        semaphore: asyncio.Semaphore = Depends(get_global_semaphore),
        limiter: AsyncRateLimiter = Depends(_get_model_limiter),
    ):
        """异步饮食分析接口（文件上传版本）"""
        # pylint: disable=too-many-arguments
        images_bytes = await read_upload_files(images)

        return await _process_analysis(
            user_id=user_id,
            user_note=user_note,
            images_bytes=images_bytes,
            auto_save=auto_save,
            semaphore=semaphore,
            limiter=limiter,
        )

    @router.post(
        "/api/diet/advice",
        response_model=DietAdviceResponse,
        dependencies=[Depends(auth_dep)],
    )
    async def diet_advice(
        req: DietAdviceRequest,
        user_id: str = Depends(get_current_user_id),  # 从 Header 注入
        semaphore: asyncio.Semaphore = Depends(get_global_semaphore),
        limiter: AsyncRateLimiter = Depends(_get_model_limiter),
    ):
        """获取饮食建议"""
        # [Access Check]
        access = Gatekeeper.check_access(user_id, "advice")
        if not access["allowed"]:
             raise HTTPException(
                 status_code=403, 
                 detail={
                     "code": access.get("code", "FORBIDDEN"),
                     "message": access["reason"],
                     "metadata": {k: v for k, v in access.items() if k not in ["allowed", "reason", "code"]}
                 }
             )

        async with semaphore:
            await limiter.check_and_wait()
            advice = await advice_uc.execute_async(
                user_id=user_id, facts=req.facts, user_note=req.user_note
            )
            print('test-advice', advice)
            if isinstance(advice, dict) and advice.get("error"):
                return DietAdviceResponse(success=False, error=str(advice.get("error")))
            
            Gatekeeper.record_usage(user_id, "advice")
            return DietAdviceResponse(success=True, result=advice)

    @router.get(
        "/api/diet/history",
        response_model=DietHistoryResponse,
        dependencies=[Depends(auth_dep)],
    )
    async def diet_history(
        user_id: str = Depends(get_current_user_id),  # 从 Header 注入
        limit: int = 20,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ):
        """获取饮食历史"""
        if start_date or end_date:
            if start_date and not end_date:
                end_date = start_date
            elif end_date and not start_date:
                start_date = end_date

            records = RecordService.get_unified_records_range(
                user_id, start_date, end_date
            )
        else:
            records = RecordService.get_recent_unified_records(
                user_id=user_id, limit=limit
            )

        return DietHistoryResponse(success=True, records=records)

    return router
