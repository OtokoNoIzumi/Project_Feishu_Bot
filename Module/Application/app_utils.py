"""
应用工具函数模块

集中管理应用层的工具函数和辅助方法
"""

import json
import os
from datetime import datetime, timedelta
from typing import Any


class TimeUtils:
    """时间相关工具函数"""

    @staticmethod
    def get_debug_time(offset_seconds: int = 5) -> str:
        """
        获取调试时间：当前时间 + offset_seconds（精确到秒）

        Args:
            offset_seconds: 偏移秒数

        Returns:
            str: 格式化的时间字符串 HH:MM:SS
        """
        debug_time = datetime.now() + timedelta(seconds=offset_seconds)
        return debug_time.strftime("%H:%M:%S")

    @staticmethod
    def format_duration(seconds: int) -> str:
        """
        格式化持续时间

        Args:
            seconds: 秒数

        Returns:
            str: 格式化的时间字符串
        """
        if seconds < 60:
            return f"({seconds}s)"

        if seconds < 3600:
            minutes = seconds // 60
            remaining_seconds = seconds % 60
            return f"({minutes}分{remaining_seconds}秒)" if remaining_seconds > 0 else f"({minutes}分)"

        hours = seconds // 3600
        remaining_minutes = (seconds % 3600) // 60
        return f"({hours}小时{remaining_minutes}分)" if remaining_minutes > 0 else f"({hours}小时)"


class PathUtils:
    """路径相关工具函数"""

    @staticmethod
    def get_project_root_from_file(file_path: str, levels_up: int = 2) -> str:
        """
        从文件路径获取项目根目录

        Args:
            file_path: 当前文件路径 (__file__)
            levels_up: 向上级数（默认2级：Module/Application -> Module -> 项目根）

        Returns:
            str: 项目根目录路径
        """
        try:
            current_dir = os.path.dirname(os.path.abspath(file_path))
            root_dir = current_dir

            for _ in range(levels_up):
                root_dir = os.path.dirname(root_dir)

            return os.path.normpath(root_dir)
        except:
            return os.getcwd()

    @staticmethod
    def ensure_cache_dir(project_root: str, cache_subdir: str = "cache") -> str:
        """
        确保缓存目录存在

        Args:
            project_root: 项目根目录
            cache_subdir: 缓存子目录名

        Returns:
            str: 缓存目录路径
        """
        cache_dir = os.path.join(project_root, cache_subdir)
        os.makedirs(cache_dir, exist_ok=True)
        return cache_dir


def custom_serializer(obj: Any) -> Any:
    """
    自定义序列化函数，用于json.dumps

    它会尝试获取对象的__dict__，如果对象没有__dict__（例如内置类型或使用__slots__的对象），
    或者__dict__中的某些值无法直接序列化，则回退到str(obj)。

    Args:
        obj: 需要序列化的对象

    Returns:
        Any: 可序列化的对象
    """
    # 处理特殊类型
    if isinstance(obj, bytes):
        return f"<bytes data len={len(obj)}>"

    # 处理复合类型
    if isinstance(obj, (list, tuple)):
        return [custom_serializer(item) for item in obj]

    if isinstance(obj, dict):
        return {k: custom_serializer(v) for k, v in obj.items()}

    # 处理有__dict__的对象
    if hasattr(obj, '__dict__'):
        return {
            k: custom_serializer(v)
            for k, v in vars(obj).items()
            if not k.startswith('_')
        }

    # 尝试JSON序列化，失败则转为字符串
    try:
        json.dumps(obj)  # 测试是否可序列化
        return obj
    except (TypeError, ValueError):
        return str(obj)


# 便捷导出
__all__ = [
    'TimeUtils', 'PathUtils', 'custom_serializer'
]
