"""
基础卡片管理器

为所有feishu卡片管理器提供通用的基础接口和功能
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTriggerResponse
from Module.Common.scripts.common import debug_utils
from Module.Services.constants import ServiceNames, CardOperationTypes, ReplyModes
from Module.Business.processors import MessageContext_Refactor
# 配置驱动的管理器映射 - 从配置文件获取


class BaseCardManager(ABC):
    """卡片管理器基类 - 配置驱动架构"""

    def __init__(self, app_controller=None, card_info=None, card_config_key=None, sender=None, message_router=None):
        self.app_controller = app_controller
        self.card_info = card_info or {}
        self.sender = sender
        self.message_router = message_router

        # 直接从card_info获取配置
        self.card_name = self.card_info.get('card_name', '未知卡片')
        self.card_config_key = card_config_key or self.card_info.get('card_config_key', 'unknown')

        self.templates = {}
        self._initialize_templates()

    @abstractmethod
    def build_card(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """构建卡片内容 - 子类必须实现"""
        pass

    def get_card_type_name(self) -> str:
        """获取卡片类型名称 - 默认返回card_name，子类可根据需要重写"""
        return self.card_name

    def _initialize_templates(self):
        """统一的配置驱动模板初始化 - 基于子类的card_config_key"""
        if self.card_info.get('template_id') and self.card_info.get('template_version'):
            self.templates = {
                "template_id": self.card_info.get('template_id'),
                "template_version": self.card_info.get('template_version')
            }
        else:
            debug_utils.log_and_print(f"⚠️ 未找到{self.card_config_key}的模板配置", log_level="WARNING")

    def _build_template_content(self, template_params: Dict[str, Any]) -> Dict[str, Any]:
        """构建模板内容的统一入口"""
        if not self.templates.get("template_id"):
            debug_utils.log_and_print(f"⚠️ {self.get_card_type_name()}缺少模板配置", log_level="WARNING")
            return {}

        return {
            "type": "template",
            "data": {
                "template_id": self.templates["template_id"],
                "template_version": self.templates.get("template_version", "1.0.0"),
                "template_variable": template_params
            }
        }

    def _handle_card_operation_common(
        self,
        card_content,
        card_operation_type: str,
        update_toast_type: str = "success",
        **kwargs
    ):
        """
        通用卡片操作处理方法 - 从CardHandler迁移

        Args:
            card_content: 卡片内容
            card_operation_type: 操作类型 ('send' | 'update_response')
            update_toast_type: 更新提示类型
            **kwargs: 其他参数，用来提供发送对象，但这里需要宽容的定义吗？，需要三种参数，再看怎么处理和调优吧

        Returns:
            发送操作: Tuple[bool, Optional[str]] (是否成功, 消息ID)
            更新响应操作: P2CardActionTriggerResponse (响应对象)
        """
        match card_operation_type:
            case CardOperationTypes.SEND:
                # 构建发送参数
                card_id = self.sender.create_card_entity(card_content)
                if card_id:
                    # 在这里储存cardid和core_data，存到内存里的user的里面，还有一个堆栈——基本和pending是一套逻辑。
                    # user_id 是一个储存card_id的问题，之前不太统一。
                    user_service = self.app_controller.get_service(ServiceNames.USER_BUSINESS_PERMISSION)
                    user_service.save_new_card_business_data(kwargs.get("user_id"), card_id, kwargs.get("business_data", {}))
                    card_content = {"type": "card", "data": {"card_id": card_id}}
                # 用card_id发送卡片之后，这个值还需要另外找地方写下来，也就是需要管理message_id和card_id的映射，这个映射的管理可能也要写到cache里持久化。不然取不到。
                send_params = {"card_content": card_content, "reply_mode": self.card_info.get('reply_mode', ReplyModes.REPLY)}
                send_params.update(kwargs)

                send_params.pop("business_data", None)
                # 尝试用新方法先创建卡片实体，在发卡片id试试。
                # 三种卡片结构的数据格式不同，template和card需要带一层type，raw不需要。
                success, message_id = self.sender.send_interactive_card(**send_params)
                if not success:
                    debug_utils.log_and_print(f"❌ {self.card_info.get('card_name')}卡片发送失败", log_level="ERROR")
                    return False, None
                self.app_controller.get_service(ServiceNames.CACHE).update_message_id_card_id_mapping(message_id, card_id, self.card_name)
                self.app_controller.get_service(ServiceNames.CACHE).save_message_id_card_id_mapping()

                return success, message_id

            case CardOperationTypes.UPDATE_RESPONSE:
                # 构建卡片更新响应
                toast_message = kwargs.get("toast_message", "操作完成")
                response_data = {
                    "toast": {
                        "type": update_toast_type,
                        "content": toast_message
                    }
                }
                if isinstance(card_content, dict) and card_content.get('type') == 'card':
                    response_data['card'] = card_content
                else:
                    response_data['card'] = {
                        "type": "raw",
                        "data": card_content
                    }
                return P2CardActionTriggerResponse(response_data)

            case _:
                debug_utils.log_and_print(f"❌ 未知的{self.card_info.get('card_name')}卡片操作类型: {card_operation_type}", log_level="ERROR")
                return False, None

    def _get_core_data(self, context: MessageContext_Refactor):
        message_id = context.message_id
        cache_service = self.app_controller.get_service(ServiceNames.CACHE)
        card_info = cache_service.get_card_info(message_id)
        card_id = card_info.get('card_id', '')
        user_service = self.app_controller.get_service(ServiceNames.USER_BUSINESS_PERMISSION)
        business_data = user_service.get_card_business_data(context.user_id, card_id)
        return business_data, card_id, card_info

    def _build_base_card_structure(self, elements: List[Dict[str, Any]], header: Dict[str, Any], padding: str = "12px") -> Dict[str, Any]:
        """构建基础卡片结构"""
        return {
            "schema": "2.0",
            "config": {"update_multi": True, "wide_screen_mode": True},
            "body": {
                "direction": "vertical",
                "padding": padding,
                "elements": elements
            },
            "header": header
        }

    def _build_input_element(self, placeholder: str, initial_value: str, disabled: bool, action_data: Dict[str, Any], name: str = '', element_id: str = '') -> Dict[str, Any]:
        """构建输入框元素"""
        return {
            "tag": "input",
            "element_id": element_id,
            "placeholder": {"tag": "plain_text", "content": placeholder},
            "default_value": str(initial_value),
            "disabled": disabled,
            "name": name or element_id,
            "behaviors": [{"type": "callback", "value": action_data}]
        }

    def _build_card_header(self, title: str, subtitle: str = "", template: str = "blue", icon: str = "") -> Dict[str, Any]:
        """构建通用卡片头部"""
        header = {
            "title": {"tag": "plain_text", "content": title},
            "template": template
        }

        if subtitle:
            header["subtitle"] = {"tag": "plain_text", "content": subtitle}

        if icon:
            header["icon"] = {"tag": "standard_icon", "token": icon}

        return header

    def _build_status_based_header(self, base_title: str, is_confirmed: bool, result: str, confirmed_prefix: str = "") -> Dict[str, Any]:
        """构建基于状态的卡片头部 - 适用于确认类卡片"""
        if not is_confirmed:
            return self._build_card_header(base_title, "请确认记录信息", "blue", "edit_outlined")

        if result == "确认":
            title = f"{confirmed_prefix}{base_title}" if confirmed_prefix else base_title
            return self._build_card_header(title, "记录信息已确认并保存", "green", "done_outlined")

        return self._build_card_header("操作已取消", "", "grey", "close_outlined")

    # 辅助方法
    def _build_form_row(self, label: str, element: Dict[str, Any], width_list: List[str] = None, element_id: str = '') -> Dict[str, Any]:
        """构建表单行"""

        if width_list is None:
            width_list = ["80px", "auto"]

        return {
            "tag": "column_set",
            "horizontal_spacing": "8px",
            "horizontal_align": "left",
            "element_id": element_id,
            "columns": [
                {
                    "tag": "column",
                    "width": width_list[0],
                    "elements": [{
                        "tag": "markdown",
                        "content": f"**{label}**",
                        "text_align": "left",
                        "text_size": "normal_v2"
                    }],
                    "vertical_align": "center"
                },
                {
                    "tag": "column",
                    "width": width_list[1],
                    "elements": [element]
                }
            ],
        }

    def _build_select_element(self, placeholder: str, options: List[Dict[str, Any]], initial_value: str, disabled: bool, action_data: Dict[str, Any], element_id: str = '', name: str = '') -> Dict[str, Any]:
        """构建选择器元素"""
        # 查找初始选择索引，对飞书来说，索引从1开始，所以需要+1
        initial_index = -1
        for i, option in enumerate(options):
            if option.get('value') == initial_value:
                initial_index = i + 1
                break

        return {
            "tag": "select_static",
            "element_id": element_id,
            "placeholder": {"tag": "plain_text", "content": placeholder},
            "options": options,
            "initial_index": initial_index if initial_index >= 0 else None,
            "width": "fill",
            "disabled": disabled,
            "name": name or element_id,
            "behaviors": [{"type": "callback", "value": action_data}]
        }

    def _build_date_picker_element(self, placeholder: str, initial_date: str, disabled: bool, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建日期选择器元素"""
        element = {
            "tag": "date_picker",
            "placeholder": {"tag": "plain_text", "content": placeholder},
            "disabled": disabled,
            "behaviors": [{"type": "callback", "value": action_data}]
        }

        if initial_date:
            element["initial_date"] = initial_date

        return element

    def _build_checkbox_element(self, text: str, checked: bool, disabled: bool, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建复选框元素"""
        return {
            "tag": "checkbox",
            "text": {"tag": "plain_text", "content": text},
            "checked": checked,
            "disabled": disabled,
            "behaviors": [{"type": "callback", "value": action_data}]
        }


class FeishuCardRegistry:
    """飞书卡片管理器注册表"""

    def __init__(self):
        self._managers: Dict[str, BaseCardManager] = {}

    def register_manager(self, card_type: str, manager: BaseCardManager):
        """注册卡片管理器"""
        self._managers[card_type] = manager
        debug_utils.log_and_print(f"✅ 注册{manager.get_card_type_name()}卡片管理器成功", log_level="INFO")

    def get_manager(self, card_type: str) -> Optional[BaseCardManager]:
        """获取卡片管理器"""
        return self._managers.get(card_type)

    def get_all_managers(self) -> Dict[str, BaseCardManager]:
        """获取所有已注册的管理器"""
        return self._managers.copy()

    def get_manager_by_operation_type(self, operation_type: str, app_controller=None) -> Optional[BaseCardManager]:
        """根据业务ID获取对应的卡片管理器 - 配置驱动"""
        if not app_controller:
            debug_utils.log_and_print("❌ 缺少应用控制器，无法获取管理器映射", log_level="ERROR")
            return None

        # 从应用控制器获取业务映射服务
        card_mapping_service = app_controller.get_service(ServiceNames.CARD_OPERATION_MAPPING)
        if not card_mapping_service:
            debug_utils.log_and_print("❌ 卡片业务映射服务不可用", log_level="ERROR")
            return None

        # # 获取业务配置
        # operation_config = card_mapping_service.get_operation_config(operation_type)
        # if not operation_config:
        #     debug_utils.log_and_print(f"❌ 未找到业务配置: {operation_type}", log_level="WARNING")
        #     return None

        # 获取管理器标识
        card_config_key = card_mapping_service.get_card_config_key(operation_type)
        if not card_config_key:
            debug_utils.log_and_print(f"❌ 业务配置缺少card_config_key字段: {operation_type}", log_level="ERROR")
            return None

        return self.get_manager(card_config_key)


# 全局注册表实例
card_registry = FeishuCardRegistry()
