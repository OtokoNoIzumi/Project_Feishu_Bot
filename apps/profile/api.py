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

def build_profile_router(settings: BackendSettings) -> APIRouter:
    router = APIRouter()
    auth_dep = require_auth(settings)

    @router.get("/api/user/profile", dependencies=[Depends(auth_dep)])
    async def get_profile(user_id: str = Depends(get_current_user_id)):
        """
        获取当前用户 Profile 配置 (View Model)。
        包含：存档的设置 (Gender/Age/Targets) + 动态的最新的 Weight/Height。
        """
        return ProfileService.get_profile_view(user_id)

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
            
        usecase = AnalyzeProfileUsecase(settings)
        result = await usecase.execute(
            user_id, 
            req.user_note, 
            req.target_months, 
            req.auto_save,
            req.profile_override,
            req.metrics_override
        )
        
        # 2. Record Usage
        Gatekeeper.record_usage(user_id, "profile")
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
