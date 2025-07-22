# 菜单记录功能扩展重构方案

## 📋 项目概述

### 核心目标
扩展菜单触发的卡片记录功能，支持在没有事件定义的情况下直接添加记录。

### 设计原则
1. **保留现有逻辑**：旧的record方法完全保留，避免影响现有功能
2. **渐进式开发**：分MVP阶段实现，数据结构一次性规划到位
3. **类型驱动**：以事件类型为核心，动态显示相应字段
4. **容器模式兼容**：与现有集成模式架构保持一致

## ✅ 已完成功能

### 直接记录核心功能
- **业务层实现**：`routine_record.py` 中的 `create_direct_record` 方法
- **适配器层实现**：`direct_record_card.py` 完整卡片功能
- **事件定义自动创建**：非 `future` 类型事项自动创建事件定义
- **时间格式支持**：支持带时区的时间格式验证
- **UI优化**：预估耗时和备注字段移至折叠面板

### 核心方法索引
- `RoutineRecord.create_direct_record()` - 创建直接记录
- `RoutineRecord._create_event_definition_from_direct_record()` - 自动创建事件定义
- `DirectRecordCard.build_direct_record_card()` - 构建直接记录卡片
- `DirectRecordCard.confirm_direct_record()` - 确认记录提交

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

## 🚀 开发进展

### ✅ 已完成阶段

#### 阶段1-6：基础架构到数据处理 (已完成)
- **业务层**：`RoutineRecord.create_direct_record()` 方法完整实现
- **适配器层**：`DirectRecordCard` 类完整实现，支持所有事件类型
- **数据验证**：时间格式验证，支持带时区格式
- **事件定义**：自动创建机制，统计信息维护
- **UI交互**：类型切换、字段动态显示、表单提交
- **集成点**：与 `quick_select_card` 的无缝集成

### 🔄 当前开发重点

#### 洗面奶使用追踪场景优化
基于用户提出的洗面奶使用追踪场景，正在规划以下架构优化：

**核心问题解决**：
- **认知负荷**：简化事件名称设定，通过直觉化操作记录
- **信息噪音**：通过 `active_records` 索引同类型事件，减少重复输入
- **关联追踪**：实现父子事件关联，形成完整业务周期

**技术实现方向**：
- `records` 和 `active_records` 改为 `OrderedDict` 存储
- `query_results_card` 增加工作流按钮（记录进度、完成事项、查看历史）
- 智能关联机制和预填充策略
- 一键流转功能，预填充字段和关联事件类型

### 阶段3-5：核心功能实现（已完成）

#### 已实现功能概览
- **瞬间完成和开始类型**：支持耗时、完成方式、备注、指标值记录
- **长期项目类型**：支持间隔类型、目标设置、指标追踪
- **未来事项类型**：支持日期时间、重要性、提醒设置
- **动态表单**：根据事件类型和指标类型动态显示字段
- **状态保持**：类型切换时保留已输入数据
- **数据提交**：完整的表单验证和记录创建流程





## 🚀 未来整合规划

### 洗面奶场景架构优化

#### 数据结构优化
- **OrderedDict 存储**：`records` 和 `active_records` 改为有序字典
- **关联机制**：支持父子事件关联，形成完整业务周期
- **智能索引**：通过 `active_records` 快速定位同类型事件

#### 工作流按钮设计
在 `query_results_card` 中增加：
- **记录进度**：快速记录当前状态（如检查剩余量）
- **完成事项**：标记事项完成并开启新周期
- **查看历史**：查看完整的使用历史记录

#### 智能关联与预填充
- **主动关联**：用户手动选择关联的父事件
- **被动关联**：系统根据事件名称模式自动建议关联
- **预填充策略**：基于历史记录智能预填充常用字段
- **一键流转**：从检查进度直接流转到完成记录

### 技术实现要点

#### 核心方法扩展
- `RoutineRecord.get_active_records_by_type()` - 按类型获取活跃记录
- `QueryResultsCard.build_workflow_buttons()` - 构建工作流按钮
- `DirectRecordCard.build_related_record_form()` - 构建关联记录表单
- `RoutineRecord.create_related_record()` - 创建关联记录

#### 用户体验流程
1. **开始使用**：创建"开始使用新洗面奶"记录
2. **定期检查**：通过工作流按钮快速记录检查结果
3. **完成使用**：标记用完，自动关联历史记录
4. **数据分析**：基于关联记录生成使用周期统计

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

## 📝 开发状态总结

### ✅ 已完成功能
- **基础架构**：常量定义、配置映射、模块初始化
- **表单架构**：动态字段显示、类型切换、状态保持
- **所有事件类型**：瞬间完成、开始、长期项目、未来事项
- **数据处理**：表单提交、验证、记录创建
- **业务集成**：与现有系统的无缝集成

### 🔄 当前开发重点

#### 洗面奶场景优化任务
- [ ] 实现 `OrderedDict` 存储结构替换现有列表存储
- [ ] 在 `query_results_card` 中添加工作流按钮（记录进度、完成事项、查看历史）
- [ ] 实现智能关联机制：父子事件关联、预填充策略
- [ ] 开发一键流转功能：从检查进度到完成记录的快速转换
- [ ] 实现 `active_records` 索引和关联事件查找

#### 核心方法待实现
- [ ] `RoutineRecord.get_active_records_by_type()` - 按类型获取活跃记录
- [ ] `QueryResultsCard.build_workflow_buttons()` - 构建工作流按钮
- [ ] `DirectRecordCard.build_related_record_form()` - 构建关联记录表单
- [ ] `RoutineRecord.create_related_record()` - 创建关联记录

## 🔄 后续优化方向

1. **数据迁移工具**：直接记录转换为事件定义的工具
2. **统计分析**：直接记录的数据分析和可视化
3. **性能优化**：大量记录的查询和存储优化
4. **用户体验**：智能提示和自动补全功能
5. **数据同步**：直接记录与事件定义记录的统一管理

## 总结

### 🎯 项目现状

**直接记录功能**已完全实现，用户可以在输入框中直接输入新事项名称，系统自动进入直接记录模式，支持所有事件类型的完整记录功能。

### 🚀 下一阶段目标

基于用户提出的**洗面奶使用追踪场景**，正在规划架构优化：

**核心价值**：
- 解决认知负荷：简化事件名称设定流程
- 减少信息噪音：通过智能关联减少重复输入
- 完整业务追踪：实现父子事件关联，形成完整使用周期

**技术实现**：
- 数据结构优化：`OrderedDict` 存储，支持快速索引
- 工作流按钮：在查询结果中提供快速操作入口
- 智能关联：自动识别和建议相关事件关联
- 一键流转：从进度检查到完成记录的无缝转换

### 📁 当前文件结构

- **主协调器**: `routine_cards/main_coordinator.py` - 路由和协调
- **快速选择**: `routine_cards/quick_select_card.py` - 事件选择和直接记录入口
- **记录卡片**: `routine_cards/record_card.py` - 基于定义的记录功能
- **直接记录**: `routine_cards/direct_record_card.py` - ✅ 已完成的直接记录功能
- **查询结果**: `routine_cards/query_results_card.py` - 🔄 待优化的工作流按钮
- **业务逻辑**: `Services/routine_record.py` - ✅ 已完成核心业务方法

---

**文档版本**：v2.0  
**创建时间**：2024-01-01  
**最后更新**：2025-07-22  
**状态**：直接记录功能已完成，洗面奶场景优化规划中