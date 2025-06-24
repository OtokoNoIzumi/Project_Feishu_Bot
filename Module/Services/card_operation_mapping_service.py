import json
import os
from typing import Dict, Any, Optional


class CardOperationMappingService:
    """卡片操作映射配置服务

    负责加载和管理卡片操作映射配置，提供配置化关联的核心服务
    通过ConfigService集成，避免重复造轮子
    """

    def __init__(self, config_service=None):
        self.config_service = config_service
        self._mappings_cache: Optional[Dict[str, Any]] = None
        self._definitions_cache: Optional[Dict[str, Any]] = None
        self._mappings_cache = {}
        self._definitions_cache = {}
        self._load_mappings()

    def _load_mappings(self) -> None:
        """加载卡片操作映射配置"""
        try:
            if not self.config_service:
                print(f"[CardOperationMapping] ConfigService不可用，无法加载配置")
                return

            # 通过ConfigService读取配置
            config_file_path = os.path.join(self.config_service.project_root_path, "cards_operation_mapping.json")
            if not os.path.exists(config_file_path):
                print(f"[CardOperationMapping] 配置文件不存在: {config_file_path}")
                return

            with open(config_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self._mappings_cache = data.get("operation_mappings", {})
                self._definitions_cache = data.get("card_configs", {})

        except Exception as e:
            print(f"[CardOperationMapping] 加载配置失败: {e}")

    def get_operation_config(self, operation_type: str) -> Dict[str, Any]:
        """根据业务ID获取配置

        Args:
            operation_type: 业务标识 (如 'update_user', 'update_ads', 'bili_video_menu')

        Returns:
            Dict[str, Any]: 业务配置字典，不存在时返回空字典
        """
        if self._mappings_cache is None:
            self._load_mappings()

        return self._mappings_cache.get(operation_type, {})


    def get_response_type(self, operation_type: str) -> str:
        """获取业务的响应类型

        Args:
            operation_type: 业务标识

        Returns:
            str: 响应类型，不存在时返回空字符串
        """
        config = self.get_operation_config(operation_type)
        return config.get("response_type", "")

    def get_timeout_seconds(self, operation_type: str) -> int:
        """获取业务的超时时间

        Args:
            operation_type: 业务标识

        Returns:
            int: 超时时间（秒），不存在时返回30秒默认值
        """
        config = self.get_operation_config(operation_type)
        return config.get("timeout_seconds", 30)

    def get_card_config_key(self, operation_type: str) -> str:
        """获取业务的卡片配置键名

        Args:
            operation_type: 业务标识

        Returns:
            str: 卡片配置键名，不存在时返回空字符串
        """
        config = self.get_operation_config(operation_type)
        return config.get("card_config_key", "")

    def get_processor(self, operation_type: str) -> str:
        """获取业务的处理器名称

        Args:
            operation_type: 业务标识

        Returns:
            str: 处理器名称，不存在时返回空字符串
        """
        config = self.get_operation_config(operation_type)
        return config.get("processor", "")

    def get_card_definition(self, card_config_key: str) -> Dict[str, Any]:
        """根据管理器键获取管理器配置

        Args:
            card_config_key: 卡片配置键 (如 'user_update', 'ads_update', 'bilibili_video_info')

        Returns:
            Dict[str, Any]: 管理器配置字典，不存在时返回空字典
        """
        if not hasattr(self, '_definitions_cache') or self._definitions_cache is None:
            self._load_mappings()

        return self._definitions_cache.get(card_config_key, {})

    def get_card_config(self, card_config_key: str) -> Dict[str, Any]:
        """根据卡片配置键获取卡片配置

        Args:
            card_config_key: 卡片配置键 (如 'user_update', 'ads_update', 'bilibili_video_info')

        Returns:
            Dict[str, Any]: 卡片配置字典，不存在时返回空字典
        """
        if not hasattr(self, '_definitions_cache') or self._definitions_cache is None:
            self._load_mappings()

        return self._definitions_cache.get(card_config_key, {})

    def get_template_info(self, card_config_key: str) -> Dict[str, str]:
        """获取卡片的模板信息

        Args:
            card_config_key: 卡片配置键

        Returns:
            Dict[str, str]: 包含template_id和template_version的字典
        """
        card_config = self.get_card_config(card_config_key)
        return {
            "template_id": card_config.get("template_id", ""),
            "template_version": card_config.get("template_version", "")
        }

    def get_all_definition(self) -> Dict[str, Dict[str, Any]]:
        """获取所有管理器配置

        Returns:
            Dict[str, Dict[str, Any]]: 完整的管理器配置字典
        """
        if not hasattr(self, '_definitions_cache') or self._definitions_cache is None:
            self._load_mappings()

        return self._definitions_cache.copy() if self._definitions_cache else {}
