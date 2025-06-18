"""
新的消息处理器 (Message Processor)

重构后的核心业务逻辑，使用子处理器模式
完全独立于前端平台，可以被任何适配器调用
"""

import time
from typing import Dict, Any, Callable, List
from .processors import (
    BaseProcessor, MessageContext, ProcessResult,
    TextProcessor, MediaProcessor, BilibiliProcessor,
    AdminProcessor, ScheduleProcessor
)
from Module.Common.scripts.common import debug_utils


class MessageProcessor(BaseProcessor):
    """
    重构后的消息处理器

    职责：
    1. 接收标准化的消息上下文
    2. 分发到对应的子处理器
    3. 返回标准化的处理结果
    """

    def __init__(self, app_controller=None):
        """
        初始化消息处理器

        Args:
            app_controller: 应用控制器，用于访问各种服务
        """
        super().__init__(app_controller)

        # 初始化子处理器
        self.text_processor = TextProcessor(app_controller)
        self.media_processor = MediaProcessor(app_controller)
        self.bilibili_processor = BilibiliProcessor(app_controller)
        self.admin_processor = AdminProcessor(app_controller)
        self.schedule_processor = ScheduleProcessor(app_controller)

        # 初始化Action分发表
        self._init_action_dispatchers()

    def _init_action_dispatchers(self):
        """初始化Action分发注册表"""
        self.action_dispatchers: Dict[str, Callable[[MessageContext, Dict[str, Any]], ProcessResult]] = {
            # B站相关动作
            "mark_bili_read": self._handle_mark_bili_read,

            # 管理员相关动作
            "confirm_update_user": self._handle_admin_card_action,
            "confirm_update_ads": self._handle_admin_card_action,

            # 新的缓存业务管理员动作
            "confirm_user_update": self._handle_pending_admin_card_action,
            "cancel_user_update": self._handle_pending_admin_card_action,
            "update_user_type": self._handle_pending_admin_card_action,

            # 交互式管理员动作
            "confirm_update_user_interactive": self._handle_interactive_admin_card_action,
            "confirm_update_ads_interactive": self._handle_interactive_admin_card_action,
            "cancel_admin_operation": self._handle_interactive_admin_card_action,

            # AI路由相关动作
            "cancel": self._handle_ai_card_action,
            "edit_content": self._handle_ai_card_action,
            "confirm_thought": self._handle_ai_card_action,
            "confirm_schedule": self._handle_ai_card_action,
            "confirm_food_order": self._handle_ai_card_action,
        }

    def register_action(self, action_name: str, handler: Callable[[MessageContext, Dict[str, Any]], ProcessResult]):
        """
        动态注册新的Action处理器

        Args:
            action_name: Action名称
            handler: 处理器函数
        """
        self.action_dispatchers[action_name] = handler
        debug_utils.log_and_print(f"✅ 注册Action处理器: {action_name}", log_level="INFO")

    def get_registered_actions(self) -> List[str]:
        """获取所有已注册的Action列表"""
        return list(self.action_dispatchers.keys())

    def process_message(self, context: MessageContext) -> ProcessResult:
        """
        处理消息的主入口

        Args:
            context: 消息上下文

        Returns:
            ProcessResult: 处理结果
        """
        try:
            # 检查事件是否已处理（去重）
            is_duplicate, event_timestamp = self._is_duplicate_event(context.event_id)
            if is_duplicate:
                time_diff = time.time() - event_timestamp
                debug_utils.log_and_print(f"📋 重复事件已跳过 [{context.message_type}] [{context.content[:50]}] 时间差: {time_diff:.2f}秒", log_level="INFO")
                return ProcessResult.no_reply_result()

            # 记录新事件
            self._record_event(context)

            # 根据消息类型分发处理
            if context.message_type == "text":
                return self._process_text_message(context)
            elif context.message_type == "image":
                return self._process_image_message(context)
            elif context.message_type == "audio":
                return self._process_audio_message(context)
            elif context.message_type == "menu_click":
                return self._process_menu_click(context)
            elif context.message_type == "card_action":
                return self._process_card_action(context)
            else:
                return ProcessResult.error_result(f"不支持的消息类型: {context.message_type}")

        except Exception as e:
            debug_utils.log_and_print(f"❌ 消息处理失败: {str(e)}", log_level="ERROR")
            return ProcessResult.error_result(f"消息处理失败: {str(e)}")

    def _process_text_message(self, context: MessageContext) -> ProcessResult:
        """处理文本消息"""
        user_msg = context.content

        # 管理员配置更新指令（最高优先级）
        if self.admin_processor.is_admin_command(user_msg):
            content = self._extract_command_content(user_msg, [self.admin_processor.get_update_trigger()])
            if user_msg.startswith(self.admin_processor.get_update_trigger()):
                self._log_command(context.user_name, "🔧", "触发配置更新指令", content)
            elif user_msg.startswith("更新用户"):
                self._log_command(context.user_name, "👤", "触发用户更新指令", user_msg[4:])
            elif user_msg.startswith("更新广告"):
                self._log_command(context.user_name, "📺", "触发广告更新指令", user_msg[4:])
            return self.admin_processor.handle_admin_command(context, user_msg)

        # TTS配音指令，改成startwith
        if user_msg.startswith("配音"):
            content = self._extract_command_content(user_msg, ["配音"])
            self._log_command(context.user_name, "🎤", "触发TTS配音指令", content)
            return self.media_processor.handle_tts_command(context, user_msg)

        # 图像生成指令
        if user_msg.startswith("生图") or user_msg.startswith("AI画图"):
            content = self._extract_command_content(user_msg, ["生图", "AI画图"])
            self._log_command(context.user_name, "🎨", "触发图像生成指令", content)
            return self.media_processor.handle_image_generation_command(context, user_msg)

        # 富文本指令
        if user_msg == "富文本":
            self._log_command(context.user_name, "📄", "触发富文本指令")
            return self.media_processor.handle_rich_text_command(context)

        # 图片/壁纸指令
        if user_msg == "图片" or user_msg == "壁纸":
            self._log_command(context.user_name, "🖼️", "触发图片指令")
            return self.media_processor.handle_sample_image_command(context)

        # B站/视频指令（触发菜单效果）
        if user_msg == "B站" or user_msg == "视频":
            self._log_command(context.user_name, "📺", "触发B站视频指令")
            return self.bilibili_processor.handle_bili_text_command(context)

        # 基础指令处理
        if user_msg == "帮助":
            self._log_command(context.user_name, "❓", "查看帮助")
            return self.text_processor.handle_help_command(context)
        elif user_msg == "你好":
            self._log_command(context.user_name, "👋", "发送问候")
            return self.text_processor.handle_greeting_command(context)

        # AI智能路由（新增 - 在原有指令之前）
        router_service = self.app_controller.get_service('router') if self.app_controller else None
        if router_service:
            route_result = router_service.route_message(user_msg, context.user_id)
            if route_result.get('success') and route_result.get('route_type') in ['shortcut', 'ai_intent']:
                # 路由成功，返回确认卡片
                return self._handle_ai_route_result(context, route_result)

        # 默认回复
        return self.text_processor.handle_default_message(context)

    def _process_image_message(self, context: MessageContext) -> ProcessResult:
        """处理图片消息 - 图像风格转换"""
        return self.media_processor.handle_image_message(context)

    def _process_audio_message(self, context: MessageContext) -> ProcessResult:
        """处理音频消息"""
        return self.media_processor.handle_audio_message(context)

    def _process_menu_click(self, context: MessageContext) -> ProcessResult:
        """处理菜单点击"""
        event_key = context.content
        if event_key == "get_bili_url":
            return self.bilibili_processor.handle_menu_click(context)

        return self.bilibili_processor.handle_menu_click(context)

    def _process_card_action(self, context: MessageContext) -> ProcessResult:
        """处理卡片按钮动作（使用注册表分发）"""
        action = context.content
        action_value = context.metadata.get('action_value', {})

        try:
            # 使用Action分发注册表
            dispatcher = self.action_dispatchers.get(action)
            if dispatcher:
                return dispatcher(context, action_value)
            else:
                return ProcessResult.error_result(f"未知的卡片动作: {action}")

        except Exception as e:
            debug_utils.log_and_print(f"❌ 卡片动作处理失败: {e}", log_level="ERROR")
            return ProcessResult.error_result(f"卡片动作处理失败: {str(e)}")

    def _handle_ai_route_result(self, context: MessageContext, route_result: Dict[str, Any]) -> ProcessResult:
        """
        处理AI路由结果，返回确认卡片

        Args:
            context: 消息上下文
            route_result: 路由结果

        Returns:
            ProcessResult: 包含确认卡片的处理结果
        """
        try:
            # 导入卡片构建器
            from Module.Services.router.card_builder import CardBuilder

            card_builder = CardBuilder()
            card_content = card_builder.build_intent_confirmation_card(route_result)

            # 记录路由成功
            intent = route_result.get('intent', '未知')
            confidence = route_result.get('confidence', 0)
            route_type = route_result.get('route_type', 'unknown')

            self._log_command(
                context.user_name,
                "🎯",
                f"AI路由成功: {intent} ({route_type})",
                f"置信度: {confidence}%"
            )

            return ProcessResult.success_result("interactive", card_content, parent_id=context.message_id)

        except Exception as e:
            debug_utils.log_and_print(f"❌ AI路由结果处理失败: {e}", log_level="ERROR")
            return ProcessResult.error_result(f"路由处理失败: {str(e)}")

    def _handle_ai_card_action(self, context: MessageContext, action_value: Dict[str, Any]) -> ProcessResult:
        """
        处理AI路由卡片的按钮动作

        Args:
            context: 消息上下文
            action: 动作类型
            action_value: 动作参数

        Returns:
            ProcessResult: 处理结果
        """
        try:
            # 从action_value中获取action类型
            action = action_value.get("action") or context.content
            intent = action_value.get('intent', '未知')
            content = action_value.get('content', '')

            if action == "cancel":
                # 取消操作
                return ProcessResult.success_result("text", {
                    "text": f"已取消 {intent} 操作"
                }, parent_id=context.message_id)

            elif action == "edit_content":
                # 编辑内容（暂时返回提示，后续可扩展为编辑界面）
                return ProcessResult.success_result("text", {
                    "text": f"编辑功能开发中，当前内容：{content}"
                }, parent_id=context.message_id)

            elif action in ["confirm_thought", "confirm_schedule", "confirm_food_order"]:
                # 确认操作 - 暂时返回成功提示，后续集成实际的数据存储
                action_map = {
                    "confirm_thought": "思考记录",
                    "confirm_schedule": "日程安排",
                    "confirm_food_order": "点餐订单"
                }

                operation_name = action_map.get(action, "操作")

                # 记录确认操作
                self._log_command(
                    context.user_name,
                    "✅",
                    f"确认{operation_name}",
                    content[:50] + "..." if len(content) > 50 else content
                )

                return ProcessResult.success_result("text", {
                    "text": f"✅ {operation_name}已确认记录\n\n内容：{content}\n\n💡 数据存储功能将在后续版本实现"
                }, parent_id=context.message_id)

            else:
                return ProcessResult.error_result(f"未知的卡片动作: {action}")

        except Exception as e:
            debug_utils.log_and_print(f"❌ AI卡片动作处理失败: {e}", log_level="ERROR")
            return ProcessResult.error_result(f"卡片动作处理失败: {str(e)}")

    def _handle_mark_bili_read(self, context: MessageContext, action_value: Dict[str, Any]) -> ProcessResult:
        """
        处理标记B站视频为已读
        根据卡片类型分发到对应的处理器
        """
        try:
            card_type = action_value.get("card_type", "menu")

            if card_type == "daily":
                # 定时卡片由ScheduleProcessor处理
                return self.schedule_processor.handle_mark_bili_read(context, action_value)
            else:
                # 菜单卡片由BilibiliProcessor处理
                return self.bilibili_processor.handle_mark_bili_read(context, action_value)

        except Exception as e:
            debug_utils.log_and_print(f"❌ 标记B站视频为已读失败: {str(e)}", log_level="ERROR")
            return ProcessResult.error_result(f"处理失败：{str(e)}")

    def _handle_admin_card_action(self, context: MessageContext, action_value: Dict[str, Any]) -> ProcessResult:
        """
        处理管理员卡片动作

        Args:
            context: 消息上下文
            action: 动作类型
            action_value: 动作参数

        Returns:
            ProcessResult: 处理结果
        """
        try:
            # 从action_value中获取action类型
            action = action_value.get("action") or context.content

            if action == "confirm_update_user":
                # 确认更新用户信息
                uid = action_value.get("uid", "")
                account_type = action_value.get("account_type", "")
                self._log_command(context.user_name, "✅", "确认更新用户", f"UID:{uid} 类型:{account_type}")
                return self.admin_processor.handle_confirm_update_user(context, action_value)
            elif action == "confirm_update_ads":
                # 确认更新广告信息
                bvid = action_value.get("bvid", "")
                ad_timestamps = action_value.get("ad_timestamps", "")
                self._log_command(context.user_name, "✅", "确认更新广告", f"BVID:{bvid} 时间:{ad_timestamps}")
                return self.admin_processor.handle_confirm_update_ads(context, action_value)
            else:
                return ProcessResult.error_result(f"未知的管理员卡片动作: {action}")
        except Exception as e:
            debug_utils.log_and_print(f"❌ 管理员卡片动作处理失败: {e}", log_level="ERROR")
            return ProcessResult.error_result(f"卡片动作处理失败: {str(e)}")

    def _handle_interactive_admin_card_action(self, context: MessageContext, action_value: Dict[str, Any]) -> ProcessResult:
        """
        处理交互式管理员卡片动作

        Args:
            context: 消息上下文
            action: 动作类型
            action_value: 动作参数

        Returns:
            ProcessResult: 处理结果
        """
        try:
            # 从action_value中获取action类型
            action = action_value.get("action") or context.content

            if action == "confirm_update_user_interactive":
                # 确认更新用户信息
                uid = action_value.get("uid", "")
                account_type = action_value.get("account_type", "")
                self._log_command(context.user_name, "✅", "确认更新用户", f"UID:{uid} 类型:{account_type}")
                return self.admin_processor.handle_interactive_card_action(context, action, action_value)
            elif action == "confirm_update_ads_interactive":
                # 确认更新广告信息
                bvid = action_value.get("bvid", "")
                ad_timestamps = action_value.get("ad_timestamps", "")
                self._log_command(context.user_name, "✅", "确认更新广告", f"BVID:{bvid} 时间:{ad_timestamps}")
                return self.admin_processor.handle_interactive_card_action(context, action, action_value)
            elif action == "cancel_admin_operation":
                # 取消管理员操作
                self._log_command(context.user_name, "❌", "取消管理员操作")
                return self.admin_processor.handle_interactive_card_action(context, action, action_value)
            else:
                return ProcessResult.error_result(f"未知的交互式管理员卡片动作: {action}")
        except Exception as e:
            debug_utils.log_and_print(f"❌ 交互式管理员卡片动作处理失败: {e}", log_level="ERROR")
            return ProcessResult.error_result(f"卡片动作处理失败: {str(e)}")

    def _handle_pending_admin_card_action(self, context: MessageContext, action_value: Dict[str, Any]) -> ProcessResult:
        """
        处理缓存业务管理员卡片动作

        Args:
            context: 消息上下文
            action_value: 动作参数

        Returns:
            ProcessResult: 处理结果
        """
        try:
            # 直接调用admin_processor的缓存操作处理方法
            return self.admin_processor.handle_pending_operation_action(context, action_value)
        except Exception as e:
            debug_utils.log_and_print(f"❌ 缓存业务管理员卡片动作处理失败: {e}", log_level="ERROR")
            return ProcessResult.error_result(f"缓存操作处理失败: {str(e)}")

    # ================ 异步处理方法（供适配器调用）================

    def process_bili_video_async(self, cached_data: Dict[str, Any] = None) -> ProcessResult:
        """异步处理B站视频推荐（由FeishuAdapter调用）"""
        return self.bilibili_processor.process_bili_video_async(cached_data)

    def process_tts_async(self, tts_text: str) -> ProcessResult:
        """异步处理TTS生成（由FeishuAdapter调用）"""
        return self.media_processor.process_tts_async(tts_text)

    def process_image_generation_async(self, prompt: str) -> ProcessResult:
        """异步处理图像生成（由FeishuAdapter调用）"""
        return self.media_processor.process_image_generation_async(prompt)

    def process_image_conversion_async(self, image_base64: str, mime_type: str,
                                     file_name: str, file_size: int) -> ProcessResult:
        """异步处理图像风格转换（由FeishuAdapter调用）"""
        return self.media_processor.process_image_conversion_async(
            image_base64, mime_type, file_name, file_size
        )

    # ================ 定时任务方法（供SchedulerService调用）================

    def create_scheduled_message(self, message_type: str, **kwargs) -> ProcessResult:
        """创建定时任务消息（供SchedulerService调用）"""
        return self.schedule_processor.create_scheduled_message(message_type, **kwargs)

    # ================ 状态查询方法 ================

    def get_status(self) -> Dict[str, Any]:
        """获取消息处理器状态"""
        return {
            "processor_type": "modular",
            "sub_processors": {
                "text": "TextProcessor",
                "media": "MediaProcessor",
                "bilibili": "BilibiliProcessor",
                "admin": "AdminProcessor",
                "schedule": "ScheduleProcessor"
            },
            "app_controller_available": self.app_controller is not None,
            "supported_message_types": ["text", "image", "audio", "menu_click", "card_action"],
            "registered_actions": {
                "count": len(self.action_dispatchers),
                "actions": list(self.action_dispatchers.keys())
            }
        }