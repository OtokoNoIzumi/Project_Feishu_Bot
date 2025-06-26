"""
用户更新卡片管理器

专门处理管理员用户状态更新确认相关的飞书卡片
"""

from typing import Dict, Any, List
from Module.Services.constants import CardActions, ResponseTypes
from .card_registry import BaseCardManager
from ..decorators import card_build_safe


class UserUpdateCardManager(BaseCardManager):
    """用户更新卡片管理器"""

    def get_interaction_components(self, operation_id: str, user_id: str, user_type: int) -> Dict[str, Any]:
        """获取用户更新确认卡片的交互组件"""

        # ✅ card_config_key是路由必需信息，必须注入
        base_action_value = {
            "card_config_key": self.card_config_key  # ✅ MessageProcessor路由需要
        }

        return {
            "confirm_action": {
                **base_action_value,
                "card_action": "confirm_user_update",
                "process_result_type": ResponseTypes.ADMIN_CARD_UPDATE,
                "operation_id": operation_id,
                "user_id": user_id,
                "user_type": user_type
            },
            "cancel_action": {
                **base_action_value,
                "card_action": "cancel_user_update",
                "process_result_type": ResponseTypes.ADMIN_CARD_UPDATE,
                "operation_id": operation_id
            },
            "user_type_selector": {
                **base_action_value,
                "card_action": "update_user_type",
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
    def build_card(self, admin_confirm_action_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建用户状态修改确认卡片内容"""
        template_params = self._format_user_update_params(admin_confirm_action_data)
        return self._build_template_content(template_params)

    @card_build_safe("格式化用户更新参数失败")
    def _format_user_update_params(self, card_data: Dict[str, Any]) -> Dict[str, Any]:
        """将操作数据格式化为模板参数"""
        # 获取基本数据
        user_id = card_data.get('user_id', '')
        user_type = card_data.get('user_type', 1)
        admin_input = card_data.get('admin_input', '')
        hold_time = card_data.get('hold_time', '(30s)')
        finished = card_data.get('finished', False)
        result = card_data.get('result', '')
        operation_id = card_data.get('operation_id', '')

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
