"""
基础消息处理器

包含共同的数据结构、工具方法和基础功能
"""

from typing import Dict, Any, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime
from functools import wraps
from Module.Common.scripts.common import debug_utils
from Module.Services.decorator_base import create_exception_handler_decorator, create_business_return_value_factory


# --- 载荷数据结构定义 (这部分保持) ---
@dataclass
class TextContent:
    text: str

@dataclass
class CardActionContent:
    # 把之前分散在 content 和 metadata 的信息都集中在这里
    tag: str  # 'button', 'select_static', 'input'
    value: Dict[str, Any]  # 原始的 action.value
    # 你的业务指示器，之前是 content 的值
    action_name: Optional[str] = None
    card_action_key: Optional[str] = None # e.g., 'design_confirm', 'cancel_order'
    form_data: Optional[Dict[str, Any]] = None
    selected_option: Optional[str] = None
    input_value: Optional[str] = None

@dataclass
class MenuClickContent:
    event_key: str

@dataclass
class FileContent:
    # 后续再看是不是可以合并
    file_key: Optional[str] = None
    image_key: Optional[str] = None

# 定义一个 ContentUnion 类型，用于类型提示
ContentPayloads = Union[
    str, # 简单文本可以继续用 str
    TextContent,
    CardActionContent,
    MenuClickContent,
    FileContent,
    Dict[str, Any] # 保留 Dict 作为通用或未标准化的载荷
]


@dataclass
class MessageContext_Refactor:
    """消息上下文 - 标准化的消息数据结构"""
    # adapter逻辑信息
    adapter_name: str
    timestamp: datetime
    event_id: str
    # 用户数据信息（目前仅来自飞书，后续可能扩展到其他平台）
    user_id: str
    user_name: str

    # 业务参数-part1
    message_type: str  # text, image, audio, menu_click, card_action
    content: ContentPayloads

    # 消息ID信息
    parent_message_id: Optional[str] = None  # 用户消息如果是回复，这里是被回复的消息ID
    message_id: Optional[str] = None  # 用户发送的这条消息的ID（系统回复时作为parent_id）

    # 业务参数-part2
    metadata: Dict[str, Any] = field(default_factory=dict)



@dataclass
class MessageContext:
    """消息上下文 - 标准化的消息数据结构"""
    user_id: str
    user_name: str
    message_type: str  # text, image, audio, menu_click, card_action
    content: Any
    timestamp: datetime
    event_id: str
    adapter_name: str
    metadata: Dict[str, Any] = None
    message_id: Optional[str] = None  # 用户发送的这条消息的ID（系统回复时作为parent_id）
    parent_message_id: Optional[str] = None  # 用户消息如果是回复，这里是被回复的消息ID

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
    # 新增：上下文信息，指向要关联的消息ID
    parent_id: Optional[str] = None  # 指向要关联的消息ID，用于建立回复关系

    @classmethod
    def success_result(cls, response_type: str, content: Any, parent_id: Optional[str] = None):
        return cls(True, response_type, content, parent_id=parent_id)

    @classmethod
    def error_result(cls, error_msg: str):
        # 错误消息保持默认逻辑（parent_id=None）
        return cls(False, "text", {"text": error_msg}, error_msg, True, parent_id=None)

    @classmethod
    def no_reply_result(cls):
        return cls(True, "text", None, should_reply=False)


# 创建Business层专用装饰器工厂
_business_safe_decorator = create_exception_handler_decorator(
    "🔴 业务处理异常",
    return_value_factory=create_business_return_value_factory()
)


# 防御性检查装饰器组
def require_app_controller(error_msg: str = "系统服务不可用"):
    """
    装饰器：确保app_controller可用

    Args:
        error_msg: 检查失败时的错误消息
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            if not self.app_controller:
                return ProcessResult.error_result(error_msg)
            return func(self, *args, **kwargs)
        return wrapper
    return decorator


def require_service(service_name: str, error_msg: Optional[str] = None, check_available: bool = False):
    """
    装饰器：确保指定服务可用

    Args:
        service_name: 服务名称
        error_msg: 自定义错误消息，默认为"xxx服务不可用"
        check_available: 是否检查服务的is_available()方法
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            if not self.app_controller:
                return ProcessResult.error_result("系统服务不可用")

            service = self.app_controller.get_service(service_name)
            if not service:
                msg = error_msg or f"{service_name}服务不可用"
                return ProcessResult.error_result(msg)

            if check_available and hasattr(service, 'is_available') and not service.is_available():
                msg = error_msg or f"{service_name}服务未启动或不可用"
                return ProcessResult.error_result(msg)

            return func(self, *args, **kwargs)
        return wrapper
    return decorator


def safe_execute(error_prefix: str = "操作失败"):
    """
    装饰器：统一异常处理

    Args:
        error_prefix: 错误消息前缀
    """
    return _business_safe_decorator(error_prefix, error_prefix=error_prefix)


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