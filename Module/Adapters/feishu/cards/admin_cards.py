"""
管理员相关卡片管理器

处理管理员操作确认、用户状态修改等功能的飞书卡片
版本：1.0.9 - 标准化交互组件架构
"""

from typing import Dict, Any
from .card_registry import BaseCardManager
from ..decorators import card_build_safe


class AdminCardInteractionComponents:
    """管理员卡片交互组件定义 - 业务层集中管理"""

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
                "action": "confirm_user_update",
                "operation_id": operation_id,
                "user_id": user_id,
                "user_type": user_type
            },

            # 取消按钮组件
            "cancel_action": {
                "action": "cancel_user_update",
                "operation_id": operation_id
            },

            # 用户类型选择器组件
            "user_type_selector": {
                "action": "select_change",
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
    def get_ads_update_confirm_components(operation_id: str, bvid: str, adtime_stamps: str) -> Dict[str, Any]:
        """
        获取广告更新确认卡片的交互组件

        Args:
            operation_id: 操作ID
            bvid: B站视频ID
            adtime_stamps: 广告时间戳

        Returns:
            Dict[str, Any]: 包含所有交互组件的定义
        """
        return {
            # 确认按钮组件
            "confirm_action": {
                "action": "confirm_ads_update",
                "operation_id": operation_id,
                "bvid": bvid,
                "adtime_stamps": adtime_stamps
            },

            # 取消按钮组件
            "cancel_action": {
                "action": "cancel_ads_update",
                "operation_id": operation_id
            },

            # 广告时间戳编辑器组件
            "adtime_editor": {
                "action": "adtime_editor_change",
                "operation_id": operation_id,
                "target_field": "adtime_stamps",  # 明确指定要更新的字段
                "current_value": adtime_stamps or ""  # 当前时间戳值
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
            "update_user": "get_user_update_confirm_components",
            "update_ads": "get_ads_update_confirm_components",
            # 未来扩展:
            # "system_config": "get_system_config_components"
        }


class AdminCardManager(BaseCardManager):
    """管理员卡片管理器"""

    def get_card_type_name(self) -> str:
        """获取卡片类型名称"""
        return "管理员"

    def _initialize_templates(self):
        """初始化管理员卡片模板配置"""
        self.templates = {
            "admin_user_update_confirm": {
                "template_id": "AAqdbwJ2cflOp",
                "template_version": "1.1.0"
            },
            "admin_ads_update_confirm": {
                "template_id": "AAqdJvEYwMDQ3",
                "template_version": "1.0.0"
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

    @card_build_safe("广告时间戳修改确认卡片构建失败")
    def build_ads_update_confirm_card(self, operation_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        构建广告时间戳修改确认卡片内容

        Args:
            operation_data: 操作数据，包含以下字段：
                - bvid: B站视频ID
                - adtime_stamps: 广告时间戳
                - admin_input: 管理员原始输入
                - hold_time: 倒计时文本
                - finished: 是否完成操作
                - result: 业务完成状态文本
                - operation_id: 操作ID（用于回调）

        Returns:
            Dict[str, Any]: 卡片内容
        """
        template_params = self._format_ads_update_params(operation_data)
        content = self._build_template_content("admin_ads_update_confirm", template_params)
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
        interaction_components = AdminCardInteractionComponents.get_user_update_confirm_components(
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

    @card_build_safe("格式化广告更新参数失败")
    def _format_ads_update_params(self, operation_data: Dict[str, Any]) -> Dict[str, Any]:
        """将广告操作数据格式化为模板参数"""

        # 获取基本数据
        bvid = operation_data.get('bvid', '')
        adtime_stamps = operation_data.get('adtime_stamps', '')
        admin_input = operation_data.get('admin_input', '')
        hold_time = operation_data.get('hold_time', '(30s)')
        finished = operation_data.get('finished', False)
        result = operation_data.get('result', '')
        operation_id = operation_data.get('operation_id', '')

        # 处理全角逗号转换 - 在显示时确保格式正确
        processed_adtime_stamps = adtime_stamps.replace('，', ',') if adtime_stamps else ''

        # 使用交互组件定义系统
        interaction_components = AdminCardInteractionComponents.get_ads_update_confirm_components(
            operation_id, bvid, processed_adtime_stamps
        )

        # 构建模板参数
        template_params = {
            "bvid": str(bvid),
            "adtime_str": processed_adtime_stamps,  # 使用处理后的时间戳
            "admin_input": admin_input,
            "hold_time": hold_time,
            "result": result,
            "finished": finished,

            # 1.0.0版本：标准化交互组件
            "confirm_action_data": interaction_components["confirm_action"],
            "cancel_action_data": interaction_components["cancel_action"],
            "ad_stamps_data": interaction_components["adtime_editor"],

            "extra_functions": []
        }

        return template_params

    @card_build_safe("更新卡片状态失败")
    def update_card_status(
        self, operation_data: Dict[str, Any], new_status: str, result_message: str = ""
    ) -> Dict[str, Any]:
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

