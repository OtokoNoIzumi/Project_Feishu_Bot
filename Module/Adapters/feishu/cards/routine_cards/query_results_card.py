# -*- coding: utf-8 -*-
"""
Query Results Card
查询结果卡片
"""

from typing import Dict, Any
import pprint
import datetime
from Module.Business.processors.base_processor import MessageContext_Refactor
from Module.Services.constants import CardConfigKeys, ToastTypes, RoutineRecordModes


class QueryResultsCard:
    """
    查询结果卡片管理器
    """

    def __init__(self, parent_manager):
        self.parent = parent_manager
        self.default_update_build_method = "update_query_results_card"
        self.today = ""
        self.year = ""

    def build_query_results_card(self, business_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        查询结果卡片核心构建逻辑
        """
        query_data = business_data.get("query_data", [])
        subtitle = f"共有 {len(query_data)} 个已知日程"
        header = self.parent.build_card_header(
            "🔍 快速查询日程",
            subtitle,
            "wathet",
        )
        elements = self.build_query_elements(business_data)
        return self.parent.build_base_card_structure(elements, header, "12px")

    def build_query_elements(self, business_data: Dict[str, Any]) -> list:
        """
        查询元素构建
        """

        is_confirmed = business_data.get("is_confirmed", False)
        cancel_confirmed = business_data.get("cancel_confirmed", False)
        continuous_record = business_data.get("continuous_record", False)

        # 统一的disabled变量 - 连续记录模式下，查询元素不被disabled
        components_disabled = (
            not cancel_confirmed and is_confirmed and not continuous_record
        )
        build_method_name = business_data.get(
            "container_build_method", self.default_update_build_method
        )
        data_source, is_container_mode = self.parent.safe_get_business_data(
            business_data, CardConfigKeys.ROUTINE_QUERY
        )
        default_action_data = {
            "card_config_key": CardConfigKeys.ROUTINE_QUERY,
            "container_build_method": build_method_name,
        }

        query_data = data_source.get("query_data", [])
        selected_category = data_source.get("selected_category", "")
        type_name_filter = data_source.get("type_name_filter", "")
        expand_position = data_source.get("expand_position", -1)
        filter_limit = data_source.get("filter_limit", 10)

        category_options_raw = data_source.get("category_options", [])

        options_dict = {option: option for option in category_options_raw}
        category_options = self.parent.build_options(options_dict)

        # 对query_data进行筛选
        filtered_records = []

        for record in query_data:
            event_name = record.get("event_name", "")
            category = record.get("category", "")

            # 类型筛选：如果选择了具体类型且不是"全部"，则进行筛选
            if (
                selected_category
                and selected_category != "全部"
                and category != selected_category
            ):
                continue
            if type_name_filter:
                keywords = [k for k in type_name_filter.strip().split() if k]
                if not all(k in event_name for k in keywords):
                    continue
            filtered_records.append(record)

        # 限制显示数量
        filtered_records = filtered_records[:filter_limit]

        elements = []
        elements.append(
            self.parent.build_form_row(
                "类型筛选",
                self.parent.build_select_element(
                    placeholder="选择类型",
                    options=category_options,
                    initial_value=selected_category,
                    disabled=components_disabled,
                    action_data={
                        "card_action": "update_category_filter",
                        **default_action_data,
                    },
                    name="category_filter",
                ),
            )
        )
        elements.append(
            self.parent.build_form_row(
                "名称筛选",
                self.parent.build_input_element(
                    placeholder="输入空格取消筛选",
                    initial_value=type_name_filter,
                    disabled=components_disabled,
                    action_data={
                        "card_action": "update_type_name_filter",
                        **default_action_data,
                    },
                    name="type_name_filter",
                ),
            )
        )
        if is_container_mode:
            query_length = len(query_data)
            if query_length > filter_limit:
                elements.append(
                    self.parent.build_markdown_element(
                        content=f"共有 {query_length} 个已知日程，当前显示上限 {filter_limit}"
                    )
                )
        elements.append(self.parent.build_line_element())

        # 特地从中途取出数据再判断子业务，用来判断要不要修改展开的默认状态。
        query_business_data = data_source.get("sub_business_data", {})
        has_query_business_data = bool(query_business_data)
        default_expanded = bool(filtered_records)
        if has_query_business_data:
            default_expanded = False

        new_elements = self._build_record_elements(
            filtered_records,
            components_disabled,
            default_action_data,
            default_expanded,
            expand_position,
        )
        elements.extend(new_elements)

        sub_business_build_method = data_source.get("sub_business_build_method", "")
        if sub_business_build_method and hasattr(
            self.parent, sub_business_build_method
        ):
            # 这里必须要用business_data，有很多最外层的通用方法在这里。
            sub_elements = getattr(self.parent, sub_business_build_method)(
                business_data
            )

            elements.append(self.parent.build_line_element())
            elements.extend(sub_elements)

        return elements

    # region 记录元素构建
    def _build_record_elements(
        self,
        filtered_records,
        is_confirmed: bool,
        default_action_data: dict,
        default_expanded: bool,
        expand_position: int,
    ) -> list:
        """
        构建记录元素
        """
        elements = []
        self.year = datetime.datetime.now().strftime("%Y")
        self.today = datetime.datetime.now().strftime("%Y-%m-%d")
        # 计算展开逻辑的独立参数
        if expand_position > -1:
            expand_logic = [False] * len(filtered_records)
            expand_logic[expand_position] = True
        else:
            if default_expanded:
                expand_logic = self._calculate_expand_logic(filtered_records)
            else:
                expand_logic = [False] * len(filtered_records)
        active_elements = []
        definition_elements = []

        for i, record in enumerate(filtered_records):
            record_type = record.get("record_type")
            current_expand = expand_logic[i]

            match record_type:
                case "active_record":
                    active_elements.extend(
                        self._build_active_record_elements(
                            record, current_expand, is_confirmed, default_action_data, i
                        )
                    )
                case "event_definition":
                    definition_elements.extend(
                        self._build_definition_elements(
                            record, current_expand, is_confirmed, default_action_data
                        )
                    )

        elements.extend(active_elements)
        if active_elements and definition_elements:
            elements.append(self.parent.build_line_element(margin="0px"))
        elements.extend(definition_elements)

        if not elements:
            elements.append(
                self.parent.build_markdown_element(content="**📝 没有符合条件的记录**")
            )
        return elements

    def _build_active_record_elements(
        self,
        record: dict,
        current_expand: bool,
        is_confirmed: bool,
        default_action_data: dict,
        expand_position: int,
    ) -> list:
        """
        构建active_record元素
        """
        elements = []
        event_name = record.get("event_name", "")
        record_id = record.get("record_id", "")
        related_events = record.get("related_events", [])
        # 按钮区
        buttons = []
        # 完成按钮
        complete_action_data = {
            "card_action": "query_record",
            "operation_hint_str": "complete_active_record",
            "record_id": record_id,
            "event_name": event_name,
            "record_mode": RoutineRecordModes.EDIT,
            "message": f"正在完成 [{event_name}]",
            **default_action_data,
        }
        buttons.append(
            self.parent.build_button_element(
                text="完成",
                disabled=is_confirmed,
                action_data=complete_action_data,
                type="primary",
                size="small",
            )
        )

        # 新关联事件按钮
        new_related_action_data = {
            "card_action": "query_record",
            "operation_hint_str": "create_related_event",
            "source_record_id": record_id,
            "expand_position": expand_position,
            "message": "正在创建关联事件",
            **default_action_data,
        }
        buttons.append(
            self.parent.build_button_element(
                text="新关联事件",
                disabled=is_confirmed,
                action_data=new_related_action_data,
                size="small",
            )
        )

        # 按钮行
        content = [
            self.parent.build_button_group_element(buttons),
        ]

        button_text_length = 0
        new_buttons = []
        # related_events 按钮
        for rel in related_events:
            current_button_length = min(4, len(rel))
            # 预检测：如果添加当前按钮会超出限制，先输出已有按钮
            if button_text_length + current_button_length > 10 and new_buttons:
                content.append(
                    self.parent.build_button_group_element(new_buttons),
                )
                new_buttons = []
                button_text_length = 0

            new_action_data = {
                "card_action": "query_record",
                "operation_hint_str": "related_event_action",
                "source_record_id": record_id,
                "event_name": rel,
                "expand_position": expand_position,
                "message": f"正在记录关联事件：{rel}",
                **default_action_data,
            }
            new_buttons.append(
                self.parent.build_button_element(
                    text=rel,
                    disabled=is_confirmed,
                    action_data=new_action_data,
                    size="small",
                )
            )
            button_text_length += current_button_length

        # 输出剩余按钮
        if new_buttons:
            content.append(
                self.parent.build_button_group_element(new_buttons),
            )

        # 头部信息
        head_info = f"**{event_name}**"
        scheduled_time = record.get("data", {}).get("scheduled_start_time", "")
        create_time = record.get("data", {}).get("create_time", "")
        last_updated = record.get("data", {}).get("last_updated", "")
        if scheduled_time:
            head_info += f"  计划: {self._get_short_time(scheduled_time)}"
        elif last_updated:
            head_info += f"  更新: {self._get_short_time(last_updated)}"
        elif create_time:
            head_info += f"  开始: {self._get_short_time(create_time)}"
        elements.append(
            self.parent.build_collapsible_panel_element(
                header_text=head_info,
                header_icon="down-small-ccm_outlined",
                expanded=current_expand,
                content=content,
            )
        )
        return elements

    def _build_definition_elements(
        self,
        record: dict,
        current_expand: bool,
        is_confirmed: bool,
        default_action_data: dict,
    ) -> list:
        """
        构建definition元素
        """
        elements = []
        event_name = record.get("event_name", "")
        definition = record.get("data", {})
        # 按钮区
        record_action_data = {
            "card_action": "query_record",
            "operation_hint_str": "quick_record_select",
            "event_name": event_name,
            "message": f"正在记录 [{event_name}]",
            **default_action_data,
        }
        buttons = []
        buttons.append(
            self.parent.build_button_element(
                text=f"记录 {event_name}",
                action_data=record_action_data,
                disabled=is_confirmed,
                type="primary",
                size="small",
            )
        )
        content = [
            self.parent.build_button_group_element(buttons),
        ]

        stat_lines = []
        stats = definition.get("stats", {})
        if definition.get("avg_duration"):
            stat_lines.append(f"平均时长: {definition.get('avg_duration')} 分钟")
        if stats.get("record_count"):
            stat_lines.append(f"记录数: {stats.get('record_count')}")
        if stats.get("cycle_count"):
            stat_lines.append(f"周期近况: {stats.get('cycle_count')}")
        if stats.get("last_refresh_date"):
            stat_lines.append(f"上次重置时间: {stats.get('last_refresh_date')}")

        if stat_lines:
            content.append(
                self.parent.build_markdown_element(
                    content="\n".join(stat_lines), text_size="small"
                )
            )

        # 头部信息
        head_info = f"**{event_name}**"
        last_record_time = definition.get("last_record_time", "")
        if last_record_time:
            head_info += f"  上次完成: {self._get_short_time(last_record_time)}"
        elements.append(
            self.parent.build_collapsible_panel_element(
                header_text=head_info,
                header_icon="down-small-ccm_outlined",
                expanded=current_expand,
                content=content,
            )
        )
        return elements

    def _get_short_time(self, time_string: str) -> str:
        """
        生成短时间字符串
        """
        return time_string.replace(f"{self.today} ", "").replace(f"{self.year}-", "")

    def _calculate_expand_logic(self, filtered_records: list) -> list:
        """
        计算展开逻辑的独立参数
        返回一个布尔列表，对应每个记录是否应该展开

        逻辑规则：
        1. 如果记录总数小于3，全部展开
        2. 如果记录总数大于等于3，检查前2个记录的内容复杂度
           - 如果前2个记录都只有按钮组（内容元素数量为1），可以展开前2个
           - 否则只展开第一个
        """
        total_records = len(filtered_records)

        # 如果记录总数小于3，全部展开
        if total_records < 3:
            return [True] * total_records

        # 如果记录总数大于等于3，检查前2个记录的内容复杂度
        expand_list = [False] * total_records

        # 检查前2个记录是否只有按钮组（内容元素数量为1）
        first_two_simple = True
        for i in range(min(2, total_records)):
            record = filtered_records[i]
            record_type = record.get("record_type")

            match record_type:
                case "active_record":
                    content_count = 1
                case "event_definition":
                    content_count = 1
                    definition = record.get("data", {})
                    stats = definition.get("stats", {})
                    if (
                        definition.get("avg_duration")
                        or stats.get("record_count")
                        or stats.get("cycle_count")
                        or stats.get("last_refresh_date")
                    ):
                        content_count = 2

                case _:
                    content_count = 1

            # 如果前2个记录中有任何一个内容元素数量大于1，则不是简单内容
            if content_count > 1:
                first_two_simple = False
                break

        # 根据前2个记录的内容复杂度决定展开策略
        if first_two_simple:
            # 前2个记录内容简单，可以展开前2个
            expand_list[0] = True
            if total_records > 1:
                expand_list[1] = True
        else:
            # 前2个记录内容复杂，只展开第一个
            expand_list[0] = True

        return expand_list

    # endregion 记录元素构建

    # region 回调事件
    def update_category_filter(self, context: MessageContext_Refactor):
        """处理类型筛选更新"""
        new_option = context.content.value.get("option", "")
        return self.parent.update_card_field(
            context,
            field_key="selected_category",
            extracted_value=new_option,
            sub_business_name=CardConfigKeys.ROUTINE_QUERY,
            toast_message="",
        )

    def update_type_name_filter(self, context: MessageContext_Refactor):
        """处理名称筛选更新"""
        filter_value = context.content.value.get("value", "").strip()
        return self.parent.update_card_field(
            context,
            "type_name_filter",
            filter_value,
            CardConfigKeys.ROUTINE_QUERY,
            "已完成筛选",
        )

    def query_record(self, context: MessageContext_Refactor):
        """统一的记录操作回调方法 - 所有动态参数通过action_data传递"""
        action_value = context.content.value
        user_id = context.user_id

        # 从action_data中获取所有动态参数
        operation_hint_str = action_value.get("operation_hint_str", "")
        record_id = action_value.get("record_id", "")
        source_record_id = action_value.get("source_record_id", "")
        event_name = action_value.get("event_name", "")
        record_mode = action_value.get("record_mode", RoutineRecordModes.ADD)
        expand_position = action_value.get("expand_position", -1)
        message = action_value.get("message", "正在处理记录操作")
        container_build_method = action_value.get(
            "container_build_method", self.default_update_build_method
        )

        # 获取当前卡片的业务数据
        business_data, card_id, error_response = self.parent.ensure_valid_context(
            context, operation_hint_str, container_build_method
        )
        if error_response:
            return error_response

        business_data["is_confirmed"] = False
        business_data["cancel_confirmed"] = False

        parent_data, _ = self.parent.safe_get_business_data(
            business_data, CardConfigKeys.ROUTINE_QUERY
        )

        # 处理expand_position
        if expand_position > -1:
            parent_data["expand_position"] = expand_position
        else:
            parent_data.pop("expand_position", None)

        # 构建记录填写界面数据
        routine_business = self.parent.message_router.routine_record

        if record_mode == RoutineRecordModes.EDIT:
            # 查找active_record
            query_data = parent_data.get("query_data", [])
            active_record = next(
                (
                    record
                    for record in query_data
                    if record.get("record_id") == record_id
                ),
                None,
            )
            new_record_data = routine_business.build_record_business_data(
                user_id,
                event_name,
                record_mode=record_mode,
                current_record_data=(
                    active_record.get("data", {}) if active_record else {}
                ),
            )
        else:
            new_record_data = routine_business.build_record_business_data(
                user_id, event_name
            )
        new_record_data["source_record_id"] = source_record_id

        # 更新业务数据
        business_data["container_build_method"] = container_build_method
        parent_data["sub_business_data"] = new_record_data
        parent_data["sub_business_name"] = CardConfigKeys.ROUTINE_RECORD
        parent_data["sub_business_build_method"] = (
            self.parent.get_sub_business_build_method(CardConfigKeys.ROUTINE_RECORD)
        )

        # 更新卡片显示
        new_card_dsl = self.parent.build_update_card_data(
            business_data, container_build_method
        )
        return self.parent.save_and_respond_with_update(
            context.user_id,
            card_id,
            business_data,
            new_card_dsl,
            message,
            ToastTypes.SUCCESS,
        )

    # endregion 回调事件
