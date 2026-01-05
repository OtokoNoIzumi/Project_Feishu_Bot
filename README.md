# 飞书机器人

一个功能完整的飞书机器人项目，基于模块化语义架构设计，支持多媒体处理、定时任务、HTTP API等功能。

可以阅读deepwiki页面【英文】查看项目情况
https://deepwiki.com/OtokoNoIzumi/Project_Feishu_Bot

## 🎯 项目总目标（Readme级）

本项目的长期目标是构建一个**完全的私人助理**，其核心交互原则为：

- **自然语言为主输入**：用户主要通过自然语言提出记录/规划/决策问题（而非传统点选式产品流程）。
- **推测执行 + 后确认（Post-Confirmation）**：系统在收到输入后优先给出完整结果与建议；如涉及 AI 识别/推断字段，必须提供**后置校准与确认**入口（飞书卡片/表单/网页均可）。
- **禁止前置澄清依赖**：面对用户不可控的模糊输入（如“燕麦牛奶”），系统应采用**可解释的默认假设**直接执行，并在结果中标注假设；用户通过卡片修改后触发重算/重生成，而不是先让用户做一堆选择。
- **尽量减少无效 LLM 调用**：
  - 可确定的触发与流程（如飞书 POST 标题“饮食”）走确定性路径，避免额外“路由一次再处理一次”。
  - 对开放式任务，优先采用 **Tools Calling/工具编排**：由一次助手请求选择工具并完成流程，避免多轮冗余调用。

## 🏗️ 系统架构

采用**语义化节点**的模块化架构，经过大幅重构优化，实现了更清晰的前后端分离和业务层次：

### 🎯 新架构层级

#### 1️⃣ **前端/Adapter层** (`Module/Adapters/`)
**纯粹的协议转换和平台接口封装**
- **`FeishuAdapter`**: 飞书平台适配器，处理WebSocket连接、消息接收发送和格式转换
- **handlers**: 事件处理器集合（消息、卡片、菜单）
- **senders**: 消息发送器，负责与飞书API交互
- **cards**: 卡片管理器，处理飞书卡片的构建和交互
- **职责**: 协议转换、输入验证、格式适配，终端操作点，不包含任何业务逻辑，但可以访问和调用所有能力

#### 2️⃣ **Router层** (`Module/Business/`)
**业务路由和逻辑处理，对应一部分原来的message_processor**
- **`MessageRouter`**: 业务层统一入口，负责消息路由和业务逻辑协调
- **processors**: 专门的业务处理器模块——后续会合并到service里，这里只保留router的逻辑
  - **`TextProcessor`**: 文本消息处理 (`get_help`, `greeting`, `default_reply`)
  - **`MediaProcessor`**: 多媒体处理 (`process_tts_async`, `sample_rich_text`, `sample_image`)
  - **`BilibiliProcessor`**: B站功能 (`video_menu`, `process_bili_video_async`)
  - **`AdminProcessor`**: 管理功能 (`handle_admin_command`, `handle_pending_operation_action`)
  - **`ScheduleProcessor`**: 定时任务 (`create_task`, `daily_summary`, `bili_notification`)
- **职责**: 消息路由、业务逻辑处理、流程控制

#### 3️⃣ **Service层** (`Module/Services/`)
**功能服务实现，整合了原来的processor子模块和service**
- **router**: 智能路由服务
  - **`RouterService`**: AI驱动的消息路由，支持快捷指令和意图识别
  - **`CardBuilder`**: 卡片构建服务，统一卡片模板管理
- **核心服务**: 通过`ServiceNames`常量化访问
  - **Config**: 配置管理，支持.env和config.json优先级
  - **Cache/PendingCache**: 缓存管理和待处理操作管理
  - **Audio/Image**: 多媒体处理服务
  - **Notion**: 数据源集成和B站数据管理
  - **LLM**: 大语言模型服务集成
- **职责**: 具体功能实现、数据处理、服务提供

#### 4️⃣ **Pending & Schedule层** (自动化)
**自动化处理层，实现异步操作和定时任务的完全自动化**
- **`PendingCacheService`**: 待处理操作自动管理
  - 支持倒计时和自动执行
  - UI更新推送机制
  - 操作状态跟踪和过期清理
- **`SchedulerService`**: 完全解耦的定时任务服务
  - 事件驱动架构，通过事件机制通知其他组件
  - 支持每日任务和间隔任务
  - 独立于前端实现的调度机制
- **职责**: 定时任务、异步操作、状态管理，完全自动化运行

#### 5️⃣ **Application层** (`Module/Application/`)
**应用控制和服务协调**
- **`AppController`**: 服务注册、统一调用、健康监控、adapter管理
- **`AppApiController`**: HTTP API控制器，RESTful接口实现
- **职责**: 服务编排、API管理、系统监控、生命周期管理

### 🔄 **架构优势**

#### **前后端完全分离**
- 前端Adapter层专注协议转换，不包含业务逻辑
- Router层处理业务路由，Service层提供功能实现
- 自动化层独立运行，减少手动干预

#### **业务逻辑清晰化**
- 消息路由与具体处理分离
- 每个处理器职责单一，易于维护和扩展
- 智能路由支持AI驱动的意图识别

#### **服务化架构**
- 所有功能模块化为独立服务
- 统一的服务注册和调用机制
- 服务间解耦，支持独立测试和部署

#### **自动化程度高**
- 待处理操作自动管理和执行
- 定时任务自动调度和监控
- UI状态自动更新和同步

## ✨ 主要功能

### 📱 基础交互
- 文本对话处理和指令路由
- 菜单点击响应和卡片交互
- 富文本卡片支持和状态管理
- 异步任务处理和错误恢复

### 🎨 多媒体处理
- **AI图像生成**: 基于文本描述生成图像
- **图像风格转换**: 上传图片自动转换为贺卡风格
- **TTS语音合成**: 文本转高质量中文语音（Coze API）
- **音频格式转换**: FFmpeg自动适配飞书音频格式

### 📺 B站推荐系统
- **1+3推荐模式**: 1个主推荐 + 3个额外推荐
- **智能已读管理**: 避免重复推荐
- **多维度统计分析**: 优先级、时长、来源、作者等
- **API集成**: 支持外部B站API数据更新

### ⏰ 定时任务系统
- **配置化管理**: 基于config.json的任务配置，支持启用/禁用
- **调试模式**: `force_latest_time`开关，自动调整任务时间为启动时间+5秒
- **任务类型**: 支持`daily_schedule`（每日汇总）和`bilibili_updates`（B站更新）
- **灵活参数**: 每个任务可配置独立的参数（如B站数据源）
- **统一处理**: `schedule.create_task()`封装所有路由逻辑

### 🌐 HTTP API接口
- **RESTful API**: 完整的HTTP接口支持
- **安全鉴权**: IP白名单 + 密钥双重验证
- **Swagger文档**: 自动生成API文档 `/docs`
- **独立部署**: 可与主服务共享或独立运行

### 🔐 认证与管理
- **动态配置更新**: 无需重启的认证参数更新
- **管理员功能**: 用户状态管理、配置更新、广告信息维护
- **状态监控**: 实时查询所有服务健康状态
- **操作确认**: 管理员操作的安全确认机制

## 🚀 快速开始

### 环境要求
- Python 3.11+
- Anaconda虚拟环境（推荐WorkSpace环境）
- 飞书机器人应用配置

### 安装依赖
```bash
pip install -r requirements.txt
```

### 配置设置
1. **环境变量配置** (`.env`)：
   - `FEISHU_APP_ID` / `FEISHU_APP_SECRET` - 飞书机器人密钥
   - `ADMIN_ID` - 管理员用户ID（必需）
   - `GRADIO_BASE_URL` / `COZE_API_KEY` - 多媒体服务集成
   - `NOTION_*` - 数据源配置
   - `ADMIN_SECRET_KEY` - HTTP API管理密钥

2. **应用配置** (`config.json`)：
   - `scheduler.tasks[]` - 定时任务配置数组
   - `pending_cache` - 操作超时和缓存配置
   - `cards` - 卡片模板和回复模式配置

3. **业务配置** (`cards_business_mapping.json`)：
   - 卡片与业务的映射关系
   - 支持热更新和插拔式配置

### 启动服务

#### Windows一键启动
```bash
start.bat
```

#### 命令行启动
```bash
# 标准启动（飞书机器人）
python main.py

# 带API验证启动
python main.py --verify-api

# 启动HTTP API服务器
python main.py --http-api --http-port 8000

# 完整功能启动
python main.py --verify-api --http-api
```

#### Jupyter环境（开发调试）
```python
# 在WorkSpace虚拟环境中
await main_async()
```

## 📝 使用说明

### 基础指令
- `帮助` - 查看完整功能列表
- `配音 文本内容` - TTS语音合成
- `生图 描述` - AI图像生成
- `富文本` - 富文本格式演示
- 发送图片 - 自动图像风格转换

### B站功能
- `B站` 或 `视频` - 获取视频推荐
- 菜单点击"B站" - 获取1+3模式推荐
- 卡片按钮操作 - 标记已读、获取更多

### 管理员功能（需管理员权限）
- `whisk令牌 cookies 新值` - 更新认证配置
- `更新用户 用户ID 类型` - 用户状态管理
- `更新广告 BVID 时间戳` - B站广告信息更新

## 🔧 配置说明

### 配置架构
- **认证配置**: 通过Gradio服务原生API处理（无需本地文件）
- **应用配置优先级**: 环境变量(.env) > 静态配置(config.json) > 服务默认值
- **卡片配置**: 业务卡片映射配置(cards_business_mapping.json)

### 重要配置项
- **飞书配置**: APP_ID、APP_SECRET、ADMIN_ID
- **服务集成**: GRADIO_BASE_URL、COZE_API_KEY、BOT_ID
- **数据源**: Notion数据库配置、B站API配置
- **安全设置**: ADMIN_SECRET_KEY、BILI_NIGHT_SILENT

## 🛠️ 开发指南

### 项目结构
```
Project_Feishu_Bot/
├── Module/                              # 🏗️ 核心模块目录
│   ├── Adapters/                        # 适配器层（飞书平台交互）
│   ├── Business/                        # 业务逻辑层（消息处理）
│   ├── Application/                     # 应用控制层（服务管理）
│   ├── Services/                        # 服务层（功能实现）
│   └── Common/                          # 公共工具和脚本
├── config.json                          # ⚙️ 静态配置文件
├── cards_business_mapping.json          # 🃏 卡片业务映射配置
├── README.md                            # 📖 项目说明文档
├── TECHNICAL_ARCHITECTURE_REFERENCE.md  # 📚 技术架构参考文档
├── CHANGELOG.md                         # 📋 项目变更日志
└── DEVELOPMENT_TIL.md                   # 💡 开发者今日学习
```

### 文档说明
- **README.md**: 项目概览、快速开始和使用指南
- **TECHNICAL_ARCHITECTURE_REFERENCE.md**: 详细的技术架构设计和实施方案
- **CHANGELOG.md**: 版本变更记录和项目发展历程
- **DEVELOPMENT_TIL.md**: 开发过程中的每日学习和技术发现

### 添加新功能
1. 在 `Services/` 下实现新服务，必须实现 `get_status()` 方法
2. 在对应 `Processor` 中添加业务逻辑
3. 通过 `AppController` 注册服务
4. 可选：添加HTTP API接口

### 开发规范

#### 🔤 重要变量命名规范
- **`context`** (MessageContext): 标准化消息上下文对象，包含用户信息、消息内容、时间戳等核心字段
- **`result_content`**: 业务处理器返回的结果数据，传递给卡片构建器的原始数据
- **`business_data`**: 从用户输入解析出的纯业务数据，如{user_id, user_type, admin_input}
- **`operation_type`**: 业务操作类型标识符，如"update_user"、"update_ads"，**禁止重复存储**
- **`card_operation_type`**: 卡片操作类型，枚举值：SEND/UPDATE_RESPONSE，决定卡片行为
- **`response_type`**: 处理结果的响应类型，如"admin_card_send"、"bili_card_update"

#### 🏗️ 架构层级约束
- **应用容器层** (Application): AppController管理和协调所有组件生命周期
- **三层处理架构**: 适配器层→业务逻辑层→服务层
- **实际调用链**: FeishuAdapter(MessageHandler) → MessageProcessor → AdminProcessor → AppController.get_service(ServiceName)
- **容器职责**: Application层负责服务注册、依赖注入、统一调用接口
- **处理链约束**: 适配器层调用业务层，业务层通过容器层访问服务层
- **配置驱动**: 卡片与业务通过配置文件桥接，避免硬编码依赖

#### 🚨 关键开发原则
- **理解优先**: 充分理解现有逻辑后再修改，不能为了解决一个问题而引入新问题
- **返回值一致性**: SEND操作返回(bool, str)元组，UPDATE操作返回响应对象
- **概念重复消除**: 禁止同一概念在多个变量中重复存储
- **配置路径规范**: 所有配置文件路径基于项目根目录，不依赖工作目录
- **避免试错**: 验证失败时停止尝试，等待用户指导，而不是继续试错

#### 飞书卡片规范

**卡片标识与关联：**
- 每个 card_id 需通过 service 层与 message_id 关联，message_id 由 sender 生成并传递。

**核心术语定义：**
- **business_info**：卡片生成前的业务信息载体。
- **card_param**：模板变量（template_variable），用于渲染卡片内容。
- **card_data**：可直接构成卡片数据的部分，即 data 字段。
- **card_info**：用于管理 message 与 sequence 映射关系的辅助结构。
- **card_content**：包含 type 和 data，可直接用于发送的完整卡片内容。

**常见问题与注意事项：**
1. **P2CardActionTriggerResponse 刷新机制**
   刷新操作属于弱兼容但强校验场景，所有刷新失败基本都是语法错误导致的；而卡片发送时的校验则相对宽松，未必会报错。
2. **卡片失效的通用防护**
   在所有交互组件的操作前，可通过 default_data 对未交互的卡片进行简化重构，提升健壮性。
   - 若需重新生成，则直接调用 build 方法，无需定义 element。
   - 若无需重新生成卡片，或生成需要缓存的数据较多，可采用“非全量更新”方式，仅更新 element，这部分在card_handle里要用0.3秒的异步避免和卡片回调冲突

## 🗓️ 开发计划

### 近期优化
1. **B站功能增强**
   - 支持按时间筛选和批量操作
   - 增加全部已读、随机推荐功能
   - LLM驱动的智能路由和参数重现

2. **交互体验提升**
   - 语音输入识别和TTS播报联动
   - 消息回复和评论识别优化
   - 上下文切换按钮和自动检测

3. **系统整合扩展**
   - 链接读取和文档处理功能
   - 外卖决策和时间记录模块
   - 天气信息和穿衣建议集成

### 技术架构
- **路由泛化**: 使用LLM驱动的通用功能调用
- **卡片系统**: 统一的模板管理和交互组件
- **数据管理**: 可撤销缓存和Notion集成优化
- **MCP标准**: 多通道平台集成方案

## 许可证

MIT License