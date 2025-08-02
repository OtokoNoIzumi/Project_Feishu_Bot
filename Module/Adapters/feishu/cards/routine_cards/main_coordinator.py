# -*- coding: utf-8 -*-
"""
Main Coordinator
主协调器

来源：routine_cards.py RoutineCardManager类
"""
from typing import Dict, Any, List
from Module.Adapters.feishu.cards.card_registry import BaseCardManager
from Module.Business.processors.base_processor import (
    MessageContext_Refactor,
    RouteResult,
)
from Module.Services.constants import CardOperationTypes, CardConfigKeys, RoutineTypes
from Module.Common.scripts.common import debug_utils
from .shared_utils import SharedUtils
from .query_results_card import QueryResultsCard
from .quick_select_card import QuickSelectCard
from .record_card_old import RecordCard_Old
from .record_card import RecordCard


class RoutineCardManager(BaseCardManager):
    """
    例行事务卡片主协调器
    负责路由和协调各个子卡片模块
    """

    _instance = None

    def __new__(cls, *_args, **_kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        app_controller,
        card_static_config,
        card_config_key,
        sender,
        message_router,
        single_instance=False,
    ):
        """
        初始化主协调器
        """
        if not hasattr(self, "_initialized"):
            super().__init__(
                app_controller,
                card_static_config,
                card_config_key,
                sender,
                message_router,
                single_instance,
            )
            self._initialized = True

        if card_config_key and card_static_config:
            self._configs[card_config_key] = card_static_config

        # routine卡片不使用模板，而是直接生成完整的卡片DSL
        self.templates = {}

        # 初始化共享工具和子卡片管理器
        self.shared_utils = SharedUtils(self)
        self.query_results_card = QueryResultsCard(self)
        self.quick_select_card = QuickSelectCard(self)
        self.record_card_old = RecordCard_Old(self)
        self.record_card = RecordCard(self)

    def build_card(
        self, route_result: RouteResult, context: MessageContext_Refactor, **kwargs
    ) -> Dict[str, Any]:
        """
        主卡片构建方法 - 兼容路由，实际构建方法都是子卡片管理器的方法。
        """
        # 获取业务数据
        business_data = kwargs.get("business_data", {})
        card_type = kwargs.get("card_type", "")

        match card_type:
            case _:
                debug_utils.log_and_print(
                    f"未知的routine卡片类型: {card_type}", log_level="WARNING"
                )
                card_data = {}
        card_content = {"type": "card_json", "data": card_data}

        return self.handle_card_operation_common(
            card_content=card_content,
            card_operation_type=CardOperationTypes.SEND,
            update_toast_type="success",
            user_id=context.user_id,
            message_id=context.message_id,
            business_data=business_data,
        )

    # region 非基类的独有共享方法
    # 感觉不是迁移重点，甚至可以减少一个独立模块。
    def get_sub_business_build_method(self, card_config_key: str):
        """获取子卡片构建方法"""
        return self._configs.get(card_config_key, {}).get(
            "sub_business_build_method", ""
        )

    def build_workflow_header(
        self, workflow_state: str, event_name: str, is_confirmed: bool, result: str
    ) -> Dict[str, Any]:
        """代理到共享工具"""
        return self.shared_utils.build_workflow_header(
            workflow_state, event_name, is_confirmed, result
        )

    def ensure_valid_context(self, context, method_name_str, default_method):
        """确保上下文有效，失效时自动处理"""
        return self.shared_utils.ensure_valid_context(
            context, method_name_str, default_method
        )

    def build_update_card_data(
        self,
        business_data: Dict[str, Any],
        default_method: str = "update_record_confirm_card",
    ):
        """获取构建方法并执行"""
        build_method_name = business_data.get("container_build_method", default_method)
        if hasattr(self, build_method_name):
            return getattr(self, build_method_name)(business_data)

        return getattr(self, default_method)(business_data)

    def build_cancel_update_card_data(
        self,
        business_data: Dict[str, Any],
        method_name_str: str,
        default_method: str = "update_record_confirm_card",
        verbose: bool = True,
    ):
        """处理空数据情况，设置取消状态"""
        if verbose:
            debug_utils.log_and_print(
                f"🔍 {method_name_str} - 卡片数据为空", log_level="WARNING"
            )
        business_data["is_confirmed"] = True
        business_data["result"] = "取消"
        return self.build_update_card_data(business_data, default_method)

    # endregion

    # region 卡片构建方法代理
    # 由dispatch_card_response调用，1级方法。
    def build_quick_select_record_card(
        self, result, context: MessageContext_Refactor, business_data: Dict[str, Any]
    ):
        """构建快速选择记录卡片 - 代理到子模块"""
        card_data = self.quick_select_card.build_quick_select_record_card(business_data)
        card_content = {"type": "card_json", "data": card_data}

        return self.handle_card_operation_common(
            card_content=card_content,
            card_operation_type=CardOperationTypes.SEND,
            update_toast_type="success",
            user_id=context.user_id,
            message_id=context.message_id,
            business_data=business_data,
            card_config_key=CardConfigKeys.ROUTINE_QUICK_SELECT,
        )

    def build_query_results_card(
        self, result, context: MessageContext_Refactor, business_data: Dict[str, Any]
    ):
        """构建查询结果卡片 - 代理到子模块"""
        card_data = self.query_results_card.build_query_results_card(business_data)
        card_content = {"type": "card_json", "data": card_data}

        return self.handle_card_operation_common(
            card_content=card_content,
            card_operation_type=CardOperationTypes.SEND,
            update_toast_type="success",
            user_id=context.user_id,
            message_id=context.message_id,
            business_data=business_data,
            card_config_key=CardConfigKeys.ROUTINE_QUERY,
        )

    # def build_quick_record_confirm_card(
    #     self, result, context: MessageContext_Refactor, business_data: Dict[str, Any]
    # ):
    #     """构建快速记录确认卡片 - 代理到子模块"""
    #     card_data = self.record_card_old.build_quick_record_confirm_card(business_data)
    #     card_content = {"type": "card_json", "data": card_data}

    #     return self.handle_card_operation_common(
    #         card_content=card_content,
    #         card_operation_type=CardOperationTypes.SEND,
    #         update_toast_type="success",
    #         user_id=context.user_id,
    #         message_id=context.message_id,
    #         business_data=business_data,
    #         card_config_key=CardConfigKeys.ROUTINE_RECORD_OLD,
    #     )

    def build_record_card(
        self, result, context: MessageContext_Refactor, business_data: Dict[str, Any]
    ):
        """构建直接记录卡片 - 代理到子模块"""
        card_data = self.record_card.build_record_card(business_data)
        card_content = {"type": "card_json", "data": card_data}

        return self.handle_card_operation_common(
            card_content=card_content,
            card_operation_type=CardOperationTypes.SEND,
            update_toast_type="success",
            user_id=context.user_id,
            message_id=context.message_id,
            business_data=business_data,
            card_config_key=CardConfigKeys.ROUTINE_RECORD,
        )

    # 嵌套的两个关键方法段落，容器的card和嵌套的element
    # ----- 配套的card子方法，会被card_action里包含的的container_build_method方式调用 -----
    def update_quick_select_record_card(
        self, business_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """构建快速选择记录卡片 - 代理到子模块"""
        return self.quick_select_card.build_quick_select_record_card(business_data)

    def update_query_results_card(
        self, business_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """构建查询结果卡片 - 代理到子模块"""
        return self.query_results_card.build_query_results_card(business_data)

    def update_record_confirm_card(
        self, business_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """构建快速记录确认卡片 - 代理到子模块"""
        return self.record_card_old.build_quick_record_confirm_card(business_data)

    def update_record_card(self, business_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建直接记录确认卡片 - 代理到子模块"""
        return self.record_card.build_record_card(business_data)

    # ----- 配套的element子方法，会在build_card被sub_business_build_method方式调用 -----
    def build_record_elements(
        self, business_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """构建直接记录元素（别名方法，兼容现有调用） - 代理到子模块"""
        return self.record_card.build_record_elements(business_data)

    def build_quick_record_elements(
        self, business_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """构建快速记录元素 - 代理到子模块"""
        return self.record_card_old.build_quick_record_elements(business_data)

    def build_query_elements(
        self, business_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """构建查询元素 - 代理到子模块"""
        return self.query_results_card.build_query_elements(business_data)

    # endregion

    # region 卡片回调事件代理
    # 由 handle_feishu_card 里的分支逻辑调用，1级方法，有一个handle_card_action的向后兼容逻辑，但这里不这么用。

    # ----- quick_select_card 的回调事件代理 -----
    def quick_record_select(self, context: MessageContext_Refactor):
        """处理快速事件选择"""
        return self.quick_select_card.quick_record_select(context)

    def select_record_by_input(self, context: MessageContext_Refactor):
        """处理输入选择记录"""
        return self.quick_select_card.select_record_by_input(context)

    def show_query_info(self, context: MessageContext_Refactor):
        """显示查询信息"""
        return self.quick_select_card.show_query_info(context)

    def toggle_continuous_record(self, context: MessageContext_Refactor):
        """切换连续记录状态"""
        return self.quick_select_card.toggle_continuous_record(context)

    def complete_active_record(self, context: MessageContext_Refactor):
        """完成active_record"""
        return self.quick_select_card.complete_active_record(context)

    def calculate_yesterday_color(self, context: MessageContext_Refactor):
        """计算昨天的颜色"""
        return self.quick_select_card.calculate_yesterday_color(context)

    def calculate_today_color(self, context: MessageContext_Refactor):
        """计算今天的颜色"""
        return self.quick_select_card.calculate_today_color(context)

    # ----- query_results_card 的回调事件代理 -----
    def update_category_filter(self, context: MessageContext_Refactor):
        """更新分类过滤器"""
        return self.query_results_card.update_category_filter(context)

    def update_type_name_filter(self, context: MessageContext_Refactor):
        """更新类型名称过滤器"""
        return self.query_results_card.update_type_name_filter(context)

    def query_record(self, context: MessageContext_Refactor):
        """统一的记录操作入口 - 代理到query_results_card"""
        return self.query_results_card.query_record(context)

    # ----- record_card 的回调事件代理 -----
    def handle_record_field_update(self, context: MessageContext_Refactor):
        """更新直接记录事项类型"""
        return self.record_card.handle_record_field_update(context)

    def cancel_record(self, context: MessageContext_Refactor):
        """取消记录"""
        return self.record_card.cancel_record(context)

    def confirm_record(self, context: MessageContext_Refactor):
        """确认记录"""
        return self.record_card.confirm_record(context)

    # ----- record_card_old 的回调事件代理 -----
    def confirm_record_old(self, context: MessageContext_Refactor):
        """确认记录-旧"""
        return self.record_card_old.confirm_record_old(context)

    def cancel_record_old(self, context: MessageContext_Refactor):
        """取消记录-旧"""
        return self.record_card_old.cancel_record_old(context)

    # endregion
