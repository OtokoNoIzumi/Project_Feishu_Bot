# -*- coding: utf-8 -*-
"""
Shared Utilities for Routine Cards
共享工具方法
"""

from typing import Dict, Any
from Module.Business.processors.base_processor import MessageContext_Refactor
from Module.Common.scripts.common import debug_utils
from Module.Services.constants import ToastTypes, RoutineTypes


class SharedUtils:
    """
    共享工具类，提供通用的卡片构建和处理方法
    """

    def __init__(self, parent_manager):
        self.parent = parent_manager  # 访问主管理器的共享方法和属性

    def update_card_field(
        self,
        context: MessageContext_Refactor,
        field_key: str,
        extracted_value,
        sub_business_name: str = "",
        toast_message: str = "",
    ):
        """routine业务专用的字段更新和刷新模板"""
        business_data, card_id, _ = self.parent.get_core_data(context)
        if not business_data:
            debug_utils.log_and_print(
                f"🔍 {field_key} - 卡片业务数据为空", log_level="WARNING"
            )
            return

        data_source, _ = self.parent.safe_get_business_data(
            business_data, sub_business_name
        )
        data_source[field_key] = extracted_value

        # 获取构建方法
        build_method_name = business_data.get(
            "container_build_method", "update_query_results_card"
        )

        new_card_dsl = self.parent.build_update_card_data(
            business_data, build_method_name
        )

        return self.parent.save_and_respond_with_update(
            context.user_id,
            card_id,
            business_data,
            new_card_dsl,
            toast_message,
            ToastTypes.INFO,
        )

    def build_workflow_header(
        self,
        workflow_state: str,
        event_name: str,
        is_confirmed: bool = False,
        result: str = "取消",
    ) -> Dict[str, Any]:
        """构建工作流程卡片头部"""
        if workflow_state == "quick_record" and event_name:
            return self.parent.build_card_header(
                f"📝 记录：{event_name}", "确认记录信息", "blue", "edit_outlined"
            )
        if workflow_state == "new_event_option":
            return self.parent.build_card_header(
                "🆕 新建事项", "事项不存在，是否新建？", "orange", "add_outlined"
            )
        if is_confirmed:
            return self.parent.build_status_based_header("", is_confirmed, result)

        return self.parent.build_card_header("🚀 快速记录", "输入或选择事项", "purple")

    def get_type_display_name(self, event_type: str) -> str:
        """获取事件类型显示名称"""
        type_names = {
            RoutineTypes.INSTANT: "⚡ 瞬间完成",
            RoutineTypes.START: "▶️ 开始事项",
            RoutineTypes.END: "⏹️ 结束事项",
            RoutineTypes.ONGOING: "🔄 长期持续",
            RoutineTypes.FUTURE: "📅 未来事项",
        }
        return type_names.get(event_type, "📝 未知类型")
