"""每日信息汇总业务

处理每日信息汇总的完整业务逻辑，包括：
1. B站信息分析数据构建
2. 运营数据获取与处理
3. 日报卡片生成
4. 用户权限验证
"""

from typing import Dict, Any, List
from datetime import datetime

from Module.Common.scripts.common import debug_utils
from Module.Services.constants import (
    ServiceNames,
    ResponseTypes,
    SchedulerConstKeys,
    ColorTypes,
)
from Module.Business.processors.base_processor import (
    BaseProcessor,
    ProcessResult,
    require_service,
    safe_execute,
)
from Module.Business.routine_record import RoutineRecord
from Module.Adapters.feishu.cards.json_builder import JsonBuilder

# 导入子模块
from .summary.backend.bili_daily_data import BiliDailyData
from .summary.backend.routine_daily_data import RoutineDailyData
from .summary.backend.system_daily_data import SystemDailyData
from .summary.frontend.bili_daily_element import BiliDailyElement
from .summary.frontend.routine_daily_element import RoutineDailyElement
from .summary.frontend.system_daily_element import SystemDailyElement


class DailySummaryBusiness(BaseProcessor):
    """
    每日信息汇总业务

    负责处理每日信息汇总的完整业务流程
    """

    # region 后端业务入口
    # 业务堆栈
    # 注册
    # main.setup_scheduled_tasks  # 如果后续要区分user，在这里就要把user_id和各自的时间设置进去。虽然现在的user_id都来自飞书，但应该可以直接扩展到其他
    # -> scheduler_service.TaskUtils.get_task_function
    # -> scheduler_service.add_daily_task

    # 触发
    # 这里service和processor的架构是旧版，以后重构
    # ScheduledEvent的结构不够好，目前type有一份冗余，现在使用的是data里的scheduler_type
    # scheduler_service.trigger_daily_schedule_reminder
    # -> main.handle_scheduled_event
    # -> schedule_processor.create_task
    # -> schedule_processor.daily_summary 这里更多应该是定时属性，业务集中在下面
    # -> daily_summary_business.create_daily_summary
    # -> main.handle_scheduled_event

    def __init__(self, app_controller, developer_mode_path=None):
        """初始化日常事项记录业务"""
        super().__init__(app_controller)
        self.developer_mode_path = developer_mode_path
        if not self.developer_mode_path:
            self.config_service = self.app_controller.get_service(ServiceNames.CONFIG)
            self.routine_business = RoutineRecord(self.app_controller)

        # 初始化子模块实例
        self.bili_data = BiliDailyData(app_controller)
        self.routine_data = RoutineDailyData(app_controller)
        self.system_data = SystemDailyData(app_controller)
        self.bili_element = BiliDailyElement(app_controller)
        self.routine_element = RoutineDailyElement(app_controller)
        self.system_element = SystemDailyElement()

    @require_service("bili_adskip", "B站广告跳过服务不可用")
    @safe_execute("创建每日信息汇总失败")
    def create_daily_summary(self, event_data: Dict[str, Any]) -> ProcessResult:
        """
        创建每日信息汇总消息（主业务入口）

        Args:
            user_id: 用户ID
            services_status: 服务状态信息

        Returns:
            ProcessResult: 处理结果
        """
        # 构建B站信息cache分析数据（整合原来的分散逻辑）
        # analysis 是后端的数据处理逻辑，然后提供给前端的卡片进行build_card
        user_id = event_data.get(SchedulerConstKeys.ADMIN_ID)
        daily_raw_data = self.get_daily_raw_data(user_id)

        # 有数据之后再在前端写
        card_content = self.create_daily_summary_card(daily_raw_data)

        return ProcessResult.user_list_result("interactive", card_content)

    # endregion

    # region 采集模块数据
    # 假设user_id信息存在来做，但实际上都先赋值为我——管理员id
    # 业务信息顺序应该是从一个配置获得某个user_id的daily_summary 的触发时间，然后到时间了开始进入本模块采集信息，再通过前端发出去
    # 这里是一个包含采集和处理两个部分的总接口
    GRANULARITY_MINUTES = 120

    def get_daily_raw_data(self, user_id: str) -> Dict[str, Any]:
        """
        获取每日信息汇总原始数据（重构后的版本）

        使用子模块架构，根据权限配置调用相应的数据处理模块
        """
        # 后续要改成从用户数据读取，这里先写死
        # 要不要进一步分离获取数据和处理，我觉得可以有，要合并回来就是剪切一下的事
        # 全开是我的，如果是其他user_id就只开日常分析
        # AI的分析可能要并行，我感觉两个是完全无关的
        # 不同人用的图片也可能不一样？但应该现在基本不着急，毕竟豆包也没啥开销
        # 模块配置：定义各业务模块的权限、开关和对应的子模块实例
        module_configs = {
            "routine": {
                "name": "日常分析",
                "system_permission": True,
                "user_enabled": True,
                "backend_instance": self.routine_data,  # 后端数据处理实例
                "data_method": "get_routine_data",
                "analyze_method": "analyze_routine_data",
                "image_method": "generate_routine_image",
            },
            "bili_video": {
                "name": "B站视频",
                "system_permission": True,
                "user_enabled": True,
                "sync_read_mark": True,
                "backend_instance": self.bili_data,  # 后端数据处理实例
                "data_method": "get_notion_bili_data",
                "analyze_method": "analyze_bili_video_data",
            },
            "bili_adskip": {
                "name": "B站广告跳过",
                "system_permission": True,
                "user_enabled": True,
                "backend_instance": self.system_data,  # 系统数据处理实例
                "data_method": "get_operation_data",
            },
            "services_status": {
                "name": "服务状态",
                "system_permission": True,
                "user_enabled": True,
                "backend_instance": self.system_data,  # 系统数据处理实例
                "data_method": "get_services_status",
            },
        }

        # 根据权限配置调用相应的子模块方法
        for module_name, config in module_configs.items():
            if config["system_permission"] and config["user_enabled"]:
                backend_instance = config["backend_instance"]
                data_method = config["data_method"]

                # 检查子模块实例是否有对应的数据获取方法
                if hasattr(backend_instance, data_method):
                    data_params = config.get("data_params", {})
                    data_params["user_id"] = user_id

                    # 调用子模块的数据获取方法
                    module_data = getattr(backend_instance, data_method)(data_params)
                    if module_data:
                        config["data"] = module_data

                        # 如果有分析方法，调用子模块的分析方法
                        analyze_method = config.get("analyze_method", "")
                        if analyze_method and hasattr(backend_instance, analyze_method):
                            config["info"] = getattr(backend_instance, analyze_method)(
                                module_data
                            )
                else:
                    debug_utils.log_and_print(
                        f"子模块{backend_instance.__class__.__name__}没有实现{data_method}方法",
                        log_level="WARNING",
                    )

        # 添加系统状态信息（不需要权限控制的基础信息）
        module_configs["system_status"] = {
            "name": "系统状态",
            "data": {
                "date": datetime.now().strftime("%Y年%m月%d日"),
                "weekday": [
                    "周一",
                    "周二",
                    "周三",
                    "周四",
                    "周五",
                    "周六",
                    "周日",
                ][datetime.now().weekday()],
            },
            "user_id": user_id,
        }

        return module_configs

    # endregion

    # region 前端日报卡片

    @safe_execute("创建日报卡片失败")
    def create_daily_summary_card(
        self, daily_raw_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """创建每日信息汇总卡片"""
        # 内容是按照顺序排列的，所以天然可以分组，还是用card_registry里的方法。

        main_color = (
            daily_raw_data.get("routine", {})
            .get("data", {})
            .get("daily", {})
            .get("main_color", {})
        )
        main_color_name = main_color.get("name", "独特的颜色")
        header_template = (
            main_color_name
            if main_color_name != "独特的颜色"
            else main_color.get("closest_to", ColorTypes.BLUE.value)
        )

        header = JsonBuilder.build_card_header(
            title="📊 每日信息汇总",
            template=header_template,
        )
        elements = self.build_daily_summary_elements(daily_raw_data)
        if elements:
            system_status = daily_raw_data.get("system_status", {}).get("data", {})
            date = system_status.get("date", "")
            weekday = system_status.get("weekday", "")
            date_element = JsonBuilder.build_markdown_element(f"**{date} {weekday}**")
            elements.insert(0, date_element)

        return JsonBuilder.build_base_card_structure(elements, header)

    def build_daily_summary_elements(
        self, daily_raw_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """构建每日信息汇总元素（重构后的版本）

        使用前端子模块架构，将各业务域的卡片构建委托给对应的前端模块
        """
        elements = []

        # 使用B站前端模块构建B站相关元素
        bili_video_data = daily_raw_data.get("bili_video", {}).get("info", {})
        video_list = []
        if bili_video_data:
            video_info, video_list = self.bili_element.build_bili_video_elements(
                bili_video_data
            )
            elements.extend(video_info)

        # 使用系统前端模块构建运营数据元素
        operation_data = daily_raw_data.get("bili_adskip", {}).get("data", {})
        if operation_data:
            elements.extend(
                self.system_element.build_operation_elements(operation_data)
            )

        # 使用系统前端模块构建服务状态元素
        services_status = daily_raw_data.get("services_status", {}).get("data", {})
        if services_status:
            elements.extend(
                self.system_element.build_services_status_elements(services_status)
            )

        # 使用日常分析前端模块构建日常分析元素
        routine_info = daily_raw_data.get("routine", {}).get("info", {})
        if routine_info:
            user_id = daily_raw_data.get("system_status", {}).get("user_id", "")
            elements.extend(
                self.routine_element.build_routine_elements(routine_info, user_id)
            )

        elements.append(JsonBuilder.build_line_element())
        elements.extend(video_list)

        return elements

    # region 回调处理

    @require_service("notion", "标记服务暂时不可用")
    @safe_execute("处理B站标记已读失败")
    def mark_bili_read_v2(self, action_value: Dict[str, Any]) -> ProcessResult:
        """处理B站视频标记已读的回调"""
        # 获取notion服务
        notion_service = self.app_controller.get_service(ServiceNames.NOTION)

        # 获取参数
        pageid = action_value.get("pageid", "")
        video_index = action_value.get("video_index", 1)

        # 执行标记为已读操作
        success = notion_service.mark_video_as_read(pageid)
        if not success:
            return ProcessResult.error_result("标记为已读失败")

        return ProcessResult.success_result(
            ResponseTypes.SCHEDULER_CARD_UPDATE_BILI_BUTTON,
            {
                "toast": {
                    "type": "success",
                    "content": f"已标记第{video_index}个推荐为已读",
                },
                "remove_element_id": f"mark_bili_read_{video_index}",
                "text_element_id": f"bili_video_{video_index}",
            },
        )

    # endregion
