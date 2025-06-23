"""
用户更新卡片管理器

专门处理管理员用户状态更新确认相关的飞书卡片
版本：1.0.9 - 标准化交互组件架构 + 配置驱动
"""

from typing import Dict, Any
from Module.Services.constants import CardActions, OperationTypes, ResponseTypes, ServiceNames, CardConfigTypes
from .card_registry import BaseCardManager
from ..decorators import card_build_safe


class UserUpdateInteractionComponents:
    """用户更新卡片交互组件定义 - 业务层集中管理"""

    @staticmethod
    def get_user_update_confirm_components(operation_id: str, user_id: str, user_type: int) -> Dict[str, Any]:
        """
        获取用户更新确认卡片的交互组件

        Args:
            operation_id: 操作ID
            user_id: 用户ID
            user_type: 当前用户类型

        Returns:
            Dict[str, Any]: 包含所有交互组件的定义
        """
        return {
            # 确认按钮组件
            "confirm_action": {
                "action": CardActions.CONFIRM_USER_UPDATE,
                "process_result_type": ResponseTypes.ADMIN_CARD_UPDATE,
                "operation_id": operation_id,
                "user_id": user_id,
                "user_type": user_type
            },

            # 取消按钮组件
            "cancel_action": {
                "action": CardActions.CANCEL_USER_UPDATE,
                "process_result_type": ResponseTypes.ADMIN_CARD_UPDATE,
                "operation_id": operation_id
            },

            # 用户类型选择器组件
            "user_type_selector": {
                "action": CardActions.UPDATE_USER_TYPE,
                "operation_id": operation_id,
                "target_field": "user_type",  # 明确指定要更新的字段
                "value_mapping": {
                    "0": 0,  # "普通用户" -> 0
                    "1": 1,  # "支持者" -> 1
                    "2": 2   # "受邀用户" -> 2
                },
                "current_value": str(user_type - 1)  # 当前选中值 (1-3 -> 0-2)
            }
        }

    @staticmethod
    def get_operation_type_mapping() -> Dict[str, str]:
        """
        获取操作类型映射 - 用于识别不同业务的交互组件

        Returns:
            Dict[str, str]: operation_type -> component_getter_method
        """
        return {
            OperationTypes.UPDATE_USER: "get_user_update_confirm_components"
        }


class UserUpdateCardManager(BaseCardManager):
    """用户更新卡片管理器 - 配置驱动"""

    def __init__(self, app_controller=None):
        """
        初始化用户更新卡片管理器

        Args:
            app_controller: 配置服务实例，用于读取卡片配置
        """
        self.app_controller = app_controller
        super().__init__()

    def get_card_type_name(self) -> str:
        """获取卡片类型名称"""
        return "用户更新"

    def _initialize_templates(self):
        """初始化用户更新卡片模板配置 - 从配置文件读取"""
        self.templates = {}

        if not self.app_controller:
            # 如果没有配置服务，使用默认配置（向后兼容）
            self.templates = {
                "admin_user_update_confirm": {
                    "template_id": "AAqdbwJ2cflOp",
                    "template_version": "1.1.0"
                }
            }
            return

        # 从配置服务获取卡片业务映射服务
        card_mapping_service = self.app_controller.get_service(ServiceNames.CARD_BUSINESS_MAPPING)
        if not card_mapping_service:
            return

        # 获取用户更新管理器的配置
        card_definition = card_mapping_service.get_card_definition(CardConfigTypes.USER_UPDATE)
        if card_definition and "templates" in card_definition:
            self.templates = card_definition["templates"]

    # 卡片构建方法组
    @card_build_safe("用户状态修改确认卡片构建失败")
    def build_user_update_confirm_card(self, operation_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        构建用户状态修改确认卡片内容

        Args:
            operation_data: 操作数据，包含以下字段：
                - user_id: 用户ID
                - user_type: 用户类型 (1-3)
                - admin_input: 管理员原始输入
                - hold_time: 倒计时文本
                - finished: 是否完成操作
                - result: 业务完成状态文本
                - operation_id: 操作ID（用于回调）

        Returns:
            Dict[str, Any]: 卡片内容
        """
        template_params = self._format_user_update_params(operation_data)
        content = self._build_template_content("admin_user_update_confirm", template_params)
        return content

    # 参数格式化方法组
    @card_build_safe("格式化用户更新参数失败")
    def _format_user_update_params(self, operation_data: Dict[str, Any]) -> Dict[str, Any]:
        """将操作数据格式化为模板参数"""

        # 获取基本数据
        user_id = operation_data.get('user_id', '')
        user_type = operation_data.get('user_type', 1)
        admin_input = operation_data.get('admin_input', '')
        hold_time = operation_data.get('hold_time', '(30s)')
        finished = operation_data.get('finished', False)
        result = operation_data.get('result', '')
        operation_id = operation_data.get('operation_id', '')

        # 使用交互组件定义系统
        interaction_components = UserUpdateInteractionComponents.get_user_update_confirm_components(
            operation_id, user_id, user_type + 1
        )

        # 构建模板参数
        template_params = {
            "user_id": str(user_id),
            "user_type": user_type + 1,
            "admin_input": admin_input,
            "hold_time": hold_time,
            "result": result,
            "finished": finished,

            # 1.0.9版本：标准化交互组件
            "confirm_action_data": interaction_components["confirm_action"],
            "cancel_action_data": interaction_components["cancel_action"],
            "user_type_selector_data": interaction_components["user_type_selector"],

            "extra_functions": []
        }

        return template_params
