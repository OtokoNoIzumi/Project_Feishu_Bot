# -*- coding: utf-8 -*-
"""
Direct Record Card
直接记录卡片
"""

from typing import Dict, Any, List
from Module.Services.constants import (
    CardConfigKeys,
    RoutineTypes,
    RoutineProgressTypes,
    DirectRecordFields,
    CardActions,
    RoutineReminderModes,
    ToastTypes,
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
        self.default_update_build_method = "update_direct_record_card"  # 默认更新构建方法

    def build_direct_record_card(
        self, business_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        直接记录卡片核心构建逻辑
        """
        # 使用 safe_get_business_data 处理递归嵌套的业务数据结构
        data_source, is_container_mode = self.parent.safe_get_business_data(
            business_data, CardConfigKeys.ROUTINE_DIRECT_RECORD
        )

        # 获取构建方法名称
        build_method_name = data_source.get(
            "container_build_method", self.default_update_build_method
        )

        # 获取基础数据
        event_name = data_source.get(DirectRecordFields.EVENT_NAME, "")
        event_type = data_source.get(DirectRecordFields.EVENT_TYPE, RoutineTypes.INSTANT)
        is_confirmed = data_source.get("is_confirmed", False)
        result = data_source.get("result", "取消")

        # 获取表单数据
        form_data = data_source.get("form_data", {})

        # 构建卡片头部
        header = self._build_direct_record_header(event_name, is_confirmed, result)

        # 构建卡片元素
        elements = self._build_direct_record_form_elements(
            form_data, event_name, event_type, is_confirmed
        )

        # 处理集成模式：检查是否有子业务数据
        sub_business_build_method = data_source.get("sub_business_build_method", "")
        if sub_business_build_method and hasattr(self.parent, sub_business_build_method):
            # 这里必须要用business_data，有很多最外层的通用方法在这里，不要偷懒。
            sub_elements = getattr(self.parent, sub_business_build_method)(business_data)
            elements.append({"tag": "hr", "margin": "6px 0px"})
            elements.extend(sub_elements)

        return self.parent.build_base_card_structure(elements, header, "12px")

    def _build_direct_record_header(
        self, event_name: str, is_confirmed: bool = False, result: str = "取消"
    ) -> Dict[str, Any]:
        """
        构建直接记录卡片头部
        """
        if is_confirmed:
            return self.parent.build_status_based_header("", is_confirmed, result)

        if event_name:
            return self.parent.build_card_header(
                f"📝 直接记录：{event_name}",
                "填写记录信息",
                "blue",
                "edit_outlined"
            )
        else:
            return self.parent.build_card_header(
                "📝 直接记录",
                "创建新的记录",
                "blue",
                "add_outlined"
            )

    def build_direct_record_elements(self, business_data: Dict[str, Any]) -> List[Dict]:
        """
        构建直接记录元素（别名方法，兼容现有调用）
        符合 sub_business_build_method 调用规范
        """
        # 使用 safe_get_business_data 处理递归嵌套的业务数据结构
        data_source, is_container_mode = self.parent.safe_get_business_data(
            business_data, CardConfigKeys.ROUTINE_DIRECT_RECORD
        )

        # 从处理后的数据源中提取所需参数
        form_data = data_source.get("form_data", {})
        event_name = data_source.get(DirectRecordFields.EVENT_NAME, "")
        event_type = data_source.get(DirectRecordFields.EVENT_TYPE, RoutineTypes.INSTANT)
        is_confirmed = data_source.get("is_confirmed", False)

        elements = self._build_direct_record_form_elements(form_data, event_name, event_type, is_confirmed)
        return elements

    def _build_direct_record_form_elements(
        self, form_data: Dict, event_name: str, event_type: str, is_confirmed: bool
    ) -> List[Dict]:
        """
        构建直接记录表单元素（内部实现）
        实现表单内外字段分离机制

        架构说明：
        - 表单外字段：非表单数据，有回调事件，状态保存在配置中
        - 表单内字段：表单数据，通过提交按钮回调一次性处理
        """
        elements = []

        # 1. 表单外字段区域（非表单数据，有回调事件，状态保存在配置中）
        elements.extend(self._build_non_form_fields(form_data, event_name, event_type, is_confirmed))

        # 2. 表单分隔线
        elements.append({"tag": "hr", "margin": "12px 0px"})

        # 3. 创建表单容器
        form_container = {"tag": "form", "elements": [], "name": "direct_record_form"}

        # 4. 表单内字段区域（表单数据，通过提交按钮回调一次性处理）
        form_fields = self._build_form_fields_by_type(event_type, form_data, is_confirmed)
        form_container["elements"].extend(form_fields)

        # 5. 提交按钮
        form_container["elements"].append(self._build_submit_button(is_confirmed))

        # 6. 添加表单容器到元素列表
        elements.append(form_container)

        return elements

    def _build_non_form_fields(
        self, form_data: Dict, event_name: str, event_type: str, is_confirmed: bool
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
                "📝 事件名称",
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
                "🏷️ 事件类型",
                self._build_event_type_selector(event_type, is_confirmed),
                width_list=["80px", "180px"],
            )
        )

        # 指标类型选择器（不在表单，有回调事件）
        progress_type = form_data.get(DirectRecordFields.PROGRESS_TYPE, RoutineProgressTypes.NONE)
        elements.append(
            self.parent.build_form_row(
                "📊 指标类型",
                self._build_progress_type_selector(progress_type, is_confirmed),
                width_list=["80px", "180px"],
            )
        )

        # 提醒模式选择器（仅未来事项，不在表单，有回调事件）
        if event_type == RoutineTypes.FUTURE:
            reminder_mode = form_data.get(DirectRecordFields.REMINDER_MODE, "off")
            elements.append(
                self.parent.build_form_row(
                    "🔔 提醒模式",
                    self._build_reminder_mode_selector(reminder_mode, is_confirmed),
                    width_list=["80px", "180px"],
                )
            )

        return elements

    def _build_event_type_selector(self, event_type: str, is_confirmed: bool) -> Dict[str, Any]:
        """
        构建事件类型选择器
        """
        options = [
            {"text": {"tag": "plain_text", "content": "⚡ 瞬间完成"}, "value": RoutineTypes.INSTANT},
            {"text": {"tag": "plain_text", "content": "▶️ 开始事项"}, "value": RoutineTypes.START},
            {"text": {"tag": "plain_text", "content": "🔄 长期持续"}, "value": RoutineTypes.ONGOING},
            {"text": {"tag": "plain_text", "content": "📅 未来事项"}, "value": RoutineTypes.FUTURE},
        ]

        action_data = {
            "card_action": CardActions.UPDATE_DIRECT_RECORD_TYPE,
            "card_config_key": CardConfigKeys.ROUTINE_DIRECT_RECORD,
            "container_build_method": self.default_update_build_method,
        }

        return self.parent.build_select_element(
            placeholder="选择事件类型",
            options=options,
            initial_value=event_type,
            disabled=is_confirmed,
            action_data=action_data,
            element_id="event_type_selector",
        )

    def _build_progress_type_selector(self, progress_type: str, is_confirmed: bool) -> Dict[str, Any]:
        """
        构建指标类型选择器
        """
        options = [
            {"text": {"tag": "plain_text", "content": "无指标"}, "value": RoutineProgressTypes.NONE},
            {"text": {"tag": "plain_text", "content": "数值记录"}, "value": RoutineProgressTypes.VALUE},
            {"text": {"tag": "plain_text", "content": "变化量"}, "value": RoutineProgressTypes.MODIFY},
        ]

        action_data = {
            "card_action": CardActions.UPDATE_PROGRESS_TYPE,
            "card_config_key": CardConfigKeys.ROUTINE_DIRECT_RECORD,
            "container_build_method": self.default_update_build_method,
        }

        return self.parent.build_select_element(
            placeholder="选择指标类型",
            options=options,
            initial_value=progress_type,
            disabled=is_confirmed,
            action_data=action_data,
            element_id="progress_type",
        )

    def _build_reminder_mode_selector(self, reminder_mode: str, is_confirmed: bool) -> Dict[str, Any]:
        """
        构建提醒模式选择器（仅未来事项）
        """
        options = [
            {"text": {"tag": "plain_text", "content": "关闭提醒"}, "value": RoutineReminderModes.OFF},
            {"text": {"tag": "plain_text", "content": "时间提醒"}, "value": RoutineReminderModes.TIME},
            {"text": {"tag": "plain_text", "content": "周期提醒"}, "value": RoutineReminderModes.CYCLE},
        ]

        action_data = {
            "card_action": CardActions.UPDATE_REMINDER_MODE,
            "card_config_key": CardConfigKeys.ROUTINE_DIRECT_RECORD,
            "container_build_method": self.default_update_build_method,
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
        self, event_type: str, form_data: Dict, is_confirmed: bool
    ) -> List[Dict]:
        """
        根据事件类型构建表单字段
        使用 match 语句进行类型分发

        表单内字段特点：
        1. 在表单内，通过提交按钮回调一次性处理
        2. 数据保存在 form_data 中
        3. 根据事件类型动态显示不同字段
        4. 受表单外字段状态影响（如指标类型影响指标值字段）
        """
        match event_type:
            case RoutineTypes.INSTANT | RoutineTypes.START:
                return self._build_instant_start_form_fields(form_data, is_confirmed)
            case RoutineTypes.ONGOING:
                return self._build_ongoing_form_fields(form_data, is_confirmed)
            case RoutineTypes.FUTURE:
                return self._build_future_form_fields(form_data, is_confirmed)
            case _:
                # 未知类型，返回空字段列表
                return []

    def _build_instant_start_form_fields(
        self, form_data: Dict, is_confirmed: bool
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
        duration_value = form_data.get("duration", "")
        elements.append(
            self.parent.build_form_row(
                "⏱️ 耗时",
                self.parent.build_input_element(
                    placeholder="请输入耗时（分钟）",
                    initial_value=str(duration_value) if duration_value else "",
                    disabled=is_confirmed,
                    action_data={},
                    name="duration"
                ),
                width_list=["80px", "180px"],
            )
        )

        # 2. 完成方式字段
        degree_value = form_data.get("degree", "")
        elements.append(
            self.parent.build_form_row(
                "✅ 完成方式",
                self.parent.build_input_element(
                    placeholder="请输入完成方式",
                    initial_value=str(degree_value) if degree_value else "",
                    disabled=is_confirmed,
                    action_data={},
                    name="degree"
                ),
                width_list=["80px", "180px"],
            )
        )

        # 3. 指标值字段（根据指标类型动态显示）
        progress_type = form_data.get(DirectRecordFields.PROGRESS_TYPE, RoutineProgressTypes.NONE)
        if progress_type != RoutineProgressTypes.NONE:
            # 根据指标类型设置不同的占位符
            if progress_type == RoutineProgressTypes.VALUE:
                placeholder_text = "最新数值"
            elif progress_type == RoutineProgressTypes.MODIFY:
                placeholder_text = "变化量（+/-）"
            else:
                placeholder_text = "指标值"

            progress_value = form_data.get(DirectRecordFields.PROGRESS_VALUE, "")
            elements.append(
                self.parent.build_form_row(
                    "📊 指标值",
                    self.parent.build_input_element(
                        placeholder=placeholder_text,
                        initial_value=str(progress_value) if progress_value else "",
                        disabled=is_confirmed,
                        action_data={},
                        name=DirectRecordFields.PROGRESS_VALUE
                    ),
                    width_list=["80px", "180px"],
                )
            )

        # 4. 备注字段
        note_value = form_data.get("note", "")
        elements.append(
            self.parent.build_form_row(
                "📝 备注",
                self.parent.build_input_element(
                    placeholder="请输入备注（可选）",
                    initial_value=str(note_value) if note_value else "",
                    disabled=is_confirmed,
                    action_data={},
                    name="note"
                ),
                width_list=["80px", "180px"],
            )
        )

        return elements

    def _build_ongoing_form_fields(
        self, form_data: Dict, is_confirmed: bool
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

        # 1. 间隔类型选择器
        interval_type = form_data.get("interval_type", "daily")
        elements.append(
            self.parent.build_form_row(
                "🔄 间隔类型",
                {
                    "tag": "select_static",
                    "name": "interval_type",
                    "placeholder": {"tag": "plain_text", "content": "选择间隔类型"},
                    "initial_option": interval_type,
                    "options": self._get_interval_type_options(),
                    "disabled": is_confirmed,
                },
                width_list=["80px", "180px"],
            )
        )

        # 2. 目标类型选择器
        target_type = form_data.get("target_type", "none")
        elements.append(
            self.parent.build_form_row(
                "🎯 目标类型",
                {
                    "tag": "select_static",
                    "name": "target_type",
                    "placeholder": {"tag": "plain_text", "content": "选择目标类型"},
                    "initial_option": target_type,
                    "options": self._get_target_type_options(),
                    "disabled": is_confirmed,
                },
                width_list=["80px", "180px"],
            )
        )

        # 3. 目标值字段（根据目标类型动态显示）
        if target_type != "none":
            placeholder_text = "目标时间（分钟）" if target_type == "time" else "目标次数"
            target_value = form_data.get("target_value", "")
            elements.append(
                self.parent.build_form_row(
                    "📈 目标值",
                    self.parent.build_input_element(
                        placeholder=placeholder_text,
                        initial_value=str(target_value) if target_value else "",
                        disabled=is_confirmed,
                        action_data={},
                        name="target_value"
                    ),
                    width_list=["80px", "180px"],
                )
            )

        # 4. 指标值字段（根据指标类型动态显示）
        progress_type = form_data.get(DirectRecordFields.PROGRESS_TYPE, RoutineProgressTypes.NONE)
        if progress_type != RoutineProgressTypes.NONE:
            if progress_type == RoutineProgressTypes.VALUE:
                placeholder_text = "最新数值"
            elif progress_type == RoutineProgressTypes.MODIFY:
                placeholder_text = "变化量（+/-）"
            else:
                placeholder_text = "指标值"

            progress_value = form_data.get(DirectRecordFields.PROGRESS_VALUE, "")
            elements.append(
                self.parent.build_form_row(
                    "📊 指标值",
                    self.parent.build_input_element(
                        placeholder=placeholder_text,
                        initial_value=str(progress_value) if progress_value else "",
                        disabled=is_confirmed,
                        action_data={},
                        name=DirectRecordFields.PROGRESS_VALUE
                    ),
                    width_list=["80px", "180px"],
                )
            )

        # 5. 备注字段
        note_value = form_data.get("note", "")
        elements.append(
            self.parent.build_form_row(
                "📝 备注",
                self.parent.build_input_element(
                    placeholder="请输入备注（可选）",
                    initial_value=str(note_value) if note_value else "",
                    disabled=is_confirmed,
                    action_data={},
                    name="note"
                ),
                width_list=["80px", "180px"],
            )
        )

        return elements

    def _get_interval_type_options(self) -> List[Dict]:
        """获取间隔类型选项"""
        return [
            {"text": {"tag": "plain_text", "content": "每日"}, "value": "daily"},
            {"text": {"tag": "plain_text", "content": "每周"}, "value": "weekly"},
            {"text": {"tag": "plain_text", "content": "每月"}, "value": "monthly"},
            {"text": {"tag": "plain_text", "content": "自定义"}, "value": "custom"},
        ]

    def _get_target_type_options(self) -> List[Dict]:
        """获取目标类型选项"""
        return [
            {"text": {"tag": "plain_text", "content": "无目标"}, "value": "none"},
            {"text": {"tag": "plain_text", "content": "时间目标"}, "value": "time"},
            {"text": {"tag": "plain_text", "content": "次数目标"}, "value": "count"},
        ]

    def _build_future_form_fields(
        self, form_data: Dict, is_confirmed: bool
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
        scheduled_time = form_data.get("scheduled_time", "")
        elements.append(
            self.parent.build_form_row(
                "📅 计划时间",
                self.parent._build_date_picker_element(
                    placeholder="选择计划执行时间",
                    initial_date=scheduled_time,
                    disabled=is_confirmed,
                    action_data={}
                ),
                width_list=["80px", "180px"],
            )
        )

        # 2. 重要性选择器
        priority = form_data.get("priority", "medium")
        elements.append(
            self.parent.build_form_row(
                "⭐ 重要性",
                self.parent.build_select_element(
                    placeholder="选择重要性",
                    options=self._get_priority_options(),
                    initial_value=priority,
                    disabled=is_confirmed,
                    action_data={},
                    name="priority"
                ),
                width_list=["80px", "180px"],
            )
        )

        # 3. 预估耗时字段
        duration_value = form_data.get("duration", "")
        elements.append(
            self.parent.build_form_row(
                "⏱️ 预估耗时",
                self.parent.build_input_element(
                    placeholder="预估耗时（分钟）",
                    initial_value=str(duration_value) if duration_value else "",
                    disabled=is_confirmed,
                    action_data={},
                    name="duration"
                ),
                width_list=["80px", "180px"],
            )
        )

        # 4. 提醒时间字段（根据提醒模式显示）
        reminder_mode = form_data.get(DirectRecordFields.REMINDER_MODE, RoutineReminderModes.OFF)
        if reminder_mode != RoutineReminderModes.OFF:
            reminder_time = form_data.get("reminder_time", "before_15min")
            elements.append(
                self.parent.build_form_row(
                    "⏰ 提醒时间",
                    self.parent.build_select_element(
                        placeholder="选择提醒时间",
                        options=self._get_reminder_time_options(),
                        initial_value=reminder_time,
                        disabled=is_confirmed,
                        action_data={},
                        name="reminder_time"
                    ),
                    width_list=["80px", "180px"],
                )
            )

            # 5. 提醒周期字段（周期模式下显示）
            if reminder_mode == RoutineReminderModes.CYCLE:
                reminder_cycle = form_data.get("reminder_cycle", [])
                elements.append(
                    self.parent.build_form_row(
                        "🔔 提醒周期",
                        self.parent.build_multi_select_element(
                            placeholder="选择提醒周期",
                            options=self._get_reminder_cycle_options(),
                            initial_values=reminder_cycle,
                            disabled=is_confirmed,
                            action_data={},
                            name="reminder_cycle"
                        ),
                        width_list=["80px", "180px"],
                    )
                )

        # 6. 备注字段
        note_value = form_data.get("note", "")
        elements.append(
            self.parent.build_form_row(
                "📝 备注",
                self.parent.build_input_element(
                    placeholder="请输入备注（可选）",
                    initial_value=str(note_value) if note_value else "",
                    disabled=is_confirmed,
                    action_data={},
                    name="note"
                ),
                width_list=["80px", "180px"],
            )
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
            {"text": {"tag": "plain_text", "content": "提前5分钟"}, "value": "before_5min"},
            {"text": {"tag": "plain_text", "content": "提前15分钟"}, "value": "before_15min"},
            {"text": {"tag": "plain_text", "content": "提前30分钟"}, "value": "before_30min"},
            {"text": {"tag": "plain_text", "content": "提前1小时"}, "value": "before_1hour"},
            {"text": {"tag": "plain_text", "content": "提前1天"}, "value": "before_1day"},
        ]

    def _get_reminder_cycle_options(self) -> List[Dict]:
        """获取提醒周期选项"""
        return [
            {"text": {"tag": "plain_text", "content": "每天"}, "value": "daily"},
            {"text": {"tag": "plain_text", "content": "每周"}, "value": "weekly"},
            {"text": {"tag": "plain_text", "content": "每月"}, "value": "monthly"},
            {"text": {"tag": "plain_text", "content": "工作日"}, "value": "weekdays"},
            {"text": {"tag": "plain_text", "content": "周末"}, "value": "weekends"},
        ]

    def _build_submit_button(self, is_confirmed: bool) -> Dict[str, Any]:
        """
        构建提交按钮组（参考 record_card 的3个按钮布局）

        按钮特点：
        1. 取消按钮：使用 callback 行为，触发取消处理
        2. 重置按钮：使用 form_action_type="reset"
        3. 确认按钮：使用 callback 行为，触发表单提交处理
        """
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
                                        "card_action": CardActions.CANCEL_DIRECT_RECORD,
                                        "card_config_key": CardConfigKeys.ROUTINE_DIRECT_RECORD,
                                        "container_build_method": self.default_update_build_method,
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
                                        "card_action": CardActions.CONFIRM_DIRECT_RECORD,
                                        "card_config_key": CardConfigKeys.ROUTINE_DIRECT_RECORD,
                                        "container_build_method": self.default_update_build_method,
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
    def update_direct_record_type(self, context: MessageContext_Refactor) -> ProcessResult:
        """处理事项类型变更回调"""
        return self._handle_direct_record_field_update(
            context,
            DirectRecordFields.EVENT_TYPE,
            "事项类型已更新"
        )

    def update_progress_type(self, context: MessageContext_Refactor) -> ProcessResult:
        """处理指标类型变更回调"""
        return self._handle_direct_record_field_update(
            context,
            DirectRecordFields.PROGRESS_TYPE,
            "指标类型已更新"
        )

    def update_reminder_mode(self, context: MessageContext_Refactor) -> ProcessResult:
        """处理提醒模式变更回调"""
        return self._handle_direct_record_field_update(
            context,
            DirectRecordFields.REMINDER_MODE,
            "提醒模式已更新"
        )

    def update_interval_type(self, context: MessageContext_Refactor) -> ProcessResult:
        """处理间隔类型变更回调"""
        return self._handle_direct_record_field_update(
            context,
            "interval_type",
            "间隔类型已更新"
        )

    def update_target_type(self, context: MessageContext_Refactor) -> ProcessResult:
        """处理目标类型变更回调"""
        return self._handle_direct_record_field_update(
            context,
            "target_type",
            "目标类型已更新"
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

    def _handle_direct_record_field_update(
        self,
        context: MessageContext_Refactor,
        field_key: str,
        toast_message: str
    ) -> ProcessResult:
        """通用字段更新处理方法"""
        # 提取选择的值
        extracted_value = context.content.value.get("option", "")
        if not extracted_value:
            extracted_value = context.content.value.get("value", "")
        
        if not extracted_value:
            return self.parent.create_error_result("未能获取选择的值")

        # 调用共享工具的字段更新方法
        return self.parent.update_card_field(
            context=context,
            field_key=field_key,
            extracted_value=extracted_value,
            sub_business_name=CardConfigKeys.ROUTINE_DIRECT_RECORD,
            toast_message=toast_message
        )
    # endregion