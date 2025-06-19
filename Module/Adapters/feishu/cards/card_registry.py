"""
基础卡片管理器

为所有feishu卡片管理器提供通用的基础接口和功能
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from Module.Common.scripts.common import debug_utils


class BaseCardManager(ABC):
    """基础卡片管理器抽象类"""

    def __init__(self):
        """初始化基础卡片管理器"""
        self.templates: Dict[str, Dict[str, str]] = {}
        self._initialize_templates()

    @abstractmethod
    def _initialize_templates(self):
        """初始化模板配置 - 子类必须实现"""
        pass

    @abstractmethod
    def get_card_type_name(self) -> str:
        """获取卡片类型名称 - 子类必须实现"""
        pass

    def get_template_info(self, template_name: str) -> Optional[Dict[str, str]]:
        """获取模板信息"""
        return self.templates.get(template_name)

    def update_template_info(self, template_name: str, template_id: str, version: str):
        """更新模板信息"""
        if template_name in self.templates:
            self.templates[template_name]['template_id'] = template_id
            self.templates[template_name]['template_version'] = version
            debug_utils.log_and_print(
                f"✅ {self.get_card_type_name()}卡片模板 {template_name} 信息已更新",
                log_level="INFO"
            )
        else:
            debug_utils.log_and_print(
                f"❌ {self.get_card_type_name()}卡片模板 {template_name} 不存在",
                log_level="WARNING"
            )

    def _build_template_content(self, template_name: str, template_params: Dict[str, Any]) -> Dict[str, Any]:
        """构建模板内容"""
        template_info = self.get_template_info(template_name)
        if not template_info:
            raise ValueError(f"模板 {template_name} 不存在")

        return {
            "data": {
                "template_id": template_info['template_id'],
                "template_variable": template_params,
                "template_version_name": template_info['template_version']
            },
            "type": "template"
        }

    def _log_success(self, operation: str):
        """记录成功日志"""
        debug_utils.log_and_print(f"✅ {self.get_card_type_name()}卡片{operation}成功", log_level="INFO")

    def _log_error(self, operation: str, error_msg: str):
        """记录错误日志"""
        debug_utils.log_and_print(f"❌ {self.get_card_type_name()}卡片{operation}失败: {error_msg}", log_level="ERROR")


class FeishuCardRegistry:
    """飞书卡片注册中心"""

    def __init__(self):
        """初始化卡片注册中心"""
        self._managers: Dict[str, BaseCardManager] = {}

    def register_manager(self, card_type: str, manager: BaseCardManager):
        """注册卡片管理器"""
        self._managers[card_type] = manager
        debug_utils.log_and_print(f"✅ 注册{card_type}卡片管理器成功", log_level="INFO")

    def get_manager(self, card_type: str) -> Optional[BaseCardManager]:
        """获取卡片管理器"""
        return self._managers.get(card_type)

    def list_managers(self) -> Dict[str, str]:
        """列出所有注册的管理器"""
        return {card_type: manager.get_card_type_name() for card_type, manager in self._managers.items()}

    def update_all_template_info(self, template_name: str, template_id: str, version: str):
        """批量更新所有管理器的模板信息"""
        for card_type, manager in self._managers.items():
            if template_name in manager.templates:
                manager.update_template_info(template_name, template_id, version)