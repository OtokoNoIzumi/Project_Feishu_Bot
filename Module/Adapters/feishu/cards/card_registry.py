"""
基础卡片管理器

为所有feishu卡片管理器提供通用的基础接口和功能
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from Module.Common.scripts.common import debug_utils
from Module.Services.constants import ServiceNames

# 配置驱动的管理器映射 - 从配置文件获取


class BaseCardManager(ABC):
    """卡片管理器基类 - 配置驱动架构"""

    def __init__(self):
        self.templates = {}
        self._initialize_templates()

    @abstractmethod
    def get_card_type_name(self) -> str:
        """获取卡片类型名称 - 子类必须实现"""
        pass

    @abstractmethod
    def get_supported_actions(self) -> List[str]:
        """获取该卡片支持的所有动作 - 子类必须实现"""
        pass

    @abstractmethod
    def build_card(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """构建卡片内容 - 子类必须实现"""
        pass

    def _initialize_templates(self):
        """统一的配置驱动模板初始化 - 基于子类的card_config_key"""
        if not hasattr(self, 'app_controller') or not self.app_controller:
            debug_utils.log_and_print(f"⚠️ {self.get_card_type_name()}卡片管理器缺少app_controller，跳过模板初始化", log_level="WARNING")
            return

        # 获取卡片配置键
        card_config_key = self._get_card_config_key()
        if not card_config_key:
            debug_utils.log_and_print(f"❌ {self.get_card_type_name()}卡片管理器未定义card_config_key", log_level="ERROR")
            return

        # 从配置服务获取模板信息
        card_mapping_service = self.app_controller.get_service(ServiceNames.CARD_OPERATION_MAPPING)
        if not card_mapping_service:
            debug_utils.log_and_print(f"❌ 卡片映射服务不可用", log_level="ERROR")
            return

        template_info = card_mapping_service.get_template_info(card_config_key)
        if template_info.get('template_id'):
            # 使用通用模板名，不再硬编码具体名称
            self.templates = template_info
        else:
            debug_utils.log_and_print(f"⚠️ 未找到{card_config_key}的模板配置", log_level="WARNING")

    def _get_card_config_key(self) -> Optional[str]:
        """获取当前卡片的配置键 - 子类可覆盖"""
        # 基于类名自动推断配置键
        class_name = self.__class__.__name__
        if "UserUpdate" in class_name:
            return "user_update"
        elif "AdsUpdate" in class_name:
            return "ads_update"
        elif "Bilibili" in class_name:
            return "bilibili_video_info"
        return None

    def _build_template_content(self, template_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        构建飞书卡片模板内容 - 简化版，使用默认模板

        Args:
            template_params: 模板参数

        Returns:
            Dict[str, Any]: 卡片内容
        """
        template_config = self.templates
        if not template_config:
            debug_utils.log_and_print(f"❌ {self.get_card_type_name()}未找到默认模板配置", log_level="ERROR")
            return {}

        return {
            "type": "template",
            "data": {
                "template_id": template_config["template_id"],
                "template_version": template_config["template_version"],
                "template_variable": template_params
            }
        }

    def update_template_info(self, template_name: str, template_id: str, version: str):
        """更新模板信息"""
        if template_name in self.templates:
            self.templates[template_name].update({
                "template_id": template_id,
                "template_version": version
            })
            debug_utils.log_and_print(f"✅ 更新{self.get_card_type_name()}模板 {template_name}: {template_id}@{version}", log_level="INFO")


class FeishuCardRegistry:
    """飞书卡片管理器注册表"""

    def __init__(self):
        self._managers: Dict[str, BaseCardManager] = {}

    def register_manager(self, card_type: str, manager: BaseCardManager):
        """注册卡片管理器"""
        self._managers[card_type] = manager
        debug_utils.log_and_print(f"✅ 注册{manager.get_card_type_name()}卡片管理器成功", log_level="INFO")

    def get_manager(self, card_type: str) -> Optional[BaseCardManager]:
        """获取卡片管理器"""
        return self._managers.get(card_type)

    def get_all_managers(self) -> Dict[str, BaseCardManager]:
        """获取所有已注册的管理器"""
        return self._managers.copy()

    def update_all_template_info(self, template_name: str, template_id: str, version: str):
        """批量更新所有管理器的模板信息"""
        for card_type, manager in self._managers.items():
            if template_name in manager.templates:
                manager.update_template_info(template_name, template_id, version)

    def get_manager_by_operation_type(self, operation_type: str, config_service=None) -> Optional[BaseCardManager]:
        """根据业务ID获取对应的卡片管理器 - 配置驱动"""
        if not config_service:
            debug_utils.log_and_print("❌ 缺少配置服务，无法获取管理器映射", log_level="ERROR")
            return None

        # 从应用控制器获取业务映射服务
        card_mapping_service = config_service.get_service(ServiceNames.CARD_OPERATION_MAPPING)
        if not card_mapping_service:
            debug_utils.log_and_print("❌ 卡片业务映射服务不可用", log_level="ERROR")
            return None

        # 获取业务配置
        operation_config = card_mapping_service.get_operation_config(operation_type)
        if not operation_config:
            debug_utils.log_and_print(f"❌ 未找到业务配置: {operation_type}", log_level="WARNING")
            return None

        # 获取管理器标识
        manager_key = operation_config.get('card_config_key')
        if not manager_key:
            debug_utils.log_and_print(f"❌ 业务配置缺少card_config_key字段: {operation_type}", log_level="ERROR")
            return None

        return self.get_manager(manager_key)


# 全局注册表实例
card_registry = FeishuCardRegistry()
