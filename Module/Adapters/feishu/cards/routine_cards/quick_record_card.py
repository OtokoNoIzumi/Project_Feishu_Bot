# -*- coding: utf-8 -*-
"""
Quick Record Card
快速记录卡片
"""

from typing import Dict, Any, List
import copy
from Module.Business.processors.base_processor import (
    MessageContext_Refactor,
    ProcessResult,
)
from Module.Services.constants import (
    CardConfigKeys,
    RoutineTypes,
    RoutineProgressTypes,
    ToastTypes,
    CardOperationTypes,
)
from Module.Common.scripts.common import debug_utils
from Module.Adapters.feishu.utils import safe_float


class QuickRecordCard:
    """
    快速记录卡片管理器
    """

    def __init__(self, parent_manager):
        self.parent = parent_manager  # 访问主管理器的共享方法和属性

    def _build_quick_record_confirm_card(
        self, business_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        快速记录确认卡片核心构建逻辑
        """
        event_name = business_data.get("event_name", "")
        is_confirmed = business_data.get("is_confirmed", False)
        result = business_data.get("result", "取消")

        base_title = f"添加记录：{event_name}" if event_name else "添加记录"
        header = self.parent._build_status_based_header(
            base_title, is_confirmed, result
        )

        return self.parent._build_base_card_structure(
            elements=self._build_quick_record_elements(business_data),
            header=header,
            padding="12px",
        )

    def _build_quick_record_elements(
        self, business_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """构建快速记录表单元素 - 条件化展示丰富信息"""
        # 解析业务层传递的数据 - 支持容器模式和常规模式
        # 交互状态和结果统一使用外层容器数据
        is_confirmed = business_data.get("is_confirmed", False)
        data_source, _ = self.parent._safe_get_business_data(
            business_data, CardConfigKeys.ROUTINE_RECORD
        )

        # 从对应数据源获取业务数据
        event_name = data_source.get("event_name", "")
        event_def = data_source.get("event_definition", {})
        avg_duration = data_source.get("avg_duration", 0.0)
        degree_info = data_source.get("degree_info", {})
        cycle_info = data_source.get("cycle_info", {})
        new_record = data_source.get("new_record", {})
        diff_minutes = data_source.get("diff_minutes", 0)
        event_type = event_def.get("type", RoutineTypes.INSTANT)
        progress_type = event_def.get("properties", {}).get("progress_type", "")
        last_progress_value = event_def.get("stats", {}).get("last_progress_value", 0)
        total_progress_value = event_def.get("stats", {}).get("total_progress_value", 0)

        elements = []

        # 1. 基础信息卡片
        elements.extend(
            self._build_basic_info_section(event_def, new_record, diff_minutes)
        )

        # 2. 条件化展示：时间预估和进度信息（合并到一个组件中）
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

        # 3. 条件化展示：目标进度信息（如果有目标设置）
        if cycle_info:
            elements.extend(self._build_cycle_progress_section(cycle_info))

        # === 确认输入部分 ===
        # 4. 条件化展示：程度选择器（如果有程度选项）
        if degree_info:
            elements.extend(
                self._build_degree_selection_section(
                    degree_info, data_source, is_confirmed
                )
            )

        # 创建表单容器
        form_elements = {"tag": "form", "elements": [], "name": "record_form"}

        # 5. 条件化展示：程度输入区域（如果有程度选项且选择了"其他"）
        if degree_info:
            selected_degree = new_record.get("degree", "")
            if selected_degree == "其他":
                form_elements["elements"].extend(
                    self._build_degree_input_section(
                        new_record.get("custom_degree", ""), is_confirmed
                    )
                )

        # 6. 条件化展示：持续时间输入区域
        if event_type in [RoutineTypes.INSTANT, RoutineTypes.END, RoutineTypes.START]:
            form_elements["elements"].extend(
                self._build_duration_input_section(
                    new_record.get("duration", ""), is_confirmed
                )
            )

        # 7. 条件化展示：进度类型选择区域
        if progress_type:
            form_elements["elements"].extend(
                self._build_progress_value_input_section(
                    new_record.get("progress_value", ""), is_confirmed
                )
            )

        # 8. 条件化展示：备注输入区域
        form_elements["elements"].extend(
            self._build_note_input_section(new_record.get("note", ""), is_confirmed)
        )

        # 9. 操作按钮或确认提示
        # if not is_confirmed:  对于表单组件，必须要有提交按钮，否则会报错，所以要用disabled来控制，而不是省略。
        form_elements["elements"].append(
            self._build_record_action_buttons(event_name, is_confirmed)
        )

        # 只有当表单有内容时才添加表单容器
        if form_elements["elements"]:
            elements.append(form_elements)
        if not is_confirmed:
            elements.append(
                {
                    "tag": "markdown",
                    "content": "**💡 重要提示** 请先选择完成日程的方式，这会清除下面所有的值！",
                }
            )

        return elements

    def _build_basic_info_section(
        self, event_def: Dict[str, Any], new_record: Dict[str, Any], diff_minutes: int
    ) -> List[Dict[str, Any]]:
        """构建基础信息区域"""
        elements = []

        # 事项类型显示
        event_type = event_def.get("type", RoutineTypes.INSTANT)

        # 基础信息卡片
        info_content = (
            f"**事项类型：** {self.parent._get_type_display_name(event_type)}\n"
        )

        # 显示记录时间
        if new_record.get("timestamp"):
            timestamp = new_record["timestamp"]
            split_timestamp = timestamp.split(" ")
            date_str = split_timestamp[0][5:10]
            time_str = split_timestamp[1][0:5]
            info_content += f"**记录时间：** {date_str} {time_str}\n"
            if diff_minutes > 0:
                info_content += f"**上次记录距今：** {diff_minutes}分钟\n"

        # 显示分类（如果有）
        category = event_def.get("category", "")
        if category:
            info_content += f"**分类：** <text_tag color='blue'>{category}</text_tag>\n"

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

    def _build_degree_selection_section(
        self,
        degree_info: Dict[str, Any],
        data_source: Dict[str, Any],
        is_confirmed: bool,
    ) -> List[Dict[str, Any]]:
        """构建程度选择区域"""
        elements = []

        degree_options = degree_info.get("degree_options", []).copy()
        if "其他" not in degree_options:
            degree_options.append("其他")
        default_degree = degree_info.get("default_degree", "")
        event_name = data_source.get("event_name", "")

        # 构建选项
        degree_select_options = []
        for degree in degree_options:
            degree_select_options.append(
                {"text": {"tag": "plain_text", "content": degree}, "value": degree}
            )

        # 智能默认值：用户上次选择 > 系统默认 > 第一个选项
        initial_degree = data_source["new_record"].get("degree", "") or default_degree

        elements.append(
            self.parent._build_form_row(
                "选择方式",
                self.parent._build_select_element(
                    placeholder=f"如何{event_name}？",
                    options=degree_select_options,
                    initial_value=initial_degree,
                    disabled=is_confirmed,
                    action_data={
                        "card_action": "update_record_degree",
                        "card_config_key": CardConfigKeys.ROUTINE_RECORD,
                    },
                    element_id="degree_select",
                ),
                width_list=["80px", "180px"],
                element_id="degree_select_row",
            )
        )

        return elements

    def _build_degree_input_section(
        self, initial_value: str, is_confirmed: bool
    ) -> List[Dict[str, Any]]:
        """构建程度输入区域"""
        # 这里要改成容器了，而没有单独的事件。
        elements = []

        elements.append(
            self.parent._build_form_row(
                "新方式",
                self.parent._build_input_element(
                    placeholder="添加新方式",
                    initial_value=initial_value,
                    disabled=is_confirmed,
                    action_data={},
                    element_id="degree_input",
                    name="custom_degree",
                ),
                width_list=["80px", "180px"],
                element_id="degree_input_row",
            )
        )

        return elements

    def _build_duration_input_section(
        self, initial_value: str, is_confirmed: bool
    ) -> List[Dict[str, Any]]:
        """构建持续时间输入区域"""
        elements = []

        elements.append(
            self.parent._build_form_row(
                "⏱️ 耗时",
                self.parent._build_input_element(
                    placeholder="记录耗时(分钟)",
                    initial_value=initial_value,
                    disabled=is_confirmed,
                    action_data={},
                    element_id="duration_input",
                    name="duration",
                ),
                width_list=["80px", "180px"],
            )
        )

        return elements

    def _build_progress_value_input_section(
        self, initial_value: str, is_confirmed: bool
    ) -> List[Dict[str, Any]]:
        """构建进度类型选择区域"""
        elements = []

        elements.append(
            self.parent._build_form_row(
                "🎯 指标值",
                self.parent._build_input_element(
                    placeholder="添加指标值",
                    initial_value=initial_value,
                    disabled=is_confirmed,
                    action_data={},
                    element_id="progress_value_input",
                    name="progress_value",
                ),
                width_list=["80px", "180px"],
            )
        )

        return elements

    def _build_note_input_section(
        self, initial_value: str, is_confirmed: bool
    ) -> List[Dict[str, Any]]:
        """构建备注输入区域"""
        elements = []

        elements.append(
            self.parent._build_form_row(
                "📝 备注",
                self.parent._build_input_element(
                    placeholder="添加备注信息",
                    initial_value=initial_value,
                    disabled=is_confirmed,
                    action_data={},
                    element_id="note_input",
                    name="note",
                ),
                width_list=["80px", "180px"],
            )
        )

        return elements

    def _build_record_action_buttons(
        self, event_name: str, is_confirmed: bool
    ) -> Dict[str, Any]:
        """构建记录操作按钮组"""
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
                                        "card_action": "cancel_record",
                                        "card_config_key": CardConfigKeys.ROUTINE_RECORD,
                                    },
                                }
                            ],
                            "name": "cancel_record",
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
                                        "card_action": "confirm_record",
                                        "card_config_key": CardConfigKeys.ROUTINE_RECORD,
                                        "event_name": event_name,
                                    },
                                }
                            ],
                            "form_action_type": "submit",
                            "name": "confirm_record",
                        }
                    ],
                    "vertical_spacing": "8px",
                    "horizontal_align": "left",
                    "vertical_align": "top",
                },
            ],
        }

    def confirm_record(self, context: MessageContext_Refactor) -> ProcessResult:
        """处理记录确认"""
        business_data, card_id, _ = self.parent._get_core_data(context)
        build_method_name = business_data.get(
            "container_build_method", "_build_quick_record_confirm_card"
        )

        data_source, _ = self.parent._safe_get_business_data(
            business_data, CardConfigKeys.ROUTINE_RECORD
        )

        business_data["is_confirmed"] = True

        core_data = data_source.get("new_record", {})
        if not core_data:
            new_card_dsl = self.parent._routine_handle_empty_data_with_cancel(
                business_data, "confirm_record", build_method_name
            )
            return self.parent._handle_card_operation_common(
                card_content=new_card_dsl,
                card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
                update_toast_type=ToastTypes.ERROR,
                toast_message="操作已失效",
            )

        business_data["result"] = "确认"

        form_data = context.content.form_data

        user_id = context.user_id
        new_degree = core_data.get("degree", "")
        if new_degree:
            if new_degree == "其他":
                # 其他留空的情况不增加定义
                new_custom_degree = form_data.get("custom_degree", "其他")
                if new_custom_degree not in ["其他", ""]:
                    core_data["degree"] = new_custom_degree
                    degree_options = data_source["event_definition"]["properties"][
                        "degree_options"
                    ]
                    if new_custom_degree not in degree_options:
                        degree_options.append(new_custom_degree)
            else:
                core_data["degree"] = new_degree

        # 并不需要格式化最新的结果，但输入值需要保留，也就是定义的部分要复制
        # 创建深拷贝以避免修改原始数据
        event_def = copy.deepcopy(data_source.get("event_definition", {}))

        duration_str = form_data.get("duration", "")
        new_duration = safe_float(duration_str)
        if new_duration is not None:
            core_data["duration"] = new_duration
        else:
            debug_utils.log_and_print(
                f"🔍 confirm_record - 耗时转换失败: [{duration_str}]",
                log_level="WARNING",
            )

        progress_type = event_def.get("properties", {}).get("progress_type", "")
        if progress_type:
            progress_value_str = str(form_data.get("progress_value", "")).strip()
            progress_value = safe_float(progress_value_str)
            if progress_value is not None:
                core_data["progress_value"] = progress_value
                if progress_type == RoutineProgressTypes.VALUE:
                    event_def["stats"]["last_progress_value"] = progress_value
                elif (progress_type == RoutineProgressTypes.MODIFY) and (
                    progress_value != 0
                ):
                    event_def["stats"]["total_progress_value"] = round(
                        event_def["stats"]["total_progress_value"] + progress_value, 3
                    )
                    event_def["stats"]["last_progress_value"] = progress_value
            else:
                debug_utils.log_and_print(
                    f"🔍 confirm_record - 进度值转换失败: [{progress_value_str}]",
                    log_level="WARNING",
                )

        core_data["note"] = form_data.get("note", "")

        new_card_dsl = self.parent._routine_get_build_method_and_execute(
            business_data, build_method_name
        )

        # 开始写入数据
        # 先写入记录
        routine_business = self.parent.message_router.routine_record
        records_data = routine_business.load_event_records(user_id)
        records_data["records"].append(core_data)
        records_data["last_updated"] = core_data.get("timestamp")
        # 再写入事件定义，做聚合类计算
        event_def["stats"]["record_count"] = (
            event_def.get("stats", {}).get("record_count", 0) + 1
        )
        cycle_info = data_source.get("cycle_info", {})
        if cycle_info:
            event_def["stats"]["cycle_count"] = cycle_info.get("cycle_count", 0) + 1
            event_def["stats"]["last_cycle_count"] = cycle_info.get(
                "last_cycle_count", 0
            )
            event_def["stats"]["last_refresh_date"] = cycle_info.get(
                "last_refresh_date", ""
            )

        event_def["stats"]["last_note"] = core_data.get("note", "")

        new_duration = core_data.get("duration", 0)
        if new_duration > 0:
            event_duration_info = event_def.get("stats", {}).get("duration", {})
            recent_durations = event_duration_info.get("recent_values", [])
            recent_durations.append(new_duration)
            if len(recent_durations) > event_duration_info.get("window_size", 10):
                recent_durations.pop(0)
            event_duration_info["recent_values"] = recent_durations
            try:
                total_duration = (
                    event_duration_info.get("avg_all_time", 0)
                    * event_duration_info.get("duration_count", 0)
                    + new_duration
                )
            except TypeError:
                total_duration = new_duration
            event_duration_info["duration_count"] = (
                event_duration_info.get("duration_count", 0) + 1
            )
            event_duration_info["avg_all_time"] = (
                total_duration / event_duration_info["duration_count"]
            )

        routine_business.save_event_records(user_id, records_data)
        event_def["last_updated"] = core_data.get("timestamp")
        full_event_def = routine_business.load_event_definitions(user_id)
        full_event_def["definitions"][event_def["name"]] = event_def
        full_event_def["last_updated"] = core_data.get("timestamp")
        full_event_def["last_record_time"] = core_data.get("timestamp")
        routine_business.save_event_definitions(user_id, full_event_def)

        event_name = context.content.value.get("event_name", "")

        return self.parent._delete_and_respond_with_update(
            context.user_id,
            card_id,
            new_card_dsl,
            f"【{event_name}】 记录成功！",
            ToastTypes.SUCCESS,
        )

    def cancel_record(self, context: MessageContext_Refactor) -> ProcessResult:
        """处理取消操作"""
        business_data, card_id, _ = self.parent._get_core_data(context)
        if not business_data:
            debug_utils.log_and_print(
                "🔍 cancel_record - 卡片数据为空", log_level="WARNING"
            )

        build_method_name = business_data.get(
            "container_build_method", "_build_quick_record_confirm_card"
        )
        business_data["is_confirmed"] = True
        business_data["result"] = "取消"

        new_card_dsl = self.parent._routine_get_build_method_and_execute(
            business_data, build_method_name
        )

        return self.parent._delete_and_respond_with_update(
            context.user_id, card_id, new_card_dsl, "操作已取消", ToastTypes.INFO
        )

    def update_record_degree(self, context: MessageContext_Refactor):
        """处理记录方式更新"""
        business_data, card_id, _ = self.parent._get_core_data(context)
        if not business_data:
            debug_utils.log_and_print(
                "🔍 update_record_degree - 卡片业务数据为空", log_level="WARNING"
            )
            return

        data_source, _ = self.parent._safe_get_business_data(
            business_data, CardConfigKeys.ROUTINE_RECORD
        )
        new_option = context.content.value.get("option")
        data_source["new_record"]["degree"] = new_option

        new_card_dsl = self.parent._routine_get_build_method_and_execute(
            business_data, "_build_quick_record_confirm_card"
        )
        return self.parent._save_and_respond_with_update(
            context.user_id,
            card_id,
            business_data,
            new_card_dsl,
            "完成方式更新成功！",
            ToastTypes.SUCCESS,
        )
