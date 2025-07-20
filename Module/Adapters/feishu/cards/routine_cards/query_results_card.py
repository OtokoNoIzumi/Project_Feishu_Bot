# -*- coding: utf-8 -*-
"""
Query Results Card
查询结果卡片

来源：routine_cards.py RoutineCardManager类
迁移的方法：
- _build_query_results_card (行号:315-358)
- _build_query_elements (行号:360-448)
- update_category_filter (行号:1483-1492)
- update_type_name_filter (行号:1494-1509)
"""

from typing import Dict, Any
from Module.Business.processors.base_processor import (
    MessageContext_Refactor,
)
from Module.Services.constants import CardConfigKeys


class QueryResultsCard:
    """
    查询结果卡片管理器
    """

    def __init__(self, parent_manager):
        self.parent = parent_manager  # 访问主管理器的共享方法和属性

    def _build_query_results_card(
        self, business_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        查询结果卡片核心构建逻辑
        """
        definitions = business_data.get("definitions", {})
        subtitle = f"共有 {len(definitions)} 个已知日程"
        header = self.parent._build_card_header(
            "🔍 快速查询日程",
            subtitle,
            "wathet",
        )
        elements = self._build_query_elements(business_data)
        return self.parent._build_base_card_structure(elements, header, "12px")

    def _build_query_elements(self, business_data: Dict[str, Any]) -> list:
        """
        查询元素构建
        """

        is_confirmed = business_data.get("is_confirmed", False)
        container_build_method = business_data.get(
            "container_build_method", "_build_query_results_card"
        )
        data_source, _ = self.parent._safe_get_business_data(
            business_data, CardConfigKeys.ROUTINE_QUERY
        )

        # 特地从中途取出数据再判断子业务，用来判断要不要修改展开的默认状态。
        query_business_data = data_source.get("sub_business_data", {})
        has_query_business_data = bool(query_business_data)

        definitions = data_source.get("definitions", {})
        selected_category = data_source.get("selected_category", "")
        type_name_filter = data_source.get("type_name_filter", "")

        all_categories = set()
        for d in definitions.values():
            all_categories.add(d.get("category", "未分类"))

        category_options = [
            {
                "text": {"tag": "plain_text", "content": c or "未分类"},
                "value": c or "未分类",
            }
            for c in sorted(all_categories)
        ]
        filtered = []

        for name, d in definitions.items():
            if selected_category and d.get("category", "未分类") != selected_category:
                continue
            if type_name_filter:
                keywords = [k for k in type_name_filter.strip().split() if k]
                if not all(k in name for k in keywords):
                    continue
            filtered.append((name, d))

        filtered = filtered[:10]

        elements = []
        elements.append(
            self.parent._build_form_row(
                "类型筛选",
                self.parent._build_select_element(
                    placeholder="选择类型",
                    options=category_options,
                    initial_value=selected_category,
                    disabled=is_confirmed,
                    action_data={
                        "card_action": "update_category_filter",
                        "card_config_key": CardConfigKeys.ROUTINE_QUERY,
                    },
                    name="category_filter",
                ),
                width_list=["80px", "180px"],
            )
        )
        elements.append(
            self.parent._build_form_row(
                "名称筛选",
                self.parent._build_input_element(
                    placeholder="输入空格取消筛选",
                    initial_value=type_name_filter,
                    disabled=is_confirmed,
                    action_data={
                        "card_action": "update_type_name_filter",
                        "card_config_key": CardConfigKeys.ROUTINE_QUERY,
                    },
                    name="type_name_filter",
                ),
                width_list=["80px", "180px"],
            )
        )
        # 待增加一个筛选结果和一件清楚筛选。
        elements.append({"tag": "hr", "margin": "0px 0px 6px 0px"})

        default_expanded = bool(filtered)
        if has_query_business_data:
            default_expanded = False

        for name, d in filtered:
            stats = d.get("stats", {})
            stat_lines = []
            if "record_count" in stats:
                stat_lines.append(f"总记录: {stats.get('record_count', 0)}")
            if "cycle_count" in stats:
                stat_lines.append(f"周期数: {stats.get('cycle_count', 0)}")
            if "last_refresh_date" in stats and stats.get("last_refresh_date"):
                stat_lines.append(f"上次重置时间: {stats.get('last_refresh_date')}")
            if "avg_all_time" in stats.get("duration", {}):
                stat_lines.append(
                    f"平均耗时: {round(stats['duration'].get('avg_all_time', 0), 1)}"
                )
            progress_type = d.get("properties", {}).get("progress_type", "")
            if progress_type:
                if "last_progress_value" in stats:
                    stat_lines.append(
                        f"最近进度: {stats.get('last_progress_value', '-')}"
                    )
                if "total_progress_value" in stats:
                    stat_lines.append(
                        f"累计进度: {stats.get('total_progress_value', '-')}"
                    )
            content = []
            content.append(
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": f"记录 {name}"},
                    "type": "primary",
                    "width": "default",
                    "size": "small",
                    "disabled": is_confirmed,
                    "behaviors": [
                        {
                            "type": "callback",
                            "value": {
                                "card_action": "quick_record_select",
                                "card_config_key": CardConfigKeys.ROUTINE_QUERY,
                                "event_name": name,
                                "container_build_method": container_build_method,
                            },
                        }
                    ],
                }
            )
            if stat_lines:
                content.append(
                    {
                        "tag": "markdown",
                        "content": "\n".join(stat_lines),
                        "text_size": "small",
                    }
                )
            head_info = f"**{name}**"
            last_update_date = d.get("last_updated", "")
            if last_update_date:
                last_update_date = (
                    last_update_date.split(" ")[0]
                    + " "
                    + last_update_date.split(" ")[1][:5]
                )
                head_info += f" 上次完成: {last_update_date}"
            elements.append(
                {
                    "tag": "collapsible_panel",
                    "expanded": default_expanded,
                    "header": {
                        "title": {"tag": "markdown", "content": head_info},
                        "icon": {
                            "tag": "standard_icon",
                            "token": "down-small-ccm_outlined",
                            "color": "",
                            "size": "16px 16px",
                        },
                        "icon_position": "right",
                        "icon_expanded_angle": -180,
                    },
                    "elements": content,
                }
            )
        if not filtered:
            elements.append(
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": "**📝 没有符合条件的日程**"},
                }
            )

        # 集成模式：根据工作流程状态显示不同内容
        sub_business_build_method = data_source.get("sub_business_build_method", "")
        if sub_business_build_method and hasattr(
            self.parent, sub_business_build_method
        ):
            # 这里必须要用business_data，有很多最外层的通用方法在这里，不要偷懒。
            sub_elements = getattr(self.parent, sub_business_build_method)(
                business_data
            )

            elements.append({"tag": "hr", "margin": "6px 0px"})
            elements.extend(sub_elements)

        return elements

    def update_category_filter(self, context: MessageContext_Refactor):
        """处理类型筛选更新"""
        new_option = context.content.value.get("option", "")
        return self.parent._routine_update_field_and_refresh(
            context,
            field_key="selected_category",
            extracted_value=new_option,
            sub_business_name=CardConfigKeys.ROUTINE_QUERY,
            toast_message="",
        )

    def update_type_name_filter(self, context: MessageContext_Refactor):
        """处理名称筛选更新"""
        filter_value = context.content.value.get("value", "").strip()
        return self.parent._routine_update_field_and_refresh(
            context,
            "type_name_filter",
            filter_value,
            CardConfigKeys.ROUTINE_QUERY,
            "已完成筛选",
        )
