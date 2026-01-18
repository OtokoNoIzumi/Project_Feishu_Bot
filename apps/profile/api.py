from fastapi import APIRouter, Depends
from apps.deps import get_current_user_id, require_internal_auth
from apps.settings import BackendSettings
from apps.profile.schemas import UserProfile, ProfileAnalyzeRequest, ProfileAnalyzeResponse
from apps.profile.service import ProfileService
from apps.profile.usecases.analyze_profile_usecase import AnalyzeProfileUsecase

def build_profile_router(settings: BackendSettings) -> APIRouter:
    router = APIRouter()
    auth_dep = require_internal_auth(settings)

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
        """保存用户 Profile 配置"""
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
        usecase = AnalyzeProfileUsecase(settings)
        return await usecase.execute(user_id, req.user_note, req.target_months, req.auto_save)

    return router
