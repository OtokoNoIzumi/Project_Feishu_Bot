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
from .record_card import RecordCard
from .direct_record_card import DirectRecordCard


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
        self.record_card = RecordCard(self)
        self.direct_record_card = DirectRecordCard(self)

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

    def update_card_field(
        self,
        context: MessageContext_Refactor,
        field_key: str,
        extracted_value,
        sub_business_name: str,
        toast_message: str,
    ):
        """代理到共享工具"""
        return self.shared_utils.update_card_field(
            context, field_key, extracted_value, sub_business_name, toast_message
        )

    def get_type_display_name(self, event_type: str) -> str:
        """获取事件类型显示名称"""
        return self.shared_utils.get_type_display_name(event_type)

    def ensure_valid_context(self, context, method_name, default_method):
        """确保上下文有效，失效时自动处理"""
        return self.shared_utils.ensure_valid_context(
            context, method_name, default_method
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
        method_name: str,
        default_method: str = "update_record_confirm_card",
        verbose: bool = True,
    ):
        """处理空数据情况，设置取消状态"""
        if verbose:
            debug_utils.log_and_print(
                f"🔍 {method_name} - 卡片数据为空", log_level="WARNING"
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

    def build_quick_record_confirm_card(
        self, result, context: MessageContext_Refactor, business_data: Dict[str, Any]
    ):
        """构建快速记录确认卡片 - 代理到子模块"""
        card_data = self.record_card.build_quick_record_confirm_card(business_data)
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

    def build_direct_record_card(
        self, result, context: MessageContext_Refactor, business_data: Dict[str, Any]
    ):
        """构建直接记录卡片 - 代理到子模块"""
        card_data = self.direct_record_card.build_direct_record_card(business_data)
        card_content = {"type": "card_json", "data": card_data}

        return self.handle_card_operation_common(
            card_content=card_content,
            card_operation_type=CardOperationTypes.SEND,
            update_toast_type="success",
            user_id=context.user_id,
            message_id=context.message_id,
            business_data=business_data,
            card_config_key=CardConfigKeys.ROUTINE_DIRECT_RECORD,
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
        return self.record_card.build_quick_record_confirm_card(business_data)

    def update_direct_record_card(
        self, business_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """构建直接记录确认卡片 - 代理到子模块"""
        return self.direct_record_card.build_direct_record_card(business_data)

    # ----- 配套的element子方法，会在build_card被sub_business_build_method方式调用 -----
    def build_direct_record_elements(
        self, business_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """构建直接记录元素（别名方法，兼容现有调用） - 代理到子模块"""
        return self.direct_record_card.build_direct_record_elements(business_data)

    def build_quick_record_elements(
        self, business_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """构建快速记录元素 - 代理到子模块"""
        return self.record_card.build_quick_record_elements(business_data)

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

    # ----- query_results_card 的回调事件代理 -----
    def update_category_filter(self, context: MessageContext_Refactor):
        """更新分类过滤器"""
        return self.query_results_card.update_category_filter(context)

    def update_type_name_filter(self, context: MessageContext_Refactor):
        """更新类型名称过滤器"""
        return self.query_results_card.update_type_name_filter(context)

    # ----- record_card 的回调事件代理 -----
    def update_record_degree(self, context: MessageContext_Refactor):
        """更新记录方式"""
        return self.record_card.update_record_degree(context)

    def confirm_record(self, context: MessageContext_Refactor):
        """确认记录"""
        return self.record_card.confirm_record(context)

    def cancel_record(self, context: MessageContext_Refactor):
        """取消记录"""
        return self.record_card.cancel_record(context)

    # ----- direct_record_card 的回调事件代理 -----
    def update_direct_record_type(self, context: MessageContext_Refactor):
        """更新直接记录事项类型"""
        return self.direct_record_card.update_direct_record_type(context)

    def update_progress_type(self, context: MessageContext_Refactor):
        """更新指标类型"""
        return self.direct_record_card.update_progress_type(context)

    def update_target_type(self, context: MessageContext_Refactor):
        """更新目标类型"""
        return self.direct_record_card.update_target_type(context)

    def update_reminder_mode(self, context: MessageContext_Refactor):
        """更新提醒模式"""
        return self.direct_record_card.update_reminder_mode(context)

    def update_check_cycle(self, context: MessageContext_Refactor):
        """更新检查周期"""
        return self.direct_record_card.update_check_cycle(context)

    def update_target_type(self, context: MessageContext_Refactor):
        """更新目标类型"""
        return self.direct_record_card.update_target_type(context)

    def cancel_direct_record(self, context: MessageContext_Refactor):
        """取消直接记录"""
        return self.direct_record_card.cancel_direct_record(context)

    # endregion

    # region 废弃的事件卡片
    def build_new_event_definition_card(self, route_result, context, business_data):
        """构建新事件定义卡片 - 转发到业务层处理"""
        card_data = self._build_new_event_definition_card(business_data)
        card_content = {"type": "card_json", "data": card_data}
        # 注意：新事件定义功能的具体实现在业务层
        # 这里只是保持接口兼容性的转发方法
        return self.handle_card_operation_common(
            card_content=card_content,
            card_operation_type=CardOperationTypes.SEND,
            update_toast_type="success",
            user_id=context.user_id,
            message_id=context.message_id,
            business_data=business_data,
        )

    def _build_new_event_definition_card(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """构建新事件定义卡片"""
        form_data = data.get("form_data", {})
        user_id = data.get("user_id", "")
        is_confirmed = data.get("is_confirmed", False)

        # 如果有初始事项名称，设置到form_data中
        initial_event_name = data.get("initial_event_name", "")
        if initial_event_name and not form_data.get("event_name"):
            form_data["event_name"] = initial_event_name

        # 获取当前选择的事件类型以控制字段显示
        selected_type = form_data.get("event_type", RoutineTypes.INSTANT)

        # 获取关联开始事项列表（如果当前类型是结束事项）
        related_start_items = []
        if selected_type == RoutineTypes.END and self.message_router:
            related_start_items = (
                self.message_router.routine_record.get_related_start_events(user_id)
            )

        header = self.build_card_header(
            "📝 新建日常事项", "请填写事项信息", "blue", "add-bold_outlined"
        )
        elements = self._build_new_event_form_elements(
            form_data,
            user_id,
            selected_type,
            is_confirmed,
            related_start_items,
        )

        return self.build_base_card_structure(elements, header, "16px")

    def _build_new_event_form_elements(
        self,
        form_data: Dict[str, Any],
        user_id: str,
        selected_type: str,
        is_confirmed: bool,
        related_start_items: List[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """构建新事件定义表单元素"""
        elements = []

        # 标题
        elements.append(
            {
                "tag": "markdown",
                "content": "**📝 请完善事项信息**",
                "text_align": "left",
                "text_size": "heading",
                "margin": "0px 0px 12px 0px",
            }
        )

        elements.append({"tag": "hr", "margin": "0px 0px 16px 0px"})

        # 1. 事项名称
        elements.append(
            self.build_form_row(
                "🏷️ 事项名称",
                self.build_input_element(
                    placeholder="输入事项名称",
                    initial_value=form_data.get("event_name", ""),
                    disabled=is_confirmed,
                    action_data={
                        "action": "update_event_name",
                    },
                    name="event_name",
                ),
            )
        )

        # 2. 事项类型
        elements.append(
            self.build_form_row(
                "⚡ 事项类型",
                self.build_select_element(
                    placeholder="选择事项类型",
                    options=self._get_event_type_options(),
                    initial_value=selected_type,
                    disabled=is_confirmed,
                    action_data={
                        "action": "update_event_type",
                    },
                    name="event_type",
                ),
            )
        )

        # 3. 所属分类
        elements.append(
            self.build_form_row(
                "📂 所属分类",
                self.build_select_element(
                    placeholder="选择分类",
                    options=[],
                    initial_value=form_data.get("category", ""),
                    disabled=is_confirmed,
                    action_data={
                        "action": "update_category",
                    },
                    name="category",
                ),
            )
        )

        # 4. 关联事项（仅结束事项显示）
        if selected_type == RoutineTypes.END:
            elements.append(
                self.build_form_row(
                    "🔗 关联开始事项",
                    self.build_select_element(
                        placeholder="选择关联的开始事项",
                        options=related_start_items or [],
                        initial_value=form_data.get("related_start_event", ""),
                        disabled=is_confirmed,
                        action_data={
                            "action": "update_related_start",
                        },
                        name="related_start_event",
                    ),
                )
            )

        # # 5. 日常检查设置（瞬间完成和长期持续显示）
        # if selected_type in [RoutineTypes.INSTANT, RoutineTypes.ONGOING]:
        #     elements.append(self.build_form_row(
        #         "📋 日常检查",
        #         self._build_checkbox_element(
        #             text="加入日常检查清单",
        #             checked=form_data.get('include_in_daily_check', False),
        #             disabled=is_confirmed,
        #             action_data={"action": "update_daily_check", "operation_id": operation_id}
        #         )
        #     ))

        # 6. 未来时间设置（仅未来事项显示）
        if selected_type == RoutineTypes.FUTURE:
            elements.append(
                self.build_form_row(
                    "⏰ 计划时间",
                    self._build_date_picker_element(
                        placeholder="选择计划执行日期",
                        initial_date=form_data.get("future_date", ""),
                        disabled=is_confirmed,
                        action_data={
                            "action": "update_future_date",
                        },
                    ),
                )
            )

        # 7. 程度选项（除未来事项外都显示）
        if selected_type != RoutineTypes.FUTURE:
            elements.append(
                self.build_form_row(
                    "📊 事项程度",
                    self.build_input_element(
                        placeholder="输入程度选项，用逗号分隔（如：简单,中等,复杂）",
                        initial_value=form_data.get("degree_options", ""),
                        disabled=is_confirmed,
                        action_data={
                            "action": "update_degree_options",
                        },
                        name="degree_options",
                    ),
                )
            )

        # 8. 备注信息
        elements.append(
            self.build_form_row(
                "📝 备注信息",
                self.build_input_element(
                    placeholder="添加备注信息（可选）",
                    initial_value=form_data.get("notes", ""),
                    disabled=is_confirmed,
                    action_data={
                        "action": "update_notes",
                    },
                    name="notes",
                ),
            )
        )

        # 分割线
        elements.append({"tag": "hr", "margin": "16px 0px 16px 0px"})

        # 操作按钮
        # if not is_confirmed:
        #     elements.append(self._build_action_buttons())

        return elements

    def _get_event_type_options(self) -> List[Dict[str, Any]]:
        """获取事件类型选项"""
        return [
            {
                "text": {"tag": "plain_text", "content": "⚡ 瞬间完成"},
                "value": RoutineTypes.INSTANT,
                "icon": {"tag": "standard_icon", "token": "lightning_outlined"},
            },
            {
                "text": {"tag": "plain_text", "content": "▶️ 开始事项"},
                "value": RoutineTypes.START,
                "icon": {"tag": "standard_icon", "token": "play_outlined"},
            },
            # {
            #     "text": {"tag": "plain_text", "content": "⏹️ 结束事项"},
            #     "value": RoutineTypes.END,
            #     "icon": {"tag": "standard_icon", "token": "stop_outlined"},
            # },
            {
                "text": {"tag": "plain_text", "content": "🔄 长期持续"},
                "value": RoutineTypes.ONGOING,
                "icon": {"tag": "standard_icon", "token": "refresh_outlined"},
            },
            {
                "text": {"tag": "plain_text", "content": "📅 未来事项"},
                "value": RoutineTypes.FUTURE,
                "icon": {"tag": "standard_icon", "token": "calendar_outlined"},
            },
        ]

    # endregion
