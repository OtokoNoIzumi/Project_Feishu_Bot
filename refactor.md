# 菜单记录功能扩展重构方案

## 📋 项目概述

### 核心目标
扩展菜单触发的卡片记录功能，支持在没有事件定义的情况下直接添加记录。

### 设计原则
1. **保留现有逻辑**：旧的record方法完全保留，避免影响现有功能
2. **渐进式开发**：分MVP阶段实现，数据结构一次性规划到位
3. **类型驱动**：以事件类型为核心，动态显示相应字段
4. **容器模式兼容**：与现有集成模式架构保持一致

## 🏗️ 数据结构设计

### 直接记录数据结构——储存在event_records.json，和原有数据不做区分
```json
{
  "record_id": "事件名_001", // 根据事件名生成
  "event_name": "用户输入的事件名",
  "event_type": "instant|start|ongoing|future",
  "timestamp": "2024-01-01 12:00:00",
  "completion_time": "2024-01-01 12:05:00",
  
  // 公共字段
  "note": "备注内容",
  "degree": "完成方式",
  "duration": 5.0,
  
  // 指标相关
  "progress_type": "none|value|modify",
  "progress_value": 1.0,
  
  // 长期项目特有——或者通过后续的事件定义获得，比如瞬间完成的刷牙也有这个属性。
  "check_cycle": "",  // 合法值 RoutineCheckCycle
  "target_type": "none|time|count",
  "target_value": 10,
}
```

### 事件类型支持范围
- ✅ **瞬间完成 (instant)**：默认选择
- ✅ **开始事项 (start)**：可选择
- ❌ **结束事项 (end)**：排除，限定为对开始的结束
- ✅ **长期持续 (ongoing)**：可选择
- ✅ **未来事项 (future)**：可选择

## 🚀 开发阶段规划

### 阶段1：基础架构扩展
**目标**：建立直接记录的基础框架

#### 业务层修改 (routine_record.py)
基于现有代码架构，需要在`RoutineRecord`类中新增以下方法：

```python
@safe_execute("构建直接记录卡片数据失败")
def build_direct_record_data(
    self, user_id: str, event_name: str, event_type: str = RoutineTypes.INSTANT
) -> Dict[str, Any]:
    """构建直接记录卡片数据，参考build_quick_record_data的模式"""
    # 返回包含form_data、event_name、event_type等字段的字典
    pass

@safe_execute("创建直接记录失败")
def create_direct_record(
    self, user_id: str, form_data: Dict[str, Any]
) -> Tuple[bool, str]:
    """创建直接记录，保存到现有的event_records.json文件"""
    # 保存到event_records.json文件
    pass

# 注：直接记录数据存储在现有的event_records.json中，无需单独的文件路径和加载方法
# 可复用现有的load_event_records方法
```

#### 适配器层修改 (routine_cards/direct_record_card.py)
基于现有的卡片构建模式，需要创建新的`DirectRecordCard`类：

```python
class DirectRecordCard:
    def __init__(self, parent_manager):
        self.parent = parent_manager
        self.default_update_build_method = "update_direct_record_card"
    
    def build_direct_record_card(self, business_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建直接记录卡片，参考_build_new_event_definition_card的结构"""
        form_data = business_data.get("form_data", {})
        event_name = business_data.get("event_name", "")
        event_type = business_data.get("event_type", RoutineTypes.INSTANT)
        is_confirmed = business_data.get("is_confirmed", False)
        
        header = self._build_card_header(
            "📝 快速记录", f"记录事项：{event_name}", "blue", "add-bold_outlined"
        )
        elements = self._build_direct_record_form_elements(
            form_data, event_name, event_type, is_confirmed
        )
        return self._build_base_card_structure(elements, header, "16px")

    def _build_direct_record_form_elements(self, business_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """构建直接记录表单元素"""
        pass

    # 注：直接复用现有的_get_event_type_options方法，在使用时过滤掉END类型
    # 无需新增_get_direct_record_type_options方法

    def update_direct_record_type(self, context: MessageContext_Refactor) -> ProcessResult:
        """处理直接记录类型变更，参考现有的update_event_type方法模式"""
        pass
```

### 阶段2：类型选择机制
**目标**：实现事件类型选择和动态字段显示

#### 核心功能
1. **类型选择器**：下拉选择，默认瞬间完成
2. **动态字段**：根据类型显示/隐藏相应字段
3. **状态保持**：类型切换时保持已输入数据

#### 字段配置
基于现有的`_build_new_event_form_elements`方法模式，实现动态字段显示：
- 事件类型选择器（复用`_get_event_type_options`）
- 根据选择类型动态显示相应字段
- 保持与现有表单构建模式一致

#### 实现方法
```python
def _build_direct_record_form_elements(
    self, form_data: Dict[str, Any], event_name: str, 
    event_type: str, is_confirmed: bool
) -> List[Dict[str, Any]]:
    """构建直接记录表单元素，参考_build_new_event_form_elements的结构"""
    elements = []
    
    # 1. 事项名称（只读显示）
    elements.append(
        self._build_form_row(
            "🏷️ 事项名称",
            self._build_input_element(
                placeholder=event_name,
                initial_value=event_name,
                disabled=True,  # 直接记录模式下事项名称不可编辑
                action_data={},
                name="event_name",
            ),
        )
    )
    
    # 2. 事项类型选择
    type_options = [opt for opt in self._get_event_type_options() if opt["value"] != RoutineTypes.END]
    elements.append(
        self._build_form_row(
            "⚡ 事项类型",
            self._build_select_element(
                placeholder="选择事项类型",
                options=type_options,
                initial_value=event_type,
                disabled=is_confirmed,
                action_data={"action": "update_direct_record_type"},
                name="event_type",
            ),
        )
    )
    
    # 3. 根据类型动态添加字段
    if event_type == RoutineTypes.INSTANT:
        elements.extend(self._build_instant_record_fields(form_data, is_confirmed))
    elif event_type == RoutineTypes.START:
        elements.extend(self._build_start_record_fields(form_data, is_confirmed))
    # ... 其他类型
    
    return elements

def _build_instant_record_fields(self, form_data: Dict, is_confirmed: bool) -> List[Dict]:
    """构建瞬间完成类型字段"""
    return [
        self._build_form_row(
            "⏰ 完成时间", 
            self._build_date_picker_element(
                placeholder="选择完成时间",
                initial_date=form_data.get("completion_time", ""),
                disabled=is_confirmed,
                action_data={"action": "update_completion_time"}
            )
        ),
        self._build_form_row(
            "📝 备注", 
            self._build_input_element(
                placeholder="添加备注（可选）",
                initial_value=form_data.get("note", ""),
                disabled=is_confirmed,
                action_data={"action": "update_note"},
                name="note"
            )
        ),
        self._build_form_row(
            "📊 完成方式", 
            self._build_input_element(
                placeholder="完成方式（可选）",
                initial_value=form_data.get("degree", ""),
                disabled=is_confirmed,
                action_data={"action": "update_degree"},
                name="degree"
            )
        )
    ]

def _build_type_specific_fields(self, event_type: str, form_data: Dict) -> List[Dict]:
    """根据类型构建特定字段"""
    pass
```

### 阶段3：MVP1 - 瞬间完成和开始类型
**目标**：实现瞬间完成和开始事项的直接记录

#### 字段配置
**公共字段**：
- 事件名称（只读显示，不在表单）
- 创建时间（当前时间，不可改，不在表单）
- 完成时间（系统自动设置，不可选择）

**瞬间完成 (instant)**：
- 指标类型（下拉单选：无/数值/变化量，默认无，**不在表单**，有回调事件）
- 耗时duration（**在表单**）
- 完成方式degree（**在表单**）
- 备注note（**在表单**）
- 指标值progress（**在表单**，placeholder根据指标类型区分）

**开始事项 (start)**：
- 指标类型（下拉单选：无/数值/变化量，默认无，**不在表单**，有回调事件）
- 耗时duration（**在表单**，开始也可以有，完成时累加）
- 完成方式degree（**在表单**）
- 备注note（**在表单**）
- 指标值progress（**在表单**，placeholder根据指标类型区分）

#### 实现方法
```python
def _build_direct_record_form_elements(
    self, form_data: Dict[str, Any], event_name: str, 
    event_type: str, is_confirmed: bool
) -> List[Dict[str, Any]]:
    """构建直接记录表单元素，区分表单内外字段"""
    elements = []
    
    # 1. 事件名称（只读显示，不在表单）
    elements.append(
        self._build_form_row(
            "📝 事件名称",
            {"tag": "div", "text": {"tag": "plain_text", "content": event_name}}
        )
    )
    
    # 2. 事项类型选择器（不在表单，有回调事件）
    type_options = [opt for opt in self._get_event_type_options() if opt["value"] != RoutineTypes.END]
    elements.append(
        self._build_form_row(
            "📋 事项类型",
            self._build_select_element(
                placeholder="选择事项类型",
                options=type_options,
                initial_value=event_type,
                disabled=is_confirmed,
                action_data={
                    "card_action": "update_record_type",
                    "card_config_key": CardConfigKeys.ROUTINE_DIRECT_RECORD,
                },
                name="event_type",
            ),
        )
    )
    
    # 3. 指标类型选择（不在表单，有回调事件，状态需保留）
    progress_type = form_data.get("progress_type", RoutineProgressTypes.NONE)
    if event_type in [RoutineTypes.INSTANT, RoutineTypes.START, RoutineTypes.ONGOING]:
        elements.append(
            self._build_form_row(
                "📊 指标类型",
                self._build_select_element(
                    placeholder="选择指标类型",
                    options=self._get_progress_type_options(),
                    initial_value=progress_type,
                    disabled=is_confirmed,
                    action_data={
                        "card_action": "update_progress_type",
                        "card_config_key": CardConfigKeys.ROUTINE_DIRECT_RECORD,
                    },
                    name="progress_type",
                ),
            )
        )
    
    # 4. 提醒模式（仅未来事项，不在表单，有回调事件）
    if event_type == RoutineTypes.FUTURE:
        reminder_mode = form_data.get("reminder_mode", "off")
        elements.append(
            self._build_form_row(
                "🔔 提醒模式",
                self._build_select_element(
                    placeholder="选择提醒模式",
                    options=self._get_reminder_mode_options(),
                    initial_value=reminder_mode,
                    disabled=is_confirmed,
                    action_data={
                        "card_action": "update_reminder_mode",
                        "card_config_key": CardConfigKeys.ROUTINE_DIRECT_RECORD,
                    },
                    name="reminder_mode",
                ),
            )
        )
    
    # 5. 表单容器开始
    elements.append({"tag": "hr", "margin": "12px 0px"})
    
    # 6. 根据事件类型构建表单内字段
    form_fields = self._build_form_fields_by_type(event_type, form_data, is_confirmed)
    elements.extend(form_fields)
    
    # 7. 提交按钮
    elements.append(
        {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "确认记录"},
            "type": "primary",
            "disabled": is_confirmed,
            "behaviors": [
                {
                    "type": "form_submit",
                    "value": {
                        "card_action": "confirm_direct_record",
                        "card_config_key": CardConfigKeys.ROUTINE_DIRECT_RECORD,
                    },
                }
            ],
        }
    )
    
    return elements

def _build_form_fields_by_type(self, event_type: str, form_data: Dict, is_confirmed: bool) -> List[Dict]:
    """根据事件类型构建表单内字段"""
    match event_type:
        case RoutineTypes.INSTANT | RoutineTypes.START:
            return self._build_instant_start_form_fields(form_data, is_confirmed)
        case RoutineTypes.ONGOING:
            return self._build_ongoing_form_fields(form_data, is_confirmed)
        case RoutineTypes.FUTURE:
            return self._build_future_form_fields(form_data, is_confirmed)
        case _:
            return []

def _build_instant_start_form_fields(self, form_data: Dict, is_confirmed: bool) -> List[Dict]:
    """构建瞬间完成和开始事项的表单字段"""
    fields = []
    
    # 耗时
    fields.append(
        self._build_form_row(
            "⏱️ 耗时（分钟）",
            self._build_input_element(
                placeholder="耗时（可选）",
                initial_value=str(form_data.get("duration", "")),
                disabled=is_confirmed,
                name="duration"
            )
        )
    )
    
    # 完成方式
    fields.append(
        self._build_form_row(
            "🎯 完成方式",
            self._build_input_element(
                placeholder="完成方式（可选）",
                initial_value=form_data.get("degree", ""),
                disabled=is_confirmed,
                name="degree"
            )
        )
    )
    
    # 备注
    fields.append(
        self._build_form_row(
            "📝 备注",
            self._build_input_element(
                placeholder="添加备注（可选）",
                initial_value=form_data.get("note", ""),
                disabled=is_confirmed,
                name="note"
            )
        )
    )
    
    # 指标值（根据指标类型显示）
    progress_type = form_data.get("progress_type", RoutineProgressTypes.NONE)
    if progress_type != RoutineProgressTypes.NONE:
        placeholder = "最新数值" if progress_type == RoutineProgressTypes.VALUE else "变化量（+/-）"
        fields.append(
            self._build_form_row(
                "📈 指标值",
                self._build_input_element(
                    placeholder=placeholder,
                    initial_value=str(form_data.get("progress_value", "")),
                    disabled=is_confirmed,
                    name="progress_value"
                )
            )
        )
    
    return fields

def _get_progress_type_options(self) -> List[Dict]:
    """获取指标类型选项"""
    return [
        {"text": {"tag": "plain_text", "content": "无指标"}, "value": RoutineProgressTypes.NONE},
        {"text": {"tag": "plain_text", "content": "数值记录"}, "value": RoutineProgressTypes.VALUE},
        {"text": {"tag": "plain_text", "content": "变化量"}, "value": RoutineProgressTypes.MODIFY}
    ]

def _get_reminder_mode_options(self) -> List[Dict]:
    """获取提醒模式选项"""
    return [
        {"text": {"tag": "plain_text", "content": "关闭"}, "value": "off"},
        {"text": {"tag": "plain_text", "content": "时间提醒"}, "value": "time"},
        {"text": {"tag": "plain_text", "content": "周期提醒"}, "value": "cycle"}
    ]

def update_progress_type(self, context: MessageContext_Refactor) -> ProcessResult:
    """处理指标类型变更（保留状态，重新构建卡片）"""
    # 更新指标类型并重新构建卡片，保留其他字段状态
    return self._handle_direct_record_field_update(context, "progress_type")

def update_reminder_mode(self, context: MessageContext_Refactor) -> ProcessResult:
    """处理提醒模式变更"""
    return self._handle_direct_record_field_update(context, "reminder_mode")

def _handle_direct_record_field_update(self, context: MessageContext_Refactor, field_name: str) -> ProcessResult:
    """处理直接记录字段更新的通用方法"""
    # 获取当前配置
    config = self.card_config_manager.get_config(
        context.user_id, CardConfigKeys.ROUTINE_DIRECT_RECORD
    )
    
    # 更新字段值
    new_value = context.content.value.get("value")
    config["form_data"][field_name] = new_value
    
    # 保存配置
    self.card_config_manager.save_config(
        context.user_id, CardConfigKeys.ROUTINE_DIRECT_RECORD, config
    )
    
    # 重新构建卡片
    return self._build_direct_record_card(context.user_id, config)

def confirm_direct_record(self, context: MessageContext_Refactor) -> ProcessResult:
    """处理直接记录确认提交"""
    # 获取表单数据
    form_data = context.content.value.get("form_data", {})
    
    # 获取卡片配置中的非表单数据
    config = self.card_config_manager.get_config(
        context.user_id, CardConfigKeys.ROUTINE_DIRECT_RECORD
    )
    
    # 合并表单数据和配置数据
    complete_data = {
        **config.get("form_data", {}),  # 非表单数据（如事件类型、指标类型等）
        **form_data  # 表单数据
    }
    
    # 调用业务层创建记录
    routine_business = self.app_controller.get_business(BusinessNames.ROUTINE_RECORD)
    success, message = routine_business.create_direct_record(
        context.user_id, complete_data
    )
    
    if success:
        # 清理配置
        self.card_config_manager.clear_config(
            context.user_id, CardConfigKeys.ROUTINE_DIRECT_RECORD
        )
        return self._respond_with_toast(message, ToastTypes.SUCCESS)
    else:
        return self._respond_with_toast(message, ToastTypes.ERROR)

def update_direct_record_type(self, context: MessageContext_Refactor) -> ProcessResult:
    """处理事项类型变更"""
    return self._handle_direct_record_field_update(context, "event_type")
```

### 阶段4：MVP2 - 长期项目类型
**目标**：支持长期持续项目记录

#### 字段配置
**长期持续 (ongoing)**：
- 指标类型（下拉单选：无/数值/变化量，默认无，**不在表单**，有回调事件）
- 间隔类型（单选，**在表单**）
- 目标类型（无/time/count，**在表单**）
- 目标值（可以为空，**在表单**）
- 备注note（**在表单**）
- 指标值progress（**在表单**，placeholder根据指标类型区分）

#### 实现方法
```python
def _build_ongoing_form_fields(self, form_data: Dict, is_confirmed: bool) -> List[Dict]:
    """构建长期项目类型的表单字段"""
    fields = []
    
    # 间隔类型（在表单内）
    fields.append(
        self._build_form_row(
            "🔄 间隔类型",
            self._build_select_element(
                placeholder="选择间隔类型",
                options=self._get_interval_type_options(),
                initial_value=form_data.get("interval_type", ""),
                disabled=is_confirmed,
                name="interval_type"
            )
        )
    )
    
    # 目标类型（在表单内）
    target_type = form_data.get("target_type", RoutineTargetTypes.NONE)
    fields.append(
        self._build_form_row(
            "🎯 目标类型",
            self._build_select_element(
                placeholder="选择目标类型",
                options=self._get_target_type_options(),
                initial_value=target_type,
                disabled=is_confirmed,
                name="target_type"
            )
        )
    )
    
    # 目标值（在表单内，根据目标类型显示）
    if target_type != RoutineTargetTypes.NONE:
        placeholder = "目标时长（分钟）" if target_type == RoutineTargetTypes.TIME else "目标次数"
        fields.append(
            self._build_form_row(
                "📊 目标值",
                self._build_input_element(
                    placeholder=placeholder,
                    initial_value=str(form_data.get("target_value", "")),
                    disabled=is_confirmed,
                    name="target_value"
                )
            )
        )
    
    # 备注（在表单内）
    fields.append(
        self._build_form_row(
            "📝 备注",
            self._build_input_element(
                placeholder="添加备注（可选）",
                initial_value=form_data.get("note", ""),
                disabled=is_confirmed,
                name="note"
            )
        )
    )
    
    # 指标值（在表单内，根据指标类型显示）
    progress_type = form_data.get("progress_type", RoutineProgressTypes.NONE)
    if progress_type != RoutineProgressTypes.NONE:
        placeholder = "增加数值" if progress_type == RoutineProgressTypes.VALUE else "变化量（+/-）"
        fields.append(
            self._build_form_row(
                "📈 指标值",
                self._build_input_element(
                    placeholder=placeholder,
                    initial_value=str(form_data.get("progress_value", "")),
                    disabled=is_confirmed,
                    name="progress_value"
                )
            )
        )
    
    return fields

def _get_interval_type_options(self) -> List[Dict]:
    """获取间隔类型选项"""
    return [
        {"text": {"tag": "plain_text", "content": "每日"}, "value": "daily"},
        {"text": {"tag": "plain_text", "content": "每周"}, "value": "weekly"},
        {"text": {"tag": "plain_text", "content": "每月"}, "value": "monthly"}
    ]

def _get_target_type_options(self) -> List[Dict]:
    """获取目标类型选项"""
    return [
        {"text": {"tag": "plain_text", "content": "无目标"}, "value": RoutineTargetTypes.NONE},
        {"text": {"tag": "plain_text", "content": "时长目标"}, "value": RoutineTargetTypes.TIME},
        {"text": {"tag": "plain_text", "content": "次数目标"}, "value": RoutineTargetTypes.COUNT}
    ]
```

### 阶段5：MVP3 - 未来事项类型
**目标**：支持未来计划事项

#### 字段配置
**未来事项 (future)**：
- 提醒模式（关/时间/周期，**不在表单**，有回调事件，改变表单显示的提醒设置，默认关）
- 日期时间选择器（**在表单**）
- 重要性（新字段，单选，**在表单**）
- 预估耗时（新字段，用duration，**在表单**）
- 提醒时间（新字段，单选，**在表单**，由提醒模式开启）
- 提醒周期（下拉多选：开始时/提前5分钟/提前一小时/提前1天/提前3天，**在表单**）
- 备注（**在表单**）

#### 实现方法
```python
def _build_future_form_fields(self, form_data: Dict, is_confirmed: bool) -> List[Dict]:
    """构建未来事项类型的表单字段"""
    fields = []
    
    # 日期时间选择器（在表单内）
    fields.append(
        self._build_form_row(
            "📅 计划日期",
            self._build_date_picker(
                initial_value=form_data.get("planned_date", ""),
                disabled=is_confirmed,
                name="planned_date"
            )
        )
    )
    
    fields.append(
        self._build_form_row(
            "⏰ 计划时间",
            self._build_time_picker(
                initial_value=form_data.get("planned_time", ""),
                disabled=is_confirmed,
                name="planned_time"
            )
        )
    )
    
    # 重要性（在表单内）
    fields.append(
        self._build_form_row(
            "⭐ 重要性",
            self._build_select_element(
                placeholder="选择重要性",
                options=self._get_priority_options(),
                initial_value=form_data.get("priority", "medium"),
                disabled=is_confirmed,
                name="priority"
            )
        )
    )
    
    # 预估耗时（在表单内）
    fields.append(
        self._build_form_row(
            "⏱️ 预估耗时（分钟）",
            self._build_input_element(
                placeholder="预估耗时",
                initial_value=str(form_data.get("estimated_duration", "")),
                disabled=is_confirmed,
                name="estimated_duration"
            )
        )
    )
    
    # 提醒时间（在表单内，由提醒模式控制显示）
    reminder_mode = form_data.get("reminder_mode", "off")
    if reminder_mode in ["time", "cycle"]:
        fields.append(
            self._build_form_row(
                "⏰ 提醒时间",
                self._build_select_element(
                    placeholder="选择提醒时间",
                    options=self._get_reminder_time_options(),
                    initial_value=form_data.get("reminder_time", ""),
                    disabled=is_confirmed,
                    name="reminder_time"
                )
            )
        )
    
    # 提醒周期（在表单内，仅周期提醒模式显示）
    if reminder_mode == "cycle":
        fields.append(
            self._build_form_row(
                "🔔 提醒周期",
                self._build_multi_select_element(
                    placeholder="选择提醒周期",
                    options=self._get_reminder_cycle_options(),
                    initial_value=form_data.get("reminder_cycle", []),
                    disabled=is_confirmed,
                    name="reminder_cycle"
                )
            )
        )
    
    # 备注（在表单内）
    fields.append(
        self._build_form_row(
            "📝 备注",
            self._build_input_element(
                placeholder="添加备注（可选）",
                initial_value=form_data.get("note", ""),
                disabled=is_confirmed,
                name="note"
            )
        )
    )
    
    return fields

def _get_priority_options(self) -> List[Dict]:
    """获取重要性选项"""
    return [
        {"text": {"tag": "plain_text", "content": "🔴 高"}, "value": "high"},
        {"text": {"tag": "plain_text", "content": "🟡 中"}, "value": "medium"},
        {"text": {"tag": "plain_text", "content": "🟢 低"}, "value": "low"}
    ]

def _get_reminder_time_options(self) -> List[Dict]:
    """获取提醒时间选项"""
    return [
        {"text": {"tag": "plain_text", "content": "开始时"}, "value": "start"},
        {"text": {"tag": "plain_text", "content": "提前5分钟"}, "value": "5min"},
        {"text": {"tag": "plain_text", "content": "提前1小时"}, "value": "1hour"},
        {"text": {"tag": "plain_text", "content": "提前1天"}, "value": "1day"},
        {"text": {"tag": "plain_text", "content": "提前3天"}, "value": "3day"}
    ]

def _get_reminder_cycle_options(self) -> List[Dict]:
    """获取提醒周期选项"""
    return [
        {"text": {"tag": "plain_text", "content": "开始时"}, "value": "start"},
        {"text": {"tag": "plain_text", "content": "提前5分钟"}, "value": "5min"},
        {"text": {"tag": "plain_text", "content": "提前1小时"}, "value": "1hour"},
        {"text": {"tag": "plain_text", "content": "提前1天"}, "value": "1day"},
        {"text": {"tag": "plain_text", "content": "提前3天"}, "value": "3day"}
    ]
```

## 🔧 技术实现细节

### 嵌套数据处理逻辑说明

#### safe_get_business_data方法使用规范

基于项目中`card_registry.py`的`safe_get_business_data`方法实现，该方法用于安全地从嵌套业务数据结构中获取目标数据：

```python
def safe_get_business_data(
    self,
    business_data: Dict[str, Any],
    sub_business_name: str = "",
    max_depth: int = 10,
) -> Tuple[Dict[str, Any], bool]:
    """
    安全地从容器里获取到自己业务数据，最多递归 max_depth 层。
    
    如果提供 sub_business_name，则一直向下查找同名节点；
    如果未提供，则直接定位到最深一层 sub_business_data。
    返回 (data, is_container_mode)。
    """
```

**使用模式：**
1. **获取指定业务数据**：`data_source, _ = self.parent.safe_get_business_data(business_data, CardConfigKeys.ROUTINE_RECORD)`
2. **获取最深层数据**：`data_source, is_container = self.parent.safe_get_business_data(business_data)`
3. **容器模式检测**：通过返回的`is_container_mode`判断是否为嵌套结构

**数据结构规范：**
- 业务数据通过`sub_business_data`字段嵌套
- 业务名称通过`sub_business_name`字段标识
- 构建方法通过`sub_business_build_method`字段指定
- 避免使用`form_data`等非标准字段名，统一使用业务数据结构

**错误处理：**
- 方法内置深度限制防止无限递归
- 返回原始数据作为降级方案
- 通过`is_container_mode`标识数据获取状态

### 集成点修改
#### select_record_by_input方法修改

在`routine_cards/quick_select_card.py`的`select_record_by_input`方法中，将事件不存在的处理逻辑从简单提示改为进入直接记录模式：

```python
# 当前逻辑（约1185-1228行）
if definitions_data and event_name in definitions_data["definitions"]:
    # 事件存在，进入快速记录模式
    # ... 现有逻辑保持不变
else:
    # 事件不存在，改为进入直接记录模式
    direct_record_data = routine_business.build_direct_record_data(
        user_id, event_name
    )
    
    business_data["workflow_state"] = "direct_record"
    business_data["container_build_method"] = container_build_method
    
    parent_data, _ = self.parent.safe_get_business_data(
        business_data, parent_business_name
    )
    parent_data["sub_business_data"] = direct_record_data
    parent_data["sub_business_name"] = CardConfigKeys.ROUTINE_DIRECT_RECORD
    sub_business_build_method = self.parent.get_sub_business_build_method(
        CardConfigKeys.ROUTINE_DIRECT_RECORD
    )
    parent_data["sub_business_build_method"] = sub_business_build_method
    
    # 更新卡片显示
    new_card_dsl = self.parent.build_update_card_data(
        business_data, container_build_method
    )
    return self.parent.save_and_respond_with_update(
        context.user_id,
        card_id,
        business_data,
        new_card_dsl,
        f"开始直接记录新事项 【{event_name}】",
        ToastTypes.SUCCESS,
    )
```

### 常量定义扩展
基于现有的`constants.py`结构，需要在相应位置添加：

```python
# 在constants.py的CardConfigKeys类中新增
class CardConfigKeys:
    # ... 现有常量
    ROUTINE_DIRECT_RECORD = "routine_direct_record"  # 新增直接记录配置键

# 在CardActions类中新增直接记录相关动作
class CardActions:
    # ... 现有动作
    # 直接记录动作
    UPDATE_DIRECT_RECORD_TYPE = "update_direct_record_type"
    UPDATE_COMPLETION_TIME = "update_completion_time"
    UPDATE_NOTE = "update_note"
    UPDATE_DEGREE = "update_degree"
    UPDATE_PROGRESS_TYPE = "update_progress_type"
    UPDATE_REMINDER_MODE = "update_reminder_mode"
    CONFIRM_DIRECT_RECORD = "confirm_direct_record"
    CANCEL_DIRECT_RECORD = "cancel_direct_record"

# 进度类型常量（如果不存在则新增）
class RoutineProgressTypes:
    NONE = "none"
    VALUE = "value"
    MODIFY = "modify"

# 目标类型常量（如果不存在则新增）
class RoutineTargetTypes:
    NONE = "none"
    TIME = "time"
    COUNT = "count"

# 直接记录字段常量（可选，用于提高代码可维护性）
class DirectRecordFields:
    RECORD_ID = "record_id"
    EVENT_NAME = "event_name"
    EVENT_TYPE = "event_type"
    TIMESTAMP = "timestamp"
    COMPLETION_TIME = "completion_time"
    NOTE = "note"
    DEGREE = "degree"
    DURATION = "duration"
    HAS_DEFINITION = "has_definition"
    CREATED_FROM = "created_from"
    PROGRESS_TYPE = "progress_type"
    PROGRESS_VALUE = "progress_value"
    TARGET_TYPE = "target_type"
    TARGET_VALUE = "target_value"
    INTERVAL_TYPE = "interval_type"
    PRIORITY = "priority"
    PLANNED_DATE = "planned_date"
    PLANNED_TIME = "planned_time"
    ESTIMATED_DURATION = "estimated_duration"
    REMINDER_MODE = "reminder_mode"
    REMINDER_TIME = "reminder_time"
    REMINDER_CYCLE = "reminder_cycle"
```

### 配置映射修改

需要在以下文件中在`CardConfigKeys.DESIGN_PLAN`和`"design_plan"`的对应位置增加`CardConfigKeys.ROUTINE_DIRECT_RECORD`和`"routine_direct_record"`：

1. **utils.py** (第164行)：
   ```python
   # 修改前
   "card_config_key": "design_plan",
   # 修改后
   "card_config_key": CardConfigKeys.ROUTINE_DIRECT_RECORD,
   ```

2. **message_handler.py** (第367行)：
   ```python
   # 修改前
   card_config_key="design_plan",
   # 修改后
   card_config_key=CardConfigKeys.ROUTINE_DIRECT_RECORD,
   ```

3. **card_handler.py** (第94行)：
   ```python
   # 修改前
   CardConfigKeys.DESIGN_PLAN, CardConfigKeys.BILIBILI_VIDEO_INFO,
   # 修改后
   CardConfigKeys.ROUTINE_DIRECT_RECORD, CardConfigKeys.BILIBILI_VIDEO_INFO,
   ```

4. **cards_operation_mapping.json** (第25行和第70行)：
   ```json
   // 修改前
   "card_config_key": "design_plan",
   "design_plan": {
   // 修改后
   "card_config_key": "routine_direct_record",
   "routine_direct_record": {
   ```

### 数据存储策略

#### 文件结构
```
user_data/
├── {user_id}/
│   ├── event_definitions.json  # 现有事件定义
│   └── event_records.json      # 现有事件记录（包含直接记录）
```

**说明**：直接记录数据继续写入现有的`event_records.json`文件，不做区分存储。

#### 直接记录在event_records.json中的结构
直接记录数据将添加到现有的`event_records.json`文件中，通过`has_definition`字段区分：

```json
{
  "user_id": "user123",
  "records": [
    {
      "record_id": "direct_record_001",
      "event_name": "喝水",
      "event_type": "instant",
      "timestamp": "2024-01-01 12:00:00",
      "completion_time": "2024-01-01 12:00:00",
      "note": "温开水",
      "degree": "适量",
      "duration": 0,
      "progress_type": "value",
      "progress_value": 250,
      "check_cycle": null,
      "target_type": "none",
      "target_value": null,
      "has_definition": false,
      "created_from": "direct_input"
    }
  ]
}
```

## 📝 开发检查清单

### 阶段1：基础架构准备
- [ ] 在 `Services/constants.py` 中添加 `RoutineProgressTypes` 和 `RoutineTargetTypes` 类
- [ ] 在 `DirectRecordFields` 中添加新字段常量（包括 `REMINDER_MODE`、`REMINDER_TIME`、`REMINDER_CYCLE` 等）
- [ ] 在 `Services/constants.py` 中添加 `CardConfigKeys.ROUTINE_DIRECT_RECORD` 常量
- [ ] 修改 `routine_cards/quick_select_card.py` 中的 `select_record_by_input` 方法，添加直接记录选项
- [ ] 修改 `feishu/utils.py` 第164行：在 `"design_plan"` 旁增加 `CardConfigKeys.ROUTINE_DIRECT_RECORD`
- [ ] 修改 `feishu/handlers/message_handler.py` 第367行： 在 `"design_plan"` 旁增加 `CardConfigKeys.ROUTINE_DIRECT_RECORD`
- [ ] 修改 `feishu/handlers/card_handler.py` 第94行：在 `CardConfigKeys.DESIGN_PLAN` 旁增加 `CardConfigKeys.ROUTINE_DIRECT_RECORD`
- [ ] 修改 `cards_operation_mapping.json` 第25行和第70行：在 `"design_plan"` 旁增加 `"routine_direct_record"`
- [ ] 创建 `routine_cards/direct_record_card.py` 文件并实现 `DirectRecordCard` 类
- [ ] 在 `routine_cards/main_coordinator.py` 中导入并初始化 `DirectRecordCard` 实例
- [ ] 在 `routine_cards/__init__.py` 中添加 `DirectRecordCard` 的导出
- [ ] 更新 `routine_cards/main_coordinator.py` 中的 `_configs` 配置映射以支持新的直接记录卡片
- [ ] 测试：确认常量可正常导入和使用

### 阶段2：表单架构设计
- [ ] 在 `routine_cards/direct_record_card.py` 中实现 `_build_direct_record_form_elements` 方法，区分表单内外字段
- [ ] 在 `routine_cards/direct_record_card.py` 中实现 `_build_form_fields_by_type` 方法，使用 `match` 语句进行类型分发
- [ ] 修改类型选择逻辑，过滤掉 `END` 类型，使用正确的 `action_data` 结构
- [ ] 测试：验证表单结构正确，字段分布符合预期

### 阶段3：瞬间完成和开始类型
- [ ] 在 `routine_cards/direct_record_card.py` 中实现 `_build_instant_start_form_fields` 方法（表单内字段）
- [ ] 在 `routine_cards/direct_record_card.py` 中实现 `_get_progress_type_options` 方法，使用正确的文本格式
- [ ] 在 `routine_cards/direct_record_card.py` 中实现 `update_progress_type` 和 `update_direct_record_type` 回调方法
- [ ] 确保指标类型状态在类型切换时保留
- [ ] 测试：验证字段显示、指标类型切换和状态保留功能

### 阶段4：长期项目类型
- [ ] 在 `routine_cards/direct_record_card.py` 中实现 `_build_ongoing_form_fields` 方法（表单内字段）
- [ ] 在 `routine_cards/direct_record_card.py` 中实现 `_get_interval_type_options` 和 `_get_target_type_options` 方法
- [ ] 确保指标值占位符根据指标类型正确显示
- [ ] 测试：验证间隔类型、目标设置和指标值输入功能

### 阶段5：未来事项类型
- [ ] 在 `routine_cards/direct_record_card.py` 中实现 `_build_future_form_fields` 方法（表单内字段）
- [ ] 在 `routine_cards/direct_record_card.py` 中实现 `_get_priority_options`、`_get_reminder_time_options` 和 `_get_reminder_cycle_options` 方法
- [ ] 在 `routine_cards/direct_record_card.py` 中实现 `update_reminder_mode` 回调方法
- [ ] 确保提醒相关字段根据提醒模式动态显示
- [ ] 测试：验证日期时间选择、重要性设置和提醒功能

### 阶段6：数据处理和提交
- [ ] 在 `routine_cards/direct_record_card.py` 中实现 `_handle_direct_record_field_update` 通用字段更新方法
- [ ] 在 `routine_cards/direct_record_card.py` 中实现 `confirm_direct_record` 表单提交处理方法
- [ ] 在 `routine_cards/direct_record_card.py` 中实现 `update_direct_record_type` 方法：处理事项类型变更
- [ ] 修改 `routine_cards/quick_select_card.py` 中的 `select_record_by_input` 方法：在事件不存在时进入直接记录模式
- [ ] 确保表单数据和非表单数据正确合并
- [ ] 实现配置清理逻辑
- [ ] 在 `Services/routine_record.py` 业务层实现 `build_direct_record_data` 和 `create_direct_record` 方法
- [ ] 确保使用 `safe_get_business_data` 方法正确处理嵌套数据结构
- [ ] 验证容器模式兼容性和数据传递正确性
- [ ] 测试：验证数据提交、状态保存和配置管理功能

## 🔄 后续优化方向

1. **数据迁移工具**：直接记录转换为事件定义的工具
2. **统计分析**：直接记录的数据分析和可视化
3. **性能优化**：大量记录的查询和存储优化
4. **用户体验**：智能提示和自动补全功能
5. **数据同步**：直接记录与事件定义记录的统一管理

## 总结

本重构方案基于现有的例行事务记录系统，通过扩展输入框功能实现直接记录新事项的能力。主要特点：

1. **架构兼容性**：完全基于现有的卡片嵌套架构和拆分后的模块化结构，无需修改核心框架
2. **数据安全性**：使用`safe_get_business_data`方法确保嵌套数据处理的安全性
3. **配置一致性**：统一使用`CardConfigKeys.ROUTINE_DIRECT_RECORD`替换原有的设计规划配置
4. **模块化设计**：基于新的`routine_cards`目录结构，创建独立的`DirectRecordCard`类
5. **代码规范性**：遵循现有的方法命名和结构模式，保持代码一致性

### 文件结构更新

基于项目重构后的新结构：
- **主协调器**: `routine_cards/main_coordinator.py` - 负责路由和协调
- **快速选择**: `routine_cards/quick_select_card.py` - 包含`select_record_by_input`方法修改
- **记录卡片**: `routine_cards/record_card.py` - 现有记录功能
- **直接记录**: `routine_cards/direct_record_card.py` - 新增的直接记录功能
- **共享工具**: `routine_cards/shared_utils.py` - 通用方法和工具

通过本方案，用户可以在输入框中直接输入新事项名称，系统将自动进入直接记录模式，提供完整的事项定义和记录功能，大大提升了用户体验和操作效率。

---

**文档版本**：v1.0  
**创建时间**：2024-01-01  
**最后更新**：2024-01-01  
**状态**：待开发