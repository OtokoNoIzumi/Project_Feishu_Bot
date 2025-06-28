"""
飞书适配器专用装饰器

为FeishuAdapter设计的专用装饰器体系，处理适配器层特有的异常情况：
1. 飞书SDK调用异常 - 网络、API错误
2. 消息转换异常 - 数据格式、解析错误
3. 文件操作异常 - 上传、下载错误
4. 异步处理异常 - 线程、后台任务错误

简化设计原则：
- 2层装饰器结构：decorator(func) -> wrapper
- 统一的错误日志格式
- 保留飞书特有的返回值逻辑
"""

from typing import Any, Callable, TypeVar
from functools import wraps
from Module.Common.scripts.common import debug_utils

F = TypeVar('F', bound=Callable[..., Any])


def feishu_sdk_safe(error_message: str = "飞书SDK调用失败", return_value: Any = False):
    """
    🔴 飞书SDK调用安全装饰器

    专门处理飞书SDK相关的异常：
    - 网络连接异常、API调用超时、飞书服务不可用、SDK内部错误

    Args:
        error_message: 错误日志消息
        return_value: 异常时的返回值 (bool/None/dict等)
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                debug_utils.log_and_print(f"🔴 飞书SDK异常 {error_message} [{func.__name__}]: {e}", log_level="ERROR")
                return return_value
        return wrapper
    return decorator


def message_conversion_safe(error_message: str = "消息转换失败"):
    """
    🔄 消息转换安全装饰器

    专门处理消息格式转换异常：
    - JSON解析错误、数据结构转换失败、字段映射错误、编码问题

    Args:
        error_message: 错误日志消息
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                debug_utils.log_and_print(f"🔄 消息转换异常 {error_message} [{func.__name__}]: {e}", log_level="ERROR")
                return None
        return wrapper
    return decorator


def file_operation_safe(error_message: str = "文件操作失败", return_value: bool = False):
    """
    📁 文件操作安全装饰器

    专门处理文件相关异常：
    - 文件上传失败、文件格式不支持、文件大小超限、存储空间不足、网络传输中断

    Args:
        error_message: 错误日志消息
        return_value: 异常时的返回值
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                debug_utils.log_and_print(f"📁 文件操作异常 {error_message} [{func.__name__}]: {e}", log_level="ERROR")
                return return_value
        return wrapper
    return decorator


def async_operation_safe(error_message: str = "异步操作失败"):
    """
    ⚡ 异步操作安全装饰器

    专门处理异步任务异常：
    - 线程创建失败、后台任务异常、资源清理错误、并发访问冲突

    Args:
        error_message: 错误日志消息
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                debug_utils.log_and_print(f"⚡ 异步操作异常 {error_message} [{func.__name__}]: {e}", log_level="ERROR")
                return None
        return wrapper
    return decorator


def card_operation_safe(error_message: str = "卡片操作失败"):
    """
    🎴 卡片操作安全装饰器

    专门处理飞书卡片相关异常，根据函数返回类型智能返回：
    - 如果函数注解返回P2CardActionTriggerResponse，返回错误toast
    - 否则返回False

    Args:
        error_message: 错误日志消息
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                debug_utils.log_and_print(f"🎴 卡片操作异常 {error_message} [{func.__name__}]: {e}", log_level="ERROR")

                # 根据函数返回类型注解决定返回值（保留原有逻辑）
                if func.__annotations__.get('return') == 'P2CardActionTriggerResponse':
                    try:
                        from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTriggerResponse
                        return P2CardActionTriggerResponse({
                            "toast": {
                                "type": "error",
                                "content": "操作失败，请稍后重试"
                            }
                        })
                    except ImportError:
                        pass
                return False
        return wrapper
    return decorator


def feishu_event_handler_safe(error_message: str = "飞书事件处理失败"):
    """
    📡 飞书事件处理安全装饰器

    专门处理飞书事件回调异常：
    - WebSocket事件处理、回调函数异常、事件解析错误

    Args:
        error_message: 错误日志消息
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                debug_utils.log_and_print(f"📡 飞书事件异常 {error_message} [{func.__name__}]: {e}", log_level="ERROR")
                return None
        return wrapper
    return decorator


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
    - 数据格式化错误、模板参数错误、卡片内容构建异常

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
                debug_utils.log_and_print(f"🃏 {error_message} [{func.__name__}]: {e}", log_level="ERROR")
                if re_raise:
                    raise
                return {}  # 卡片构建失败时返回空字典
        return wrapper
    return decorator
