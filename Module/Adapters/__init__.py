"""
适配器层模块 (Adapters Layer)

该模块包含各种前端平台的适配器
设计原则：协议转换、平台隔离、标准接口
"""

from .feishu_adapter import FeishuAdapter

__all__ = [
    'FeishuAdapter'
]