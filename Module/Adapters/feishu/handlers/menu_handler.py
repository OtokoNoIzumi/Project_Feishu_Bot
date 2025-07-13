"""
飞书菜单处理器 (Feishu Menu Handler)

负责处理飞书菜单事件，包括：
- 菜单点击事件处理
- 菜单到消息上下文的转换
"""

import datetime
from typing import Optional

from Module.Common.scripts.common import debug_utils
from Module.Business.processors import MessageContext, MessageContext_Refactor, MenuClickContent, RouteResult, ProcessResult
from Module.Services.constants import MessageTypes, AdapterNames, MenuClickTypes
from ..decorators import (
    feishu_event_handler_safe, message_conversion_safe
)


class MenuHandler:
    """飞书菜单处理器"""

    def __init__(self, app_controller, message_router, sender):
        """
        初始化菜单处理器

        Args:
            app_controller: 应用控制器实例
            message_router: 业务消息路由器
            sender: 消息发送器实例
        """
        self.message_router = message_router
        self.sender = sender
        self.app_controller = app_controller
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
        context_refactor = self._convert_menu_to_context(data)
        if self.sender.filter_duplicate_message(context_refactor):
            return

        event_key = context_refactor.content.event_key
        match event_key:
            case MenuClickTypes.GET_BILI_URL:
                debug_utils.log_and_print(f"📺 B站视频推荐 by [{context_refactor.user_name}]", log_level="INFO")
                # 统一使用新的路由决策，实现DRY原则
                route_result = self.message_router.bili.video_menu_route_choice()
            case MenuClickTypes.NEW_ROUTINE:
                debug_utils.log_and_print(f"🚀 快速日常记录 by [{context_refactor.user_name}]", log_level="INFO")
                # 处理快速日常记录
                route_result = self.message_router.routine_record.quick_record_menu_route_choice(context_refactor.user_id)
            case _:
                debug_utils.log_and_print(f"❓ 未知菜单键: {event_key}", log_level="INFO")
                text = f"收到菜单点击：{event_key}，功能开发中..."
                self.sender.send_feishu_message_reply(context_refactor, text)
                return

        if self.message_handler:
            if isinstance(route_result, RouteResult):
                self.message_handler.handle_route_result_dynamic(route_result, context_refactor)
            elif isinstance(route_result, ProcessResult):
                self.sender.send_feishu_message_reply(context_refactor, route_result.response_content.get('text', ''))
        else:
            debug_utils.log_and_print("❌ MessageHandler未注入，无法处理RouteResult", log_level="ERROR")

        return

    @message_conversion_safe("菜单转换失败")
    def _convert_menu_to_context(self, data) -> Optional[MessageContext]:
        """将飞书菜单点击转换为标准消息上下文"""
        # 提取基本信息
        event_id = data.header.event_id
        user_id = data.event.operator.operator_id.open_id

        # 提取通用数据（时间戳和用户名）
        user_name = self.sender.get_user_name(user_id)
        message_timestamp = datetime.datetime.now()

        # 菜单事件的内容是event_key，区分业务的核心参数
        event_key = data.event.event_key
        menu_click_content = MenuClickContent(event_key=event_key)
        new_message_context = MessageContext_Refactor(
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

        return new_message_context
