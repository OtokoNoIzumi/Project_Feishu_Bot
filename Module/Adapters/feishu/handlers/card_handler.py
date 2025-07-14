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
from Module.Business.daily_summary_business import DailySummaryBusiness
from ..decorators import (
    card_operation_safe, message_conversion_safe
)
from ..utils import noop_debug


class CardHandler:
    """飞书卡片处理器"""

    def __init__(self, app_controller, message_router, sender, debug_functions=None, card_registry=None):
        """
        初始化卡片处理器

        Args:
            app_controller: 应用控制器实例
            message_router: 业务消息路由器
            sender: 消息发送器实例
            debug_functions: 调试函数字典，包含debug_p2im_object等
        """
        self.message_router = message_router
        self.sender = sender

        # 获取应用控制器以访问服务
        self.app_controller = app_controller

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

        在业务概念上是顶层入口和最终终点，需要有能力调用和组织所有服务、卡片、处理器。

        遵循的通用业务架构是：
        1. 信息格式转换：将卡片点击转换为标准消息上下文处理
        1.1 原则上所有的卡片信息都是信息完备的，这里就包括了要访问的card_action，以及为了解决异步长时间的card_action提前回消息机制，而预先要发的普通消息
        2. 被跳过的通用架构的message_router，因为可以直接用参数直接执行卡片属地的内部方法
        3. 异步前的文本信息
        4. 用参数直接执行卡片属地的内部方法，至于是否需要pending_cache_service，由卡片内部决定

        这反过来要求卡片创建时需要遵循通用的信息格式，以及卡片内部方法的参数格式。
        核心思路还是要前后端解耦，不然直接这里就全做完就可以了。
        分离前端的业务数据，和后端的业务能力。

        """
        # 转换为标准消息上下文
        conversion_result = self._convert_card_to_context(data)

        context, context_refactor = conversion_result

        if self.sender.filter_duplicate_message(context_refactor):
            # 似乎对于card的回调事件，根本进不来，回另外报超时，并且不重复，最后可以考虑删掉
            # return 可以不用P2CardActionTriggerResponse，直接return
            return

        if context_refactor.content.card_config_key in [CardConfigKeys.DESIGN_PLAN, CardConfigKeys.BILIBILI_VIDEO_INFO, CardConfigKeys.ROUTINE_RECORD]:
            message_before_action = context_refactor.content.value.get('message_before_action', '')
            if message_before_action:
                # 看起来是冗余的检测，但胜在增加了可读性，也确保了外层的局部可靠
                self.sender.send_feishu_message_reply(context_refactor, message_before_action)

            card_action = context_refactor.content.card_action_key
            card_config_key = context_refactor.content.card_config_key
            # 获取card_manager
            card_manager = self.card_registry.get_manager(card_config_key)
            if not card_manager:
                return P2CardActionTriggerResponse({
                    "toast": {"type": "error", "content": f"未找到卡片管理器: {card_config_key}"}
                })

            if hasattr(card_manager, card_action):
                return getattr(card_manager, card_action)(context_refactor)

        # 特殊类型处理
        card_action = context_refactor.content.card_action_key
        if hasattr(self, card_action):
            return getattr(self, card_action)(context_refactor)

        # 调用业务处理器，由业务层判断处理类型
        result = self.message_router.process_message(context)
        # 统一处理成功和失败的响应，减少分支嵌套
        if result.success:
            # 特殊类型处理
            match result.response_type:
                case ResponseTypes.ADMIN_CARD_UPDATE:
                    return self._handle_admin_card_operation(
                        result_content=result.response_content,
                        card_operation_type=CardOperationTypes.UPDATE_RESPONSE
                    )

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
        event_id = data.header.event_id

        user_id = data.event.operator.open_id

        # 对于卡片事件，使用当前时间而不是事件时间（保持原有逻辑）
        timestamp = datetime.datetime.now()
        user_name = self.sender.get_user_name(user_id)

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
        card_config_key = action_value.get('card_config_key', "")

        content_refactor = CardActionContent(
            tag=action_tag,
            value=action_value,
            card_config_key=card_config_key,
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
        result,
        context_refactor: MessageContext_Refactor,
        **kwargs
    ) -> Any:
        """
        分发卡片响应，作为一个公共模块接受外部的参数，并根据参数调用不同的卡片操作方法
        作为一个response的属性，上游是MessageContext/ProcessResult，后者优先级更高，最好能分离清楚不再包括原生data，不然功能耦合太重。
        """
        card_manager = self.card_registry.get_manager(card_config_key)
        if not card_manager:
            debug_utils.log_and_print(f"❌ 未找到卡片管理器: {card_config_key}", log_level="ERROR")
            return ProcessResult.error_result(f"未找到卡片管理器: {card_config_key}")
        if hasattr(card_manager, card_action):
            return getattr(card_manager, card_action)(result, context_refactor, **kwargs)
        else:
            debug_utils.log_and_print(f"❌ 未支持的动作: {card_action}", log_level="ERROR")
            return ProcessResult.error_result(f"未支持的动作: {card_action}")

    @card_operation_safe("标记B站视频为已读失败")
    def mark_bili_read_in_daily_summary(self, context_refactor: MessageContext_Refactor) -> P2CardActionTriggerResponse:
        """
        直接处理标记B站视频为已读事件，调用业务层方法
        因为没有特地新建daily_summary的卡片模块，所以直接在这里处理。

        Args:
            context_refactor: 消息上下文

        Returns:
            P2CardActionTriggerResponse: 处理结果
        """
        # 调用业务层方法处理标记已读逻辑
        daily_summary_business = DailySummaryBusiness(app_controller=self.app_controller)
        action_value = context_refactor.content.value
        result = daily_summary_business.mark_bili_read_v2(action_value)

        if not result.success:
            return P2CardActionTriggerResponse({
                "toast": {"type": "error", "content": result.error_message or "标记为已读失败"}
            })

        # 处理业务层返回的响应内容
        response_content = result.response_content

        message_id = context_refactor.message_id
        cache_service = self.app_controller.get_service(ServiceNames.CACHE)
        card_info = cache_service.get_card_info(message_id)
        card_id = card_info.get('card_id', '')

        self.sender.delete_card_element(
            card_id=card_id,
            element_id=response_content.get('remove_element_id'),
            sequence=card_info.get('sequence', 1),
            message_id=message_id,
            delay_seconds=0.3
        )

        # 移除不需要返回给飞书的字段
        response_content.pop('remove_element_id', None)
        response_content.pop('text_element_id', None)

        return P2CardActionTriggerResponse(response_content)
