"""
Clerk JWT Authentication.

Provides JWT verification for Clerk-authenticated users.
Uses PyJWT with JWKS for signature verification.
"""

import logging
import time
from typing import Optional, List
from dataclasses import dataclass

import jwt
from jwt import PyJWKClient

logger = logging.getLogger(__name__)


@dataclass
class ClerkJWTConfig:
    """Configuration for Clerk JWT verification."""
    
    # JWKS URL from Clerk Dashboard (e.g., https://xxx.clerk.accounts.dev/.well-known/jwks.json)
    jwks_url: str
    
    # Authorized parties (azp claim) - origins permitted to use tokens
    # e.g., ["https://izumilife.site", "http://localhost:8080"]
    authorized_parties: List[str]
    
    # Cache JWKS keys for performance (seconds)
    jwks_cache_seconds: int = 300


class ClerkJWTAuth:
    """
    Clerk JWT 验证器。
    
    验证从前端 Clerk SDK 获取的 session token，确保用户已登录。
    """
    
    def __init__(self, config: Optional[ClerkJWTConfig] = None):
        self.config = config
        self._jwks_client: Optional[PyJWKClient] = None
        
        if config and config.jwks_url:
            self._init_jwks_client()
    
    def _init_jwks_client(self) -> None:
        """Initialize the JWKS client for key retrieval."""
        try:
            self._jwks_client = PyJWKClient(
                self.config.jwks_url,
                cache_jwk_set=True,
                lifespan=self.config.jwks_cache_seconds,
            )
            logger.info("Clerk JWKS client initialized: %s", self.config.jwks_url)
        except Exception as e:
            logger.error("Failed to initialize Clerk JWKS client: %s", e)
            self._jwks_client = None
    
    def is_enabled(self) -> bool:
        """Check if Clerk JWT auth is enabled."""
        return self._jwks_client is not None
    
    def verify_token(self, token: str) -> Optional[dict]:
        """
        验证 Clerk JWT token。
        
        Args:
            token: JWT token (不含 "Bearer " 前缀)
            
        Returns:
            解码后的 token payload (包含 sub=user_id)，验证失败返回 None
        """
        if not self.is_enabled():
            logger.warning("Clerk JWT auth not enabled, skipping verification")
            return None
        
        try:
            # 1. Get signing key from JWKS
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            
            # 2. Decode and verify token
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                options={
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_aud": False,  # Clerk doesn't use aud claim
                },
            )
            
            # 3. Validate expiration manually (double-check)
            current_time = int(time.time())
            exp = payload.get("exp", 0)
            nbf = payload.get("nbf", 0)
            
            if exp < current_time:
                logger.warning("Clerk JWT expired: exp=%s, now=%s", exp, current_time)
                return None
            
            if nbf > current_time:
                logger.warning("Clerk JWT not yet valid: nbf=%s, now=%s", nbf, current_time)
                return None
            
            # 4. Validate authorized party (azp claim) if present
            azp = payload.get("azp")
            if azp and self.config.authorized_parties:
                if azp not in self.config.authorized_parties:
                    logger.warning("Clerk JWT invalid azp: %s not in %s", azp, self.config.authorized_parties)
                    return None
            
            # 5. Check for pending status (Organizations feature)
            sts = payload.get("sts")
            if sts == "pending":
                logger.warning("Clerk JWT user status is pending")
                return None
            
            logger.debug("Clerk JWT verified successfully: sub=%s", payload.get("sub"))
            return payload
            
        except jwt.ExpiredSignatureError:
            logger.warning("Clerk JWT expired signature")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning("Clerk JWT invalid: %s", e)
            return None
        except Exception as e:
            logger.error("Clerk JWT verification error: %s", e)
            return None
    
    def get_user_id(self, token: str) -> Optional[str]:
        """
        从 JWT 中提取用户 ID。
        
        Args:
            token: JWT token
            
        Returns:
            Clerk User ID (sub claim)，验证失败返回 None
        """
        payload = self.verify_token(token)
        if payload:
            return payload.get("sub")
        return None
