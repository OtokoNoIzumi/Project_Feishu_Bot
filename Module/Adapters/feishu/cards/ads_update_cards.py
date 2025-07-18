"""
广告更新卡片管理器

专门处理B站广告时间戳更新确认相关的飞书卡片
"""

from typing import Dict, Any
from Module.Services.constants import ResponseTypes
from .card_registry import BaseCardManager
from ..decorators import card_build_safe


class AdsUpdateCardManager(BaseCardManager):
    """广告更新卡片管理器"""

    def get_interaction_components(self, operation_id: str, bvid: str, adtime_stamps: str) -> Dict[str, Any]:
        """获取广告更新确认卡片的交互组件"""

        # ✅ card_config_key是路由必需信息，必须注入
        base_action_value = {
            "card_config_key": self.card_config_key  # ✅ MessageProcessor路由需要
        }

        return {
            "confirm_action": {
                **base_action_value,
                "card_action": "confirm_ads_update",
                "process_result_type": ResponseTypes.ADMIN_CARD_UPDATE,
                "operation_id": operation_id,
                "bvid": bvid,
                "adtime_stamps": adtime_stamps
            },
            "cancel_action": {
                **base_action_value,
                "card_action": "cancel_ads_update",
                "process_result_type": ResponseTypes.ADMIN_CARD_UPDATE,
                "operation_id": operation_id
            },
            "adtime_editor": {
                **base_action_value,
                "card_action": "adtime_editor_change",
                "operation_id": operation_id,
                "target_field": "adtime_stamps",
                "current_value": adtime_stamps or ""
            }
        }

    @card_build_safe("广告时间戳修改确认卡片构建失败")
    def build_card(self, admin_confirm_action_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建广告时间戳修改确认卡片内容"""
        template_params = self._format_ads_update_params(admin_confirm_action_data)
        return self._build_template_content(template_params)

    @card_build_safe("格式化广告更新参数失败")
    def _format_ads_update_params(self, card_data: Dict[str, Any]) -> Dict[str, Any]:
        """将广告操作数据格式化为模板参数"""
        # 获取基本数据
        bvid = card_data.get('bvid', '')
        adtime_stamps = card_data.get('adtime_stamps', '')
        admin_input = card_data.get('admin_input', '')
        hold_time = card_data.get('hold_time', '(30s)')
        finished = card_data.get('finished', False)
        result = card_data.get('result', '')
        operation_id = card_data.get('operation_id', '')

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
