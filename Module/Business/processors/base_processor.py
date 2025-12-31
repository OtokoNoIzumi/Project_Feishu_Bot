"""
基础消息处理器

包含共同的数据结构、工具方法和基础功能
"""

from typing import Dict, Any, Optional, Union, List
from dataclasses import dataclass, field
from datetime import datetime
from functools import wraps
from Module.Common.scripts.common import debug_utils

from Module.Services.constants import ResponseTypes


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
    card_config_key: Optional[str] = None
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

@dataclass
class PostContent:
    """飞书 POST 类型消息内容（富文本文章）"""
    title: str  # 文章标题，作为驱动开关（如"饮食"）
    text: str  # 合并所有文本内容
    image_keys: List[str] = field(default_factory=list)  # 所有图片的 image_key 列表
    raw_content: Optional[Dict[str, Any]] = None  # 原始 POST 内容，用于调试

# 定义一个 ContentUnion 类型，用于类型提示
ContentPayloads = Union[
    str, # 简单文本可以继续用 str
    TextContent,
    CardActionContent,
    MenuClickContent,
    FileContent,
    PostContent,
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
    chat_type: Optional[str] = None


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
class RouteResult:
    """路由结果 - 中层业务路由决策，承载业务标识和参数"""
    success: bool
    route_type: str  # 业务标识，如"bili_video_card"

    # 错误处理
    error_message: Optional[str] = None

    # 业务参数载体
    route_params: Dict[str, Any] = field(default_factory=dict)

    # 前置消息
    message_before_async: Optional[str] = None

    # 路由决策相关
    should_reply: bool = True

    @classmethod
    def create_route_result(
        cls,
        route_type: str,
        route_params: Optional[Dict[str, Any]] = None,
        message_before_async: Optional[str] = None,
        should_reply: bool = True
    ):
        """创建路由结果"""
        return cls(
            success=True,
            route_type=route_type,
            route_params=route_params or {},
            message_before_async=message_before_async,
            should_reply=should_reply
        )

    @classmethod
    def error_route_result(cls, error_msg: str):
        """创建错误路由结果"""
        return cls(
            success=False,
            route_type="error",
            error_message=error_msg,
            should_reply=True
        )

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
    async_action: Optional[str] = None # 异步操作，用于后续处理
    message_before_async: Optional[str] = None # 异步消息，用于后续处理
    reply_message_type: Optional[str] = None # 回复消息类型，用于后续处理
    user_list: Optional[List[str]] = None # 用户列表，用于后续处理

    @classmethod
    def async_result(
        cls,
        async_action: str,
        message_before_async: Optional[str] = None,
        reply_message_type: Optional[str] = None,
        should_reply: bool = True
    ):
        return cls(
            success=True,
            response_type=ResponseTypes.ASYNC_ACTION,
            response_content={},
            async_action=async_action,
            message_before_async=message_before_async,
            reply_message_type=reply_message_type,
            should_reply=should_reply
        )

    @classmethod
    def success_result(cls, response_type: str, content: Any, parent_id: Optional[str] = None):
        return cls(True, response_type, content, parent_id=parent_id)

    @classmethod
    def user_list_result(cls, response_type: str, content: Any, user_list: List[str] = None):
        return cls(True, response_type, content, user_list=user_list)

    @classmethod
    def error_result(cls, error_msg: str):
        # 错误消息保持默认逻辑（parent_id=None）
        return cls(False, "text", {"text": error_msg}, error_msg, True, parent_id=None, reply_message_type="text")

    @classmethod
    def no_reply_result(cls):
        return cls(True, "text", None, should_reply=False)


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
    🔴 Business层统一异常处理装饰器

    Args:
        error_prefix: 错误消息前缀
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                debug_utils.log_and_print(f"🔴 业务处理异常 {error_prefix} [{func.__name__}]: {e}", log_level="ERROR")
                return ProcessResult.error_result(f"{error_prefix}: {str(e)}")
        return wrapper
    return decorator


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
