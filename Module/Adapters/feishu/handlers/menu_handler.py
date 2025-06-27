"""
飞书菜单处理器 (Feishu Menu Handler)

负责处理飞书菜单事件，包括：
- 菜单点击事件处理
- 菜单到消息上下文的转换
"""

import datetime
from typing import Optional

from Module.Common.scripts.common import debug_utils
from Module.Business.processors import MessageContext, MessageContext_Refactor, MenuClickContent
from ..decorators import (
    feishu_event_handler_safe, message_conversion_safe
)
from Module.Services.constants import ProcessResultConstKeys, ProcessResultNextAction, MessageTypes, AdapterNames, ResponseTypes


class MenuHandler:
    """飞书菜单处理器"""

    def __init__(self, message_router, sender, user_name_getter):
        """
        初始化菜单处理器

        Args:
            message_router: 业务消息路由器
            sender: 消息发送器实例
            user_name_getter: 用户名获取函数
        """
        self.message_router = message_router
        self.sender = sender
        self._get_user_name = user_name_getter
        self.message_handler = None  # 由adapter注入

    def set_message_handler(self, message_handler):
        """注入MessageHandler实例"""
        self.message_handler = message_handler

    @feishu_event_handler_safe("飞书菜单处理失败")
    def handle_feishu_menu(self, data) -> None:
        """
        处理飞书菜单点击事件

        将菜单点击转换为标准消息上下文处理
        """
        # 转换为标准消息上下文
        context, context_refactor = self._convert_menu_to_context(data)
        if not context:
            debug_utils.log_and_print("❌ 菜单上下文转换失败", log_level="ERROR")
            return

        # 调用业务处理器
        result = self.message_router.process_message(context)

        # 检查是否需要异步处理B站视频推荐
        if result.response_type == ResponseTypes.ASYNC_ACTION:
            self.sender.send_feishu_reply_with_context(context_refactor, result)

            match result.async_action:
                case ProcessResultNextAction.PROCESS_BILI_VIDEO:
                    self.message_handler._handle_bili_video_async(context_refactor)
                case _:
                    debug_utils.log_and_print(f"❌ 未知异步操作: {result.async_action}", log_level="ERROR")

            return

        # 发送回复（菜单点击通常需要主动发送消息）
        if result.should_reply:
            self.sender.send_direct_message(context.user_id, result)

    @message_conversion_safe("菜单转换失败")
    def _convert_menu_to_context(self, data) -> Optional[MessageContext]:
        """将飞书菜单点击转换为标准消息上下文"""
        # 提取基本信息
        event_id = data.header.event_id
        user_id = data.event.operator.operator_id.open_id

        # 提取通用数据（时间戳和用户名）
        user_name = self._get_user_name(user_id)
        message_timestamp = datetime.datetime.now()

        # 菜单事件的内容是event_key，区分业务的核心参数
        event_key = data.event.event_key
        menu_click_content = MenuClickContent(event_key=event_key)
        New_MessageContext = MessageContext_Refactor(
            adapter_name=AdapterNames.FEISHU,
            timestamp=message_timestamp,
            event_id=event_id,

            user_id=user_id,
            user_name=user_name,

            message_type=MessageTypes.MENU_CLICK,
            content=menu_click_content,
            metadata={
                'app_id': data.header.app_id
            }
        )

        legacy_context = MessageContext(
            user_id=user_id,
            user_name=user_name,
            message_type=MessageTypes.MENU_CLICK,  # 自定义类型
            content=event_key,
            timestamp=message_timestamp,
            event_id=event_id,
            adapter_name=AdapterNames.FEISHU,  # ✅ 标识来源adapter
            metadata={
                'app_id': data.header.app_id
            }
        )

        return legacy_context, New_MessageContext
