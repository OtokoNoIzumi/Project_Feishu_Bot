"""
日常事项记录卡片管理器

处理日常事项记录相关的飞书卡片交互，包括：
1. 新事件定义卡片 - 完整的事件属性设置
2. 快速记录确认卡片 - 已存在事件的快速记录
3. 快速选择记录卡片 - 菜单触发的快捷事项选择
4. 查询结果展示卡片 - 替代文字查询的可视化界面
"""

import uuid
from typing import Dict, Any, List, Optional
from enum import Enum
import json

from .card_registry import BaseCardManager
from ..decorators import card_build_safe
from Module.Services.constants import (
    CardOperationTypes, ServiceNames, RoutineTypes,
    ToastTypes, CardConfigKeys
)
from Module.Business.processors import ProcessResult, MessageContext_Refactor, RouteResult
from Module.Services.service_decorators import require_service
from Module.Common.scripts.common import debug_utils
from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTriggerResponse


class RoutineCardMode(Enum):
    """日常事项卡片模式"""
    NEW_EVENT_DEFINITION = "new_event_definition"      # 新事件定义
    QUICK_RECORD_CONFIRM = "quick_record_confirm"      # 快速记录确认
    QUICK_SELECT_RECORD = "quick_select_record"        # 快速选择记录
    QUERY_RESULTS = "query_results"                    # 查询结果展示


class RoutineCardManager(BaseCardManager):
    """日常事项记录卡片管理器"""

    def __init__(self, app_controller=None, card_info=None, card_config_key=None, sender=None, message_router=None):
        super().__init__(app_controller, card_info, card_config_key, sender, message_router)
        # routine卡片不使用模板，而是直接生成完整的卡片DSL
        self.templates = {}

        # 分类选项配置
        self.default_categories = [
            {"text": {"tag": "plain_text", "content": "个人卫生"}, "value": "hygiene", "icon": {"tag": "standard_icon", "token": "bath_outlined"}},
            {"text": {"tag": "plain_text", "content": "健康管理"}, "value": "health", "icon": {"tag": "standard_icon", "token": "heart_outlined"}},
            {"text": {"tag": "plain_text", "content": "生活起居"}, "value": "living", "icon": {"tag": "standard_icon", "token": "home_outlined"}},
            {"text": {"tag": "plain_text", "content": "工作学习"}, "value": "work", "icon": {"tag": "standard_icon", "token": "laptop_outlined"}},
            {"text": {"tag": "plain_text", "content": "运动健身"}, "value": "fitness", "icon": {"tag": "standard_icon", "token": "run_outlined"}},
            {"text": {"tag": "plain_text", "content": "其他"}, "value": "other", "icon": {"tag": "standard_icon", "token": "more_outlined"}}
        ]

    @card_build_safe("日常事项卡片构建失败")
    def build_quick_record_confirm_card(self, route_result: RouteResult, context: MessageContext_Refactor, business_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建日常事项卡片"""
        # card_data是来自内部的方法，无论是用模板，还是raw。
        card_data = self._build_quick_record_confirm_card(business_data)
        card_content = {"type": "card_json", "data": card_data}
        # 接下来是把这个data处理到外部……这里不封装一层type和data，目前是为了后续步骤处理data。
        # 温柔安全的，先不改变签名。
        # 目前这个阶段并不是每个都用card_id，我应该先做好兼容。

        return self._handle_card_operation_common(
            card_content=card_content,
            card_operation_type=CardOperationTypes.SEND,
            update_toast_type='success',
            user_id=context.user_id,
            message_id=context.message_id,
            business_data=business_data
        )

    @card_build_safe("日常事项卡片构建失败")
    def build_card(self, route_result: RouteResult, context: MessageContext_Refactor, **kwargs) -> Dict[str, Any]:
        """构建日常事项卡片"""
        # 虽然有调用，但应该把这个视作特别业务的最后一步，后面是通用的流程，那么这里需要构建的信息就是card_content。
        business_data = kwargs.get('business_data', {})
        card_type = kwargs.get('card_type', RoutineCardMode.NEW_EVENT_DEFINITION.value)

        match card_type:
            case RoutineCardMode.NEW_EVENT_DEFINITION.value:
                card_content = self._build_new_event_definition_card(business_data)
            case RoutineCardMode.QUICK_SELECT_RECORD.value:
                card_content = self._build_quick_select_record_card(business_data)
            case RoutineCardMode.QUERY_RESULTS.value:
                card_content = self._build_query_results_card(business_data)
            case _:
                debug_utils.log_and_print(f"未知的routine卡片类型: {card_type}", log_level="WARNING")
                card_content = {}
        card_content = {"type": "card_json", "data": card_content}
        # card_id = self.sender.create_card_entity(card_content)
        # if card_id:
        #     user_service = self.app_controller.get_service(ServiceNames.USER_BUSINESS_PERMISSION)
        #     user_service.save_new_card_data(context.user_id, card_id, card_data)
        #     card_content = {"type": "card", "data": {"card_id": card_id}}
        # else:
        #     debug_utils.log_and_print(f"❌ 创建卡片实体失败", log_level="ERROR")

        return self._handle_card_operation_common(
            card_content=card_content,
            card_operation_type=CardOperationTypes.SEND,
            update_toast_type='success',
            user_id=context.user_id,
            message_id=context.message_id,
            business_data=business_data
        )

    def _build_new_event_definition_card(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """构建新事件定义卡片"""
        form_data = data.get('form_data', {})
        operation_id = data.get('operation_id', str(uuid.uuid4()))
        user_id = data.get('user_id', '')
        is_confirmed = data.get('is_confirmed', False)

        # 如果有初始事项名称，设置到form_data中
        initial_event_name = data.get('initial_event_name', '')
        if initial_event_name and not form_data.get('event_name'):
            form_data['event_name'] = initial_event_name

        # 获取当前选择的事件类型以控制字段显示
        selected_type = form_data.get('event_type', RoutineTypes.INSTANT)

        # 获取关联开始事项列表（如果当前类型是结束事项）
        related_start_items = []
        if selected_type == RoutineTypes.END and self.message_router:
            related_start_items = self.message_router.routine_record.get_related_start_events(user_id)

        # 构建卡片DSL
        card_dsl = {
            "schema": "2.0",
            "config": {
                "update_multi": True,
                "wide_screen_mode": True
            },
            "body": {
                "direction": "vertical",
                "padding": "16px 16px 16px 16px",
                "elements": self._build_new_event_form_elements(form_data, operation_id, user_id, selected_type, is_confirmed, related_start_items)
            },
            "header": {
                "title": {"tag": "plain_text", "content": "📝 新建日常事项"},
                "subtitle": {"tag": "plain_text", "content": "请填写事项信息"},
                "template": "blue",
                "icon": {"tag": "standard_icon", "token": "add-bold_outlined"}
            }
        }
        return card_dsl

    def _build_new_event_form_elements(self, form_data: Dict[str, Any], operation_id: str, user_id: str, selected_type: str, is_confirmed: bool, related_start_items: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """构建新事件定义表单元素"""
        elements = []

        # 标题
        elements.append({
            "tag": "markdown",
            "content": "**📝 请完善事项信息**",
            "text_align": "left",
            "text_size": "heading",
            "margin": "0px 0px 12px 0px"
        })

        elements.append({"tag": "hr", "margin": "0px 0px 16px 0px"})

        # 1. 事项名称
        elements.append(self._build_form_row(
            "🏷️ 事项名称",
            self._build_input_element(
                placeholder="输入事项名称",
                initial_value=form_data.get('event_name', ''),
                disabled=is_confirmed,
                action_data={"action": "update_event_name", "operation_id": operation_id}
            )
        ))

        # 2. 事项类型
        elements.append(self._build_form_row(
            "⚡ 事项类型",
            self._build_select_element(
                placeholder="选择事项类型",
                options=self._get_event_type_options(),
                initial_value=selected_type,
                disabled=is_confirmed,
                action_data={"action": "update_event_type", "operation_id": operation_id}
            )
        ))

        # 3. 所属分类
        elements.append(self._build_form_row(
            "📂 所属分类",
            self._build_select_element(
                placeholder="选择分类",
                options=self.default_categories,
                initial_value=form_data.get('category', ''),
                disabled=is_confirmed,
                action_data={"action": "update_category", "operation_id": operation_id}
            )
        ))

        # 4. 关联事项（仅结束事项显示）
        if selected_type == RoutineTypes.END:
            elements.append(self._build_form_row(
                "🔗 关联开始事项",
                self._build_select_element(
                    placeholder="选择关联的开始事项",
                    options=related_start_items or [],
                    initial_value=form_data.get('related_start_event', ''),
                    disabled=is_confirmed,
                    action_data={"action": "update_related_start", "operation_id": operation_id}
                )
            ))

        # # 5. 日常检查设置（瞬间完成和长期持续显示）
        # if selected_type in [RoutineTypes.INSTANT, RoutineTypes.ONGOING]:
        #     elements.append(self._build_form_row(
        #         "📋 日常检查",
        #         self._build_checkbox_element(
        #             text="加入日常检查清单",
        #             checked=form_data.get('include_in_daily_check', False),
        #             disabled=is_confirmed,
        #             action_data={"action": "update_daily_check", "operation_id": operation_id}
        #         )
        #     ))

        # 6. 未来时间设置（仅未来事项显示）
        if selected_type == RoutineTypes.FUTURE:
            elements.append(self._build_form_row(
                "⏰ 计划时间",
                self._build_date_picker_element(
                    placeholder="选择计划执行日期",
                    initial_date=form_data.get('future_date', ''),
                    disabled=is_confirmed,
                    action_data={"action": "update_future_date", "operation_id": operation_id}
                )
            ))

        # 7. 程度选项（除未来事项外都显示）
        if selected_type != RoutineTypes.FUTURE:
            elements.append(self._build_form_row(
                "📊 事项程度",
                self._build_input_element(
                    placeholder="输入程度选项，用逗号分隔（如：简单,中等,复杂）",
                    initial_value=form_data.get('degree_options', ''),
                    disabled=is_confirmed,
                    action_data={"action": "update_degree_options", "operation_id": operation_id}
                )
            ))

        # 8. 备注信息
        elements.append(self._build_form_row(
            "📝 备注信息",
            self._build_input_element(
                placeholder="添加备注信息（可选）",
                initial_value=form_data.get('notes', ''),
                disabled=is_confirmed,
                action_data={"action": "update_notes", "operation_id": operation_id}
            )
        ))

        # 分割线
        elements.append({"tag": "hr", "margin": "16px 0px 16px 0px"})

        # 操作按钮
        if not is_confirmed:
            elements.append(self._build_action_buttons(operation_id, user_id))
        else:
            # 确认成功提示
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "plain_text",
                    "content": f"✅ {data.get('confirmation_message', '事项创建成功！')}",
                    "text_size": "normal_v2",
                    "text_align": "center",
                    "text_color": "green"
                },
                "margin": "12px 0px 0px 0px",
                "border": "1px solid green",
                "corner_radius": "4px",
                "padding": "8px 12px 8px 12px"
            })

        return elements

    def _build_quick_record_confirm_card(self, business_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建快速记录确认卡片"""
        # 这里写一下加工属性的条件思路，还要注意卡片需要更新，在这里先跑通element_id的更新，否则就要全量了
        # 信息分展示、条件展示和交互，大概对应固定信息，stats信息和有效的record值。
        # 向后兼容的先跑通：按照已有代码先展示信息，最下面提供动态交互组件。
        # 如果是纯动态，这个方法就不会被反复调用；如果会反复调用，那么在卡片里要存的就不是record，而是data。
        # 对于enable的刷新也是全量更新比较有效率，而不是一个一个改的吗？
        # 如果要重新生成，那么也就意味着每一个子模块回调事件里的逻辑在主逻辑也有有一份。
        event_name = business_data.get('event_name', '')
        is_confirmed = business_data.get('is_confirmed', False)
        result = business_data.get('result', '取消')
        card_status = result if is_confirmed else "确认中"

        match card_status:
            case "确认":
                subtitle = "记录信息确认成功"
                color = "green"
                icon = "done_outlined"
            case "取消":
                subtitle = "操作已取消"
                color = "grey"
                icon = "close_outlined"
            case "确认中":
                subtitle = "请确认记录信息"
                color = "blue"
                icon = "edit_outlined"

        card_dsl = {
            "schema": "2.0",
            "config": {"update_multi": True, "wide_screen_mode": True},
            "body": {
                "direction": "vertical",
                "padding": "12px",
                "elements": self._build_quick_record_elements(event_name, business_data, card_status)
            },
            "header": {
                "title": {"tag": "plain_text", "content": f"添加记录：{event_name}"},
                "subtitle": {"tag": "plain_text", "content": subtitle},
                "template": color,
                "icon": {"tag": "standard_icon", "token": icon}
            }
        }
        return card_dsl

    def _build_quick_record_elements(self, event_name: str, business_data: Dict[str, Any], card_status: str) -> List[Dict[str, Any]]:
        """构建快速记录表单元素 - 条件化展示丰富信息"""
        # 解析业务层传递的数据
        # 等提交之后一口气用最新数据更新一次卡片。
        event_def = business_data.get('event_definition', {})
        user_id = business_data.get('user_id', '')
        is_confirmed = business_data.get('is_confirmed', False)

        # 业务层计算好的智能数据
        avg_duration = business_data.get('avg_duration', 0.0)
        degree_info = business_data.get('degree_info', {})
        cycle_info = business_data.get('cycle_info', {})
        new_record = business_data.get('new_record', {})
        event_type = event_def.get('type', RoutineTypes.INSTANT)

        elements = []

        # 1. 基础信息卡片
        elements.extend(self._build_basic_info_section(event_def, new_record))

        # 2. 条件化展示：时间预估信息（如果有历史数据，后续可以考虑做提交日志后动态重算，但现在还是算了）
        if avg_duration > 0:
            elements.extend(self._build_duration_info_section(avg_duration))

        # 3. 条件化展示：目标进度信息（如果有目标设置）
        if cycle_info:
            elements.extend(self._build_cycle_progress_section(cycle_info))

        # === 确认输入部分 ===
        # 4. 条件化展示：程度选择器（如果有程度选项）
        if degree_info:
            elements.extend(self._build_degree_selection_section(degree_info, business_data, is_confirmed))

        # 创建表单容器
        form_elements = {
            "tag": "form",
            "elements": [],
            "name": "record_form"
        }

        # 5. 条件化展示：程度输入区域（如果有程度选项且选择了"其他"）
        if degree_info:
            selected_degree = degree_info.get('selected_degree', '')
            if selected_degree == '其他':
                form_elements['elements'].extend(self._build_degree_input_section(new_record.get('custom_degree', ''), is_confirmed))

        # 6. 条件化展示：持续时间输入区域
        if event_type in [RoutineTypes.INSTANT, RoutineTypes.END, RoutineTypes.START]:
            form_elements['elements'].extend(self._build_duration_input_section(new_record.get('duration', ''), is_confirmed))

        # 7. 条件化展示：备注输入区域
        form_elements['elements'].extend(self._build_note_input_section(new_record.get('note', ''), is_confirmed))

        # 8. 操作按钮或确认提示
        # if not is_confirmed:  对于表单组件，必须要有提交按钮，否则会报错，所以要用disabled来控制，而不是省略。
        form_elements['elements'].append(self._build_record_action_buttons(user_id, event_name, is_confirmed))

        # 只有当表单有内容时才添加表单容器
        if form_elements['elements']:
            elements.append(form_elements)
        if not is_confirmed:
            elements.append({"tag": "markdown", "content": "**💡 重要提示** 请先选择完成日程的方式，这会清除下面所有的值！"})

        return elements

    def _build_basic_info_section(self, event_def: Dict[str, Any], new_record: Dict[str, Any]) -> List[Dict[str, Any]]:
        """构建基础信息区域"""
        elements = []

        # 事项类型显示
        event_type = event_def.get('type', RoutineTypes.INSTANT)

        # 基础信息卡片
        info_content = f"**事项类型：** {self._get_type_display_name(event_type)}\n"

        # 显示记录ID（用户友好的序号）
        if new_record.get('record_id'):
            record_number = new_record['record_id'].split('_')[-1]  # 提取序号部分
            info_content += f"**记录编号：** #{record_number}\n"

        # 显示记录时间
        if new_record.get('timestamp'):
            timestamp = new_record['timestamp']
            split_timestamp = timestamp.split(' ')
            date_str = split_timestamp[0][5:10]
            time_str = split_timestamp[1][0:5]
            info_content += f"**记录时间：** {date_str} {time_str}\n" # 格式化时间显示：今天 14:30

        # 显示分类（如果有）
        category = event_def.get('category', '')
        if category:
            info_content += f"**分类：** <text_tag color='blue'>{category}</text_tag>\n"

        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": info_content.rstrip('\n')
            },
        })

        return elements

    def _build_duration_info_section(self, avg_duration: float) -> List[Dict[str, Any]]:
        """构建时间预估信息区域"""
        elements = []

        # 格式化时长显示，更加用户友好
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

        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"⏱️ **预估用时：** {duration_str}"
            },
            "element_id": "duration_info"
        })

        return elements

    def _build_cycle_progress_section(self, cycle_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """构建循环进度信息区域"""
        elements = []

        # 基础数据提取
        cycle_count = max(0, int(cycle_info.get('cycle_count', 0)))
        target_type = cycle_info.get('target_type', '')
        target_value = cycle_info.get('target_value')
        last_cycle_info = cycle_info.get('last_cycle_info', '')

        # 判断是否有目标
        has_target = target_value and int(target_value) > 0

        # 构建主要进度内容
        progress_content_parts = []

        if has_target:
            # 有目标：显示目标进度
            target_val = max(1, int(target_value))
            progress_percent = min(100, (cycle_count / target_val * 100))
            target_type_display = {"count": "次数", "duration": "时长", "other": "其他"}.get(target_type, target_type)

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

            progress_content_parts.append(f"🎯 **{target_type_display}目标：** {cycle_count}/{target_val}")

            # 进度条
            filled_blocks = int(progress_percent // 10)
            progress_bar = "●" * filled_blocks + "○" * (10 - filled_blocks)
            progress_content_parts.append(f"📊 <font color={color}>{progress_bar}</font> {progress_percent:.0f}% {status_emoji}")
        else:
            # 无目标：显示累计进度
            unit_display = {"count": "次", "duration": "分钟", "other": ""}.get(target_type, "")
            progress_content_parts.append(f"📊 **累计进度：** {cycle_count}{unit_display}")

        # 组装最终内容
        progress_content = "\n".join(progress_content_parts)
        if last_cycle_info and last_cycle_info.strip():
            progress_content += f"\n📈 {last_cycle_info}"

        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": progress_content
            },
        })

        return elements

    def _build_degree_selection_section(self, degree_info: Dict[str, Any], business_data: Dict[str, Any], is_confirmed: bool) -> List[Dict[str, Any]]:
        """构建程度选择区域"""
        elements = []

        degree_options = degree_info.get('degree_options', []).copy()
        if '其他' not in degree_options:
            degree_options.append('其他')
        default_degree = degree_info.get('default_degree', '')
        event_name = business_data.get('event_name', '')

        # 构建选项
        degree_select_options = []
        for degree in degree_options:
            degree_select_options.append({
                "text": {"tag": "plain_text", "content": degree},
                "value": degree
            })

        # 智能默认值：用户上次选择 > 系统默认 > 第一个选项
        initial_degree = business_data['degree_info'].get('selected_degree',"") or default_degree

        elements.append(self._build_form_row(
            "选择方式",
            self._build_select_element(
                placeholder=f"如何{event_name}？",
                options=degree_select_options,
                initial_value=initial_degree,
                disabled=is_confirmed,
                action_data={
                    "card_action": "update_record_degree",
                    "card_config_key": CardConfigKeys.ROUTINE_RECORD,
                    # "origin_data": data
                },
                element_id="degree_select"
            ),
            width_list=["80px", "180px"],
            element_id="degree_select_row"
        ))

        return elements

    def update_record_degree(self, context: MessageContext_Refactor):
        """处理记录方式更新"""
        # 对于选择其他的情况，要在卡片界面显示一个新元素，让用户输入。这很可能要全面更新卡片，因为没有元素。
        # origin_data = context.content.value.get('origin_data', {})
        # 避免重复值触发。
        card_data, card_id, card_info = self._get_core_data(context)
        if not card_data:
            debug_utils.log_and_print(f"🔍 update_record_degree - 卡片数据为空", log_level="WARNING")
            return
        new_option = context.content.value.get('option')

        card_data['new_record']['degree'] = new_option
        card_data['degree_info']['selected_degree'] = new_option
        user_service = self.app_controller.get_service(ServiceNames.USER_BUSINESS_PERMISSION)
        user_service.save_new_card_data(context.user_id, card_id, card_data)
        new_card_dsl = self._build_quick_record_confirm_card(card_data)

        return self._handle_card_operation_common(
            card_content=new_card_dsl,
            card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
            update_toast_type=ToastTypes.SUCCESS,
            toast_message=f"完成方式更新成功！"
        )

    def _build_degree_input_section(self, initial_value: str = '', is_confirmed: bool = False) -> List[Dict[str, Any]]:
        """构建程度输入区域"""
        # 这里要改成容器了，而没有单独的事件。
        elements = []

        elements.append(self._build_form_row(
            "新方式",
            self._build_input_element(
                placeholder="添加新方式",
                initial_value=initial_value,
                disabled=is_confirmed,
                action_data={
                    "card_action": "add_new_degree",
                    "card_config_key": CardConfigKeys.ROUTINE_RECORD,
                },
                element_id="degree_input",
                name="custom_degree"
            ),
            width_list=["80px", "180px"],
            element_id="degree_input_row"
        ))

        return elements

    def add_new_degree(self, context: MessageContext_Refactor):
        """处理记录耗时更新"""
        card_data, card_id, _ = self._get_core_data(context)
        if not card_data:
            debug_utils.log_and_print(f"🔍 add_new_degree - 卡片数据为空", log_level="WARNING")
            return
        new_degree = context.content.value.get('value')
        new_card_dsl = {"message": "异步更新中..."}
        if  new_degree:
            card_data['new_record']['custom_degree'] = new_degree
            user_service = self.app_controller.get_service(ServiceNames.USER_BUSINESS_PERMISSION)
            user_service.save_new_card_data(context.user_id, card_id, card_data)

        return self._handle_card_operation_common(
            card_content=new_card_dsl,
            card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
            update_toast_type=ToastTypes.SUCCESS,
            toast_message=f"添加新的完成方式成功！"
        )

    def _build_duration_input_section(self,initial_value: str = '', is_confirmed: bool = False) -> List[Dict[str, Any]]:
        """构建持续时间输入区域"""
        elements = []

        elements.append(self._build_form_row(
            "⏱️ 耗时",
            self._build_input_element(
                placeholder="记录耗时(分钟)",
                initial_value=initial_value,
                disabled=is_confirmed,
                action_data={
                    "card_action": "update_record_duration",
                    "card_config_key": CardConfigKeys.ROUTINE_RECORD,
                },
                element_id="duration_input",
                name="duration"
            ),
            width_list=["80px", "180px"]
        ))

        return elements

    def update_record_duration(self, context: MessageContext_Refactor):
        """处理记录耗时更新"""
        card_data, card_id, _ = self._get_core_data(context)
        if not card_data:
            debug_utils.log_and_print(f"🔍 update_record_duration - 卡片数据为空", log_level="WARNING")
            return
        new_duration = context.content.value.get('value')
        new_card_dsl = {"message": "异步更新中..."}
        if  new_duration.strip().isdigit():
            card_data['new_record']['duration'] = int(new_duration)
            user_service = self.app_controller.get_service(ServiceNames.USER_BUSINESS_PERMISSION)
            user_service.save_new_card_data(context.user_id, card_id, card_data)

        return self._handle_card_operation_common(
            card_content=new_card_dsl,
            card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
            update_toast_type=ToastTypes.SUCCESS,
            toast_message=f"耗时更新成功！"
        )

    def _build_note_input_section(self, initial_value: str = '', is_confirmed: bool = False) -> List[Dict[str, Any]]:
        """构建备注输入区域"""
        elements = []

        elements.append(self._build_form_row(
            "📝 备注",
            self._build_input_element(
                placeholder="添加备注信息",
                initial_value=initial_value,
                disabled=is_confirmed,
                action_data={
                    "card_action": "update_record_note",
                    "card_config_key": CardConfigKeys.ROUTINE_RECORD,
                },
                element_id="note_input",
                name="note"
            ),
            width_list=["80px", "180px"]
        ))

        return elements

    def update_record_note(self, context: MessageContext_Refactor):
        """处理记录耗时更新"""
        card_data, card_id, _ = self._get_core_data(context)
        if not card_data:
            debug_utils.log_and_print(f"🔍 update_record_note - 卡片数据为空", log_level="WARNING")
            return
        new_note = context.content.value.get('value')
        new_card_dsl = {"message": "异步更新中..."}
        if  new_note:
            card_data['new_record']['note'] = new_note
            user_service = self.app_controller.get_service(ServiceNames.USER_BUSINESS_PERMISSION)
            user_service.save_new_card_data(context.user_id, card_id, card_data)

        return self._handle_card_operation_common(
            card_content=new_card_dsl,
            card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
            update_toast_type=ToastTypes.SUCCESS,
            toast_message=f"备注更新成功！"
        )

    def _build_record_action_buttons(self, user_id: str, event_name: str, is_confirmed: bool = False) -> Dict[str, Any]:
        """构建记录操作按钮组"""
        return {
            "tag": "column_set",
            "horizontal_align": "left",
            "columns": [
                {
                    "tag": "column",
                    "width": "auto",
                    "elements": [{
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "取消"},
                        "type": "danger",
                        "width": "default",
                        "icon": {"tag": "standard_icon", "token": "close-bold_outlined"},
                        "disabled": is_confirmed,
                        "behaviors": [{
                            "type": "callback",
                            "value": {
                                "card_action": "cancel_record",
                                "card_config_key": CardConfigKeys.ROUTINE_RECORD,
                            }
                        }],
                        "name": "cancel_record"
                    }],
                    "vertical_spacing": "8px",
                    "horizontal_align": "left",
                    "vertical_align": "top"
                },
                {
                    "tag": "column",
                    "width": "auto",
                    "elements": [{
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "重置"},
                        "type": "default",
                        "width": "default",
                        "disabled": is_confirmed,
                        "form_action_type": "reset",
                        "name": "reset_form"
                    }],
                    "vertical_spacing": "8px",
                    "horizontal_align": "left",
                    "vertical_align": "top"
                },
                {
                    "tag": "column",
                    "width": "auto",
                    "elements": [{
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "确认"},
                        "type": "primary",
                        "width": "default",
                        "icon": {"tag": "standard_icon", "token": "done_outlined"},
                        "disabled": is_confirmed,
                        "behaviors": [{
                            "type": "callback",
                            "value": {
                                "card_action": "confirm_record",
                                "card_config_key": CardConfigKeys.ROUTINE_RECORD,
                                "event_name": event_name
                            }
                        }],
                        "form_action_type": "submit",
                        "name": "confirm_record"
                    }],
                    "vertical_spacing": "8px",
                    "horizontal_align": "left",
                    "vertical_align": "top"
                }
            ]
        }

    def confirm_record(self, context: MessageContext_Refactor) -> ProcessResult:
        """处理记录确认"""

        card_data, card_id, card_info = self._get_core_data(context)
        core_data = card_data.get('new_record', {})
        if not core_data:
            # 其实应该假设card_id也失效了，用message_id直接batch，但是这里先不处理。
            debug_utils.log_and_print(f"🔍 confirm_record - 卡片数据为空", log_level="WARNING")
            card_data['is_confirmed'] = True
            card_data['result'] = "取消"
            new_card_dsl = self._build_quick_record_confirm_card(card_data)

            return self._handle_card_operation_common(
                card_content=new_card_dsl,
                card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
                update_toast_type=ToastTypes.ERROR,
                toast_message="操作已失效"
            )

        event_def = card_data.get('event_definition', {})
        form_data = context.content.form_data

        user_id = context.user_id
        new_degree = core_data.get('degree', '')
        if new_degree:
            if new_degree == '其他':
                # 其他留空的情况不增加定义

                core_data['degree'] = form_data.get('custom_degree', "其他")
                if form_data.get('custom_degree', "其他") != "其他":
                    event_def['properties']['degree_options'].append(form_data.get('custom_degree', "其他"))
            else:
                core_data['degree'] = new_degree
        core_data['duration'] = int(form_data.get('duration', 0))
        core_data['note'] = form_data.get('note', "")

        # 开始写入数据
        # 先写入记录
        records_data = self.message_router.routine_record._load_event_records(user_id)
        records_data['records'].append(core_data)
        # 再写入事件定义，做聚合类计算
        event_def['stats']['record_count'] = event_def.get('stats',{}).get('record_count', 0) + 1
        cycle_info = card_data.get('cycle_info', {})
        if cycle_info:
            event_def['stats']['cycle_count'] = cycle_info.get('cycle_count', 0) + 1
            event_def['stats']['last_cycle_count'] = cycle_info.get('last_cycle_count', 0)
            event_def['stats']['last_refresh_date'] = cycle_info.get('last_refresh_date', "")

        # event_def['stats']['last_progress_value'] = event_def.get('stats',{}).get('last_progress_value', 0) + core_data.get('duration', 0)
        event_def['stats']['last_note'] = core_data.get('note', "")

        new_duration = core_data.get('duration', 0)
        if new_duration > 0:
            event_duration_info = event_def.get('stats',{}).get('duration',{})
            recent_durations = event_duration_info.get('recent_values',[])
            recent_durations.append(new_duration)
            if len(recent_durations) > event_duration_info.get('window_size', 10):
                recent_durations.pop(0)
            event_duration_info['recent_values'] = recent_durations
            try:
                total_duration = event_duration_info.get('avg_all_time', 0)*event_duration_info.get('duration_count', 0) + new_duration
            except TypeError:
                total_duration = new_duration
            event_duration_info['duration_count'] = event_duration_info.get('duration_count', 0) + 1
            event_duration_info['avg_all_time'] = total_duration/event_duration_info['duration_count']

        self.message_router.routine_record._save_event_records(user_id, records_data)
        event_def['last_updated'] = self.message_router.routine_record._get_formatted_time()
        full_event_def = self.message_router.routine_record._load_event_definitions(user_id)
        full_event_def['definitions'][event_def['name']] = event_def
        full_event_def['last_updated'] = self.message_router.routine_record._get_formatted_time()
        self.message_router.routine_record._save_event_definitions(user_id, full_event_def)

        card_data['is_confirmed'] = True
        card_data['result'] = "确认"
        event_name = context.content.value.get('event_name', '')

        new_card_dsl = self._build_quick_record_confirm_card(card_data)
        user_service = self.app_controller.get_service(ServiceNames.USER_BUSINESS_PERMISSION)
        user_service.del_card_data(context.user_id, card_id)


        return self._handle_card_operation_common(
            card_content=new_card_dsl,
            card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
            update_toast_type=ToastTypes.SUCCESS,
            toast_message=f"'{event_name}' 记录成功！"
        )

    def cancel_record(self, context: MessageContext_Refactor) -> ProcessResult:
        """处理取消操作"""
        card_data, card_id, card_info = self._get_core_data(context)
        if not card_data:
            debug_utils.log_and_print(f"🔍 cancel_record - 卡片数据为空", log_level="WARNING")

        card_data['is_confirmed'] = True
        card_data['result'] = "取消"
        new_card_dsl = self._build_quick_record_confirm_card(card_data)

        user_service = self.app_controller.get_service(ServiceNames.USER_BUSINESS_PERMISSION)
        user_service.del_card_data(context.user_id, card_id)

        return self._handle_card_operation_common(
            card_content=new_card_dsl,
            card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
            update_toast_type=ToastTypes.INFO,
            toast_message="操作已取消"
        )

    def _build_confirmation_message(self, card_status: str) -> Dict[str, Any]:
        """构建确认成功提示"""
        result_msg = {
            "确认": "✅ 记录成功！",
            "取消": "❌ 操作已取消",
        }
        result_color = {
            "确认": "green",
            "取消": "grey",
        }

        return {
            "tag": "div",
            "text": {
                "tag": "plain_text",
                "content": f"{result_msg.get(card_status, '❌ 记录失败！')}",
                "text_size": "normal_v2",
                "text_align": "center",
                "text_color": result_color.get(card_status, 'grey')
            },
        }

    def _build_quick_select_record_card(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """构建快速选择记录卡片"""
        quick_events = data.get('quick_events', [])
        operation_id = data.get('operation_id', str(uuid.uuid4()))
        user_id = data.get('user_id', '')

        card_dsl = {
            "schema": "2.0",
            "config": {"update_multi": True, "wide_screen_mode": True},
            "body": {
                "direction": "vertical",
                "padding": "16px 16px 16px 16px",
                "elements": self._build_quick_select_elements(quick_events, operation_id, user_id)
            },
            "header": {
                "title": {"tag": "plain_text", "content": "🚀 快速记录"},
                "subtitle": {"tag": "plain_text", "content": "选择或新建事项"},
                "template": "purple",
                "icon": {"tag": "standard_icon", "token": "flash_outlined"}
            }
        }

        return card_dsl

    def _build_quick_select_elements(self, quick_events: List[Dict[str, Any]], operation_id: str, user_id: str) -> List[Dict[str, Any]]:
        """构建快速选择表单元素"""
        elements = []

        # 标题
        elements.append({
            "tag": "markdown",
            "content": "**🚀 快速记录事项**",
            "text_align": "left",
            "text_size": "heading",
            "margin": "0px 0px 12px 0px"
        })

        elements.append({"tag": "hr", "margin": "0px 0px 16px 0px"})

        # 新建事项输入框
        elements.append(self._build_form_row(
            "🆕 新建事项",
            self._build_input_element(
                placeholder="输入新事项名称",
                initial_value="",
                disabled=False,
                action_data={"action": "new_event_input", "operation_id": operation_id}
            )
        ))

        # 分割线
        elements.append({
            "tag": "markdown",
            "content": "**或选择现有事项：**",
            "text_align": "left",
            "margin": "16px 0px 8px 0px"
        })

        # 快速事项按钮组
        if quick_events:
            for i, event in enumerate(quick_events):
                event_name = event.get('name', '')
                event_type = event.get('type', RoutineTypes.INSTANT)
                type_emoji = {"instant": "⚡", "start": "▶️", "end": "⏹️", "ongoing": "🔄", "future": "📅"}.get(event_type, "📝")
                is_quick_access = event.get('properties', {}).get('quick_access', False)

                # 快捷访问标记
                prefix = "⭐" if is_quick_access else "📋"

                button = {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": f"{prefix} {type_emoji} {event_name}"},
                    "type": "primary" if is_quick_access else "default",
                    "width": "fill",
                    "size": "medium",
                    "margin": "4px 0px 4px 0px",
                    "behaviors": [{
                        "type": "callback",
                        "value": {
                            "action": "select_quick_event",
                            "operation_id": operation_id,
                            "event_name": event_name,
                            "user_id": user_id
                        }
                    }]
                }

                elements.append(button)

        # 取消按钮
        elements.append({
            "tag": "button",
            "text": {"tag": "plain_text", "content": "取消"},
            "type": "danger",
            "width": "default",
            "size": "medium",
            "margin": "16px 0px 0px 0px",
            "behaviors": [{
                "type": "callback",
                "value": {
                    "action": "cancel_quick_select",
                    "operation_id": operation_id
                }
            }]
        })

        return elements

    def _build_query_results_card(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """构建查询结果展示卡片"""
        results = data.get('results', [])
        query_type = data.get('query_type', 'recent')

        card_dsl = {
            "schema": "2.0",
            "config": {"update_multi": True, "wide_screen_mode": True},
            "body": {
                "direction": "vertical",
                "padding": "16px 16px 16px 16px",
                "elements": self._build_query_results_elements(results, query_type)
            },
            "header": {
                "title": {"tag": "plain_text", "content": "📋 日常事项查询结果"},
                "subtitle": {"tag": "plain_text", "content": f"共找到 {len(results)} 个事项"},
                "template": "cyan",
                "icon": {"tag": "standard_icon", "token": "search_outlined"}
            }
        }

        return card_dsl

    def _build_query_results_elements(self, results: List[Dict[str, Any]], query_type: str) -> List[Dict[str, Any]]:
        """构建查询结果元素"""
        elements = []

        if not results:
            elements.append({
                "tag": "markdown",
                "content": "**📝 暂无事项记录**\n\n使用菜单或发送 'r 事项名称' 来创建第一个记录",
                "text_align": "center",
                "margin": "20px 0px 20px 0px"
            })
            return elements

        # 标题
        elements.append({
            "tag": "markdown",
            "content": f"**📋 {query_type.upper()}事项列表**",
            "text_align": "left",
            "text_size": "heading",
            "margin": "0px 0px 12px 0px"
        })

        elements.append({"tag": "hr", "margin": "0px 0px 16px 0px"})

        # 结果列表
        for i, item in enumerate(results):
            event_name = item.get('event_name', '')
            event_def = item.get('event_definition', {})
            last_record = item.get('last_record', {})

            event_type = event_def.get('type', RoutineTypes.INSTANT)
            type_emoji = {"instant": "⚡", "start": "▶️", "end": "⏹️", "ongoing": "🔄", "future": "📅"}.get(event_type, "📝")

            # 格式化最后记录时间
            last_time = "无记录"
            if last_record:
                timestamp = last_record.get('timestamp', '')
                if len(timestamp) >= 16:
                    last_time = f"{timestamp[5:10]} {timestamp[11:16]}"

            # 记录数量
            record_count = event_def.get('record_count', 0)

            # 可折叠的详情卡片
            detail_elements = [
                {
                    "tag": "column_set",
                    "horizontal_spacing": "8px",
                    "columns": [
                        {
                            "tag": "column",
                            "width": "auto",
                            "elements": [{
                                "tag": "markdown",
                                "content": f"**{type_emoji} {event_name}**",
                                "text_size": "normal_v2"
                            }]
                        },
                        {
                            "tag": "column",
                            "width": "auto",
                            "elements": [{
                                "tag": "markdown",
                                "content": f"共{record_count}次 | 最近: {last_time}",
                                "text_size": "small",
                                "text_color": "grey"
                            }]
                        }
                    ]
                }
            ]

            # 如果有程度选项，显示
            degree_options = event_def.get('properties', {}).get('degree_options', [])
            if degree_options:
                detail_elements.append({
                    "tag": "markdown",
                    "content": f"**程度选项：** {', '.join(degree_options)}",
                    "text_size": "small",
                    "margin": "4px 0px 0px 0px"
                })

            # # 折叠元素
            # collapsible_element = {
            #     "tag": "collapsible_panel",
            #     "expanded": False,
            #     "header": {
            #         "elements": detail_elements[:1]  # 只显示标题行
            #     },
            #     "body": {
            #         "direction": "vertical",
            #         "elements": detail_elements[1:] if len(detail_elements) > 1 else [
            #             {"tag": "markdown", "content": "暂无更多详细信息", "text_size": "small", "text_color": "grey"}
            #         ]
            #     },
            #     "margin": "0px 0px 8px 0px"
            # }

            # elements.append(collapsible_element)

        return elements

    def _build_select_element(self, placeholder: str, options: List[Dict[str, Any]], initial_value: str, disabled: bool, action_data: Dict[str, Any], element_id: str = '') -> Dict[str, Any]:
        """构建选择器元素"""
        # 查找初始选择索引，对飞书来说，索引从1开始，所以需要+1
        initial_index = -1
        for i, option in enumerate(options):
            if option.get('value') == initial_value:
                initial_index = i + 1
                break

        return {
            "tag": "select_static",
            "element_id": element_id,
            "placeholder": {"tag": "plain_text", "content": placeholder},
            "options": options,
            "initial_index": initial_index if initial_index >= 0 else None,
            "width": "fill",
            "disabled": disabled,
            "behaviors": [{"type": "callback", "value": action_data}]
        }

    def _build_date_picker_element(self, placeholder: str, initial_date: str, disabled: bool, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建日期选择器元素"""
        element = {
            "tag": "date_picker",
            "placeholder": {"tag": "plain_text", "content": placeholder},
            "disabled": disabled,
            "behaviors": [{"type": "callback", "value": action_data}]
        }

        if initial_date:
            element["initial_date"] = initial_date

        return element

    def _build_action_buttons(self, operation_id: str, user_id: str) -> Dict[str, Any]:
        """构建操作按钮组"""
        return {
            "tag": "column_set",
            "flex_mode": "stretch",
            "horizontal_spacing": "12px",
            "columns": [
                {
                    "tag": "column",
                    "width": "auto",
                    "elements": [{
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "取消"},
                        "type": "danger",
                        "width": "default",
                        "size": "medium",
                        "icon": {"tag": "standard_icon", "token": "close-bold_outlined"},
                        "behaviors": [{
                            "type": "callback",
                            "value": {
                                "action": "cancel_new_event",
                                "operation_id": operation_id
                            }
                        }]
                    }],
                    "horizontal_align": "left"
                },
                {
                    "tag": "column",
                    "width": "auto",
                    "elements": [{
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "确认创建"},
                        "type": "primary",
                        "width": "default",
                        "size": "medium",
                        "icon": {"tag": "standard_icon", "token": "done_outlined"},
                        "behaviors": [{
                            "type": "callback",
                            "value": {
                                "action": "confirm_new_event",
                                "operation_id": operation_id,
                                "user_id": user_id
                            }
                        }]
                    }],
                    "horizontal_align": "right"
                }
            ]
        }

    def _get_event_type_options(self) -> List[Dict[str, Any]]:
        """获取事件类型选项"""
        return [
            {
                "text": {"tag": "plain_text", "content": "⚡ 瞬间完成"},
                "value": RoutineTypes.INSTANT,
                "icon": {"tag": "standard_icon", "token": "lightning_outlined"}
            },
            {
                "text": {"tag": "plain_text", "content": "▶️ 开始事项"},
                "value": RoutineTypes.START,
                "icon": {"tag": "standard_icon", "token": "play_outlined"}
            },
            {
                "text": {"tag": "plain_text", "content": "⏹️ 结束事项"},
                "value": RoutineTypes.END,
                "icon": {"tag": "standard_icon", "token": "stop_outlined"}
            },
            {
                "text": {"tag": "plain_text", "content": "🔄 长期持续"},
                "value": RoutineTypes.ONGOING,
                "icon": {"tag": "standard_icon", "token": "refresh_outlined"}
            },
            {
                "text": {"tag": "plain_text", "content": "📅 未来事项"},
                "value": RoutineTypes.FUTURE,
                "icon": {"tag": "standard_icon", "token": "calendar_outlined"}
            }
        ]

    def _get_type_display_name(self, event_type: str) -> str:
        """获取事件类型显示名称"""
        type_names = {
            RoutineTypes.INSTANT: "⚡ 瞬间完成",
            RoutineTypes.START: "▶️ 开始事项",
            RoutineTypes.END: "⏹️ 结束事项",
            RoutineTypes.ONGOING: "🔄 长期持续",
            RoutineTypes.FUTURE: "📅 未来事项"
        }
        return type_names.get(event_type, "📝 未知类型")

    # 卡片交互处理方法
    def handle_new_event_form_update(self, context: MessageContext_Refactor) -> ProcessResult:
        """处理新事件表单更新"""
        action_value = context.content.value
        action = action_value.get('action', '')
        operation_id = action_value.get('operation_id', '')

        # 这里需要从业务层获取当前表单状态并更新
        # 具体实现将在后续步骤中与业务层配合完成

        # 临时返回更新响应
        return self._handle_card_operation_common(
            card_content={"message": "表单更新功能开发中..."},
            card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
            update_toast_type=ToastTypes.INFO,
            toast_message="表单已更新"
        )

    def handle_new_event_confirm(self, context: MessageContext_Refactor) -> ProcessResult:
        """处理新事件确认"""
        action_value = context.content.value
        operation_id = action_value.get('operation_id', '')
        user_id = action_value.get('user_id', '')

        # 这里需要调用业务层创建新事件
        # 具体实现将在后续步骤中完成

        return self._handle_card_operation_common(
            card_content={"message": "新事件创建功能开发中..."},
            card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
            update_toast_type=ToastTypes.SUCCESS,
            toast_message="事件创建成功！"
        )

    def handle_quick_event_select(self, context: MessageContext_Refactor) -> ProcessResult:
        """处理快速事件选择"""
        action_value = context.content.value
        operation_id = action_value.get('operation_id', '')
        user_id = action_value.get('user_id', '')
        event_name = action_value.get('event_name', '')

        # 这里需要调用业务层处理快速记录
        # 具体实现将在后续步骤中完成

        return self._handle_card_operation_common(
            card_content={"message": "快速记录功能开发中..."},
            card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
            update_toast_type=ToastTypes.SUCCESS,
            toast_message=f"正在记录 '{event_name}'..."
        )
