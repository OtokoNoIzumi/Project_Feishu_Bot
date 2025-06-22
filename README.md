# 飞书机器人

一个功能完整的飞书机器人项目，基于四层架构设计，支持多媒体处理、定时任务、HTTP API等功能。

## 🏗️ 系统架构

```
前端交互层 (Adapters)
    ↓
核心业务层 (Business)
    ↓
应用控制层 (Application)
    ↓
服务层 (Services)
```

### 核心组件
- **FeishuAdapter**: 飞书平台交互和消息处理
- **MessageProcessor**: 业务逻辑路由和处理
- **AppController**: 统一服务管理和API接口
- **Services**: 功能服务（配置、缓存、音频、图像、定时任务、数据管理）

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
- **每日信息汇总**: 07:30 自动推送服务状态和B站数据分析
- **B站更新推送**: 15:30 和 23:55 自动检查和推送
- **夜间静默模式**: 23:00-07:00 只处理不通知
- **事件驱动架构**: 完全解耦的任务调度系统

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
1. 复制 `.env.example` 为 `.env`
2. 配置飞书机器人密钥：
   - `FEISHU_APP_ID` - 飞书应用ID
   - `FEISHU_APP_SECRET` - 飞书应用密钥
   - `ADMIN_ID` - 管理员用户ID
3. 配置服务集成：
   - `GRADIO_BASE_URL` - 图像生成服务地址
   - `COZE_API_KEY` - TTS服务密钥
   - `NOTION_*` - Notion数据库配置
4. 可选API配置：
   - `ADMIN_SECRET_KEY` - HTTP API管理密钥
   - `BILI_API_BASE` - B站外部API地址

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