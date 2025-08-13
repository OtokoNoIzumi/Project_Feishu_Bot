"""日常分析卡片构建模块

负责日常分析相关的前端卡片构建和展示逻辑
"""

from typing import Dict, Any, List
from collections import defaultdict
import pandas as pd
from Module.Common.scripts.common import debug_utils
from Module.Adapters.feishu.cards.json_builder import JsonBuilder
from Module.Business.shared_process import format_time_label
from Module.Business.routine_record import RoutineRecord
from Module.Services.constants import (
    AdapterNames,
    ColorTypes,
)


class RoutineDailyElement:
    """日常分析卡片元素构建器"""

    def __init__(self, app_controller):
        self.app_controller = app_controller
        self.routine_business = RoutineRecord(app_controller)

    # region 外部调用接口

    def build_routine_elements(
        self, routine_data: Dict[str, Any], user_id: str
    ) -> List[Dict[str, Any]]:
        """构建日常模块元素"""
        elements = []
        image_key = routine_data.get("daily", {}).get("image_key", "")
        main_color = routine_data.get("daily", {}).get("main_color", {})
        weekly_data = routine_data.get("weekly", {})

        if image_key:
            image_element = JsonBuilder.build_image_element(
                image_key=image_key,
                alt=f"昨天你的{main_color.get('max_weight_category', '')}印章",
                title="昨日个性印章",
                corner_radius="5px",
                scale_type="crop_center",
                size="80px 90px",
            )
            elements.append(image_element)

        if weekly_data:
            # 先增加card里的内容，再把其他内容创建成文档
            pie_raw_data = weekly_data.get("category_stats", [])

            if pie_raw_data:
                pie_data = []
                color_mapping = {}  # 用于存储类型到颜色的映射
                for item in pie_raw_data:
                    type_name = item.get("category", "") or "无分类"
                    color = item.get("color", "#959BEE")  # 默认颜色

                    pie_data.append(
                        {
                            "type": type_name,
                            "value": round(
                                item.get("category_total_duration", 0) / 60, 1
                            ),
                        }
                    )
                    color_mapping[type_name] = color
                pie_element = JsonBuilder.build_chart_element(
                    chart_type="pie",
                    title="上周时间统计",
                    data=pie_data,
                    color_mapping=color_mapping,
                    formatter="{type}: {value}小时,{_percent_}%",
                )
                elements.append(pie_element)

            # 这里直接添加文档，还需要异步调用llm？这个似乎不应该是前端做的事，那就先增加文档吧。
            # 这里的业务逻辑结果就是往一个tokens的文件夹增加一个page，存在本地
            weekly_record = self.routine_business.load_weekly_record(user_id)
            root_folder_token = weekly_record.get("root_folder_token", "")
            business_folder_token = weekly_record.get("business_folder_token", {}).get(
                "周报告", ""
            )
            document_manager = self.app_controller.get_adapter(
                AdapterNames.FEISHU
            ).cloud_manager

            need_update_tokens = False
            if not root_folder_token:
                root_folder_token = document_manager.get_user_root_folder_token(user_id)
                weekly_record["root_folder_token"] = root_folder_token
                need_update_tokens = True
            if not business_folder_token:
                business_folder_token = document_manager.get_user_business_folder_token(
                    user_id, "周报告", root_folder_token
                )
                weekly_record["business_folder_token"]["周报告"] = business_folder_token
                need_update_tokens = True

            if need_update_tokens:
                self.routine_business.save_weekly_record(user_id, weekly_record)

            title = weekly_data.get("document_title", "")
            # 原子化同步调用：先创建文档，再写入块（均带指数退避）。如需非阻塞，未来切换到异步客户端统一调度。
            doc_data = document_manager.create_document(
                folder_token=business_folder_token,
                document_title=title,
            )
            # SDK 返回路径：data.document.document_id
            document_id = (
                getattr(getattr(doc_data, "document", None), "document_id", None)
                if doc_data
                else None
            )
            if document_id:
                content = self.generate_weekly_document_content(routine_data)
                block_resp = document_manager.create_document_block_descendant(
                    document_id=document_id,
                    block_data=content,
                    document_title=title,
                )
                url = f"https://ddsz-peng13.feishu.cn/docx/{document_id}"
                folder_url = f"https://ddsz-peng13.feishu.cn/drive/folder/{business_folder_token}"
                # 要看看怎么设置为默认打开链接，但这是小事，还是要先加内容，以及后续稍微人多一点之前就要做异步的改造，包括配合LLM
                markdown_element = JsonBuilder.build_markdown_element(
                    content=f"[查看分析：{title}]({url})\n[访问报告文件夹]({folder_url})"
                )
                elements.append(markdown_element)
                action_suggestions_data = weekly_data.get("ai_analysis", {}).get(
                    "strategic_action_suggestions", []
                )
                if action_suggestions_data:
                    markdown_element = JsonBuilder.build_markdown_element(
                        content=":MeMeMe: **本周行动建议**"
                    )
                    elements.append(markdown_element)
                    for action in action_suggestions_data:
                        action_data = {
                            "card_action": "mark_weekly_action_accepted",
                            "action_id": action.get("id", ""),
                        }
                        checker_element = JsonBuilder.build_checker_element(
                            text=f"{action.get('execution_difficulty', '')}难度: {action.get('title', '')}",
                            checked=action.get("accepted", False),
                            disabled=False,
                            action_data=action_data,
                        )
                        markdown_element = JsonBuilder.build_markdown_element(
                            content=action.get("specific_action", ""),
                            text_size="small",
                        )
                        elements.extend([checker_element, markdown_element])

            else:
                debug_utils.log_and_print("创建周报告文档失败", log_level="ERROR")

        return elements

    # endregion

    # region 周报告

    def generate_weekly_document_content(self, routine_data: Dict[str, Any]) -> str:
        """生成周报告文档内容(也可能兼容成月报)"""
        # 以嵌套块的方式一次性组装好
        # 每个元素都包含了自己的id进children和自己的内容，进descendants
        weekly_data = routine_data.get("weekly", {})
        weekly_table_data = weekly_data.get("timetable", {})

        children = []
        descendants = []
        # 先构建表格
        document_manager = self.app_controller.get_adapter(
            AdapterNames.FEISHU
        ).cloud_manager

        # 安全获取数据
        time_labels: List[str] = weekly_table_data.get("time_labels", [])
        days_data: Dict[str, Any] = weekly_table_data.get("days", {})

        # 顶层 children（两个块：标题 + 表格）
        # 文档大概要在这里处理，那么children和descendents要一起加咯？然后再追加之前的表格，这个作为一个总容器还是不错的
        heading_block_id = "heading_timetable"
        table_block_id = "table_timetable"
        children = [heading_block_id, table_block_id]

        # 标题块（采用 heading1）
        heading_block = document_manager.create_formated_text_block(
            block_id=heading_block_id,
            text="个人时间表",
            block_type="heading1",
        )
        descendants.append(heading_block)

        # 表头映射
        day_label_map = {
            "mon": "周一",
            "tue": "周二",
            "wed": "周三",
            "thu": "周四",
            "fri": "周五",
            "sat": "周六",
            "sun": "周日",
        }
        day_keys: List[str] = list(day_label_map.keys())

        # 表格 children 顺序：按行 (header -> 每个时间点)，每行按列 (time -> mon..sun)
        table_children_ids: List[str] = []

        # 表头行 cell 与文本
        header_cell_ids = ["cell_header_time"] + [
            f"cell_header_{day}" for day in day_keys
        ]
        header_text_ids = ["text_header_time"] + [
            f"text_header_{day}" for day in day_keys
        ]
        table_children_ids.extend(header_cell_ids)

        # 添加表头 cell 与 text 块
        # 时间列表头
        descendants.append(
            document_manager.create_table_cell_block(
                block_id=header_cell_ids[0], children=[header_text_ids[0]]
            )
        )
        descendants.append(
            document_manager.create_text_block(
                block_id=header_text_ids[0], text="时间", align=2
            )
        )
        # 星期列表头
        for idx, day in enumerate(day_keys, start=1):
            descendants.append(
                document_manager.create_table_cell_block(
                    block_id=header_cell_ids[idx], children=[header_text_ids[idx]]
                )
            )
            descendants.append(
                document_manager.create_text_block(
                    block_id=header_text_ids[idx], text=day_label_map[day], align=2
                )
            )

        # 数据行 cell 与文本
        for time_label in time_labels:
            # 使用小时作为 id 片段，如 "00"、"02"、"12" 等
            row_cell_ids = [f"cell_{time_label}"] + [
                f"cell_{time_label}_{day}" for day in day_keys
            ]
            row_text_ids = [f"text_{time_label}"] + [
                f"text_{time_label}_{day}" for day in day_keys
            ]
            table_children_ids.extend(row_cell_ids)

            # 时间列单元格
            descendants.append(
                document_manager.create_table_cell_block(
                    block_id=row_cell_ids[0], children=[row_text_ids[0]]
                )
            )
            descendants.append(
                document_manager.create_text_block(
                    block_id=row_text_ids[0], text=time_label, align=2
                )
            )

            # 每天列单元格
            for col_index, day in enumerate(day_keys, start=1):
                # 取对应槽位数据
                slot_info: Dict[str, Any] = days_data.get(day, {}).get(time_label, {})
                slot_text: str = slot_info.get("text", "")
                slot_color = slot_info.get("color", None)
                background_color_id = (
                    slot_color.background_color_id
                    if hasattr(slot_color, "background_color_id")
                    else -1
                )

                descendants.append(
                    document_manager.create_table_cell_block(
                        block_id=row_cell_ids[col_index],
                        children=[row_text_ids[col_index]],
                    )
                )
                descendants.append(
                    document_manager.create_text_block(
                        block_id=row_text_ids[col_index],
                        text=slot_text,
                        background_color=background_color_id,
                        align=2,
                    )
                )

        # 表格块
        row_size = 1 + len(time_labels)
        column_size = 1 + len(day_keys)
        table_block = document_manager.create_table_block(
            row_size=row_size,
            column_size=column_size,
            block_id=table_block_id,
            children=table_children_ids,
            column_width=[70] + [110] * len(day_keys),
            header_row=True,
            header_column=True,
        )
        descendants.append(table_block)

        # 添加AI分析报告和重要报告和活动明细

        ai_analysis = weekly_data.get("ai_analysis", {})
        event_records = weekly_data.get("event_summary", [])
        # 如果为DataFrame，按需转换为records
        if hasattr(event_records, "to_dict"):
            event_records = event_records.to_dict(orient="records")
        category_stats = weekly_data.get("category_stats", [])

        # === AI分析报告 ===
        if ai_analysis:
            core_narrative = ai_analysis.get("core_narrative", {})
            ai_title = "AI分析报告"
            if core_narrative["theme"]:
                ai_title += f':{core_narrative["theme"]}'
            children.append("heading_ai_analysis")
            descendants.append(
                document_manager.create_formated_text_block(
                    block_id="heading_ai_analysis",
                    text=ai_title,
                    block_type="heading1",
                )
            )

            # 分析师前言
            if ai_analysis.get("analyst_foreword"):
                children.append("heading_analyst_foreword")
                descendants.append(
                    document_manager.create_formated_text_block(
                        block_id="heading_analyst_foreword",
                        text="分析师前言",
                        block_type="heading2",
                    )
                )
                children.append("text_analyst_foreword")
                descendants.append(
                    document_manager.create_text_block(
                        block_id="text_analyst_foreword",
                        text=ai_analysis["analyst_foreword"],
                    )
                )

            # 核心叙事
            if core_narrative:
                children.append("heading_core_narrative")
                descendants.append(
                    document_manager.create_formated_text_block(
                        block_id="heading_core_narrative",
                        text="核心叙事",
                        block_type="heading2",
                    )
                )

                if core_narrative.get("narrative_summary"):
                    children.append("heading_narrative_summary")
                    descendants.append(
                        document_manager.create_formated_text_block(
                            block_id="heading_narrative_summary",
                            text="叙事总结",
                            block_type="heading3",
                        )
                    )
                    children.append("text_narrative_summary")
                    descendants.append(
                        document_manager.create_text_block(
                            block_id="text_narrative_summary",
                            text=core_narrative["narrative_summary"],
                        )
                    )

                # 动态框架洞察
                dynamic_framework = core_narrative.get("dynamic_framework_insight", {})
                if (
                    dynamic_framework
                    and dynamic_framework.get("relevance_score", -1) > 6
                ):
                    children.append("heading_dynamic_framework")
                    descendants.append(
                        document_manager.create_formated_text_block(
                            block_id="heading_dynamic_framework",
                            text="动态框架洞察",
                            block_type="heading3",
                        )
                    )

                    framework_text = ""
                    if dynamic_framework.get("framework_name"):
                        framework_text += (
                            f"框架：{dynamic_framework['framework_name']}\n\n"
                        )
                    if dynamic_framework.get("insight"):
                        framework_text += dynamic_framework["insight"]

                    children.append("text_dynamic_framework")
                    descendants.append(
                        document_manager.create_text_block(
                            block_id="text_dynamic_framework", text=framework_text
                        )
                    )

            # 节律分析
            rhythm_analysis = ai_analysis.get("rhythm_analysis", {})
            if rhythm_analysis:
                children.append("heading_rhythm_analysis")
                descendants.append(
                    document_manager.create_formated_text_block(
                        block_id="heading_rhythm_analysis",
                        text="节律分析",
                        block_type="heading2",
                    )
                )

                # 已识别的节律
                identified_rhythms = rhythm_analysis.get("identified_rhythms", [])
                if identified_rhythms:
                    children.append("heading_identified_rhythms")
                    descendants.append(
                        document_manager.create_formated_text_block(
                            block_id="heading_identified_rhythms",
                            text="已知的节律",
                            block_type="heading3",
                        )
                    )
                    children.append("text_identified_rhythms")
                    descendants.append(
                        document_manager.create_text_block(
                            block_id="text_identified_rhythms",
                            text="\n".join(
                                [f"• {rhythm}" for rhythm in identified_rhythms]
                            ),
                        )
                    )

                # 潜在新节律
                potential_new_rhythms = rhythm_analysis.get("potential_new_rhythms", [])
                if potential_new_rhythms:
                    children.append("heading_potential_new_rhythms")
                    descendants.append(
                        document_manager.create_formated_text_block(
                            block_id="heading_potential_new_rhythms",
                            text="潜在节律",
                            block_type="heading3",
                        )
                    )
                    children.append("text_potential_new_rhythms")
                    descendants.append(
                        document_manager.create_text_block(
                            block_id="text_potential_new_rhythms",
                            text="\n".join(
                                [f"• {rhythm}" for rhythm in potential_new_rhythms]
                            ),
                        )
                    )

                # 预测
                if rhythm_analysis.get("prediction"):
                    children.append("heading_rhythm_prediction")
                    descendants.append(
                        document_manager.create_formated_text_block(
                            block_id="heading_rhythm_prediction",
                            text="节律预测",
                            block_type="heading3",
                        )
                    )
                    children.append("text_rhythm_prediction")
                    descendants.append(
                        document_manager.create_text_block(
                            block_id="text_rhythm_prediction",
                            text=rhythm_analysis["prediction"],
                        )
                    )

            # 隐藏数据洞察
            hidden_insights = ai_analysis.get("hidden_data_insights", [])
            if hidden_insights:
                children.append("heading_hidden_insights")
                descendants.append(
                    document_manager.create_formated_text_block(
                        block_id="heading_hidden_insights",
                        text="数据洞察",
                        block_type="heading2",
                    )
                )

                for i, insight in enumerate(hidden_insights):
                    if insight.get("title"):
                        children.append(f"heading_insight_{i}")
                        descendants.append(
                            document_manager.create_formated_text_block(
                                block_id=f"heading_insight_{i}",
                                text=insight["title"],
                                block_type="heading3",
                            )
                        )

                    if insight.get("finding"):
                        children.append(f"text_insight_{i}")
                        descendants.append(
                            document_manager.create_text_block(
                                block_id=f"text_insight_{i}", text=insight["finding"]
                            )
                        )

            # 过往行动回顾
            previous_actions = ai_analysis.get("previous_actions_review", {})
            if previous_actions:
                children.append("heading_previous_actions")
                descendants.append(
                    document_manager.create_formated_text_block(
                        block_id="heading_previous_actions",
                        text="上期建议回顾",
                        block_type="heading2",
                    )
                )

                # 反馈演化说明
                if previous_actions.get("feedback_evolution_note"):
                    children.append("heading_feedback_evolution")
                    descendants.append(
                        document_manager.create_formated_text_block(
                            block_id="heading_feedback_evolution",
                            text="你的变化",
                            block_type="heading3",
                        )
                    )
                    children.append("text_feedback_evolution")
                    descendants.append(
                        document_manager.create_text_block(
                            block_id="text_feedback_evolution",
                            text=previous_actions["feedback_evolution_note"],
                        )
                    )

                # 详细回顾
                detailed_review = previous_actions.get("detailed_review", [])
                if detailed_review:
                    children.append("heading_detailed_review")
                    descendants.append(
                        document_manager.create_formated_text_block(
                            block_id="heading_detailed_review",
                            text="详细建议回顾",
                            block_type="heading3",
                        )
                    )

                    for i, review in enumerate(detailed_review):
                        suggestion_id = review.get("suggestion_id", f"建议{i+1}")
                        user_choice = review.get("user_choice", False)
                        assessment = review.get("analyst_assessment", "")

                        children.append(f"heading_review_{i}")
                        descendants.append(
                            document_manager.create_formated_text_block(
                                block_id=f"heading_review_{i}",
                                text=f"{suggestion_id} (响应: {'采纳' if user_choice else '拒绝'})",
                                block_type="heading4",
                            )
                        )

                        if assessment:
                            children.append(f"text_review_{i}")
                            descendants.append(
                                document_manager.create_text_block(
                                    block_id=f"text_review_{i}", text=assessment
                                )
                            )

            # 战略性行动建议
            strategic_suggestions = ai_analysis.get("strategic_action_suggestions", [])
            if strategic_suggestions:
                children.append("heading_strategic_suggestions")
                descendants.append(
                    document_manager.create_formated_text_block(
                        block_id="heading_strategic_suggestions",
                        text="本周行动建议",
                        block_type="heading2",
                    )
                )

                for i, suggestion in enumerate(strategic_suggestions):
                    if suggestion.get("title"):
                        title_text = suggestion["title"]

                        children.append(f"heading_suggestion_{i}")
                        descendants.append(
                            document_manager.create_formated_text_block(
                                block_id=f"heading_suggestion_{i}",
                                text=title_text,
                                block_type="heading3",
                            )
                        )

                        suggestion_content = ""
                        if suggestion.get("reasoning"):
                            suggestion_content += f"理由：{suggestion['reasoning']}\n\n"

                        if suggestion.get("specific_action"):
                            suggestion_content += (
                                f"具体行动：{suggestion['specific_action']}\n\n"
                            )

                        if suggestion.get("execution_difficulty"):
                            suggestion_content += (
                                f"执行难度：{suggestion['execution_difficulty']}\n\n"
                            )

                        if suggestion.get("expected_outcome"):
                            suggestion_content += (
                                f"预期结果：{suggestion['expected_outcome']}\n\n"
                            )
                        if suggestion.get("minimum_action"):
                            suggestion_content += (
                                f"最小行动：{suggestion['minimum_action']}"
                            )

                        if suggestion_content:
                            children.append(f"text_suggestion_{i}")
                            descendants.append(
                                document_manager.create_text_block(
                                    block_id=f"text_suggestion_{i}",
                                    text=suggestion_content,
                                )
                            )

        # === 重要报告 ===
        children.append("heading_important_report")
        descendants.append(
            document_manager.create_formated_text_block(
                block_id="heading_important_report",
                text="重要报告",
                block_type="heading1",
            )
        )

        children.append("heading_important_report_interval")
        descendants.append(
            document_manager.create_formated_text_block(
                block_id="heading_important_report_interval",
                text="事件间隔",
                block_type="heading2",
            )
        )

        important_lines = []
        # 筛选有间隔且display_unit不为空的记录
        valid_records = []
        for record in event_records:
            if (
                record.get("event_interval_minutes")
                and not pd.isna(record.get("event_interval_minutes"))
                and record.get("display_unit")
            ):
                valid_records.append(record)

        # 按间隔从小到大排序
        sorted_records = sorted(
            valid_records, key=lambda x: x.get("event_interval_minutes", float("inf"))
        )

        # 去重：基于display_unit和event_interval_minutes
        seen = set()
        unique_records = []
        for record in sorted_records:
            key = (record["display_unit"], record["event_interval_minutes"])
            if key not in seen:
                seen.add(key)
                unique_records.append(record)

        # 生成显示文本
        for record in unique_records:
            display_unit = record["display_unit"]
            minutes = int(round(float(record["event_interval_minutes"])))
            interval_label = format_time_label(minutes)
            important_lines.append(
                f"{display_unit}间隔：{interval_label} | {minutes} 分钟"
            )

        children.append("text_important_overview")
        descendants.append(
            document_manager.create_text_block(
                block_id="text_important_overview", text="\n".join(important_lines)
            )
        )

        # === 活动数据分类明细 ===
        children.append("heading_category_details")
        descendants.append(
            document_manager.create_formated_text_block(
                block_id="heading_category_details",
                text="活动数据分类明细",
                block_type="heading1",
            )
        )

        # 分类排序：未记录最后，其他按总时长降序
        category_totals = {
            stat["category"]: stat["category_total_duration"] for stat in category_stats
        }
        sorted_categories = sorted(
            category_totals.keys(),
            key=lambda x: (1 if x == "未记录" else 0, -category_totals[x]),
        )

        # 按分类分组事件记录
        category_events = defaultdict(lambda: defaultdict(list))
        for record in event_records:
            category_events[record["category"]][record["event_name"]].append(record)

        def format_duration_stats(record):
            """格式化时长统计信息"""
            count = int(record["count"])
            force_new_line = False
            if count <= 1:
                return "", force_new_line

            avg = int(round(record["avg_duration"]))
            min_dur = int(round(record["min_duration"]))
            max_dur = int(round(record["max_duration"]))

            if avg == min_dur == max_dur or (min_dur != 0 and max_dur / min_dur < 1.2):
                return f"平均时长：{format_time_label(avg, 'hour')}", force_new_line

            force_new_line = True

            final_str = f"平均时长：{format_time_label(avg, 'hour')}｜最短：{format_time_label(min_dur, 'hour')}｜最长：{format_time_label(max_dur, 'hour')}"

            if max_dur > 30:
                max_start = str(record["max_duration_start_at"])[:16]
                week_day = day_label_map[
                    record["max_duration_start_at"].strftime("%a").lower()
                ]
                final_str += f"，{max_start} {week_day}"

            return final_str, force_new_line

        # 生成各分类内容
        for category in sorted_categories:
            # 分类标题
            children.extend([f"heading_cat_{category}", f"text_cat_{category}"])
            descendants.extend(
                [
                    document_manager.create_formated_text_block(
                        block_id=f"heading_cat_{category}",
                        text=f"📜 {category if category else '无分类'}",
                        block_type="heading2",
                    ),
                    document_manager.create_text_block(
                        block_id=f"text_cat_{category}",
                        text=f"总时长：{format_time_label(category_totals[category], 'hour')}",
                    ),
                ]
            )

            # 该分类下的事件，按事件总时长排序
            events = category_events[category]
            sorted_events = sorted(
                events.items(),
                key=lambda x: x[1][0].get("event_total_duration", 0),
                reverse=True,
            )

            for event_name, records in sorted_events:
                # 事件标题
                children.extend(
                    [
                        f"heading_ev_{category}_{event_name}",
                        f"text_ev_{category}_{event_name}",
                    ]
                )
                descendants.append(
                    document_manager.create_formated_text_block(
                        block_id=f"heading_ev_{category}_{event_name}",
                        text=event_name,
                        block_type="heading3",
                    )
                )

                # 事件基本信息
                first_record = records[0]
                info_parts = [
                    f"总时长：{format_time_label(first_record['event_total_duration'], 'hour')}",
                    f"事件次数：{int(first_record['event_total_count'])}",
                ]

                # 添加分类间隔信息（如果有）
                if first_record.get("category_interval_minutes") and not pd.isna(
                    first_record.get("category_interval_minutes")
                ):
                    minutes = first_record["category_interval_minutes"]
                    interval_label = format_time_label(minutes)
                    info_parts.append(f"事件间隔：{interval_label}")

                # 检查是否有完成方式记录
                degree_records = [r for r in records if r.get("degree")]
                no_degree_records = [r for r in records if not r.get("degree")]

                final_str = " ｜ ".join(info_parts)

                # 如果没有完成方式记录，在事件级显示统计
                if not degree_records and no_degree_records:
                    extra_str, force_new_line = format_duration_stats(
                        no_degree_records[0]
                    )
                    if extra_str:
                        if force_new_line or len(info_parts) > 2:
                            final_str += "\n"
                        final_str += extra_str

                descendants.append(
                    document_manager.create_text_block(
                        block_id=f"text_ev_{category}_{event_name}", text=final_str
                    )
                )

                # 处理完成方式记录
                if degree_records:
                    # 创建完成方式引用容器的children列表
                    degree_children = []

                    for record in sorted(
                        degree_records,
                        key=lambda x: x.get("total_duration", 0),
                        reverse=True,
                    ):
                        degree = record.get("degree", "未分级")
                        degree_children.extend(
                            [
                                f"heading_deg_{category}_{event_name}_{degree}",
                                f"text_deg_{category}_{event_name}_{degree}",
                            ]
                        )

                        descendants.append(
                            document_manager.create_formated_text_block(
                                block_id=f"heading_deg_{category}_{event_name}_{degree}",
                                text=degree,
                                block_type="heading4",
                            )
                        )

                        # 完成方式统计信息
                        parts = [
                            f"总时长：{format_time_label(record['total_duration'], 'hour')}",
                            f"次数：{int(record['count'])}",
                        ]
                        if record.get("degree_interval_minutes") and not pd.isna(
                            record.get("degree_interval_minutes")
                        ):
                            interval_minutes = int(
                                round(float(record["degree_interval_minutes"]))
                            )
                            interval_label = format_time_label(interval_minutes)
                            parts.append(
                                f"间隔时间：{interval_label} ({interval_minutes} 分钟)"
                            )

                        degree_str = " ｜ ".join(parts)
                        extra_str, force_new_line = format_duration_stats(record)
                        if extra_str:
                            if force_new_line or len(parts) > 2:
                                degree_str += "\n"
                            degree_str += extra_str

                        descendants.append(
                            document_manager.create_text_block(
                                block_id=f"text_deg_{category}_{event_name}_{degree}",
                                text=degree_str,
                            )
                        )

                    # 创建完成方式引用容器
                    quote_block_id = f"quote_deg_{category}_{event_name}"
                    children.append(quote_block_id)
                    descendants.append(
                        document_manager.create_quote_block(
                            block_id=quote_block_id, children=degree_children
                        )
                    )

        # 组合顶层内容
        content = document_manager.create_descendant_block_body(
            index=0, children=children, descendants=descendants
        )
        return content

    # endregion

    # region 历史-报告卡片

    def generate_weekly_card_content(self, weekly_table_data: Dict[str, Any]) -> str:
        """生成周报告卡片内容"""
        elements = []
        elements.append(JsonBuilder.build_markdown_element("上周时间表"))
        columns = []
        columns.append(
            JsonBuilder.build_table_column_element(
                name="time",
                display_name="时间",
                data_type="text",
                width="80px",
            )
        )
        day_dict = {
            "mon": "周一",
            "tue": "周二",
            "wed": "周三",
            "thu": "周四",
            "fri": "周五",
            "sat": "周六",
            "sun": "周日",
        }
        for day_key, day_name in day_dict.items():
            columns.append(
                JsonBuilder.build_table_column_element(
                    name=day_key,
                    display_name=day_name,
                    data_type="options",
                    width="120px",
                )
            )
        table_element = JsonBuilder.build_table_element(
            columns=columns,
            rows=[],
            freeze_first_column=True,
        )

        time_labels = weekly_table_data.get("time_labels", [])
        days_data = weekly_table_data.get("days", {})
        default_slot_data = {
            "text": "空闲",
            "color": ColorTypes.GREY,
            "category_label": "空闲",
        }

        for time_label in time_labels:
            row = {"time": time_label}

            for day_key in day_dict:
                day_data = days_data.get(day_key, {})
                slot_data = day_data.get(time_label, default_slot_data)

                row[day_key] = [
                    {
                        "text": slot_data.get("text", default_slot_data.get("text")),
                        "color": slot_data.get(
                            "color", default_slot_data.get("color")
                        ).option_value,
                    }
                ]

            table_element["rows"].append(row)

        elements.append(table_element)
        return elements

    # endregion
