import asyncio
from typing import Dict

from apps.settings import BackendSettings
from libs.utils.rate_limiter import AsyncRateLimiter

# --- 并发控制（Semaphore）---
# 限制同时进行 Gemini 交互的请求数（全局总并发限制）
GLOBAL_SEMAPHORE = asyncio.Semaphore(20)


def get_global_semaphore() -> asyncio.Semaphore:
    return GLOBAL_SEMAPHORE


# --- 频率限制（RateLimiter）---
# 不同模型的每分钟请求数限制（RPM）
# 格式：{model_name: AsyncRateLimiter(max_count, time_limit=60)}
MODEL_LIMITERS: Dict[str, AsyncRateLimiter] = {
    "gemini-2.5-flash": AsyncRateLimiter(max_count=15, time_limit=60),
    "gemini-1.5-flash": AsyncRateLimiter(max_count=15, time_limit=60),
    "gemini-1.5-pro": AsyncRateLimiter(max_count=2, time_limit=60),
    "gemini-pro": AsyncRateLimiter(max_count=2, time_limit=60),
    "default": AsyncRateLimiter(max_count=10, time_limit=60),
}


def get_model_limiter(settings: BackendSettings) -> AsyncRateLimiter:
    """根据配置的模型名称获取对应的限流器"""
    return MODEL_LIMITERS.get(settings.gemini_model_name, MODEL_LIMITERS["default"])
