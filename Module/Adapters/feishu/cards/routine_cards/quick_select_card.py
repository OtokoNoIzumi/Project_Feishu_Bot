# -*- coding: utf-8 -*-
"""
Quick Select Card
快速选择卡片
"""

from datetime import datetime, timedelta
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
    RoutineRecordModes,
)


class QuickSelectCard:
    """
    快速选择卡片管理器
    """

    def __init__(self, parent_manager):
        self.parent = parent_manager  # 访问主管理器的共享方法和属性
        self.default_update_build_method = "update_quick_select_record_card"  # 目前是对接主容器里的方法，最终调用在那边，这里只是传标识

    def build_quick_select_record_card(
        self, business_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        快速选择记录卡片核心构建逻辑
        作为最上层的嵌套容器，要注意控制元素(tag)数量，不要超过200个，否则会报错。
        """
        # 1级入口，不需要嵌套，但其实也可以来一个？嵌套应该是通用能力？等第4个做的时候再改吧。
        build_method_name = business_data.get(
            "container_build_method", self.default_update_build_method
        )
        event_name = business_data.get("selected_event_name", "")
        is_confirmed = business_data.get("is_confirmed", False)
        cancel_confirmed = business_data.get("cancel_confirmed", False)
        result = business_data.get("result", "取消")
        quick_events = business_data.get("quick_events", [])

        # 提取集成模式相关数据，和后台业务无关的初始数据在这里初始化
        workflow_state = business_data.get("workflow_state", "initial")
        input_text = business_data.get("input_text", "")

        header = self.parent.build_workflow_header(
            workflow_state, event_name, is_confirmed, result
        )
        elements = []

        # 查询日程行 - 左边查询日程按钮，右边连续记录checkbox
        continuous_record = business_data.get("continuous_record", False)
        # 统一的disabled变量
        components_disabled = (
            not cancel_confirmed and is_confirmed and not continuous_record
        )
        query_action_data = {
            "card_action": "show_query_info",
            "card_config_key": CardConfigKeys.ROUTINE_QUICK_SELECT,
            "container_build_method": build_method_name,
        }
        query_button = self.parent.build_button_element(
            text="查询日程",
            action_data=query_action_data,
            disabled=components_disabled,
            button_type="primary",
            size="small",
        )

        continuous_action_data = {
            "card_action": "toggle_continuous_record",
            "card_config_key": CardConfigKeys.ROUTINE_QUICK_SELECT,
            "container_build_method": build_method_name,
        }

        continuous_checker = self.parent.build_checker_element(
            text="连续记录",
            checked=continuous_record,
            disabled=components_disabled,
            action_data=continuous_action_data,
        )

        elements.append(
            self.parent.build_column_set_element(
                columns=[
                    self.parent.build_column_element(
                        elements=[query_button],
                        width="90px",
                    ),
                    self.parent.build_column_element(
                        elements=[continuous_checker],
                        width="170px",
                        vertical_align="center",
                        horizontal_align="right",
                    ),
                ],
            )
        )

        elements.append(
            self.parent.build_form_row(
                "添加事项",
                self.parent.build_input_element(
                    placeholder="输入事项名称...",
                    initial_value=input_text,
                    disabled=components_disabled,
                    action_data={
                        "card_action": "select_record_by_input",
                        "card_config_key": CardConfigKeys.ROUTINE_QUICK_SELECT,
                        "container_build_method": build_method_name,
                    },
                    element_id="new_event_name",
                    name="new_event_name",
                ),
                width_list=["90px", "170px"],
            )
        )

        # 只在sub_business最多1层时显示快捷添加按钮组
        # 判断business_data的sub_business_data是否为dict且其下没有sub_business_data字段（即只有1层）
        show_quick_buttons = True
        sub_business_data = business_data.get("sub_business_data")
        if isinstance(sub_business_data, dict) and sub_business_data.get("sub_business_data") is not None:
            show_quick_buttons = False

        # 快捷添加按钮组 - 使用压缩布局
        if quick_events and show_quick_buttons:
            # 添加快捷添加标题
            elements.append(self.parent.build_markdown_element("**快捷添加**"))

            button_text_length = 0
            new_buttons = []

            for event in quick_events:
                event_name_btn = event.get("name", "")
                event_type = event.get("type", RoutineTypes.INSTANT.value)
                type_emoji = RoutineTypes.get_type_emoji(event_type)
                is_active_record = event.get("is_active_record", False)

                # 预检测长度，如果添加当前按钮会超出限制，先输出当前行
                current_button_length = max(4, len(event_name_btn) + 2)
                if (
                    button_text_length + current_button_length > 13
                    or len(new_buttons) >= 3
                ) and new_buttons:
                    elements.append(
                        self.parent.build_button_group_element(buttons=new_buttons)
                    )
                    new_buttons = []
                    button_text_length = 0

                # 根据是否为active_record设置不同的action_data
                if is_active_record:
                    # active_record事件：进入完成模式
                    button_action_data = {
                        "card_action": "complete_active_record",
                        "record_id": event.get("active_record_id", ""),
                        "event_name": event_name_btn,
                        "card_config_key": CardConfigKeys.ROUTINE_QUICK_SELECT,
                        "container_build_method": build_method_name,
                    }
                    button_type = "primary"  # active_record使用primary样式
                else:
                    # 普通事件：进入新建模式
                    button_action_data = {
                        "card_action": "quick_record_select",
                        "card_config_key": CardConfigKeys.ROUTINE_QUICK_SELECT,
                        "event_name": event_name_btn,
                        "container_build_method": build_method_name,
                    }
                    button_type = "default"  # 非active_record使用default样式

                new_buttons.append(
                    self.parent.build_button_element(
                        text=f"{type_emoji} {event_name_btn}",
                        action_data=button_action_data,
                        button_type=button_type,
                        size="small",
                        disabled=components_disabled,
                    )
                )

                button_text_length += current_button_length

            # 添加剩余的按钮
            if new_buttons:
                elements.append(
                    self.parent.build_button_group_element(buttons=new_buttons)
                )

        # # 添加计算按钮组
        # elements.append(self.parent.build_markdown_element("**颜色计算**"))

        # calculate_buttons = []

        # # 计算昨天按钮
        # yesterday_action_data = {
        #     "card_action": "calculate_yesterday_color",
        #     "card_config_key": CardConfigKeys.ROUTINE_QUICK_SELECT,
        #     "container_build_method": build_method_name,
        # }
        # calculate_buttons.append(
        #     self.parent.build_button_element(
        #         text="🎨 计算昨天",
        #         action_data=yesterday_action_data,
        #         type="default",
        #         size="small",
        #         disabled=components_disabled,
        #     )
        # )

        # # 计算今天按钮
        # today_action_data = {
        #     "card_action": "calculate_today_color",
        #     "card_config_key": CardConfigKeys.ROUTINE_QUICK_SELECT,
        #     "container_build_method": build_method_name,
        # }
        # calculate_buttons.append(
        #     self.parent.build_button_element(
        #         text="🎨 计算今天",
        #         action_data=today_action_data,
        #         type="default",
        #         size="small",
        #         disabled=components_disabled,
        #     )
        # )

        # elements.append(
        #     self.parent.build_button_group_element(buttons=calculate_buttons)
        # )

        # 集成模式：根据工作流程状态显示不同内容
        sub_business_build_method = business_data.get("sub_business_build_method", "")
        if sub_business_build_method and hasattr(
            self.parent, sub_business_build_method
        ):
            sub_elements = getattr(self.parent, sub_business_build_method)(
                business_data
            )

            elements.append(self.parent.build_line_element())
            elements.extend(sub_elements)

        return self.parent.build_base_card_structure(elements, header, "12px")

    # region 回调方法
    def toggle_continuous_record(
        self, context: MessageContext_Refactor
    ) -> ProcessResult:
        """
        切换连续记录状态
        """
        action_value = context.content.value
        container_build_method = action_value.get(
            "container_build_method", self.default_update_build_method
        )

        # 获取当前卡片的业务数据
        business_data, card_id, error_response = self.parent.ensure_valid_context(
            context, "toggle_continuous_record", container_build_method
        )
        if error_response:
            return error_response

        # 切换连续记录状态
        current_state = business_data.get("continuous_record", False)
        business_data["continuous_record"] = not current_state
        is_confirmed = business_data.get("is_confirmed", False)
        if is_confirmed:
            business_data["cancel_confirmed"] = True

        # 更新卡片显示
        new_card_dsl = self.parent.build_update_card_data(
            business_data, container_build_method
        )

        toast_message = (
            "已开启连续记录模式" if not current_state else "已关闭连续记录模式"
        )
        return self.parent.save_and_respond_with_update(
            context.user_id,
            card_id,
            business_data,
            new_card_dsl,
            toast_message,
            ToastTypes.SUCCESS,
        )

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
            "container_build_method", self.default_update_build_method
        )

        # 获取当前卡片的业务数据
        business_data, card_id, error_response = self.parent.ensure_valid_context(
            context, "quick_record_select", container_build_method
        )
        if error_response:
            return error_response

        business_data["is_confirmed"] = False
        business_data["cancel_confirmed"] = False
        # 加载事件定义
        routine_business = self.parent.message_router.routine_record

        definitions_data = routine_business.load_event_definitions(user_id)
        if (
            definitions_data and event_name in definitions_data["definitions"]
        ):  # 虽然是冗余但先保留吧

            new_record_data = routine_business.build_record_business_data(
                user_id, event_name
            )

            business_data["workflow_state"] = (
                "quick_record"  # 集成模式状态，这个姑且先保留吧，稍微冗余一点点
            )
            business_data["container_build_method"] = container_build_method

            parent_data, _ = self.parent.safe_get_business_data(
                business_data, parent_business_name
            )

            parent_data["sub_business_data"] = new_record_data
            parent_data["sub_business_name"] = CardConfigKeys.ROUTINE_RECORD
            sub_business_build_method = self.parent.get_sub_business_build_method(
                CardConfigKeys.ROUTINE_RECORD
            )
            parent_data["sub_business_build_method"] = sub_business_build_method

            # 更新卡片显示
            new_card_dsl = self.parent.build_update_card_data(
                business_data, container_build_method
            )
            return self.parent.save_and_respond_with_update(
                context.user_id,
                card_id,
                business_data,
                new_card_dsl,
                f"开始记录 [{event_name}]",
                ToastTypes.SUCCESS,
            )

        # 如果事件不存在，保持在选择模式
        business_data["selected_event_name"] = event_name

        new_card_dsl = self.build_quick_select_record_card(business_data)
        return self.parent.handle_card_operation_common(
            card_content=new_card_dsl,
            card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
            update_toast_type=ToastTypes.INFO,
            toast_message=f"输入了新事项 '{event_name}'",
        )

    def complete_active_record(self, context: MessageContext_Refactor) -> ProcessResult:
        """
        完成活跃记录的专用方法
        """
        action_value = context.content.value
        user_id = context.user_id
        parent_business_name = action_value.get(
            "card_config_key", CardConfigKeys.ROUTINE_QUICK_SELECT
        )
        event_name = action_value.get("event_name", "")
        record_id = action_value.get("record_id", "")
        container_build_method = action_value.get(
            "container_build_method", self.default_update_build_method
        )

        # 获取当前卡片的业务数据
        business_data, card_id, error_response = self.parent.ensure_valid_context(
            context, "complete_active_record", container_build_method
        )
        if error_response:
            return error_response

        business_data["is_confirmed"] = False
        business_data["cancel_confirmed"] = False

        # 获取routine_business实例
        routine_business = self.parent.message_router.routine_record

        active_record_data = {}

        # 查找对应的active_record_data
        for event in business_data.get("quick_events", []):
            if (
                event.get("name") == event_name
                and event.get("is_active_record")
                and event.get("active_record_id") == record_id
            ):
                active_record_data = event.get("active_record_data")
                break

        # 使用routine_business的build_record_business_data方法构建完整数据
        new_record_data = routine_business.build_record_business_data(
            user_id,
            event_name,
            record_mode=RoutineRecordModes.EDIT,
            current_record_data=active_record_data,
        )

        business_data["workflow_state"] = "quick_record"
        business_data["container_build_method"] = container_build_method

        parent_data, _ = self.parent.safe_get_business_data(
            business_data, parent_business_name
        )

        parent_data["sub_business_data"] = new_record_data
        parent_data["sub_business_name"] = CardConfigKeys.ROUTINE_RECORD
        sub_business_build_method = self.parent.get_sub_business_build_method(
            CardConfigKeys.ROUTINE_RECORD
        )
        parent_data["sub_business_build_method"] = sub_business_build_method

        # 更新卡片显示
        new_card_dsl = self.parent.build_update_card_data(
            business_data, container_build_method
        )
        if active_record_data:
            toast_msg = f"正在完成 [{event_name}]"
        else:
            toast_msg = f"无法找到活跃记录 [{event_name}] 的数据"
        return self.parent.save_and_respond_with_update(
            context.user_id,
            card_id,
            business_data,
            new_card_dsl,
            toast_msg,
            ToastTypes.SUCCESS,
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
            "container_build_method", self.default_update_build_method
        )

        # 获取当前卡片的业务数据
        business_data, card_id, error_response = self.parent.ensure_valid_context(
            context, "select_record_by_input", container_build_method
        )
        if error_response:
            return error_response

        business_data["is_confirmed"] = False
        business_data["cancel_confirmed"] = False

        routine_business = self.parent.message_router.routine_record
        new_record_data = routine_business.build_record_business_data(
            user_id, event_name
        )

        business_data["workflow_state"] = (
            "quick_record"  # 集成模式状态，这个姑且先保留吧，稍微冗余一点点
        )
        business_data["container_build_method"] = container_build_method

        parent_data, _ = self.parent.safe_get_business_data(
            business_data, parent_business_name
        )

        parent_data["sub_business_data"] = new_record_data
        parent_data["sub_business_name"] = CardConfigKeys.ROUTINE_RECORD
        sub_business_build_method = self.parent.get_sub_business_build_method(
            CardConfigKeys.ROUTINE_RECORD
        )
        parent_data["sub_business_build_method"] = sub_business_build_method

        # 更新卡片显示
        new_card_dsl = self.parent.build_update_card_data(
            business_data, container_build_method
        )
        return self.parent.save_and_respond_with_update(
            context.user_id,
            card_id,
            business_data,
            new_card_dsl,
            f"正在记录 【{event_name}】",
            ToastTypes.SUCCESS,
        )

    def show_query_info(self, context: MessageContext_Refactor):
        """
        显示查询信息处理
        """
        action_value = context.content.value
        user_id = context.user_id
        parent_business_name = action_value.get(
            "card_config_key", CardConfigKeys.ROUTINE_QUICK_SELECT
        )
        container_build_method = action_value.get(
            "container_build_method", self.default_update_build_method
        )

        # 获取当前卡片的业务数据
        business_data, card_id, error_response = self.parent.ensure_valid_context(
            context, "show_query_info", container_build_method
        )
        if error_response:
            return error_response

        routine_business = self.parent.message_router.routine_record
        new_query_node_data = routine_business.build_query_business_data(user_id)
        new_query_node_data["filter_limit"] = 5 # 这里还是5，晚点实现成展开之后只保留1个选中的

        business_data["workflow_state"] = (
            "quick_record"  # 集成模式状态，这个姑且先保留吧，稍微冗余一点点
        )
        business_data["container_build_method"] = container_build_method

        parent_data, _ = self.parent.safe_get_business_data(
            business_data, parent_business_name
        )

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
        new_card_dsl = self.parent.build_update_card_data(
            business_data, container_build_method
        )
        return self.parent.save_and_respond_with_update(
            context.user_id,
            card_id,
            business_data,
            new_card_dsl,
            "",
            ToastTypes.SUCCESS,
        )

    # endregion

    # region 测试方法
    def calculate_yesterday_color(
        self, context: MessageContext_Refactor
    ) -> ProcessResult:
        """
        计算昨天的颜色
        """
        # 计算昨天的日期
        yesterday = datetime.now() - timedelta(days=1)
        target_date = yesterday.strftime("%Y-%m-%d")
        return self.calculate_color_palette(context, target_date)

    def calculate_today_color(self, context: MessageContext_Refactor) -> ProcessResult:
        """
        计算今天的颜色
        """
        # 计算今天的日期

        today = datetime.now()
        target_date = today.strftime("%Y-%m-%d")
        return self.calculate_color_palette(context, target_date)

    def calculate_color_palette(
        self, context: MessageContext_Refactor, target_date: str
    ) -> ProcessResult:
        """
        计算颜色调色盘
        """
        action_value = context.content.value
        user_id = context.user_id
        container_build_method = action_value.get(
            "container_build_method", self.default_update_build_method
        )
        # 获取当前卡片的业务数据
        business_data, card_id, error_response = self.parent.ensure_valid_context(
            context, "calculate_color_palette", container_build_method
        )
        if error_response:
            return error_response

        # 调用routine_record的计算方法
        routine_business = self.parent.message_router.routine_record
        color_result, palette_data = routine_business.calculate_daily_color(
            user_id, target_date
        )

        # 输出详细的计算过程日志
        print(f"\n{'='*50}")
        print(f"({target_date})的详细构成:")
        print(f"颜色: {color_result}")
        print(f"调色盘: {palette_data}")
        print(f"{'='*50}")

        # 更新卡片显示（保持原样）
        new_card_dsl = self.parent.build_update_card_data(
            business_data, container_build_method
        )
        return self.parent.save_and_respond_with_update(
            context.user_id,
            card_id,
            business_data,
            new_card_dsl,
            f"({target_date})的颜色: {color_result.get('name')}, hex: {color_result.get('hex')}",
            ToastTypes.SUCCESS,
        )

    # endregion
