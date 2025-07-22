# -*- coding: utf-8 -*-
"""
Direct Record Card
直接记录卡片
"""

import json
from typing import Dict, Any, List
from Module.Services.constants import (
    RoutineTypes,
    RoutineProgressTypes,
    RoutineReminderModes,
    ToastTypes,
    CardConfigKeys,
    CardOperationTypes,
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
        else:
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
        data_source, is_container_mode = self.parent.safe_get_business_data(
            business_data, "routine_direct_record"
        )

        # 从统一数据结构中提取所需参数
        record_data = data_source.get("record_data", {})
        
        # 从统一结构中提取数据
        event_name = data_source.get("event_name", "")
        event_type = record_data.get("event_type", "")

        elements = []

        # 1. 表单外字段区域（非表单数据，有回调事件，状态保存在配置中）
        elements.extend(
            self._build_non_form_fields(
                record_data, event_name, event_type, is_confirmed, build_method_name
            )
        )

        # 2. 表单分隔线
        elements.append(
            {
                "tag": "markdown",
                "content": "**💡 重要提示** 请先完成上面的设定，这会清除下面的所有值！",
            }
        )

        # 3. 创建表单容器
        form_container = {"tag": "form", "elements": [], "name": "direct_record_form"}

        # 4. 表单内字段区域（表单数据，通过提交按钮回调一次性处理）
        form_fields = self._build_form_fields_by_type(
            event_type, record_data, is_confirmed
        )
        form_container["elements"].extend(form_fields)

        # 5. 提交按钮
        form_container["elements"].append(
            self._build_submit_button(is_confirmed, build_method_name)
        )

        # 6. 添加表单容器到元素列表
        elements.append(form_container)

        # 7. 处理集成模式：检查是否有子业务数据
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

    def _build_non_form_fields(
        self,
        record_data: Dict,
        event_name: str,
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

        # 事件名称（只读显示，不在表单）
        elements.append(
            self.parent.build_form_row(
                "事件名称",
                {
                    "tag": "markdown",
                    "content": f"**{event_name}**" if event_name else "*未设置*",
                },
                width_list=["80px", "180px"],
            )
        )

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
            "card_config_key": "routine_direct_record",
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
            "card_config_key": "routine_direct_record",
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
            "card_config_key": "routine_direct_record",
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
            "card_config_key": "routine_direct_record",
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

    def _build_form_fields_by_type(
        self, event_type: str, record_data: Dict, is_confirmed: bool
    ) -> List[Dict]:
        """
        根据事件类型构建表单字段
        使用 match 语句进行类型分发

        表单内字段特点：
        1. 在表单内，通过提交按钮回调一次性处理
        2. 数据保存在 record_data 中
        3. 根据事件类型动态显示不同字段
        4. 受表单外字段状态影响（如指标类型影响指标值字段）
        """
        match event_type:
            case RoutineTypes.INSTANT | RoutineTypes.START:
                return self._build_instant_start_form_fields(record_data, is_confirmed)
            case RoutineTypes.ONGOING:
                return self._build_ongoing_form_fields(record_data, is_confirmed)
            case RoutineTypes.FUTURE:
                return self._build_future_form_fields(record_data, is_confirmed)
            case _:
                # 未知类型，返回空字段列表
                return []

    def _build_instant_start_form_fields(
        self, record_data: Dict, is_confirmed: bool
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

        # 2. 完成方式字段
        degree_value = record_data.get("degree", "")
        elements.append(
            self.parent.build_form_row(
                "完成方式",
                self.parent.build_input_element(
                    placeholder="请输入完成方式",
                    initial_value=str(degree_value) if degree_value else "",
                    disabled=is_confirmed,
                    action_data={},
                    name="degree",
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
        if target_type != "none":
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
        from Module.Services.constants import RoutineCheckCycle

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
        scheduled_time = record_data.get("scheduled_time", "")
        elements.append(
            self.parent.build_form_row(
                "计划时间",
                self.parent._build_date_picker_element(
                    placeholder="选择计划执行时间",
                    initial_date=scheduled_time,
                    disabled=is_confirmed,
                    action_data={},
                    name="scheduled_time",
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
                reminder_datetime = record_data.get("reminder_datetime", "")
                elements.append(
                    self.parent.build_form_row(
                        "提醒时间",
                        self.parent._build_date_picker_element(
                            placeholder="选择具体提醒时间",
                            initial_date=reminder_datetime,
                            disabled=is_confirmed,
                            action_data={},
                            name="reminder_datetime",
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
        构建提交按钮组（参考 record_card 的3个按钮布局）

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
                                        "card_config_key": "routine_direct_record",
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
                                        "card_config_key": "routine_direct_record",
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
        build_method_name = context.content.value.get(
            "container_build_method", self.default_update_build_method
        )
        business_data, card_id, error_response = self.parent.ensure_valid_context(
            context, "confirm_direct_record", build_method_name
        )
        if error_response:
            return error_response

        # 获取direct_record的数据源
        data_source, _ = self.parent.safe_get_business_data(
            business_data, CardConfigKeys.ROUTINE_DIRECT_RECORD
        )

        # 标记为已确认
        business_data["is_confirmed"] = True

        # 获取表单数据并合并到record_data中
        form_data = context.content.form_data
        record_data = data_source.get("record_data", {}).copy()
        record_data.update(form_data)

        # 调用业务层创建直接记录
        routine_business = self.parent.message_router.routine_record
        success, message = routine_business.create_direct_record(
            context.user_id, record_data
        )

        if not success:
            # 创建失败，返回错误
            new_card_dsl = self.parent.build_cancel_update_card_data(
                business_data, "confirm_direct_record", build_method_name
            )
            return self.parent.handle_card_operation_common(
                card_content=new_card_dsl,
                card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
                update_toast_type=ToastTypes.ERROR,
                toast_message=message,
            )

        # 创建成功，构建确认后的卡片
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

    # endregion
