"""
Dependencies for FastAPI.

Provides dependency injection for authentication and other shared resources.
"""

from typing import Optional

from fastapi import Header, HTTPException, status

from libs.auth_internal.token_auth import InternalTokenAuth
from apps.settings import BackendSettings


def require_internal_auth(settings: BackendSettings):
    """
    Dependency generator for internal token authentication.

    Args:
        settings: The backend settings containing the internal token.

    Returns:
        A dependency function that validates the Authorization header.
    """
    auth = InternalTokenAuth(token=settings.internal_token)

    async def _dep(authorization: Optional[str] = Header(default=None)):
        if not auth.is_enabled():
            return
        ok = auth.verify_authorization_header(authorization)
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized: missing/invalid internal token",
            )

    return _dep
