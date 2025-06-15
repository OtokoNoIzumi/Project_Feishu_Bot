"""
基础消息处理器

包含共同的数据结构、工具方法和基础功能
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime
from Module.Common.scripts.common import debug_utils


@dataclass
class MessageContext:
    """消息上下文 - 标准化的消息数据结构"""
    user_id: str
    user_name: str
    message_type: str  # text, image, audio, menu_click, card_action
    content: Any
    timestamp: datetime
    event_id: str
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class ProcessResult:
    """处理结果 - 标准化的响应数据结构"""
    success: bool
    response_type: str  # text, image, audio, post, interactive, image_list
    response_content: Any
    error_message: str = None
    should_reply: bool = True

    @classmethod
    def success_result(cls, response_type: str, content: Any):
        return cls(True, response_type, content)

    @classmethod
    def error_result(cls, error_msg: str):
        return cls(False, "text", {"text": error_msg}, error_msg, True)

    @classmethod
    def no_reply_result(cls):
        return cls(True, "text", None, should_reply=False)


class BaseProcessor:
    """
    基础消息处理器

    提供所有子处理器共同需要的功能和工具方法
    """

    def __init__(self, app_controller=None):
        """
        初始化基础处理器

        Args:
            app_controller: 应用控制器，用于访问各种服务
        """
        self.app_controller = app_controller

    def _extract_command_content(self, user_msg: str, triggers: list) -> str:
        """提取指令后的实际内容"""
        for trigger in triggers:
            if trigger in user_msg:
                if user_msg.startswith(trigger):
                    return user_msg[len(trigger):].strip()
                else:
                    # 对于包含型匹配，找到第一个匹配位置后提取
                    idx = user_msg.find(trigger)
                    return user_msg[idx + len(trigger):].strip()
        return user_msg.strip()

    def _log_command(self, user_name: str, emoji: str, action: str, content: str = None):
        """统一的指令日志输出"""
        if content:
            debug_utils.log_and_print(f"{emoji} {user_name} {action}：{content}", log_level="INFO")
        else:
            debug_utils.log_and_print(f"{emoji} {user_name} {action}", log_level="INFO")

    def _is_duplicate_event(self, event_id: str) -> bool:
        """检查事件是否重复"""
        if not self.app_controller:
            debug_utils.log_and_print("app_controller为空，无法检查重复事件", log_level="WARNING")
            return False

        cache_service = self.app_controller.get_service('cache')
        if not cache_service:
            debug_utils.log_and_print("缓存服务不可用，无法检查重复事件", log_level="WARNING")
            return False

        # 直接调用缓存服务的check_event方法
        is_duplicate = cache_service.check_event(event_id)
        event_timestamp = cache_service.get_event_timestamp(event_id)
        return is_duplicate, event_timestamp

    def _record_event(self, context: MessageContext):
        """记录新事件"""
        if not self.app_controller:
            debug_utils.log_and_print("app_controller为空，无法记录事件", log_level="WARNING")
            return

        cache_service = self.app_controller.get_service('cache')
        if not cache_service:
            debug_utils.log_and_print("缓存服务不可用，无法记录事件", log_level="WARNING")
            return

        # 直接调用缓存服务的方法
        cache_service.add_event(context.event_id)
        cache_service.save_event_cache()

        # 更新用户缓存
        cache_service.update_user(context.user_id, context.user_name)