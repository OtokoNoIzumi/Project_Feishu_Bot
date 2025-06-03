# 飞书机器人API使用指南

## 📖 概述

本项目提供了完整的API接口，支持多种前端访问方式。无论是飞书机器人、Web应用、移动端还是第三方集成，都可以通过统一的API接口访问所有功能。

## 🏗️ 架构设计

### 当前架构
```
应用层: Web/Mobile/CLI/第三方
    ↓ (HTTP API 或 直接调用)
AppController (统一API接口)
    ↓ (服务调用)
Services (音频/图像/调度器/配置/缓存)
    ↓ (事件机制)
FeishuAdapter (飞书前端)
```

### 设计优势
- **解耦设计**: 飞书适配器只是前端之一，不是核心依赖
- **多前端支持**: 同一套API支持所有类型的前端
- **事件驱动**: 定时任务通过事件机制解耦
- **标准接口**: 所有API返回统一的JSON格式

## 🧪 API验证方法

### 方法1: 启动时验证 (推荐)
```bash
# 基础启动
python main_refactored_schedule.py

# 启动时验证API + HTTP服务器
python main_refactored_schedule.py --verify-api --http-api

# 自定义HTTP端口
python main_refactored_schedule.py --http-api --http-port 9000
```

### 方法2: 独立验证脚本
```bash
# 独立API验证（创建新的AppController实例）
python test_runtime_api.py

# 选择验证方式：
# 1. 一次性验证所有API
# 2. 交互模式验证
```

### 方法3: HTTP API验证
```bash
# 启动独立的HTTP API服务器
python http_api_server.py

# 自定义主机和端口
python http_api_server.py --host 0.0.0.0 --port 9000

# 访问API文档
# http://127.0.0.1:8000/docs
```

## 🌐 HTTP API接口

### 健康检查
```bash
GET http://127.0.0.1:8000/health
```

### 日程管理
```bash
# 获取日程数据
GET http://127.0.0.1:8000/api/schedule
```

### B站功能
```bash
# 触发B站更新
POST http://127.0.0.1:8000/api/bilibili/update
Content-Type: application/json

{
  "sources": ["favorites", "dynamic"]
}
```

### 音频功能
```bash
# TTS生成
POST http://127.0.0.1:8000/api/audio/tts
Content-Type: application/json

{
  "text": "这是测试文本"
}
```

### 图像功能
```bash
# AI图像生成
POST http://127.0.0.1:8000/api/image/generate
Content-Type: application/json

{
  "prompt": "一只可爱的小猫"
}

# 图像处理
POST http://127.0.0.1:8000/api/image/process
Content-Type: application/json

{
  "image_base64": "base64编码的图像数据",
  "mime_type": "image/jpeg",
  "file_name": "test.jpg"
}
```

### 定时任务管理
```bash
# 获取任务列表
GET http://127.0.0.1:8000/api/scheduler/tasks

# 添加任务
POST http://127.0.0.1:8000/api/scheduler/tasks
Content-Type: application/json

{
  "task_name": "test_task",
  "time_str": "14:30",
  "task_type": "daily_schedule"
}

# 删除任务
DELETE http://127.0.0.1:8000/api/scheduler/tasks/test_task
```

## 💻 编程接口调用

### Python调用示例
```python
from Module.Application.app_controller import AppController

# 创建控制器实例
app_controller = AppController()
app_controller.auto_register_services()

# 初始化图像服务
image_service = app_controller.get_service('image')
if image_service:
    image_service.initialize()

# 调用API
result = app_controller.api_get_schedule_data()
print(result)

result = app_controller.api_generate_tts("测试文本")
print(f"音频大小: {len(result['audio_data'])} 字节")

result = app_controller.api_generate_image("可爱小猫")
print(f"生成图片: {result['image_paths']}")
```

### JavaScript调用示例
```javascript
// 健康检查
fetch('http://127.0.0.1:8000/health')
  .then(response => response.json())
  .then(data => console.log(data));

// TTS生成
fetch('http://127.0.0.1:8000/api/audio/tts', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    text: '这是测试文本'
  })
})
.then(response => response.json())
.then(data => console.log(data));
```

## 🔄 运行时验证场景

### 场景1: 主程序运行时验证
1. 启动主程序: `python main_refactored_schedule.py --verify-api`
2. 系统会在启动时自动验证所有API
3. 验证通过后正常启动飞书机器人

### 场景2: 独立验证测试
1. 主程序正在运行 (飞书机器人服务)
2. 另开窗口运行: `python test_runtime_api.py`
3. 创建独立的AppController实例进行验证
4. 不影响主程序运行

### 场景3: HTTP API验证
1. 启动带HTTP API的主程序: `python main_refactored_schedule.py --http-api`
2. 通过浏览器访问: `http://127.0.0.1:8000/docs`
3. 在Swagger界面中测试所有API
4. 或使用curl/Postman等工具调用

## ❓ 关于FeishuAdapter的设计

### 当前设计 (推荐)
- **FeishuAdapter直接依赖AppController**:
  - ✅ 简单高效，减少中间层
  - ✅ 共享服务实例，避免重复初始化
  - ✅ 事件机制解耦，支持扩展其他前端
  - ✅ 飞书特定功能可以直接访问底层服务

### 替代设计 (通过API)
- **FeishuAdapter通过HTTP API访问**:
  - ❌ 增加网络开销和延迟
  - ❌ 需要序列化/反序列化复杂数据
  - ❌ 错误处理更复杂
  - ❌ 失去了类型安全
  - ✅ 完全解耦，但这种解耦在同一进程内意义不大

## 🎯 推荐使用方式

### 开发阶段
```bash
# 启动时验证API，确保所有功能正常
python main_refactored_schedule.py --verify-api
```

### 生产环境
```bash
# 同时启动飞书机器人和HTTP API
python main_refactored_schedule.py --http-api

# 这样可以支持:
# 1. 飞书用户通过机器人使用
# 2. Web应用通过HTTP API使用
# 3. 移动端通过HTTP API使用
# 4. 第三方系统集成
```

### 第三方集成
```bash
# 仅启动HTTP API服务器（不需要飞书机器人）
python http_api_server.py --host 0.0.0.0 --port 8000
```

## 📝 API响应格式

所有API都返回统一格式：
```json
{
  "success": true,
  "data": "实际数据",
  "error": "错误信息(仅在失败时)"
}
```

这种设计确保了：
- **一致性**: 所有前端都使用相同的接口
- **扩展性**: 易于添加新的前端类型
- **维护性**: 业务逻辑集中在AppController中
- **可测试性**: 每个组件都可以独立测试