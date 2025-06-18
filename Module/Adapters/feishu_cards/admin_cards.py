"""
管理员相关卡片管理器

处理管理员操作确认、用户状态修改等功能的飞书卡片
"""

from typing import Dict, Any, Optional
from Module.Common.scripts.common import debug_utils
from .base_card_manager import BaseCardManager
from ..feishu_decorators import card_build_safe


class AdminCardManager(BaseCardManager):
    """管理员卡片管理器"""

    def __init__(self):
        """初始化管理员卡片管理器"""
        super().__init__()

    def get_card_type_name(self) -> str:
        """获取卡片类型名称"""
        return "管理员"

    def _initialize_templates(self):
        """初始化管理员卡片模板配置"""
        self.templates = {
            "admin_user_update_confirm": {
                "template_id": "AAqdbwJ2cflOp",
                "template_version": "1.0.4"
            }
        }

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

        # 用户类型映射 (1-3 对应 普通用户-受邀用户)
        user_type_map = {
            1: "普通用户",
            2: "支持者",
            3: "受邀用户"
        }
        user_type_display = user_type_map.get(user_type, "未知类型")
        user_type_str = str(user_type)

        # # 构建确认操作的action数据
        # confirm_action_data = {
        #     "action": "confirm_user_update",
        #     "operation_id": operation_id,
        #     "user_id": user_id,
        #     "user_type": user_type
        # }

        # # 构建取消操作的action数据
        # cancel_action_data = {
        #     "action": "cancel_user_update",
        #     "operation_id": operation_id
        # }
        # 操作已完成，显示结果
        template_params = {
            "user_id": str(user_id),
            "user_type": user_type,
            "user_type_str": user_type_str,
            "admin_input": admin_input,
            "hold_time": hold_time,
            "result": result,
            "finished": finished,
            "operation_id": operation_id
        }


        return template_params

    @card_build_safe("更新卡片状态失败")
    def update_card_status(self, operation_data: Dict[str, Any], new_status: str, result_message: str = "") -> Dict[str, Any]:
        """
        更新卡片状态（用于操作完成后的卡片更新，测试数据，待删除）

        Args:
            operation_data: 原操作数据
            new_status: 新状态 ('confirmed', 'cancelled', 'expired')
            result_message: 结果消息

        Returns:
            Dict[str, Any]: 更新后的卡片内容
        """
        # 根据状态生成结果文本
        status_messages = {
            'confirmed': f"✅ 操作已确认并执行\n{result_message}",
            'cancelled': "❌ 操作已取消",
            'expired': "⏰ 操作已过期，自动执行默认操作"
        }

        result_text = status_messages.get(new_status, result_message)

        # 更新操作数据
        updated_data = operation_data.copy()
        updated_data.update({
            'finished': True,
            'result': result_text
        })

        return self.build_user_update_confirm_card(updated_data)

    # 回调处理方法组
    @card_build_safe("处理卡片回调失败")
    def handle_card_callback(self, action_data: Dict[str, Any], form_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        处理卡片回调

        Args:
            action_data: 动作数据
            form_data: 表单数据（可选）

        Returns:
            Dict[str, Any]: 处理结果
        """
        action = action_data.get('action', '')
        operation_id = action_data.get('operation_id', '')

        if not operation_id:
            return {"success": False, "message": "缺少操作ID"}

        if action == "confirm_user_update":
            return self._handle_confirm_action(action_data, form_data)
        elif action == "cancel_user_update":
            return self._handle_cancel_action(action_data)
        elif action == "update_user_type":
            return self._handle_user_type_update(action_data, form_data)
        else:
            return {"success": False, "message": f"未知操作: {action}"}

    def _handle_confirm_action(self, action_data: Dict[str, Any], form_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """处理确认操作"""
        # 这里返回需要传递给业务层的数据
        result = {
            "success": True,
            "action": "confirm",
            "operation_id": action_data.get('operation_id'),
            "user_id": action_data.get('user_id'),
            "user_type": action_data.get('user_type')
        }

        # 如果有表单数据，优先使用表单数据
        if form_data:
            if 'user_id_input' in form_data:
                result['user_id'] = form_data['user_id_input']
            if 'user_type_select' in form_data:
                result['user_type'] = int(form_data['user_type_select'])

        return result

    def _handle_cancel_action(self, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理取消操作"""
        return {
            "success": True,
            "action": "cancel",
            "operation_id": action_data.get('operation_id')
        }

    def _handle_user_type_update(self, action_data: Dict[str, Any], form_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """处理用户类型更新（用于选择器变更）"""
        new_user_type = action_data.get('selected_value')
        if form_data and 'user_type_select' in form_data:
            new_user_type = form_data['user_type_select']

        return {
            "success": True,
            "action": "update_data",
            "operation_id": action_data.get('operation_id'),
            "new_data": {
                "user_type": int(new_user_type) if new_user_type else 1
            }
        }

    # 实用方法
    def create_toast_response(self, message: str, toast_type: str = "success") -> Dict[str, Any]:
        """
        创建Toast响应

        Args:
            message: 提示消息
            toast_type: 提示类型 ('success', 'error', 'warning', 'info')

        Returns:
            Dict[str, Any]: Toast响应数据
        """
        return {
            "toast": {
                "type": toast_type,
                "content": message
            }
        }

    def create_card_update_response(self, card_content: Dict[str, Any], toast_message: str = "") -> Dict[str, Any]:
        """
        创建卡片更新响应

        Args:
            card_content: 新的卡片内容
            toast_message: Toast消息（可选）

        Returns:
            Dict[str, Any]: 卡片更新响应数据
        """
        response = {
            "card": {
                "type": "raw",
                "data": card_content
            }
        }

        if toast_message:
            response["toast"] = {
                "type": "success",
                "content": toast_message
            }

        return response