"""
应用控制器

提供服务注册、统一调用接口和多服务协同功能
设计原则：简单、实用、高性能，支持MVP快速验证
"""

import os
from typing import Dict, Any, Optional, Tuple
from Module.Common.scripts.common import debug_utils
from Module.Services import AVAILABLE_SERVICES
from Module.Services.constants import ServiceNames
from .app_utils import PathUtils


class AppController:
    """
    应用控制器 - 统一管理和调用各种服务

    功能：
    1. 服务注册和管理
    2. 统一的服务调用接口
    3. 服务状态监控
    4. 简单的错误处理和恢复
    """

    def __init__(self, project_root_path: str = ""):
        """
        初始化应用控制器

        Args:
            project_root_path: 项目根路径，用于服务初始化
        """
        self.project_root_path = project_root_path or PathUtils.get_project_root_from_file(__file__, levels_up=2)
        self.services: Dict[str, Any] = {}
        self.service_configs: Dict[str, Dict[str, Any]] = {}
        self.initialized_services: set = set()

    def register_service(self, service_name: str, service_class: type, config: Dict[str, Any] = None) -> bool:
        """
        注册服务

        Args:
            service_name: 服务名称
            service_class: 服务类
            config: 服务配置参数

        Returns:
            bool: 注册是否成功
        """
        try:
            if service_name in self.services:
                debug_utils.log_and_print(f"服务 '{service_name}' 已存在，将被覆盖", log_level="WARNING")

            self.service_configs[service_name] = config or {}

            # 暂时只注册类，不立即初始化（懒加载）
            self.services[service_name] = {
                'class': service_class,
                'instance': None,
                'status': 'registered'
            }

            return True

        except Exception as e:
            debug_utils.log_and_print(f"注册服务 '{service_name}' 失败: {e}", log_level="ERROR")
            return False

    def _initialize_service(self, service_name: str) -> bool:
        """
        初始化特定服务（懒加载）

        Args:
            service_name: 服务名称

        Returns:
            bool: 初始化是否成功
        """
        if service_name not in self.services:
            debug_utils.log_and_print(f"服务 '{service_name}' 未注册", log_level="ERROR")
            return False

        if service_name in self.initialized_services:
            return True  # 已初始化

        try:
            service_info = self.services[service_name]
            service_class = service_info['class']
            config = self.service_configs[service_name]

            # 根据服务类型进行特定初始化
            match service_name:
                case ServiceNames.CONFIG:
                    instance = service_class(
                        project_root_path=self.project_root_path,
                        **config
                    )
                case ServiceNames.CACHE:
                    cache_dir = config.get('cache_dir', os.path.join(self.project_root_path, "cache"))
                    os.makedirs(cache_dir, exist_ok=True)
                    instance = service_class(cache_dir)
                case ServiceNames.AUDIO | ServiceNames.SCHEDULER | ServiceNames.LLM | ServiceNames.ROUTER:
                    instance = service_class(app_controller=self)
                case ServiceNames.NOTION:
                    cache_service = self.get_service(ServiceNames.CACHE)
                    if not cache_service:
                        raise Exception("notion服务需要cache服务，但cache服务初始化失败")
                    instance = service_class(cache_service)
                case ServiceNames.CARD_BUSINESS_MAPPING:
                    config_service = self.get_service(ServiceNames.CONFIG)
                    if not config_service:
                        raise Exception("card_business_mapping服务需要config服务，但config服务初始化失败")
                    instance = service_class(config_service)
                case _:
                    instance = service_class(**config)

            service_info['instance'] = instance
            service_info['status'] = 'initialized'
            self.initialized_services.add(service_name)  # 延迟到post_init后标记

            return True

        except Exception as e:
            debug_utils.log_and_print(f"初始化服务 '{service_name}' 失败: {e}", log_level="ERROR")
            self.services[service_name]['status'] = 'failed'
            return False

    def get_service(self, service_name: str) -> Optional[Any]:
        """
        获取服务实例

        Args:
            service_name: 服务名称

        Returns:
            Optional[Any]: 服务实例，如果失败返回None
        """
        if service_name not in self.services:
            debug_utils.log_and_print(f"服务 '{service_name}' 未注册", log_level="ERROR")
            return None

        # 懒加载：如果还未初始化，先初始化
        if service_name not in self.initialized_services:
            if not self._initialize_service(service_name):
                return None

        return self.services[service_name]['instance']

    def call_service(self, service_name: str, method_name: str, *args, **kwargs) -> Tuple[bool, Any]:
        """
        统一的服务调用接口

        Args:
            service_name: 服务名称
            method_name: 方法名称
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            Tuple[bool, Any]: (是否成功, 返回值或错误信息)
        """
        try:
            service = self.get_service(service_name)
            if service is None:
                return False, f"服务 '{service_name}' 不可用"

            if not hasattr(service, method_name):
                return False, f"服务 '{service_name}' 没有方法 '{method_name}'"

            method = getattr(service, method_name)
            result = method(*args, **kwargs)

            return True, result

        except Exception as e:
            error_msg = f"调用 {service_name}.{method_name} 失败: {e}"
            debug_utils.log_and_print(error_msg, log_level="ERROR")
            return False, error_msg

    def get_service_status(self, service_name: str = None) -> Dict[str, Any]:
        """
        获取服务状态

        Args:
            service_name: 服务名称，如果为None则返回所有服务状态

        Returns:
            Dict[str, Any]: 服务状态信息
        """
        if service_name:
            if service_name not in self.services:
                return {"error": f"服务 '{service_name}' 未注册"}

            service_info = self.services[service_name]
            status = {
                "name": service_name,
                "status": service_info['status'],
                "initialized": service_name in self.initialized_services,
                "available": service_info['instance'] is not None
            }

            # 如果服务已初始化，尝试获取详细状态
            if service_name in self.initialized_services and service_info['instance']:
                try:
                    if hasattr(service_info['instance'], 'get_status'):
                        status["details"] = service_info['instance'].get_status()
                except:
                    pass

            return status

        # 返回所有服务状态
        all_status = {
            "controller": {
                "project_root": self.project_root_path,
                "total_services": len(self.services),
                "initialized_services": sum(1 for name, info in self.services.items() if info.get("status") == 'initialized')
            },
            "services": {}
        }

        for name in self.services:
            all_status["services"][name] = self.get_service_status(name)

        return all_status

    def initialize_all_services(self) -> Dict[str, bool]:
        """
        初始化所有注册的服务

        Returns:
            Dict[str, bool]: 各服务初始化结果
        """
        results = {}

        for service_name in self.services:
            results[service_name] = self._initialize_service(service_name)

        debug_utils.log_and_print(
            f"批量初始化完成，成功: {sum(results.values())}/{len(results)}",
            log_level="INFO"
        )

        return results

    def auto_register_services(self) -> Dict[str, bool]:
        """
        自动注册可用的服务

        Returns:
            Dict[str, bool]: 各服务注册结果
        """
        results = {}

        try:
            for service_name, service_class in AVAILABLE_SERVICES.items():
                # 根据服务类型设置默认配置
                match service_name:
                    case ServiceNames.CONFIG:
                        config = {
                            'static_config_file_path': 'config.json'
                        }
                    case ServiceNames.CACHE:
                        config = {
                            'cache_dir': os.path.join(self.project_root_path, 'cache')
                        }
                    case ServiceNames.PENDING_CACHE:
                        config = {
                            'cache_dir': os.path.join(self.project_root_path, 'cache'),
                            'max_operations_per_user': 2
                        }
                    case ServiceNames.CARD_BUSINESS_MAPPING:
                        config = {}
                    case _:
                        config = {}

                results[service_name] = self.register_service(service_name, service_class, config)

            debug_utils.log_and_print(
                f"自动注册完成，成功: {sum(results.values())}/{len(results)}",
                log_level="INFO"
            )

        except ImportError as e:
            debug_utils.log_and_print(f"自动注册失败，无法导入服务: {e}", log_level="ERROR")

        return results

    def health_check(self) -> Dict[str, Any]:
        """
        健康检查

        Returns:
            Dict[str, Any]: 健康状态信息
        """
        health_status = {
            "overall_status": "healthy",
            "controller_status": "running",
            "services": {},
            "summary": {
                "total": len(self.services),
                "healthy": 0,
                "unhealthy": 0,
                "uninitialized": 0
            }
        }

        for service_name in self.services:
            try:
                service_status = self.get_service_status(service_name)

                if service_status.get("available", False):
                    status = "healthy"
                    health_status["summary"]["healthy"] += 1
                elif service_status.get("status", "uninitialized") == "initialized":
                    status = "unhealthy"
                    health_status["summary"]["unhealthy"] += 1
                else:
                    status = "uninitialized"
                    health_status["summary"]["uninitialized"] += 1

                health_status["services"][service_name] = {
                    "status": status,
                    "details": service_status
                }

            except Exception as e:
                health_status["services"][service_name] = {
                    "status": "error",
                    "error": str(e)
                }
                health_status["summary"]["unhealthy"] += 1

        # 更新总体状态
        if health_status["summary"]["unhealthy"] > 0:
            health_status["overall_status"] = "degraded"
        elif health_status["summary"]["healthy"] == 0:
            health_status["overall_status"] = "initializing"

        return health_status
