# 🎨 飞书卡片快速添加指南

本指南说明如何快速添加一个新的飞书卡片业务，对现有系统的影响极小，可以快速拔插。

## 🏗️ 系统架构概览

```
配置文件 (cards_business_mapping.json)
    ↓ 驱动
卡片管理器 (XXXCardManager)
    ↓ 注册到
卡片注册表 (FeishuCardRegistry)
    ↓ 使用
卡片处理器 (CardHandler)
```

## 🚀 添加新卡片的5个步骤

### **步骤1: 创建卡片管理器**

在 `Module/Adapters/feishu/cards/` 目录下创建新的管理器文件：

```python
# 示例：music_cards.py
"""
音乐推荐卡片管理器

专门处理音乐推荐相关的飞书卡片
"""

from typing import Dict, Any
from .card_registry import BaseCardManager
from ..decorators import card_build_safe
from Module.Services.constants import CardActions, ResponseTypes


class MusicInteractionComponents:
    """音乐卡片交互组件定义"""

    @staticmethod
    def get_music_recommend_components(operation_id: str, song_id: str) -> Dict[str, Any]:
        """获取音乐推荐卡片的交互组件"""
        return {
            "play_action": {
                "action": CardActions.PLAY_MUSIC,
                "process_result_type": ResponseTypes.MUSIC_CARD_UPDATE,
                "operation_id": operation_id,
                "song_id": song_id
            },
            "like_action": {
                "action": CardActions.LIKE_MUSIC,
                "process_result_type": ResponseTypes.MUSIC_CARD_UPDATE,
                "operation_id": operation_id,
                "song_id": song_id
            }
        }


class MusicCardManager(BaseCardManager):
    """音乐推荐卡片管理器"""

    def get_card_type_name(self) -> str:
        """获取卡片类型名称"""
        return "音乐推荐"

    def _initialize_templates(self):
        """初始化音乐卡片模板配置"""
        self.templates = {
            "music_recommend": {
                "template_id": "AAqxxxxxxxxxxxxx",
                "template_version": "1.0.0"
            }
        }

    @card_build_safe("音乐推荐卡片构建失败")
    def build_music_recommend_card(self, music_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建音乐推荐卡片内容"""
        template_params = self._format_music_params(music_data)
        content = self._build_template_content("music_recommend", template_params)
        return content

    @card_build_safe("格式化音乐参数失败")
    def _format_music_params(self, music_data: Dict[str, Any]) -> Dict[str, Any]:
        """将音乐数据格式化为模板参数"""

        # 获取基本数据
        song_id = music_data.get('song_id', '')
        song_title = music_data.get('song_title', '')
        artist = music_data.get('artist', '')
        operation_id = music_data.get('operation_id', '')

        # 使用交互组件定义系统
        interaction_components = MusicInteractionComponents.get_music_recommend_components(
            operation_id, song_id
        )

        # 构建模板参数
        template_params = {
            "song_id": song_id,
            "song_title": song_title,
            "artist": artist,
            "operation_id": operation_id,

            # 交互组件数据
            "play_action": interaction_components["play_action"],
            "like_action": interaction_components["like_action"]
        }

        return template_params
```

### **步骤2: 注册卡片管理器**

在 `Module/Adapters/feishu/cards/__init__.py` 中添加导入和注册：

```python
# 添加导入
from .music_cards import MusicCardManager

# 在 __all__ 中添加
__all__ = [
    'BaseCardManager',
    'FeishuCardRegistry',
    'BilibiliCardManager',
    'UserUpdateCardManager',
    'AdsUpdateCardManager',
    'MusicCardManager'  # 新增
]

# 在 initialize_card_managers() 函数中添加注册
def initialize_card_managers():
    """初始化并注册所有卡片管理器 - 基于配置映射"""
    # ... 现有代码 ...

    # 注册音乐推荐卡片管理器
    music_manager = MusicCardManager()
    card_registry.register_manager("music", music_manager)

    # ... 现有代码 ...
```

### **步骤3: 配置文件添加映射**

在 `cards_business_mapping.json` 中添加业务配置：

```json
{
  "business_mappings": {
    // ... 现有配置 ...

    "music_recommend": {
      "response_type": "music_card_send",
      "card_manager": "music",
      "card_template": "music_recommend",
      "card_builder_method": "build_music_recommend_card",
      "timeout_seconds": 60,
      "actions": ["play_music", "like_music"],
      "business_processor": "MusicProcessor",
      "description": "音乐推荐卡片"
    }
  },
  "card_managers": {
    // ... 现有配置 ...

    "music": {
      "class_name": "MusicCardManager",
      "module_path": "Module.Adapters.feishu.cards.music_cards",
      "manager_type": "音乐推荐",
      "templates": {
        "music_recommend": {
          "template_id": "AAqxxxxxxxxxxxxx",
          "template_version": "1.0.0"
        }
      }
    }
  }
}
```

### **步骤4: 添加业务处理器**

在 `Module/Business/processors/` 下创建 `music_processor.py`：

```python
"""
音乐处理器

处理音乐推荐相关的业务逻辑
"""

from typing import Dict, Any
from .base_processor import BaseProcessor, MessageContext, ProcessResult, safe_execute


class MusicProcessor(BaseProcessor):
    """音乐推荐处理器"""

    def __init__(self, app_controller=None):
        super().__init__(app_controller)

    @safe_execute("音乐推荐处理失败")
    def handle_music_command(self, context: MessageContext, user_msg: str) -> ProcessResult:
        """处理音乐推荐命令"""

        # 业务逻辑：获取推荐音乐
        music_data = {
            'song_id': '12345',
            'song_title': '示例歌曲',
            'artist': '示例歌手',
            'operation_id': f"music_{context.user_id}_{int(time.time())}"
        }

        return ProcessResult.success_result(
            "music_card_send",  # 对应配置中的response_type
            music_data,
            parent_id=context.message_id
        )

    @safe_execute("音乐操作处理失败")
    def handle_music_action(self, action_value: Dict[str, Any]) -> ProcessResult:
        """处理音乐卡片交互"""

        action = action_value.get('action', '')
        song_id = action_value.get('song_id', '')

        if action == CardActions.PLAY_MUSIC:
            # 处理播放音乐
            return ProcessResult.success_result("music_card_update", {
                'song_id': song_id,
                'status': 'playing',
                'message': '正在播放...'
            })
        elif action == CardActions.LIKE_MUSIC:
            # 处理喜欢音乐
            return ProcessResult.success_result("music_card_update", {
                'song_id': song_id,
                'status': 'liked',
                'message': '已添加到喜欢'
            })

        return ProcessResult.error_result("未知的音乐操作")
```

### **步骤5: 集成到消息处理器**

在 `Module/Business/message_processor.py` 中添加路由：

```python
# 添加导入
from .processors.music_processor import MusicProcessor

class MessageProcessor:
    def __init__(self, app_controller=None):
        # ... 现有代码 ...
        self.music_processor = MusicProcessor(app_controller)

    def process_message(self, context: MessageContext) -> ProcessResult:
        """处理消息的主要方法"""
        # ... 现有代码 ...

        # 添加音乐命令判断
        if user_msg.startswith("推荐音乐"):
            return self.music_processor.handle_music_command(context, user_msg)

        # 在卡片操作处理中添加
        if context.message_type == MessageTypes.CARD_ACTION:
            action = context.content
            action_value = context.metadata.get('action_value', {})

            # ... 现有代码 ...

            # 添加音乐操作处理
            if action in [CardActions.PLAY_MUSIC, CardActions.LIKE_MUSIC]:
                return self.music_processor.handle_music_action(action_value)
```

## ✅ 验证新卡片

添加完成后，运行以下验证：

```python
# 验证管理器注册
from Module.Adapters.feishu.cards import initialize_card_managers
registry = initialize_card_managers()
manager = registry.get_manager("music")
print(f"音乐管理器: {manager.get_card_type_name()}")

# 验证配置映射
from Module.Application.app_controller import AppController
app_controller = AppController()
app_controller.initialize_environment()

validation_results = registry.validate_business_mapping(app_controller)
print(f"music_recommend 验证: {'✅' if validation_results.get('music_recommend') else '❌'}")
```

## 🔧 快速拔插特性

### **移除卡片的步骤：**

1. **从配置文件中删除** `business_mappings` 和 `card_managers` 中的对应项
2. **从 `__init__.py` 中移除** 导入和注册代码
3. **删除管理器文件** `music_cards.py`
4. **删除处理器文件** `music_processor.py`
5. **从消息处理器中移除** 相关路由代码

### **系统影响极小的原因：**

- ✅ **配置驱动**: 所有映射关系都在配置文件中，不影响核心代码
- ✅ **独立管理器**: 每个卡片管理器完全独立，删除不影响其他卡片
- ✅ **自动注册**: 注册表机制确保只有存在的管理器被加载
- ✅ **业务隔离**: 处理器独立，不会影响其他业务逻辑

## 🎯 最佳实践

1. **命名规范**: 文件名使用 `{business}_cards.py` 格式
2. **职责分离**: 一个管理器只负责一种业务类型的卡片
3. **配置优先**: 所有可变参数都放在配置文件中
4. **错误安全**: 使用 `@card_build_safe` 装饰器确保异常安全
5. **交互组件**: 使用独立的交互组件类定义所有用户交互逻辑

通过这种方式，添加新卡片就像安装插件一样简单，完全不会影响现有系统的稳定性！ 🚀