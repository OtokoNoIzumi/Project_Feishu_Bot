"""
基础卡片管理器

为所有feishu卡片管理器提供通用的基础接口和功能
"""

import json
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from lark_oapi.event.callback.model.p2_card_action_trigger import (
    P2CardActionTriggerResponse,
)
from Module.Common.scripts.common import debug_utils
from Module.Services.constants import (
    ServiceNames,
    CardOperationTypes,
    ReplyModes,
    ColorTypes,
)
from Module.Business.processors import MessageContext_Refactor

# 配置驱动的管理器映射 - 从配置文件获取


class BaseCardManager(ABC):
    """卡片管理器基类 - 配置驱动架构"""

    def __init__(
        self,
        app_controller=None,
        card_static_config=None,
        card_config_key=None,
        sender=None,
        message_router=None,
        single_instance=False,
    ):
        self.app_controller = app_controller
        self.card_static_config = card_static_config or {}
        self.sender = sender
        self.message_router = message_router
        self.single_instance = single_instance

        # 存储所有配置
        if not hasattr(self, "_configs"):
            self._configs = {}

        # 直接从card_info获取配置，这个可以用在非单例的卡片管理器上，单例的特殊卡片管理器需要自己实现。
        self.card_name = self.card_static_config.get("card_name", "未知卡片")
        self.card_config_key = card_config_key or self.card_static_config.get(
            "card_config_key", "unknown"
        )

        self.templates = {}
        self._initialize_templates()

    @abstractmethod
    def build_card(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """构建卡片内容 - 子类必须实现"""

    def get_card_name_by_config_key(self, card_config_key=None):
        """获取指定配置键的卡片名称"""
        if self.single_instance:
            return self._configs.get(card_config_key, {}).get("card_name", "未知卡片")

        return self.card_name

    def get_reply_mode_by_config_key(self, card_config_key=None):
        """获取指定配置键的卡片名称"""
        if self.single_instance:
            return self._configs.get(card_config_key, {}).get(
                "reply_mode", ReplyModes.REPLY
            )

        return self.card_static_config.get("reply_mode", ReplyModes.REPLY)

    def get_card_type_name(self) -> str:
        """获取卡片类型名称 - 默认返回card_name，子类可根据需要重写"""
        return self.card_name

    def _initialize_templates(self):
        """统一的配置驱动模板初始化 - 基于子类的card_config_key"""
        # 正好单例的特例模式业务太复杂，没有这套逻辑，暂时不用考虑兼容。
        if self.card_static_config.get("template_id") and self.card_static_config.get(
            "template_version"
        ):
            self.templates = {
                "template_id": self.card_static_config.get("template_id"),
                "template_version": self.card_static_config.get("template_version"),
            }
        else:
            debug_utils.log_and_print(
                f"⚠️ 未找到{self.card_config_key}的模板配置", log_level="WARNING"
            )

    def _build_template_content(
        self, template_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """构建模板内容的统一入口"""
        if not self.templates.get("template_id"):
            debug_utils.log_and_print(
                f"⚠️ {self.get_card_type_name()}缺少模板配置", log_level="WARNING"
            )
            return {}

        return {
            "type": "template",
            "data": {
                "template_id": self.templates["template_id"],
                "template_version": self.templates.get("template_version", "1.0.0"),
                "template_variable": template_params,
            },
        }

    def handle_card_operation_common(
        self,
        card_content,
        card_operation_type: str,
        update_toast_type: str = "success",
        **kwargs,
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
                current_config_key = kwargs.get("card_config_key", self.card_config_key)
                reply_mode = self.get_reply_mode_by_config_key(
                    card_config_key=current_config_key
                )
                card_name = self.get_card_name_by_config_key(current_config_key)

                card_id = self.sender.create_card_entity(card_content)
                if card_id:
                    # 在这里储存cardid和core_data，存到内存里的user的里面，还有一个堆栈——基本和pending是一套逻辑。
                    user_service = self.app_controller.get_service(
                        ServiceNames.USER_BUSINESS_PERMISSION
                    )
                    user_service.save_new_card_business_data(
                        kwargs.get("user_id"), card_id, kwargs.get("business_data", {})
                    )
                    card_content = {"type": "card", "data": {"card_id": card_id}}

                send_params = {
                    "card_content": card_content,
                    "reply_mode": reply_mode,
                }
                send_params.update(kwargs)

                send_params.pop("business_data", None)
                send_params.pop("card_config_key", None)

                # 三种卡片结构的数据格式不同，template和card需要带一层type，raw不需要。
                success, message_id = self.sender.send_interactive_card(**send_params)
                if not success:
                    debug_utils.log_and_print(
                        f"❌ {card_name}卡片发送失败",
                        log_level="ERROR",
                    )
                    return False, None
                self.app_controller.get_service(
                    ServiceNames.CACHE
                ).update_message_id_card_id_mapping(message_id, card_id, self.card_name)
                self.app_controller.get_service(
                    ServiceNames.CACHE
                ).save_message_id_card_id_mapping()

                return success, message_id

            case CardOperationTypes.UPDATE_RESPONSE:
                # 构建卡片更新响应
                toast_message = kwargs.get("toast_message", "操作完成")
                response_data = {
                    "toast": {"type": update_toast_type, "content": toast_message}
                }
                if (
                    isinstance(card_content, dict)
                    and card_content.get("type") == "card"
                ):
                    response_data["card"] = card_content
                else:
                    response_data["card"] = {"type": "raw", "data": card_content}
                return P2CardActionTriggerResponse(response_data)

            case _:
                debug_utils.log_and_print(
                    f"❌ 未知的{self.card_name}卡片操作类型: {card_operation_type}",
                    log_level="ERROR",
                )
                return False, None

    def get_core_data(self, context: MessageContext_Refactor):
        """获取卡片核心数据"""
        message_id = context.message_id
        cache_service = self.app_controller.get_service(ServiceNames.CACHE)
        card_info = cache_service.get_card_info(message_id)
        card_id = card_info.get("card_id", "")
        user_service = self.app_controller.get_service(
            ServiceNames.USER_BUSINESS_PERMISSION
        )
        business_data = user_service.get_card_business_data(context.user_id, card_id)
        return business_data, card_id, card_info

    def safe_get_business_data(
        self,
        business_data: Dict[str, Any],
        sub_business_name: str = "",
        max_depth: int = 10,
    ) -> Dict[str, Any]:
        """
        安全地从容器里获取到自己业务数据，最多递归 max_depth 层。

        如果提供 sub_business_name，则一直向下查找同名节点；
        如果未提供，则直接定位到最深一层 sub_business_data。
        返回 (data, is_container_mode)。
        """
        node = business_data
        for _ in range(max_depth):
            if sub_business_name:
                # 按名字找：当前节点就是目标就结束
                if node.get("sub_business_name") == sub_business_name:
                    return node.get("sub_business_data", {}), True
            # 继续往下走
            child = node.get("sub_business_data")
            if not child or not isinstance(child, dict):
                break
            node = child

        # 循环结束的处理
        if sub_business_name:
            # 给了名字但在深度限制内都没找到，返回原始数据
            return business_data, False
        else:
            # 没给名字，返回走到的最深层
            is_container_mode = node is not business_data
            return node, is_container_mode

    def save_and_respond_with_update(
        self,
        user_id,
        card_id: str,
        business_data: dict,
        new_card_dsl: dict,
        toast_message: str,
        toast_type: str,
    ):
        """负责保存数据并响应卡片更新。"""
        user_service = self.app_controller.get_service(
            ServiceNames.USER_BUSINESS_PERMISSION
        )
        user_service.save_new_card_business_data(user_id, card_id, business_data)

        return self.handle_card_operation_common(
            card_content=new_card_dsl,
            card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
            update_toast_type=toast_type,
            toast_message=toast_message,
        )

    def delete_and_respond_with_update(
        self,
        user_id,
        card_id: str,
        new_card_dsl: dict,
        toast_message: str,
        toast_type: str,
    ):
        """负责删除数据并响应卡片更新。"""
        user_service = self.app_controller.get_service(
            ServiceNames.USER_BUSINESS_PERMISSION
        )
        user_service.del_card_business_data(user_id, card_id)

        return self.handle_card_operation_common(
            card_content=new_card_dsl,
            card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
            update_toast_type=toast_type,
            toast_message=toast_message,
        )

    def get_category_color(self, category_name: str, categories_data: List) -> str:
        """
        获取分类的颜色信息

        Args:
            category_name: 分类名称
            categories_data: 分类数据列表（包含name和color的对象数组）

        Returns:
            str: 分类颜色，默认为ColorTypes.BLUE.value
        """
        match_color = ColorTypes.get_by_value(category_name).value
        if not categories_data:
            return match_color

        # 从分类数据中查找对应的颜色
        for category_obj in categories_data:
            if category_obj.get("name") == category_name:
                return category_obj.get("color", match_color)

        return match_color  # 默认颜色

    def print_json(self, mark: str, data: Dict[str, Any]):
        """打印json数据"""
        print(
            f"test-[{mark}]\n",
            json.dumps(json.dumps(data, ensure_ascii=False), ensure_ascii=False),
        )

    # region json卡片方法
    def build_base_card_structure(
        self,
        elements: List[Dict[str, Any]],
        header: Dict[str, Any],
        padding: str = "12px",
    ) -> Dict[str, Any]:
        """构建基础卡片结构"""
        return {
            "schema": "2.0",
            "config": {"update_multi": True, "wide_screen_mode": True},
            "body": {"direction": "vertical", "padding": padding, "elements": elements},
            "header": header,
        }

    def build_input_element(
        self,
        placeholder: str,
        initial_value: str,
        disabled: bool,
        action_data: Dict[str, Any],
        name: str = "",
        element_id: str = "",
        required: bool = False,
    ) -> Dict[str, Any]:
        """构建输入框元素"""
        final_element = {
            "tag": "input",
            "element_id": element_id,
            "placeholder": {"tag": "plain_text", "content": placeholder},
            "default_value": str(initial_value),
            "disabled": disabled,
            "name": name or element_id,
            "behaviors": [{"type": "callback", "value": action_data}],
        }
        if required:
            # 仅表单里可用用，表单外赋值会报错。
            final_element["required"] = True
        return final_element

    def build_card_header(
        self,
        title: str,
        subtitle: str = "",
        template: str = ColorTypes.BLUE.value,
        icon: str = "",
    ) -> Dict[str, Any]:
        """构建通用卡片头部"""
        header = {
            "title": {"tag": "plain_text", "content": title},
            "template": template,
        }

        if subtitle:
            header["subtitle"] = {"tag": "plain_text", "content": subtitle}

        if icon:
            header["icon"] = {"tag": "standard_icon", "token": icon}

        return header

    def build_status_based_header(
        self,
        base_title: str,
        is_confirmed: bool,
        result: str,
        confirmed_prefix: str = "",
    ) -> Dict[str, Any]:
        """构建基于状态的卡片头部 - 适用于确认类卡片"""
        if not is_confirmed:
            return self.build_card_header(
                base_title, "请确认记录信息", ColorTypes.BLUE.value, "edit_outlined"
            )

        if result == "确认":
            title = (
                f"{confirmed_prefix}{base_title}" if confirmed_prefix else base_title
            )
            return self.build_card_header(
                title, "记录信息已确认并保存", ColorTypes.GREEN.value, "done_outlined"
            )

        return self.build_card_header(
            "操作已取消", "", ColorTypes.GREY.value, "close_outlined"
        )

    # 辅助方法
    def build_form_row(
        self,
        label: str,
        element: Dict[str, Any],
        width_list: List[str] = None,
        element_id: str = "",
    ) -> Dict[str, Any]:
        """构建表单行"""

        if width_list is None:
            width_list = ["80px", "180px"]

        return {
            "tag": "column_set",
            "horizontal_align": "left",
            "element_id": element_id,
            "columns": [
                {
                    "tag": "column",
                    "width": width_list[0],
                    "elements": [
                        {
                            "tag": "markdown",
                            "content": f"**{label}**",
                            "text_align": "left",
                        }
                    ],
                    "vertical_align": "center",
                },
                {"tag": "column", "width": width_list[1], "elements": [element]},
            ],
        }

    def build_select_element(
        self,
        placeholder: str,
        options: List[Dict[str, Any]],
        initial_value: str,
        disabled: bool,
        action_data: Dict[str, Any],
        element_id: str = "",
        name: str = "",
    ) -> Dict[str, Any]:
        """构建选择器元素"""
        # 查找初始选择索引，对飞书来说，索引从1开始，所以需要+1
        initial_index = -1
        for i, option in enumerate(options):
            if option.get("value") == initial_value:
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
            "behaviors": [{"type": "callback", "value": action_data}],
        }

    def build_date_picker_element(
        self,
        placeholder: str,
        initial_date: str,
        disabled: bool,
        action_data: Dict[str, Any],
        name: str = "",
    ) -> Dict[str, Any]:
        """构建日期选择器元素"""
        element = {
            "tag": "picker_datetime",
            "placeholder": {"tag": "plain_text", "content": placeholder},
            "disabled": disabled,
            "behaviors": [{"type": "callback", "value": action_data}],
            "name": name,
        }

        if initial_date:
            element["initial_datetime"] = initial_date

        return element

    def build_checker_element(
        self,
        text: str,
        checked: bool,
        disabled: bool,
        action_data: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """构建复选框元素"""
        final_element = {
            "tag": "checker",
            "text": {"tag": "plain_text", "content": text},
            "checked": checked,
            "disabled": disabled,
        }
        if action_data:
            final_element["behaviors"] = [{"type": "callback", "value": action_data}]
        return final_element

    def build_multi_select_element(
        self,
        placeholder: str,
        options: List[Dict[str, Any]],
        initial_values: List[str],
        disabled: bool,
        action_data: Dict[str, Any],
        element_id: str = "",
        name: str = "",
    ) -> Dict[str, Any]:
        """构建多选选择器元素"""
        return {
            "tag": "multi_select_static",
            "element_id": element_id,
            "placeholder": {"tag": "plain_text", "content": placeholder},
            "options": options,
            "selected_values": initial_values,
            "width": "fill",
            "disabled": disabled,
            "name": name or element_id,
            "behaviors": [{"type": "callback", "value": action_data}],
        }

    def build_markdown_element(
        self,
        content: str,
        text_size: str = "normal",
    ) -> Dict[str, Any]:
        """构建markdown元素"""
        return {
            "tag": "markdown",
            "content": content,
            "text_size": text_size,
        }

    def build_line_element(
        self,
        margin: str = "6px 0px",
    ) -> Dict[str, Any]:
        """构建分割线元素"""
        return {
            "tag": "hr",
            "margin": margin,
        }

    def build_options(
        self,
        options_dict: Dict[str, Any],
    ) -> Dict[str, Any]:
        """构建选项元素 - 用于构建选择器元素的选项"""
        options = []
        for key, content in options_dict.items():
            options.append(
                {
                    "text": {"tag": "plain_text", "content": content},
                    "value": key,
                }
            )
        return options

    def build_button_element(
        self,
        text: str,
        action_data: Dict[str, Any] = None,
        disabled: bool = False,
        element_id: str = "",
        name: str = "",
        type: str = "default",
        size: str = "medium",
        icon: str = "",
        form_action_type: str = "",
    ) -> Dict[str, Any]:
        """构建按钮元素"""
        final_element = {
            "tag": "button",
            "text": {"tag": "plain_text", "content": text},
            "disabled": disabled,
            "type": type,
            "size": size,
        }
        if action_data:
            final_element["behaviors"] = [{"type": "callback", "value": action_data}]
        if name:
            final_element["name"] = name
        if element_id:
            final_element["element_id"] = element_id
        if icon:
            final_element["icon"] = {"tag": "standard_icon", "token": icon}
        if form_action_type:
            final_element["form_action_type"] = form_action_type
        return final_element

    def build_column_set_element(
        self,
        columns: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """构建列组元素"""
        return {"tag": "column_set", "columns": columns}

    def build_column_element(
        self,
        elements: List[Dict[str, Any]],
        width: str = "auto",
        vertical_align: str = "top",
        horizontal_align: str = "left",
    ) -> Dict[str, Any]:
        """构建列元素"""
        return {
            "tag": "column",
            "width": width,
            "vertical_align": vertical_align,
            "horizontal_align": horizontal_align,
            "elements": elements,
        }

    def build_button_group_element(
        self,
        buttons: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """构建按钮组元素"""
        columns = [self.build_column_element([button]) for button in buttons]
        return self.build_column_set_element(columns)

    def build_collapsible_panel_element(
        self,
        header_text: str,
        header_icon: str,
        icon_size: str = "16px 16px",
        expanded: bool = False,
        content: List[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """构建折叠面板元素"""
        if content is None:
            content = []

        return {
            "tag": "collapsible_panel",
            "expanded": expanded,
            "header": {
                "title": {"tag": "markdown", "content": header_text},
                "icon": {
                    "tag": "standard_icon",
                    "token": header_icon,
                    "color": "",
                    "size": icon_size,
                },
                "icon_position": "right",
                "icon_expanded_angle": -180,
            },
            "elements": content,
        }

    def build_form_element(
        self,
        elements: List[Dict[str, Any]],
        name: str = "",
    ) -> Dict[str, Any]:
        """构建表单元素"""
        return {"tag": "form", "elements": elements, "name": name}

    # endregion


# region 卡片注册表
class FeishuCardRegistry:
    """飞书卡片管理器注册表"""

    def __init__(self):
        self._managers: Dict[str, BaseCardManager] = {}

    def register_manager(self, card_type: str, manager: BaseCardManager):
        """注册卡片管理器"""
        # 这里的业务目标就是两个，一个是注册一个字典，可以重复，一个是输出日志。
        self._managers[card_type] = manager
        card_name = manager.get_card_name_by_config_key(card_type)
        single_instance = manager.single_instance
        if single_instance:
            debug_utils.log_and_print(
                f"✅ 单例卡片{manager.__class__.__name__}的{card_name}管理器复用注册成功",
                log_level="INFO",
            )
        else:
            debug_utils.log_and_print(
                f"✅ 注册{card_name}卡片管理器成功", log_level="INFO"
            )

    def get_manager(self, card_type: str) -> Optional[BaseCardManager]:
        """获取卡片管理器"""
        return self._managers.get(card_type)

    def get_all_managers(self) -> Dict[str, BaseCardManager]:
        """获取所有已注册的管理器"""
        return self._managers.copy()


# 全局注册表实例
card_registry = FeishuCardRegistry()
