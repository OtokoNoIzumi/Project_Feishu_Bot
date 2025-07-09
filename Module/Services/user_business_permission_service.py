"""
用户业务权限服务

提供用户业务权限管理能力，支持：
1. 系统许可权限控制
2. 用户个人开关控制
3. 按用户ID和业务名称进行权限检查
"""

from typing import Dict, Any
from Module.Common.scripts.common import debug_utils
from .service_decorators import service_operation_safe
from Module.Services.constants import EnvVars, ServiceNames


class UserBusinessPermissionService:
    """
    用户业务权限服务

    管理用户对不同业务功能的访问权限
    支持系统级许可和用户级开关的双重控制
    """

    def __init__(self, app_controller):
        """初始化用户业务权限服务"""
        # 硬编码权限配置（用户ID在最外层，便于用户视角管理）
        self.app_controller = app_controller
        self.admin_id = self.app_controller.get_service(ServiceNames.CONFIG).get(EnvVars.ADMIN_ID)
        self._user_permissions = {
            # 不同的app_id对应不同的openid，这里develop的是08158e2f511912a18063fc6072ce42da，release的是ou_bb1ec32fbd4660b4d7ca36b3640f6fde
            self.admin_id: {
                "daily_summary": {
                    "system_permission": True,
                    "user_enabled": True
                }
            },
            "ou_ac04234023cf23e54cdd0b1c1dadd000": {
                "daily_summary": {
                    "system_permission": False,
                    "user_enabled": True
                }
            }
        }

    @service_operation_safe("检查业务权限失败", return_value=False)
    def check_business_permission(self, user_id: str, business_name: str) -> bool:
        """
        检查用户是否有指定业务的权限

        Args:
            user_id: 用户ID
            business_name: 业务名称

        Returns:
            bool: 是否有权限（系统许可 AND 用户开关都为True）
        """
        if not user_id or not business_name:
            debug_utils.log_and_print(f"权限检查参数无效: user_id={user_id}, business_name={business_name}", log_level="WARNING")
            return False

        # 获取用户权限配置
        user_config = self._user_permissions.get(user_id, {})
        business_config = user_config.get(business_name, {})

        # 检查系统许可权限
        system_permission = business_config.get("system_permission", False)
        if not system_permission:
            return False

        # 检查用户开关
        user_enabled = business_config.get("user_enabled", False)
        if not user_enabled:
            return False

        return True

    @service_operation_safe("获取用户业务权限配置失败", return_value={})
    def get_user_business_config(self, user_id: str, business_name: str) -> Dict[str, Any]:
        """
        获取用户指定业务的权限配置

        Args:
            user_id: 用户ID
            business_name: 业务名称

        Returns:
            Dict[str, Any]: 权限配置信息
        """
        if not user_id or not business_name:
            return {}

        user_config = self._user_permissions.get(user_id, {})
        return user_config.get(business_name, {})

    @service_operation_safe("获取业务权限概览失败", return_value={})
    def get_business_permissions_overview(self, business_name: str) -> Dict[str, Dict[str, Any]]:
        """
        获取指定业务的所有用户权限概览

        Args:
            business_name: 业务名称

        Returns:
            Dict[str, Dict[str, Any]]: 业务权限概览 {user_id: config}
        """
        overview = {}
        for user_id, user_config in self._user_permissions.items():
            if business_name in user_config:
                overview[user_id] = user_config[business_name]
        return overview

    def get_enabled_users_for_business(self, business_name: str) -> list[str]:
        """
        获取指定业务的所有有权限用户列表

        Args:
            business_name: 业务名称

        Returns:
            list[str]: 有权限的用户ID列表
        """
        enabled_users = []

        for user_id in self._user_permissions.keys():
            if self.check_business_permission(user_id, business_name):
                enabled_users.append(user_id)

        return enabled_users