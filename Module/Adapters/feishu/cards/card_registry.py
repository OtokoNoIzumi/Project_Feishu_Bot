"""
基础卡片管理器

为所有feishu卡片管理器提供通用的基础接口和功能
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from Module.Common.scripts.common import debug_utils

# 配置驱动的管理器映射 - 从配置文件获取


class BaseCardManager(ABC):
    """所有卡片管理器的基础类"""

    def __init__(self):
        """初始化基础卡片管理器"""
        self.templates = {}
        self._initialize_templates()

    @abstractmethod
    def get_card_type_name(self) -> str:
        """获取卡片类型名称（用于日志和调试）"""
        pass

    @abstractmethod
    def _initialize_templates(self):
        """初始化卡片模板配置（子类实现）"""
        pass

    def _build_template_content(self, template_name: str, template_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        构建飞书卡片模板内容

        Args:
            template_name: 模板名称
            template_params: 模板参数

        Returns:
            Dict[str, Any]: 卡片内容
        """
        template_config = self.templates.get(template_name)
        if not template_config:
            debug_utils.log_and_print(f"❌ 未找到模板配置: {template_name}", log_level="ERROR")
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

    def get_manager_by_business_id(self, business_id: str, config_service=None) -> Optional[BaseCardManager]:
        """根据业务ID获取对应的卡片管理器 - 配置驱动"""
        if not config_service:
            debug_utils.log_and_print("❌ 缺少配置服务，无法获取管理器映射", log_level="ERROR")
            return None

        # 从应用控制器获取业务映射服务
        from Module.Services.constants import ServiceNames
        card_mapping_service = config_service.get_service(ServiceNames.CARD_BUSINESS_MAPPING)
        if not card_mapping_service:
            debug_utils.log_and_print("❌ 卡片业务映射服务不可用", log_level="ERROR")
            return None

        # 获取业务配置
        business_config = card_mapping_service.get_business_config(business_id)
        if not business_config:
            debug_utils.log_and_print(f"❌ 未找到业务配置: {business_id}", log_level="WARNING")
            return None

        # 获取管理器标识
        manager_key = business_config.get('card_manager')
        if not manager_key:
            debug_utils.log_and_print(f"❌ 业务配置缺少card_manager字段: {business_id}", log_level="ERROR")
            return None

        return self.get_manager(manager_key)

    def validate_business_mapping(self, config_service=None) -> Dict[str, bool]:
        """验证业务映射配置的完整性 - 配置驱动"""
        results = {}

        if not config_service:
            debug_utils.log_and_print("⚠️ 缺少配置服务，跳过业务映射验证", log_level="WARNING")
            return results

        # 从应用控制器获取业务映射服务
        from Module.Services.constants import ServiceNames
        card_mapping_service = config_service.get_service(ServiceNames.CARD_BUSINESS_MAPPING)
        if not card_mapping_service:
            debug_utils.log_and_print("⚠️ 卡片业务映射服务不可用，跳过验证", log_level="WARNING")
            return results

        # 获取所有业务配置
        all_business_configs = card_mapping_service.get_all_business_configs()

        for business_id, business_config in all_business_configs.items():
            manager_key = business_config.get('card_manager')
            if manager_key:
                manager = self.get_manager(manager_key)
                results[business_id] = manager is not None
            else:
                results[business_id] = False

        return results


# 全局注册表实例
card_registry = FeishuCardRegistry()
