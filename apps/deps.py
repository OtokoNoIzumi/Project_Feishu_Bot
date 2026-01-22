"""
Dependencies for FastAPI.

Provides dependency injection for authentication and other shared resources.
"""

from typing import Optional

from fastapi import Header, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from libs.auth_internal.token_auth import InternalTokenAuth
from libs.auth_internal.user_mapper import user_mapper
from apps.settings import BackendSettings

# 定义 HTTPBearer Security Scheme，让 Swagger UI 显示 Authorize 按钮
# auto_error=False 允许未认证时继续（由我们手动检查）
http_bearer = HTTPBearer(auto_error=False)


def require_internal_auth(settings: BackendSettings):
    """
    Dependency generator for internal token authentication.

    Uses HTTPBearer security scheme so Swagger UI shows the Authorize button
    and includes Authorization header in requests.

    Args:
        settings: The backend settings containing the internal token.

    Returns:
        A dependency function that validates the Authorization header.
    """
    auth = InternalTokenAuth(token=settings.internal_token)

    async def _dep(
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer)
    ):
        # 如果未配置 token，跳过认证
        if not auth.is_enabled():
            return
        
        # 构造 Authorization header 字符串
        authorization = None
        if credentials:
            authorization = f"Bearer {credentials.credentials}"
        
        ok = auth.verify_authorization_header(authorization)
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized: missing/invalid internal token",
            )

    return _dep


async def get_current_user_id(
    x_user_id: Optional[str] = Header(default=None, alias="X-User-ID")
) -> str:
    """
    统一的用户身份解析依赖。
    
    1. 从 X-User-ID Header 读取原始 ID
    2. 通过 UserMapper 解析为 Master ID (如果有映射)
    3. 校验白名单 (当前为软校验，可升级为硬拦截)
    
    Returns:
        resolved_user_id: 解析后的用户 ID
    """
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-User-ID header",
        )
    
    # ID 映射
    resolved_id = user_mapper.resolve_user_id(x_user_id)
    
    # 白名单校验 (当前为软校验，日志记录；后续可改为强拦截)
    if not user_mapper.is_whitelisted(resolved_id):
        # 硬拦截版本 (取消注释即可启用):
        # raise HTTPException(
        #     status_code=status.HTTP_403_FORBIDDEN,
        #     detail="User not in whitelist",
        # )
        pass  # MVP 阶段：仅映射，不阻断
    
    return resolved_id
