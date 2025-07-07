# 定时任务与信息汇总架构设计

## 概述

本文档描述了针对用户需求（每2小时个人状态评估、每周盘点、每月盘点等）设计的**定时器分层管理 + 信息汇总**架构方案，有效解决了信息冲刷问题，实现了智能的定时任务管理。

## 核心架构

### 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      SchedulerService                      │
│                    (业务定时任务统一管理)                      │
├─────────────────────────────────────────────────────────────┤
│ • 每日汇总 (8:00)          • 个人状态评估 (每2小时)           │
│ • B站更新 (12:00, 18:00)   • 周度盘点 (周日 20:00)          │
│ • 月度盘点 (月末 19:00)    • ... 更多定时任务               │
└─────────────────┬───────────────────────────────────────────┘
                  │ 事件发布
                  ▼
┌─────────────────────────────────────────────────────────────┐
│               MessageAggregationService                     │
│                   (信息汇总与智能调度)                        │
├─────────────────────────────────────────────────────────────┤
│ • 收集各种定时任务信息      • AI智能汇总                     │
│ • 按优先级排序             • 避免信息冲刷                    │
│ • 智能时间窗口管理         • 批量发送机制                    │
└─────────────────┬───────────────────────────────────────────┘
                  │ 汇总发送
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                  用户接收汇总消息                            │
│                (友好的AI摘要格式)                            │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│               PendingCacheService                           │
│                 (UI更新，独立运行)                           │
│ • 1秒间隔UI更新           • 独立于业务定时任务              │
└─────────────────────────────────────────────────────────────┘
```

## 设计原则

### 1. 定时器分层管理

**业务层定时器**：
- `SchedulerService` 统一管理所有业务定时任务
- 支持每日、每2小时、每周、每月等多种频率
- 使用事件机制解耦前端实现

**UI层定时器**：
- `PendingCacheService` 保持独立的高频UI更新
- 专注于用户交互体验，1秒间隔更新倒计时

### 2. 信息汇总策略

**收集阶段**：
- 各定时任务产生信息时不直接发送
- 先收集到 `MessageAggregationService`
- 按来源类型、优先级分类管理

**汇总阶段**：
- 智能时间窗口（默认5分钟）
- 消息数量阈值触发（2-8条消息）
- 紧急消息立即处理

**发送阶段**：
- AI生成友好摘要
- 合并相似信息
- 一次性发送汇总结果

## 新增功能

### 1. 个人状态评估 (每2小时)

**数据收集**：
- 系统健康状态检查
- 待处理任务统计
- 服务运行状况
- 性能指标监控

**触发时间**：建议 9:00, 15:00, 21:00

### 2. 周度盘点 (每周日)

**数据内容**：
- 本周系统统计
- 成果亮点汇总
- 下周关注重点
- 服务运行报告

### 3. 月度盘点 (每月末)

**数据内容**：
- 月度关键成就
- 系统演进情况
- 增长指标分析
- 下月目标设定

## 技术实现

### 新增服务

1. **MessageAggregationService**
   - 消息收集与优先级管理
   - AI汇总引擎集成
   - 智能调度算法

2. **扩展SchedulerService**
   - 新增状态评估、周度、月度任务
   - 数据收集方法集成
   - 事件发布机制

3. **扩展ScheduleProcessor**
   - 新任务类型处理
   - 信息格式化方法
   - 降级处理逻辑

### 配置管理

支持通过 `config.json` 灵活配置：

```json
{
  "scheduler": {
    "tasks": [
      {
        "name": "personal_status_morning",
        "type": "personal_status_eval",
        "time": "09:00",
        "enabled": true
      }
    ]
  }
}
```

## 使用指南

### 1. 启用新功能

将 `config_with_new_tasks_example.json` 的内容复制到你的 `config.json`：

```bash
# 备份现有配置
cp config.json config.json.bak

# 应用新配置
cp config_with_new_tasks_example.json config.json
```

### 2. 配置定时任务

根据个人需求调整任务时间：

```json
{
  "name": "personal_status_afternoon",
  "type": "personal_status_eval",
  "time": "15:00",  // 调整为你喜欢的时间
  "enabled": true   // 启用或禁用
}
```

### 3. 调整汇总参数

根据信息量调整汇总策略：

```python
aggregation_service.configure_aggregation(
    window_seconds=300,  # 汇总时间窗口
    max_messages=8,      # 最多消息数
    min_messages=2       # 最少触发数
)
```

## 性能优化

### 1. 定时器资源管理

- 业务定时任务：1秒检查间隔，多任务共享
- UI更新：独立1秒间隔，专注用户体验
- 清理任务：动态间隔调整，节省资源

### 2. 信息处理优化

- 消息批量处理，减少API调用
- AI汇总智能去重，避免冗余信息
- 优先级机制，重要信息优先处理

### 3. 内存管理

- 过期消息自动清理（24小时）
- 已处理消息及时移除
- 服务状态监控和告警

## 扩展性

### 添加新的定时任务类型

1. **在constants.py添加新类型**：
```python
class SchedulerTaskTypes:
    NEW_TASK_TYPE = "new_task_type"
```

2. **在SchedulerService添加触发方法**：
```python
def trigger_new_task(self):
    # 实现新任务逻辑
    pass
```

3. **在TaskUtils注册**：
```python
SchedulerTaskTypes.NEW_TASK_TYPE: scheduler_service.trigger_new_task
```

4. **在ScheduleProcessor添加处理方法**：
```python
def handle_new_task(self, task_data):
    # 处理新任务数据
    pass
```

### 自定义汇总策略

```python
# 为特定消息类型设置规则
aggregation_service.set_aggregation_rule("new_task_type", {
    "priority": "high",
    "immediate_send": True,
    "merge_strategy": "standalone"
})
```

## 故障排除

### 常见问题

1. **信息汇总服务未启动**
   - 检查 `MessageAggregationService` 是否正确注册
   - 查看服务状态：`app_controller.health_check()`

2. **定时任务不执行**
   - 检查任务配置：`enabled: true`
   - 查看调度器状态：`scheduler_service.get_status()`

3. **消息不汇总**
   - 检查消息数量是否达到阈值
   - 查看汇总回调是否正确注册

### 调试方法

```python
# 查看汇总服务状态
aggregation_service = app_controller.get_service(ServiceNames.MESSAGE_AGGREGATION)
print(aggregation_service.get_status())

# 查看定时任务列表
scheduler_service = app_controller.get_service(ServiceNames.SCHEDULER)
print(scheduler_service.list_tasks())

# 强制触发汇总
aggregation_service._trigger_aggregation(reason="debug")
```

## 总结

通过**定时器分层管理 + 信息汇总**架构，我们成功解决了：

✅ **避免信息冲刷**：AI汇总多条信息为简洁摘要
✅ **高效资源利用**：业务定时器统一管理，UI更新独立运行
✅ **灵活扩展**：支持任意定时任务类型和汇总策略
✅ **用户体验**：智能调度，友好的信息呈现

这个架构为你的个人状态评估、周度盘点、月度盘点等需求提供了完整的技术支撑，同时保持了系统的高性能和可维护性。