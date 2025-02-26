"""
接口定义模块

该模块定义了平台无关的接口，用于不同平台实现之间的统一抽象
"""

from Module.Interface.message import Message, MessageType, MessageHandler
from Module.Interface.platform import Platform