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

        # 3. 表单内字段区域（表单数据，通过提交按钮回调一次性处理）
        form_fields = self._build_form_fields_by_type(event_type, form_data, is_confirmed)
        elements.extend(form_fields)

        # 4. 提交按钮
        elements.append(self._build_submit_button(is_confirmed))

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
            {"text": "⚡ 瞬间完成", "value": RoutineTypes.INSTANT},
            {"text": "▶️ 开始事项", "value": RoutineTypes.START},
            {"text": "🔄 长期持续", "value": RoutineTypes.ONGOING},
            {"text": "📅 未来事项", "value": RoutineTypes.FUTURE},
        ]

        # 查找初始选择索引，对飞书来说，索引从1开始，所以需要+1
        initial_index = -1
        for i, option in enumerate(options):
            if option.get("value") == event_type:
                initial_index = i + 1
                break

        return {
            "tag": "select_static",
            "placeholder": {"tag": "plain_text", "content": "选择事件类型"},
            "options": [
                {
                    "text": {"tag": "plain_text", "content": opt["text"]},
                    "value": opt["value"]
                }
                for opt in options
            ],
            "initial_index": initial_index if initial_index >= 0 else 1,
            "disabled": is_confirmed,
            "behaviors": [
                {
                    "type": "callback",
                    "value": {
                        "card_action": CardActions.UPDATE_DIRECT_RECORD_TYPE,
                        "card_config_key": CardConfigKeys.ROUTINE_DIRECT_RECORD,
                        "container_build_method": self.default_update_build_method,
                    },
                }
            ] if not is_confirmed else [],
        }

    def _build_progress_type_selector(self, progress_type: str, is_confirmed: bool) -> Dict[str, Any]:
        """
        构建指标类型选择器
        """
        options = [
            {"text": "无指标", "value": RoutineProgressTypes.NONE},
            {"text": "数值记录", "value": RoutineProgressTypes.VALUE},
            {"text": "变化量", "value": RoutineProgressTypes.MODIFY},
        ]

        # 查找初始选择索引，对飞书来说，索引从1开始，所以需要+1
        initial_index = -1
        for i, option in enumerate(options):
            if option.get("value") == progress_type:
                initial_index = i + 1
                break

        return {
            "tag": "select_static",
            "placeholder": {"tag": "plain_text", "content": "选择指标类型"},
            "options": [
                {
                    "text": {"tag": "plain_text", "content": opt["text"]},
                    "value": opt["value"]
                }
                for opt in options
            ],
            "initial_index": initial_index if initial_index >= 0 else 1,
            "disabled": is_confirmed,
            "behaviors": [
                {
                    "type": "callback",
                    "value": {
                        "card_action": CardActions.UPDATE_PROGRESS_TYPE,
                        "card_config_key": CardConfigKeys.ROUTINE_DIRECT_RECORD,
                        "container_build_method": self.default_update_build_method,
                    },
                }
            ] if not is_confirmed else [],
        }

    def _build_reminder_mode_selector(self, reminder_mode: str, is_confirmed: bool) -> Dict[str, Any]:
        """
        构建提醒模式选择器（仅未来事项）
        """
        options = [
            {"text": "关闭提醒", "value": "off"},
            {"text": "时间提醒", "value": "time"},
            {"text": "周期提醒", "value": "cycle"},
        ]

        # 查找初始选择索引，对飞书来说，索引从1开始，所以需要+1
        initial_index = -1
        for i, option in enumerate(options):
            if option.get("value") == reminder_mode:
                initial_index = i + 1
                break

        return {
            "tag": "select_static",
            "placeholder": {"tag": "plain_text", "content": "选择提醒模式"},
            "options": [
                {
                    "text": {"tag": "plain_text", "content": opt["text"]},
                    "value": opt["value"]
                }
                for opt in options
            ],
            "initial_index": initial_index if initial_index >= 0 else 1,
            "disabled": is_confirmed,
            "behaviors": [
                {
                    "type": "callback",
                    "value": {
                        "card_action": CardActions.UPDATE_REMINDER_MODE,
                        "card_config_key": CardConfigKeys.ROUTINE_DIRECT_RECORD,
                        "container_build_method": self.default_update_build_method,
                    },
                }
            ] if not is_confirmed else [],
        }

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
        # 这是一个占位实现，将在任务6中完善
        elements = []

        # 添加一个更明显的占位提示
        elements.append(
            self.parent.build_form_row(
                "📋 表单字段",
                {
                    "tag": "markdown",
                    "content": "*瞬间完成/开始事项表单字段（将在任务6中实现）*",
                    "text_size": "small"
                },
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
        # 这是一个占位实现，将在任务7中完善
        elements = []

        # 添加一个更明显的占位提示
        elements.append(
            self.parent.build_form_row(
                "📋 表单字段",
                {
                    "tag": "markdown",
                    "content": "*长期持续事项表单字段（将在任务7中实现）*",
                    "text_size": "small"
                },
                width_list=["80px", "180px"],
            )
        )

        return elements

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
        # 这是一个占位实现，将在任务8中完善
        elements = []

        # 添加一个更明显的占位提示
        elements.append(
            self.parent.build_form_row(
                "📋 表单字段",
                {
                    "tag": "markdown",
                    "content": "*未来事项表单字段（将在任务8中实现）*",
                    "text_size": "small"
                },
                width_list=["80px", "180px"],
            )
        )

        return elements

    def _build_submit_button(self, is_confirmed: bool) -> Dict[str, Any]:
        """
        构建提交按钮

        按钮特点：
        1. 使用 callback 行为，触发表单提交处理
        2. 提交时触发 CONFIRM_DIRECT_RECORD 动作
        3. 确认后变为禁用状态
        """
        if is_confirmed:
            return {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "已提交"},
                "type": "default",
                "width": "fill",
                "size": "medium",
                "disabled": True,
            }

        return {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "确认记录"},
            "type": "primary",
            "width": "fill",
            "size": "medium",
            "disabled": False,
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
        }