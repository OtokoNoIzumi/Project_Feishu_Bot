# -*- coding: utf-8 -*-
"""
Quick Select Card
快速选择卡片

来源：routine_cards.py RoutineCardManager类
迁移的方法：
- _build_quick_select_record_card (行号:196-263)
- quick_record_select (行号:1083-1157)
- select_record_by_input (行号:1159-1228)
- show_query_info (行号:1230-1310) - 需要修改business_data获取方式
"""

from typing import Dict, Any
from Module.Business.processors.base_processor import (
    MessageContext_Refactor,
    ProcessResult,
)
from Module.Services.constants import (
    CardConfigKeys,
    CardOperationTypes,
    ToastTypes,
    RoutineTypes,
)


class QuickSelectCard:
    """
    快速选择卡片管理器
    """

    def __init__(self, parent_manager):
        self.parent = parent_manager  # 访问主管理器的共享方法和属性

    def _build_quick_select_record_card(
        self, business_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        快速选择记录卡片核心构建逻辑
        """
        # 1级入口，不需要嵌套，但其实也可以来一个？嵌套应该是通用能力？等第4个做的时候再改吧。
        event_name = business_data.get("selected_event_name", "")
        is_confirmed = business_data.get("is_confirmed", False)
        result = business_data.get("result", "取消")
        quick_events = business_data.get("quick_events", [])

        # 提取集成模式相关数据，和后台业务无关的初始数据在这里初始化
        workflow_state = business_data.get("workflow_state", "initial")
        input_text = business_data.get("input_text", "")

        header = self.parent._build_workflow_header(
            workflow_state, event_name, is_confirmed, result
        )
        elements = []

        elements.append(
            self.parent._build_form_row(
                "✏️ 事项",
                self.parent._build_input_element(
                    placeholder="输入事项名称...",
                    initial_value=input_text,
                    disabled=is_confirmed,
                    action_data={
                        "card_action": "select_record_by_input",
                        "card_config_key": CardConfigKeys.ROUTINE_QUICK_SELECT,
                    },
                    element_id="new_event_name",
                    name="new_event_name",
                ),
                width_list=["80px", "180px"],
            )
        )

        elements.append(
            self.parent._build_form_row(
                "快捷添加",
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "查询日程"},
                    "type": "primary",
                    "width": "default",
                    "size": "medium",
                    "disabled": is_confirmed,
                    "behaviors": [
                        {
                            "type": "callback",
                            "value": {
                                "card_action": "show_query_info",
                                "card_config_key": CardConfigKeys.ROUTINE_QUICK_SELECT,
                            },
                        }
                    ],
                },
                width_list=["80px", "180px"],
            )
        )

        for event in quick_events:
            event_name_btn = event.get("name", "")
            event_type = event.get("type", RoutineTypes.INSTANT)
            type_emoji = {
                "instant": "⚡",
                "start": "▶️",
                "end": "⏹️",
                "ongoing": "🔄",
                "future": "📅",
            }.get(event_type, "📝")
            is_quick_access = event.get("properties", {}).get("quick_access", False)

            elements.append(
                {
                    "tag": "button",
                    "text": {
                        "tag": "plain_text",
                        "content": f"{type_emoji} {event_name_btn}",
                    },
                    "type": "primary" if is_quick_access else "default",
                    "width": "fill",
                    "size": "medium",
                    "disabled": is_confirmed,
                    "behaviors": [
                        {
                            "type": "callback",
                            "value": {
                                "card_action": "quick_record_select",
                                "card_config_key": CardConfigKeys.ROUTINE_QUICK_SELECT,
                                "event_name": event_name_btn,
                                "container_build_method": "_build_quick_select_record_card",
                            },
                        }
                    ],
                }
            )

        # 集成模式：根据工作流程状态显示不同内容
        sub_business_build_method = business_data.get("sub_business_build_method", "")
        if sub_business_build_method and hasattr(
            self.parent, sub_business_build_method
        ):
            sub_elements = getattr(self.parent, sub_business_build_method)(
                business_data
            )

            elements.append({"tag": "hr", "margin": "6px 0px"})
            elements.extend(sub_elements)

        return self.parent._build_base_card_structure(elements, header, "12px")

    def quick_record_select(self, context: MessageContext_Refactor):
        """
        快速记录选择处理
        """
        action_value = context.content.value
        user_id = context.user_id
        parent_business_name = action_value.get(
            "card_config_key", CardConfigKeys.ROUTINE_QUICK_SELECT
        )
        event_name = action_value.get("event_name", "")
        container_build_method = action_value.get(
            "container_build_method", "_build_quick_select_record_card"
        )

        # 获取当前卡片的业务数据
        business_data, card_id, _ = self.parent._get_core_data(context)
        if not business_data:
            new_card_dsl = self.parent._routine_handle_empty_data_with_cancel(
                business_data or {},
                method_name="quick_record_select",
                default_method=container_build_method,
            )
            return self.parent._handle_card_operation_common(
                card_content=new_card_dsl,
                card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
                update_toast_type=ToastTypes.ERROR,
                toast_message="操作已失效",
            )

        # 加载事件定义
        routine_business = self.parent.message_router.routine_record
        definitions_data = routine_business.load_event_definitions(user_id)
        if (
            definitions_data and event_name in definitions_data["definitions"]
        ):  # 虽然是冗余但先保留吧
            event_def = definitions_data["definitions"][event_name]
            last_record_time = definitions_data.get("last_record_time", None)
            quick_record_data = routine_business.build_quick_record_data(
                user_id, event_name, event_def, last_record_time
            )

            business_data["workflow_state"] = (
                "quick_record"  # 集成模式状态，这个姑且先保留吧，稍微冗余一点点
            )
            business_data["container_build_method"] = container_build_method

            parent_data, _ = self.parent._safe_get_business_data(
                business_data, parent_business_name
            )

            parent_data["sub_business_data"] = quick_record_data
            parent_data["sub_business_name"] = CardConfigKeys.ROUTINE_RECORD
            sub_business_build_method = self.parent.get_sub_business_build_method(
                CardConfigKeys.ROUTINE_RECORD
            )
            parent_data["sub_business_build_method"] = sub_business_build_method

            # 更新卡片显示
            new_card_dsl = self.parent._routine_get_build_method_and_execute(
                business_data, container_build_method
            )
            return self.parent._save_and_respond_with_update(
                context.user_id,
                card_id,
                business_data,
                new_card_dsl,
                f"开始记录 [{event_name}]",
                ToastTypes.SUCCESS,
            )

        # 如果事件不存在，保持在选择模式
        business_data["selected_event_name"] = event_name

        new_card_dsl = self._build_quick_select_record_card(business_data)
        return self.parent._handle_card_operation_common(
            card_content=new_card_dsl,
            card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
            update_toast_type=ToastTypes.INFO,
            toast_message=f"输入了新事项 '{event_name}'",
        )

    def select_record_by_input(self, context: MessageContext_Refactor) -> ProcessResult:
        """
        输入选择记录处理
        """
        action_value = context.content.value
        user_id = context.user_id
        parent_business_name = action_value.get(
            "card_config_key", CardConfigKeys.ROUTINE_QUICK_SELECT
        )
        event_name = context.content.input_value
        container_build_method = action_value.get(
            "container_build_method", "_build_quick_select_record_card"
        )

        # 获取当前卡片的业务数据
        business_data, card_id, _ = self.parent._get_core_data(context)
        if not business_data:
            new_card_dsl = self.parent._routine_handle_empty_data_with_cancel(
                business_data or {},
                method_name="select_record_by_input",
                default_method=container_build_method,
            )
            return self.parent._handle_card_operation_common(
                card_content=new_card_dsl,
                card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
                update_toast_type=ToastTypes.ERROR,
                toast_message="操作已失效",
            )

        routine_business = self.parent.message_router.routine_record
        definitions_data = routine_business.load_event_definitions(user_id)

        if definitions_data and event_name in definitions_data["definitions"]:
            # 事件存在，进入快速记录模式
            event_def = definitions_data["definitions"][event_name]
            last_record_time = definitions_data.get("last_record_time", None)
            quick_record_data = routine_business.build_quick_record_data(
                user_id, event_name, event_def, last_record_time
            )

            business_data["workflow_state"] = (
                "quick_record"  # 集成模式状态，这个姑且先保留吧，稍微冗余一点点
            )
            business_data["container_build_method"] = container_build_method

            parent_data, _ = self.parent._safe_get_business_data(
                business_data, parent_business_name
            )
            parent_data["sub_business_data"] = quick_record_data
            parent_data["sub_business_name"] = CardConfigKeys.ROUTINE_RECORD
            sub_business_build_method = self.parent.get_sub_business_build_method(
                CardConfigKeys.ROUTINE_RECORD
            )
            parent_data["sub_business_build_method"] = sub_business_build_method

            # 更新卡片显示
            new_card_dsl = self.parent._routine_get_build_method_and_execute(
                business_data, container_build_method
            )
            return self.parent._save_and_respond_with_update(
                context.user_id,
                card_id,
                business_data,
                new_card_dsl,
                f"正在记录 【{event_name}】",
                ToastTypes.SUCCESS,
            )

        # 事件不存在，显示新建提示但保持在选择模式
        # 这里是下一个迭代的优化重点。
        return self.parent._handle_card_operation_common(
            card_content={"message": "请输入事项名称"},
            card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
            update_toast_type=ToastTypes.INFO,
            toast_message=f"'{event_name}' 是新事项，可以创建新定义",
        )

    def show_query_info(self, context: MessageContext_Refactor) -> ProcessResult:
        """
        显示查询信息处理
        """
        action_value = context.content.value
        user_id = context.user_id
        parent_business_name = action_value.get(
            "card_config_key", CardConfigKeys.ROUTINE_QUICK_SELECT
        )
        container_build_method = action_value.get(
            "container_build_method", "_build_quick_select_record_card"
        )

        # 获取当前卡片的业务数据
        business_data, card_id, _ = self.parent._get_core_data(context)
        if not business_data:
            new_card_dsl = self.parent._routine_handle_empty_data_with_cancel(
                business_data or {}, "show_query_info", container_build_method
            )
            return self.parent._handle_card_operation_common(
                card_content=new_card_dsl,
                card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
                update_toast_type=ToastTypes.ERROR,
                toast_message="操作已失效",
            )

        routine_business = self.parent.message_router.routine_record
        definitions_data = routine_business.load_event_definitions(user_id)

        if definitions_data:
            # 事件存在，进入快速记录模式
            business_data["workflow_state"] = (
                "quick_record"  # 集成模式状态，这个姑且先保留吧，稍微冗余一点点
            )
            business_data["container_build_method"] = container_build_method

            parent_data, _ = self.parent._safe_get_business_data(
                business_data, parent_business_name
            )

            # query 的数据结构非常简单，就是definitions_data
            new_query_node_data = definitions_data

            # 1. 准备工作：检查并"抢救"需要保留的孙子节点
            #    只有当父节点的子业务本身就是QUERY，且这个QUERY下面还有子业务（即孙子节点）时，我们才需要保留。
            existing_sub_name = parent_data.get("sub_business_name")
            existing_sub_data = parent_data.get("sub_business_data")

            if (
                existing_sub_name == CardConfigKeys.ROUTINE_QUERY
                and existing_sub_data
                and existing_sub_data.get("sub_business_data")
            ):

                # 找到了需要保留的孙子节点，我们把它从旧的结构中取出来
                grandchild_data = existing_sub_data.get("sub_business_data")
                grandchild_name = existing_sub_data.get("sub_business_name")
                grandchild_method = existing_sub_data.get("sub_business_build_method")

                # 将孙子节点挂载到我们即将使用的新查询节点上
                new_query_node_data["sub_business_data"] = grandchild_data
                new_query_node_data["sub_business_name"] = grandchild_name
                new_query_node_data["sub_business_build_method"] = grandchild_method

            # 2. 执行操作：用准备好的新查询节点覆盖父节点的子业务
            #    无论之前是什么情况（没有子业务、子业务不是QUERY、子业务是QUERY但没有孙子），
            #    父节点的子业务都会被设置为我们刚刚准备好的新查询节点。
            parent_data["sub_business_data"] = new_query_node_data
            parent_data["sub_business_name"] = CardConfigKeys.ROUTINE_QUERY
            sub_business_build_method = self.parent.get_sub_business_build_method(
                CardConfigKeys.ROUTINE_QUERY
            )
            parent_data["sub_business_build_method"] = sub_business_build_method

            # 更新卡片显示
            new_card_dsl = self.parent._routine_get_build_method_and_execute(
                business_data, container_build_method
            )
            return self.parent._save_and_respond_with_update(
                context.user_id,
                card_id,
                business_data,
                new_card_dsl,
                "",
                ToastTypes.SUCCESS,
            )
