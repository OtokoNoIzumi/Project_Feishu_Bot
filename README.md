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
- **FeishuAdapter**: 飞书平台交互
- **MessageProcessor**: 业务逻辑处理
- **AppController**: 服务管理
- **Services**: 功能服务（配置、缓存、音频、图像、定时任务、数据）

## ✨ 主要功能

### 📱 基础交互
- 文本对话处理
- 菜单点击响应
- 卡片交互支持
- 异步任务处理

### 🎨 多媒体处理
- **AI图像生成**: 基于文本描述生成图像
- **图像风格转换**: 上传图片转换为贺卡风格
- **TTS语音合成**: 文本转高质量中文语音
- **音频格式转换**: 自动适配飞书音频格式

### 📺 B站推荐系统
- **1+3推荐模式**: 1个主推荐 + 3个额外推荐
- **已读状态管理**: 避免重复推荐
- **智能统计分析**: 多维度数据统计
- **数据可视化**: 飞书图表展示

### ⏰ 定时任务
- **每日日程提醒**: 07:30 信息汇总
- **B站更新推送**: 15:30 和 23:55 自动处理
- **夜间静默模式**: 22:00-08:00 只处理不通知
- **事件驱动架构**: 解耦的任务系统

### 🌐 HTTP API
- RESTful API接口
- 安全鉴权机制
- Swagger文档
- 完整的功能API

### 🔐 认证配置
- **无需本地配置文件**: 认证配置完全通过Gradio服务原生API处理
- **动态配置更新**: 支持实时更新认证参数
- **状态监控**: 实时查询认证服务状态

## 🚀 快速开始

### 环境要求
- Python 3.11+
- Anaconda环境
- 飞书机器人配置

### 安装依赖
```bash
pip install -r requirements.txt
```

### 配置设置
1. 复制 `.env.example` 为 `.env`
2. 配置飞书机器人密钥
3. 设置其他服务配置

### 启动服务

#### Windows
```bash
start.bat
```

#### 命令行
```bash
# 标准启动
python main.py

# 带API验证
python main.py --verify-api

# 启动HTTP API服务器
python main.py --http-api --http-port 8000

# 完整功能启动
python main.py --verify-api --http-api
```

#### Jupyter环境
```python
await main_async()
```

## 📝 使用说明

### 基础指令
- `帮助` - 查看功能列表
- `配音 文本内容` - TTS语音合成
- `生图 描述` - AI图像生成
- 发送图片 - 图像风格转换

### B站功能
- `B站推荐` - 获取视频推荐
- `B站统计` - 查看数据统计
- 卡片按钮 - 标记已读、获取更多

## 🔧 配置说明

### 配置架构
**认证配置**: 通过Gradio服务原生API处理（无需本地配置文件）
- 认证状态查询: `image_service.get_auth_status()`
- 认证配置更新: `image_service.update_auth_config()`

**应用配置优先级**:
1. 环境变量 (.env)
2. 静态配置 (config.json)

### 主要配置项
- `FEISHU_APP_ID` - 飞书应用ID
- `FEISHU_APP_SECRET` - 飞书应用密钥
- `GRADIO_BASE_URL` - Gradio服务地址
- `COZE_BOT_URL` - Coze机器人API地址
- 其他服务配置

## 📚 API文档

启动HTTP API服务器后，访问：
- API文档: `http://localhost:8000/docs`
- 健康检查: `http://localhost:8000/health`

## 🛠️ 开发指南

### 项目结构
```
Module/
├── Application/    # 应用控制层
├── Business/       # 业务逻辑层
├── Adapters/       # 适配器层
├── Services/       # 服务层
└── Common/         # 公共工具
```

### 添加新功能
1. 在 `Services/` 下实现新服务
2. 服务必须实现 `get_status()` 方法
3. 在 `MessageProcessor` 中添加业务逻辑
4. 通过 `AppController` 注册服务

### 开发规范
- 充分理解现有逻辑后再修改
- 统一使用 `debug_utils` 记录日志
- 优雅处理异常，提供友好错误信息
- 配置文件路径基于项目根目录

## 许可证

MIT License

## 🗓️ 后续开发计划与想法

1. **B站工具功能迁移与增强**
   - 已将原B站工具的所有功能迁移，包括按时间筛选、获取某时间段最后一个阅读清单等。
   - 支持在B站视频清单中批量去除特定内容（如炉石）。
   - 和bili后端配合增加一个日报，以及清理提示词的定时API-bili后端的up主数据分析可以稍微沉淀一点点了，另外的一个搜索，则是要和来源清单一起进入配置，才可以方便拓展和删改-而且看起来最好也有API来维护
   - 计划列出所有能力清单，并探索用LLM驱动的rooter泛化调用已有功能，而不是为每个用例单独开发——包括用卡片把参数重现出来的功能，这个二次输入确认是确保AI辅助编辑的一个重要界面，需要支持API，而不是绑定在飞书上。

2. **飞书机器人智能交互优化**
   - 飞书原生支持语音输入，后续考虑结合TTS实现语音播报与处理。
   - 测试飞书机器人对评论和回复的识别能力，提升消息处理的智能性。
   - 优化AI聊天窗口的上下文切换逻辑，增加按钮切换是否使用上下文，自动检测是否需要纳入前一条消息，避免遗漏。

3. **定时任务与提醒系统**
   - 将定时任务配置化，便于灵活调整。
   - 早间提醒整合更多信息，如服务器可用状态、服务健康检查等，天气模块？用api请求天气并对比温差，然后给出穿衣参考和注意事项？

4. **系统整合与自动化**
   - 邮件系统计划用MCP（多通道平台）方案整合，不再自研。
   - 外卖决策尝试用收藏夹+数据库方式替代传统定位和决策流程。

记录时间差的这个独立模块和逻辑-还要支持API，比如上次洗澡的时间之类，但要稍微构建一下，输入按钮不太够的

外部数据源看起来是不太行，打不通。
先从日常开始吧，天气，日程，rooter？还有B站功能迁移

B站按钮后续增加一个全部已读，以及随机抽取，+选择范围，默认是10分钟？

用类似MCP的规范来做router吗？这样可能会好一点

飞书机器人业务api化——飞书只是前端，不要实现逻辑

数字分身天然就要包括多个自己，除了主体之外还有其他几个预设槽位


I am a creative and strategic leader with a passion for crafting immersive game experiences. As a game designer and CEO, I have honed my skills in project management, team leadership, and communication while directing the strategic vision of an AI consulting organization. My experience in narrative design and player engagement analysis allows me to create compelling storylines that resonate with players. Driven by a desire for continuous learning and a deep interest in education and self-development, I am constantly seeking new ways to innovate and improve the player experience. I leverage my expertise in Python and strategic planning to guide development teams and cultivate strong client relationships, ensuring that every project is a success.

不是高频的业务不需要用数据库，反倒是Notion访问性和编辑性都不错，现在也有加载缓存的方法了

所谓可撤销的缓存业务=没有真实提交，但是查询的时候又可以和正式数据合并在一起，这样一来一般也就缓存1-2份数据，这样还要不要有一个定时，也是有必要的，因为没必要一直缓存，可以用一个半小时的循环来检查是不是有超过半小时的缓存，超过的就写入了。
用户也可以根据下面的跟随气泡快速修改发证机关。点击和打字编辑效果一致——意味着需要开启上下文模式，但这个最好可以用消息评论的串，减少管理的复杂度——或者至少要验证一下消息的id和回复消息的逻辑

对于酒馆战棋这种版本的逻辑，为了呼应思考，至少可以有一个非全局的领域开关，只在这里更新——也就是默认全局不读取，需要主动引用，或者被概率抽到。
但是对于文档的部分，我可能需要一个可视化的地方，飞书文档应该就是另一个比较好的储存和编辑位置？需要一个结构来储存。

TTS的识别也是要先查看消息结构，是不是包括文字，但这里需要保留的是原始信息，方便回听，这就是闪念胶囊了。