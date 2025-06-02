# 飞书机器人项目重构计划

## 重构目标
1. 简化架构，减少无用抽象层
2. 业务逻辑与前端解耦，API服务化
3. 支持多前端扩展的应用层设计
4. 消除防御性设计，追求内部100%可用

## 新架构设计

### 三层架构

```
┌─────────────────────────────────────────────────────────────┐
│                    前端适配器层 (Adapters)                     │
├─────────────────────────────────────────────────────────────┤
│  FeishuAdapter  │  WebAdapter   │  CliAdapter  │ ...        │
│  (飞书前端)     │  (Web前端)    │  (CLI前端)   │            │
└─────────────────────────────────────────────────────────────┘
                             │
                    统一的指令接口
                             │
┌─────────────────────────────────────────────────────────────┐
│                    业务应用层 (Application)                   │
├─────────────────────────────────────────────────────────────┤
│          AppController (主控制器)                            │
│          CommandDispatcher (指令分发器)                      │
│          BusinessWorkflows (业务流程编排)                    │
└─────────────────────────────────────────────────────────────┘
                             │
                    调用API服务
                             │
┌─────────────────────────────────────────────────────────────┐
│                     API服务层 (Services)                     │
├─────────────────────────────────────────────────────────────┤
│ MediaService │ NotionService │ BilibiliService │ ConfigService│
│ (媒体处理)   │ (Notion集成)  │ (B站功能)       │ (配置管理)    │
│              │               │                 │              │
│ ScheduleService │ TtsService │ ImageService   │ CacheService │
│ (日程管理)      │ (语音合成)  │ (图像处理)     │ (缓存管理)    │
└─────────────────────────────────────────────────────────────┘
```

## 目录结构重构

### 重构前
```
Module/
├── Core/           # 核心服务（混乱）
├── Interface/      # 抽象接口（过度抽象）
├── Platforms/      # 平台实现（职责不清）
└── Common/         # 公共库（保持不变）
```

### 重构后
```
Module/
├── Services/       # API服务层 - 独立的业务服务
│   ├── media/
│   ├── notion/
│   ├── bilibili/
│   ├── schedule/
│   ├── config/
│   └── cache/
├── Application/    # 业务应用层 - 业务流程编排
│   ├── controllers/
│   ├── dispatchers/
│   └── workflows/
├── Adapters/       # 前端适配器层 - 前端特定实现
│   ├── feishu/
│   ├── web/
│   └── cli/
└── Common/         # 公共库（保持不变）
```

## 核心组件重新设计

### 1. 指令系统
```python
class Command:
    """统一的指令对象"""
    def __init__(self, action: str, params: dict, context: dict):
        self.action = action      # 指令动作，如 "get_notion_data"
        self.params = params      # 指令参数
        self.context = context    # 上下文信息（用户ID、会话ID等）

class CommandResult:
    """统一的指令结果"""
    def __init__(self, success: bool, data: any = None, error: str = None):
        self.success = success
        self.data = data
        self.error = error
```

### 2. 应用控制器
```python
class AppController:
    """主应用控制器"""
    def __init__(self):
        self.services = {}      # 注册的API服务
        self.adapters = {}      # 注册的前端适配器
        self.dispatcher = CommandDispatcher()

    def register_service(self, name: str, service: any):
        """注册API服务"""

    def register_adapter(self, name: str, adapter: any):
        """注册前端适配器"""

    def execute_command(self, command: Command) -> CommandResult:
        """执行指令"""
```

### 3. 前端适配器接口
```python
class Adapter:
    """前端适配器基类"""
    def __init__(self, app_controller: AppController):
        self.app = app_controller

    def start(self):
        """启动前端服务"""

    def stop(self):
        """停止前端服务"""

    def handle_user_input(self, user_input: any) -> Command:
        """将前端用户输入转换为统一指令"""

    def handle_command_result(self, result: CommandResult, context: dict):
        """将指令结果转换为前端输出"""
```

## 重构步骤

### 第一阶段：创建新架构框架
1. 创建Services、Application、Adapters目录结构
2. 实现Command、CommandResult等核心类
3. 实现AppController和CommandDispatcher
4. 创建Adapter基类

### 第二阶段：服务拆分和迁移
1. 将BotService中的功能拆分到独立的API服务
2. 重构各个服务，去除平台依赖
3. 实现服务间的直接调用关系

### 第三阶段：前端适配器实现
1. 实现FeishuAdapter，迁移飞书相关代码
2. 去除Platform抽象层
3. 简化消息处理流程

### 第四阶段：主入口重构
1. 重构main_new.py，使用新的AppController
2. 清理旧的抽象层代码
3. 更新配置和启动逻辑

## 具体实现原则

1. **服务独立性**：每个API服务可以独立运行和测试
2. **直接调用**：内部服务间直接调用，不通过接口抽象
3. **简单配置**：统一的配置管理，避免多层配置传递
4. **错误透明**：错误直接抛出，不做多层包装
5. **同步优先**：优先使用同步接口，异步需求用适配器包装

## 预期收益

1. **代码简化**：减少50%以上的抽象层代码
2. **易于理解**：清晰的三层架构，职责明确
3. **易于扩展**：新增前端只需实现Adapter
4. **易于测试**：每个服务可独立测试
5. **性能提升**：减少不必要的对象创建和方法调用