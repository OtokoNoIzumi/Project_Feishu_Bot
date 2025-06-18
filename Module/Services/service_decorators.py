"""
Services层专用装饰器

为各种服务操作提供统一的异常处理和日志记录
独立于其他模块，专门服务于Services层
"""

from functools import wraps
from typing import TypeVar, Callable, Any, Optional, Dict, List
from Module.Common.scripts.common import debug_utils

F = TypeVar('F', bound=Callable[..., Any])


def service_operation_safe(error_message: str, return_value: Any = None, log_args: bool = False):
    """
    🔧 通用服务操作安全装饰器

    适用于大部分服务层操作：
    - 业务逻辑执行
    - 数据处理操作
    - 内部方法调用

    Args:
        error_message: 错误描述信息
        return_value: 异常时的返回值
        log_args: 是否记录方法参数（用于调试）
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                if log_args and len(args) > 1:  # 跳过self参数
                    debug_utils.log_and_print(f"🔧 执行{func.__name__}: args={args[1:][:2]}", log_level="DEBUG")
                return func(*args, **kwargs)
            except Exception as e:
                debug_utils.log_and_print(f"🔧 {error_message}: {e}", log_level="ERROR")
                return return_value
        return wrapper
    return decorator


def external_api_safe(error_message: str, return_value: Any = None, api_name: str = ""):
    """
    🌐 外部API调用安全装饰器

    专门处理外部服务调用：
    - Notion API
    - 文件上传/下载
    - 第三方服务集成

    Args:
        error_message: 错误描述信息
        return_value: API失败时的返回值
        api_name: API名称（用于日志）
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                if api_name:
                    debug_utils.log_and_print(f"🌐 {api_name} API调用成功", log_level="DEBUG")
                return result
            except Exception as e:
                api_info = f"[{api_name}] " if api_name else ""
                debug_utils.log_and_print(f"🌐 {api_info}{error_message}: {e}", log_level="ERROR")
                return return_value
        return wrapper
    return decorator


def file_processing_safe(error_message: str, return_value: Any = None, cleanup_files: List[str] = None):
    """
    📁 文件处理安全装饰器

    专门处理文件相关操作：
    - 文件读写
    - 格式转换
    - 临时文件处理

    Args:
        error_message: 错误描述信息
        return_value: 文件操作失败时的返回值
        cleanup_files: 需要清理的临时文件列表
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            temp_files = []
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                debug_utils.log_and_print(f"📁 {error_message}: {e}", log_level="ERROR")
                return return_value
            finally:
                # 清理临时文件
                if cleanup_files:
                    import os
                    for file_path in cleanup_files:
                        if file_path and os.path.exists(file_path):
                            try:
                                os.remove(file_path)
                                debug_utils.log_and_print(f"📁 清理临时文件: {file_path}", log_level="DEBUG")
                            except:
                                pass
        return wrapper
    return decorator


def config_operation_safe(error_message: str, return_value: Any = None, operation_type: str = ""):
    """
    ⚙️ 配置操作安全装饰器

    专门处理配置相关操作：
    - 配置文件读写
    - 环境变量处理
    - 设置项验证

    Args:
        error_message: 错误描述信息
        return_value: 配置操作失败时的返回值
        operation_type: 操作类型（get/set/validate等）
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                if operation_type:
                    debug_utils.log_and_print(f"⚙️ 配置{operation_type}操作成功", log_level="DEBUG")
                return result
            except Exception as e:
                op_info = f"[{operation_type}] " if operation_type else ""
                debug_utils.log_and_print(f"⚙️ {op_info}{error_message}: {e}", log_level="ERROR")
                return return_value
        return wrapper
    return decorator


def cache_operation_safe(error_message: str, return_value: Any = None, cache_key: str = ""):
    """
    🗄️ 缓存操作安全装饰器

    专门处理缓存相关操作：
    - 缓存读写
    - 缓存清理
    - 缓存验证

    Args:
        error_message: 错误描述信息
        return_value: 缓存操作失败时的返回值
        cache_key: 缓存键名（用于日志）
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                if cache_key:
                    debug_utils.log_and_print(f"🗄️ 缓存操作成功: {cache_key}", log_level="DEBUG")
                return result
            except Exception as e:
                key_info = f"[{cache_key}] " if cache_key else ""
                debug_utils.log_and_print(f"🗄️ {key_info}{error_message}: {e}", log_level="ERROR")
                return return_value
        return wrapper
    return decorator


def scheduler_operation_safe(error_message: str, return_value: Any = None, task_name: str = ""):
    """
    ⏰ 调度器操作安全装饰器

    专门处理调度器相关操作：
    - 任务调度
    - 定时执行
    - 任务状态管理

    Args:
        error_message: 错误描述信息
        return_value: 调度操作失败时的返回值
        task_name: 任务名称（用于日志）
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                if task_name:
                    debug_utils.log_and_print(f"⏰ 调度任务成功: {task_name}", log_level="DEBUG")
                return result
            except Exception as e:
                task_info = f"[{task_name}] " if task_name else ""
                debug_utils.log_and_print(f"⏰ {task_info}{error_message}: {e}", log_level="ERROR")
                return return_value
        return wrapper
    return decorator