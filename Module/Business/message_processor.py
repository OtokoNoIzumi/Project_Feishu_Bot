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
    AdminProcessor, ScheduleProcessor,
    require_app_controller, safe_execute
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

    @safe_execute("消息分发器初始化失败")
    def _init_action_dispatchers(self):
        """初始化Action分发表，映射卡片动作到处理方法"""
        self.action_dispatchers = {
            # B站相关卡片动作
            "mark_bili_read": self._handle_mark_bili_read,

            # 管理员相关卡片动作（缓存业务，新版本）
            "confirm_user_update": self._handle_pending_admin_card_action,
            "cancel_user_update": self._handle_pending_admin_card_action,
            "update_user_type": self._handle_pending_admin_card_action,

            # 卡片选择器动作
            "select_change": self._handle_select_action,
        }

    @require_app_controller("系统服务不可用")
    @safe_execute("消息处理失败")
    def process_message(self, context: MessageContext) -> ProcessResult:
        """
        处理消息的主入口

        Args:
            context: 消息上下文

        Returns:
            ProcessResult: 处理结果
        """
        # 检查事件是否已处理（去重）
        is_duplicate, event_timestamp = self._is_duplicate_event(context.event_id)
        if is_duplicate:
            time_diff = time.time() - event_timestamp
            debug_utils.log_and_print(f"📋 重复事件已跳过 [{context.message_type}] [{context.content[:50]}] 时间差: {time_diff:.2f}秒", log_level="INFO")
            return ProcessResult.no_reply_result()

        # 记录新事件
        self._record_event(context)

        # 根据消息类型分发处理
        return self._dispatch_by_message_type(context)

    @safe_execute("消息类型分发失败")
    def _dispatch_by_message_type(self, context: MessageContext) -> ProcessResult:
        """根据消息类型分发处理"""
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

    @safe_execute("文本消息处理失败")
    def _process_text_message(self, context: MessageContext) -> ProcessResult:
        """处理文本消息"""
        user_msg = context.content

        # 1. 检查管理员命令
        if self.admin_processor.is_admin_command(user_msg):
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
        """处理图片消息"""
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

    @safe_execute("卡片动作处理失败")
    def _process_card_action(self, context: MessageContext) -> ProcessResult:
        """处理卡片动作"""
        action = context.content
        action_value = context.metadata.get('action_value', {})

        # 使用分发表处理动作
        handler = self.action_dispatchers.get(action)
        if handler:
            return handler(context, action_value)
        else:
            return ProcessResult.error_result(f"未知的卡片动作: {action}")


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

    @safe_execute("缓存业务管理员卡片动作处理失败")
    def _handle_pending_admin_card_action(self, context: MessageContext, action_value: Dict[str, Any]) -> ProcessResult:
        """
        处理缓存业务管理员卡片动作

        Args:
            context: 消息上下文
            action_value: 动作参数

        Returns:
            ProcessResult: 处理结果
        """
        # 直接调用admin_processor的缓存操作处理方法
        return self.admin_processor.handle_pending_operation_action(action_value)

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

    @safe_execute("下拉选择处理失败")
    def _handle_select_action(self, context: MessageContext, action_value: Dict[str, Any]) -> ProcessResult:
        """
        处理select_static类型的卡片动作（用户修改下拉选择）
        基于1.0.9版本的交互组件架构

        Args:
            context: 消息上下文
            action_value: 动作值，包含operation_id、option等字段

        Returns:
            ProcessResult: 处理结果
        """
        # 从action_value提取关键信息
        operation_id = action_value.get('operation_id')
        selected_option = action_value.get('option', '0')

        if not operation_id:
            debug_utils.log_and_print("❌ select_action缺少operation_id", log_level="ERROR")
            return ProcessResult.no_reply_result()

        # 获取pending操作
        pending_cache_service = self.app_controller.get_service('pending_cache')
        operation = pending_cache_service.get_operation(operation_id)

        if not operation:
            debug_utils.log_and_print(f"❌ 未找到操作: {operation_id}", log_level="ERROR")
            return ProcessResult.no_reply_result()

        # 使用交互组件架构获取更新逻辑
        update_success = self._apply_select_change(operation, selected_option)

        if not update_success:
            debug_utils.log_and_print(
                f"⚠️ 选择更新失败: option={selected_option}, operation={operation_id}",
                log_level="WARNING"
            )

        # 返回静默处理（select_action不显示Toast，用户体验更流畅）
        return ProcessResult.no_reply_result()

    def _apply_select_change(self, operation, selected_option: str) -> bool:
        """
        应用选择变更到操作数据
        基于1.0.9版本交互组件架构的配置驱动更新

        Args:
            operation: 待处理操作对象
            selected_option: 用户选择的选项值

        Returns:
            bool: 是否更新成功
        """
        try:
            # 导入交互组件定义
            from Module.Adapters.feishu_cards.admin_cards import AdminCardInteractionComponents

            # 获取操作类型映射
            type_mapping = AdminCardInteractionComponents.get_operation_type_mapping()
            component_getter = type_mapping.get(operation.operation_type)

            if not component_getter:
                debug_utils.log_and_print(f"⚠️ 未支持的操作类型select_change: {operation.operation_type}", log_level="WARNING")
                return False

            # 获取交互组件定义
            if component_getter == "get_user_update_confirm_components":
                components = AdminCardInteractionComponents.get_user_update_confirm_components(
                    operation.operation_id,
                    operation.operation_data.get('user_id', ''),
                    operation.operation_data.get('user_type', 1)
                )

                # 处理用户类型选择器更新
                selector_config = components.get("user_type_selector", {})
                target_field = selector_config.get("target_field")
                value_mapping = selector_config.get("value_mapping", {})

                if target_field and selected_option in value_mapping:
                    # 执行数据更新
                    new_value = value_mapping[selected_option]
                    old_value = operation.operation_data.get(target_field)

                    # 更新操作数据
                    pending_cache_service = self.app_controller.get_service('pending_cache')
                    success = pending_cache_service.update_operation_data(
                        operation.operation_id,
                        {target_field: new_value}
                    )

                    if success:
                        debug_utils.log_and_print(
                            f"🔄 操作数据已更新: {target_field} {old_value}→{new_value}",
                            log_level="INFO"
                        )

                    return success
                else:
                    debug_utils.log_and_print(f"⚠️ 无效的选项映射: {selected_option}", log_level="WARNING")
                    return False

            # 未来可扩展其他操作类型的处理
            else:
                debug_utils.log_and_print(f"⚠️ 未实现的组件获取方法: {component_getter}", log_level="WARNING")
                return False

        except Exception as e:
            debug_utils.log_and_print(f"❌ 应用选择变更失败: {e}", log_level="ERROR")
            return False