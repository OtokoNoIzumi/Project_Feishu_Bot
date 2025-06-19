"""
适配器层模块 (Adapters Layer)

该模块包含各种前端平台的适配器
设计原则：协议转换、平台隔离、标准接口

架构重构说明：
- 飞书适配器已重构为模块化架构
- 支持handlers、senders、cards等组件化设计
- 保持向后兼容的统一入口
"""

from .feishu import FeishuAdapter

__all__ = [
    'FeishuAdapter'
]