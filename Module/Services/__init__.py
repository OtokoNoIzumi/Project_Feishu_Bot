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
from .message_aggregation_service import MessageAggregationService
from .user_business_permission_service import UserBusinessPermissionService
from .bili_adskip_service import BiliAdskipService
from .constants import ServiceNames

__all__ = [
    'CacheService',
    'ConfigService',
    'AudioService',
    'ImageService',
    'SchedulerService',
    'NotionService',
    'LLMService',
    'RouterService',
    'PendingCacheService',
    'MessageAggregationService',
    'UserBusinessPermissionService',
    'BiliAdskipService'
]

# 服务注册表（用于应用控制器）
AVAILABLE_SERVICES = {
    ServiceNames.CACHE: CacheService,
    ServiceNames.CONFIG: ConfigService,
    ServiceNames.AUDIO: AudioService,
    ServiceNames.IMAGE: ImageService,
    ServiceNames.SCHEDULER: SchedulerService,
    ServiceNames.NOTION: NotionService,
    ServiceNames.LLM: LLMService,
    ServiceNames.ROUTER: RouterService,
    ServiceNames.PENDING_CACHE: PendingCacheService,
    ServiceNames.MESSAGE_AGGREGATION: MessageAggregationService,
    ServiceNames.USER_BUSINESS_PERMISSION: UserBusinessPermissionService,
    ServiceNames.BILI_ADSKIP: BiliAdskipService
}