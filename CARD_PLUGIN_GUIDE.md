# 🎨 飞书卡片模块技术指南

本指南详细说明飞书卡片模块的架构设计、实现方式和开发流程，包含最新的配置驱动架构和扩展机制。

## 🏗️ 系统架构概览

项目采用配置驱动的卡片管理架构，实现了高度模块化和可扩展的卡片系统：

```
配置文件层 (cards_business_mapping.json)
    ↓ 驱动配置
卡片业务映射服务 (CardBusinessMappingService)
    ↓ 提供映射
卡片管理器 (BaseCardManager)
    ↓ 注册到
卡片注册表 (FeishuCardRegistry)
    ↓ 使用
卡片处理器 (CardHandler)
    ↓ 集成
业务处理器 (MessageProcessor)
```

## 🔧 核心组件详解

### 1. 配置驱动架构

项目实现了完全配置驱动的卡片管理系统，通过 `cards_business_mapping.json` 集中管理所有卡片配置：

```json
{
  "business_mappings": {
    "业务标识": {
      "response_type": "响应类型",
      "card_config_key": "卡片配置键",
      "processor": "业务处理器",
      "timeout_seconds": 30,
      "description": "业务描述"
    }
  },
  "card_configs": {
    "卡片配置键": {
      "reply_modes": "回复模式",
      "class_name": "管理器类名",
      "module_path": "模块路径",
      "template_id": "飞书模板ID",
      "template_version": "模板版本"
    }
  }
}
```

### 2. 基础卡片管理器 (BaseCardManager)

所有卡片管理器都继承自 `BaseCardManager`，提供统一的接口和功能：

```python
class BaseCardManager(ABC):
    """卡片管理器基类 - 配置驱动架构"""

    @abstractmethod
    def get_card_type_name(self) -> str:
        """获取卡片类型名称"""
        pass

    @abstractmethod
    def get_supported_actions(self) -> List[str]:
        """获取该卡片支持的所有动作"""
        pass

    @abstractmethod
    def build_card(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """构建卡片内容"""
        pass
```

### 3. 卡片注册表 (FeishuCardRegistry)

实现单例模式的卡片管理器注册系统，支持：
- 自动注册配置化的卡片管理器
- 根据业务ID动态获取管理器
- 统一的模板信息管理

### 4. 卡片业务映射服务 (CardBusinessMappingService)

提供配置化的业务映射服务，实现：
- 配置文件解析和缓存
- 业务配置查询接口
- 模板信息获取

## 🚀 卡片开发流程

### 步骤1: 创建卡片管理器

在 `Module/Adapters/feishu/cards/` 目录下创建新的管理器文件：

```python
# 示例：music_cards.py
"""
音乐推荐卡片管理器
"""

from typing import Dict, Any, List
from .card_registry import BaseCardManager
from ..decorators import card_build_safe
from Module.Services.constants import CardActions, ResponseTypes


class MusicCardManager(BaseCardManager):
    """音乐推荐卡片管理器"""

    def __init__(self, app_controller=None):
        self.app_controller = app_controller
        super().__init__()

    def get_card_type_name(self) -> str:
        return "音乐推荐"

    def get_supported_actions(self) -> List[str]:
        return [CardActions.PLAY_MUSIC, CardActions.LIKE_MUSIC]

    @card_build_safe("音乐推荐卡片构建失败")
    def build_card(self, music_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建音乐推荐卡片内容"""
        template_params = self._format_music_params(music_data)
        return self._build_template_content(template_params)

    def _format_music_params(self, music_data: Dict[str, Any]) -> Dict[str, Any]:
        """将音乐数据格式化为模板参数"""
        return {
            "song_title": music_data.get('title', ''),
            "artist": music_data.get('artist', ''),
            "play_action": {
                "action": CardActions.PLAY_MUSIC,
                "song_id": music_data.get('song_id', '')
            }
        }
```

### 步骤2: 配置业务映射

在 `cards_business_mapping.json` 中添加业务配置：

```json
{
  "business_mappings": {
    "music_recommend": {
      "response_type": "music_card_send",
      "card_config_key": "music_recommendation",
      "processor": "MusicProcessor",
      "timeout_seconds": 60,
      "description": "音乐推荐卡片"
    }
  },
  "card_configs": {
    "music_recommendation": {
      "reply_modes": "new",
      "class_name": "MusicCardManager",
      "module_path": "Module.Adapters.feishu.cards.music_cards",
      "template_id": "AAqxxxxxxxxxxxxx",
      "template_version": "1.0.0"
    }
  }
}
```

### 步骤3: 添加业务处理器

在 `Module/Business/processors/` 下创建对应的业务处理器：

```python
"""
音乐处理器
"""

from typing import Dict, Any
from .base_processor import BaseProcessor, MessageContext, ProcessResult
from Module.Services.constants import ResponseTypes


class MusicProcessor(BaseProcessor):
    """音乐推荐处理器"""

    def process_music_request(self, context: MessageContext) -> ProcessResult:
        """处理音乐推荐请求"""
        # 业务逻辑实现
        music_data = self._get_music_recommendation(context.content)

        return ProcessResult.success_result(
            ResponseTypes.MUSIC_CARD_SEND,
            music_data
        )
```

### 步骤4: 注册卡片管理器

系统采用自动注册机制，通过配置文件自动发现和注册卡片管理器，无需手动修改注册代码。

## 🎯 当前已实现的卡片类型

### 1. B站视频卡片 (BilibiliCardManager)
- **功能**: B站视频推荐菜单显示
- **支持动作**: `mark_bili_read`
- **模板ID**: `AAqBPdq4sxIy5`
- **特性**: 支持主视频+附加视频列表，已读状态管理

### 2. 用户更新卡片 (UserUpdateCardManager)
- **功能**: 管理员用户状态更新确认
- **支持动作**: `confirm_user_update`, `cancel_user_update`, `update_user_type`
- **模板ID**: `AAqdbwJ2cflOp`
- **特性**: 交互式用户类型选择，操作确认机制

### 3. 广告时间更新卡片 (AdsUpdateCardManager)
- **功能**: B站广告时间戳更新确认
- **支持动作**: `confirm_ads_update`, `cancel_ads_update`, `adtime_editor_change`
- **模板ID**: `AAqdJvEYwMDQ3`
- **特性**: 时间编辑器，批量更新支持

## 🔄 卡片事件处理流程

```
飞书卡片点击事件
    ↓
CardHandler.handle_feishu_card()
    ↓
_convert_card_to_context() (转换为MessageContext)
    ↓
MessageProcessor.process_message()
    ↓
对应的业务处理器处理
    ↓
返回ProcessResult
    ↓
根据response_type生成相应响应
```

## 🛠️ 关键技术特性

### 1. 装饰器安全机制
- `@card_build_safe`: 卡片构建异常处理
- `@card_operation_safe`: 卡片操作异常处理
- `@message_conversion_safe`: 消息转换异常处理

### 2. 配置驱动的模板管理
- 自动从配置文件加载模板信息
- 统一的模板参数格式化
- 版本化的模板管理

### 3. 交互组件定义系统
- 标准化的交互组件定义
- 动作类型统一管理
- 响应类型映射机制

### 4. 错误处理和调试支持
- 统一的错误日志记录
- 调试信息输出
- 操作失败回滚机制

## 📊 扩展指南

### 添加新动作类型
1. 在 `Module/Services/constants.py` 的 `CardActions` 类中添加新动作
2. 在对应的卡片管理器中实现动作处理逻辑
3. 在业务处理器中添加动作路由

### 添加新响应类型
1. 在 `ResponseTypes` 类中定义新类型
2. 在 `CardHandler` 中添加响应处理逻辑
3. 在业务处理器中使用新的响应类型

### 自定义卡片模板
1. 在飞书开放平台创建新模板
2. 在配置文件中添加模板信息
3. 在管理器中实现模板参数格式化

## 🔍 调试和监控

### 日志系统
- 使用 `debug_utils.log_and_print()` 进行统一日志记录
- 支持不同日志级别 (INFO, WARNING, ERROR)
- 卡片操作全程日志追踪

### 配置验证
- 启动时自动验证配置文件格式
- 卡片管理器注册状态检查
- 模板信息完整性验证

## 🎮 最佳实践

1. **使用配置驱动**: 优先通过配置文件而非硬编码实现功能
2. **异常安全**: 所有卡片操作都应使用相应的装饰器保护
3. **统一接口**: 遵循 `BaseCardManager` 定义的标准接口
4. **模块化设计**: 保持卡片管理器、业务处理器和配置的分离
5. **版本管理**: 为卡片模板维护版本信息，支持渐进式升级

## 📚 相关文档

- [技术架构参考](TECHNICAL_ARCHITECTURE_REFERENCE.md)
- [开发变更日志](CHANGELOG.md)
- [AI路由器设计](AI_ROUTER_DESIGN.md)