"""系统状态数据处理模块

负责系统状态相关的数据获取和处理
"""

from typing import Dict, Any
from Module.Services.constants import ServiceNames


class SystemDailyData:
    """系统状态数据处理器"""

    def __init__(self, app_controller):
        self.app_controller = app_controller

    def get_operation_data(self, _data_params: Dict[str, Any] = None) -> Dict[str, Any]:
        """获取运营数据"""
        bili_service = self.app_controller.get_service(ServiceNames.BILI_ADSKIP)
        operation_data = bili_service.get_operation_data()

        return operation_data

    def get_services_status(
        self, _data_params: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """获取服务状态"""
        scheduler_service = self.app_controller.get_service(ServiceNames.SCHEDULER)
        services_status = scheduler_service.check_services_status()

        return services_status
