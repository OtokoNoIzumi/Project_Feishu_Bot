"""
飞书卡片处理器 (Feishu Card Handler)

负责处理飞书卡片事件，包括：
- 卡片按钮点击事件处理
- 卡片到消息上下文的转换
- 卡片操作通用处理
"""

import time
import datetime
from typing import Optional, Dict, Any
from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTriggerResponse

from Module.Common.scripts.common import debug_utils
from Module.Business.processors import MessageContext, ProcessResult, MessageContext_Refactor, CardActionContent
from Module.Services.constants import (
    ServiceNames, CardOperationTypes, CardConfigKeys, ResponseTypes,
    Messages, CardActions, UIElements, FieldNames, DefaultValues, MessageTypes,
    DesignPlanConstants, AdapterNames
)
from ..decorators import (
    card_operation_safe, message_conversion_safe
)
from ..utils import noop_debug


class CardHandler:
    """飞书卡片处理器"""

    def __init__(self, message_processor, sender, user_name_getter, debug_functions=None, card_registry=None):
        """
        初始化卡片处理器

        Args:
            message_processor: 业务消息处理器
            sender: 消息发送器实例
            user_name_getter: 用户名获取函数
            debug_functions: 调试函数字典，包含debug_p2im_object等
        """
        self.message_processor = message_processor
        self.sender = sender
        self._get_user_name = user_name_getter

        # 获取应用控制器以访问服务
        self.app_controller = getattr(message_processor, 'app_controller', None)

        # 获取配置驱动的卡片注册表
        self.card_registry = card_registry

        # 设置调试函数
        if debug_functions:
            self.debug_p2im_object = debug_functions.get('debug_p2im_object', noop_debug)
        else:
            self.debug_p2im_object = noop_debug

    @property
    def card_mapping_service(self):
        """获取卡片业务映射服务"""
        if self.app_controller:
            return self.app_controller.get_service(ServiceNames.CARD_OPERATION_MAPPING)
        return None

    @card_operation_safe("飞书卡片处理失败")
    def handle_feishu_card(self, data) -> P2CardActionTriggerResponse:
        """
        处理飞书卡片按钮点击事件

        将卡片点击转换为标准消息上下文处理
        """
        # 转换为标准消息上下文
        conversion_result = self._convert_card_to_context(data)

        context, context_refactor = conversion_result

        # 按照新的架构，节奏process和adapter，那么必要的数据转换要先在这里完成，那就要分发回卡片模块，对于design_plan，我许可qrcode在内部调用
        if context.metadata.get('action_value').get('card_config_key') == CardConfigKeys.DESIGN_PLAN:
            card_action = context.metadata.get('action_value').get('card_action')
            card_config_key = context.metadata.get('action_value').get('card_config_key')
            if not card_config_key:
                return P2CardActionTriggerResponse({
                    "toast": {"type": "error", "content": "缺少卡片配置键"}
                })
            # 获取card_manager
            card_manager = self.card_registry.get_manager(card_config_key)
            if not card_manager:
                return P2CardActionTriggerResponse({
                    "toast": {"type": "error", "content": f"未找到卡片管理器: {card_config_key}"}
                })
            method_name = f"handle_{card_action}"

            if hasattr(card_manager, method_name):
                return getattr(card_manager, method_name)(context_refactor)


        # 调用业务处理器，由业务层判断处理类型
        result = self.message_processor.process_message(context)
        # 统一处理成功和失败的响应，减少分支嵌套
        if result.success:
            # 特殊类型处理
            match result.response_type:
                case ResponseTypes.BILI_CARD_UPDATE:
                    return self._handle_bili_card_operation(
                        result_content=result.response_content,
                        card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
                        toast_message=Messages.VIDEO_MARKED_READ
                    )
                case ResponseTypes.ADMIN_CARD_UPDATE:
                    return self._handle_admin_card_operation(
                        result_content=result.response_content,
                        card_operation_type=CardOperationTypes.UPDATE_RESPONSE
                    )
                case ResponseTypes.SCHEDULER_CARD_UPDATE_BILI_BUTTON:
                    return P2CardActionTriggerResponse(result.response_content)

                case _:
                    # 默认成功响应
                    return P2CardActionTriggerResponse({
                        "toast": {
                            "type": "success",
                            "content": Messages.OPERATION_SUCCESS
                        }
                    })
        else:
            # 失败响应
            return P2CardActionTriggerResponse({
                "toast": {
                    "type": "error",
                    "content": result.error_message or Messages.OPERATION_FAILED
                }
            })

    @message_conversion_safe("卡片转换失败")
    def _convert_card_to_context(self, data) -> Optional[MessageContext]:
        """
        将飞书卡片点击转换为标准消息上下文
        更好的做法是快速获取卡片事件里的标识信息，然后根据标识信息获取卡片管理器
        再根据卡片管理器获取格式化的方法，然后调用方法，这样就不需要再根据action_tag来处理了，用get_attr从参数里获取方法并执行，实现动态调用。
        """
        # 调试输出P2ImMessageReceiveV1Card对象信息
        self.debug_p2im_object(data, "P2ImMessageReceiveV1Card")

        # 提取基本信息
        event_id = f"card_{data.event.operator.open_id}_{int(time.time())}"  # 卡片事件生成ID
        user_id = data.event.operator.open_id

        # 对于卡片事件，使用当前时间而不是事件时间（保持原有逻辑）
        timestamp = datetime.datetime.now()
        user_name = self._get_user_name(user_id)

        # ✅ 标准化字段：独立必要字段
        adapter_name = AdapterNames.FEISHU  # 标识来源adapter
        message_id = data.event.context.open_message_id  # update操作需要

        # 卡片动作信息
        action = data.event.action
        # 优化action.value为None或空的处理逻辑
        action_value = getattr(action, 'value', None)
        if not isinstance(action_value, dict) or action_value is None:
            action_value = {}

        action_tag = action.tag if hasattr(action, 'tag') else 'button'
        content = action_value.get('card_action', '')

        content_refactor = CardActionContent(
            tag=action_tag,
            action_name=action.name if hasattr(action, 'name') else None,
            value=action_value,
            card_action_key=content,
            form_data=action.form_value,
            selected_option=action.option if hasattr(action, 'option') else None,
            input_value=action.input_value if hasattr(action, 'input_value') else None
        )

        New_MessageContext = MessageContext_Refactor(
            adapter_name=AdapterNames.FEISHU,
            timestamp=timestamp,
            event_id=event_id,

            user_id=user_id,
            user_name=user_name,
            message_id=message_id,
            parent_message_id=message_id,

            message_type=MessageTypes.CARD_ACTION,
            content=content_refactor,
        )

        # 处理不同类型的卡片交互事件
        match action_tag:
            case UIElements.SELECT_STATIC:
                # 对于select_static，action.option包含选中的值
                action_option = action.option if hasattr(action, 'option') else '0'
                action_value.update({
                    FieldNames.OPTION: action_option,
                    FieldNames.TAG: action_tag
                })
            case UIElements.INPUT:
                # 对于input类型，action.input_value包含用户输入的值
                input_value = action.input_value if hasattr(action, 'input_value') else DefaultValues.EMPTY_STRING
                action_value.update({
                    FieldNames.VALUE: input_value,  # 将输入值添加到action_value中
                    FieldNames.TAG: action_tag
                })
            case _:
                # 普通按钮动作
                if action.name == 'design_confirm':
                    # 反转FORM_FIELD_MAP，直接查找key对应的form_key，避免嵌套循环
                    reverse_field_map = {v: k for k, v in DesignPlanConstants.FORM_FIELD_MAP.items()}
                    for key, value in action.form_value.items():
                        form_key = reverse_field_map.get(key)
                        if form_key:
                            action_value['raw_card_data'][form_key] = value


        legacy_context = MessageContext(
            user_id=user_id,
            user_name=user_name,
            message_type=MessageTypes.CARD_ACTION,  # 自定义类型
            content=content,
            timestamp=timestamp,
            event_id=event_id,
            adapter_name=adapter_name,  # ✅ 独立字段
            message_id=message_id,      # ✅ 独立字段
            metadata={
                'action_value': action_value,
                'action_tag': action_tag
            }
        )

        return legacy_context, New_MessageContext

    @card_operation_safe("B站卡片操作失败")
    def _handle_bili_card_operation(self, result_content: Dict[str, Any], card_operation_type: str, **kwargs) -> Any:
        """
        统一处理B站卡片的构建和操作

        Args:
            video_data: 业务层返回的视频数据
            card_operation_type: 操作类型 ('send' | 'update_response')
            **kwargs: 额外参数(user_id, toast_message等)

        Returns:
            bool: 发送操作的成功状态
            P2CardActionTriggerResponse: 更新响应操作的响应对象
        """
        # B站特有的参数验证
        if card_operation_type == CardOperationTypes.SEND:
            user_id = kwargs.get(FieldNames.USER_ID)
            if not user_id:
                debug_utils.log_and_print("❌ 发送B站卡片缺少用户ID", log_level="ERROR")
                return False, None

        # 使用配置驱动获取B站卡片管理器
        bili_card_manager = self.card_registry.get_manager(CardConfigKeys.BILIBILI_VIDEO_INFO)
        if not bili_card_manager:
            debug_utils.log_and_print("❌ 未找到B站卡片管理器", log_level="ERROR")
            if card_operation_type == CardOperationTypes.SEND:
                return False, None
            return False
        update_toast_type = result_content.get('result_type', 'success') if isinstance(result_content, dict) else 'success'
        # 使用通用卡片操作处理
        return bili_card_manager._handle_card_operation_common(
            card_content=bili_card_manager.build_card(video_data=result_content),
            card_operation_type=card_operation_type,
            update_toast_type=update_toast_type,
            **kwargs
        )

    @card_operation_safe("管理员卡片操作失败")
    def _handle_admin_card_operation(self, result_content: Dict[str, Any], card_operation_type: str,**kwargs) -> Any:
        """
        统一处理管理员卡片的构建和操作 - 配置驱动版本

        Args:
            operation_data: 业务层返回的操作数据
            card_operation_type: 操作类型 ('send' | 'update_response')
            **kwargs: 额外参数(chat_id, user_id, message_id等)

        Returns:
            bool: 发送操作的成功状态
            P2CardActionTriggerResponse: 更新响应操作的响应对象
        """
        # 管理员特有的参数验证
        match card_operation_type:
            case CardOperationTypes.SEND:
                chat_id = kwargs.get("chat_id")
                message_id = kwargs.get("message_id")
                if not chat_id or not message_id:
                    debug_utils.log_and_print("❌ 发送管理员卡片缺少chat_id或message_id", log_level="ERROR")
                    return False, None
            case _:
                pass

        # 从操作数据获取业务ID - 配置化解决方案
        operation_type = result_content.get('operation_type', '')
        if not operation_type:
            debug_utils.log_and_print("❌ 缺少业务ID (operation_type)", log_level="ERROR")
            if card_operation_type == CardOperationTypes.SEND:
                return False, None
            return False

        # 使用配置驱动获取卡片管理器
        card_manager = self.card_registry.get_manager_by_operation_type(operation_type, self.app_controller)
        if not card_manager:
            debug_utils.log_and_print(f"❌ 未找到业务ID对应的管理器: {operation_type}", log_level="ERROR")
            if card_operation_type == CardOperationTypes.SEND:
                return False, None
            return False
        update_toast_type = result_content.get('result_type', 'success') if isinstance(result_content, dict) else 'success'

        # 使用通用卡片操作处理
        return card_manager._handle_card_operation_common(
            card_content=card_manager.build_card(admin_confirm_action_data=result_content),
            card_operation_type=card_operation_type,
            update_toast_type=update_toast_type,
            **kwargs
        )

    def create_card_ui_update_callback(self):
        """
        创建卡片UI更新回调函数

        Returns:
            Callable: 可以传递给pending_cache_service的回调函数
        """
        def update_card_ui(operation) -> bool:
            """
            卡片UI更新回调实现

            Args:
                operation: PendingOperation对象

            Returns:
                bool: 更新是否成功
            """
            try:
                if not operation.ui_message_id:
                    debug_utils.log_and_print(f"❌ 卡片更新失败: 缺少ui_message_id [{operation.operation_id[:20]}...]", log_level="ERROR")
                    return False

                # 使用配置驱动获取卡片管理器和构建方法
                operation_type = operation.operation_data.get('operation_type', '')
                card_manager = self.card_registry.get_manager_by_operation_type(operation_type, self.app_controller)
                if not card_manager:
                    debug_utils.log_and_print(f"❌ 卡片更新失败: 未找到操作类型对应的管理器 {operation_type}", log_level="ERROR")
                    return False

                # 构建卡片内容
                card_content = card_manager.build_card(operation.operation_data)

                # 调用消息发送器的卡片更新方法
                success = self.sender.update_interactive_card(operation.ui_message_id, card_content)

                # 只在失败时记录错误日志
                if not success:
                    debug_utils.log_and_print(f"❌ 卡片更新API失败 [{operation.operation_id[:20]}...]", log_level="ERROR")

                return success

            except Exception as e:
                debug_utils.log_and_print(f"❌ 卡片UI更新异常: {e} [{operation.operation_id[:20]}...]", log_level="ERROR")
                return False

        return update_card_ui

    def handle_card_action(self, context: MessageContext) -> ProcessResult:
        """处理卡片动作 - 配置驱动路由到具体card_manager"""
        action_value = context.metadata.get('action_value', {})

        # ✅ 通过card_config_key路由到正确的card_manager
        card_config_key = action_value.get('card_config_key')
        if not card_config_key:
            return ProcessResult.error_result("缺少卡片配置键")

        # 获取card_manager
        card_manager = self.card_registry.get_manager(card_config_key)
        if not card_manager:
            return ProcessResult.error_result(f"未找到卡片管理器: {card_config_key}")

        # ✅ 调用card_manager的handle方法，传入标准化context
        card_action = action_value.get('card_action')
        method_name = f"handle_{card_action}"

        if hasattr(card_manager, method_name):
            return getattr(card_manager, method_name)(context)
        else:
            return ProcessResult.error_result(f"未支持的动作: {card_action}")

    def dispatch_card_response(
        self,
        card_config_key: str,
        card_action: str,
        result: ProcessResult,
        context_refactor: MessageContext_Refactor,
        **kwargs
    ) -> Any:
        """
        分发卡片响应，作为一个公共模块接受外部的参数，并根据参数调用不同的卡片操作方法
        作为一个response的属性，上游是MessageContext/ProcessResult，后者优先级更高，最好能分离清楚不再包括原生data，不然功能耦合太重。
        """
        card_manager = self.card_registry.get_manager(card_config_key)
        if not card_manager:
            return ProcessResult.error_result(f"未找到卡片管理器: {card_config_key}")
        method_name = f"handle_{card_action}"
        if hasattr(card_manager, method_name):
            return getattr(card_manager, method_name)(result, context_refactor)
        else:
            return ProcessResult.error_result(f"未支持的动作: {card_action}")
