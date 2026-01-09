import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field

from apps.deps import require_internal_auth
from apps.llm_runtime import get_global_semaphore, get_model_limiter
from apps.settings import BackendSettings
from apps.keep.usecases.parse_scale import KeepScaleParseUsecase
from apps.keep.usecases.parse_sleep import KeepSleepParseUsecase
from apps.keep.usecases.parse_dimensions import KeepDimensionsParseUsecase
from apps.keep.usecases.parse_unified import KeepUnifiedParseUsecase
from libs.utils.rate_limiter import AsyncRateLimiter


# --- Request/Response Models ---

class KeepScaleParseRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    user_note: str = ""
    images_b64: List[str] = []

class KeepScaleParseResponse(BaseModel):
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class KeepSleepParseRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    user_note: str = ""
    images_b64: List[str] = []

class KeepSleepParseResponse(BaseModel):
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class KeepDimensionsParseRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    user_note: str = ""
    images_b64: List[str] = []

class KeepDimensionsParseResponse(BaseModel):
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class KeepUnifiedParseRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    user_note: str = ""
    images_b64: List[str] = []

class KeepUnifiedParseResponse(BaseModel):
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


def build_keep_router(settings: BackendSettings) -> APIRouter:
    router = APIRouter()
    auth_dep = require_internal_auth(settings)

    # Initialize Usecases
    scale_uc = KeepScaleParseUsecase(gemini_model_name=settings.gemini_model_name)
    sleep_uc = KeepSleepParseUsecase(gemini_model_name=settings.gemini_model_name)
    dimensions_uc = KeepDimensionsParseUsecase(gemini_model_name=settings.gemini_model_name)
    unified_uc = KeepUnifiedParseUsecase(gemini_model_name=settings.gemini_model_name)

    def _get_model_limiter() -> AsyncRateLimiter:
        return get_model_limiter(settings)

    # return router  <-- Removing this line as it prevents endpoints from being registered

    # --- Scale Endpoint --- (Updated to match request)

    @router.post("/api/keep/scale/parse", response_model=KeepScaleParseResponse, dependencies=[Depends(auth_dep)])
    async def keep_scale_parse(
        req: KeepScaleParseRequest,
        semaphore: asyncio.Semaphore = Depends(get_global_semaphore),
        limiter: AsyncRateLimiter = Depends(_get_model_limiter),
    ):
        await limiter.check_and_wait()
        async with semaphore:
            result = await scale_uc.execute_async(user_note=req.user_note, images_b64=req.images_b64)
            if isinstance(result, dict) and result.get("error"):
                return KeepScaleParseResponse(success=False, error=str(result.get("error")))
            return KeepScaleParseResponse(success=True, result=result)

    @router.post(
        "/api/keep/scale/parse_upload", response_model=KeepScaleParseResponse, dependencies=[Depends(auth_dep)]
    )
    async def keep_scale_parse_upload(
        user_id: str = Form(...),
        user_note: str = Form(""),
        images: List[UploadFile] = File(default=[], description="KEEP截图"),
        semaphore: asyncio.Semaphore = Depends(get_global_semaphore),
        limiter: AsyncRateLimiter = Depends(_get_model_limiter),
    ):
        await limiter.check_and_wait()
        images_bytes: List[bytes] = []
        for f in images or []:
            try:
                images_bytes.append(await f.read())
            except Exception:
                continue

        async with semaphore:
            result = await scale_uc.execute_with_image_bytes_async(user_note=user_note, images_bytes=images_bytes)
            if isinstance(result, dict) and result.get("error"):
                return KeepScaleParseResponse(success=False, error=str(result.get("error")))
            return KeepScaleParseResponse(success=True, result=result)

    # --- Sleep Endpoint ---

    @router.post("/api/keep/sleep/parse", response_model=KeepSleepParseResponse, dependencies=[Depends(auth_dep)])
    async def keep_sleep_parse(
        req: KeepSleepParseRequest,
        semaphore: asyncio.Semaphore = Depends(get_global_semaphore),
        limiter: AsyncRateLimiter = Depends(_get_model_limiter),
    ):
        await limiter.check_and_wait()
        async with semaphore:
            result = await sleep_uc.execute_async(user_note=req.user_note, images_b64=req.images_b64)
            if isinstance(result, dict) and result.get("error"):
                return KeepSleepParseResponse(success=False, error=str(result.get("error")))
            return KeepSleepParseResponse(success=True, result=result)

    @router.post("/api/keep/sleep/parse_upload", response_model=KeepSleepParseResponse, dependencies=[Depends(auth_dep)])
    async def keep_sleep_parse_upload(
        user_id: str = Form(...),
        user_note: str = Form(""),
        images: List[UploadFile] = File(default=[], description="Keep睡眠截图"),
        semaphore: asyncio.Semaphore = Depends(get_global_semaphore),
        limiter: AsyncRateLimiter = Depends(_get_model_limiter),
    ):
        await limiter.check_and_wait()
        images_bytes: List[bytes] = []
        for f in images or []:
            try:
                images_bytes.append(await f.read())
            except Exception:
                continue

        async with semaphore:
            result = await sleep_uc.execute_with_image_bytes_async(user_note=user_note, images_bytes=images_bytes)
            if isinstance(result, dict) and result.get("error"):
                return KeepSleepParseResponse(success=False, error=str(result.get("error")))
            return KeepSleepParseResponse(success=True, result=result)

    # --- Dimensions Endpoint ---

    @router.post("/api/keep/dimensions/parse", response_model=KeepDimensionsParseResponse, dependencies=[Depends(auth_dep)])
    async def keep_dimensions_parse(
        req: KeepDimensionsParseRequest,
        semaphore: asyncio.Semaphore = Depends(get_global_semaphore),
        limiter: AsyncRateLimiter = Depends(_get_model_limiter),
    ):
        await limiter.check_and_wait()
        async with semaphore:
            result = await dimensions_uc.execute_async(user_note=req.user_note, images_b64=req.images_b64)
            if isinstance(result, dict) and result.get("error"):
                return KeepDimensionsParseResponse(success=False, error=str(result.get("error")))
            return KeepDimensionsParseResponse(success=True, result=result)

    @router.post("/api/keep/dimensions/parse_upload", response_model=KeepDimensionsParseResponse, dependencies=[Depends(auth_dep)])
    async def keep_dimensions_parse_upload(
        user_id: str = Form(...),
        user_note: str = Form(""),
        images: List[UploadFile] = File(default=[], description="Keep围度截图"),
        semaphore: asyncio.Semaphore = Depends(get_global_semaphore),
        limiter: AsyncRateLimiter = Depends(_get_model_limiter),
    ):
        await limiter.check_and_wait()
        images_bytes: List[bytes] = []
        for f in images or []:
            try:
                images_bytes.append(await f.read())
            except Exception:
                continue

        async with semaphore:
            result = await dimensions_uc.execute_with_image_bytes_async(user_note=user_note, images_bytes=images_bytes)
            if isinstance(result, dict) and result.get("error"):
                return KeepDimensionsParseResponse(success=False, error=str(result.get("error")))
            return KeepDimensionsParseResponse(success=True, result=result)


    # --- Unified Endpoint ---

    @router.post("/api/keep/analyze", response_model=KeepUnifiedParseResponse, dependencies=[Depends(auth_dep)])
    async def keep_unified_analyze(
        req: KeepUnifiedParseRequest,
        semaphore: asyncio.Semaphore = Depends(get_global_semaphore),
        limiter: AsyncRateLimiter = Depends(_get_model_limiter),
    ):
        """
        统一接口：智能分析上传的 Keep 图片（支持体重/睡眠/围度混合，支持多张图）。
        """
        await limiter.check_and_wait()
        async with semaphore:
            result = await unified_uc.execute_async(user_note=req.user_note, images_b64=req.images_b64)
            if isinstance(result, dict) and result.get("error"):
                return KeepUnifiedParseResponse(success=False, error=str(result.get("error")))
            return KeepUnifiedParseResponse(success=True, result=result)

    @router.post("/api/keep/analyze_upload", response_model=KeepUnifiedParseResponse, dependencies=[Depends(auth_dep)])
    async def keep_unified_analyze_upload(
        user_id: str = Form(...),
        user_note: str = Form(""),
        images: List[UploadFile] = File(default=[], description="任意 Keep 截图（混合）"),
        semaphore: asyncio.Semaphore = Depends(get_global_semaphore),
        limiter: AsyncRateLimiter = Depends(_get_model_limiter),
    ):
        """
        统一接口（上传版）：适合 Swagger 测试。支持多图混合上传。
        """
        await limiter.check_and_wait()
        images_bytes: List[bytes] = []
        for f in images or []:
            try:
                images_bytes.append(await f.read())
            except Exception:
                continue

        async with semaphore:
            result = await unified_uc.execute_with_image_bytes_async(user_note=user_note, images_bytes=images_bytes)
            if isinstance(result, dict) and result.get("error"):
                return KeepUnifiedParseResponse(success=False, error=str(result.get("error")))
            return KeepUnifiedParseResponse(success=True, result=result)

    return router
