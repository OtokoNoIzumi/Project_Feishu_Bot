"""
Dependencies for FastAPI.

Provides dependency injection for authentication and other shared resources.
"""

import logging
from typing import Optional

from fastapi import Header, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from libs.auth_internal.token_auth import InternalTokenAuth
from libs.auth_internal.user_mapper import user_mapper
from libs.auth_clerk.clerk_jwt_auth import ClerkJWTAuth, ClerkJWTConfig
from apps.settings import BackendSettings

logger = logging.getLogger(__name__)

# 定义 HTTPBearer Security Scheme，让 Swagger UI 显示 Authorize 按钮
# auto_error=False 允许未认证时继续（由我们手动检查）
http_bearer = HTTPBearer(auto_error=False)


def require_internal_auth(settings: BackendSettings):
    """
    Dependency generator for internal token authentication ONLY.
    
    This is the original simple auth, kept for backward compatibility.
    For new code, use require_auth() which supports both Internal Token and Clerk JWT.
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


# 全局单例缓存
_clerk_auth_instance: Optional[ClerkJWTAuth] = None

def get_clerk_auth_instance(settings: BackendSettings) -> Optional[ClerkJWTAuth]:
    """Get or create the singleton ClerkJWTAuth instance."""
    global _clerk_auth_instance
    
    if not settings.clerk_jwks_url:
        return None
        
    if _clerk_auth_instance is None:
        clerk_config = ClerkJWTConfig(
            jwks_url=settings.clerk_jwks_url,
            authorized_parties=list(settings.clerk_authorized_parties),
        )
        _clerk_auth_instance = ClerkJWTAuth(config=clerk_config)
        
    return _clerk_auth_instance

def require_auth(settings: BackendSettings):
    """
    Dependency generator for dual authentication: Internal Token OR Clerk JWT.
    
    认证逻辑顺序：
    1. 如果 Internal Token 已配置且匹配 → 通过 (管理员/调试用途)
    2. 如果 Internal Token 未配置或不匹配 → 尝试 Clerk JWT 验证
    3. 如果 Clerk JWT 也不通过 → 拒绝请求
    
    Args:
        settings: The backend settings containing auth configuration.
    
    Returns:
        A dependency function that validates authentication.
    """
    internal_auth = InternalTokenAuth(token=settings.internal_token)
    
    # 获取 Clerk JWT 认证实例（单例）
    clerk_auth = get_clerk_auth_instance(settings)

    async def _dep(
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer)
    ):
        token = credentials.credentials if credentials else None
        
        # 如果没有任何认证方式配置，跳过认证
        if not internal_auth.is_enabled() and (clerk_auth is None or not clerk_auth.is_enabled()):
            logger.warning("No authentication configured, allowing request")
            return
        
        # 1. 尝试 Internal Token 验证
        if internal_auth.is_enabled() and token:
            authorization = f"Bearer {token}"
            if internal_auth.verify_authorization_header(authorization):
                logger.debug("Request authenticated via Internal Token")
                return  # 验证通过
        
        # 2. 尝试 Clerk JWT 验证
        if clerk_auth and clerk_auth.is_enabled() and token:
            payload = clerk_auth.verify_token(token)
            if payload:
                logger.debug("Request authenticated via Clerk JWT: user=%s", payload.get("sub"))
                return  # 验证通过
        
        # 3. 都不通过，拒绝请求
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: invalid token or not logged in",
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

