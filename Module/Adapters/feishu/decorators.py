"""
飞书适配器专用装饰器

为FeishuAdapter设计的专用装饰器体系，处理适配器层特有的异常情况：
1. 飞书SDK调用异常 - 网络、API错误
2. 消息转换异常 - 数据格式、解析错误
3. 文件操作异常 - 上传、下载错误
4. 异步处理异常 - 线程、后台任务错误
"""

from typing import Any, Callable, TypeVar
from functools import wraps

from Module.Common.scripts.common import debug_utils
from Module.Services.decorator_base import create_exception_handler_decorator, create_feishu_return_value_factory

F = TypeVar('F', bound=Callable[..., Any])

# 创建飞书专用装饰器工厂
_feishu_sdk_decorator = create_exception_handler_decorator("🔴 飞书SDK异常", default_return_value=False)
_message_conversion_decorator = create_exception_handler_decorator("🔄 消息转换异常", default_return_value=None)
_file_operation_decorator = create_exception_handler_decorator("📁 文件操作异常", default_return_value=False)
_async_operation_decorator = create_exception_handler_decorator("⚡ 异步操作异常", default_return_value=None)
_feishu_event_decorator = create_exception_handler_decorator("📡 飞书事件异常", default_return_value=None)
_card_operation_decorator = create_exception_handler_decorator(
    "🎴 卡片操作异常",
    default_return_value=False,
    return_value_factory=create_feishu_return_value_factory()
)


def feishu_sdk_safe(error_message: str = "飞书SDK调用失败", return_value: Any = False):
    """
    飞书SDK调用安全装饰器

    专门处理飞书SDK相关的异常：
    - 网络连接异常
    - API调用超时
    - 飞书服务不可用
    - SDK内部错误

    Args:
        error_message: 错误日志消息
        return_value: 异常时的返回值 (bool/None/dict等)
    """
    return _feishu_sdk_decorator(error_message, return_value)


def message_conversion_safe(error_message: str = "消息转换失败"):
    """
    消息转换安全装饰器

    专门处理消息格式转换异常：
    - JSON解析错误
    - 数据结构转换失败
    - 字段映射错误
    - 编码问题

    Args:
        error_message: 错误日志消息
    """
    return _message_conversion_decorator(error_message)


def file_operation_safe(error_message: str = "文件操作失败", return_value: bool = False):
    """
    文件操作安全装饰器

    专门处理文件相关异常：
    - 文件上传失败
    - 文件格式不支持
    - 文件大小超限
    - 存储空间不足
    - 网络传输中断

    Args:
        error_message: 错误日志消息
        return_value: 异常时的返回值
    """
    return _file_operation_decorator(error_message, return_value)


def async_operation_safe(error_message: str = "异步操作失败"):
    """
    异步操作安全装饰器

    专门处理异步任务异常：
    - 线程创建失败
    - 后台任务异常
    - 资源清理错误
    - 并发访问冲突

    Args:
        error_message: 错误日志消息
    """
    return _async_operation_decorator(error_message)


def card_operation_safe(error_message: str = "卡片操作失败"):
    """
    卡片操作安全装饰器

    专门处理飞书卡片相关异常，返回标准的卡片响应格式：
    - 卡片构建失败
    - 卡片更新异常
    - 交互响应错误

    Args:
        error_message: 错误日志消息
    """
    return _card_operation_decorator(error_message)


def feishu_event_handler_safe(error_message: str = "飞书事件处理失败"):
    """
    飞书事件处理安全装饰器

    专门处理飞书事件回调异常：
    - WebSocket事件处理
    - 回调函数异常
    - 事件解析错误

    对于void返回的事件处理函数，异常时不返回任何值

    Args:
        error_message: 错误日志消息
    """
    return _feishu_event_decorator(error_message)


# 组合装饰器：为常见场景提供预配置的装饰器组合
def feishu_message_handler(error_message: str = "飞书消息处理失败"):
    """
    飞书消息处理组合装饰器

    结合事件处理和消息转换的安全机制
    """
    def decorator(func: F) -> F:
        # 先应用事件处理安全，再应用消息转换安全
        func = feishu_event_handler_safe(error_message)(func)
        return func
    return decorator


def feishu_api_call(error_message: str = "飞书API调用失败", return_value: bool = False):
    """
    飞书API调用组合装饰器

    结合SDK安全和网络异常处理
    """
    def decorator(func: F) -> F:
        return feishu_sdk_safe(error_message, return_value)(func)
    return decorator


def card_build_safe(error_message: str, re_raise: bool = True):
    """
    🃏 卡片构建安全装饰器

    专门处理卡片构建过程中的异常：
    - 数据格式化错误
    - 模板参数错误
    - 卡片内容构建异常

    Args:
        error_message: 错误描述信息
        re_raise: 是否重新抛出异常（默认True，保持原有行为）
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                debug_utils.log_and_print(f"🃏 {error_message}: {e}", log_level="ERROR")
                if re_raise:
                    raise
                return {}  # 卡片构建失败时返回空字典
        return wrapper
    return decorator
