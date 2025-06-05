# 飞书机器人重构版 - 技术参考文档

## 📋 项目状态

**当前版本：v3.0 重构完成版 ✅**
**清理状态：✅ 项目清理完成，仅保留生产环境必需文件**
**架构状态：✅ 四层架构完全实现，所有功能验证通过**

---

## 📁 当前项目架构

```
Project_Feishu_Bot/
├── main_refactored.py                    # 🚀 主启动文件
├── http_api_server.py                    # 🌐 HTTP API服务器
├── test_runtime_api.py                   # 🧪 API验证工具
├── start.bat                             # 🔧 Windows启动脚本
├── config.json                           # ⚙️ 静态配置文件
├── requirements.txt                      # 📦 依赖包清单
├── README.md                             # 📖 项目说明文档
├── REFACTOR_TECHNICAL_REFERENCE.md       # 📚 技术参考文档
├── cache/                                # 💾 运行时缓存目录
├── notebooks/                            # 📓 开发环境
│   └── Feishu_Bot.ipynb                  # Jupyter开发环境
└── Module/                               # 🏗️ 核心模块目录
    ├── Application/                      # 应用控制层
    │   ├── app_controller.py             # 应用控制器
    │   └── command.py                    # 命令模式实现
    ├── Business/                         # 业务逻辑层
    │   └── message_processor.py          # 消息处理器
    ├── Adapters/                         # 适配器层
    │   ├── feishu_adapter.py             # 飞书平台适配器
    │   └── base.py                       # 适配器基类
    ├── Services/                         # 服务层
    │   ├── config_service.py             # 配置服务
    │   ├── cache_service.py              # 缓存服务
    │   ├── audio/                        # 音频服务模块
    │   │   └── audio_service.py
    │   ├── image/                        # 图像服务模块
    │   │   └── image_service.py
    │   ├── scheduler/                    # 定时任务服务模块
    │   │   └── scheduler_service.py
    │   └── notion/                       # Notion服务模块
    │       └── notion_service.py         # B站数据管理
    └── Common/                           # 公共模块库
        └── scripts/                      # 工具脚本
            └── common/                   # 通用工具
                └── debug_utils.py        # 调试工具
```

---

## 🏗️ 四层架构设计

### 1️⃣ 前端交互层 (Adapters)
- **FeishuAdapter**: 飞书平台协议转换、事件处理、媒体上传
- **HTTPAdapter**: RESTful API接口、安全鉴权、Swagger文档
- **职责**: 协议转换、输入验证、格式适配

### 2️⃣ 核心业务层 (Business)
- **MessageProcessor**: 业务逻辑处理、消息路由、定时任务处理
- **职责**: 业务规则、流程控制、数据处理

### 3️⃣ 应用控制层 (Application)
- **AppController**: 服务注册、统一调用、健康监控
- **Command**: 命令模式实现、操作封装
- **职责**: 服务编排、API管理、系统监控

### 4️⃣ 服务层 (Services)
- **ConfigService**: 三层配置管理、运行时更新
- **CacheService**: 内存缓存、文件缓存、事件去重
- **AudioService**: TTS语音合成、音频格式转换
- **ImageService**: AI图像生成、风格转换、图片处理
- **SchedulerService**: 定时任务调度、事件驱动架构
- **NotionService**: B站数据获取、统计分析、已读管理

---

## 🔧 核心类和方法清单

### AppController (Module/Application/app_controller.py)

#### ✅ 实际存在的方法：
```python
class AppController:
    def __init__(self, project_root_path: str)

    # 服务管理
    def auto_register_services() -> Dict[str, bool]          # ✅ 自动注册所有服务
    def get_service(self, service_name: str)                 # ✅ 获取服务实例
    def call_service(self, service_name: str, method_name: str, *args, **kwargs)

    # 状态检查
    def health_check() -> Dict[str, Any]                     # ✅ 系统健康检查
    def get_status() -> Dict[str, Any]                       # ✅ 获取系统状态
```

#### health_check() 返回数据结构：
```python
{
    "overall_status": "healthy/unhealthy/degraded",
    "summary": {
        "healthy": int,
        "unhealthy": int,
        "uninitialized": int
    },
    "services": {
        "service_name": {
            "status": "healthy/unhealthy/uninitialized/error",
            "details": {...}
        }
    }
}
```

### ConfigService (Module/Services/config_service.py)

#### ✅ 实际存在的方法：
```python
class ConfigService:
    def __init__(self, auth_config_file_path: str = "",
                 static_config_file_path: str = "config.json",
                 project_root_path: str = "")

    # 配置获取
    def get(self, key: str, default: Any = None) -> Any      # ✅ 获取配置值
    def get_env(self, key: str, default: Any = None) -> Any  # ✅ 获取环境变量

    # 配置管理
    def update_config(self, variable_name: str, new_value: str, ...) -> Tuple[bool, str]
    def reload_all_configs() -> Tuple[bool, str]             # ✅ 重新加载配置
    def validate_config() -> Dict[str, Any]                  # ✅ 验证配置

    # 状态和信息
    def get_status() -> Dict[str, Any]                       # ✅ 获取服务状态
    def get_safe_config() -> Dict[str, Any]                  # ✅ 获取安全配置
    def get_config_source(self, key: str) -> Optional[str]   # ✅ 获取配置来源
    def get_project_info() -> Dict[str, Any]                 # ✅ 获取项目信息
```

### ImageService (Module/Services/image/image_service.py)

#### ✅ 实际存在的方法：
```python
class ImageService:
    def __init__(self, app_controller=None)

    # 初始化和状态
    def initialize() -> bool                                 # ✅ 服务初始化
    def is_available() -> bool                               # ✅ 检查服务可用性
    def get_status() -> Dict[str, Any]                       # ✅ 获取服务状态

    # 图像处理
    def generate_ai_image(self, prompt: str = None, image_input: Dict = None) -> Optional[List[str]]
    def process_text_to_image(self, prompt: str) -> Optional[List[str]]
    def process_image_to_image(self, image_base64: str, mime_type: str = "image/jpeg",
                              file_name: str = "image.jpg", file_size: int = 0) -> Optional[List[str]]
```

### AudioService (Module/Services/audio/audio_service.py)

#### ✅ 实际存在的方法：
```python
class AudioService:
    def __init__(self, app_controller=None)

    # 音频处理
    def generate_tts(self, text: str) -> Optional[bytes]     # ✅ TTS语音合成
    def convert_to_opus(self, input_file_path: str, duration_ms: int = None) -> Tuple[Optional[str], int]
    def process_tts_request(self, text: str) -> Tuple[bool, Optional[bytes], str]

    # 文件管理
    def create_temp_audio_file(self, audio_data: bytes, suffix: str = ".mp3") -> str
    def cleanup_temp_file(self, file_path: str)              # ✅ 清理临时文件

    # 状态检查
    def get_status() -> Dict[str, Any]                       # ✅ 获取服务状态
```

### CacheService (Module/Services/cache_service.py)

#### ✅ 实际存在的方法：
```python
class CacheService:
    def __init__(self, project_root_path: str = "")

    # 事件缓存
    def check_event(self, event_id: str) -> bool             # ✅ 检查事件是否存在
    def add_event(self, event_id: str)                       # ✅ 添加事件记录
    def save_event_cache()                                   # ✅ 保存事件缓存

    # 用户缓存
    def update_user(self, user_id: str, user_name: str)      # ✅ 更新用户信息

    # 通用缓存
    def get(self, key: str, default: Any = None) -> Any      # ✅ 获取缓存值
    def set(self, key: str, value: Any, ttl: int = 0)        # ✅ 设置缓存值

    # 状态管理
    def get_status() -> Dict[str, Any]                       # ✅ 获取服务状态
```

### SchedulerService (Module/Services/scheduler/scheduler_service.py)

#### ✅ 实际存在的方法：
```python
class SchedulerService:
    def __init__(self, app_controller=None)

    # 任务管理
    def add_daily_task(self, task_name: str, time_str: str, task_func, **kwargs) -> bool
    def remove_task(self, task_name: str) -> bool            # ✅ 移除任务
    def list_tasks() -> List[Dict]                           # ✅ 列出所有任务

    # 调度控制
    def run_pending()                                        # ✅ 执行待处理任务
    def clear_all_tasks()                                    # ✅ 清除所有任务

    # 事件系统
    def add_event_listener(self, listener_func)              # ✅ 添加事件监听器
    def trigger_daily_schedule_reminder()                    # ✅ 触发日程提醒
    def trigger_bilibili_updates_reminder(self, sources=None) # ✅ 触发B站更新提醒

    # 状态检查
    def get_status() -> Dict[str, Any]                       # ✅ 获取服务状态
```

### NotionService (Module/Services/notion/notion_service.py)

#### ✅ 实际存在的方法：
```python
class NotionService:
    def __init__(self, cache_service: CacheService)

    # B站视频获取
    def get_bili_video() -> Dict                             # ✅ 获取单个推荐视频
    def get_bili_videos_multiple() -> Dict                   # ✅ 获取多个推荐视频
    def get_video_by_id(self, pageid: str) -> Dict           # ✅ 根据ID获取视频

    # 已读状态管理
    def mark_video_as_read(self, pageid: str) -> bool        # ✅ 标记视频为已读
    def is_video_read(self, pageid: str) -> bool             # ✅ 检查视频是否已读

    # 统计分析
    def get_bili_videos_statistics() -> Dict                 # ✅ 获取视频统计数据

    # 状态检查
    def get_status() -> Dict[str, Any]                       # ✅ 获取服务状态
```

### MessageProcessor (Module/Business/message_processor.py)

#### ✅ 实际存在的方法：
```python
class MessageProcessor:
    def __init__(self, app_controller=None)

    # 消息处理
    def process_message(self, context: MessageContext) -> ProcessResult
    def create_scheduled_message(self, message_type: str, **kwargs) -> ProcessResult

    # 特定功能处理
    def handle_text_message(self, context: MessageContext) -> ProcessResult
    def handle_menu_click(self, context: MessageContext) -> ProcessResult
    def handle_card_action(self, context: MessageContext) -> ProcessResult
    def handle_image_message(self, context: MessageContext) -> ProcessResult
```

---

## 🚀 启动和使用

### 标准启动
```bash
# Windows环境
start.bat

# 或直接运行
python main_refactored.py
```

### 高级启动选项
```bash
# 启动时验证API
python main_refactored.py --verify-api

# 同时启动HTTP API服务器
python main_refactored.py --http-api --http-port 8000

# 完整功能启动
python main_refactored.py --verify-api --http-api --http-port 8000
```

### Jupyter环境
```python
# 异步启动
await main_async()
```

---

## 📊 功能特性总览

### ✅ 已完成功能
- **📱 基础交互**: 文本对话、菜单点击、卡片交互
- **🎤 音频处理**: TTS语音合成、格式转换
- **🎨 图像处理**: AI图像生成、图像风格转换
- **📺 B站推荐**: 1+3模式、已读管理、数据统计
- **⏰ 定时任务**: 事件驱动架构、夜间静默模式
- **🌐 HTTP API**: RESTful接口、安全鉴权
- **🏗️ 四层架构**: 完整实现和统一服务管理

### 🔧 技术特性
- **异步处理**: 即时响应 + 后台处理
- **服务化架构**: 模块化、可扩展、易维护
- **配置管理**: 三层优先级、运行时更新
- **健康监控**: 完整的系统状态检查
- **事件驱动**: 解耦的定时任务系统

---

## 🛡️ 开发规范

### 配置管理规范
1. **三层配置优先级**: 环境变量(.env) > 认证配置文件 > 静态配置(config.json)
2. **AUTH_CONFIG_FILE_PATH**: 必须从环境变量读取，不能从config.json读取
3. **路径解析**: 所有配置文件路径解析都要基于项目根路径

### 代码修改原则
1. **充分理解**: 每次修改前必须充分理解现有业务逻辑和文件依赖
2. **避免引入新问题**: 不能为了解决一个问题而引入新问题
3. **验证失败处理**: 如果验证失败，应该停止尝试，等待用户指导

### 服务开发规范
1. **统一接口**: 所有服务都应实现`get_status()`方法
2. **错误处理**: 优雅处理异常，提供友好错误信息
3. **日志记录**: 使用`debug_utils`进行统一日志记录

---

## 📈 版本历史

- **v3.0 重构完成版**: ✅ 四层架构完整实现，所有功能验证通过
- **项目清理完成**: ✅ 删除旧版本文件，仅保留生产环境必需文件
- **架构优化**: ✅ NotionService迁移到Services层，统一服务管理

---

## 🎯 未来规划

- **微信适配器**: WeChatAdapter实现
- **更多数据源**: 扩展数据获取渠道
- **智能推荐**: 优化推荐算法
- **性能优化**: 进一步提升系统性能