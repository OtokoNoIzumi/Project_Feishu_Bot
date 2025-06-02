"""
API服务层模块

该模块包含所有独立的业务API服务
"""

from .cache_service import CacheService
from .config_service import ConfigService

__all__ = [
    'CacheService',
    'ConfigService'
]

# 服务注册表（用于应用控制器）
AVAILABLE_SERVICES = {
    'cache': CacheService,
    'config': ConfigService
}