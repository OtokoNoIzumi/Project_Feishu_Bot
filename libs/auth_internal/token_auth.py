from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class InternalTokenAuth:
    """
    最小化的进程间鉴权：Bearer Token

    使用方式（HTTP 请求头）：
    Authorization: Bearer <token>
    """

    token: Optional[str]

    def is_enabled(self) -> bool:
        return bool(self.token and self.token.strip())

    def verify_authorization_header(self, authorization: Optional[str]) -> bool:
        if not self.is_enabled():
            return True
        if not authorization:
            return False
        prefix = "Bearer "
        if not authorization.startswith(prefix):
            return False
        provided = authorization[len(prefix):].strip()
        return provided == (self.token or "").strip()


