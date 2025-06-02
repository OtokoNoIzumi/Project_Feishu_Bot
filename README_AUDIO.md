# 飞书机器人音频处理功能 (阶段2A MVP)

## 📋 功能概述

本版本实现了完整的音频处理功能，包括：
- 🎤 **TTS文本转语音** - 使用Coze API进行语音合成
- 🔄 **音频格式转换** - FFmpeg支持的多格式转换为opus
- 📁 **临时文件管理** - 自动创建和清理临时文件
- 🔗 **飞书音频上传** - 自动上传音频到飞书并发送

## 🏗️ 架构设计

### 四层架构
```
┌─────────────────────────────────────────────────┐
│                前端交互层                         │
│  FeishuAdapter - 飞书协议转换与音频上传处理       │
└─────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────┐
│                核心业务层                         │
│  MessageProcessor - TTS指令识别与异步处理        │
└─────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────┐
│                应用控制层                         │
│  AppController - 服务注册与统一调用管理          │
└─────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────┐
│                  服务层                          │
│  AudioService - TTS生成+格式转换+文件管理        │
│  ConfigService - 配置管理                       │
│  CacheService - 缓存管理                        │
└─────────────────────────────────────────────────┘
```

### 音频处理流程
```
用户输入 "配音 文本内容"
        ↓
FeishuAdapter 接收消息
        ↓
MessageProcessor 识别TTS指令
        ↓
发送 "正在生成配音..." 提示
        ↓
异步调用 AudioService.process_tts_request()
        ↓
CozeTTS.generate() 调用API获取音频
        ↓
create_temp_audio_file() 创建临时MP3
        ↓
convert_to_opus() FFmpeg转换格式
        ↓
upload_opus_to_feishu() 上传到飞书
        ↓
发送音频消息到用户
        ↓
cleanup_temp_file() 清理临时文件
```

## 🚀 快速开始

### 1. 环境要求
- Python 3.11+
- FFmpeg (用于音频转换)
- 飞书机器人应用凭证
- Coze API密钥

### 2. 配置文件

#### `.env` 环境变量
```env
# 飞书应用配置
FEISHU_APP_MESSAGE_ID=your_app_id
FEISHU_APP_MESSAGE_SECRET=your_app_secret

# Coze TTS配置
COZE_API_KEY=your_coze_api_key

# FFmpeg路径（可选，默认使用系统PATH）
FFMPEG_PATH=/path/to/ffmpeg

# 管理员ID（可选）
ADMIN_ID=your_user_open_id
```

#### `config.json` 静态配置
```json
{
  "bot_id": "7473130113548402722",
  "coze_bot_url": "https://api.coze.cn/v1/workflow/run",
  "voice_id": "peach",
  "log_level": "INFO"
}
```

### 3. 运行服务

#### 方式1：直接运行
```bash
python main_refactored_audio.py
```

#### 方式2：测试音频服务
```bash
python test_audio_service.py
```

### 4. 使用方法

在飞书中向机器人发送：
- `配音 你好，欢迎使用飞书机器人` - 生成语音
- `帮助` - 查看功能说明
- `你好` - 基础问候

## 📁 文件结构

```
Project_Feishu_Bot/
├── Module/
│   ├── Services/
│   │   ├── audio/
│   │   │   ├── __init__.py
│   │   │   └── audio_service.py      # 🎵 音频服务核心
│   │   ├── cache_service.py
│   │   ├── config_service.py
│   │   └── __init__.py               # 服务注册表
│   ├── Business/
│   │   └── message_processor.py     # TTS指令处理
│   ├── Adapters/
│   │   └── feishu_adapter.py        # 飞书音频上传
│   ├── Application/
│   │   └── app_controller.py        # 服务管理
│   └── Common/
├── main_refactored_audio.py         # 🚀 主启动文件
├── test_audio_service.py            # 🧪 测试脚本
├── config.json
├── .env
└── README_AUDIO.md
```

## 🔧 AudioService API

### 核心方法

#### `process_tts_request(text: str)`
完整的TTS处理流程
```python
success, audio_data, error_msg = audio_service.process_tts_request("测试文本")
```

#### `convert_to_opus(input_path: str)`
音频格式转换
```python
opus_path, duration_ms = audio_service.convert_to_opus("audio.mp3")
```

#### `create_temp_audio_file(audio_data: bytes)`
创建临时文件
```python
temp_path = audio_service.create_temp_audio_file(audio_data, ".mp3")
```

#### `cleanup_temp_file(file_path: str)`
清理临时文件
```python
audio_service.cleanup_temp_file(temp_path)
```

## 🎯 特性亮点

### 1. 🔧 **解耦设计**
- 音频服务完全独立，可单独测试和替换
- 支持不同TTS提供商的切换
- FFmpeg路径可配置，支持系统安装或自定义路径

### 2. 🚀 **异步处理**
- TTS生成不阻塞用户交互
- 先发送"处理中"提示，后发送音频结果
- 自动错误处理和用户反馈

### 3. 🛡️ **错误容错**
- 服务不可用时优雅降级
- 详细的错误日志和用户友好的错误信息
- 自动资源清理，防止临时文件泄露

### 4. 📊 **可观测性**
- 完整的服务状态监控
- 健康检查API
- 详细的调试日志

## ⚠️ 注意事项

1. **Conda环境限制**: AI无法在cursor shell中验证conda环境，需要用户手动在WorkSpace环境中测试

2. **依赖要求**:
   - 确保FFmpeg已安装并在PATH中，或配置FFMPEG_PATH
   - Coze API密钥必须有效且有TTS权限

3. **文件权限**: 确保应用有权限在项目目录创建临时文件

4. **网络要求**: TTS功能需要访问Coze API (api.coze.cn)

## 🔮 后续规划

- ✅ **阶段2A**: TTS语音合成 (当前版本)
- 📋 **阶段2B**: 音频转文字 (ASR)
- 📋 **阶段2C**: 音频格式转换增强
- 📋 **阶段3**: 图像处理服务集成
- 📋 **阶段4**: 完整多媒体处理平台

---

**架构优势**: 每个服务职责单一，易于测试和扩展，为后续多媒体功能奠定坚实基础。