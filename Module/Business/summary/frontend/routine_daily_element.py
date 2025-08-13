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

        # 添加个性印章图片元素
        if image_key:
            elements.append(self._build_image_element(image_key, main_color))

        # 添加周报数据元素
        if weekly_data:
            elements.extend(
                self._build_weekly_elements(weekly_data, user_id, routine_data)
            )

        return elements

    def _build_image_element(
        self, image_key: str, main_color: Dict[str, Any]
    ) -> Dict[str, Any]:
        """构建个性印章图片元素"""
        return JsonBuilder.build_image_element(
            image_key=image_key,
            alt=f"昨天你的{main_color.get('max_weight_category', '')}印章",
            title="昨日个性印章",
            corner_radius="5px",
            scale_type="crop_center",
            size="80px 90px",
        )

    def _build_weekly_elements(
        self, weekly_data: Dict[str, Any], user_id: str, routine_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """构建周报相关元素"""
        elements = []

        # 添加饼图元素
        pie_element = self._build_pie_chart_element(weekly_data)
        if pie_element:
            elements.append(pie_element)

        # 创建文档并添加相关元素
        document_elements = self._create_weekly_document(
            weekly_data, user_id, routine_data
        )
        elements.extend(document_elements)

        return elements

    # endregion

    # region 周报元素

    def _build_pie_chart_element(
        self, weekly_data: Dict[str, Any]
    ) -> Dict[str, Any] | None:
        """构建饼图元素"""
        pie_raw_data = weekly_data.get("category_stats", [])
        if not pie_raw_data:
            return None

        pie_data = []
        color_mapping = {}
        for item in pie_raw_data:
            type_name = item.get("category", "") or "无分类"
            color = item.get("color", "#959BEE")

            pie_data.append(
                {
                    "type": type_name,
                    "value": round(item.get("category_total_duration", 0) / 60, 1),
                }
            )
            color_mapping[type_name] = color

        return JsonBuilder.build_chart_element(
            chart_type="pie",
            title="上周时间统计",
            data=pie_data,
            color_mapping=color_mapping,
            formatter="{type}: {value}小时,{_percent_}%",
        )

    def _create_weekly_document(
        self, weekly_data: Dict[str, Any], user_id: str, routine_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """创建周报文档并返回相关元素"""
        elements = []

        # 获取或创建文件夹tokens
        weekly_record = self.routine_business.load_weekly_record(user_id)
        document_manager = self.app_controller.get_adapter(
            AdapterNames.FEISHU
        ).cloud_manager

        folder_tokens = self._ensure_folder_tokens(
            weekly_record, user_id, document_manager
        )
        if folder_tokens["need_update"]:
            self.routine_business.save_weekly_record(user_id, weekly_record)

        # 创建文档
        document_id = self._create_document(
            weekly_data, folder_tokens["business"], document_manager
        )
        if document_id:
            elements.extend(
                self._build_document_elements(
                    document_id,
                    folder_tokens["business"],
                    weekly_data,
                    routine_data,
                    document_manager,
                )
            )
        else:
            debug_utils.log_and_print("创建周报告文档失败", log_level="ERROR")

        return elements

    def _ensure_folder_tokens(
        self, weekly_record: Dict[str, Any], user_id: str, document_manager
    ) -> Dict[str, Any]:
        """确保文件夹tokens存在"""
        root_folder_token = weekly_record.get("root_folder_token", "")
        business_folder_token = weekly_record.get("business_folder_token", {}).get(
            "周报告", ""
        )
        need_update = False

        if not root_folder_token:
            root_folder_token = document_manager.get_user_root_folder_token(user_id)
            weekly_record["root_folder_token"] = root_folder_token
            need_update = True

        if not business_folder_token:
            business_folder_token = document_manager.get_user_business_folder_token(
                user_id, "周报告", root_folder_token
            )
            weekly_record["business_folder_token"]["周报告"] = business_folder_token
            need_update = True

        return {
            "root": root_folder_token,
            "business": business_folder_token,
            "need_update": need_update,
        }

    def _create_document(
        self, weekly_data: Dict[str, Any], business_folder_token: str, document_manager
    ) -> str | None:
        """创建周报文档"""
        title = weekly_data.get("document_title", "")
        doc_data = document_manager.create_document(
            folder_token=business_folder_token,
            document_title=title,
        )
        return (
            getattr(getattr(doc_data, "document", None), "document_id", None)
            if doc_data
            else None
        )

    # endregion

    # region 文档元素

    def _build_document_elements(
        self,
        document_id: str,
        business_folder_token: str,
        weekly_data: Dict[str, Any],
        routine_data: Dict[str, Any],
        document_manager,
    ) -> List[Dict[str, Any]]:
        """构建文档相关元素"""
        elements = []
        title = weekly_data.get("document_title", "")

        # 写入文档内容
        content = self.generate_weekly_document_content(routine_data)
        document_manager.create_document_block_descendant(
            document_id=document_id,
            block_data=content,
            document_title=title,
        )

        # 添加文档链接
        elements.append(
            self._build_document_link_element(document_id, business_folder_token, title)
        )

        # 添加行动建议元素
        action_elements = self._build_action_suggestion_elements(weekly_data)
        elements.extend(action_elements)

        return elements

    def _build_document_link_element(
        self, document_id: str, business_folder_token: str, title: str
    ) -> Dict[str, Any]:
        """构建文档链接元素"""
        url = f"https://ddsz-peng13.feishu.cn/docx/{document_id}"
        folder_url = (
            f"https://ddsz-peng13.feishu.cn/drive/folder/{business_folder_token}"
        )
        content = f"[查看分析：{title}]({url})\n[访问报告文件夹]({folder_url})"
        return JsonBuilder.build_markdown_element(content=content)

    def _build_action_suggestion_elements(
        self, weekly_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """构建行动建议元素"""
        elements = []
        action_suggestions_data = weekly_data.get("ai_analysis", {}).get(
            "strategic_action_suggestions", []
        )

        if not action_suggestions_data:
            return elements

        # 添加标题
        elements.append(
            JsonBuilder.build_markdown_element(content=":MeMeMe: **本周行动建议**")
        )

        # 添加每个建议
        for action in action_suggestions_data:
            elements.extend(self._build_single_action_elements(action))

        return elements

    def _build_single_action_elements(
        self, action: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """构建单个行动建议元素"""
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

        return [checker_element, markdown_element]

    # endregion

    # region 周报告文档

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
        children.extend([heading_block_id, table_block_id])

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

        # 构建表格内容
        table_children_ids = self._build_table_content(
            time_labels,
            days_data,
            day_keys,
            day_label_map,
            descendants,
            document_manager,
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

        # 构建AI分析报告部分
        self._build_ai_analysis_section(
            weekly_data, children, descendants, document_manager
        )

        # 构建重要报告部分
        self._build_important_report_section(
            weekly_data, children, descendants, document_manager
        )

        # 构建活动数据分类明细部分
        self._build_category_details_section(
            weekly_data, children, descendants, document_manager
        )

        # 组合顶层内容
        content = document_manager.create_descendant_block_body(
            index=0, children=children, descendants=descendants
        )
        return content

    # endregion

    # region 文档内表格

    def _build_table_content(
        self,
        time_labels: List[str],
        days_data: Dict[str, Any],
        day_keys: List[str],
        day_label_map: Dict[str, str],
        descendants: List[Dict],
        document_manager,
    ) -> List[str]:
        """构建表格内容"""
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
            document_manager.create_formated_text_block(
                block_id=header_text_ids[0], text="时间", block_type="text", align=2
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
                document_manager.create_formated_text_block(
                    block_id=header_text_ids[idx],
                    text=day_label_map[day],
                    block_type="text",
                    align=2,
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
                document_manager.create_formated_text_block(
                    block_id=row_text_ids[0],
                    text=time_label,
                    block_type="text",
                    align=2,
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
                    document_manager.create_formated_text_block(
                        block_id=row_text_ids[col_index],
                        text=slot_text,
                        block_type="text",
                        background_color=background_color_id,
                        align=2,
                    )
                )

        return table_children_ids

    # endregion

    # region 文档内AI分析

    def _build_ai_analysis_section(
        self,
        weekly_data: Dict[str, Any],
        children: List[str],
        descendants: List[Dict],
        document_manager,
    ) -> None:
        """构建AI分析报告部分"""
        ai_analysis = weekly_data.get("ai_analysis", {})
        core_narrative = ai_analysis.get("core_narrative", {})

        if not ai_analysis:
            return

        children.append("heading_ai_analysis")
        descendants.append(
            document_manager.create_formated_text_block(
                block_id="heading_ai_analysis",
                text="AI 分析报告",
                block_type="heading1",
            )
        )

        # 分析师前言
        self._build_analyst_foreword(
            ai_analysis, children, descendants, document_manager
        )

        # 核心叙事
        self._build_core_narrative(
            core_narrative, children, descendants, document_manager
        )

        # 节律分析
        self._build_rhythm_analysis(
            ai_analysis, children, descendants, document_manager
        )

        # 隐藏数据洞察
        self._build_hidden_insights(
            ai_analysis, children, descendants, document_manager
        )

        # 过往行动回顾
        self._build_previous_actions_review(
            ai_analysis, children, descendants, document_manager
        )

        # 战略性行动建议
        self._build_strategic_suggestions(
            ai_analysis, children, descendants, document_manager
        )

    def _build_analyst_foreword(
        self,
        ai_analysis: Dict[str, Any],
        children: List[str],
        descendants: List[Dict],
        document_manager,
    ) -> None:
        """构建分析师前言部分"""
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
                document_manager.create_formated_text_block(
                    block_id="text_analyst_foreword",
                    text=ai_analysis["analyst_foreword"],
                    block_type="text",
                )
            )

    def _build_core_narrative(
        self,
        core_narrative: Dict[str, Any],
        children: List[str],
        descendants: List[Dict],
        document_manager,
    ) -> None:
        """构建核心叙事部分"""
        if not core_narrative:
            return

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
                document_manager.create_formated_text_block(
                    block_id="text_narrative_summary",
                    text=core_narrative["narrative_summary"],
                    block_type="text",
                )
            )

        # 动态框架洞察
        self._build_dynamic_framework(
            core_narrative, children, descendants, document_manager
        )

    def _build_dynamic_framework(
        self,
        core_narrative: Dict[str, Any],
        children: List[str],
        descendants: List[Dict],
        document_manager,
    ) -> None:
        """构建动态框架洞察部分"""
        dynamic_framework = core_narrative.get("dynamic_framework_insight", {})
        if dynamic_framework and dynamic_framework.get("relevance_score", -1) > 6:
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
                framework_text += f"框架：{dynamic_framework['framework_name']}\n\n"
            if dynamic_framework.get("insight"):
                framework_text += dynamic_framework["insight"]

            children.append("text_dynamic_framework")
            descendants.append(
                document_manager.create_formated_text_block(
                    block_id="text_dynamic_framework",
                    text=framework_text,
                    block_type="text",
                )
            )

    def _build_rhythm_analysis(
        self,
        ai_analysis: Dict[str, Any],
        children: List[str],
        descendants: List[Dict],
        document_manager,
    ) -> None:
        """构建节律分析部分"""
        rhythm_analysis = ai_analysis.get("rhythm_analysis", {})
        if not rhythm_analysis:
            return

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
                document_manager.create_formated_text_block(
                    block_id="text_identified_rhythms",
                    text="\n".join([f"• {rhythm}" for rhythm in identified_rhythms]),
                    block_type="text",
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
                document_manager.create_formated_text_block(
                    block_id="text_potential_new_rhythms",
                    text="\n".join([f"• {rhythm}" for rhythm in potential_new_rhythms]),
                    block_type="text",
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
                document_manager.create_formated_text_block(
                    block_id="text_rhythm_prediction",
                    text=rhythm_analysis["prediction"],
                    block_type="text",
                )
            )

    def _build_hidden_insights(
        self,
        ai_analysis: Dict[str, Any],
        children: List[str],
        descendants: List[Dict],
        document_manager,
    ) -> None:
        """构建隐藏数据洞察部分"""
        hidden_insights = ai_analysis.get("hidden_data_insights", [])
        if not hidden_insights:
            return

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
                    document_manager.create_formated_text_block(
                        block_id=f"text_insight_{i}",
                        text=insight["finding"],
                        block_type="text",
                    )
                )

    def _build_previous_actions_review(
        self,
        ai_analysis: Dict[str, Any],
        children: List[str],
        descendants: List[Dict],
        document_manager,
    ) -> None:
        """构建过往行动回顾部分"""
        previous_actions = ai_analysis.get("previous_actions_review", {})
        if not previous_actions:
            return

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
                document_manager.create_formated_text_block(
                    block_id="text_feedback_evolution",
                    text=previous_actions["feedback_evolution_note"],
                    block_type="text",
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
                        document_manager.create_formated_text_block(
                            block_id=f"text_review_{i}",
                            text=assessment,
                            block_type="text",
                        )
                    )

    def _build_strategic_suggestions(
        self,
        ai_analysis: Dict[str, Any],
        children: List[str],
        descendants: List[Dict],
        document_manager,
    ) -> None:
        """构建本周行动建议部分"""
        strategic_suggestions = ai_analysis.get("strategic_action_suggestions", [])
        if not strategic_suggestions:
            return

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
                children.append(f"heading_suggestion_{i}")
                descendants.append(
                    document_manager.create_formated_text_block(
                        block_id=f"heading_suggestion_{i}",
                        text=suggestion["title"],
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
                    suggestion_content += f"最小行动：{suggestion['minimum_action']}"

                if suggestion_content:
                    children.append(f"text_suggestion_{i}")
                    descendants.append(
                        document_manager.create_formated_text_block(
                            block_id=f"text_suggestion_{i}",
                            text=suggestion_content,
                            block_type="text",
                        )
                    )

    # endregion

    # region 周期间隔分析

    def _build_important_report_section(
        self,
        weekly_data: Dict[str, Any],
        children: List[str],
        descendants: List[Dict],
        document_manager,
    ) -> None:
        """构建重要报告部分"""
        event_records = weekly_data.get("event_summary", [])

        # 如果为DataFrame，按需转换为records
        if hasattr(event_records, "to_dict"):
            event_records = event_records.to_dict(orient="records")

        # 生成间隔报告
        important_lines = self._generate_event_interval_lines(event_records)

        if not important_lines:
            return

        children.append("heading_important_overview")
        descendants.append(
            document_manager.create_formated_text_block(
                block_id="heading_important_overview",
                text="重要概览",
                block_type="heading1",
            )
        )

        children.append("text_important_overview")
        descendants.append(
            document_manager.create_formated_text_block(
                block_id="text_important_overview",
                text="\n".join(important_lines),
                block_type="text",
            )
        )

    def _generate_event_interval_lines(self, event_records: List[Dict]) -> List[str]:
        """生成事件间隔报告行"""
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

        return important_lines

    def _build_category_details_section(
        self,
        weekly_data: Dict[str, Any],
        children: List[str],
        descendants: List[Dict],
        document_manager,
    ) -> None:
        """构建活动数据分类明细部分"""
        event_records = weekly_data.get("event_summary", [])
        category_stats = weekly_data.get("category_stats", [])

        # 如果为DataFrame，按需转换为records
        if hasattr(event_records, "to_dict"):
            event_records = event_records.to_dict(orient="records")

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

            final_str = (
                f"平均时长：{format_time_label(avg, 'hour')}｜最短："
                f"{format_time_label(min_dur, 'hour')}｜最长：{format_time_label(max_dur, 'hour')}"
            )

            if max_dur > 30:
                max_start = str(record["max_duration_start_at"])[:16]
                day_labels = {
                    "mon": "周一",
                    "tue": "周二",
                    "wed": "周三",
                    "thu": "周四",
                    "fri": "周五",
                    "sat": "周六",
                    "sun": "周日",
                }
                week_day = day_labels[
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
                    document_manager.create_formated_text_block(
                        block_id=f"text_cat_{category}",
                        text=f"总时长：{format_time_label(category_totals[category], 'hour')}",
                        block_type="text",
                    ),
                ]
            )

            # 生成该分类下的事件列表
            event_items = category_events[category]
            sorted_events = sorted(
                event_items.items(),
                key=lambda x: x[1][0].get("event_total_duration", 0),
                reverse=True,
            )
            for event_name, records in sorted_events:
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
                    document_manager.create_formated_text_block(
                        block_id=f"text_ev_{category}_{event_name}",
                        text=final_str,
                        block_type="text",
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
                            document_manager.create_formated_text_block(
                                block_id=f"text_deg_{category}_{event_name}_{degree}",
                                text=degree_str,
                                block_type="text",
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
