"""
基础卡片管理器

为所有feishu卡片管理器提供通用的基础接口和功能
"""

import json
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Callable
from functools import wraps
from lark_oapi.event.callback.model.p2_card_action_trigger import (
    P2CardActionTriggerResponse,
)
from Module.Common.scripts.common import debug_utils
from Module.Services.constants import (
    ServiceNames,
    CardOperationTypes,
    ReplyModes,
    ColorTypes,
    ToastTypes,
)
from Module.Business.processors import MessageContext_Refactor
from .json_builder import JsonBuilder

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

    @classmethod
    def card_updater(
        cls,
        sub_business_name: str = "",
        toast_message: str = "",
        default_update_method: str = None,
    ):
        """卡片更新装饰器 - 分离模板操作和业务逻辑

        Args:
            sub_business_name: 子业务名称，用于获取业务数据
            toast_message: 默认的提示消息
            default_update_method: 默认的更新构建方法名

        Returns:
            装饰器函数
        """

        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(card_instance, context: MessageContext_Refactor):
                # 装饰器是实际handler的入口，所以只有context

                manager = getattr(card_instance, "parent", card_instance)
                # 1. 获取构建方法名
                build_method_name = context.content.value.get(
                    "container_build_method",
                    default_update_method
                    or getattr(manager, "default_update_build_method", "update_card"),
                )

                # 2. 确保上下文有效
                business_data, card_id, error_response = manager.ensure_valid_context(
                    context, func.__name__, build_method_name
                )
                if error_response:
                    return error_response

                # 3. 获取业务数据源
                data_source, _ = manager.safe_get_business_data(
                    business_data, sub_business_name
                )

                # 4. 执行业务逻辑，返回可选的toast消息，这里传参到装饰器修正的方法里，也就多了一个data_source
                actual_toast = (
                    func(card_instance, context, data_source) or toast_message
                )

                # 5. 构建新的卡片DSL
                new_card_dsl = manager.build_update_card_data(
                    business_data, build_method_name
                )

                # 6. 保存并响应更新
                return manager.save_and_respond_with_update(
                    context.user_id,
                    card_id,
                    business_data,
                    new_card_dsl,
                    actual_toast,
                    ToastTypes.INFO,
                )

            return wrapper

        return decorator

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

    def count_tags_lightweight(self, node) -> int:
        """
        一个高性能、递归的函数，只用于计算嵌套字典/列表中 'tag' 键的总数。
        不处理任何字符串转换或HTML生成，追求最高效率。
        """
        count = 0
        # 使用栈（stack）来替代深度递归，避免在极深层级时爆栈，性能也更好
        stack = [node]

        while stack:
            current_node = stack.pop()

            if isinstance(current_node, dict):
                if "tag" in current_node:
                    count += 1
                # 将字典的值（可能是dict或list）压入栈中
                stack.extend(current_node.values())

            elif isinstance(current_node, list):
                # 将列表的元素压入栈中
                stack.extend(current_node)

        return count

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
        tag_total = self.count_tags_lightweight(card_content)
        if tag_total <= 200:
            debug_utils.log_and_print(f"tag计数器结果: {tag_total}", log_level="DEBUG")
        else:
            debug_utils.log_and_print(f"tag数量过多: {tag_total}", log_level="ERROR")

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
    def build_base_card_structure(self, *args, **kwargs):
        return JsonBuilder.build_base_card_structure(*args, **kwargs)

    def build_input_element(self, *args, **kwargs):
        return JsonBuilder.build_input_element(*args, **kwargs)

    def build_card_header(self, *args, **kwargs):
        return JsonBuilder.build_card_header(*args, **kwargs)

    def build_status_based_header(self, *args, **kwargs):
        return JsonBuilder.build_status_based_header(*args, **kwargs)

    def build_form_row(self, *args, **kwargs):
        return JsonBuilder.build_form_row(*args, **kwargs)

    def build_select_element(self, *args, **kwargs):
        return JsonBuilder.build_select_element(*args, **kwargs)

    def build_date_picker_element(self, *args, **kwargs):
        return JsonBuilder.build_date_picker_element(*args, **kwargs)

    def build_checker_element(self, *args, **kwargs):
        return JsonBuilder.build_checker_element(*args, **kwargs)

    def build_multi_select_element(self, *args, **kwargs):
        return JsonBuilder.build_multi_select_element(*args, **kwargs)

    def build_markdown_element(self, *args, **kwargs):
        return JsonBuilder.build_markdown_element(*args, **kwargs)

    def build_line_element(self, *args, **kwargs):
        return JsonBuilder.build_line_element(*args, **kwargs)

    def build_options(self, *args, **kwargs):
        return JsonBuilder.build_options(*args, **kwargs)

    def build_button_element(self, *args, **kwargs):
        return JsonBuilder.build_button_element(*args, **kwargs)

    def build_column_set_element(self, *args, **kwargs):
        return JsonBuilder.build_column_set_element(*args, **kwargs)

    def build_column_element(self, *args, **kwargs):
        return JsonBuilder.build_column_element(*args, **kwargs)

    def build_button_group_element(self, *args, **kwargs):
        return JsonBuilder.build_button_group_element(*args, **kwargs)

    def build_collapsible_panel_element(self, *args, **kwargs):
        return JsonBuilder.build_collapsible_panel_element(*args, **kwargs)

    def build_form_element(self, *args, **kwargs):
        return JsonBuilder.build_form_element(*args, **kwargs)

    def build_chart_element(self, *args, **kwargs):
        return JsonBuilder.build_chart_element(*args, **kwargs)

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
