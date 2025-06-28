"""
消息处理器子模块

将原有的MessageProcessor按业务功能拆分为多个专门的处理器
"""

from .base_processor import (
    BaseProcessor, MessageContext, ProcessResult, safe_execute, require_app_controller,
    RouteResult, MessageContext_Refactor
)
from .base_processor import TextContent, CardActionContent, MenuClickContent, FileContent, ContentPayloads
from .text_processor import TextProcessor
from .media_processor import MediaProcessor
from .bilibili_processor import BilibiliProcessor
from .admin_processor import AdminProcessor
from .schedule_processor import ScheduleProcessor

__all__ = [
    'BaseProcessor',
    'MessageContext',
    'ProcessResult',
    'TextProcessor',
    'MediaProcessor',
    'BilibiliProcessor',
    'AdminProcessor',
    'ScheduleProcessor',
    'safe_execute',
    'require_app_controller',
    'MessageContext_Refactor',
    'TextContent',
    'CardActionContent',
    'MenuClickContent',
    'FileContent',
    'ContentPayloads',
    'RouteResult',
]