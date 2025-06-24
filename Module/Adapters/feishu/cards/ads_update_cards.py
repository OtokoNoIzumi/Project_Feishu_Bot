"""
广告更新卡片管理器

专门处理B站广告时间戳更新确认相关的飞书卡片
"""

from typing import Dict, Any, List
from Module.Services.constants import CardActions, OperationTypes, ResponseTypes
from .card_registry import BaseCardManager
from ..decorators import card_build_safe


class AdsUpdateCardManager(BaseCardManager):
    """广告更新卡片管理器"""

    def __init__(self, app_controller=None, card_info=None):
        self.app_controller = app_controller
        self.card_info = card_info
        self.card_name = card_info.get('card_name')
        self.card_config_key = card_info.get('card_config_key')
        super().__init__()

    def get_card_type_name(self) -> str:
        return self.card_name

    def get_supported_actions(self) -> List[str]:
        """获取该卡片支持的所有动作"""
        return [
            CardActions.CONFIRM_ADS_UPDATE,
            CardActions.CANCEL_ADS_UPDATE,
            CardActions.ADTIME_EDITOR_CHANGE
        ]

    def get_interaction_components(self, operation_id: str, bvid: str, adtime_stamps: str) -> Dict[str, Any]:
        """获取广告更新确认卡片的交互组件"""
        return {
            "confirm_action": {
                "action": CardActions.CONFIRM_ADS_UPDATE,
                "process_result_type": ResponseTypes.ADMIN_CARD_UPDATE,
                "operation_id": operation_id,
                "bvid": bvid,
                "adtime_stamps": adtime_stamps
            },
            "cancel_action": {
                "action": CardActions.CANCEL_ADS_UPDATE,
                "process_result_type": ResponseTypes.ADMIN_CARD_UPDATE,
                "operation_id": operation_id
            },
            "adtime_editor": {
                "action": CardActions.ADTIME_EDITOR_CHANGE,
                "operation_id": operation_id,
                "target_field": "adtime_stamps",
                "current_value": adtime_stamps or ""
            }
        }

    @card_build_safe("广告时间戳修改确认卡片构建失败")
    def build_card(self, operation_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建广告时间戳修改确认卡片内容"""
        template_params = self._format_ads_update_params(operation_data)
        return self._build_template_content(template_params)

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

        # 处理全角逗号转换
        processed_adtime_stamps = adtime_stamps.replace('，', ',') if adtime_stamps else ''

        # 获取交互组件
        interaction_components = self.get_interaction_components(
            operation_id, bvid, processed_adtime_stamps
        )

        return {
            "bvid": str(bvid),
            "adtime_str": processed_adtime_stamps,
            "admin_input": admin_input,
            "hold_time": hold_time,
            "result": result,
            "finished": finished,
            "confirm_action_data": interaction_components["confirm_action"],
            "cancel_action_data": interaction_components["cancel_action"],
            "ad_stamps_data": interaction_components["adtime_editor"],
            "extra_functions": []
        }
