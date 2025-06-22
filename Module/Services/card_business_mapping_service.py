import json
import os
from typing import Dict, Any, Optional


class CardBusinessMappingService:
    """卡片业务映射配置服务

    负责加载和管理卡片业务映射配置，提供配置化关联的核心服务
    通过ConfigService集成，避免重复造轮子
    """

    def __init__(self, config_service=None):
        self.config_service = config_service
        self._mappings_cache: Optional[Dict[str, Any]] = None
        self._load_mappings()

    def _load_mappings(self) -> None:
        """加载卡片业务映射配置"""
        try:
            if self.config_service:
                # 通过ConfigService读取配置
                config_file_path = os.path.join(self.config_service.project_root_path, "cards_business_mapping.json")
                if os.path.exists(config_file_path):
                    with open(config_file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        self._mappings_cache = data.get("business_mappings", {})
                else:
                    print(f"[CardBusinessMapping] 配置文件不存在: {config_file_path}")
                    self._mappings_cache = {}
            else:
                print(f"[CardBusinessMapping] ConfigService不可用，无法加载配置")
                self._mappings_cache = {}
        except Exception as e:
            print(f"[CardBusinessMapping] 加载配置失败: {e}")
            self._mappings_cache = {}

    def get_business_config(self, business_id: str) -> Dict[str, Any]:
        """根据业务ID获取配置

        Args:
            business_id: 业务标识 (如 'update_user', 'update_ads', 'bili_video_menu')

        Returns:
            Dict[str, Any]: 业务配置字典，不存在时返回空字典
        """
        if self._mappings_cache is None:
            self._load_mappings()

        return self._mappings_cache.get(business_id, {})

    def get_config_by_response_type(self, response_type: str) -> Dict[str, Any]:
        """根据响应类型获取配置

        Args:
            response_type: 响应类型 (如 'admin_card_send', 'bili_card_send')

        Returns:
            Dict[str, Any]: 匹配的业务配置，不存在时返回空字典
        """
        if self._mappings_cache is None:
            self._load_mappings()

        for business_id, config in self._mappings_cache.items():
            if config.get("response_type") == response_type:
                return config

        return {}

    def get_all_mappings(self) -> Dict[str, Dict[str, Any]]:
        """获取所有业务映射配置

        Returns:
            Dict[str, Dict[str, Any]]: 完整的业务映射配置字典
        """
        if self._mappings_cache is None:
            self._load_mappings()

        return self._mappings_cache.copy() if self._mappings_cache else {}

    def reload_mappings(self) -> bool:
        """重新加载映射配置

        Returns:
            bool: 重载是否成功
        """
        try:
            self._load_mappings()
            return True
        except Exception as e:
            print(f"[CardBusinessMapping] 重载配置失败: {e}")
            return False

    def validate_business_mapping(self, business_id: str) -> bool:
        """验证单个业务映射配置的完整性

        Args:
            business_id: 业务标识

        Returns:
            bool: 验证是否通过
        """
        config = self.get_business_config(business_id)
        if not config:
            return False

        required_fields = [
            "response_type", "card_template", "card_builder_method",
            "timeout_seconds", "actions", "business_processor"
        ]

        for field in required_fields:
            if field not in config:
                print(f"[CardBusinessMapping] 业务 {business_id} 缺少必填字段: {field}")
                return False

        return True

    def validate_all_mappings(self) -> Dict[str, bool]:
        """验证所有业务映射配置

        Returns:
            Dict[str, bool]: 各业务的验证结果
        """
        results = {}
        for business_id in self.get_all_mappings().keys():
            results[business_id] = self.validate_business_mapping(business_id)

        return results

    def get_response_type(self, business_id: str) -> str:
        """获取业务的响应类型

        Args:
            business_id: 业务标识

        Returns:
            str: 响应类型，不存在时返回空字符串
        """
        config = self.get_business_config(business_id)
        return config.get("response_type", "")

    def get_timeout_seconds(self, business_id: str) -> int:
        """获取业务的超时时间

        Args:
            business_id: 业务标识

        Returns:
            int: 超时时间（秒），不存在时返回30秒默认值
        """
        config = self.get_business_config(business_id)
        return config.get("timeout_seconds", 30)

    def get_card_builder_method(self, business_id: str) -> str:
        """获取业务的卡片构建方法名

        Args:
            business_id: 业务标识

        Returns:
            str: 卡片构建方法名，不存在时返回空字符串
        """
        config = self.get_business_config(business_id)
        return config.get("card_builder_method", "")

    def get_business_actions(self, business_id: str) -> list:
        """获取业务支持的动作列表

        Args:
            business_id: 业务标识

        Returns:
            list: 动作列表，不存在时返回空列表
        """
        config = self.get_business_config(business_id)
        return config.get("actions", [])