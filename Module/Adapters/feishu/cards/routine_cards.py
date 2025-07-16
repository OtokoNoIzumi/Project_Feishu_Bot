"""
日常事项记录卡片管理器

处理日常事项记录相关的飞书卡片交互，包括：
1. 新事件定义卡片 - 完整的事件属性设置
2. 快速记录确认卡片 - 已存在事件的快速记录
3. 快速选择记录卡片 - 菜单触发的快捷事项选择
4. 查询结果展示卡片 - 替代文字查询的可视化界面
"""

import uuid
from typing import Dict, Any, List
from enum import Enum
import copy

from .card_registry import BaseCardManager
from ..decorators import card_build_safe
from Module.Services.constants import (
    CardOperationTypes, ServiceNames, RoutineTypes,
    ToastTypes, CardConfigKeys, RoutineProgressTypes
)
from Module.Business.processors import ProcessResult, MessageContext_Refactor, RouteResult
from Module.Common.scripts.common import debug_utils
from Module.Adapters.feishu.utils import safe_float


class RoutineCardMode(Enum):
    """日常事项卡片模式"""
    NEW_EVENT_DEFINITION = "new_event_definition"      # 新事件定义
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
        card_data = self._build_quick_record_confirm_card(business_data)
        card_content = {"type": "card_json", "data": card_data}

        return self._handle_card_operation_common(
            card_content=card_content,
            card_operation_type=CardOperationTypes.SEND,
            update_toast_type='success',
            user_id=context.user_id,
            message_id=context.message_id,
            business_data=business_data
        )

    @card_build_safe("菜单快速记录日常卡片构建失败")
    def build_quick_select_record_card(self, route_result: RouteResult, context: MessageContext_Refactor, business_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建快速选择记录卡片"""
        card_data = self._build_quick_select_record_card(business_data)
        card_content = {"type": "card_json", "data": card_data}

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
        # 后续应该可以从这里拆分掉
        business_data = kwargs.get('business_data', {})
        card_type = kwargs.get('card_type', RoutineCardMode.NEW_EVENT_DEFINITION.value)

        match card_type:
            case RoutineCardMode.NEW_EVENT_DEFINITION.value:
                card_data = self._build_new_event_definition_card(business_data)
            case RoutineCardMode.QUERY_RESULTS.value:
                card_data = self._build_query_results_card(business_data)
            case _:
                debug_utils.log_and_print(f"未知的routine卡片类型: {card_type}", log_level="WARNING")
                card_data = {}
        card_content = {"type": "card_json", "data": card_data}

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
                action_data={"action": "update_event_name", "operation_id": operation_id},
                name="event_name"
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
                    action_data={"action": "update_degree_options", "operation_id": operation_id},
                    name="degree_options"
                )
            ))

        # 8. 备注信息
        elements.append(self._build_form_row(
            "📝 备注信息",
            self._build_input_element(
                placeholder="添加备注信息（可选）",
                initial_value=form_data.get('notes', ''),
                disabled=is_confirmed,
                action_data={"action": "update_notes", "operation_id": operation_id},
                name="notes"
            )
        ))

        # 分割线
        elements.append({"tag": "hr", "margin": "16px 0px 16px 0px"})

        # 操作按钮
        if not is_confirmed:
            elements.append(self._build_action_buttons(operation_id, user_id))

        return elements

    def _build_quick_record_confirm_card(self, business_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建快速记录确认卡片"""
        # 如果要重新生成，比如多disable，那么也就意味着每一个子模块回调事件里的逻辑在主逻辑也有有一份，现在也是这么处理的。
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

        if event_name:
            title = f"添加记录：{event_name}"
        else:
            title = subtitle
            subtitle = ""
        card_dsl = {
            "schema": "2.0",
            "config": {"update_multi": True, "wide_screen_mode": True},
            "body": {
                "direction": "vertical",
                "padding": "12px",
                "elements": self._build_quick_record_elements(business_data)
            },
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "subtitle": {"tag": "plain_text", "content": subtitle},
                "template": color,
                "icon": {"tag": "standard_icon", "token": icon}
            }
        }
        return card_dsl

    def _build_quick_record_elements(self, business_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """构建快速记录表单元素 - 条件化展示丰富信息"""
        # 解析业务层传递的数据 - 支持容器模式和常规模式
        sub_business_data = business_data.get('sub_business_data', {})
        is_container_mode = bool(sub_business_data)

        # 数据源选择：容器模式使用sub_business_data，常规模式使用business_data
        data_source = sub_business_data if is_container_mode else business_data

        # 交互状态和结果统一使用外层容器数据
        is_confirmed = business_data.get('is_confirmed', False)

        # 从对应数据源获取业务数据
        event_name = data_source.get('event_name', '')
        event_def = data_source.get('event_definition', {})
        avg_duration = data_source.get('avg_duration', 0.0)
        degree_info = data_source.get('degree_info', {})
        cycle_info = data_source.get('cycle_info', {})
        new_record = data_source.get('new_record', {})
        diff_minutes = data_source.get('diff_minutes', 0)
        event_type = event_def.get('type', RoutineTypes.INSTANT)
        progress_type = event_def.get('properties', {}).get('progress_type', "")
        last_progress_value = event_def.get('stats', {}).get('last_progress_value', 0)
        total_progress_value = event_def.get('stats', {}).get('total_progress_value', 0)

        elements = []

        # 1. 基础信息卡片
        elements.extend(self._build_basic_info_section(event_def, new_record, diff_minutes))

        # 2. 条件化展示：时间预估和进度信息（合并到一个组件中）
        if avg_duration > 0 or (progress_type and (last_progress_value or total_progress_value)):
            elements.extend(self._build_duration_and_progress_section(avg_duration, progress_type, last_progress_value, total_progress_value))

        # 3. 条件化展示：目标进度信息（如果有目标设置）
        if cycle_info:
            elements.extend(self._build_cycle_progress_section(cycle_info))

        # === 确认输入部分 ===
        # 4. 条件化展示：程度选择器（如果有程度选项）
        if degree_info:
            elements.extend(self._build_degree_selection_section(degree_info, data_source, is_confirmed))

        # 创建表单容器
        form_elements = {
            "tag": "form",
            "elements": [],
            "name": "record_form"
        }

        # 5. 条件化展示：程度输入区域（如果有程度选项且选择了"其他"）
        if degree_info:
            selected_degree = new_record.get('degree', '')
            if selected_degree == '其他':
                form_elements['elements'].extend(self._build_degree_input_section(new_record.get('custom_degree', ''), is_confirmed))

        # 6. 条件化展示：持续时间输入区域
        if event_type in [RoutineTypes.INSTANT, RoutineTypes.END, RoutineTypes.START]:
            form_elements['elements'].extend(self._build_duration_input_section(new_record.get('duration', ''), is_confirmed))

        # 7. 条件化展示：进度类型选择区域
        if progress_type:
            form_elements['elements'].extend(self._build_progress_value_input_section(new_record.get('progress_value', ''), is_confirmed))

        # 8. 条件化展示：备注输入区域
        form_elements['elements'].extend(self._build_note_input_section(new_record.get('note', ''), is_confirmed))

        # 9. 操作按钮或确认提示
        # if not is_confirmed:  对于表单组件，必须要有提交按钮，否则会报错，所以要用disabled来控制，而不是省略。
        form_elements['elements'].append(self._build_record_action_buttons(event_name, is_confirmed))

        # 只有当表单有内容时才添加表单容器
        if form_elements['elements']:
            elements.append(form_elements)
        if not is_confirmed:
            elements.append({"tag": "markdown", "content": "**💡 重要提示** 请先选择完成日程的方式，这会清除下面所有的值！"})

        return elements

    def _build_basic_info_section(self, event_def: Dict[str, Any], new_record: Dict[str, Any], diff_minutes: int) -> List[Dict[str, Any]]:
        """构建基础信息区域"""
        elements = []

        # 事项类型显示
        event_type = event_def.get('type', RoutineTypes.INSTANT)

        # 基础信息卡片
        info_content = f"**事项类型：** {self._get_type_display_name(event_type)}\n"

        # 显示记录时间
        if new_record.get('timestamp'):
            timestamp = new_record['timestamp']
            split_timestamp = timestamp.split(' ')
            date_str = split_timestamp[0][5:10]
            time_str = split_timestamp[1][0:5]
            info_content += f"**记录时间：** {date_str} {time_str}\n"
            if diff_minutes > 0:
                info_content += f"**上次记录距今：** {diff_minutes}分钟\n"

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

    def _build_duration_and_progress_section(self, avg_duration: float, progress_type: str, last_progress_value: float, total_progress_value: float) -> List[Dict[str, Any]]:
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
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": combined_content
                },
                "element_id": "extra_info"
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
            real_progress_percent = round(cycle_count / target_val * 100, 1)
            progress_content_parts.append(f"📊 <font color={color}>{progress_bar}</font> {real_progress_percent}% {status_emoji}")
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

    def _build_degree_selection_section(self, degree_info: Dict[str, Any], data_source: Dict[str, Any], is_confirmed: bool) -> List[Dict[str, Any]]:
        """构建程度选择区域"""
        elements = []

        degree_options = degree_info.get('degree_options', []).copy()
        if '其他' not in degree_options:
            degree_options.append('其他')
        default_degree = degree_info.get('default_degree', '')
        event_name = data_source.get('event_name', '')

        # 构建选项
        degree_select_options = []
        for degree in degree_options:
            degree_select_options.append({
                "text": {"tag": "plain_text", "content": degree},
                "value": degree
            })

        # 智能默认值：用户上次选择 > 系统默认 > 第一个选项
        initial_degree = data_source['new_record'].get('degree', "") or default_degree

        elements.append(self._build_form_row(
            "选择方式",
            self._build_select_element(
                placeholder=f"如何{event_name}？",
                options=degree_select_options,
                initial_value=initial_degree,
                disabled=is_confirmed,
                action_data={
                    "card_action": "update_record_degree",
                    "card_config_key": CardConfigKeys.ROUTINE_RECORD
                },
                element_id="degree_select"
            ),
            width_list=["80px", "180px"],
            element_id="degree_select_row"
        ))

        return elements

    def update_record_degree(self, context: MessageContext_Refactor):
        """处理记录方式更新"""
        business_data, card_id, _ = self._get_core_data(context)
        if not business_data:
            debug_utils.log_and_print("🔍 update_record_degree - 卡片业务数据为空", log_level="WARNING")
            return

        sub_business_data = business_data.get('sub_business_data', {})
        is_container_mode = bool(sub_business_data)
        data_source = sub_business_data if is_container_mode else business_data
        new_option = context.content.value.get('option')

        build_method_name = business_data.get('container_build_method', '_build_quick_record_confirm_card')

        data_source['new_record']['degree'] = new_option
        user_service = self.app_controller.get_service(ServiceNames.USER_BUSINESS_PERMISSION)
        user_service.save_new_card_business_data(context.user_id, card_id, business_data)
        if hasattr(self, build_method_name):
            new_card_dsl = getattr(self, build_method_name)(business_data)
        else:
            new_card_dsl = self._build_quick_record_confirm_card(business_data)

        return self._handle_card_operation_common(
            card_content=new_card_dsl,
            card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
            update_toast_type=ToastTypes.SUCCESS,
            toast_message="完成方式更新成功！"
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
                },
                element_id="degree_input",
                name="custom_degree"
            ),
            width_list=["80px", "180px"],
            element_id="degree_input_row"
        ))

        return elements

    def _build_duration_input_section(self, initial_value: str = '', is_confirmed: bool = False) -> List[Dict[str, Any]]:
        """构建持续时间输入区域"""
        elements = []

        elements.append(self._build_form_row(
            "⏱️ 耗时",
            self._build_input_element(
                placeholder="记录耗时(分钟)",
                initial_value=initial_value,
                disabled=is_confirmed,
                action_data={
                },
                element_id="duration_input",
                name="duration"
            ),
            width_list=["80px", "180px"]
        ))

        return elements

    def _build_progress_value_input_section(self, initial_value: str = '', is_confirmed: bool = False) -> List[Dict[str, Any]]:
        """构建进度类型选择区域"""
        elements = []

        elements.append(self._build_form_row(
            "🎯 指标值",
            self._build_input_element(
                placeholder="添加指标值",
                initial_value=initial_value,
                disabled=is_confirmed,
                action_data={
                },
                element_id="progress_value_input",
                name="progress_value"
            ),
            width_list=["80px", "180px"]
        ))

        return elements

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
                },
                element_id="note_input",
                name="note"
            ),
            width_list=["80px", "180px"]
        ))

        return elements

    def _build_record_action_buttons(self, event_name: str, is_confirmed: bool = False) -> Dict[str, Any]:
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

        business_data, card_id, _ = self._get_core_data(context)
        sub_business_data = business_data.get('sub_business_data', {})
        is_container_mode = bool(sub_business_data)
        data_source = sub_business_data if is_container_mode else business_data
        build_method_name = business_data.get('container_build_method', '_build_quick_record_confirm_card')

        business_data['is_confirmed'] = True

        core_data = data_source.get('new_record', {})
        if not core_data:
            # 其实应该假设card_id也失效了，用message_id直接batch，但是这里先不处理。
            debug_utils.log_and_print("🔍 confirm_record - 卡片数据为空", log_level="WARNING")
            business_data['result'] = "取消"
            if hasattr(self, build_method_name):
                new_card_dsl = getattr(self, build_method_name)(business_data)
            else:
                new_card_dsl = self._build_quick_record_confirm_card(business_data)

            return self._handle_card_operation_common(
                card_content=new_card_dsl,
                card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
                update_toast_type=ToastTypes.ERROR,
                toast_message="操作已失效"
            )

        business_data['result'] = "确认"

        form_data = context.content.form_data

        user_id = context.user_id
        new_degree = core_data.get('degree', '')
        if new_degree:
            if new_degree == '其他':
                # 其他留空的情况不增加定义
                new_custom_degree = form_data.get('custom_degree', "其他")
                if new_custom_degree not in ["其他", ""]:
                    core_data['degree'] = new_custom_degree
                    degree_options = data_source['event_definition']['properties']['degree_options']
                    if new_custom_degree not in degree_options:
                        degree_options.append(new_custom_degree)
            else:
                core_data['degree'] = new_degree

        # 并不需要格式化最新的结果，但输入值需要保留，也就是定义的部分要复制
        # 创建深拷贝以避免修改原始数据
        event_def = copy.deepcopy(data_source.get('event_definition', {}))

        duration_str = form_data.get('duration', "")
        new_duration = safe_float(duration_str)
        if new_duration is not None:
            core_data['duration'] = new_duration
        else:
            debug_utils.log_and_print(f"🔍 confirm_record - 耗时转换失败: [{duration_str}]", log_level="WARNING")

        progress_type = event_def.get('properties', {}).get('progress_type', "")
        if progress_type:
            progress_value_str = str(form_data.get('progress_value', "")).strip()
            progress_value = safe_float(progress_value_str)
            if progress_value is not None:
                core_data['progress_value'] = progress_value
                if progress_type == RoutineProgressTypes.VALUE:
                    event_def['stats']['last_progress_value'] = progress_value
                elif (progress_type == RoutineProgressTypes.MODIFY) and (progress_value != 0):
                    event_def['stats']['total_progress_value'] = round(event_def['stats']['total_progress_value'] + progress_value, 3)
                    event_def['stats']['last_progress_value'] = progress_value
            else:
                debug_utils.log_and_print(f"🔍 confirm_record - 进度值转换失败: [{progress_value_str}]", log_level="WARNING")

        core_data['note'] = form_data.get('note', "")

        if hasattr(self, build_method_name):
            new_card_dsl = getattr(self, build_method_name)(business_data)
        else:
            new_card_dsl = self._build_quick_record_confirm_card(business_data)

        # 开始写入数据
        # 先写入记录
        routine_business = self.message_router.routine_record
        records_data = routine_business.load_event_records(user_id)
        records_data['records'].append(core_data)
        # 再写入事件定义，做聚合类计算
        event_def['stats']['record_count'] = event_def.get('stats', {}).get('record_count', 0) + 1
        cycle_info = data_source.get('cycle_info', {})
        if cycle_info:
            event_def['stats']['cycle_count'] = cycle_info.get('cycle_count', 0) + 1
            event_def['stats']['last_cycle_count'] = cycle_info.get('last_cycle_count', 0)
            event_def['stats']['last_refresh_date'] = cycle_info.get('last_refresh_date', "")

        event_def['stats']['last_note'] = core_data.get('note', "")

        new_duration = core_data.get('duration', 0)
        if new_duration > 0:
            event_duration_info = event_def.get('stats', {}).get('duration', {})
            recent_durations = event_duration_info.get('recent_values', [])
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

        routine_business.save_event_records(user_id, records_data)
        event_def['last_updated'] = core_data.get('timestamp')
        full_event_def = routine_business.load_event_definitions(user_id)
        full_event_def['definitions'][event_def['name']] = event_def
        full_event_def['last_updated'] = core_data.get('timestamp')
        full_event_def['last_record_time'] = core_data.get('timestamp')
        routine_business.save_event_definitions(user_id, full_event_def)

        event_name = context.content.value.get('event_name', '')

        user_service = self.app_controller.get_service(ServiceNames.USER_BUSINESS_PERMISSION)
        user_service.del_card_business_data(context.user_id, card_id)

        return self._handle_card_operation_common(
            card_content=new_card_dsl,
            card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
            update_toast_type=ToastTypes.SUCCESS,
            toast_message=f"'{event_name}' 记录成功！"
        )

    def cancel_record(self, context: MessageContext_Refactor) -> ProcessResult:
        """处理取消操作"""
        business_data, card_id, _ = self._get_core_data(context)
        if not business_data:
            debug_utils.log_and_print("🔍 cancel_record - 卡片数据为空", log_level="WARNING")

        build_method_name = business_data.get('container_build_method', '_build_quick_record_confirm_card')
        business_data['is_confirmed'] = True
        business_data['result'] = "取消"

        if hasattr(self, build_method_name):
            new_card_dsl = getattr(self, build_method_name)(business_data)
        else:
            new_card_dsl = self._build_quick_record_confirm_card(business_data)

        user_service = self.app_controller.get_service(ServiceNames.USER_BUSINESS_PERMISSION)
        user_service.del_card_business_data(context.user_id, card_id)

        return self._handle_card_operation_common(
            card_content=new_card_dsl,
            card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
            update_toast_type=ToastTypes.INFO,
            toast_message="操作已取消"
        )

    def _build_quick_select_record_card(self, business_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建快速选择记录卡片"""

        event_name = business_data.get('selected_event_name', '')
        is_confirmed = business_data.get('is_confirmed', False)
        result = business_data.get('result', '取消')
        card_status = result if is_confirmed else "运行中"
        quick_events = business_data.get('quick_events', [])

        # 提取集成模式相关数据，和后台业务无关的初始数据在这里初始化
        workflow_state = business_data.get('workflow_state', 'initial')
        input_text = business_data.get('input_text', '')

        # 构建基础卡片结构
        card_dsl = {
            "schema": "2.0",
            "config": {"update_multi": True, "wide_screen_mode": True},
            "body": {
                "direction": "vertical",
                "padding": "12px",
                "elements": []
            },
            "header": self._build_card_header(workflow_state, event_name)
        }
        elements = card_dsl['body']['elements']

        elements.append(self._build_form_row(
            "✏️ 事项",
            self._build_input_element(
                placeholder="输入事项名称...",
                initial_value=input_text,
                disabled=is_confirmed,
                action_data={
                    "card_action": "handle_input_event_name",
                    "card_config_key": CardConfigKeys.ROUTINE_QUICK_SELECT,
                },
                element_id="new_event_name",
                name="new_event_name"
            ),
            width_list=["80px", "180px"]
        ))

        elements.append(self._build_form_row(
            "快捷添加",
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "查询日程"},
                "type": "primary",
                "width": "default",
                "size": "medium",
                "disabled": is_confirmed,
                "behaviors": [{
                    "type": "callback",
                    "value": {
                        "card_action": "handle_quick_event_query",
                        "card_config_key": CardConfigKeys.ROUTINE_QUICK_SELECT,
                    }
                }]
            },
            width_list=["80px", "180px"]
        ))

        for event in quick_events:
            event_name_btn = event.get('name', '')
            event_type = event.get('type', RoutineTypes.INSTANT)
            type_emoji = {"instant": "⚡", "start": "▶️", "end": "⏹️", "ongoing": "🔄", "future": "📅"}.get(event_type, "📝")
            is_quick_access = event.get('properties', {}).get('quick_access', False)

            elements.append({
                "tag": "button",
                "text": {"tag": "plain_text", "content": f"{type_emoji} {event_name_btn}"},
                "type": "primary" if is_quick_access else "default",
                "width": "fill",
                "size": "medium",
                "disabled": is_confirmed,
                "behaviors": [{
                    "type": "callback",
                    "value": {
                        "card_action": "quick_record_select",
                        "card_config_key": CardConfigKeys.ROUTINE_QUICK_SELECT,
                        "event_name": event_name_btn
                    }
                }]
            })

        # 集成模式：根据工作流程状态显示不同内容
        sub_business_build_method = business_data.get('sub_business_build_method', '')
        if sub_business_build_method and hasattr(self, sub_business_build_method):
            sub_elements = getattr(self, sub_business_build_method)(business_data)

            elements.append({
                "tag": "hr",
                "margin": "6px 0px"
            })
            elements.extend(sub_elements)

        return card_dsl

    def _build_card_header(self, workflow_state: str, event_name: str) -> Dict[str, Any]:
        """构建卡片头部，根据集成模式和状态显示不同内容"""
        if workflow_state == "quick_record" and event_name:
            return {
                "title": {"tag": "plain_text", "content": f"📝 记录：{event_name}"},
                "subtitle": {"tag": "plain_text", "content": "确认记录信息"},
                "template": "blue",
                "icon": {"tag": "standard_icon", "token": "edit_outlined"}
            }
        elif workflow_state == "new_event_option":
            return {
                "title": {"tag": "plain_text", "content": "🆕 新建事项"},
                "subtitle": {"tag": "plain_text", "content": "事项不存在，是否新建？"},
                "template": "orange",
                "icon": {"tag": "standard_icon", "token": "add_outlined"}
            }
        else:
            return {
                "title": {"tag": "plain_text", "content": "🚀 快速记录"},
                "subtitle": {"tag": "plain_text", "content": "输入或选择事项"},
                "template": "purple",
            }


    def _build_query_results_card(self, business_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建查询结果展示卡片"""
        results = business_data.get('results', [])
        query_type = business_data.get('query_type', 'recent')

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

    def quick_record_select(self, context: MessageContext_Refactor) -> ProcessResult:
        """处理快速事件选择"""
        action_value = context.content.value
        user_id = context.user_id  # 从 context 中获取 user_id
        event_name = action_value.get('event_name', '')

        # 获取当前卡片的业务数据
        business_data, card_id, _ = self._get_core_data(context)
        if not business_data:
            debug_utils.log_and_print("🔍 quick_record_select - 卡片数据为空", log_level="WARNING")
            business_data['is_confirmed'] = True
            business_data['result'] = "取消"
            new_card_dsl = self._build_quick_select_record_card(business_data)

            return self._handle_card_operation_common(
                card_content=new_card_dsl,
                card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
                update_toast_type=ToastTypes.ERROR,
                toast_message="操作已失效"
            )

        # 本质的步骤就是替换/添加sub_business_data，然后更新卡片。
        # 需要添加的第一个肯定是raw_data，第二个是向后兼容的workflow_state
        # 然后是一些控制参数，两层business_data都要考虑，这样就完成了传参。当然也有一种情况，本来就可以通过sub来区别，也就不用管传参了。

        # 加载事件定义
        routine_business = self.message_router.routine_record
        definitions_data = routine_business.load_event_definitions(user_id)
        if definitions_data and event_name in definitions_data["definitions"]:  # 虽然是冗余但先保留吧
            event_def = definitions_data["definitions"][event_name]
            last_record_time = definitions_data.get("last_record_time", None)
            quick_record_data = routine_business.build_quick_record_data(user_id, event_name, event_def, last_record_time)

            business_data['workflow_state'] = 'quick_record'  # 集成模式状态，这个姑且先保留吧，稍微冗余一点点
            business_data['sub_business_data'] = quick_record_data
            business_data['sub_business_build_method'] = '_build_quick_record_elements'
            business_data['container_build_method'] = '_build_quick_select_record_card'

            # 更新卡片显示
            new_card_dsl = self._build_quick_select_record_card(business_data)
            user_service = self.app_controller.get_service(ServiceNames.USER_BUSINESS_PERMISSION)
            user_service.save_new_card_business_data(user_id, card_id, business_data)

            return self._handle_card_operation_common(
                card_content=new_card_dsl,
                card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
                update_toast_type=ToastTypes.SUCCESS,
                toast_message=f"开始记录 [{event_name}]"
            )

        # 如果事件不存在，保持在选择模式
        business_data['selected_event_name'] = event_name

        new_card_dsl = self._build_quick_select_record_card(business_data)
        return self._handle_card_operation_common(
            card_content=new_card_dsl,
            card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
            update_toast_type=ToastTypes.INFO,
            toast_message=f"输入了新事项 '{event_name}'"
        )

    def handle_input_event_name(self, context: MessageContext_Refactor) -> ProcessResult:
        """处理输入框事件名称输入"""
        # 先做一个兼容select的，再考虑event。
        event_name = context.content.input_value
        user_id = context.user_id

        # 获取当前卡片的业务数据——待处理成通用方法
        business_data, card_id, _ = self._get_core_data(context)
        if not business_data:
            debug_utils.log_and_print("🔍 quick_record_select - 卡片数据为空", log_level="WARNING")
            business_data['is_confirmed'] = True
            business_data['result'] = "取消"
            new_card_dsl = self._build_quick_select_record_card(business_data)

            return self._handle_card_operation_common(
                card_content=new_card_dsl,
                card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
                update_toast_type=ToastTypes.ERROR,
                toast_message="操作已失效"
            )

        routine_business = self.message_router.routine_record
        definitions_data = routine_business.load_event_definitions(user_id)

        if definitions_data and event_name in definitions_data["definitions"]:
            # 事件存在，进入快速记录模式
            event_def = definitions_data["definitions"][event_name]
            last_record_time = definitions_data.get("last_record_time", None)
            quick_record_data = routine_business.build_quick_record_data(user_id, event_name, event_def, last_record_time)

            business_data['workflow_state'] = 'quick_record'  # 集成模式状态，这个姑且先保留吧，稍微冗余一点点
            business_data['sub_business_data'] = quick_record_data
            business_data['sub_business_build_method'] = '_build_quick_record_elements'
            business_data['container_build_method'] = '_build_quick_select_record_card'

            # 更新卡片显示
            new_card_dsl = self._build_quick_select_record_card(business_data)
            user_service = self.app_controller.get_service(ServiceNames.USER_BUSINESS_PERMISSION)
            user_service.save_new_card_business_data(user_id, card_id, business_data)

            return self._handle_card_operation_common(
                card_content=new_card_dsl,
                card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
                update_toast_type=ToastTypes.SUCCESS,
                toast_message=f"正在记录 '{event_name}'..."
            )
        else:
            # 事件不存在，显示新建提示但保持在选择模式

            return self._handle_card_operation_common(
                card_content={"message": "请输入事项名称"},
                card_operation_type=CardOperationTypes.UPDATE_RESPONSE,
                update_toast_type=ToastTypes.INFO,
                toast_message=f"'{event_name}' 是新事项，可以创建新定义"
            )
