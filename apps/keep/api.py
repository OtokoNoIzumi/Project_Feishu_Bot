import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field

from apps.deps import require_internal_auth
from apps.llm_runtime import get_global_semaphore, get_model_limiter
from apps.settings import BackendSettings
from apps.keep.usecases.parse_scale import KeepScaleParseUsecase
from libs.utils.rate_limiter import AsyncRateLimiter


class KeepScaleParseRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    user_note: str = ""
    images_b64: List[str] = []


class KeepScaleParseResponse(BaseModel):
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


def build_keep_router(settings: BackendSettings) -> APIRouter:
    router = APIRouter()
    auth_dep = require_internal_auth(settings)

    parse_uc = KeepScaleParseUsecase(gemini_model_name=settings.gemini_model_name)

    def _get_model_limiter() -> AsyncRateLimiter:
        return get_model_limiter(settings)

    @router.post("/api/keep/scale/parse", response_model=KeepScaleParseResponse, dependencies=[Depends(auth_dep)])
    async def keep_scale_parse(
        req: KeepScaleParseRequest,
        semaphore: asyncio.Semaphore = Depends(get_global_semaphore),
        limiter: AsyncRateLimiter = Depends(_get_model_limiter),
    ):
        await limiter.check_and_wait()
        async with semaphore:
            result = await parse_uc.execute_async(user_note=req.user_note, images_b64=req.images_b64)
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
        # images: List[UploadFile] = File(default_factory=list, description="KEEP截图"),
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
            result = await parse_uc.execute_with_image_bytes_async(user_note=user_note, images_bytes=images_bytes)
            if isinstance(result, dict) and result.get("error"):
                return KeepScaleParseResponse(success=False, error=str(result.get("error")))
            return KeepScaleParseResponse(success=True, result=result)

    return router



