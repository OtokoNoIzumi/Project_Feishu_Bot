"""
用户更新卡片管理器

专门处理管理员用户状态更新确认相关的飞书卡片
"""

from typing import Dict, Any, List
from Module.Services.constants import CardActions, OperationTypes, ResponseTypes
from .card_registry import BaseCardManager
from ..decorators import card_build_safe


class UserUpdateCardManager(BaseCardManager):
    """用户更新卡片管理器"""

    def __init__(self, app_controller=None):
        self.app_controller = app_controller
        super().__init__()

    def get_card_type_name(self) -> str:
        return "用户更新"

    def get_supported_actions(self) -> List[str]:
        """获取该卡片支持的所有动作"""
        return [
            CardActions.CONFIRM_USER_UPDATE,
            CardActions.CANCEL_USER_UPDATE,
            CardActions.UPDATE_USER_TYPE
        ]

    def get_interaction_components(self, operation_id: str, user_id: str, user_type: int) -> Dict[str, Any]:
        """获取用户更新确认卡片的交互组件"""
        return {
            "confirm_action": {
                "action": CardActions.CONFIRM_USER_UPDATE,
                "process_result_type": ResponseTypes.ADMIN_CARD_UPDATE,
                "operation_id": operation_id,
                "user_id": user_id,
                "user_type": user_type
            },
            "cancel_action": {
                "action": CardActions.CANCEL_USER_UPDATE,
                "process_result_type": ResponseTypes.ADMIN_CARD_UPDATE,
                "operation_id": operation_id
            },
            "user_type_selector": {
                "action": CardActions.UPDATE_USER_TYPE,
                "operation_id": operation_id,
                "target_field": "user_type",
                "value_mapping": {
                    "0": 0,  # "普通用户" -> 0
                    "1": 1,  # "支持者" -> 1
                    "2": 2   # "受邀用户" -> 2
                },
                "current_value": str(user_type - 1)  # 当前选中值 (1-3 -> 0-2)
            }
        }

    @card_build_safe("用户状态修改确认卡片构建失败")
    def build_card(self, operation_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建用户状态修改确认卡片内容"""
        template_params = self._format_user_update_params(operation_data)
        return self._build_template_content(template_params)

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

        # 获取交互组件
        interaction_components = self.get_interaction_components(
            operation_id, user_id, user_type + 1
        )

        return {
            "user_id": str(user_id),
            "user_type": user_type + 1,
            "admin_input": admin_input,
            "hold_time": hold_time,
            "result": result,
            "finished": finished,
            "confirm_action_data": interaction_components["confirm_action"],
            "cancel_action_data": interaction_components["cancel_action"],
            "user_type_selector_data": interaction_components["user_type_selector"],
            "extra_functions": []
        }
