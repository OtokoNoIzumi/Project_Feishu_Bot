"""
飞书消息发送器模块 (Feishu Message Senders)

包含各类消息发送功能：
- message_sender: 统一消息发送器
- 支持文本、图片、音频、富文本等多种消息类型
- 支持不同发送模式：新消息、回复、线程回复

设计原则：
- 统一接口：所有发送操作通过统一入口
- 类型支持：支持飞书全部消息类型
- 模式灵活：支持多种发送模式
"""

from .message_sender import MessageSender

__all__ = ['MessageSender']