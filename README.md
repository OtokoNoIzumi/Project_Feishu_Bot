# 飞书机器人

一个功能完整的飞书机器人项目，基于模块化语义架构设计，支持多媒体处理、定时任务、HTTP API等功能。

## 🏗️ 系统架构

采用**语义化节点**的模块化架构，主要模块节点：

### 🎯 主模块节点
- **`main`**: 应用入口，负责启动流程和定时任务配置化管理
- **`app_controller`**: 服务协调器，统一管理所有服务生命周期和健康状态
- **`feishu_adapter`**: 飞书平台适配器，处理消息接收、发送和格式转换

### 🧩 业务处理节点
**MessageProcessor**暴露的语义化处理节点：
- **`message_processor.text`**: 文本处理 (`get_help`, `greeting`, `default_reply`)
- **`message_processor.media`**: 多媒体处理 (`process_tts_async`, `sample_rich_text`, `sample_image`)
- **`message_processor.bili`**: B站功能 (`video_menu`, `process_bili_video_async`)
- **`message_processor.admin`**: 管理功能 (`handle_admin_command`, `handle_pending_operation_action`)
- **`message_processor.schedule`**: 定时任务 (`create_task`, `daily_summary`, `bili_notification`)

### 🔧 服务支撑层
通过`ServiceNames`常量化访问：
- **Config**: 配置管理，支持.env和config.json优先级
- **Cache/PendingCache**: 缓存管理和待处理操作管理
- **Audio/Image**: 多媒体处理服务
- **Scheduler**: 配置化定时任务服务
- **Notion**: 数据源集成

### 🃏 卡片架构设计

项目采用**配置化关联**的卡片架构，实现业务与卡片的彻底解耦：

#### 核心理念
- **卡片定位**: 卡片是飞书Adapter的附属特性，本质是消息的接收、标准格式化、展示和传递容器
- **业务解耦**: 业务层与卡片层通过配置文件桥接，避免硬编码依赖
- **依赖方向**: 卡片可以向下调用业务层，但业务层不能依赖卡片

#### 3个独立卡片业务
1. **用户更新确认卡片** (`admin_user_update_confirm`)
   - 管理员用户状态管理的确认界面
   - 支持用户类型选择和操作确认

2. **广告更新确认卡片** (`admin_ads_update_confirm`)
   - B站广告时间戳编辑的确认界面
   - 支持时间戳编辑器和操作确认

3. **B站视频菜单卡片** (`bili_video_menu`)
   - B站视频推荐的交互界面
   - 支持1+3推荐模式和已读管理

#### 配置化关联机制
```json
// cards_business_mapping.json - 业务卡片映射配置
{
  "business_mappings": {
    "update_user": {
      "response_type": "admin_card_send",
      "card_template": "admin_user_update_confirm",
      "timeout_seconds": 30,
      "actions": ["confirm_user_update", "cancel_user_update"]
    },
    "update_ads": {
      "response_type": "admin_ads_send",
      "card_template": "admin_ads_update_confirm",
      "timeout_seconds": 45,
      "actions": ["confirm_ads_update", "cancel_ads_update"]
    }
  }
}
```

#### 快速插拔支持
- **新增卡片**: 仅需在配置文件中添加映射关系，无需修改业务代码
- **模板热更新**: 卡片模板和配置支持重启加载
- **最小入侵**: 新卡片插拔对现有业务零影响

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
- **理解优先**: 充分理解现有逻辑后再修改
- **统一日志**: 正式功能使用 `debug_utils` 记录所有日志，开发阶段的功能需要给日志一些方便搜索定位的特殊标记，比如'test-',或者"⚠️⚠️⚠️"，在验收完成后把测试日志和新日志里的标记移除
- **优雅异常**: 提供友好的错误信息和降级方案
- **路径规范**: 所有配置文件路径基于项目根目录
- **避免试错**: 验证失败时停止尝试，等待用户指导

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

## 一些备忘

检查富文本的消息？—message_type为post，感觉可以先不去解析
2025-06-22 15:46:32,661 DEBUG { 'challenge': None,
  'event': { 'message': { 'chat_id': 'oc_00da7eba51fbc1fdcf5cf40ab332bf7e',
                          'chat_type': 'p2p',
                          'content': '{"title":"写个小作文","content":[[{"tag":"text","text":"重新刷新prompt","style":[]}],[{"tag":"img","image_key":"img_v3_02ng_f530c621-511e-4155-885f-84327da9255g","width":850,"height":1188}]]}',
                          'create_time': '1750578393311',
                          'mentions': None,
                          'message_id': 'om_x100b4a4f035f60b80f37721ad0ea286',
                          'message_type': 'post',
                          'parent_id': None,
                          'root_id': None,
                          'thread_id': None,
                          'update_time': '1750578393311',
                          'user_agent': None},
             'sender': { 'sender_id': { 'open_id': 'ou_08158e2f511912a18063fc6072ce42da',
                                        'union_id': 'on_f30d6f403ec60cad71c6c9c1e1da1ce0',
                                        'user_id': None},
                         'sender_type': 'user',
                         'tenant_key': '101c4da96edf975e'}},
  'header': { 'app_id': 'cli_a6bf8e1105de900b',
              'create_time': '1750578393583',
              'event_id': 'e076931bdbe7eda2f26c0bafe475c7c7',
              'event_type': 'im.message.receive_v1',
              'tenant_key': '101c4da96edf975e',
              'token': ''},
  'schema': '2.0',
  'token': None,
  'ts': None,
  'type': None,
  'uuid': None}

pin和置顶没消息

任务是一个消息，点击完成任务不是消息
2025-06-22 15:53:30,857 DEBUG 🔍 P2ImMessageReceiveV1对象详细信息 (pprint):
2025-06-22 15:53:30,857 DEBUG { 'challenge': None,
  'event': { 'message': { 'chat_id': 'oc_00da7eba51fbc1fdcf5cf40ab332bf7e',
                          'chat_type': 'p2p',
                          'content': '{"task_id":"96dba4b6-1fe7-4ce4-abd5-fbdf7344671a","summary":{"title":"","content":[[{"tag":"text","text":"增加卡片导入","style":[]}]]},"due_time":"1750550400000"}',
                          'create_time': '1750578811485',
                          'mentions': None,
                          'message_id': 'om_x100b4a4f29785fe40f38a30d3d08f8e',
                          'message_type': 'todo',
                          'parent_id': None,
                          'root_id': None,
                          'thread_id': None,
                          'update_time': '1750578811485',
                          'user_agent': None},
             'sender': { 'sender_id': { 'open_id': 'ou_08158e2f511912a18063fc6072ce42da',
                                        'union_id': 'on_f30d6f403ec60cad71c6c9c1e1da1ce0',
                                        'user_id': None},
                         'sender_type': 'user',
                         'tenant_key': '101c4da96edf975e'}},
  'header': { 'app_id': 'cli_a6bf8e1105de900b',
              'create_time': '1750578811799',
              'event_id': 'bb8c2ecdde189373ecb4d0d04c97fbbc',
              'event_type': 'im.message.receive_v1',
              'tenant_key': '101c4da96edf975e',
              'token': ''},
  'schema': '2.0',
  'token': None,
  'ts': None,
  'type': None,
  'uuid': None}
2025-06-22 15:53:30,857 DEBUG   - 关键信息: 此消息非回复消息 (parent_id is None or empty)