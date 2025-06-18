"""
装饰器基础工厂

仅供Services、Adapters、Business三层的装饰器模块内部使用
提供通用的装饰器构建函数，避免重复代码
不对外暴露，不放入Common公共库
"""

from functools import wraps
from typing import TypeVar, Callable, Any, Optional, List
from Module.Common.scripts.common import debug_utils

F = TypeVar('F', bound=Callable[..., Any])


def create_exception_handler_decorator(
    log_prefix: str,
    default_return_value: Any = None,
    return_value_factory: Optional[Callable] = None,
    cleanup_handler: Optional[Callable] = None
):
    """
    创建异常处理装饰器的工厂函数

    Args:
        log_prefix: 日志前缀（如 "🔧", "🌐", "📁"）
        default_return_value: 默认返回值
        return_value_factory: 返回值工厂函数，接收异常和原函数，返回错误值
        cleanup_handler: 清理处理函数
    """
    def decorator_factory(error_message: str, return_value: Any = None, **extra_params):
        def decorator(func: F) -> F:
            @wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    # 记录日志
                    func_name = func.__name__
                    debug_utils.log_and_print(
                        f"{log_prefix} {error_message} [{func_name}]: {e}",
                        log_level="ERROR"
                    )

                    # 确定返回值
                    if return_value_factory:
                        return return_value_factory(e, func, **extra_params)
                    elif return_value is not None:
                        return return_value
                    else:
                        return default_return_value
                finally:
                    # 执行清理
                    if cleanup_handler:
                        cleanup_handler(**extra_params)
            return wrapper
        return decorator
    return decorator_factory


def create_file_cleanup_handler():
    """创建文件清理处理器"""
    def cleanup_files(cleanup_files: List[str] = None, **kwargs):
        if cleanup_files:
            import os
            for file_path in cleanup_files:
                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        debug_utils.log_and_print(f"📁 清理临时文件: {file_path}", log_level="DEBUG")
                    except:
                        pass
    return cleanup_files


def create_feishu_return_value_factory():
    """创建飞书专用返回值工厂"""
    def factory(exception, func, **kwargs):
        # 根据函数返回类型决定错误响应
        if func.__annotations__.get('return') == 'P2CardActionTriggerResponse':
            from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTriggerResponse
            return P2CardActionTriggerResponse({
                "toast": {
                    "type": "error",
                    "content": "操作失败，请稍后重试"
                }
            })
        return kwargs.get('default_return_value', False)
    return factory


def create_business_return_value_factory():
    """创建Business层专用返回值工厂"""
    def factory(exception, func, **kwargs):
        from Module.Business.processors.base_processor import ProcessResult
        error_prefix = kwargs.get('error_prefix', '操作失败')
        return ProcessResult.error_result(f"{error_prefix}: {str(exception)}")
    return factory