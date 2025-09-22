# -*- coding: utf-8 -*-
"""
Record Card
记录卡片
"""

import copy
from datetime import datetime
from typing import Dict, Any, List
from lark_oapi.event.callback.model.p2_card_action_trigger import (
    P2CardActionTriggerResponse,
)

from Module.Adapters.feishu.utils import safe_float
from Module.Services.constants import (
    RoutineTypes,
    RoutineProgressTypes,
    RoutineTargetTypes,
    RoutineReminderModes,
    RoutineReminderTimeOptions,
    ToastTypes,
    CardConfigKeys,
    CardOperationTypes,
    RoutineCheckCycle,
    RoutineRecordModes,
    ColorTypes,
)
from Module.Business.processors.base_processor import (
    MessageContext_Refactor,
    ProcessResult,
)
from Module.Services.config_service import set_nested_value
from Module.Business.shared_process import format_time_label
from Module.Adapters.feishu.cards.card_registry import BaseCardManager


class RecordCard:
    """
    记录卡片管理器
    支持在没有事件定义的情况下直接创建记录
    """

    def __init__(self, parent_manager):
        self.parent = parent_manager  # 访问主管理器的共享方法和属性
        self.default_update_build_method = "update_record_card"  # 默认更新构建方法

    def build_record_card(self, business_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        记录卡片核心构建逻辑
        只负责构建 header 和卡片结构，其他逻辑移到 elements 中
        """
        # 构建卡片头部
        header = self._build_record_header(business_data)

        # 构建卡片元素
        elements = self.build_record_elements(business_data)

        return self.parent.build_base_card_structure(elements, header, "12px")

    def _build_record_header(self, business_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        构建记录卡片头部
        """
        is_confirmed = business_data.get("is_confirmed", False)
        result = business_data.get("result", "取消")

        if is_confirmed:
            return self.parent.build_status_based_header("", is_confirmed, result)

        event_name = business_data.get("event_name", "")
        record_mode = business_data.get("record_mode", "")

        match record_mode:
            case RoutineRecordModes.REGIST:
                title = "新建记录" + (f"：{event_name}" if event_name else "")
                subtitle = "填写相关信息"
                icon = "add_outlined"
            case RoutineRecordModes.ADD:
                title = "添加记录" + (f"：{event_name}" if event_name else "")
                subtitle = "请确认记录信息"
                icon = "edit_outlined"
            case RoutineRecordModes.EDIT:
                title = "完成记录" + (f"：{event_name}" if event_name else "")
                subtitle = "请确认记录信息"
                icon = "edit_outlined"

        return self.parent.build_card_header(
            title, subtitle, ColorTypes.BLUE.value, icon
        )

    def build_record_elements(self, business_data: Dict[str, Any]) -> List[Dict]:
        """
        构建记录元素
        符合 sub_business_build_method 调用规范
        直接处理所有业务逻辑和数据传递
        """
        # 获取基础数据
        build_method_name = business_data.get(
            "container_build_method", self.default_update_build_method
        )
        is_confirmed = business_data.get("is_confirmed", False)

        # 使用 safe_get_business_data 处理递归嵌套的业务数据结构
        data_source, containing_mode = self.parent.safe_get_business_data(
            business_data, CardConfigKeys.ROUTINE_RECORD
        )

        # 从统一数据结构中提取所需参数
        event_definition = data_source.get("event_definition", {})
        event_type = event_definition.get("type", RoutineTypes.INSTANT.value)

        elements = []

        # 1. 计算信息区域（包含基础信息、时间预估、循环进度等）
        elements.extend(self._build_computed_info_by_type(data_source, containing_mode))

        # 2. 表单外字段区域（非表单数据，有回调事件，状态保存在配置中）
        non_form_elements = self._build_non_form_fields(
            data_source, is_confirmed, build_method_name
        )
        if non_form_elements:
            elements.extend(non_form_elements)
            # 3. 表单分隔线
            elements.append(
                self.parent.build_markdown_element(
                    "**💡 重要提示** 请先完成上面的设定，这会清除下面的所有值！"
                )
            )

        # 4. 表单内字段区域（表单数据，通过提交按钮回调一次性处理）
        form_container = self._build_form_fields_by_type(
            event_type, data_source, is_confirmed, build_method_name
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
            # 这里必须要用business_data，有很多最外层的通用方法在这里。
            sub_elements = getattr(self.parent, sub_business_build_method)(
                business_data
            )
            elements.append(self.parent.build_line_element())
            elements.extend(sub_elements)

        return elements

    # region 信息区域
    def _build_computed_info_by_type(
        self, data_source: Dict[str, Any], containing_mode: str
    ) -> List[Dict[str, Any]]:
        """
        构建基础信息区域（包含基础信息、时间预估、循环进度等）
        """
        elements = []

        # 基础信息显示区域
        record_data = data_source.get("record_data", {})
        computed_data = data_source.get("computed_data", {})

        event_name = record_data.get("event_name", "")

        if event_name or record_data.get("create_time"):
            diff_minutes = computed_data.get("diff_minutes", 0)
            elements.extend(
                self._build_basic_info_section(
                    data_source, event_name, diff_minutes, containing_mode
                )
            )

        # 时间预估和进度信息
        avg_duration = computed_data.get("avg_duration", 0)

        elements.extend(
            self._build_duration_and_progress_section(
                data_source,
                avg_duration,
            )
        )

        # 循环进度信息
        elements.extend(self._build_cycle_progress_section(data_source))

        return elements

    def _build_basic_info_section(
        self,
        data_source: Dict[str, Any],
        event_name: Dict[str, Any],
        diff_minutes: int,
        containing_mode: str,
    ) -> List[Dict[str, Any]]:
        """
        构建基础信息区域
        """
        elements = []
        record_mode = data_source.get("record_mode", "")
        record_data = data_source.get("record_data", {})
        event_definition = data_source.get("event_definition", {})

        # 基础信息卡片
        event_type = event_definition.get("type", RoutineTypes.FUTURE.value)

        info_content = ""

        if record_mode == RoutineRecordModes.ADD:
            info_content += (
                f"**事项类型：** {RoutineTypes.get_type_display_name(event_type)}\n"
            )

        # 显示时间信息
        time_info = self._build_time_info_section(data_source, event_name, diff_minutes)
        if time_info:
            info_content += time_info

        # 显示分类（如果有）
        pinyin_initials = event_definition.get("pinyin_initials", [])
        if pinyin_initials:
            extra_info = f" 快捷访问:"
            key_str = pinyin_initials[0]
        else:
            extra_info = ""
            key_str = ""
        category = event_definition.get("category", "")
        if category:
            # 获取分类颜色
            categories_data = data_source.get("categories", [])
            category_color = self.parent.get_category_color(category, categories_data)


            info_content += (
                f"**分类：** <text_tag color='{category_color}'>{category}</text_tag>{extra_info}<font color='{category_color}'>{key_str}</font>\n"
            )
        else:
            info_content += extra_info+key_str

        if info_content:
            elements.append(
                self.parent.build_markdown_element(info_content.rstrip("\n"))
            )

        return elements

    def _build_time_info_section(
        self,
        data_source: Dict[str, Any],
        event_name: str,
        diff_minutes: int,
    ) -> str:
        """
        构建时间信息显示内容

        Args:
            data_source: 完整的数据源
            event_name: 事件名称
            diff_minutes: 时间差（分钟）

        Returns:
            str: 格式化的时间信息字符串
        """
        # 从data_source获取必要数据
        record_data = data_source.get("record_data", {})
        event_definition = data_source.get("event_definition", {})
        record_mode = data_source.get("record_mode", "")
        event_type = event_definition.get("type", RoutineTypes.FUTURE.value)
        source_event_name = data_source.get("source_event_name", "")

        # 组件1: 获取时间标签
        time_label = self._get_time_label(
            event_type, record_mode, event_name, source_event_name, record_data
        )

        # 组件2: 获取时间值
        time_value = self._get_time_value(event_type, record_data)

        # 组件3: 获取时间差标签
        diff_time_label = self._get_diff_time_label(
            event_type, record_mode, event_name, source_event_name, diff_minutes
        )

        # 组件4: 获取时间差值
        diff_time_value = self._get_diff_time_value(event_type, diff_minutes)

        # 合并组件
        return self._merge_time_components(
            time_label, time_value, diff_time_label, diff_time_value
        )

    def _get_time_value(self, event_type: str, record_data: Dict[str, Any]) -> str:
        """获取时间值组件"""
        if event_type == RoutineTypes.FUTURE.value:
            return record_data.get("scheduled_start_time") or record_data.get(
                "create_time", ""
            )
        else:
            return record_data.get("create_time", "")

    def _get_time_label(
        self,
        event_type: str,
        record_mode: str,
        event_name: str,
        source_event_name: str,
        record_data: Dict[str, Any],
    ) -> str:
        """获取时间标签组件"""
        # 确定基础标签
        if event_type == RoutineTypes.FUTURE.value:
            base_label = (
                "预计开始时间"
                if record_data.get("scheduled_start_time")
                else "记录时间"
            )
        elif event_type == RoutineTypes.INSTANT.value:
            base_label = "记录时间"
        else:
            base_label = "开始时间"

        # 获取事件前缀
        event_prefix = self._get_record_mode_info(
            record_mode, event_name, source_event_name, "event_prefix"
        )
        return f"{event_prefix}{base_label}"

    def _get_diff_time_label(
        self,
        event_type: str,
        record_mode: str,
        event_name: str,
        source_event_name: str,
        diff_minutes: int,
    ) -> str:
        """获取时间差标签组件"""
        if diff_minutes <= 0 or event_type == RoutineTypes.FUTURE.value:
            return ""

        return self._get_record_mode_info(
            record_mode, event_name, source_event_name, "diff_label"
        )

    def _get_record_mode_info(
        self,
        record_mode: str,
        event_name: str,
        source_event_name: str,
        info_type: str,
    ) -> str:
        """统一处理record_mode的匹配逻辑，根据info_type返回不同信息"""

        # 使用字典映射替代冗长的match-case
        mode_configs = {
            RoutineRecordModes.REGIST: {
                "diff_label": "上次记录距今",
                "event_prefix": event_name
                or (f"{source_event_name}的关联事件" if source_event_name else ""),
            },
            RoutineRecordModes.EDIT: {
                "diff_label": "已经持续",
                "event_prefix": event_name or "",
            },
            RoutineRecordModes.ADD: {
                "diff_label": f"上次{event_name}距今",
                "event_prefix": "",
            },
        }

        return mode_configs.get(record_mode, {}).get(info_type, "")

    def _get_diff_time_value(self, event_type: str, diff_minutes: int) -> str:
        """获取时间差值组件"""
        if diff_minutes <= 0 or event_type == RoutineTypes.FUTURE.value:
            return ""
        return format_time_label(diff_minutes)

    def _merge_time_components(
        self,
        time_label: str,
        time_value: str,
        diff_time_label: str,
        diff_time_value: str,
    ) -> str:
        """合并时间组件"""
        result = ""

        # 添加主时间信息
        if time_label and time_value:
            result += f"**{time_label}：** {time_value}\n"

        # 添加时间差信息
        if diff_time_label and diff_time_value:
            result += f"**{diff_time_label}：** {diff_time_value}\n"

        return result

    def _build_duration_and_progress_section(
        self,
        data_source: Dict[str, Any],
        avg_duration: float,
    ) -> List[Dict[str, Any]]:
        """构建时间预估和进度信息区域"""
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

        computed_data = data_source.get("computed_data", {})
        estimated_duration = computed_data.get("estimated_duration", 0)
        if estimated_duration > 0:
            content_parts.append(f"**扣除其他事件后的时间：** {estimated_duration}分钟")
            last_duration = computed_data.get("last_duration", 0)
            if last_duration > 0:
                content_parts.append(f"**开始事件用时：** {last_duration}分钟")

        # 格式化进度信息
        event_definition = data_source.get("event_definition", {})
        progress_type = event_definition.get("properties", {}).get("progress_type", "")

        last_record_data = data_source.get("last_record_data", {})
        last_progress_value = last_record_data.get("progress_value", 0)

        if progress_type and last_progress_value:

            match progress_type:
                case RoutineProgressTypes.VALUE.value:
                    progress_str = f"{round(last_progress_value, 1)}"
                case RoutineProgressTypes.MODIFY.value:
                    total_progress_value = event_definition.get("stats", {}).get(
                        "total_progress_value", 0
                    )
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
            elements.append(self.parent.build_markdown_element(combined_content))

        return elements

    def _build_cycle_progress_section(
        self, data_source: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """构建循环进度信息区域"""
        elements = []

        # 基础数据提取
        event_definition = data_source.get("event_definition", {})
        target_type = event_definition.get("properties", {}).get("target_type", "")
        target_value = event_definition.get("properties", {}).get("target_value", 0)
        has_target = target_value and int(target_value) > 0

        computed_data = data_source.get("computed_data", {})
        cycle_info = computed_data.get("cycle_info", {})

        if not has_target and not cycle_info:
            # 还是还原一下之前的大方向，有cycle和target才显示进度。
            return elements

        cycle_count = max(0, int(cycle_info.get("cycle_count", 0)))
        target_progress_value = computed_data.get("target_progress_value", 0)
        current_value = cycle_count if cycle_info else target_progress_value

        progress_content_parts = []
        # 构建进度显示内容
        if has_target:
            target_val = max(1, int(target_value))
            progress_percent = min(100, (current_value / target_val * 100))
            target_type_display = RoutineTargetTypes.get_chinese_name(target_type)

            status_emoji, color = self._get_progress_status_style(progress_percent)

            progress_content_parts.append(
                f"🎯 **{target_type_display}目标：** {current_value}/{target_val}"
            )

            # 进度条
            filled_blocks = int(progress_percent // 10)
            progress_bar = "●" * filled_blocks + "○" * (10 - filled_blocks)
            real_progress_percent = round(current_value / target_val * 100, 1)
            progress_content_parts.append(
                f"📊 <font color={color}>{progress_bar}</font> {real_progress_percent}% {status_emoji}"
            )
        else:  # 无目标值的情况（情况2）
            unit = RoutineTargetTypes.get_unit(target_type)
            progress_content_parts.append(f"📊 **累计进度：** {current_value}{unit}")

        # 组装最终内容
        last_cycle_description = cycle_info.get("last_cycle_description", "")
        if last_cycle_description:
            last_cycle_count = cycle_info.get("last_cycle_count", 0)
            last_cycle_info = f"📈 {last_cycle_description}的情况：{last_cycle_count}"
            if has_target:
                last_cycle_info += f"/{target_value}"
            progress_content_parts.append(last_cycle_info)

        progress_content = "\n".join(progress_content_parts)

        if progress_content:
            elements.append(self.parent.build_markdown_element(progress_content))

        return elements

    def _get_progress_status_style(self, progress_percent: float) -> tuple[str, str]:
        """获取进度状态的样式（emoji和颜色）"""
        if progress_percent >= 100:
            return "🎉", "green"

        if progress_percent >= 80:
            return "🔥", "green"

        if progress_percent >= 50:
            return "💪", "orange"

        return "📈", "red"

    # endregion

    # region 表单外字段区域

    def _build_non_form_fields(
        self,
        data_source: Dict,
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

        event_definition = data_source.get("event_definition", {})
        event_type = event_definition.get("type", RoutineTypes.INSTANT.value)

        record_mode = data_source.get("record_mode", "")
        record_data = data_source.get("record_data", {})

        if record_mode == RoutineRecordModes.REGIST:
            # 新建事件，显示类型选择器
            elements.append(
                self.parent.build_form_row(
                    "事件类型",
                    self._build_event_type_selector(
                        event_type, is_confirmed, build_method_name
                    ),
                )
            )

        # 完成方式选择器（如果有选项）
        degree_options = event_definition.get("properties", {}).get(
            "degree_options", []
        )
        if degree_options:
            elements.extend(
                self._build_degree_selection_section(
                    degree_options.copy(), record_data, is_confirmed, build_method_name
                )
            )

        # 指标类型选择器
        if event_type != RoutineTypes.FUTURE.value:
            need_progress_selector = record_mode == RoutineRecordModes.REGIST
            if need_progress_selector:
                progress_type = event_definition.get("properties", {}).get(
                    "progress_type", RoutineProgressTypes.NONE.value
                )
                elements.append(
                    self.parent.build_form_row(
                        "指标类型",
                        self._build_progress_type_selector(
                            progress_type, is_confirmed, build_method_name
                        ),
                    )
                )

            # 2. 目标类型选择器
            need_target_selector = record_mode == RoutineRecordModes.REGIST
            if need_target_selector:
                target_type = event_definition.get("properties", {}).get(
                    "target_type", RoutineTargetTypes.NONE.value
                )
                elements.append(
                    self.parent.build_form_row(
                        "目标类型",
                        self._build_target_type_selector(
                            target_type, is_confirmed, build_method_name
                        ),
                    )
                )

        # 提醒模式选择器
        if event_type == RoutineTypes.FUTURE.value:
            reminder_mode = record_data.get(
                "reminder_mode", RoutineReminderModes.OFF.value
            )
            elements.append(
                self.parent.build_form_row(
                    "提醒模式",
                    self._build_reminder_mode_selector(
                        reminder_mode, is_confirmed, build_method_name
                    ),
                )
            )

        return elements

    def _build_event_type_selector(
        self, event_type: str, is_confirmed: bool, build_method_name: str
    ) -> Dict[str, Any]:
        """
        构建事件类型选择器
        """

        action_data = {
            "card_action": "handle_record_field_update",
            "card_config_key": CardConfigKeys.ROUTINE_RECORD,
            "container_build_method": build_method_name,
            "nested_field_pos": "event_definition.type",
            "toast_message": "事项类型已更新",
        }

        return self.parent.build_select_element(
            placeholder="选择事件类型",
            options=RoutineTypes.build_options(),
            initial_value=event_type,
            disabled=is_confirmed,
            action_data=action_data,
            element_id="event_type_selector",
        )

    def _build_degree_selection_section(
        self,
        degree_options: List[str],
        record_data: Dict[str, Any],
        is_confirmed: bool,
        build_method_name: str,
    ) -> List[Dict[str, Any]]:
        """
        构建程度选择区域
        """
        elements = []

        # 获取程度选项和当前值
        current_degree = record_data.get("degree", "")
        event_name = record_data.get("event_name", "")

        if not degree_options:
            return elements

        if "其他" not in degree_options:
            degree_options.append("其他")

        options_dict = {option: option for option in degree_options}
        options = self.parent.build_options(options_dict)

        # 程度选择器
        degree_selector = self.parent.build_select_element(
            placeholder=f"如何{event_name}？",
            options=options,
            initial_value=(current_degree if current_degree in degree_options else ""),
            disabled=is_confirmed,
            action_data={
                "card_action": "handle_record_field_update",
                "card_config_key": CardConfigKeys.ROUTINE_RECORD,
                "container_build_method": build_method_name,
                "nested_field_pos": "record_data.degree",
                "toast_message": "完成方式已更新",
            },
            element_id="degree_selector",
        )

        elements.append(
            self.parent.build_form_row(
                "选择方式",
                degree_selector,
            )
        )

        return elements

    def _build_progress_type_selector(
        self, progress_type: str, is_confirmed: bool, build_method_name: str
    ) -> Dict[str, Any]:
        """
        构建指标类型选择器
        """
        options = RoutineProgressTypes.build_options()

        action_data = {
            "card_action": "handle_record_field_update",
            "card_config_key": CardConfigKeys.ROUTINE_RECORD,
            "container_build_method": build_method_name,
            "nested_field_pos": "event_definition.properties.progress_type",
            "toast_message": "指标类型已更新",
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
        options = RoutineTargetTypes.build_options()

        action_data = {
            "card_action": "handle_record_field_update",
            "card_config_key": CardConfigKeys.ROUTINE_RECORD,
            "container_build_method": build_method_name,
            "nested_field_pos": "event_definition.properties.target_type",
            "toast_message": "目标类型已更新",
        }

        return self.parent.build_select_element(
            placeholder="选择目标类型",
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
        options = RoutineReminderModes.build_options()

        action_data = {
            "card_action": "handle_record_field_update",
            "card_config_key": CardConfigKeys.ROUTINE_RECORD,
            "container_build_method": build_method_name,
            "nested_field_pos": "record_data.reminder_mode",
            "toast_message": "提醒模式已更新",
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
        self,
        event_type: str,
        data_source: Dict,
        is_confirmed: bool,
        build_method_name: str,
    ) -> Dict:
        """
        根据事件类型构建表单容器
        返回完整的表单容器，包含程度输入区域和其他表单字段

        表单内字段特点：
        1. 在表单内，通过提交按钮回调一次性处理
        2. 根据事件类型动态显示不同字段
        3. 受表单外字段状态影响（如指标类型影响指标值字段）
        """
        # 获取基础表单字段
        form_fields = []
        record_data = data_source.get("record_data", {})
        event_name = record_data.get("event_name", "")
        if not event_name:
            form_fields.append(
                self.parent.build_form_row(
                    "事件名称",
                    self.parent.build_input_element(
                        placeholder="新事件名称（必填）",
                        initial_value=event_name,
                        disabled=is_confirmed,
                        action_data={},
                        name="event_name",
                        required=True and not is_confirmed,
                    ),
                )
            )

        match event_type:
            case RoutineTypes.INSTANT.value | RoutineTypes.START.value:
                form_fields.extend(
                    self._build_instant_start_form_fields(
                        data_source, is_confirmed, build_method_name
                    )
                )
            case RoutineTypes.ONGOING.value:
                form_fields.extend(
                    self._build_ongoing_form_fields(data_source, is_confirmed)
                )
            case RoutineTypes.FUTURE.value:
                form_fields.extend(
                    self._build_future_form_fields(data_source, is_confirmed)
                )
        # 返回完整的表单容器
        return self.parent.build_form_element(form_fields, "direct_record_form")

    def _build_instant_start_form_fields(
        self, data_source: Dict, is_confirmed: bool, build_method_name: str
    ) -> List[Dict]:
        """
        构建瞬间完成和开始事项类型的表单字段

        表单内字段包括：
        - 所属分类 category（在表单）
        - 耗时 duration（在表单）
        - 完成方式 degree（在表单）
        - 备注 note（在表单）
        - 指标值 progress（在表单，placeholder根据指标类型区分）
        """
        elements = []

        record_data = data_source.get("record_data", {})
        event_definition = data_source.get("event_definition", {})
        record_mode = data_source.get("record_mode", "")
        selected_degree = record_data.get("degree", "")

        # 1. 所属分类字段（仅在ADD模式下显示）
        if record_mode == RoutineRecordModes.REGIST:
            elements.append(
                self._build_category_select_field(data_source, is_confirmed)
            )

        # 2. 完成方式字段（条件显示）
        need_degree_input = (record_mode == RoutineRecordModes.REGIST) or (
            selected_degree == "其他" and record_mode == RoutineRecordModes.ADD
        )
        if need_degree_input:
            degree_value = record_data.get("custom_degree", "")
            elements.append(
                self.parent.build_form_row(
                    "完成方式",
                    self.parent.build_input_element(
                        placeholder="增加新方式（可选）",
                        initial_value=str(degree_value) if degree_value else "",
                        disabled=is_confirmed,
                        action_data={},
                        name="custom_degree",
                    ),
                )
            )

        # 3. 耗时字段
        duration_value = record_data.get("duration", "")
        if record_mode != RoutineRecordModes.EDIT:
            # 创建快填按钮

            action_data = {
                "card_action": "handle_record_field_update",
                "card_config_key": CardConfigKeys.ROUTINE_RECORD,
                "container_build_method": build_method_name,
                "nested_field_pos": "record_data.duration",
                "toast_message": "耗时已更新",
                "value_mode": "diff_create_time",
            }

            quick_fill_button = self.parent.build_button_element(
                text="⏱快填",
                action_data=action_data,
                disabled=is_confirmed,
                name="quick_fill_duration",
                button_type="default",
                size="small",
            )

            width_list = ["80px", "100px", "70px"]
            duration_elements = self.parent.build_form_row(
                "⏱️ 耗时",
                self.parent.build_input_element(
                    placeholder="单位:分钟",
                    initial_value=str(duration_value) if duration_value else "",
                    disabled=is_confirmed,
                    action_data={},
                    name="duration",
                ),
                width_list=width_list,
                third_element=quick_fill_button,
            )
        else:
            duration_elements = self.parent.build_form_row(
                "⏱️ 耗时",
                self.parent.build_input_element(
                    placeholder="单位:分钟",
                    initial_value=str(duration_value) if duration_value else "",
                    disabled=is_confirmed,
                    action_data={},
                    name="duration",
                ),
            )

        elements.append(duration_elements)

        # 4. 指标值字段（根据指标类型动态显示）
        elements.extend(
            self._build_progress_field(event_definition, record_data, is_confirmed)
        )

        # 5. 附加信息字段（分类和备注）
        elements.extend(
            self._build_additional_info_fields(
                data_source, record_data, is_confirmed, record_mode
            )
        )

        return elements

    def _build_ongoing_form_fields(
        self, data_source: Dict, is_confirmed: bool
    ) -> List[Dict]:
        """
        构建长期持续类型的表单字段

        表单内字段包括：
        - 所属分类 category（在表单）
        - 间隔类型（单选，在表单）
        - 目标类型（无/time/count，在表单）
        - 目标值（可以为空，在表单）
        - 备注 note（在表单）
        - 指标值 progress（在表单，placeholder根据指标类型区分）
        """
        elements = []
        event_definition = data_source.get("event_definition", {})
        record_data = data_source.get("record_data", {})
        record_mode = data_source.get("record_mode", "")

        # 1. 所属分类字段（仅在ADD模式下显示）
        if record_mode == RoutineRecordModes.REGIST:
            elements.append(
                self._build_category_select_field(data_source, is_confirmed)
            )

        # 2. 循环周期选择器
        check_cycle = event_definition.get("properties", {}).get("check_cycle", "")
        elements.append(
            self.parent.build_form_row(
                "循环周期",
                self.parent.build_select_element(
                    placeholder="设置检查周期",
                    options=RoutineCheckCycle.build_options(),
                    initial_value=check_cycle,
                    disabled=is_confirmed,
                    action_data={},
                    name="check_cycle",
                ),
            )
        )

        # 3. 指标值字段（根据指标类型动态显示）
        elements.extend(
            self._build_progress_field(event_definition, record_data, is_confirmed)
        )

        # 4. 目标值字段（根据目标类型动态显示）
        elements.extend(
            self._build_target_field(event_definition, record_data, is_confirmed)
        )

        # 5. 附加信息字段（分类和备注）
        elements.extend(
            self._build_additional_info_fields(
                data_source, record_data, is_confirmed, record_mode
            )
        )

        return elements

    def _build_future_form_fields(
        self, data_source: Dict, is_confirmed: bool
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
        record_data = data_source.get("record_data", {})

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
            )
        )

        # 3. 提醒设置字段（根据提醒模式显示）
        elements.extend(self._build_reminder_fields(record_data, is_confirmed))

        # 4. 附加信息字段（预估耗时和备注）
        elements.append(
            self._build_collapsible_additional_info(
                [
                    self._build_duration_field(record_data, is_confirmed),
                    self._build_note_field(record_data, is_confirmed),
                ]
            )
        )

        return elements

    # region 表单内字段组件
    def _build_category_select_field(
        self, data_source: Dict, is_confirmed: bool
    ) -> Dict:
        """构建分类选择字段"""
        category_options = data_source.get("category_options", [])
        event_definition = data_source.get("event_definition", {})
        category_value = event_definition.get("category", "")

        # 构建分类选项
        options_dict = {option: option for option in category_options}
        category_select_options = self.parent.build_options(options_dict)

        return self.parent.build_form_row(
            "所属分类",
            self.parent.build_select_element(
                placeholder="选择分类",
                options=category_select_options,
                initial_value=category_value,
                disabled=is_confirmed,
                action_data={},
                name="category_select",
            ),
        )

    def _build_progress_field(
        self, event_definition: Dict, record_data: Dict, is_confirmed: bool
    ) -> List[Dict]:
        """构建指标值字段"""
        progress_type = event_definition.get("properties", {}).get(
            "progress_type", RoutineProgressTypes.NONE.value
        )
        if progress_type == RoutineProgressTypes.NONE.value:
            return []

        placeholder_text = RoutineProgressTypes.get_by_value(progress_type).placeholder
        progress_value = record_data.get("progress_value", "")

        return [
            self.parent.build_form_row(
                "📈 指标值",
                self.parent.build_input_element(
                    placeholder=placeholder_text,
                    initial_value=str(progress_value) if progress_value else "",
                    disabled=is_confirmed,
                    action_data={},
                    name="progress_value",
                ),
            )
        ]

    def _build_target_field(
        self, event_definition: Dict, record_data: Dict, is_confirmed: bool
    ) -> List[Dict]:
        """构建目标值字段"""
        target_type = event_definition.get("properties", {}).get(
            "target_type", RoutineTargetTypes.NONE.value
        )
        if not target_type or target_type == RoutineTargetTypes.NONE.value:
            return []

        placeholder_text = (
            "目标时间（分钟）"
            if target_type == RoutineTargetTypes.TIME.value
            else "目标次数"
        )
        target_value = record_data.get("target_value", "")

        return [
            self.parent.build_form_row(
                "🎯 目标值",
                self.parent.build_input_element(
                    placeholder=placeholder_text,
                    initial_value=str(target_value) if target_value else "",
                    disabled=is_confirmed,
                    action_data={},
                    name="target_value",
                ),
            )
        ]

    def _build_reminder_fields(
        self, record_data: Dict, is_confirmed: bool
    ) -> List[Dict]:
        """构建提醒相关字段"""
        reminder_mode = record_data.get("reminder_mode", RoutineReminderModes.OFF.value)

        match reminder_mode:
            case RoutineReminderModes.TIME.value:
                # TIME模式：具体时间提醒，使用日期时间选择器
                reminder_time = record_data.get("reminder_time", "")
                return [
                    self.parent.build_form_row(
                        "提醒时间",
                        self.parent.build_date_picker_element(
                            placeholder="选择具体提醒时间",
                            initial_date=reminder_time,
                            disabled=is_confirmed,
                            action_data={},
                            name="reminder_time",
                        ),
                    )
                ]
            case RoutineReminderModes.RELATIVE.value:
                # RELATIVE模式：相对时间提醒，使用多选框选择相对时间
                reminder_relative = record_data.get("reminder_relative", [])
                return [
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
                    )
                ]
            case _:
                return []

    def _build_additional_info_fields(
        self,
        data_source: Dict,
        record_data: Dict,
        is_confirmed: bool,
        record_mode: str,
    ) -> List[Dict]:
        """构建附加信息字段（分类和备注）"""
        if record_mode == RoutineRecordModes.REGIST:
            # ADD模式下显示分类和备注字段
            event_definition = data_source.get("event_definition", {})
            additional_fields = [
                self._build_category_input_field(event_definition, is_confirmed),
                self._build_note_field(record_data, is_confirmed),
            ]
            return [self._build_collapsible_additional_info(additional_fields)]

        # RECORD模式下只显示备注字段
        return [self._build_note_field(record_data, is_confirmed)]

    def _build_category_input_field(
        self, event_definition: Dict, is_confirmed: bool
    ) -> Dict:
        """构建分类输入字段"""
        category_value = event_definition.get("category", "")
        return self.parent.build_form_row(
            "新建分类",
            self.parent.build_input_element(
                placeholder="优先级更高",
                initial_value=category_value,
                disabled=is_confirmed,
                action_data={},
                name="category_input",
            ),
        )

    def _build_note_field(self, record_data: Dict, is_confirmed: bool) -> Dict:
        """构建备注字段"""
        note_value = record_data.get("note", "")
        return self.parent.build_form_row(
            "📝 备注",
            self.parent.build_input_element(
                placeholder="请输入备注（可选）",
                initial_value=str(note_value) if note_value else "",
                disabled=is_confirmed,
                action_data={},
                name="note",
            ),
        )

    def _build_duration_field(self, record_data: Dict, is_confirmed: bool) -> Dict:
        """构建耗时字段"""
        duration_value = record_data.get("duration", "")
        return self.parent.build_form_row(
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

    def _build_collapsible_additional_info(self, additional_fields: List[Dict]) -> Dict:
        """构建可折叠的附加信息面板"""
        return self.parent.build_collapsible_panel_element(
            header_text="📋 附加信息",
            header_icon="down-small-ccm_outlined",
            expanded=False,
            content=additional_fields,
        )

    def _get_priority_options(self) -> List[Dict]:
        """获取重要性选项"""
        dict_options = {
            "low": "低",
            "medium": "中",
            "high": "高",
            "urgent": "紧急",
        }
        return self.parent.build_options(dict_options)

    def _get_reminder_time_options(self) -> List[Dict]:
        """获取提醒时间选项"""
        return RoutineReminderTimeOptions.build_options()

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
        cancel_action_data = {
            "card_action": "cancel_record",
            "card_config_key": CardConfigKeys.ROUTINE_RECORD,
            "container_build_method": build_method_name,
        }

        confirm_action_data = {
            "card_action": "confirm_record",
            "card_config_key": CardConfigKeys.ROUTINE_RECORD,
            "container_build_method": build_method_name,
        }
        cancel_button = self.parent.build_button_element(
            text="取消",
            action_data=cancel_action_data,
            disabled=is_confirmed,
            button_type="danger",
            icon="close-bold_outlined",
            name="cancel_record",
        )
        reset_button = self.parent.build_button_element(
            text="重置",
            disabled=is_confirmed,
            form_action_type="reset",
            name="reset_form",
        )
        confirm_button = self.parent.build_button_element(
            text="确认",
            action_data=confirm_action_data,
            disabled=is_confirmed,
            button_type="primary",
            icon="done_outlined",
            form_action_type="submit",
            name="confirm_record",
        )

        return self.parent.build_button_group_element(
            [cancel_button, reset_button, confirm_button]
        )

    # endregion

    # region 回调处理方法
    @BaseCardManager.card_updater(
        sub_business_name=CardConfigKeys.ROUTINE_RECORD, toast_message="字段已更新"
    )
    def handle_record_field_update(
        self, context: MessageContext_Refactor, data_source
    ) -> str:
        """通用字段更新处理方法"""

        # 提取选择的值
        extracted_value = context.content.value.get("option", "")
        if not extracted_value:
            extracted_value = context.content.value.get("value", "")

        value_mode = context.content.value.get("value_mode", "")
        if not extracted_value and not value_mode:
            return P2CardActionTriggerResponse(
                {"toast": {"type": "error", "content": "未能获取选择的值"}}
            )

        nested_field_pos = context.content.value.get("nested_field_pos", "record_data")

        # 从context中动态获取toast消息
        toast_message = context.content.value.get("toast_message", "字段已更新")

        match value_mode:
            case "diff_create_time":
                last_time = datetime.strptime(
                    data_source.get("record_data", {}).get("create_time", ""),
                    "%Y-%m-%d %H:%M",
                )
                extracted_value = round(
                    (datetime.now() - last_time).total_seconds() / 60, 1
                )

        set_nested_value(data_source, nested_field_pos, extracted_value)

        # 返回动态获取的toast消息，装饰器会使用这个值
        return toast_message

    def cancel_record(self, context: MessageContext_Refactor) -> ProcessResult:
        """取消直接记录"""
        build_method_name = context.content.value.get(
            "container_build_method", self.default_update_build_method
        )
        business_data, card_id, error_response = self.parent.ensure_valid_context(
            context, "cancel_record", build_method_name
        )
        if error_response:
            return error_response

        new_card_dsl = self.parent.build_cancel_update_card_data(
            business_data, "cancel_record", build_method_name, verbose=False
        )
        # 检查是否为连续记录模式
        continuous_record = business_data.get("continuous_record", False)
        if continuous_record:
            return self.parent.save_and_respond_with_update(
                context.user_id,
                card_id,
                business_data,
                new_card_dsl,
                "已取消当前记录",
                ToastTypes.INFO,
            )

        return self.parent.delete_and_respond_with_update(
            context.user_id, card_id, new_card_dsl, "操作已取消", ToastTypes.INFO
        )

    def confirm_record(self, context: MessageContext_Refactor) -> ProcessResult:
        """确认直接记录"""
        # 通用的数据嵌套解析与错误处理
        build_method_name = context.content.value.get(
            "container_build_method", self.default_update_build_method
        )
        business_data, card_id, error_response = self.parent.ensure_valid_context(
            context, "confirm_record", build_method_name
        )
        if error_response:
            return error_response

        data_source, _ = self.parent.safe_get_business_data(
            business_data, CardConfigKeys.ROUTINE_RECORD
        )

        # 1. 合并表单数据
        form_data = context.content.form_data

        fields_in_event_definition = ["check_cycle"]

        # 2. 处理特殊字段格式化，以及前端数据合并
        self._handle_card_data(data_source, form_data, fields_in_event_definition)
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
        event_name = data_source.get("record_data", {}).get("event_name", "直接记录")
        continuous_record = business_data.get("continuous_record", False)
        business_data["is_confirmed"] = True
        business_data["result"] = "确认"
        new_card_dsl = self.parent.build_update_card_data(
            business_data, build_method_name
        )

        if continuous_record:
            return self.parent.save_and_respond_with_update(
                context.user_id,
                card_id,
                business_data,
                new_card_dsl,
                f"【{event_name}】 {message}，可继续添加新记录",
                ToastTypes.SUCCESS,
            )

        # 非连续记录模式：删除数据并显示确认状态
        return self.parent.delete_and_respond_with_update(
            context.user_id,
            card_id,
            new_card_dsl,
            f"【{event_name}】 {message}",
            ToastTypes.SUCCESS,
        )

    def _handle_card_data(
        self, data_source: Dict, form_data: Dict, fields_in_event_definition: List[str]
    ) -> None:
        """
        格式化记录数据，处理特殊字段
        """
        record_data = data_source.get("record_data", {})
        record_mode = data_source.get("record_mode", RoutineRecordModes.ADD)

        event_definition = data_source.get("event_definition", {})
        if "properties" not in event_definition:
            event_definition["properties"] = {}

        # 处理分类字段的优先级逻辑
        category_input = form_data.get("category_input", "").strip()
        category_select = form_data.get("category_select", "").strip()

        # 优先使用输入框的内容，如果为空则使用选择框的内容
        final_category = category_input if category_input else category_select
        if final_category:
            event_definition["category"] = final_category

        if final_category not in data_source.get("category_options", []):
            color_value = ColorTypes.get_random_color().value
            data_source["categories"].append(
                {
                    "name": final_category,
                    "color": color_value,
                }
            )

        # 移除原始的分类字段，避免重复处理
        form_data.pop("category_input", None)
        form_data.pop("category_select", None)

        for field in fields_in_event_definition:
            if field in form_data:
                event_definition["properties"][field] = form_data[field]
                del form_data[field]

        record_data.update(form_data)

        # 处理自定义程度
        custom_degree = record_data.get("custom_degree", "").strip()
        if custom_degree and custom_degree != "其他":

            if (
                record_mode == RoutineRecordModes.ADD
                and record_data.get("degree") == "其他"
            ):
                record_data["degree"] = custom_degree

            # 更新事件定义的程度选项
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

        datetime_fields = [
            "create_time",
            "reminder_time",
            "end_time",
            "scheduled_start_time",
        ]
        for field in datetime_fields:
            original_value = record_data.get(field)
            if original_value:
                time_part = original_value.split(" +")[0].split(" -")[0]
                record_data[field] = time_part

    # endregion
