# 飞书卡片系统硬编码优化技术方案
## refactor_0626.md

### 1. 项目背景

基于`design_plan_cards.py`这个90%完成度的示例模板，发现整个业务堆栈中存在严重的硬编码问题，主要集中在两个handler和message_processor模块中。

**当前架构**: 1+3层架构
- **应用控制层（容器）**: 服务编排、生命周期管理
- **适配器层**: 飞书协议转换、事件处理
- **业务逻辑层**: 消息路由、业务规则处理
- **服务层**: 具体功能实现、数据持久化

**配置驱动**: `cards_operation_mapping.json`提供业务初始化信息

### 2. 核心硬编码问题

#### 2.1 MessageProcessor层硬编码
```python
# Module/Business/message_processor.py
self.action_dispatchers = {
    CardActions.CONFIRM_USER_UPDATE: self._handle_pending_admin_card_action,
    CardActions.CONFIRM_ADS_UPDATE: self._handle_pending_admin_card_action,
    CardActions.CONFIRM_DESIGN_PLAN: self._handle_design_plan_action,
    # ❌ 每个新卡片都需要手动添加
}
```

#### 2.2 CardHandler层硬编码
```python
# Module/Adapters/feishu/handlers/card_handler.py
match result.response_type:
    case ResponseTypes.BILI_CARD_UPDATE:
        return self._handle_bili_card_operation(...)
    case ResponseTypes.ADMIN_CARD_UPDATE:
        return self._handle_admin_card_operation(...)
    # ❌ 每个新卡片都需要手动添加
```

### 3. 解决方案核心思路

**属地集中管理**: 在卡片的`format_xxx_params`方法中内置必要信息到交互事件回调对象中，实现配置的属地集中管理。

**优势**:
- 自然知道来源card_manager
- 知道对应调用的method
- 实现配置的属地集中管理

### 4. 关键约束和否决点

#### 4.1 信息标准化收集
- **要求**: 在handler的convert方法中完成所有有价值信息的标准化处理
- **禁止**: 后续不再访问原始飞书data结构

#### 4.2 真正解耦
- **要求**: 业务层和飞书解耦，方法不应依赖`feishu_data`
- **禁止**: 业务层方法接受`feishu_data`参数

#### 4.3 路由必要性
- **必须**: `card_config_key`必须注入到`action_value`中
- **原因**: MessageProcessor需要通过它路由到正确的card_manager

#### 4.4 YAGNI原则
- **禁止**: 添加现阶段用不到的参数
- **禁止**: 冗余的双层方法设计

### 5. Handler标准化分析

基于三个handler的convert方法分析：

| Handler | 标准字段 | 独立必要字段 | 弹性Metadata |
|---------|----------|-------------|-------------|
| **MessageHandler** | `user_id`, `user_name`, `content`, `timestamp`, `event_id`, `message_id` | `parent_message_id` | `chat_id`, `chat_type` |
| **MenuHandler** | `user_id`, `user_name`, `content`, `timestamp`, `event_id` | - | `app_id` |
| **CardHandler** | `user_id`, `user_name`, `content`, `timestamp`, `event_id` | `adapter_name`, `message_id` | `action_value`, `action_tag` |

### 6. 实施方案

#### 6.1 MessageContext标准化
```python
@dataclass
class MessageContext:
    # 标准字段（所有handler共有）
    user_id: str
    user_name: str
    content: str
    timestamp: datetime
    event_id: str

    # 独立必要字段（handler特有）
    adapter_name: str           # ✅ 新增：标识来源adapter，在各自handle的convert里添加
    message_id: Optional[str]   # MessageHandler/CardHandler需要
    parent_message_id: Optional[str]  # MessageHandler需要

    # 弹性metadata（具体业务数据）
    metadata: Dict[str, Any] = field(default_factory=dict)
```

#### 6.2 CardHandler.convert标准化
```python
def _convert_card_to_context(self, data) -> Optional[MessageContext]:
    """将飞书卡片动作转换为标准消息上下文"""

    # 标准字段
    event_id = data.header.event_id
    user_id = data.event.operator.operator_id.open_id
    user_name = self._get_user_name(user_id)
    timestamp = extract_timestamp(data)

    # 独立必要字段
    adapter_name = "feishu"  # ✅ 标识来源adapter
    message_id = data.event.context.open_message_id  # ✅ update操作需要

    # 动作信息提取
    action = data.event.action
    action_value = action.value if action.value else {}
    action_tag = action.tag if hasattr(action, 'tag') else DefaultValues.EMPTY_STRING
    content = action_value.get(FieldNames.ACTION, DefaultValues.UNKNOWN_ACTION)

    return MessageContext(
        user_id=user_id,
        user_name=user_name,
        message_type=MessageTypes.CARD_ACTION,
        content=content,
        timestamp=timestamp,
        event_id=event_id,
        adapter_name=adapter_name,  # ✅ 独立字段
        message_id=message_id,      # ✅ 独立字段
        metadata={
            'action_value': action_value,  # ✅ 弹性数据
            'action_tag': action_tag       # ✅ 弹性数据
        }
    )
```

#### 6.3 卡片管理器注入card_config_key
```python
def get_interaction_components(self, **kwargs):
    """构建交互组件"""

    # ✅ card_config_key是路由必需信息，必须注入
    base_action_value = {
        "card_config_key": self.card_config_key  # ✅ MessageProcessor路由需要
    }

    confirm_action_value = {
        **base_action_value,
        "action": CardActions.CONFIRM_DESIGN_PLAN
    }

    # ... 构建按钮组件
```

#### 6.4 MessageProcessor配置驱动分发
```python
def _process_card_action(self, context: MessageContext):
    """处理卡片动作 - 配置驱动"""
    # ✅ 获取adapter，分发回adapter层处理
    adapter_name = context.adapter_name
    adapter = self.app_controller.get_adapter(adapter_name)

    if not adapter or not hasattr(adapter, 'card_handler'):
        return ProcessResult.error_result(f"未找到adapter或card_handler: {adapter_name}")

    # ✅ 分发回adapter的card_handler继续处理，保持层次边界
    return adapter.card_handler.handle_card_action(context)
```

#### 6.5 CardHandler新增handle_card_action方法
```python
def handle_card_action(self, context: MessageContext) -> ProcessResult:
    """处理卡片动作 - 配置驱动路由到具体card_manager"""
    action_value = context.metadata.get('action_value', {})

    # ✅ 通过card_config_key路由到正确的card_manager
    card_config_key = action_value.get('card_config_key')
    if not card_config_key:
        return ProcessResult.error_result("缺少卡片配置键")

    # 获取card_manager
    card_manager = self.card_registry.get_manager(card_config_key)
    if not card_manager:
        return ProcessResult.error_result(f"未找到卡片管理器: {card_config_key}")

    # ✅ 调用card_manager的handle方法，传入标准化context
    action = action_value.get('action')
    method_name = f"handle_{action}"

    if hasattr(card_manager, method_name):
        return getattr(card_manager, method_name)(context)
    else:
        return ProcessResult.error_result(f"未支持的动作: {action}")

def handle_feishu_card(self, data) -> P2CardActionTriggerResponse:
    """统一处理飞书卡片动作"""
    context = self._convert_card_to_context(data)
    if not context:
        return self._create_error_response("卡片上下文转换失败")

    # ✅ 统一通过MessageProcessor分发，移除所有硬编码分支
    result = self.message_processor.process_message(context)

    # ✅ 统一响应处理
    return self._create_card_response(result)
```

#### 6.6 卡片管理器标准化方法
```python
class BaseCardManager:
    def handle_confirm_design_plan(self, context: MessageContext) -> ProcessResult:
        """处理设计方案确认动作"""
        # ✅ 只接受标准化context，不依赖feishu_data
        action_value = context.metadata.get('action_value', {})

        # 业务逻辑处理...

        return ProcessResult.success_result(...)
```

### 7. 实施步骤

1. **步骤1**: 修改MessageContext添加`adapter_name`字段
2. **步骤2**: 修改CardHandler.convert添加必要字段收集
3. **步骤3**: 卡片管理器注入card_config_key到action_value
4. **步骤4**: MessageProcessor实现配置驱动分发到adapter
5. **步骤5**: CardHandler新增handle_card_action方法路由到card_manager
6. **步骤6**: CardHandler移除硬编码响应分支
7. **步骤7**: 卡片管理器实现标准化handle方法

### 8. 需要修改的模块清单

#### 8.1 核心数据结构修改
- `Module/Business/processors/base_processor.py`
  - 修改MessageContext添加`adapter_name`字段

#### 8.2 Handler层修改
- `Module/Adapters/feishu/handlers/message_handler.py`
  - `_convert_message_to_context`方法添加`adapter_name="feishu"`

- `Module/Adapters/feishu/handlers/menu_handler.py`
  - `_convert_menu_to_context`方法添加`adapter_name="feishu"`

- `Module/Adapters/feishu/handlers/card_handler.py`
  - `_convert_card_to_context`方法添加`adapter_name="feishu"`和`message_id`
  - 新增`handle_card_action`方法实现配置驱动路由
  - 移除`handle_feishu_card`中的硬编码分支

#### 8.3 业务逻辑层修改
- `Module/Business/message_processor.py`
  - 修改`_process_card_action`方法，改为分发到adapter
  - 移除硬编码的`action_dispatchers`

#### 8.4 卡片管理器修改
- `Module/Adapters/feishu/cards/design_plan_cards.py`
  - `get_interaction_components`方法注入`card_config_key`
  - 新增`handle_confirm_design_plan`方法

- `Module/Adapters/feishu/cards/user_update_cards.py`
  - `get_interaction_components`方法注入`card_config_key`
  - 新增`handle_confirm_user_update`方法
  - 新增`handle_cancel_user_update`方法
  - 新增`handle_update_user_type`方法

- `Module/Adapters/feishu/cards/ads_update_cards.py`
  - `get_interaction_components`方法注入`card_config_key`
  - 新增`handle_confirm_ads_update`方法
  - 新增`handle_cancel_ads_update`方法
  - 新增`handle_adtime_editor_change`方法

- `Module/Adapters/feishu/cards/bilibili_cards.py`
  - `_format_bili_video_params`方法中注入`card_config_key`到`action_info`
  - 新增`handle_mark_bili_read`方法

#### 8.4.1 Schedule模块向后兼容处理
**兼容策略**：保持现有分发机制，通过`card_type`区分新旧体系
- `Module/Business/message_processor.py`
  - 保留`_handle_mark_bili_read`的智能分发逻辑
  - `card_type="daily"` → ScheduleProcessor（老方法）
  - `card_type="menu"` → BilibiliCards（新体系）

- `Module/Business/processors/schedule_processor.py`
  - 保持现有`handle_mark_bili_read`方法不变
  - 保持`original_analysis_data`数据结构不变
  - 保持`SCHEDULER_CARD_UPDATE_BILI_BUTTON`响应类型不变

**注意**：Schedule模块的卡片不加入新cards体系，通过`card_type`标识区分处理路径

#### 8.5 应用控制层修改
- `Module/Application/app_controller.py`
  - 确认`get_adapter`方法存在并正常工作
  - 可能需要adapter注册管理逻辑

#### 8.6 基础类修改
- `Module/Adapters/feishu/cards/card_registry.py`
  - 可能需要添加通用的handle方法基类

#### 8.7 配置文件
- `cards_operation_mapping.json` - 无需修改，作为配置参考

### 9. 验证标准

- ✅ 新增卡片无需修改handler硬编码
- ✅ 业务层方法不依赖feishu_data
- ✅ 配置驱动的路由分发
- ✅ 标准化的信息收集和传递
- ✅ 属地集中的卡片管理

---
**创建时间**: 2025-06-26
**版本**: v1.0
**状态**: 待实施