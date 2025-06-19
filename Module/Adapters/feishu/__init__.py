"""
飞书适配器模块 (Feishu Adapter Module)

提供与飞书平台的完整集成，包括：
- 消息处理和发送
- 卡片交互管理
- 事件处理器
- 装饰器工具

架构设计：
- adapter.py: 主适配器入口
- handlers/: 各类事件处理器
- senders/: 消息发送组件
- cards/: 卡片管理组件
"""

from .adapter import FeishuAdapter
from .decorators import (
    feishu_api_call,
    feishu_event_handler_safe,
    feishu_sdk_safe,
    async_operation_safe,
    card_operation_safe,
    message_conversion_safe,
    file_operation_safe
)

__all__ = [
    'FeishuAdapter',
    'feishu_api_call',
    'feishu_event_handler_safe',
    'feishu_sdk_safe',
    'async_operation_safe',
    'card_operation_safe',
    'message_conversion_safe',
    'file_operation_safe'
]