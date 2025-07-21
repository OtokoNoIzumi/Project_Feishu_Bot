"""
日常事项记录业务

处理日常事项记录的完整业务逻辑，包括：
1. 用户独立文件夹数据存储
2. 事项创建和记录管理
3. 前置指令识别和处理
4. 查询和展示功能
5. 事件定义与记录分离的数据模型
"""

import os
import json
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from Module.Common.scripts.common import debug_utils
from Module.Services.constants import (
    ServiceNames,
    RoutineTypes,
    RouteTypes,
    RoutineCheckCycle,
    RoutineProgressTypes,
    RoutineTargetTypes,
    DirectRecordFields,
)
from Module.Business.processors.base_processor import (
    BaseProcessor,
    ProcessResult,
    safe_execute,
)
from Module.Business.processors import RouteResult


# 从一开始就用抽象层
class EventStorage:
    def save_event(self, event_data):
        pass

    def load_events(self):
        pass

    def query_events(self, filter_func):
        pass


class JSONEventStorage(EventStorage):
    def save_event(self, event_data):
        # JSON实现
        pass

    def load_events(self, user_data_path, user_id):
        # JSON实现
        pass

    def query_events(self, filter_func):
        # JSON实现
        pass


class RoutineRecord(BaseProcessor):
    """
    日常事项记录业务

    负责处理日常事项记录的完整业务流程，支持：
    - 事件定义与记录分离
    - 复杂属性管理（分类、程度、关联等）
    - 适配器无关的数据模型
    - 使用抽象方法准备多个数据储存逻辑的话，最好用一个set storage的接口，在初始化的内部做一个设置？好像也没必要set，直接赋值就行。
    """

    def __init__(self, app_controller):
        """初始化日常事项记录业务"""
        super().__init__(app_controller)
        self.config_service = self.app_controller.get_service(ServiceNames.CONFIG)
        self.user_permission_service = self.app_controller.get_service(
            ServiceNames.USER_BUSINESS_PERMISSION
        )
        self.storage = JSONEventStorage()

    def _get_formatted_time(self) -> str:
        """
        获取格式化的时间字符串

        Returns:
            str: 格式化时间 "2025-07-10 09:07:30"
        """
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _get_user_data_path(self, user_id: str) -> str:
        """
        获取用户数据存储路径

        Args:
            user_id: 用户ID

        Returns:
            str: 用户数据文件夹路径
        """
        storage_path = self.config_service.get(
            "routine_record.storage_path", "user_data/"
        )

        # 如果不是绝对路径，基于项目根路径解析
        if not os.path.isabs(storage_path):
            project_root = self.config_service.project_root_path
            storage_path = os.path.join(project_root, storage_path)

        user_folder = os.path.join(storage_path, user_id)

        # 确保用户文件夹存在
        os.makedirs(user_folder, exist_ok=True)

        return user_folder

    def _get_event_definitions_file_path(self, user_id: str) -> str:
        """
        获取用户事件定义文件路径

        Args:
            user_id: 用户ID

        Returns:
            str: 事件定义文件路径
        """
        user_folder = self._get_user_data_path(user_id)
        return os.path.join(user_folder, "event_definitions.json")

    def _get_event_records_file_path(self, user_id: str) -> str:
        """
        获取用户事件记录文件路径

        Args:
            user_id: 用户ID

        Returns:
            str: 事件记录文件路径
        """
        user_folder = self._get_user_data_path(user_id)
        return os.path.join(user_folder, "event_records.json")

    def _create_event_definition(
        self, event_name: str, event_type: str = RoutineTypes.INSTANT
    ) -> Dict[str, Any]:
        """
        创建事件定义

        Args:
            event_name: 事件名称
            event_type: 事件类型

        Returns:
            Dict[str, Any]: 事件定义
        """
        # 其实还需要套用一些默认的不同类型的属性，等做到了再说
        current_time = self._get_formatted_time()
        return {
            "name": event_name,
            "type": event_type,
            "category": "",
            "description": "",
            "properties": {
                # 关联属性
                "related_start_event": None,
                "related_events": [],
                # 显示属性
                "include_in_daily_check": False,
                # 快捷访问属性
                "quick_access": False,
                # 程度/层次属性
                "has_degrees": False,
                "degree_options": [],
                "default_degree": "",
                # 时间属性
                "future_date": None,
                "estimated_duration": None,
                # 目标属性
                "check_cycle": None,
                "custom_cycle_config": None,
                "target_type": None,  # 次数/时长
                "target_value": None,  # 目标值
                # 指标属性
                "progress_type": "",  # 进度类型
            },
            "stats": {
                "record_count": 0,
                "cycle_count": 0,
                "last_target_count": 0,
                "duration": {
                    "recent_values": [],  # 最近N次的耗时值
                    "window_size": 10,  # 滑动窗口大小
                    "duration_count": 0,  # 有耗时记录的次数
                    "avg_all_time": None,  # 历史平均耗时
                },
                "last_refresh_date": None,
                "last_progress_value": None,
                "last_note": "",  # 记录最近一次的备注
            },
            "created_time": current_time,
            "last_record_time": None,
            "last_updated": current_time,
        }

    def _get_next_record_id(self, user_id: str, event_name: str) -> str:
        """
        生成下一个记录ID

        Args:
            user_id: 用户ID
            event_name: 事件名称

        Returns:
            str: 记录ID，格式为 event_name_序号
        """
        definitions_data = self.load_event_definitions(user_id)

        # 计算该事件的现有记录数量
        count = (
            definitions_data.get("definitions", {})
            .get(event_name, {})
            .get("stats", {})
            .get("record_count", 0)
        )

        # 生成新的序号（从00001开始）
        next_num = count + 1
        return f"{event_name}_{next_num:05d}"

    def _create_event_record(
        self,
        event_name: str,
        user_id: str,
        degree: str = "",
        note: str = "",
        related_records: List[str] = None,
    ) -> Dict[str, Any]:
        """
        创建事件记录

        Args:
            event_name: 事件名称
            user_id: 用户ID
            degree: 事件程度
            note: 备注
            related_records: 关联记录ID列表

        Returns:
            Dict[str, Any]: 事件记录
        """
        current_time = self._get_formatted_time()
        record_id = self._get_next_record_id(user_id, event_name)

        return {
            "record_id": record_id,
            "event_name": event_name,
            "timestamp": current_time,
            "degree": degree,
            "note": note,
            "related_records": related_records or [],
        }

    @safe_execute("加载事件定义失败")
    def load_event_definitions(self, user_id: str) -> Dict[str, Any]:
        """
        加载用户的事件定义

        Args:
            user_id: 用户ID

        Returns:
            Dict[str, Any]: 事件定义数据
        """
        file_path = self._get_event_definitions_file_path(user_id)

        if not os.path.exists(file_path):
            # 创建空数据结构
            current_time = self._get_formatted_time()
            default_data = {
                "user_id": user_id,
                "definitions": {},
                "categories": [],
                "created_time": current_time,
                "last_updated": current_time,
            }
            self.save_event_definitions(user_id, default_data)
            return default_data

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 确保基本字段存在
                if "categories" not in data:
                    data["categories"] = []
                return data
        except (json.JSONDecodeError, FileNotFoundError) as e:
            debug_utils.log_and_print(f"读取事件定义文件失败: {e}", log_level="ERROR")
            return {}

    @safe_execute("加载事件记录失败")
    def load_event_records(self, user_id: str) -> Dict[str, Any]:
        """
        加载用户的事件记录

        Args:
            user_id: 用户ID

        Returns:
            Dict[str, Any]: 事件记录数据
        """
        file_path = self._get_event_records_file_path(user_id)

        if not os.path.exists(file_path):
            # 创建空记录结构
            current_time = self._get_formatted_time()
            default_data = {
                "user_id": user_id,
                "active_records": [],
                "records": [],
                "created_time": current_time,
                "last_updated": current_time,
            }
            self.save_event_records(user_id, default_data)
            return default_data

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data
        except (json.JSONDecodeError, FileNotFoundError) as e:
            debug_utils.log_and_print(f"读取事件记录文件失败: {e}", log_level="ERROR")
            return {}

    @safe_execute("保存事件定义失败")
    def save_event_definitions(self, user_id: str, data: Dict[str, Any]) -> bool:
        """
        保存用户的事件定义

        Args:
            user_id: 用户ID
            data: 要保存的数据

        Returns:
            bool: 保存是否成功
        """
        file_path = self._get_event_definitions_file_path(user_id)

        # 更新最后修改时间
        if "last_updated" not in data:
            data["last_updated"] = self._get_formatted_time()

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            debug_utils.log_and_print(f"保存事件定义文件失败: {e}", log_level="ERROR")
            return False

    @safe_execute("保存事件记录失败")
    def save_event_records(self, user_id: str, data: Dict[str, Any]) -> bool:
        """
        保存用户的事件记录

        Args:
            user_id: 用户ID
            data: 要保存的数据

        Returns:
            bool: 保存是否成功
        """
        file_path = self._get_event_records_file_path(user_id)

        # 更新最后修改时间
        if "last_updated" not in data:
            data["last_updated"] = self._get_formatted_time()

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            debug_utils.log_and_print(f"保存事件记录文件失败: {e}", log_level="ERROR")
            return False

    @safe_execute("获取关联开始事项失败")
    def get_related_start_events(self, user_id: str) -> List[Dict[str, Any]]:
        """
        获取可作为关联开始事项的列表

        Args:
            user_id: 用户ID

        Returns:
            List[Dict[str, Any]]: 开始事项选项列表
        """
        definitions_data = self.load_event_definitions(user_id)
        if not definitions_data:
            return []

        definitions = definitions_data.get("definitions", {})
        start_events = []

        for event_name, event_def in definitions.items():
            if event_def.get("type") == RoutineTypes.START:
                start_events.append(
                    {
                        "text": {"tag": "plain_text", "content": event_name},
                        "value": event_name,
                    }
                )

        return start_events

    def check_user_permission(self, user_id: str) -> bool:
        """
        检查用户是否有routine_record权限

        Args:
            user_id: 用户ID

        Returns:
            bool: 是否有权限
        """
        if not self.user_permission_service:
            debug_utils.log_and_print("用户权限服务不可用", log_level="WARNING")
            return False

        return self.user_permission_service.check_business_permission(
            user_id, "routine_record"
        )

    @safe_execute("检测前置指令失败")
    def detect_prefix_command(self, message_text: str) -> Optional[Tuple[str, str]]:
        """
        检测消息中的前置指令

        Args:
            message_text: 用户输入的消息文本

        Returns:
            Optional[Tuple[str, str]]: (指令类型, 事项名称) 或 None
        """
        if not message_text:
            return None

        message_text = message_text.strip()

        # 检测创建指令
        if message_text.startswith("r "):
            event_name = message_text[2:].strip()
            if event_name:
                return ("create", event_name)

        if message_text.startswith("日程 "):
            event_name = message_text[3:].strip()
            if event_name:
                return ("create", event_name)

        # 检测查询指令
        if message_text in ["rs", "查看日程"]:
            return ("query", "")

        return None

    @safe_execute("处理消息路由失败")
    def route_message(self, context, user_msg: str):
        """
        处理routine相关的消息路由

        Args:
            context: 消息上下文
            user_msg: 用户消息

        Returns:
            ProcessResult 或 None:
            - ProcessResult: 可直接返回的处理结果
            - None: 该消息不是routine相关
        """
        # 1. 检查前置指令
        command_result = self.detect_prefix_command(user_msg)
        if command_result:
            command_type, item_name = command_result
            match command_type:
                case "create":
                    debug_utils.log_and_print(
                        f"📝 {context.user_name} 触发日程创建指令：{item_name}",
                        log_level="INFO",
                    )
                    return self.process_routine_create(context.user_id, item_name)
                case "query":
                    debug_utils.log_and_print(
                        f"📋 {context.user_name} 触发日程查询指令", log_level="INFO"
                    )
                    return self.process_routine_query(context.user_id)

        return None

    @safe_execute("处理查询请求失败")
    def process_routine_query(self, user_id: str):
        """
        处理事项查询

        Args:
            user_id: 用户ID

        Returns:
            RouteResult: 路由结果，指向查询结果卡片
        """
        # 检查权限
        if not self.check_user_permission(user_id):
            return ProcessResult.error_result("您暂无使用日常事项记录功能的权限")

        query_data = self.load_event_definitions(user_id)
        # 构建路由结果，指向查询结果卡片
        route_result = RouteResult.create_route_result(
            route_type=RouteTypes.ROUTINE_QUERY_RESULTS_CARD,
            route_params={"business_data": query_data},
        )

        return route_result

    @safe_execute("处理事项创建失败")
    def process_routine_create(self, user_id: str, item_name: str):
        """
        处理事项创建或记录

        Args:
            user_id: 用户ID
            item_name: 事项名称

        Returns:
            RouteResult: 路由结果，指向对应的卡片
        """
        # 检查权限
        if not self.check_user_permission(user_id):
            return ProcessResult.error_result("您暂无使用日常事项记录功能的权限")

        # 直接使用新架构加载数据
        definitions_data = self.load_event_definitions(user_id)

        if not definitions_data:
            return ProcessResult.error_result("加载事件定义失败")

        # 检查事项是否已存在
        if item_name in definitions_data.get("definitions", {}):
            # 事项已存在，直接记录，这里要封装原始数据
            event_def = definitions_data["definitions"][item_name]
            last_record_time = definitions_data.get("last_record_time", None)
            # 并且这里要能够直接绕过前端直接对接业务——本来前端就是多一层中转和丰富信息，也就是如果这个不routeresult，而是直接到业务也应该OK。
            routine_record_data = self.build_quick_record_data(
                user_id, item_name, event_def, last_record_time
            )
            route_result = RouteResult.create_route_result(
                route_type=RouteTypes.ROUTINE_QUICK_RECORD_CARD,
                route_params={"business_data": routine_record_data},
            )
            return route_result

        # 新事项，展示事件定义卡片
        card_data = self.build_direct_record_data(user_id, item_name)
        route_result = RouteResult.create_route_result(
            route_type=RouteTypes.ROUTINE_DIRECT_RECORD_CARD,
            route_params={
                "business_data": card_data,
            },
        )
        # card_data = self.build_new_event_card_data(user_id, item_name)
        # route_result = RouteResult.create_route_result(
        #     route_type=RouteTypes.ROUTINE_NEW_EVENT_CARD,
        #     route_params={
        #         "business_data": card_data,
        #     },
        # )
        return route_result

    @safe_execute("构建新事件定义卡片数据失败")
    def build_new_event_card_data(
        self, user_id: str, initial_event_name: str = ""
    ) -> Dict[str, Any]:
        """
        构建新事件定义卡片数据

        Args:
            user_id: 用户ID
            initial_event_name: 初始事项名称
            operation_id: 操作ID

        Returns:
            Dict[str, Any]: 卡片数据
        """
        return {
            "user_id": user_id,
            "initial_event_name": initial_event_name,
            "form_data": {
                "event_name": initial_event_name,
                "event_type": RoutineTypes.INSTANT,
                "category": "",
                "include_in_daily_check": False,
                "degree_options": "",
                "notes": "",
            },
        }

    @safe_execute("构建快速记录确认卡片数据失败")
    def build_quick_record_data(
        self,
        user_id: str,
        event_name: str,
        event_def: Dict[str, Any],
        last_record_time: str = None,
    ) -> Dict[str, Any]:
        """
        构建快速记录确认卡片数据

        Args:
            user_id: 用户ID
            event_name: 事项名称

        Returns:
            Dict[str, Any]: 卡片数据
        """
        # 获取事件定义
        # 这里的核心目的是提供必要的原始信息，解析和结构要给到前端，前端只是一个额外确认和补充，这里就是要准备好完备数据了。
        new_record = self._create_event_record(event_name, user_id)

        avg_duration = self._calculate_average_duration(user_id, event_name)
        has_degrees = event_def.get("properties", {}).get("has_degrees", False)
        if has_degrees:
            degree_info = {
                "degree_options": event_def.get("properties", {}).get(
                    "degree_options", []
                ),
                "default_degree": event_def.get("properties", {}).get(
                    "default_degree", ""
                ),
            }
        else:
            degree_info = {}

        # 这里的顺序要改一下，首先是累计值和重置，然后是有没有目标。
        check_cycle = event_def.get("properties", {}).get("check_cycle", None)
        if check_cycle:
            cycle_count = event_def.get("stats", {}).get("cycle_count", 0)
            last_refresh_date = event_def.get("stats", {}).get(
                "last_refresh_date", None
            )

            # 统一分析周期状态
            cycle_status = self._analyze_cycle_status(last_refresh_date, check_cycle)

            if cycle_status["need_refresh"]:
                last_cycle_count = cycle_count
                last_refresh_date = self._get_formatted_time()
                cycle_count = 0
            else:
                last_cycle_count = event_def.get("stats", {}).get("last_cycle_count", 0)

            target_type = event_def.get("properties", {}).get(
                "target_type", None
            )  # 决定了是不是要输入值，所以要保留的。
            target_value = event_def.get("properties", {}).get("target_value", 0)

            if target_type:
                last_cycle_info = f'{cycle_status["description"]}的情况：{last_cycle_count}/{target_value}'
            else:
                last_cycle_info = (
                    f'{cycle_status["description"]}的情况：{last_cycle_count}'
                )

            cycle_info = {
                "cycle_count": cycle_count,
                "last_cycle_count": last_cycle_count,
                "target_type": target_type,
                "target_value": target_value,
                "last_cycle_info": last_cycle_info,
                "last_refresh_date": last_refresh_date,
            }
        else:
            cycle_info = {}

        if last_record_time:
            last_record_time = datetime.strptime(last_record_time, "%Y-%m-%d %H:%M:%S")
            diff_minutes = round(
                (datetime.now() - last_record_time).total_seconds() / 60, 1
            )
        else:
            diff_minutes = 0

        return {
            "user_id": user_id,
            "event_name": event_name,
            "event_definition": event_def,  # 这里有一个问题是 definition里已经包含了上面处理的信息，只是没计算。所以最好这里传出去的都是处理好的原始信息？ 留给AI判断
            "new_record": new_record,
            "avg_duration": avg_duration,
            "degree_info": degree_info,
            "cycle_info": cycle_info,
            "diff_minutes": diff_minutes,
        }

    def _calculate_average_duration(self, user_id: str, event_name: str) -> float:
        """
        计算事项的平均耗时
        """
        definitions_data = self.load_event_definitions(user_id)
        event_duration_records = (
            definitions_data.get("definitions", {})
            .get(event_name, {})
            .get("stats", {})
            .get("duration", {})
            .get("recent_values", [])
        )
        if not event_duration_records:
            return 0.0
        avg_duration = round(
            sum(event_duration_records) / len(event_duration_records), 1
        )
        return avg_duration

    def _analyze_cycle_status(
        self, last_refresh_date: str, check_cycle: str
    ) -> Dict[str, Any]:
        """
        分析周期状态，统一处理周期相关的所有计算

        Args:
            last_refresh_date: 上次刷新时间
            check_cycle: 检查周期

        Returns:
            Dict[str, Any]: 包含以下字段的字典
                - need_refresh: bool - 是否需要刷新
                - cycle_gap: int - 跨越的周期数量
                - description: str - 周期描述
        """
        if not check_cycle:
            return {"need_refresh": False, "cycle_gap": 0, "description": ""}

        if not last_refresh_date:
            return {
                "need_refresh": True,
                "cycle_gap": 0,
                "description": f"前一{check_cycle}",
            }

        last_refresh = datetime.strptime(last_refresh_date, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()

        # 统一计算周期差异
        cycle_gap = 0
        need_refresh = False

        match check_cycle:
            case RoutineCheckCycle.DAILY:
                days_diff = (now.date() - last_refresh.date()).days
                cycle_gap = max(0, days_diff)
                need_refresh = days_diff > 0
            case RoutineCheckCycle.WEEKLY:
                last_week = last_refresh.isocalendar()[1]
                current_week = now.isocalendar()[1]
                last_year = last_refresh.year
                current_year = now.year

                if current_year == last_year:
                    cycle_gap = max(0, current_week - last_week)
                else:
                    # 跨年计算
                    weeks_in_last_year = 52 if last_year % 4 != 0 else 53
                    cycle_gap = max(
                        0, (current_week - 1) + (weeks_in_last_year - last_week)
                    )
                need_refresh = cycle_gap > 0
            case RoutineCheckCycle.MONTHLY:
                months_diff = (current_year - last_year) * 12 + (
                    now.month - last_refresh.month
                )
                cycle_gap = max(0, months_diff)
                need_refresh = cycle_gap > 0
            case RoutineCheckCycle.SEASONALLY:
                last_season = (last_refresh.month - 1) // 3
                current_season = (now.month - 1) // 3
                seasons_diff = (current_year - last_year) * 4 + (
                    current_season - last_season
                )
                cycle_gap = max(0, seasons_diff)
                need_refresh = cycle_gap > 0
            case RoutineCheckCycle.YEARLY:
                cycle_gap = max(0, current_year - last_year)
                need_refresh = cycle_gap > 0
            case _:
                raise ValueError(f"不支持的 check_cycle: {check_cycle}")
        # 生成描述
        gap_description = "前一" if cycle_gap <= 1 else f"前{cycle_gap}"

        match check_cycle:
            case RoutineCheckCycle.DAILY:
                description = f"{gap_description}天"
            case RoutineCheckCycle.WEEKLY:
                description = f"{gap_description}周"
            case RoutineCheckCycle.MONTHLY:
                description = f"{gap_description}个月"
            case RoutineCheckCycle.SEASONALLY:
                description = f"{gap_description}个季度"
            case RoutineCheckCycle.YEARLY:
                description = f"{gap_description}年"
            case _:
                description = f"{gap_description}个{check_cycle}"

        return {
            "need_refresh": need_refresh,
            "cycle_gap": cycle_gap,
            "description": description,
        }

    @safe_execute("处理快速记录菜单路由失败")
    def quick_record_menu_route_choice(self, user_id: str):
        """
        处理快速记录菜单路由选择

        Args:
            user_id: 用户ID

        Returns:
            RouteResult: 路由结果，指向快速选择记录卡片
        """
        # 检查权限
        if not self.check_user_permission(user_id):
            return ProcessResult.error_result("您暂无使用日常事项记录功能的权限")

        # 构建卡片数据，支持集成模式
        menu_shortcut_data = self.build_quick_select_card_data(
            user_id=user_id,
        )

        # 构建路由结果，指向routine卡片的快速选择模式
        route_result = RouteResult.create_route_result(
            route_type=RouteTypes.ROUTINE_QUICK_SELECT_CARD,
            route_params={"business_data": menu_shortcut_data},
        )

        return route_result

    @safe_execute("构建快速选择记录卡片数据失败")
    def build_quick_select_card_data(
        self, user_id: str, max_items: int = 5
    ) -> Dict[str, Any]:
        """
        构建快速选择记录卡片数据（扩展版本：支持集成模式）

        Args:
            user_id: 用户ID
            max_items: 最大显示事件数量

        Returns:
            Dict[str, Any]: 卡片数据
        """
        # 业务数据未必都需要在这里定义，是否连续更新是前端的事，取值或者设定值，这里是业务逻辑的数据。
        definitions_data = self.load_event_definitions(user_id)
        quick_events = []
        definitions = definitions_data.get("definitions", {})

        if definitions:
            # 分离快速访问事件和最近事件
            quick_access_events = []
            recent_events = []

            for event_name, event_def in definitions.items():
                event_info = {
                    "name": event_name,
                    "type": event_def.get("type", RoutineTypes.INSTANT),
                    "properties": event_def.get("properties", {}),
                    "last_updated": event_def.get("last_updated", ""),
                    "definition": event_def,  # 保留完整定义，用于快速记录
                }

                if event_def.get("properties", {}).get("quick_access", False):
                    quick_access_events.append(event_info)
                else:
                    recent_events.append(event_info)

            # 排序并合并事件列表
            quick_access_events.sort(key=lambda x: x["last_updated"], reverse=True)
            recent_events.sort(key=lambda x: x["last_updated"], reverse=True)

            # 确保快速访问事件优先显示
            result = quick_access_events[:3]
            remaining_slots = max_items - len(result)
            if remaining_slots > 0:
                result.extend(recent_events[:remaining_slots])
            quick_events = result

        # 构建基础卡片数据
        quick_select_data = {"user_id": user_id, "quick_events": quick_events}

        return quick_select_data

    @safe_execute("处理事件创建业务逻辑失败")
    def create_new_event_from_form(
        self, user_id: str, form_data: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        根据表单数据创建新事件

        Args:
            user_id: 用户ID
            form_data: 表单数据

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        try:
            # 验证必填字段
            event_name = form_data.get("event_name", "").strip()
            if not event_name:
                return False, "事项名称不能为空"

            event_type = form_data.get("event_type", RoutineTypes.INSTANT)
            if not isinstance(event_type, RoutineTypes):
                return False, "无效的事项类型"

            # 加载数据
            definitions_data = self.load_event_definitions(user_id)
            if event_name in definitions_data.get("definitions", {}):
                return False, f"事项 '{event_name}' 已存在"

            # 创建事件定义
            new_event_def = self._create_event_definition(event_name, event_type)

            # 更新属性
            new_event_def["category"] = form_data.get("category", "")
            new_event_def["description"] = form_data.get("notes", "")

            # 根据事项类型设置特定属性
            properties = new_event_def["properties"]

            if event_type == RoutineTypes.END:
                properties["related_start_event"] = form_data.get("related_start_event")

            if event_type in [RoutineTypes.INSTANT, RoutineTypes.ONGOING]:
                properties["include_in_daily_check"] = form_data.get(
                    "include_in_daily_check", False
                )

            if event_type == RoutineTypes.FUTURE:
                properties["future_date"] = form_data.get("future_date")

            if event_type != RoutineTypes.FUTURE:
                # 处理程度选项
                degree_options_str = form_data.get("degree_options", "").strip()
                if degree_options_str:
                    degree_options = [
                        opt.strip()
                        for opt in degree_options_str.split(",")
                        if opt.strip()
                    ]
                    properties["has_degrees"] = len(degree_options) > 0
                    properties["degree_options"] = degree_options
                    if degree_options:
                        properties["default_degree"] = degree_options[0]

            # 保存数据
            definitions_data["definitions"][event_name] = new_event_def
            if self.save_event_definitions(user_id, definitions_data):
                return True, f"成功创建事项 '{event_name}'"

            return False, "保存事项失败"

        except Exception as e:
            debug_utils.log_and_print(f"创建事项失败: {e}", log_level="ERROR")
            return False, f"创建事项失败: {str(e)}"

    @safe_execute("处理记录创建业务逻辑失败")
    def create_record_from_form(
        self, user_id: str, event_name: str, form_data: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        根据表单数据创建新记录

        Args:
            user_id: 用户ID
            event_name: 事项名称
            form_data: 表单数据

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        try:
            # 加载数据
            definitions_data = self.load_event_definitions(user_id)
            records_data = self.load_event_records(user_id)

            if event_name not in definitions_data.get("definitions", {}):
                return False, f"事项 '{event_name}' 不存在"

            # 创建新记录
            current_time = self._get_formatted_time()
            new_record = self._create_event_record(
                event_name=event_name,
                user_id=user_id,
                degree=form_data.get("custom_degree", ""),
                note=form_data.get("record_note", ""),
            )

            # 添加记录
            records_data["records"].append(new_record)

            # 更新事件定义的统计信息
            event_def = definitions_data["definitions"][event_name]
            event_def["record_count"] = event_def.get("record_count", 0) + 1
            event_def["last_updated"] = current_time

            # 保存数据
            if self.save_event_definitions(
                user_id, definitions_data
            ) and self.save_event_records(user_id, records_data):
                return True, f"成功记录 '{event_name}' - {current_time[11:16]}"

            return False, "保存记录失败"

        except Exception as e:
            debug_utils.log_and_print(f"创建记录失败: {e}", log_level="ERROR")
            return False, f"创建记录失败: {str(e)}"

    @safe_execute("构建直接记录卡片数据失败")
    def build_direct_record_data(self, user_id: str, event_name: str, event_type: str = RoutineTypes.INSTANT) -> Dict[str, Any]:
        """
        构建直接记录卡片数据

        Args:
            user_id: 用户ID
            event_name: 事件名称
            event_type: 事件类型，默认为瞬间完成

        Returns:
            Dict[str, Any]: 直接记录卡片数据
        """
        current_time = self._get_formatted_time()

        # 构建初始表单数据
        form_data = {
            "progress_type": RoutineProgressTypes.NONE,
            "reminder_mode": "off",
            "duration": "",
            "note": "",
            "degree": "",
            "progress_value": "",
            "planned_date": "",
            "planned_time": "",
            "priority": "medium",
            "estimated_duration": "",
            "reminder_time": "start",
            "reminder_cycle": [],
            "check_cycle": "",
            "target_type": RoutineTargetTypes.NONE,
            "target_value": ""
        }

        return {
            "user_id": user_id,
            "event_name": event_name,
            "event_type": event_type,
            "form_data": form_data,
            "is_confirmed": False,
            "created_time": current_time
        }

    @safe_execute("创建直接记录失败")
    def create_direct_record(self, user_id: str, form_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        创建并保存直接记录到 event_records.json

        Args:
            user_id: 用户ID
            form_data: 表单数据

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        try:
            # 验证数据
            is_valid, error_msg = self._validate_direct_record_data(form_data)
            if not is_valid:
                return False, error_msg

            # 加载记录数据
            records_data = self.load_event_records(user_id)
            if not records_data:
                return False, "加载记录数据失败"

            # 生成记录ID
            event_name = form_data.get("event_name", "").strip()
            record_id = self._generate_direct_record_id(user_id, event_name)

            # 构建记录数据
            current_time = self._get_formatted_time()
            event_type = form_data.get("event_type", RoutineTypes.INSTANT)

            # 基础记录结构
            new_record = {
                "record_id": record_id,
                "event_name": event_name,
                "event_type": event_type,
                "timestamp": current_time,
                "completion_time": current_time,

                # 公共字段
                "note": form_data.get("note", ""),
                "degree": form_data.get("degree", ""),
                "duration": self._safe_parse_number(form_data.get("duration", "")),

                # 指标相关
                "progress_type": form_data.get("progress_type", RoutineProgressTypes.NONE),
                "progress_value": self._safe_parse_number(form_data.get("progress_value", "")),

                # 元数据字段
                "has_definition": False,
                "created_from": "direct_input"
            }

            # 根据事件类型添加特定字段
            if event_type == RoutineTypes.ONGOING:
                new_record.update({
                    "check_cycle": form_data.get("check_cycle", ""),
                    "target_type": form_data.get("target_type", RoutineTargetTypes.NONE),
                    "target_value": self._safe_parse_number(form_data.get("target_value", ""), as_int=True)
                })
            elif event_type == RoutineTypes.FUTURE:
                new_record.update({
                    "priority": form_data.get("priority", "medium"),
                    "planned_date": form_data.get("planned_date", ""),
                    "planned_time": form_data.get("planned_time", ""),
                    "estimated_duration": self._safe_parse_number(form_data.get("estimated_duration", "")),
                    "reminder_mode": form_data.get("reminder_mode", "off"),
                    "reminder_time": form_data.get("reminder_time", "start"),
                    "reminder_cycle": form_data.get("reminder_cycle", [])
                })

            # 根据事件类型决定存储位置
            if event_type in [RoutineTypes.START, RoutineTypes.ONGOING, RoutineTypes.FUTURE]:
                # 开始、持续、未来事项存储到 active_records
                records_data["active_records"].append(new_record)
            else:
                # 瞬间完成事项存储到 records
                records_data["records"].append(new_record)

            records_data["last_updated"] = current_time

            # 保存数据
            if self.save_event_records(user_id, records_data):
                return True, f"成功创建直接记录 '{event_name}' - {current_time[11:16]}"

            return False, "保存记录失败"

        except Exception as e:
            debug_utils.log_and_print(f"创建直接记录失败: {e}", log_level="ERROR")
            return False, f"创建直接记录失败: {str(e)}"

    def _validate_direct_record_data(self, form_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        验证直接记录数据

        Args:
            form_data: 表单数据

        Returns:
            Tuple[bool, str]: (是否有效, 错误消息)
        """
        # 基础字段验证
        event_name = form_data.get("event_name", "").strip()
        if not event_name:
            return False, "事件名称不能为空"
        if len(event_name) > 50:
            return False, "事件名称不能超过50个字符"

        event_type = form_data.get("event_type", "")
        valid_types = [RoutineTypes.INSTANT, RoutineTypes.START, RoutineTypes.ONGOING, RoutineTypes.FUTURE]
        if event_type not in valid_types:
            return False, "无效的事件类型"

        # 数值字段统一验证
        numeric_fields = {
            "duration": "耗时",
            "progress_value": "指标值",
            "estimated_duration": "预估耗时",
            "target_value": "目标值"
        }

        for field, field_name in numeric_fields.items():
            value = form_data.get(field, "")
            if value and not self._is_valid_number(value):
                return False, f"{field_name}必须是有效数字"

        # 未来事项必填验证
        if event_type == RoutineTypes.FUTURE:
            planned_date = form_data.get("planned_date", "")
            if not planned_date:
                return False, "未来事项必须设置计划日期"
            # 简单日期格式验证
            try:
                datetime.strptime(planned_date, "%Y-%m-%d")
            except ValueError:
                try:
                    datetime.strptime(planned_date, "%Y/%m/%d")
                except ValueError:
                    return False, "计划日期格式无效"

        return True, ""

    def _generate_direct_record_id(self, user_id: str, event_name: str) -> str:
        """
        生成直接记录ID，使用"事件名_001"格式

        Args:
            user_id: 用户ID
            event_name: 事件名称

        Returns:
            str: 记录ID
        """
        # 加载现有记录以计算序号
        records_data = self.load_event_records(user_id)

        # 统计所有位置的同名记录数量
        all_records = records_data.get("records", []) + records_data.get("active_records", [])
        count = sum(1 for record in all_records if record.get("event_name") == event_name)

        # 生成新的序号（从001开始）
        next_num = count + 1
        return f"{event_name}_{next_num:03d}"

    def _safe_parse_number(self, value_str: str, as_int: bool = False) -> float:
        """
        安全解析数值字符串

        Args:
            value_str: 数值字符串
            as_int: 是否返回整数

        Returns:
            float/int: 解析后的数值，失败返回0
        """
        if not value_str:
            return 0

        try:
            result = float(value_str)
            return int(result) if as_int else result
        except (ValueError, TypeError):
            return 0

    def _is_valid_number(self, value_str: str) -> bool:
        """
        检查字符串是否为有效数字

        Args:
            value_str: 待检查的字符串

        Returns:
            bool: 是否为有效数字
        """
        if not value_str:
            return True  # 空字符串视为有效（可选字段）

        try:
            float(value_str)
            return True
        except (ValueError, TypeError):
            return False
