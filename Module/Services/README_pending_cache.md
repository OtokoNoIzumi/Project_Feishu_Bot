# 缓存业务服务 (PendingCacheService)

## 概述

缓存业务服务是一个通用的操作确认和缓存系统，专门为需要用户确认的敏感操作设计。它提供了倒计时、自动执行、用户限制等功能，并与飞书卡片系统深度集成。

## 核心特性

### 🎯 业务特性
- **操作缓存**: 在真正执行前将操作存储在缓存中
- **用户确认**: 通过飞书卡片提供交互式确认界面
- **倒计时机制**: 可配置的操作超时时间
- **默认操作**: 超时后的默认行为（确认/取消）
- **用户限制**: 每用户最大并发操作数限制
- **状态管理**: 完整的操作生命周期跟踪

### 🔧 技术特性
- **类型安全**: 使用dataclass和enum提供类型安全
- **异步定时器**: 非阻塞的倒计时实现
- **持久化**: 操作自动保存到磁盘，支持服务重启
- **可扩展**: 通过执行器模式支持不同业务类型
- **错误恢复**: 优雅的异常处理和错误恢复

## 架构设计

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Admin Input   │    │  Message        │    │  Feishu         │
│   Command       ├────┤  Processor      ├────┤  Adapter        │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Admin           │    │ Pending Cache   │    │ Admin Card      │
│ Processor       ├────┤ Service         ├────┤ Manager         │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ API Executor    │    │ Timer Manager   │    │ Feishu Card     │
│ (User Update)   │    │ (Async)         │    │ Template        │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 使用流程

### 1. 初始化服务

```python
from Module.Services.pending_cache_service import PendingCacheService

# 创建服务实例
cache_service = PendingCacheService(
    cache_dir="cache",
    max_operations_per_user=2
)

# 注册执行器
def execute_user_update(operation):
    # 实际的API调用逻辑
    return call_user_update_api(operation.operation_data)

cache_service.register_executor("update_user", execute_user_update)
```

### 2. 创建缓存操作

```python
# 在admin_processor中
operation_id = cache_service.create_operation(
    user_id=context.user_id,           # 管理员用户ID
    operation_type="update_user",      # 操作类型
    operation_data={                   # 操作数据
        'user_id': '696423',
        'user_type': 2,
        'admin_input': '更新用户 696423 支持者'
    },
    admin_input="更新用户 696423 支持者",
    hold_time_seconds=30,              # 30秒倒计时
    default_action="confirm"           # 默认确认
)
```

### 3. 生成确认卡片

```python
from Module.Adapters.feishu_cards.admin_cards import AdminCardManager

admin_card_manager = AdminCardManager()

# 准备卡片数据
card_data = {
    'user_id': '696423',
    'user_type': 2,
    'admin_input': '更新用户 696423 支持者',
    'operation_id': operation_id,
    'finished': False,
    'hold_time': '30秒'
}

# 生成卡片
card_content = admin_card_manager.build_user_update_confirm_card(card_data)
```

### 4. 处理用户交互

```python
# 在message_processor中处理卡片回调
def handle_pending_admin_card_action(self, context, action_value):
    return self.admin_processor.handle_pending_operation_action(context, action_value)

# 在admin_processor中
def handle_pending_operation_action(self, context, action_value):
    action = action_value.get('action', '')
    operation_id = action_value.get('operation_id', '')

    if action == "confirm_user_update":
        success = pending_cache_service.confirm_operation(operation_id)
        # 生成结果卡片...
    elif action == "cancel_user_update":
        success = pending_cache_service.cancel_operation(operation_id)
        # 生成取消卡片...
```

## 状态管理

### 操作状态枚举
```python
class OperationStatus(Enum):
    PENDING = "pending"      # 等待确认
    CONFIRMED = "confirmed"  # 已确认
    CANCELLED = "cancelled"  # 已取消
    EXPIRED = "expired"      # 已过期
    EXECUTED = "executed"    # 已执行
```

### 状态转换图
```
    [创建]
      │
      ▼
  ┌─────────┐
  │ PENDING │
  └─────────┘
      │
      ├─ 用户确认 ──────► [EXECUTED]
      ├─ 用户取消 ──────► [CANCELLED]
      └─ 超时 ─────────► [EXPIRED] → [EXECUTED/CANCELLED]
```

## 配置选项

### 缓存服务配置
```python
cache_service = PendingCacheService(
    cache_dir="cache",                    # 缓存目录
    max_operations_per_user=2             # 用户最大并发操作数
)
```

### 操作配置
```python
operation_id = cache_service.create_operation(
    user_id="admin_12345",
    operation_type="update_user",
    operation_data={...},
    admin_input="原始命令",
    hold_time_seconds=30,                 # 倒计时时间
    default_action="confirm"              # 默认操作: confirm/cancel
)
```

### 卡片模板配置
```python
# 在admin_cards.py中
self.templates = {
    "admin_user_update_confirm": {
        "template_id": "AAqdbwJ2cflOp",   # 飞书模板ID
        "template_version": "1.0.0"      # 模板版本
    }
}
```

## 扩展指南

### 添加新的操作类型

1. **注册执行器**
```python
def execute_new_operation(operation):
    # 具体的执行逻辑
    return True

cache_service.register_executor("new_operation_type", execute_new_operation)
```

2. **添加卡片模板**
```python
# 在对应的卡片管理器中添加新模板
self.templates["new_operation_confirm"] = {
    "template_id": "YOUR_TEMPLATE_ID",
    "template_version": "1.0.0"
}
```

3. **实现处理逻辑**
```python
# 在相应的processor中添加处理方法
def handle_new_operation_command(self, context, user_msg):
    # 解析命令，创建缓存操作
    operation_id = self._create_pending_new_operation(...)
    return ProcessResult.success_result("admin_card_send", data)
```

### 自定义倒计时时间

可以根据操作重要性设置不同的倒计时：
```python
OPERATION_TIMEOUTS = {
    "update_user": 30,      # 30秒
    "delete_data": 60,      # 60秒 (更重要)
    "system_config": 120,   # 2分钟 (最重要)
}

hold_time = OPERATION_TIMEOUTS.get(operation_type, 30)
```

## 最佳实践

### 1. 错误处理
```python
try:
    operation_id = cache_service.create_operation(...)
    return ProcessResult.success_result("admin_card_send", data)
except Exception as e:
    debug_utils.log_and_print(f"创建缓存操作失败: {e}", log_level="ERROR")
    return ProcessResult.error_result("操作创建失败")
```

### 2. 日志记录
```python
# 在关键操作点添加日志
debug_utils.log_and_print(f"✅ 创建缓存操作: {operation_id}", log_level="INFO")
debug_utils.log_and_print(f"⏰ 用户 {user_id} 操作超时自动执行", log_level="WARN")
```

### 3. 性能优化
- 定期清理过期操作（自动实现）
- 合理设置用户并发限制
- 使用异步定时器避免阻塞

### 4. 安全考虑
- 验证用户权限
- 限制操作频率
- 记录敏感操作日志

## 故障排除

### 常见问题

1. **操作自动执行失败**
   - 检查执行器是否正确注册
   - 查看API调用是否成功
   - 检查网络连接和权限

2. **卡片显示异常**
   - 验证模板ID和版本
   - 检查模板参数格式
   - 确认飞书模板配置

3. **定时器不工作**
   - 确认服务运行状态
   - 检查系统时间同步
   - 查看线程资源是否充足

### 调试工具

```python
# 获取服务状态
status = cache_service.get_service_status()
print(json.dumps(status, indent=2))

# 查看用户操作
operations = cache_service.get_user_operations(user_id)
for op in operations:
    print(f"Operation {op.operation_id}: {op.status.value}")

# 检查特定操作
operation = cache_service.get_operation(operation_id)
if operation:
    print(f"剩余时间: {operation.get_remaining_time_text()}")
```

## 更新日志

### v1.0.0 (2024-12)
- 🎉 初始版本发布
- ✅ 实现基础缓存业务功能
- ✅ 集成飞书卡片系统
- ✅ 支持用户状态更新操作
- ✅ 提供完整的演示程序

## 贡献指南

1. 遵循现有的代码规范
2. 添加完整的类型注解
3. 提供详细的文档说明
4. 编写相应的测试用例
5. 确保向后兼容性

## 许可证

本项目使用相同的许可证作为主项目。