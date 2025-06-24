"""
Services层专用装饰器

为各种服务操作提供统一的异常处理和日志记录
独立于其他模块，专门服务于Services层

装饰器层级结构：
1. Module/Services/decorator_base.py - 装饰器基础工厂（内部使用）
2. Module/Services/service_decorators.py - Services层装饰器（本文件）
3. Module/Adapters/feishu/decorators.py - 飞书适配器专用装饰器
4. Module/Business/processors/base_processor.py - Business层装饰器

通用装饰器：
- require_service: 通用服务依赖检查，适用于Services层和main.py
- service_operation_safe: 通用服务操作安全装饰器

Business层专用：
- Module.Business.processors.base_processor.require_service: 返回ProcessResult的版本
"""

from functools import wraps
from typing import TypeVar, Callable, Any, Optional, Dict, List
from Module.Common.scripts.common import debug_utils
from .decorator_base import create_exception_handler_decorator, create_file_cleanup_handler

F = TypeVar('F', bound=Callable[..., Any])

# 创建各种装饰器工厂
_service_decorator = create_exception_handler_decorator("🔧", default_return_value=None)
_api_decorator = create_exception_handler_decorator("🌐", default_return_value=None)
_file_decorator = create_exception_handler_decorator("📁", default_return_value=None, cleanup_handler=create_file_cleanup_handler())
_config_decorator = create_exception_handler_decorator("⚙️", default_return_value=None)
_cache_decorator = create_exception_handler_decorator("🗄️", default_return_value=None)
_scheduler_decorator = create_exception_handler_decorator("⏰", default_return_value=None)


def require_service(service_name: str, error_msg: Optional[str] = None, check_available: bool = False, return_value: Any = None):
    """
    通用装饰器：确保指定服务可用

    适用于Services层和main.py等需要服务检查的场景

    Args:
        service_name: 服务名称
        error_msg: 自定义错误消息，默认为"xxx服务不可用"
        check_available: 是否检查服务的is_available()方法
        return_value: 服务不可用时的返回值（默认None）
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 尝试从不同位置获取app_controller
            app_controller = None

            # 方法1：如果是类方法，从self获取
            if args and hasattr(args[0], 'app_controller'):
                app_controller = args[0].app_controller
            # 方法2：如果是函数，从第一个参数获取（假设传入了app_controller）
            elif args and hasattr(args[0], 'get_service'):
                app_controller = args[0]

            if not app_controller:
                debug_utils.log_and_print("🔧 无法获取app_controller，服务检查失败", log_level="ERROR")
                return return_value

            service = app_controller.get_service(service_name)
            if not service:
                msg = error_msg or f"{service_name}服务不可用"
                debug_utils.log_and_print(f"🔧 {msg}", log_level="ERROR")
                return return_value

            if check_available and hasattr(service, 'is_available') and not service.is_available():
                msg = error_msg or f"{service_name}服务未启动或不可用"
                debug_utils.log_and_print(f"🔧 {msg}", log_level="ERROR")
                return return_value

            return func(*args, **kwargs)
        return wrapper
    return decorator


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
    return _file_decorator(error_message, return_value, cleanup_files=cleanup_files)


def config_operation_safe(error_message: str, return_value: Any = None, config_operation_type: str = ""):
    """
    ⚙️ 配置操作安全装饰器

    专门处理配置相关操作：
    - 配置文件读写
    - 环境变量处理
    - 设置项验证

    Args:
        error_message: 错误描述信息
        return_value: 配置操作失败时的返回值
        config_operation_type: 操作类型（get/set/validate等）
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                if config_operation_type:
                    debug_utils.log_and_print(f"⚙️ 配置{config_operation_type}操作成功", log_level="DEBUG")
                return result
            except Exception as e:
                op_info = f"[{config_operation_type}] " if config_operation_type else ""
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