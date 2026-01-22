"""
Backend Settings.

Loads and validates configuration for the backend application,
aggregating settings from environment variables and config files.
"""

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List

from libs.core.config_loader import load_root_config
from libs.core.project_paths import get_project_root


@dataclass(frozen=True)
class BackendSettings:
    """Immutable configuration object for the backend service."""

    host: str
    port: int
    internal_token: str
    gemini_model_name: str
    
    # Clerk JWT 认证配置
    clerk_jwks_url: str = ""  # e.g., https://xxx.clerk.accounts.dev/.well-known/jwks.json
    clerk_authorized_parties: tuple = ()  # Allowed origins for azp claim


_DOTENV_CACHE: Dict[str, str] = {}


def _load_dotenv_vars() -> Dict[str, str]:
    """
    Load key/value pairs from project root .env without third-party deps.
    """
    if _DOTENV_CACHE:
        return _DOTENV_CACHE

    env_path = get_project_root() / ".env"
    if not env_path.exists():
        return _DOTENV_CACHE

    content = env_path.read_text(encoding="utf-8", errors="ignore")
    pattern = re.compile(
        r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:["\'](.+?)["\']|([^#\r\n]*))'
    )

    for line in content.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        key = match.group(1)
        val = match.group(2) if match.group(2) is not None else match.group(3)
        if val is not None:
            _DOTENV_CACHE[key] = val.strip()

    return _DOTENV_CACHE


def _get_env_value(name: str, default: str = "") -> str:
    """
    Read from real env first, then .env, then fallback.
    """
    value = os.getenv(name)
    if value is not None and value.strip():
        return value.strip()
    dotenv_val = _load_dotenv_vars().get(name, "").strip()
    return dotenv_val if dotenv_val else default


def load_settings() -> BackendSettings:
    """
    后端配置（单进程入口）

    配置优先级：环境变量 > 根目录 config.json > 默认值
    """
    root_cfg = load_root_config()

    host = _get_env_value("BACKEND_HOST", "127.0.0.1")
    port = int(_get_env_value("BACKEND_PORT", "8001"))
    internal_token = _get_env_value("BACKEND_INTERNAL_TOKEN", "").strip()

    default_model = str(root_cfg.get("GEMINI_MODEL_NAME") or "gemini-2.5-flash")
    gemini_model_name = _get_env_value("GEMINI_MODEL_NAME", default_model)
    
    # Clerk JWT 配置
    clerk_jwks_url = _get_env_value("CLERK_JWKS_URL", "")
    
    # 允许的 authorized parties (逗号分隔)
    # 例如: "https://izumilife.site,http://localhost:8080"
    authorized_parties_str = _get_env_value("CLERK_AUTHORIZED_PARTIES", "")
    clerk_authorized_parties = tuple(
        p.strip() for p in authorized_parties_str.split(",") if p.strip()
    )

    return BackendSettings(
        host=host,
        port=port,
        internal_token=internal_token,
        gemini_model_name=gemini_model_name,
        clerk_jwks_url=clerk_jwks_url,
        clerk_authorized_parties=clerk_authorized_parties,
    )

