import os
from dataclasses import dataclass

from libs.core.config_loader import load_root_config


@dataclass(frozen=True)
class BackendSettings:
    host: str
    port: int
    internal_token: str
    gemini_model_name: str


def load_settings() -> BackendSettings:
    """
    后端配置（单进程入口）

    配置优先级：环境变量 > 根目录 config.json > 默认值
    """
    root_cfg = load_root_config()

    host = os.getenv("BACKEND_HOST", "127.0.0.1")
    port = int(os.getenv("BACKEND_PORT", "8001"))
    internal_token = os.getenv("BACKEND_INTERNAL_TOKEN", "").strip()

    default_model = str(root_cfg.get("GEMINI_MODEL_NAME") or "gemini-2.5-flash")
    gemini_model_name = os.getenv("GEMINI_MODEL_NAME", default_model)

    return BackendSettings(
        host=host,
        port=port,
        internal_token=internal_token,
        gemini_model_name=gemini_model_name,
    )
