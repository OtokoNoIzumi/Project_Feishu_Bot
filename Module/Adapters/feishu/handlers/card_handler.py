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
from Module.Business.processors import MessageContext
from Module.Services.constants import (
    ServiceNames, CardOperationTypes, CardConfigKeys, ResponseTypes,
    Messages, CardActions, UIElements, FieldNames, DefaultValues, MessageTypes
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
            return self.app_controller.get_service(ServiceNames.CARD_BUSINESS_MAPPING)
        return None

    @card_operation_safe("飞书卡片处理失败")
    def handle_feishu_card(self, data) -> P2CardActionTriggerResponse:
        """
        处理飞书卡片按钮点击事件

        将卡片点击转换为标准消息上下文处理
        """
        # 转换为标准消息上下文
        context = self._convert_card_to_context(data)
        if not context:
            return P2CardActionTriggerResponse({})

        # 调用业务处理器，由业务层判断处理类型
        result = self.message_processor.process_message(context)
        # 统一处理成功和失败的响应，减少分支嵌套
        if result.success:
            # 特殊类型处理
            match result.response_type:
                case ResponseTypes.BILI_CARD_UPDATE:
                    return self._handle_bili_card_operation(
                        result.response_content,
                        card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
                        toast_message=Messages.VIDEO_MARKED_READ
                    )
                case ResponseTypes.ADMIN_CARD_UPDATE:
                    return self._handle_admin_card_operation(
                        result.response_content,
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
        """将飞书卡片点击转换为标准消息上下文"""
        # 调试输出P2ImMessageReceiveV1Card对象信息
        self.debug_p2im_object(data, "P2ImMessageReceiveV1Card")

        # 提取基本信息
        event_id = f"card_{data.event.operator.open_id}_{int(time.time())}"  # 卡片事件生成ID
        user_id = data.event.operator.open_id

        # 对于卡片事件，使用当前时间而不是事件时间（保持原有逻辑）
        timestamp = datetime.datetime.now()
        user_name = self._get_user_name(user_id)

        # 卡片动作信息
        action = data.event.action
        # 优化action.value为None或空的处理逻辑
        action_value = getattr(action, 'value', None)
        if not isinstance(action_value, dict) or action_value is None:
            action_value = {}

        action_tag = action.tag if hasattr(action, 'tag') else 'button'

        # 处理不同类型的卡片交互事件
        if action_tag == UIElements.SELECT_STATIC:
            # 对于select_static，action.option包含选中的值
            action_option = action.option if hasattr(action, 'option') else '0'
            action_value.update({
                FieldNames.ACTION: CardActions.UPDATE_USER_TYPE,  # 统一的动作名
                FieldNames.OPTION: action_option,
                FieldNames.TAG: action_tag
            })
            content = CardActions.UPDATE_USER_TYPE
        elif action_tag == UIElements.INPUT:
            # 对于input类型，action.input_value包含用户输入的值
            input_value = action.input_value if hasattr(action, 'input_value') else DefaultValues.EMPTY_STRING

            # 处理空输入：单空格" "代替空字符串
            if input_value == DefaultValues.SINGLE_SPACE:
                input_value = DefaultValues.EMPTY_STRING
                debug_utils.log_and_print("🔄 检测到单空格输入，转换为空字符串", log_level="INFO")
            action_value.update({
                FieldNames.VALUE: input_value,  # 将输入值添加到action_value中
                FieldNames.TAG: action_tag
            })
            content = action_value.get(FieldNames.ACTION, DefaultValues.UNKNOWN_INPUT_ACTION)
        else:
            # 普通按钮动作
            content = action_value.get(FieldNames.ACTION, DefaultValues.UNKNOWN_ACTION)

        return MessageContext(
            user_id=user_id,
            user_name=user_name,
            message_type=MessageTypes.CARD_ACTION,  # 自定义类型
            content=content,
            timestamp=timestamp,
            event_id=event_id,
            metadata={
                'action_value': action_value,
                'action_tag': action_tag,
                'interaction_type': 'card',
                FieldNames.OPEN_MESSAGE_ID: data.event.context.open_message_id if hasattr(data.event, 'context') and hasattr(data.event.context, 'open_message_id') else DefaultValues.EMPTY_STRING,
                FieldNames.OPEN_CHAT_ID: data.event.context.open_chat_id if hasattr(data.event, 'context') and hasattr(data.event.context, 'open_chat_id') else DefaultValues.EMPTY_STRING
            }
        )

    @card_operation_safe("B站卡片操作失败")
    def _handle_bili_card_operation(self, video_data: Dict[str, Any], card_operation_type: str, **kwargs) -> Any:
        """
        统一处理B站卡片的构建和操作

        Args:
            video_data: 业务层返回的视频数据
            operation_type: 操作类型 ('send' | 'update_response')
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
                return False

        # 使用配置驱动获取B站卡片管理器
        bili_card_manager = self.card_registry.get_manager(CardConfigKeys.BILIBILI_VIDEO_INFO)
        if not bili_card_manager:
            debug_utils.log_and_print("❌ 未找到B站卡片管理器", log_level="ERROR")
            return False

        # 使用通用卡片操作处理
        return self._handle_card_operation_common(
            card_content=bili_card_manager.build_card(video_data),
            data=video_data,
            card_operation_type=card_operation_type,
            card_config_type=CardConfigKeys.BILIBILI_VIDEO_INFO,
            **kwargs
        )

    @card_operation_safe("管理员卡片操作失败")
    def _handle_admin_card_operation(self, operation_data: Dict[str, Any], card_operation_type: str,**kwargs) -> Any:
        """
        统一处理管理员卡片的构建和操作 - 配置驱动版本

        Args:
            operation_data: 业务层返回的操作数据
            operation_type: 操作类型 ('send' | 'update_response')
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
                    return False
            case _:
                pass

        # 从操作数据获取业务ID - 配置化解决方案
        business_id = operation_data.get('operation_type', '')
        if not business_id:
            debug_utils.log_and_print("❌ 缺少业务ID (operation_type)", log_level="ERROR")
            return False

        # 使用配置驱动获取卡片管理器
        card_manager = self.card_registry.get_manager_by_business_id(business_id, self.app_controller)
        if not card_manager:
            debug_utils.log_and_print(f"❌ 未找到业务ID对应的管理器: {business_id}", log_level="ERROR")
            return False

        # 使用通用卡片操作处理
        return self._handle_card_operation_common(
            card_content=card_manager.build_card(operation_data),
            data=operation_data,
            card_operation_type=card_operation_type,
            card_config_type=CardConfigKeys.USER_UPDATE,
            **kwargs
        )

    def _handle_card_operation_common(
        self,
        card_content,
        data: Dict[str, Any],
        card_operation_type: str,
        card_config_type: str,
        **kwargs
    ) -> Any:
        """
        通用卡片操作处理方法

        Args:
            card_manager: 卡片管理器实例
            build_method_name: 卡片构建方法名
            data: 业务数据
            operation_type: 操作类型 ('send' | 'update_response')
            card_config_type: 卡片配置类型，用于获取回复模式
            **kwargs: 额外参数

        Returns:
            发送操作: Tuple[bool, Optional[str]] (是否成功, 消息ID)
            更新响应操作: P2CardActionTriggerResponse (响应对象)
        """
        # 使用卡片管理器构建卡片内容
        match card_operation_type:
            case CardOperationTypes.SEND:
                # 从配置获取卡片的回复模式
                reply_mode = self.sender.get_card_reply_mode(card_config_type)

                # 构建发送参数
                send_params = {"card_content": card_content, "reply_mode": reply_mode}
                send_params.update(kwargs)

                success, message_id = self.sender.send_interactive_card(**send_params)
                if not success:
                    debug_utils.log_and_print(f"❌ {card_config_type}卡片发送失败", log_level="ERROR")
                    return False, None

                return success, message_id

            case CardOperationTypes.UPDATE_RESPONSE:
                # 构建卡片更新响应
                toast_message = kwargs.get("toast_message", "操作完成")
                result_type = data.get('result_type', 'success') if isinstance(data, dict) else 'success'

                response_data = {
                    "toast": {
                        "type": result_type,
                        "content": toast_message
                    },
                    "card": {
                        "type": "raw",
                        "data": card_content
                    }
                }
                return P2CardActionTriggerResponse(response_data)

            case _:
                debug_utils.log_and_print(f"❌ 未知的{card_config_type}卡片操作类型: {card_operation_type}", log_level="ERROR")
                return False, None

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
                card_manager = self.card_registry.get_manager_by_business_id(operation.operation_type, self.app_controller)
                if not card_manager:
                    debug_utils.log_and_print(f"❌ 卡片更新失败: 未找到操作类型对应的管理器 {operation.operation_type}", log_level="ERROR")
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
