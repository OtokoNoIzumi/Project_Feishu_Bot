# 飞书机器人重构版 - 技术参考文档

## ⚠️ 重构工作流程规范

**在进行任何代码修改前，必须先查阅本文档！**

本文档记录了所有现有的方法、模块和接口，确保重构工作基于实际存在的API，避免使用不存在的方法。

---

## 📁 项目架构概览

```
Project_Feishu_Bot/
├── Module/
│   ├── Application/
│   │   └── app_controller.py              # 应用控制器
│   ├── Business/
│   │   └── message_processor.py           # 业务逻辑处理器
│   ├── Adapters/
│   │   └── feishu_adapter.py              # 飞书平台适配器
│   ├── Services/                          # 服务层
│   │   ├── __init__.py                    # 服务注册表
│   │   ├── config_service.py              # 配置服务
│   │   ├── cache_service.py               # 缓存服务
│   │   ├── audio/                         # 音频服务模块
│   │   │   ├── __init__.py
│   │   │   └── audio_service.py
│   │   ├── image/                         # 图像服务模块
│   │   │   ├── __init__.py
│   │   │   └── image_service.py
│   │   └── scheduler/                     # 定时任务服务模块
│   │       ├── __init__.py
│   │       └── scheduler_service.py
│   └── Common/
│       └── scripts/
│           └── common/
│               └── debug_utils.py          # 调试工具
├── main_refactored_audio.py               # 音频版本启动文件
├── main_refactored_audio_image.py         # 音频+图像版本启动文件
├── main_refactored_schedule.py            # 定时任务版本启动文件
├── test_image_service.py                  # 图像服务测试脚本
└── test_scheduler_service.py              # 定时任务服务测试脚本
```

---

## 🔧 核心类和方法清单

### 1. AppController (Module/Application/app_controller.py)

#### ✅ 实际存在的方法：
```python
class AppController:
    def __init__(self, project_root_path: str)

    # 服务管理
    def auto_register_services() -> Dict[str, bool]          # ✅ 正确方法名
    def get_service(self, service_name: str)
    def call_service(self, service_name: str, method_name: str, *args, **kwargs)

    # 状态检查
    def health_check() -> Dict[str, Any]                     # ✅ 正确方法名
    def get_status() -> Dict[str, Any]
```

#### ❌ 不存在的方法（禁止使用）：
```python
# ❌ 这些方法不存在，禁止使用！
def register_available_services()     # 错误！正确是 auto_register_services()
def get_health_status()              # 错误！正确是 health_check()
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

### 2. ConfigService (Module/Services/config_service.py)

#### ✅ 实际存在的方法：
```python
class ConfigService:
    def __init__(self, auth_config_file_path: str = "",
                 static_config_file_path: str = "config.json",
                 project_root_path: str = "")

    def get(self, key: str, default: Any = None) -> Any
    def get_env(self, key: str, default: Any = None) -> Any
    def update_config(self, variable_name: str, new_value: str, ...) -> Tuple[bool, str]
    def get_status() -> Dict[str, Any]
    def get_safe_config() -> Dict[str, Any]
    def reload_all_configs() -> Tuple[bool, str]
    def validate_config() -> Dict[str, Any]
    def get_config_source(self, key: str) -> Optional[str]
    def get_project_info() -> Dict[str, Any]
```

#### ❌ 不存在的方法（禁止使用）：
```python
# ❌ ConfigService 没有 initialize 方法！
def initialize()                     # 错误！ConfigService不需要手动初始化
```

### 3. ImageService (Module/Services/image/image_service.py)

#### ✅ 实际存在的方法：
```python
class ImageService:
    def __init__(self, app_controller=None)

    # 初始化和状态
    def initialize() -> bool                                 # ✅ ImageService有此方法
    def is_available() -> bool
    def get_status() -> Dict[str, Any]

    # 图像处理
    def generate_ai_image(self, prompt: str = None, image_input: Dict = None) -> Optional[List[str]]
    def process_text_to_image(self, prompt: str) -> Optional[List[str]]
    def process_image_to_image(self, image_base64: str, mime_type: str = "image/jpeg",
                              file_name: str = "image.jpg", file_size: int = 0) -> Optional[List[str]]

    # 私有方法
    def _load_config()
    def _init_gradio_client()
    def _check_service_health() -> bool
    def _parse_generation_result(self, result) -> Optional[List[str]]
```

### 4. AudioService (Module/Services/audio/audio_service.py)

#### ✅ 实际存在的方法：
```python
class AudioService:
    def __init__(self, app_controller=None)

    # 音频处理
    def generate_tts(self, text: str) -> Optional[bytes]
    def convert_to_opus(self, input_file_path: str, duration_ms: int = None) -> Tuple[Optional[str], int]
    def process_tts_request(self, text: str) -> Tuple[bool, Optional[bytes], str]

    # 文件管理
    def create_temp_audio_file(self, audio_data: bytes, suffix: str = ".mp3") -> str
    def cleanup_temp_file(self, file_path: str)

    # 状态和配置
    def get_status() -> Dict[str, Any]
    def _load_config()
    def _get_ffmpeg_command() -> Optional[str]
```

#### ❌ 不存在的方法（禁止使用）：
```python
# ❌ AudioService 没有 initialize 方法！
def initialize()                     # 错误！AudioService不需要手动初始化
```

### 5. CacheService (Module/Services/cache_service.py)

#### ✅ 实际存在的方法：
```python
class CacheService:
    def __init__(self, project_root_path: str = "")

    # 事件缓存
    def check_event(self, event_id: str) -> bool
    def add_event(self, event_id: str)
    def save_event_cache()

    # 用户缓存
    def update_user(self, user_id: str, user_name: str)

    # 通用缓存
    def get(self, key: str, default: Any = None) -> Any
    def set(self, key: str, value: Any, ttl: int = 0)

    # 状态管理
    def get_status() -> Dict[str, Any]
```

### 6. MessageProcessor (Module/Business/message_processor.py)

#### ✅ 实际存在的方法：
```python
class MessageProcessor:
    def __init__(self, app_controller=None)

    # 主要处理方法
    def process_message(self, context: MessageContext) -> ProcessResult

    # 异步处理方法（由适配器调用）
    def process_tts_async(self, tts_text: str) -> ProcessResult
    def process_image_generation_async(self, prompt: str) -> ProcessResult
    def process_image_conversion_async(self, image_base64: str, mime_type: str,
                                     file_name: str, file_size: int) -> ProcessResult

    # 私有处理方法
    def _process_text_message(self, context: MessageContext) -> ProcessResult
    def _process_image_message(self, context: MessageContext) -> ProcessResult
    def _process_audio_message(self, context: MessageContext) -> ProcessResult
    def _process_menu_click(self, context: MessageContext) -> ProcessResult
    def _process_card_action(self, context: MessageContext) -> ProcessResult

    # 事件管理
    def _is_duplicate_event(self, event_id: str) -> bool
    def _record_event(self, context: MessageContext)

    # 指令处理
    def _handle_config_update(self, context: MessageContext, user_msg: str) -> ProcessResult
    def _handle_tts_command(self, context: MessageContext, user_msg: str) -> ProcessResult
    def _handle_image_generation_command(self, context: MessageContext, user_msg: str) -> ProcessResult
    def _handle_help_command(self, context: MessageContext) -> ProcessResult
    def _handle_greeting_command(self, context: MessageContext) -> ProcessResult

    # 定时任务相关（与SchedulerService集成）
    def process_scheduled_message(self, message_type: str, context: MessageContext) -> ProcessResult

    # 状态
    def get_status() -> Dict[str, Any]
    def _load_config()
```

### 6. SchedulerService (Module/Services/scheduler/scheduler_service.py)

#### ✅ 实际存在的方法：
```python
class SchedulerService:
    def __init__(self, app_controller=None)

    # 服务管理
    def get_status() -> Dict[str, Any]

    # 定时任务管理
    def add_cron_job(self, job_id: str, func: callable, trigger: str, **kwargs) -> bool
    def remove_job(self, job_id: str) -> bool
    def get_jobs() -> List[Dict[str, Any]]

    # 内置任务（从旧版迁移）
    def send_daily_schedule(self)                           # 每日日程提醒
    def send_bilibili_updates(self)                         # B站更新推送

    # 私有方法
    def _setup_default_jobs()
    def _load_config()
```

#### ❌ 不存在的方法（禁止使用）：
```python
# ❌ SchedulerService 没有 initialize 方法！
def initialize()                     # 错误！SchedulerService不需要手动初始化
```

### 7. FeishuAdapter (Module/Adapters/feishu_adapter.py)

#### ✅ 实际存在的方法：
```python
class FeishuAdapter:
    def __init__(self, message_processor, app_controller=None)

    # 启动和停止
    def start()                                              # 同步启动
    async def start_async()                                  # 异步启动
    def stop()

    # 事件处理（飞书SDK回调）
    def _handle_feishu_message(self, data) -> None
    def _handle_feishu_menu(self, data) -> None
    def _handle_feishu_card(self, data) -> P2CardActionTriggerResponse

    # 消息转换
    def _convert_message_to_context(self, data) -> Optional[MessageContext]
    def _convert_menu_to_context(self, data) -> Optional[MessageContext]
    def _convert_card_to_context(self, data) -> Optional[MessageContext]
    def _extract_message_content(self, message) -> Any

    # 用户信息
    def _get_user_name(self, open_id: str) -> str

    # 消息发送
    def _send_feishu_reply(self, original_data, result: ProcessResult) -> bool
    def _send_direct_message(self, user_id: str, result: ProcessResult) -> bool

    # 异步处理
    def _handle_tts_async(self, original_data, tts_text: str)
    def _handle_image_generation_async(self, original_data, prompt: str)
    def _handle_image_conversion_async(self, original_data, context)

    # 资源管理
    def _get_image_resource(self, original_data) -> Optional[Tuple[str, str, str, int]]
    def _upload_and_send_images(self, original_data, image_paths: List[str]) -> bool
    def _upload_and_send_single_image(self, original_data, image_path: str) -> bool
    def _upload_and_send_audio(self, original_data, audio_data: bytes) -> bool
    def _upload_opus_to_feishu(self, opus_path: str, duration_ms: int) -> Optional[str]

    # 配置和状态
    def _init_feishu_config()
    def _create_ws_client()
    def get_status() -> Dict[str, Any]
```

---

## 📊 数据结构规范

### MessageContext
```python
@dataclass
class MessageContext:
    user_id: str
    user_name: str
    message_type: str          # "text", "image", "audio", "menu_click", "card_action"
    content: Any
    timestamp: datetime
    event_id: str
    metadata: Dict[str, Any] = None
```

### ProcessResult
```python
@dataclass
class ProcessResult:
    success: bool
    response_type: str         # "text", "image", "audio", "post", "image_list"
    response_content: Any
    error_message: str = None
    should_reply: bool = True

    # 工厂方法
    @classmethod
    def success_result(cls, response_type: str, content: Any)

    @classmethod
    def error_result(cls, error_msg: str)

    @classmethod
    def no_reply_result(cls)
```

---

## 🚀 服务注册和启动流程

### 正确的启动代码模式：
```python
# 1. 创建应用控制器
app_controller = AppController(project_root_path=str(current_dir))

# 2. 自动注册服务（正确方法名！）
registration_results = app_controller.auto_register_services()

# 3. 检查系统健康状态（正确方法名！）
health_status = app_controller.health_check()

# 4. 获取服务（ConfigService不需要initialize）
config_service = app_controller.get_service('config')
# ❌ 错误：config_service.initialize()  # ConfigService没有此方法！

# 5. 初始化有initialize方法的服务
image_service = app_controller.get_service('image')
if image_service:
    image_service.initialize()  # ✅ 正确：ImageService有此方法

# 6. 创建业务处理器和适配器
message_processor = MessageProcessor(app_controller=app_controller)
feishu_adapter = FeishuAdapter(
    message_processor=message_processor,
    app_controller=app_controller
)

# 7. 启动适配器
feishu_adapter.start()  # 同步方式
# 或
await feishu_adapter.start_async()  # 异步方式
```

---

## 🔍 服务状态检查标准

### health_check() 结果处理：
```python
health_status = app_controller.health_check()

# ✅ 正确的访问方式
overall_status = health_status['overall_status']
healthy_count = health_status['summary']['healthy']
unhealthy_count = health_status['summary']['unhealthy']
uninitialized_count = health_status['summary']['uninitialized']

for service_name, service_info in health_status['services'].items():
    status = service_info['status']  # ✅ 正确：先获取service_info，再获取status
    details = service_info.get('details', {})

# ❌ 错误的访问方式（旧版本格式）
# healthy_count = health_status['healthy_count']        # 错误！
# status = health_status['services'][service_name]     # 错误！
```

---

## 📋 服务调用模式

### 缓存服务调用：
```python
# ✅ 正确的调用方式（直接调用方法）
cache_service = app_controller.get_service('cache')
is_duplicate = cache_service.check_event(event_id)
cache_service.add_event(event_id)
cache_service.save_event_cache()

# ❌ 错误的调用方式（使用call_service）
# app_controller.call_service('cache', 'get/set')      # 错误的方法名！
```

### 配置服务调用：
```python
# ✅ 正确的调用方式
config_service = app_controller.get_service('config')
value = config_service.get('key_name', default_value)

# 或通过 call_service
success, value = app_controller.call_service('config', 'get', 'key_name', default_value)
```

---

## 📝 文件命名和组织规范

### 主启动文件：
- `main_refactored_audio.py` - 仅音频功能版本
- `main_refactored_audio_image.py` - 音频+图像功能版本

### 测试文件：
- `test_image_service.py` - 图像服务专项测试
- `test_*.py` - 其他测试文件

### 服务模块：
- `Module/Services/service_name.py` - 单文件服务
- `Module/Services/service_name/` - 多文件服务模块

---

## ⚠️ 常见错误防范清单

### 在编写任何代码前，必须检查：

1. **方法名检查**：
   - ✅ `auto_register_services()` 不是 `register_available_services()`
   - ✅ `health_check()` 不是 `get_health_status()`

2. **初始化方法检查**：
   - ✅ ConfigService 没有 `initialize()` 方法
   - ✅ AudioService 没有 `initialize()` 方法
   - ✅ ImageService 有 `initialize()` 方法
   - ✅ CacheService 没有 `initialize()` 方法
   - ✅ SchedulerService 没有 `initialize()` 方法

3. **数据结构检查**：
   - ✅ health_check返回的是嵌套结构，不是平面结构
   - ✅ services中每个服务是dict，包含status和details

4. **构造函数参数检查**：
   - ✅ `AppController(project_root_path=str(path))` 不是 `AppController(path)`

5. **导入检查**：
   - ✅ 确认所有使用的类和方法都已正确导入
   - ✅ 确认路径和模块名正确

---

## 📚 参考代码示例

参考已验证可用的代码：
- `main_refactored_audio.py` - 完整的启动流程
- `main_refactored_audio_image.py` - 多媒体功能版本
- `main_refactored_schedule.py` - 定时任务版本
- `Module/Services/` - 各服务的实际实现
- `Module/Business/message_processor.py` - 业务逻辑处理

**记住：所有新代码都必须基于实际存在的方法和接口！**

---

## 🔄 文档更新规范

每当添加新服务或修改现有接口时，必须同步更新本文档的相应部分。

**版本：** 2025-06-03
**最后更新：** schedule服务集成完成后