"""
业务层模块 (Business Layer)

该模块包含核心业务逻辑，完全独立于前端平台
设计原则：平台无关、高复用、业务聚焦
"""

from .message_router import MessageRouter

__all__ = [
    'MessageRouter'
]