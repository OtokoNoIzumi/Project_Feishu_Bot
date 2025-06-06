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

### 配置优先级
1. 环境变量 (.env)
2. 认证配置文件
3. 静态配置 (config.json)

### 主要配置项
- `FEISHU_APP_ID` - 飞书应用ID
- `FEISHU_APP_SECRET` - 飞书应用密钥
- `AUTH_CONFIG_FILE_PATH` - 认证配置文件路径
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

## �� 许可证

MIT License
