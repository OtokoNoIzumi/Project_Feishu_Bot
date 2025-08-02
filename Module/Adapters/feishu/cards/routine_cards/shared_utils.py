# -*- coding: utf-8 -*-
"""
Shared Utilities for Routine Cards
共享工具方法
"""

from typing import Dict, Any
from Module.Business.processors.base_processor import MessageContext_Refactor
from Module.Services.constants import ToastTypes, CardOperationTypes, ColorTypes


class SharedUtils:
    """
    共享工具类，提供通用的卡片构建和处理方法
    """

    def __init__(self, parent_manager):
        self.parent = parent_manager  # 访问主管理器的共享方法和属性
        self.default_update_build_method = "update_query_results_card"

    def ensure_valid_context(self, context, method_name_str, default_method):
        """确保上下文有效，失效时自动处理"""
        business_data, card_id, _ = self.parent.get_core_data(context)
        if not business_data:
            new_card_dsl = self.parent.build_cancel_update_card_data(
                {}, method_name_str, default_method
            )
            return (
                None,
                None,
                self.parent.handle_card_operation_common(
                    card_content=new_card_dsl,
                    card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
                    update_toast_type=ToastTypes.ERROR,
                    toast_message="操作已失效",
                ),
            )
        return business_data, card_id, None

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
                f"📝 记录：{event_name}",
                "确认记录信息",
                ColorTypes.BLUE.value,
                "edit_outlined",
            )
        if workflow_state == "new_event_option":
            return self.parent.build_card_header(
                "🆕 新建事项",
                "事项不存在，是否新建？",
                ColorTypes.ORANGE.value,
                "add_outlined",
            )
        if is_confirmed:
            return self.parent.build_status_based_header("", is_confirmed, result)

        return self.parent.build_card_header(
            "🚀 快速记录", "输入或选择事项", ColorTypes.PURPLE.value
        )
