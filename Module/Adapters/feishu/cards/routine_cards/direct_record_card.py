# -*- coding: utf-8 -*-
"""
Direct Record Card
直接记录卡片
"""

import json
import copy
from typing import Dict, Any, List
from Module.Adapters.feishu.utils import safe_float
from Module.Services.constants import (
    RoutineTypes,
    RoutineProgressTypes,
    RoutineReminderModes,
    ToastTypes,
    CardConfigKeys,
    CardOperationTypes,
    RoutineCheckCycle,
)
from Module.Business.processors.base_processor import (
    MessageContext_Refactor,
    ProcessResult,
)


class DirectRecordCard:
    """
    直接记录卡片管理器
    支持在没有事件定义的情况下直接创建记录
    """

    def __init__(self, parent_manager):
        self.parent = parent_manager  # 访问主管理器的共享方法和属性
        self.default_update_build_method = (
            "update_direct_record_card"  # 默认更新构建方法
        )

    def build_direct_record_card(self, business_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        直接记录卡片核心构建逻辑
        只负责构建 header 和卡片结构，其他逻辑移到 elements 中
        """
        # 构建卡片头部
        header = self._build_direct_record_header(business_data)

        # 构建卡片元素
        elements = self.build_direct_record_elements(business_data)

        return self.parent.build_base_card_structure(elements, header, "12px")

    def _build_direct_record_header(
        self, business_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        构建直接记录卡片头部
        """
        is_confirmed = business_data.get("is_confirmed", False)
        event_name = business_data.get("event_name", "")
        result = business_data.get("result", "取消")

        if is_confirmed:
            return self.parent.build_status_based_header("", is_confirmed, result)

        if event_name:
            return self.parent.build_card_header(
                f"直接记录：{event_name}", "填写记录信息", "blue", "edit_outlined"
            )

        return self.parent.build_card_header(
            "直接记录", "创建新的记录", "blue", "add_outlined"
        )

    def build_direct_record_elements(self, business_data: Dict[str, Any]) -> List[Dict]:
        """
        构建直接记录元素
        符合 sub_business_build_method 调用规范
        直接处理所有业务逻辑和数据传递
        """
        # 获取基础数据（从根级business_data获取，与record_card保持一致）
        build_method_name = business_data.get(
            "container_build_method", self.default_update_build_method
        )
        is_confirmed = business_data.get("is_confirmed", False)

        # 使用 safe_get_business_data 处理递归嵌套的业务数据结构
        data_source, _ = self.parent.safe_get_business_data(
            business_data, "routine_direct_record"
        )

        # 从统一数据结构中提取所需参数
        record_data = data_source.get("record_data", {})

        # 从统一结构中提取数据
        event_type = record_data.get("event_type", "")

        elements = []

        # 1. 计算信息区域（包含基础信息、时间预估、循环进度等）
        elements.extend(self._build_computed_info_by_type(data_source))

        # 2. 表单外字段区域（非表单数据，有回调事件，状态保存在配置中）
        elements.extend(
            self._build_non_form_fields(
                data_source, event_type, is_confirmed, build_method_name
            )
        )
        # 3. 表单分隔线
        elements.append(
            {
                "tag": "markdown",
                "content": "**💡 重要提示** 请先完成上面的设定，这会清除下面的所有值！",
            }
        )
        # 4. 表单内字段区域（表单数据，通过提交按钮回调一次性处理）
        form_container = self._build_form_fields_by_type(
            event_type, data_source, is_confirmed
        )
        # 5. 提交按钮
        form_container["elements"].append(
            self._build_submit_button(is_confirmed, build_method_name)
        )
        elements.append(form_container)

        # 6. 子业务元素（处理集成模式）
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

    # region 辅助信息区域
    def _build_computed_info_by_type(
        self, data_source: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        构建计算信息区域（包含基础信息、时间预估、循环进度等）
        """
        elements = []

        # 基础信息显示区域
        record_data = data_source.get("record_data", {})
        computed_data = data_source.get("computed_data", {})

        event_name = record_data.get("event_name", "")
        if event_name or record_data.get("create_time"):
            diff_minutes = computed_data.get("diff_minutes", 0)
            elements.extend(
                self._build_basic_info_section(data_source, event_name, diff_minutes)
            )

        # 时间预估和进度信息
        avg_duration = computed_data.get("avg_duration", 0)
        progress_type = record_data.get("progress_type", "")
        last_progress_value = computed_data.get("last_progress_value", 0)
        total_progress_value = computed_data.get("total_progress_value", 0)

        if avg_duration > 0 or (
            progress_type and (last_progress_value or total_progress_value)
        ):
            elements.extend(
                self._build_duration_and_progress_section(
                    avg_duration,
                    progress_type,
                    last_progress_value,
                    total_progress_value,
                )
            )

        # 循环进度信息（如果有目标设置）
        cycle_info = computed_data.get("cycle_info", {})
        if cycle_info:
            elements.extend(self._build_cycle_progress_section(cycle_info))

        return elements

    def _build_basic_info_section(
        self, data_source: Dict[str, Any], event_name: Dict[str, Any], diff_minutes: int
    ) -> List[Dict[str, Any]]:
        """
        构建基础信息区域
        """
        elements = []
        record_mode = data_source.get("record_mode", "")
        record_data = data_source.get("record_data", {})
        event_definition = data_source.get("event_definition", {})

        # 基础信息卡片
        event_type = event_definition.get("type", RoutineTypes.INSTANT)
        if record_mode == "direct":
            info_content = f"**事件名称： {event_name}**\n"

        else:
            info_content = (
                f"**事项类型：** {self.parent.get_type_display_name(event_type)}\n"
            )

        # 显示时间信息（严格四字段模式）
        time_field = None
        time_label = ""

        if event_type == RoutineTypes.FUTURE:
            # 未来事项显示预计开始时间
            time_field = record_data.get("scheduled_start_time")
            time_label = "预计开始时间"
        else:
            # 其他事项显示开始时间
            time_field = record_data.get("create_time")
            if event_type == RoutineTypes.INSTANT:
                time_label = "记录时间"
            else:
                time_label = "开始时间"

        if time_field:
            split_timestamp = time_field.split(" ")
            date_str = split_timestamp[0][5:10]
            time_str = split_timestamp[1][0:5]
            info_content += f"**{time_label}：** {date_str} {time_str}\n"
            if diff_minutes > 0 and event_type != RoutineTypes.FUTURE:
                info_content += f"**上次记录距今：** {diff_minutes}分钟\n"

        # 显示分类（如果有）
        category = event_definition.get("category", "")
        if category:
            info_content += f"**分类：** <text_tag color='blue'>{category}</text_tag>\n"

        if info_content:
            elements.append(
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": info_content.rstrip("\n")},
                }
            )

        return elements

    def _build_duration_and_progress_section(
        self,
        avg_duration: float,
        progress_type: str,
        last_progress_value: float,
        total_progress_value: float,
    ) -> List[Dict[str, Any]]:
        """构建时间预估和进度信息区域（合并到一个组件中）"""
        elements = []
        content_parts = []

        # 格式化时长显示，更加用户友好
        if avg_duration > 0:
            if avg_duration >= 1440:  # 超过24小时
                duration_str = f"{avg_duration/1440:.1f}天"
            elif avg_duration >= 60:  # 超过1小时
                hours = int(avg_duration // 60)
                minutes = int(avg_duration % 60)
                if minutes > 0:
                    duration_str = f"{hours}小时{minutes}分钟"
                else:
                    duration_str = f"{hours}小时"
            elif avg_duration >= 1:  # 1分钟以上
                duration_str = f"{avg_duration:.0f}分钟"
            else:  # 小于1分钟
                duration_str = f"{avg_duration*60:.0f}秒"

            content_parts.append(f"⏱️ **预估用时：** {duration_str}")

        # 格式化进度信息
        if progress_type and last_progress_value:
            match progress_type:
                case RoutineProgressTypes.VALUE:
                    progress_str = f"{round(last_progress_value, 1)}"
                case RoutineProgressTypes.MODIFY:
                    if last_progress_value > 0:
                        progress_str = f"增加 {round(last_progress_value, 1)}，累计 {round(total_progress_value, 1)}"
                    elif last_progress_value < 0:
                        progress_str = f"减少 {round(last_progress_value, 1)}，累计 {round(total_progress_value, 1)}"
                    else:
                        progress_str = f"累计 {round(total_progress_value, 1)}"
                case _:
                    progress_str = f"{round(last_progress_value, 1)}"

            content_parts.append(f"🎯 **上次指标情况：** {progress_str}")

        # 合并内容，用换行符分隔
        if content_parts:
            combined_content = "\n".join(content_parts)
            elements.append(
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": combined_content},
                    "element_id": "extra_info",
                }
            )

        return elements

    def _build_cycle_progress_section(
        self, cycle_info: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """构建循环进度信息区域"""
        elements = []

        # 基础数据提取
        cycle_count = max(0, int(cycle_info.get("cycle_count", 0)))
        target_type = cycle_info.get("target_type", "")
        target_value = cycle_info.get("target_value")
        last_cycle_info = cycle_info.get("last_cycle_info", "")

        # 判断是否有目标
        has_target = target_value and int(target_value) > 0

        # 构建主要进度内容
        progress_content_parts = []

        if has_target:
            # 有目标：显示目标进度
            target_val = max(1, int(target_value))
            progress_percent = min(100, (cycle_count / target_val * 100))
            target_type_display = {
                "count": "次数",
                "duration": "时长",
                "other": "其他",
            }.get(target_type, target_type)

            # 选择颜色和emoji
            if progress_percent >= 100:
                status_emoji = "🎉"
                color = "green"
            elif progress_percent >= 80:
                status_emoji = "🔥"
                color = "green"
            elif progress_percent >= 50:
                status_emoji = "💪"
                color = "orange"
            else:
                status_emoji = "📈"
                color = "red"

            progress_content_parts.append(
                f"🎯 **{target_type_display}目标：** {cycle_count}/{target_val}"
            )

            # 进度条
            filled_blocks = int(progress_percent // 10)
            progress_bar = "●" * filled_blocks + "○" * (10 - filled_blocks)
            real_progress_percent = round(cycle_count / target_val * 100, 1)
            progress_content_parts.append(
                f"📊 <font color={color}>{progress_bar}</font> {real_progress_percent}% {status_emoji}"
            )
        else:
            # 无目标：显示累计进度
            unit_display = {"count": "次", "duration": "分钟", "other": ""}.get(
                target_type, ""
            )
            progress_content_parts.append(
                f"📊 **累计进度：** {cycle_count}{unit_display}"
            )

        # 组装最终内容
        progress_content = "\n".join(progress_content_parts)
        if last_cycle_info and last_cycle_info.strip():
            progress_content += f"\n📈 {last_cycle_info}"

        elements.append(
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": progress_content},
            }
        )

        return elements

    # endregion

    # region 表单外字段区域

    def _build_non_form_fields(
        self,
        data_source: Dict,
        event_type: str,
        is_confirmed: bool,
        build_method_name: str,
    ) -> List[Dict]:
        """
        构建表单外字段（非表单数据，有回调事件，状态保存在配置中）

        表单外字段特点：
        1. 不在表单内，不通过提交按钮处理
        2. 有独立的回调事件处理
        3. 状态保存在配置管理器中
        4. 会影响表单内字段的显示
        """
        elements = []

        computed_data = data_source.get("computed_data", {})
        record_mode = data_source.get("record_mode", "")
        record_data = data_source.get("record_data", {})
        if record_mode == "direct":
            # 事件类型选择器（不在表单，有回调事件）
            elements.append(
                self.parent.build_form_row(
                    "事件类型",
                    self._build_event_type_selector(
                        event_type, is_confirmed, build_method_name
                    ),
                    width_list=["80px", "180px"],
                )
            )
        # 程度选择器（如果有程度选项）
        degree_info = computed_data.get("degree_info", {})
        if degree_info:
            elements.extend(
                self._build_degree_selection_section(
                    degree_info, record_data, is_confirmed, build_method_name
                )
            )

        # 指标类型选择器（不在表单，有回调事件）
        if event_type != RoutineTypes.FUTURE:
            progress_type = record_data.get("progress_type", RoutineProgressTypes.NONE)
            elements.append(
                self.parent.build_form_row(
                    "指标类型",
                    self._build_progress_type_selector(
                        progress_type, is_confirmed, build_method_name
                    ),
                    width_list=["80px", "180px"],
                )
            )

        # 2. 目标类型选择器
        if event_type == RoutineTypes.ONGOING:
            target_type = record_data.get("target_type", "none")
            elements.append(
                self.parent.build_form_row(
                    "目标类型",
                    self._build_target_type_selector(
                        target_type, is_confirmed, build_method_name
                    ),
                    width_list=["80px", "180px"],
                )
            )
        # 提醒模式选择器（仅未来事项，不在表单，有回调事件）
        if event_type == RoutineTypes.FUTURE:
            reminder_mode = record_data.get("reminder_mode", "off")
            elements.append(
                self.parent.build_form_row(
                    "提醒模式",
                    self._build_reminder_mode_selector(
                        reminder_mode, is_confirmed, build_method_name
                    ),
                    width_list=["80px", "180px"],
                )
            )

        return elements

    def _build_event_type_selector(
        self, event_type: str, is_confirmed: bool, build_method_name: str
    ) -> Dict[str, Any]:
        """
        构建事件类型选择器
        """
        options = [
            {
                "text": {"tag": "plain_text", "content": "⚡ 瞬间完成"},
                "value": RoutineTypes.INSTANT,
            },
            {
                "text": {"tag": "plain_text", "content": "▶️ 开始事项"},
                "value": RoutineTypes.START,
            },
            {
                "text": {"tag": "plain_text", "content": "🔄 长期持续"},
                "value": RoutineTypes.ONGOING,
            },
            {
                "text": {"tag": "plain_text", "content": "📅 未来事项"},
                "value": RoutineTypes.FUTURE,
            },
        ]

        action_data = {
            "card_action": "update_direct_record_type",
            "card_config_key": CardConfigKeys.ROUTINE_DIRECT_RECORD,
            "container_build_method": build_method_name,
        }

        return self.parent.build_select_element(
            placeholder="选择事件类型",
            options=options,
            initial_value=event_type,
            disabled=is_confirmed,
            action_data=action_data,
            element_id="event_type_selector",
        )

    def _build_degree_selection_section(
        self,
        degree_info: Dict[str, Any],
        record_data: Dict[str, Any],
        is_confirmed: bool,
        build_method_name: str,
    ) -> List[Dict[str, Any]]:
        """
        构建程度选择区域
        """
        elements = []

        # 获取程度选项和当前值
        degree_options = degree_info.get("degree_options", [])
        current_degree = record_data.get("degree", "")

        if not degree_options:
            return elements

        # 构建程度选择器选项
        options = []
        for option in degree_options:
            options.append(
                {"text": {"tag": "plain_text", "content": option}, "value": option}
            )

        # 添加"其他"选项
        options.append(
            {"text": {"tag": "plain_text", "content": "其他"}, "value": "其他"}
        )

        # 程度选择器
        degree_selector = self.parent.build_select_element(
            placeholder="选择完成方式",
            options=options,
            initial_value=(
                current_degree
                if current_degree in [opt["value"] for opt in options]
                else ""
            ),
            disabled=is_confirmed,
            action_data={
                "card_action": "update_record_degree",
                "card_config_key": CardConfigKeys.ROUTINE_DIRECT_RECORD,
                "container_build_method": build_method_name,
            },
            element_id="degree_selector",
        )

        elements.append(
            self.parent.build_form_row(
                "完成方式",
                degree_selector,
                width_list=["80px", "180px"],
            )
        )

        return elements

    def _build_progress_type_selector(
        self, progress_type: str, is_confirmed: bool, build_method_name: str
    ) -> Dict[str, Any]:
        """
        构建指标类型选择器
        """
        options = [
            {
                "text": {"tag": "plain_text", "content": "无指标"},
                "value": RoutineProgressTypes.NONE,
            },
            {
                "text": {"tag": "plain_text", "content": "数值记录"},
                "value": RoutineProgressTypes.VALUE,
            },
            {
                "text": {"tag": "plain_text", "content": "变化量"},
                "value": RoutineProgressTypes.MODIFY,
            },
        ]

        action_data = {
            "card_action": "update_progress_type",
            "card_config_key": CardConfigKeys.ROUTINE_DIRECT_RECORD,
            "container_build_method": build_method_name,
        }

        return self.parent.build_select_element(
            placeholder="选择指标类型",
            options=options,
            initial_value=progress_type,
            disabled=is_confirmed,
            action_data=action_data,
            element_id="progress_type",
        )

    def _build_target_type_selector(
        self, target_type: str, is_confirmed: bool, build_method_name: str
    ) -> Dict[str, Any]:
        """
        构建指标类型选择器
        """
        options = [
            {"text": {"tag": "plain_text", "content": "无目标"}, "value": "none"},
            {"text": {"tag": "plain_text", "content": "时间目标"}, "value": "time"},
            {"text": {"tag": "plain_text", "content": "次数目标"}, "value": "count"},
        ]

        action_data = {
            "card_action": "update_target_type",
            "card_config_key": CardConfigKeys.ROUTINE_DIRECT_RECORD,
            "container_build_method": build_method_name,
        }

        return self.parent.build_select_element(
            placeholder="选择指标类型",
            options=options,
            initial_value=target_type,
            disabled=is_confirmed,
            action_data=action_data,
            element_id="target_type",
        )

    def _build_reminder_mode_selector(
        self, reminder_mode: str, is_confirmed: bool, build_method_name: str
    ) -> Dict[str, Any]:
        """
        构建提醒模式选择器（仅未来事项）
        """
        options = [
            {
                "text": {"tag": "plain_text", "content": "关闭提醒"},
                "value": RoutineReminderModes.OFF,
            },
            {
                "text": {"tag": "plain_text", "content": "具体时间"},
                "value": RoutineReminderModes.TIME,
            },
            {
                "text": {"tag": "plain_text", "content": "相对时间"},
                "value": RoutineReminderModes.RELATIVE,
            },
        ]

        action_data = {
            "card_action": "update_reminder_mode",
            "card_config_key": CardConfigKeys.ROUTINE_DIRECT_RECORD,
            "container_build_method": build_method_name,
        }

        return self.parent.build_select_element(
            placeholder="选择提醒模式",
            options=options,
            initial_value=reminder_mode,
            disabled=is_confirmed,
            action_data=action_data,
            element_id="reminder_mode_selector",
        )

    # endregion

    # region 表单内字段区域
    def _build_form_fields_by_type(
        self, event_type: str, data_source: Dict, is_confirmed: bool
    ) -> Dict:
        """
        根据事件类型构建表单容器
        返回完整的表单容器，包含程度输入区域和其他表单字段

        表单内字段特点：
        1. 在表单内，通过提交按钮回调一次性处理
        2. 数据保存在 record_data 中
        3. 根据事件类型动态显示不同字段
        4. 受表单外字段状态影响（如指标类型影响指标值字段）
        """
        # 获取基础表单字段
        form_fields = []
        record_data = data_source.get("record_data", "")
        match event_type:
            case RoutineTypes.INSTANT | RoutineTypes.START:
                form_fields = self._build_instant_start_form_fields(
                    data_source, is_confirmed
                )
            case RoutineTypes.ONGOING:
                form_fields = self._build_ongoing_form_fields(record_data, is_confirmed)
            case RoutineTypes.FUTURE:
                form_fields = self._build_future_form_fields(record_data, is_confirmed)
            case _:
                # 未知类型，返回空字段列表
                form_fields = []
        # 返回完整的表单容器
        return {
            "tag": "form",
            "name": "direct_record_form",
            "elements": form_fields,
        }

    def _build_instant_start_form_fields(
        self, data_source: Dict, is_confirmed: bool
    ) -> List[Dict]:
        """
        构建瞬间完成和开始事项类型的表单字段

        表单内字段包括：
        - 耗时 duration（在表单）
        - 完成方式 degree（在表单）
        - 备注 note（在表单）
        - 指标值 progress（在表单，placeholder根据指标类型区分）
        """
        elements = []

        # 1. 耗时字段
        record_data = data_source.get("record_data", "")
        duration_value = record_data.get("duration", "")
        elements.append(
            self.parent.build_form_row(
                "⏱️ 耗时",
                self.parent.build_input_element(
                    placeholder="请输入耗时（分钟）",
                    initial_value=str(duration_value) if duration_value else "",
                    disabled=is_confirmed,
                    action_data={},
                    name="duration",
                ),
                width_list=["80px", "180px"],
            )
        )

        record_mode = data_source.get("record_mode", "")
        selected_degree = record_data.get("degree", "")
        need_degree_input = (record_mode == "direct") or (
            selected_degree == "其他" and record_mode == "quick"
        )

        if need_degree_input:
            # 2. 完成方式字段
            degree_value = record_data.get("custom_degree", "")
            elements.append(
                self.parent.build_form_row(
                    "完成方式",
                    self.parent.build_input_element(
                        placeholder="请输入完成方式",
                        initial_value=str(degree_value) if degree_value else "",
                        disabled=is_confirmed,
                        action_data={},
                        name="custom_degree",
                    ),
                    width_list=["80px", "180px"],
                )
            )

        # 3. 指标值字段（根据指标类型动态显示）
        progress_type = record_data.get("progress_type", RoutineProgressTypes.NONE)
        if progress_type != RoutineProgressTypes.NONE:
            # 根据指标类型设置不同的占位符
            if progress_type == RoutineProgressTypes.VALUE:
                placeholder_text = "最新数值"
            elif progress_type == RoutineProgressTypes.MODIFY:
                placeholder_text = "变化量（+/-）"
            else:
                placeholder_text = "指标值"

            progress_value = record_data.get("progress_value", "")
            elements.append(
                self.parent.build_form_row(
                    "📈 指标值",
                    self.parent.build_input_element(
                        placeholder=placeholder_text,
                        initial_value=str(progress_value) if progress_value else "",
                        disabled=is_confirmed,
                        action_data={},
                        name="progress_value",
                    ),
                    width_list=["80px", "180px"],
                )
            )

        # 4. 备注字段
        note_value = record_data.get("note", "")
        elements.append(
            self.parent.build_form_row(
                "📝 备注",
                self.parent.build_input_element(
                    placeholder="请输入备注（可选）",
                    initial_value=str(note_value) if note_value else "",
                    disabled=is_confirmed,
                    action_data={},
                    name="note",
                ),
                width_list=["80px", "180px"],
            )
        )

        return elements

    def _build_ongoing_form_fields(
        self, record_data: Dict, is_confirmed: bool
    ) -> List[Dict]:
        """
        构建长期持续类型的表单字段

        表单内字段包括：
        - 间隔类型（单选，在表单）
        - 目标类型（无/time/count，在表单）
        - 目标值（可以为空，在表单）
        - 备注 note（在表单）
        - 指标值 progress（在表单，placeholder根据指标类型区分）
        """
        elements = []

        # 1. 检查周期选择器
        check_cycle = record_data.get("check_cycle", "")
        elements.append(
            self.parent.build_form_row(
                "循环周期",
                self.parent.build_select_element(
                    placeholder="设置检查周期",
                    options=self._get_check_cycle_options(),
                    initial_value=check_cycle,
                    disabled=is_confirmed,
                    action_data={},
                    name="check_cycle",
                ),
                width_list=["80px", "180px"],
            )
        )

        # 2. 指标值字段（根据指标类型动态显示）
        progress_type = record_data.get("progress_type", RoutineProgressTypes.NONE)
        if progress_type != RoutineProgressTypes.NONE:
            if progress_type == RoutineProgressTypes.VALUE:
                placeholder_text = "最新数值"
            elif progress_type == RoutineProgressTypes.MODIFY:
                placeholder_text = "变化量（+/-）"
            else:
                placeholder_text = "指标值"

            progress_value = record_data.get("progress_value", "")
            elements.append(
                self.parent.build_form_row(
                    "📈 指标值",
                    self.parent.build_input_element(
                        placeholder=placeholder_text,
                        initial_value=str(progress_value) if progress_value else "",
                        disabled=is_confirmed,
                        action_data={},
                        name="progress_value",
                    ),
                    width_list=["80px", "180px"],
                )
            )

        # 3. 目标值字段（根据目标类型动态显示）
        target_type = record_data.get("target_type", "")
        if target_type != "":
            placeholder_text = (
                "目标时间（分钟）" if target_type == "time" else "目标次数"
            )
            target_value = record_data.get("target_value", "")
            elements.append(
                self.parent.build_form_row(
                    "🎯 目标值",
                    self.parent.build_input_element(
                        placeholder=placeholder_text,
                        initial_value=str(target_value) if target_value else "",
                        disabled=is_confirmed,
                        action_data={},
                        name="target_value",
                    ),
                    width_list=["80px", "180px"],
                )
            )

        # 4. 备注字段
        note_value = record_data.get("note", "")
        elements.append(
            self.parent.build_form_row(
                "📝 备注",
                self.parent.build_input_element(
                    placeholder="请输入备注（可选）",
                    initial_value=str(note_value) if note_value else "",
                    disabled=is_confirmed,
                    action_data={},
                    name="note",
                ),
                width_list=["80px", "180px"],
            )
        )

        return elements

    def _get_check_cycle_options(self) -> List[Dict]:
        """获取检查周期选项"""
        return [
            {
                "text": {"tag": "plain_text", "content": "每日"},
                "value": RoutineCheckCycle.DAILY,
            },
            {
                "text": {"tag": "plain_text", "content": "每周"},
                "value": RoutineCheckCycle.WEEKLY,
            },
            {
                "text": {"tag": "plain_text", "content": "每月"},
                "value": RoutineCheckCycle.MONTHLY,
            },
            {
                "text": {"tag": "plain_text", "content": "每季"},
                "value": RoutineCheckCycle.SEASONALLY,
            },
            {
                "text": {"tag": "plain_text", "content": "每年"},
                "value": RoutineCheckCycle.YEARLY,
            },
        ]

    def _build_future_form_fields(
        self, record_data: Dict, is_confirmed: bool
    ) -> List[Dict]:
        """
        构建未来事项类型的表单字段

        表单内字段包括：
        - 日期时间选择器（在表单）
        - 重要性（新字段，单选，在表单）
        - 预估耗时（新字段，用duration，在表单）
        - 提醒时间（新字段，单选，在表单，由提醒模式开启）
        - 提醒周期（下拉多选，在表单）
        - 备注（在表单）
        """
        elements = []

        # 1. 日期时间选择器
        scheduled_start_time = record_data.get("scheduled_start_time", "")
        elements.append(
            self.parent.build_form_row(
                "计划时间",
                self.parent.build_date_picker_element(
                    placeholder="选择计划时间",
                    initial_date=scheduled_start_time,
                    disabled=is_confirmed,
                    action_data={},
                    name="scheduled_start_time",
                ),
                width_list=["80px", "180px"],
            )
        )

        # 2. 重要性选择器
        priority = record_data.get("priority", "medium")
        elements.append(
            self.parent.build_form_row(
                "⭐ 重要性",
                self.parent.build_select_element(
                    placeholder="选择重要性",
                    options=self._get_priority_options(),
                    initial_value=priority,
                    disabled=is_confirmed,
                    action_data={},
                    name="priority",
                ),
                width_list=["80px", "180px"],
            )
        )

        # 4. 提醒设置字段（根据提醒模式显示）
        reminder_mode = record_data.get("reminder_mode", RoutineReminderModes.OFF)
        match reminder_mode:
            case RoutineReminderModes.TIME:
                # TIME模式：具体时间提醒，使用日期时间选择器
                reminder_time = record_data.get("reminder_time", "")
                elements.append(
                    self.parent.build_form_row(
                        "提醒时间",
                        self.parent.build_date_picker_element(
                            placeholder="选择具体提醒时间",
                            initial_date=reminder_time,
                            disabled=is_confirmed,
                            action_data={},
                            name="reminder_time",
                        ),
                        width_list=["80px", "180px"],
                    )
                )

            case RoutineReminderModes.RELATIVE:
                # RELATIVE模式：相对时间提醒，使用多选框选择相对时间
                reminder_relative = record_data.get("reminder_relative", [])
                elements.append(
                    self.parent.build_form_row(
                        "提醒时间",
                        self.parent.build_multi_select_element(
                            placeholder="选择提醒间隔",
                            options=self._get_reminder_time_options(),
                            initial_values=reminder_relative,
                            disabled=is_confirmed,
                            action_data={},
                            name="reminder_relative",
                        ),
                        width_list=["80px", "180px"],
                    )
                )

        # 3. 预估耗时和备注字段 - 放在折叠面板中
        additional_fields = []

        # 预估耗时字段
        duration_value = record_data.get("duration", "")
        additional_fields.append(
            self.parent.build_form_row(
                "预估耗时",
                self.parent.build_input_element(
                    placeholder="预估耗时（分钟）",
                    initial_value=str(duration_value) if duration_value else "",
                    disabled=is_confirmed,
                    action_data={},
                    name="duration",
                ),
                width_list=["80px", "180px"],
            )
        )

        # 备注字段
        note_value = record_data.get("note", "")
        additional_fields.append(
            self.parent.build_form_row(
                "📝 备注",
                self.parent.build_input_element(
                    placeholder="请输入备注（可选）",
                    initial_value=str(note_value) if note_value else "",
                    disabled=is_confirmed,
                    action_data={},
                    name="note",
                ),
                width_list=["80px", "180px"],
            )
        )

        # 将附加字段放入折叠面板
        elements.append(
            {
                "tag": "collapsible_panel",
                "expanded": False,
                "header": {
                    "title": {"tag": "markdown", "content": "📋 附加信息"},
                    "icon": {
                        "tag": "standard_icon",
                        "token": "down-small-ccm_outlined",
                        "color": "",
                        "size": "16px 16px",
                    },
                    "icon_position": "right",
                    "icon_expanded_angle": -180,
                },
                "elements": additional_fields,
            }
        )

        return elements

    def _get_priority_options(self) -> List[Dict]:
        """获取重要性选项"""
        return [
            {"text": {"tag": "plain_text", "content": "低"}, "value": "low"},
            {"text": {"tag": "plain_text", "content": "中"}, "value": "medium"},
            {"text": {"tag": "plain_text", "content": "高"}, "value": "high"},
            {"text": {"tag": "plain_text", "content": "紧急"}, "value": "urgent"},
        ]

    def _get_reminder_time_options(self) -> List[Dict]:
        """获取提醒时间选项"""
        return [
            {
                "text": {"tag": "plain_text", "content": "提前5分钟"},
                "value": "before_5min",
            },
            {
                "text": {"tag": "plain_text", "content": "提前15分钟"},
                "value": "before_15min",
            },
            {
                "text": {"tag": "plain_text", "content": "提前30分钟"},
                "value": "before_30min",
            },
            {
                "text": {"tag": "plain_text", "content": "提前1小时"},
                "value": "before_1hour",
            },
            {
                "text": {"tag": "plain_text", "content": "提前1天"},
                "value": "before_1day",
            },
        ]

    def _build_submit_button(
        self, is_confirmed: bool, build_method_name: str = None
    ) -> Dict[str, Any]:
        """
        构建提交按钮组

        按钮特点：
        1. 取消按钮：使用 callback 行为，触发取消处理
        2. 重置按钮：使用 form_action_type="reset"
        3. 确认按钮：使用 callback 行为，触发表单提交处理
        """
        if build_method_name is None:
            build_method_name = self.default_update_build_method
        return {
            "tag": "column_set",
            "horizontal_align": "left",
            "columns": [
                {
                    "tag": "column",
                    "width": "auto",
                    "elements": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "取消"},
                            "type": "danger",
                            "width": "default",
                            "icon": {
                                "tag": "standard_icon",
                                "token": "close-bold_outlined",
                            },
                            "disabled": is_confirmed,
                            "behaviors": [
                                {
                                    "type": "callback",
                                    "value": {
                                        "card_action": "cancel_direct_record",
                                        "card_config_key": CardConfigKeys.ROUTINE_DIRECT_RECORD,
                                        "container_build_method": build_method_name,
                                    },
                                }
                            ],
                            "name": "cancel_direct_record",
                        }
                    ],
                    "vertical_spacing": "8px",
                    "horizontal_align": "left",
                    "vertical_align": "top",
                },
                {
                    "tag": "column",
                    "width": "auto",
                    "elements": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "重置"},
                            "type": "default",
                            "width": "default",
                            "disabled": is_confirmed,
                            "form_action_type": "reset",
                            "name": "reset_form",
                        }
                    ],
                    "vertical_spacing": "8px",
                    "horizontal_align": "left",
                    "vertical_align": "top",
                },
                {
                    "tag": "column",
                    "width": "auto",
                    "elements": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "确认"},
                            "type": "primary",
                            "width": "default",
                            "icon": {"tag": "standard_icon", "token": "done_outlined"},
                            "disabled": is_confirmed,
                            "behaviors": [
                                {
                                    "type": "callback",
                                    "value": {
                                        "card_action": "confirm_direct_record",
                                        "card_config_key": CardConfigKeys.ROUTINE_DIRECT_RECORD,
                                        "container_build_method": build_method_name,
                                    },
                                }
                            ],
                            "form_action_type": "submit",
                            "name": "confirm_direct_record",
                        }
                    ],
                    "vertical_spacing": "8px",
                    "horizontal_align": "left",
                    "vertical_align": "top",
                },
            ],
        }

    # endregion

    # region 回调处理方法
    def update_direct_record_type(
        self, context: MessageContext_Refactor
    ) -> ProcessResult:
        """处理事项类型变更回调"""
        return self._handle_direct_record_field_update(
            context, "event_type", "事项类型已更新"
        )

    def update_progress_type(self, context: MessageContext_Refactor) -> ProcessResult:
        """处理指标类型变更回调"""
        return self._handle_direct_record_field_update(
            context, "progress_type", "指标类型已更新"
        )

    def update_target_type(self, context: MessageContext_Refactor) -> ProcessResult:
        """处理目标类型变更回调"""
        return self._handle_direct_record_field_update(
            context, "target_type", "目标类型已更新"
        )

    def update_reminder_mode(self, context: MessageContext_Refactor) -> ProcessResult:
        """处理提醒模式变更回调"""
        return self._handle_direct_record_field_update(
            context, "reminder_mode", "提醒模式已更新"
        )

    def update_check_cycle(self, context: MessageContext_Refactor) -> ProcessResult:
        """处理检查周期变更回调"""
        return self._handle_direct_record_field_update(
            context, "check_cycle", "检查周期已更新"
        )

    def update_record_degree(self, context: MessageContext_Refactor) -> ProcessResult:
        """处理完成方式变更回调"""
        return self._handle_direct_record_field_update(
            context, "degree", "完成方式已更新"
        )

    def cancel_direct_record(self, context: MessageContext_Refactor) -> ProcessResult:
        """取消直接记录"""
        build_method_name = context.content.value.get(
            "container_build_method", self.default_update_build_method
        )
        business_data, card_id, error_response = self.parent.ensure_valid_context(
            context, "cancel_direct_record", build_method_name
        )
        if error_response:
            return error_response

        new_card_dsl = self.parent.build_cancel_update_card_data(
            business_data, "cancel_direct_record", build_method_name, verbose=False
        )

        return self.parent.delete_and_respond_with_update(
            context.user_id, card_id, new_card_dsl, "操作已取消", ToastTypes.INFO
        )

    def confirm_direct_record(self, context: MessageContext_Refactor) -> ProcessResult:
        """确认直接记录"""
        # 通用的数据嵌套解析与错误处理
        build_method_name = context.content.value.get(
            "container_build_method", self.default_update_build_method
        )
        business_data, card_id, error_response = self.parent.ensure_valid_context(
            context, "confirm_direct_record", build_method_name
        )
        if error_response:
            return error_response

        data_source, _ = self.parent.safe_get_business_data(
            business_data, CardConfigKeys.ROUTINE_DIRECT_RECORD
        )

        # 1. 合并表单数据到record_data
        form_data = context.content.form_data
        record_data = data_source.get("record_data", {})

        record_data.update(form_data)
        # 2. 处理特殊字段格式化
        self._format_record_data(record_data, data_source)
        dup_business_data = copy.deepcopy(data_source)

        # 3. 调用业务层创建记录
        routine_business = self.parent.message_router.routine_record
        success, message = routine_business.create_direct_record(
            context.user_id, dup_business_data
        )

        if not success:
            # 创建失败，仅显示错误提示，保持卡片状态
            return self.parent.handle_card_operation_common(
                card_content={},
                card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
                update_toast_type=ToastTypes.ERROR,
                toast_message=message,
            )

        # 4. 创建成功，构建确认后的卡片
        business_data["is_confirmed"] = True
        business_data["result"] = "确认"
        new_card_dsl = self.parent.build_update_card_data(
            business_data, build_method_name
        )

        event_name = data_source.get("event_name", "直接记录")
        return self.parent.delete_and_respond_with_update(
            context.user_id,
            card_id,
            new_card_dsl,
            f"【{event_name}】 {message}",
            ToastTypes.SUCCESS,
        )

    def _handle_direct_record_field_update(
        self, context: MessageContext_Refactor, field_key: str, toast_message: str
    ) -> ProcessResult:
        """通用字段更新处理方法"""
        # 提取选择的值
        extracted_value = context.content.value.get("option", "")
        if not extracted_value:
            extracted_value = context.content.value.get("value", "")

        if not extracted_value:
            return self.parent.create_error_result("未能获取选择的值")

        # 获取构建方法名称
        build_method_name = context.content.value.get(
            "container_build_method", self.default_update_build_method
        )

        # 获取业务数据
        business_data, card_id, error_response = self.parent.ensure_valid_context(
            context, "_handle_direct_record_field_update", build_method_name
        )
        if error_response:
            return error_response

        # 获取direct_record的数据源
        data_source, _ = self.parent.safe_get_business_data(
            business_data, "routine_direct_record"
        )

        if "record_data" not in data_source:
            data_source["record_data"] = {}
        data_source["record_data"][field_key] = extracted_value

        # 构建新卡片
        new_card_dsl = self.parent.build_update_card_data(
            business_data, build_method_name
        )

        # if field_key == 'reminder_mode':
        #     print("test-cycle", json.dumps(json.dumps(new_card_dsl, ensure_ascii=False), ensure_ascii=False))

        return self.parent.save_and_respond_with_update(
            context.user_id,
            card_id,
            business_data,
            new_card_dsl,
            toast_message,
            ToastTypes.INFO,
        )

    def _format_record_data(self, record_data: Dict, data_source: Dict) -> None:
        """
        格式化记录数据，处理特殊字段
        """

        # 处理自定义程度
        if record_data.get("degree") == "其他":
            custom_degree = record_data.get("custom_degree", "").strip()
            if custom_degree and custom_degree != "其他":
                record_data["degree"] = custom_degree
                # 更新事件定义的程度选项
                event_definition = data_source.get("event_definition", {})
                if "properties" in event_definition:
                    degree_options = event_definition["properties"].setdefault(
                        "degree_options", []
                    )
                    if custom_degree not in degree_options:
                        degree_options.append(custom_degree)

        # 处理数值字段
        numeric_fields = ["duration", "progress_value", "target_value"]
        for field in numeric_fields:
            original_value = record_data.get(field)
            value_str = str(
                original_value if original_value is not None else ""
            ).strip()
            if value_str:
                numeric_value = safe_float(value_str)
                final_value = numeric_value if numeric_value is not None else 0
                record_data[field] = final_value

        datetime_fields = ["create_time", "reminder_time", "end_time", "scheduled_start_time"]
        for field in datetime_fields:
            original_value = record_data.get(field)
            if original_value:
                time_part = original_value.split(" +")[0].split(" -")[0]
                record_data[field] = time_part

    # endregion
