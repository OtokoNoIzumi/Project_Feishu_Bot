"""
飞书处理器模块 (Feishu Handlers)

包含所有飞书事件处理器：
- MessageHandler: 消息处理器
- CardHandler: 卡片处理器
- MenuHandler: 菜单处理器

设计原则：
- 单一职责：每个处理器专注特定事件类型
- 标准接口：统一的处理器接口
- 可扩展性：易于添加新的事件处理器
"""

from .message_handler import MessageHandler
from .card_handler import CardHandler
from .menu_handler import MenuHandler

__all__ = ['MessageHandler', 'CardHandler', 'MenuHandler']