from fastapi import APIRouter, Depends, Body, HTTPException
from apps.deps import get_current_user_id, require_auth
from apps.settings import BackendSettings
from apps.profile.schemas import UserProfile, ProfileAnalyzeRequest, ProfileAnalyzeResponse
from apps.profile.service import ProfileService
from apps.profile.usecases.analyze_profile_usecase import AnalyzeProfileUsecase
from apps.profile.invitation_manager import InvitationManager
from apps.profile.nid_manager import NIDManager
from apps.profile.invitation_schemas import BatchCodeManageRequest, InvitationCodeDefinition
from apps.profile.gatekeeper import Gatekeeper
from apps.common.utils import decode_images_b64
import logging

logger = logging.getLogger(__name__)

from apps.common.usage_tracker import UsageTracker

def build_profile_router(settings: BackendSettings) -> APIRouter:
    router = APIRouter()
    auth_dep = require_auth(settings)

    @router.get("/api/user/profile", dependencies=[Depends(auth_dep)])
    async def get_profile(user_id: str = Depends(get_current_user_id)):
        """
        获取当前用户 Profile 配置 (View Model)。
        包含：存档的设置 (Gender/Age/Targets) + 动态的最新的 Weight/Height。
        以及：今日用量与额度 (limits)。
        """
        data = ProfileService.get_profile_view(user_id)
        
        # Inject Limits Info
        profile_obj = ProfileService.load_profile(user_id)
        current_level, _ = Gatekeeper.get_current_effective_level(profile_obj)
        limits_config = Gatekeeper.get_limits()
        usage = UsageTracker.get_today_usage(user_id)
        
        data["limits_info"] = {
            "level": current_level,
            "usage": usage,
            "max": {}
        }
        
        default_limits = {"basic": 5, "pro": 10, "ultra": -1}
        for feat, feat_limits in limits_config.items():
            if isinstance(feat_limits, dict):
                val = feat_limits.get(current_level, default_limits.get(current_level, 5))
                data["limits_info"]["max"][feat] = val
                
        return data

    @router.post("/api/user/profile", response_model=UserProfile, dependencies=[Depends(auth_dep)])
    async def save_profile(
        profile: UserProfile, 
        user_id: str = Depends(get_current_user_id)
    ):
        """保存用户 Profile 配置。age 会自动转换为 birth_date 存储。"""
        ProfileService.save_profile(user_id, profile)
        return profile

    @router.post("/api/user/profile/analyze", response_model=ProfileAnalyzeResponse, dependencies=[Depends(auth_dep)])
    async def analyze_profile(
        req: ProfileAnalyzeRequest,
        user_id: str = Depends(get_current_user_id)
    ):
        """
        AI 分析用户请求并给出 Profile 修改建议。
        如果 auto_save=True，则自动应用建议。
        """
        # 1. Access Control
        access = Gatekeeper.check_access(user_id, "profile")
        if not access["allowed"]:
            raise HTTPException(
                status_code=403, 
                detail={
                    "code": access.get("code", "FORBIDDEN"),
                    "message": access["reason"],
                    "metadata": {k: v for k, v in access.items() if k not in ["allowed", "reason", "code"]}
                }
            )
            
        # [Image Limit Check] - Soft Enforcement
        images_bytes = decode_images_b64(req.images_b64)
        warning_message = None
        
        if images_bytes:
            img_access = Gatekeeper.check_access(user_id, "image_analyze", amount=len(images_bytes))
            if not img_access["allowed"]:
                # Limit reached: degrade to text-only mode and warn
                images_bytes = []
                warning_message = f"今日图片分析额度已用完，仅针对文本内容进行分析。"
                logger.info(f"User {user_id} image limit reached for profile, processing text only.")

        usecase = AnalyzeProfileUsecase(settings)
        result = await usecase.execute(
            user_id, 
            req.user_note, 
            req.target_months, 
            req.auto_save,
            req.profile_override,
            req.metrics_override,
            images=images_bytes
        )
        
        # 2. Record Usage
        Gatekeeper.record_usage(user_id, "profile")
        if images_bytes:
            Gatekeeper.record_usage(user_id, "image_analyze", amount=len(images_bytes))
            
        if warning_message:
            result.warning = warning_message
            
        return result

    @router.post("/api/user/invitation/redeem", dependencies=[Depends(auth_dep)])
    async def redeem_invitation_code(
        code: str = Body(..., embed=True),
        user_id: str = Depends(get_current_user_id)
    ):
        """Redeem an invitation code to upgrade account or change NID."""
        try:
            # Delegate all logic to InvitationManager
            result = InvitationManager.redeem_code(code, user_id)
            return result
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Internal Error: {str(e)}")

    @router.get("/api/admin/invitation/codes", dependencies=[Depends(auth_dep)])
    async def list_invitation_codes():
        """Administrative: List all invitation codes."""
        return InvitationManager._load_codes()

    @router.post("/api/admin/invitation/codes", dependencies=[Depends(auth_dep)])
    async def manage_invitation_codes(req: BatchCodeManageRequest):
        """Administrative: Batch add/update/delete codes."""
        InvitationManager.manage_codes(req.action, req.codes)
        return {"success": True, "action": req.action, "count": len(req.codes)}

    return router
