import asyncio
import base64
import logging
import hashlib
from datetime import datetime
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
from apps.common.record_service import RecordService
from libs.utils.rate_limiter import AsyncRateLimiter

logger = logging.getLogger(__name__)


# --- Request/Response Models ---


class KeepParseRequestBase(BaseModel):
    user_id: str = Field(..., min_length=1)
    user_note: str = ""
    images_b64: List[str] = []
    auto_save: bool = False


class KeepParseResponseBase(BaseModel):
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    saved_status: Optional[Dict[str, Any]] = None


# Scale
class KeepScaleParseRequest(KeepParseRequestBase):
    pass


class KeepScaleParseResponse(KeepParseResponseBase):
    pass


# Sleep
class KeepSleepParseRequest(KeepParseRequestBase):
    pass


class KeepSleepParseResponse(KeepParseResponseBase):
    pass


# Dimensions
class KeepDimensionsParseRequest(KeepParseRequestBase):
    pass


class KeepDimensionsParseResponse(KeepParseResponseBase):
    pass


# Unified
class KeepUnifiedParseRequest(KeepParseRequestBase):
    pass


class KeepUnifiedParseResponse(KeepParseResponseBase):
    pass


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
        # [Usage Log] Request Entrance
        access_log = f"[Request] User:{user_id} | Action:keep_{event_type_for_save} | Images:{len(images_bytes)} | Note:{bool(user_note)} | AutoSave:{auto_save}"
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
                occurred_dt = None
                oa_str = result.get("occurred_at")
                if oa_str:
                    try:
                        # Try parsing YYYY-MM-DD HH:MM:SS
                        # Handle potential YYYY-MM-DD HH:MM if SS missing
                        if len(oa_str) == 16:
                            oa_str += ":00"
                        occurred_dt = datetime.fromisoformat(oa_str.replace(" ", "T"))
                    except:
                        pass

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

        images_bytes = []
        for s in req.images_b64 or []:
            if s:
                try:
                    images_bytes.append(base64.b64decode(s))
                except:
                    continue

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
        images_bytes = []
        for f in images or []:
            try:
                images_bytes.append(await f.read())
            except:
                continue
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

        images_bytes = []
        for s in req.images_b64 or []:
            if s:
                try:
                    images_bytes.append(base64.b64decode(s))
                except:
                    continue
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
        images_bytes = []
        for f in images or []:
            try:
                images_bytes.append(await f.read())
            except:
                continue
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

        images_bytes = []
        for s in req.images_b64 or []:
            if s:
                try:
                    images_bytes.append(base64.b64decode(s))
                except:
                    continue
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
        images_bytes = []
        for f in images or []:
            try:
                images_bytes.append(await f.read())
            except:
                continue
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

        images_bytes = []
        for s in req.images_b64 or []:
            if s:
                try:
                    images_bytes.append(base64.b64decode(s))
                except:
                    continue
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
        images_bytes = []
        for f in images or []:
            try:
                images_bytes.append(await f.read())
            except:
                continue
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
