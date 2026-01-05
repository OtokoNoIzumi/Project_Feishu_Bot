import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field

from apps.deps import require_internal_auth
from apps.settings import BackendSettings
from apps.diet.usecases.analyze import DietAnalyzeUsecase
from apps.diet.usecases.commit import DietCommitUsecase
from apps.diet.usecases.history import DietHistoryUsecase
from libs.utils.rate_limiter import AsyncRateLimiter


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


# --- 并发控制（Semaphore）---
# 限制同时进行 Gemini 交互的请求数（全局总并发限制）
GLOBAL_SEMAPHORE = asyncio.Semaphore(1)


def get_global_semaphore():
    """获取全局并发信号量"""
    return GLOBAL_SEMAPHORE


# --- 频率限制（RateLimiter）---
# 不同模型的每分钟请求数限制（RPM）
# 格式：{model_name: AsyncRateLimiter(max_count, time_limit=60)}
MODEL_LIMITERS: Dict[str, AsyncRateLimiter] = {
    "gemini-2.5-flash": AsyncRateLimiter(max_count=15, time_limit=60),
    "gemini-1.5-flash": AsyncRateLimiter(max_count=15, time_limit=60),
    "gemini-1.5-pro": AsyncRateLimiter(max_count=2, time_limit=60),
    "gemini-pro": AsyncRateLimiter(max_count=2, time_limit=60),
    "default": AsyncRateLimiter(max_count=10, time_limit=60),
}


def build_diet_router(settings: BackendSettings) -> APIRouter:
    router = APIRouter()
    auth_dep = require_internal_auth(settings)

    analyze_uc = DietAnalyzeUsecase(gemini_model_name=settings.gemini_model_name)
    commit_uc = DietCommitUsecase()
    history_uc = DietHistoryUsecase()

    # 创建闭包函数，捕获 settings
    def get_model_limiter() -> AsyncRateLimiter:
        """根据配置的模型名称获取对应的限流器"""
        return MODEL_LIMITERS.get(settings.gemini_model_name, MODEL_LIMITERS["default"])

    @router.post("/api/diet/analyze", response_model=DietAnalyzeResponse, dependencies=[Depends(auth_dep)])
    async def diet_analyze(
        req: DietAnalyzeRequest,
        semaphore: asyncio.Semaphore = Depends(get_global_semaphore),
        limiter: AsyncRateLimiter = Depends(get_model_limiter),
    ):
        """
        异步饮食分析接口（支持多用户并发 + 并发限制 + 频率限制）

        - 使用 Semaphore 控制全局并发数
        - 使用 RateLimiter 控制不同模型的 RPM
        """
        # A. 检查频率限制（RPM）
        await limiter.check_and_wait()

        # B. 获取并发锁
        async with semaphore:
            # C. 执行业务（异步）
            result = await analyze_uc.execute_async(user_note=req.user_note, images_b64=req.images_b64)
            if isinstance(result, dict) and result.get("error"):
                return DietAnalyzeResponse(success=False, error=str(result.get("error")))
            return DietAnalyzeResponse(success=True, result=result)

    @router.post("/api/diet/analyze_upload", response_model=DietAnalyzeResponse, dependencies=[Depends(auth_dep)])
    async def diet_analyze_upload(
        user_id: str = Form(...),
        user_note: str = Form(""),
        images: List[UploadFile] = File(default_factory=list),
        semaphore: asyncio.Semaphore = Depends(get_global_semaphore),
        limiter: AsyncRateLimiter = Depends(get_model_limiter),
    ):
        """
        异步饮食分析接口（文件上传版本，支持多用户并发 + 并发限制 + 频率限制）
        """
        # A. 检查频率限制（RPM）
        await limiter.check_and_wait()

        # B. 读取文件（异步）
        images_bytes: List[bytes] = []
        for f in images or []:
            try:
                images_bytes.append(await f.read())
            except Exception:
                continue

        # C. 获取并发锁
        async with semaphore:
            # D. 执行业务（异步）
            result = await analyze_uc.execute_with_image_bytes_async(user_note=user_note, images_bytes=images_bytes)
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


