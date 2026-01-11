"""
Keep API Router.

Provides endpoints for parsing Keep app screenshots (Scale, Sleep, Dimensions, or Unified)
and storing the results.
"""

import asyncio
import hashlib
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field

from apps.common.record_service import RecordService
from apps.common.utils import (
    decode_images_b64,
    parse_occurred_at,
    read_upload_files,
)
from apps.deps import require_internal_auth
from apps.keep.usecases.parse_dimensions import KeepDimensionsParseUsecase
from apps.keep.usecases.parse_scale import KeepScaleParseUsecase
from apps.keep.usecases.parse_sleep import KeepSleepParseUsecase
from apps.keep.usecases.parse_unified import KeepUnifiedParseUsecase
from apps.llm_runtime import get_global_semaphore, get_model_limiter
from apps.settings import BackendSettings
from libs.utils.rate_limiter import AsyncRateLimiter

logger = logging.getLogger(__name__)


# --- Request/Response Models ---


class KeepParseRequestBase(BaseModel):
    """Base request model for Keep parsing."""

    user_id: str = Field(..., min_length=1)
    user_note: str = ""
    images_b64: List[str] = []
    auto_save: bool = False


class KeepParseResponseBase(BaseModel):
    """Base response model for Keep parsing."""

    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    saved_status: Optional[Dict[str, Any]] = None


# Scale
class KeepScaleParseRequest(KeepParseRequestBase):
    """Request model for Keep scale parsing."""


class KeepScaleParseResponse(KeepParseResponseBase):
    """Response model for Keep scale parsing."""


# Sleep
class KeepSleepParseRequest(KeepParseRequestBase):
    """Request model for Keep sleep parsing."""


class KeepSleepParseResponse(KeepParseResponseBase):
    """Response model for Keep sleep parsing."""


# Dimensions
class KeepDimensionsParseRequest(KeepParseRequestBase):
    """Request model for Keep dimensions parsing."""


class KeepDimensionsParseResponse(KeepParseResponseBase):
    """Response model for Keep dimensions parsing."""


# Unified
class KeepUnifiedParseRequest(KeepParseRequestBase):
    """Request model for Keep unified parsing."""


class KeepUnifiedParseResponse(KeepParseResponseBase):
    """Response model for Keep unified parsing."""


def build_keep_router(settings: BackendSettings) -> APIRouter:
    router = APIRouter()
    auth_dep = require_internal_auth(settings)

    # Initialize Usecases
    scale_uc = KeepScaleParseUsecase(gemini_model_name=settings.gemini_model_name)
    sleep_uc = KeepSleepParseUsecase(gemini_model_name=settings.gemini_model_name)
    dimensions_uc = KeepDimensionsParseUsecase(
        gemini_model_name=settings.gemini_model_name
    )
    unified_uc = KeepUnifiedParseUsecase(gemini_model_name=settings.gemini_model_name)

    def _get_model_limiter() -> AsyncRateLimiter:
        return get_model_limiter(settings)

    async def _auto_save_result(
        user_id: str,
        event_type: str,
        result: Dict[str, Any],
        image_hashes: List[str] = None,
        occurred_at: datetime = None,
    ) -> Dict[str, Any]:
        """Auto-save helper for single event types"""
        try:
            data_to_save = result
            # Try to unwrap common keys if present to save cleaner data
            if event_type == "scale" and "scale_event" in result:
                data_to_save = result["scale_event"]
            elif event_type == "sleep" and "sleep_event" in result:
                data_to_save = result["sleep_event"]
            elif event_type == "dimensions" and "body_measure_event" in result:
                data_to_save = result["body_measure_event"]

            # Pass image_hashes for deduplication
            await RecordService.save_keep_event(
                user_id, event_type, data_to_save, image_hashes, occurred_at
            )
            return {"status": "success", "detail": f"Saved {event_type} event"}
        # pylint: disable=broad-exception-caught
        except Exception as e:
            return {"status": "error", "detail": str(e)}

    async def _auto_save_unified_result(
        user_id: str,
        result: Dict[str, Any],
        image_hashes: List[str] = None,
        occurred_at: datetime = None,
    ) -> Dict[str, Any]:
        """Auto-save helper for unified results"""
        saved_details = []
        try:
            for item in result.get("scale_events", []):
                await RecordService.save_keep_event(
                    user_id, "scale", item, image_hashes, occurred_at
                )
                saved_details.append("scale")

            for item in result.get("sleep_events", []):
                await RecordService.save_keep_event(
                    user_id, "sleep", item, image_hashes, occurred_at
                )
                saved_details.append("sleep")

            for item in result.get("body_measure_events", []):
                await RecordService.save_keep_event(
                    user_id, "dimensions", item, image_hashes, occurred_at
                )
                saved_details.append("dimensions")

            msg = f"Saved {len(saved_details)} items"
            if saved_details:
                msg += f": {', '.join(saved_details)}"
            return {"status": "success", "detail": msg}
        # pylint: disable=broad-exception-caught
        except Exception as e:
            return {"status": "error", "detail": str(e)}

    # --- Generic Processing Helper ---

    async def _process_parse(
        user_id: str,
        user_note: str,
        images_bytes: List[bytes],
        auto_save: bool,
        usecase: Any,
        event_type_for_save: str,  # 'scale', 'sleep', 'dimensions', or 'unified'
        semaphore: asyncio.Semaphore,
        limiter: AsyncRateLimiter,
        response_model: Any,
    ):
        """Generic processing logic for all Keep parsing endpoints."""
        # pylint: disable=too-many-arguments, too-many-locals
        # [Usage Log] Request Entrance
        access_log = (
            f"[Request] User:{user_id} | Action:keep_{event_type_for_save} | "
            f"Images:{len(images_bytes)} | Note:{bool(user_note)} | "
            f"AutoSave:{auto_save}"
        )
        logger.info(access_log)

        async with semaphore:
            await limiter.check_and_wait()
            result = await usecase.execute_with_image_bytes_async(
                user_note=user_note, images_bytes=images_bytes
            )

            if isinstance(result, dict) and result.get("error"):
                return response_model(success=False, error=str(result.get("error")))

            saved_status = None
            if auto_save:
                # Compute image hashes for deduplication
                image_hashes = [hashlib.sha256(b).hexdigest() for b in images_bytes]

                # Check for occurred_at from LLM extraction (Backfill support)
                occurred_dt = parse_occurred_at(result.get("occurred_at"))

                if event_type_for_save == "unified":
                    saved_status = await _auto_save_unified_result(
                        user_id, result, image_hashes, occurred_dt
                    )
                else:
                    saved_status = await _auto_save_result(
                        user_id, event_type_for_save, result, image_hashes, occurred_dt
                    )

            return response_model(
                success=True, result=result, saved_status=saved_status
            )

    # --- Scale Endpoints ---
    @router.post(
        "/api/keep/scale/parse",
        response_model=KeepScaleParseResponse,
        dependencies=[Depends(auth_dep)],
    )
    async def keep_scale_parse(
        req: KeepScaleParseRequest,
        semaphore: asyncio.Semaphore = Depends(get_global_semaphore),
        limiter: AsyncRateLimiter = Depends(_get_model_limiter),
    ):
        """Async parse Keep scale screenshots."""

        images_bytes = decode_images_b64(req.images_b64)

        return await _process_parse(
            req.user_id,
            req.user_note,
            images_bytes,
            req.auto_save,
            scale_uc,
            "scale",
            semaphore,
            limiter,
            KeepScaleParseResponse,
        )

    @router.post(
        "/api/keep/scale/parse_upload",
        response_model=KeepScaleParseResponse,
        dependencies=[Depends(auth_dep)],
    )
    async def keep_scale_parse_upload(
        user_id: str = Form(...),
        user_note: str = Form(""),
        auto_save: bool = Form(False),
        images: List[UploadFile] = File(default=[], description="KEEP截图"),
        semaphore: asyncio.Semaphore = Depends(get_global_semaphore),
        limiter: AsyncRateLimiter = Depends(_get_model_limiter),
    ):
        """Async parse Keep scale screenshots (upload)."""
        # pylint: disable=too-many-arguments
        images_bytes = await read_upload_files(images)
        return await _process_parse(
            user_id,
            user_note,
            images_bytes,
            auto_save,
            scale_uc,
            "scale",
            semaphore,
            limiter,
            KeepScaleParseResponse,
        )

    # --- Sleep Endpoints ---
    @router.post(
        "/api/keep/sleep/parse",
        response_model=KeepSleepParseResponse,
        dependencies=[Depends(auth_dep)],
    )
    async def keep_sleep_parse(
        req: KeepSleepParseRequest,
        semaphore: asyncio.Semaphore = Depends(get_global_semaphore),
        limiter: AsyncRateLimiter = Depends(_get_model_limiter),
    ):
        """Async parse Keep sleep screenshots."""

        images_bytes = decode_images_b64(req.images_b64)
        return await _process_parse(
            req.user_id,
            req.user_note,
            images_bytes,
            req.auto_save,
            sleep_uc,
            "sleep",
            semaphore,
            limiter,
            KeepSleepParseResponse,
        )

    @router.post(
        "/api/keep/sleep/parse_upload",
        response_model=KeepSleepParseResponse,
        dependencies=[Depends(auth_dep)],
    )
    async def keep_sleep_parse_upload(
        user_id: str = Form(...),
        user_note: str = Form(""),
        auto_save: bool = Form(False),
        images: List[UploadFile] = File(default=[], description="Keep睡眠截图"),
        semaphore: asyncio.Semaphore = Depends(get_global_semaphore),
        limiter: AsyncRateLimiter = Depends(_get_model_limiter),
    ):
        """Async parse Keep sleep screenshots (upload)."""
        # pylint: disable=too-many-arguments
        images_bytes = await read_upload_files(images)
        return await _process_parse(
            user_id,
            user_note,
            images_bytes,
            auto_save,
            sleep_uc,
            "sleep",
            semaphore,
            limiter,
            KeepSleepParseResponse,
        )

    # --- Dimensions Endpoints ---
    @router.post(
        "/api/keep/dimensions/parse",
        response_model=KeepDimensionsParseResponse,
        dependencies=[Depends(auth_dep)],
    )
    async def keep_dimensions_parse(
        req: KeepDimensionsParseRequest,
        semaphore: asyncio.Semaphore = Depends(get_global_semaphore),
        limiter: AsyncRateLimiter = Depends(_get_model_limiter),
    ):
        """Async parse Keep dimensions screenshots."""

        images_bytes = decode_images_b64(req.images_b64)
        return await _process_parse(
            req.user_id,
            req.user_note,
            images_bytes,
            req.auto_save,
            dimensions_uc,
            "dimensions",
            semaphore,
            limiter,
            KeepDimensionsParseResponse,
        )

    @router.post(
        "/api/keep/dimensions/parse_upload",
        response_model=KeepDimensionsParseResponse,
        dependencies=[Depends(auth_dep)],
    )
    async def keep_dimensions_parse_upload(
        user_id: str = Form(...),
        user_note: str = Form(""),
        auto_save: bool = Form(False),
        images: List[UploadFile] = File(default=[], description="Keep围度截图"),
        semaphore: asyncio.Semaphore = Depends(get_global_semaphore),
        limiter: AsyncRateLimiter = Depends(_get_model_limiter),
    ):
        """Async parse Keep dimensions screenshots (upload)."""
        # pylint: disable=too-many-arguments
        images_bytes = await read_upload_files(images)
        return await _process_parse(
            user_id,
            user_note,
            images_bytes,
            auto_save,
            dimensions_uc,
            "dimensions",
            semaphore,
            limiter,
            KeepDimensionsParseResponse,
        )

    # --- Unified Endpoints ---
    @router.post(
        "/api/keep/analyze",
        response_model=KeepUnifiedParseResponse,
        dependencies=[Depends(auth_dep)],
    )
    async def keep_unified_analyze(
        req: KeepUnifiedParseRequest,
        semaphore: asyncio.Semaphore = Depends(get_global_semaphore),
        limiter: AsyncRateLimiter = Depends(_get_model_limiter),
    ):
        """
        统一接口：智能分析上传的 Keep 图片（支持体重/睡眠/围度混合，支持多张图）。
        auto_save=True 时会自动拆分并保存所有识别到的事件。
        """
        # pylint: disable=too-many-arguments

        images_bytes = decode_images_b64(req.images_b64)
        return await _process_parse(
            req.user_id,
            req.user_note,
            images_bytes,
            req.auto_save,
            unified_uc,
            "unified",
            semaphore,
            limiter,
            KeepUnifiedParseResponse,
        )

    @router.post(
        "/api/keep/analyze_upload",
        response_model=KeepUnifiedParseResponse,
        dependencies=[Depends(auth_dep)],
    )
    async def keep_unified_analyze_upload(
        user_id: str = Form(...),
        user_note: str = Form(""),
        auto_save: bool = Form(False),
        images: List[UploadFile] = File(
            default=[], description="任意 Keep 截图（混合）"
        ),
        semaphore: asyncio.Semaphore = Depends(get_global_semaphore),
        limiter: AsyncRateLimiter = Depends(_get_model_limiter),
    ):
        """Async unified Keep analysis (upload)."""
        # pylint: disable=too-many-arguments
        images_bytes = await read_upload_files(images)
        return await _process_parse(
            user_id,
            user_note,
            images_bytes,
            auto_save,
            unified_uc,
            "unified",
            semaphore,
            limiter,
            KeepUnifiedParseResponse,
        )

    return router

