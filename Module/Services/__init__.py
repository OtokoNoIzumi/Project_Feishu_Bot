"""
API服务层模块

该模块包含所有独立的业务API服务
"""

from .cache_service import CacheService
from .config_service import ConfigService
from .audio import AudioService
from .image import ImageService
from .scheduler import SchedulerService
from .notion import NotionService
from .llm import LLMService
from .router import RouterService
from .pending_cache_service import PendingCacheService

__all__ = [
    'CacheService',
    'ConfigService',
    'AudioService',
    'ImageService',
    'SchedulerService',
    'NotionService',
    'LLMService',
    'RouterService',
    'PendingCacheService'
]

# 服务注册表（用于应用控制器）
AVAILABLE_SERVICES = {
    'cache': CacheService,
    'config': ConfigService,
    'audio': AudioService,
    'image': ImageService,
    'scheduler': SchedulerService,
    'notion': NotionService,
    'llm': LLMService,
    'router': RouterService,
    'pending_cache': PendingCacheService
}