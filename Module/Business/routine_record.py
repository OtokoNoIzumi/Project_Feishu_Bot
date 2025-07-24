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
from collections import OrderedDict

from Module.Common.scripts.common import debug_utils
from Module.Services.constants import (
    ServiceNames,
    RoutineTypes,
    RouteTypes,
    RoutineCheckCycle,
    RoutineProgressTypes,
    RoutineTargetTypes,
    RoutineRecordModes,
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
            str: 格式化时间 "2025-07-10 09:07"
        """
        return datetime.now().strftime("%Y-%m-%d %H:%M")

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
        self, event_name: str, event_type: str = RoutineTypes.INSTANT.value
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
                "degree_options": [],
                "default_degree": "",
                # 时间属性
                "future_date": None,
                # 目标属性
                "check_cycle": None,
                "custom_cycle_config": None,
                "target_type": RoutineTargetTypes.NONE.value,  # 次数/时长
                "target_value": None,  # 目标值
                # 指标属性
                "progress_type": RoutineProgressTypes.NONE.value,  # 进度类型
            },
            "stats": {
                "record_count": 0,
                "cycle_count": 0,
                "last_cycle_count": 0,
                "duration": {
                    "recent_values": [],  # 最近N次的耗时值
                    "window_size": 10,  # 滑动窗口大小
                    "duration_count": 0,  # 有耗时记录的次数
                    "avg_all_time": 0,  # 历史平均耗时
                },
                "last_refresh_date": None,
                "last_record_id": None,
            },
            "created_time": current_time,
            "last_record_time": None,
            "last_updated": current_time,
        }

    def _get_next_record_id(self, user_id: str, event_name: str) -> str:
        """
        生成下一个记录ID，基于事件定义中的record_count统计
        高效且可靠的ID生成方法

        Args:
            user_id: 用户ID
            event_name: 事件名称

        Returns:
            str: 记录ID，格式为 event_name_00001
        """
        # 优先使用事件定义中的统计信息
        definitions_data = self.load_event_definitions(user_id)
        definitions = definitions_data.get("definitions", {})

        if event_name in definitions:
            # 事件定义存在，使用record_count生成ID
            current_count = (
                definitions[event_name].get("stats", {}).get("record_count", 0)
            )
            next_num = current_count + 1
            candidate_id = f"{event_name}_{next_num:05d}"

            # 验证ID唯一性（防御性编程）
            if self._verify_id_uniqueness(user_id, candidate_id):
                return candidate_id
            else:
                # 如果统计不准确，回退到扫描方式并修复统计
                return self._generate_id_with_scan_and_fix(user_id, event_name)
        else:
            # 事件定义不存在，扫描现有记录生成ID
            return self._generate_id_with_scan(user_id, event_name)

    def _verify_id_uniqueness(self, user_id: str, candidate_id: str) -> bool:
        """
        验证ID在所有记录中的唯一性

        Args:
            user_id: 用户ID
            candidate_id: 候选ID

        Returns:
            bool: ID是否唯一
        """
        records_data = self.load_event_records(user_id)

        # 检查records中是否存在
        if candidate_id in records_data.get("records", {}):
            return False

        # 检查active_records中是否存在
        if candidate_id in records_data.get("active_records", {}):
            return False

        return True

    def _generate_id_with_scan(self, user_id: str, event_name: str) -> str:
        """
        通过扫描现有记录生成ID（用于事件定义不存在的情况）

        Args:
            user_id: 用户ID
            event_name: 事件名称

        Returns:
            str: 记录ID
        """
        records_data = self.load_event_records(user_id)
        existing_ids = set()

        # 收集同名事件的所有ID
        for record_dict in [
            records_data.get("records", {}),
            records_data.get("active_records", {}),
        ]:
            for record_id, record in record_dict.items():
                if record.get("event_name") == event_name:
                    existing_ids.add(record_id)

        # 找到下一个可用序号
        next_num = 1
        while True:
            candidate_id = f"{event_name}_{next_num:05d}"
            if candidate_id not in existing_ids:
                return candidate_id
            next_num += 1

            if next_num > 99999:
                raise ValueError(f"无法为事件 '{event_name}' 生成唯一ID")

    def _generate_id_with_scan_and_fix(self, user_id: str, event_name: str) -> str:
        """
        扫描生成ID并修复事件定义中的统计信息

        Args:
            user_id: 用户ID
            event_name: 事件名称

        Returns:
            str: 记录ID
        """
        # 先用扫描方式生成ID
        new_id = self._generate_id_with_scan(user_id, event_name)

        # 修复事件定义中的record_count
        definitions_data = self.load_event_definitions(user_id)
        if event_name in definitions_data.get("definitions", {}):
            # 计算实际记录数量
            actual_count = self._count_records_for_event(user_id, event_name)
            definitions_data["definitions"][event_name]["stats"][
                "record_count"
            ] = actual_count
            self.save_event_definitions(user_id, definitions_data)

        return new_id

    def _count_records_for_event(self, user_id: str, event_name: str) -> int:
        """
        统计指定事件的实际记录数量

        Args:
            user_id: 用户ID
            event_name: 事件名称

        Returns:
            int: 记录数量
        """
        records_data = self.load_event_records(user_id)
        count = 0

        # 统计records中的记录
        for record in records_data.get("records", {}).values():
            if record.get("event_name") == event_name:
                count += 1

        # 统计active_records中的记录
        for record in records_data.get("active_records", {}).values():
            if record.get("event_name") == event_name:
                count += 1

        return count

    def _create_event_record(
        self,
        event_name: str,
        user_id: str,
        record_mode: str,
    ) -> Dict[str, Any]:
        """
        创建事件记录

        Args:
            event_name: 事件名称
            user_id: 用户ID
            record_mode: 记录模式
        Returns:
            Dict[str, Any]: 事件记录
        """
        current_time = self._get_formatted_time()
        match record_mode:
            case RoutineRecordModes.ADD:
                record_id = ""
            case RoutineRecordModes.RECORD:
                record_id = self._get_next_record_id(user_id, event_name)

        return {
            "record_id": record_id,
            "event_name": event_name,
            "create_time": current_time,
        }

    @safe_execute("读取事件定义文件失败")
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

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data

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
                "active_records": OrderedDict(),
                "records": OrderedDict(),
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
            if event_def.get("type") == RoutineTypes.START.value:
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
        # 三明治结构：权限-核心数据-路由
        if not self.check_user_permission(user_id):
            return ProcessResult.error_result("您暂无使用日常事项记录功能的权限")

        routine_business_data = self.build_record_business_data(user_id, item_name)

        route_result = RouteResult.create_route_result(
            route_type=RouteTypes.ROUTINE_RECORD_CARD,
            route_params={
                "business_data": routine_business_data,
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
                "event_type": RoutineTypes.INSTANT.value,
                "category": "",
                "include_in_daily_check": False,
                "degree_options": "",
                "notes": "",
            },
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

    def _calculate_total_duration(self, user_id: str, event_name: str) -> float:
        """
        计算事项的平均耗时
        """
        definitions_data = self.load_event_definitions(user_id)
        event_duration_info = (
            definitions_data.get("definitions", {})
            .get(event_name, {})
            .get("stats", {})
            .get("duration", {})
        )
        duration_count = event_duration_info.get("duration_count", 0)
        avg_duration = event_duration_info.get("avg_all_time", 0)
        return round(avg_duration*duration_count,1)

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

        last_refresh = datetime.strptime(last_refresh_date, "%Y-%m-%d %H:%M")
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
                    "type": event_def.get("type", RoutineTypes.INSTANT.value),
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

            event_type = form_data.get("event_type", RoutineTypes.INSTANT.value)
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

            if event_type == RoutineTypes.END.value:
                properties["related_start_event"] = form_data.get("related_start_event")

            if event_type in [RoutineTypes.INSTANT.value, RoutineTypes.ONGOING.value]:
                properties["include_in_daily_check"] = form_data.get(
                    "include_in_daily_check", False
                )

            if event_type == RoutineTypes.FUTURE.value:
                properties["future_date"] = form_data.get("future_date")

            if event_type != RoutineTypes.FUTURE.value:
                # 处理程度选项
                degree_options_str = form_data.get("degree_options", "").strip()
                if degree_options_str:
                    degree_options = [
                        opt.strip()
                        for opt in degree_options_str.split(",")
                        if opt.strip()
                    ]
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

    @safe_execute("构建日程记录卡片数据失败")
    def build_record_business_data(
        self,
        user_id: str,
        event_name: str,
        record_mode: str = "",
    ) -> Dict[str, Any]:
        """
        构建日程记录卡片数据
        不做权限校验，就是生产数据
        """
        definitions_data = self.load_event_definitions(user_id)
        last_record_time = definitions_data.get("last_record_time", None)
        event_definition = definitions_data["definitions"].get(event_name, {})

        # query/record/add
        record_mode = record_mode or (RoutineRecordModes.RECORD if event_definition else RoutineRecordModes.ADD)

        # 基础数据
        business_data = {
            "record_mode": record_mode,
            "user_id": user_id,
            "event_name": event_name,
        }

        # 公共的计算可以放在外面
        computed_data = {}
        # 计算时间差
        if last_record_time:
            last_time = datetime.strptime(
                last_record_time, "%Y-%m-%d %H:%M"
            )
            diff_minutes = round(
                (datetime.now() - last_time).total_seconds() / 60, 1
            )
            computed_data["diff_minutes"] = diff_minutes

        new_record_data = self._create_event_record(event_name, user_id, record_mode)
        match record_mode:
            case RoutineRecordModes.ADD:
                event_definition["type"] = RoutineTypes.INSTANT.value

            case RoutineRecordModes.RECORD:
                last_record_id = event_definition.get("stats", {}).get("last_record_id", "")
                if last_record_id:
                    event_records = self.load_event_records(user_id)
                    last_record_data = event_records.get("records", {}).get(last_record_id)
                    if not last_record_data:
                        last_record_data = event_records.get("active_records", {}).get(last_record_id, {})
                    business_data["last_record_data"] = last_record_data

                avg_duration = self._calculate_average_duration(user_id, event_name)
                if avg_duration > 0:
                    computed_data["avg_duration"] = avg_duration

                target_type = event_definition.get("properties", {}).get(
                    "target_type", ""
                )

                match target_type:
                    case RoutineTargetTypes.COUNT.value:
                        target_progress_value = event_definition.get("stats", {}).get(
                            "record_count", 0
                        )
                    case RoutineTargetTypes.TIME.value:
                        target_progress_value = self._calculate_total_duration(user_id, event_name)
                    case _:
                        target_progress_value = 0
                computed_data["total_target_progress_value"] = target_progress_value

                # 计算周期信息
                check_cycle = event_definition.get("properties", {}).get(
                    "check_cycle", None
                )

                if check_cycle:
                    cycle_count = event_definition.get("stats", {}).get(
                        "cycle_count", 0
                    )
                    last_refresh_date = event_definition.get("stats", {}).get(
                        "last_refresh_date", None
                    )

                    # 统一分析周期状态
                    cycle_status = self._analyze_cycle_status(
                        last_refresh_date, check_cycle
                    )
                    if cycle_status["need_refresh"]:
                        last_cycle_count = cycle_count
                        last_refresh_date = self._get_formatted_time()
                        cycle_count = 0
                    else:
                        last_cycle_count = event_definition.get("stats", {}).get(
                            "last_cycle_count", 0
                        )

                    cycle_info = {
                        "cycle_count": cycle_count,
                        "last_cycle_count": last_cycle_count,
                        "last_cycle_description": cycle_status["description"],
                        "last_refresh_date": last_refresh_date,
                    }
                    computed_data["cycle_info"] = cycle_info


        business_data["event_definition"] = event_definition
        business_data["record_data"] = new_record_data
        business_data["computed_data"] = computed_data

        return business_data

    @safe_execute("创建直接记录失败")
    def create_direct_record(
        self, user_id: str, dup_business_data: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        创建并保存直接记录到 event_records.json
        对于非 future 类型的事项，同时创建事件定义

        Args:
            user_id: 用户ID
            record_data: 表单数据

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        # 验证数据
        record_data = dup_business_data.get("record_data", {})
        event_definition = dup_business_data.get("event_definition", {})

        # 生成记录ID
        event_name = record_data.get("event_name", "").strip()

        # 构建记录数据
        current_time = self._get_formatted_time()
        event_type = event_definition.get("type", RoutineTypes.INSTANT.value)

        # 构建记录数据，过滤空值和冗余字段
        new_record = {}

        # 复制有效的表单数据（过滤空值）
        for key, value in record_data.items():
            if value is not None and value != "":
                new_record[key] = value

        # 添加系统字段
        if "record_id" not in new_record:
            record_id = self._get_next_record_id(user_id, event_name)
            new_record["record_id"] = record_id
        else:
            record_id = new_record.get("record_id", "")

        if event_type == RoutineTypes.INSTANT.value:
            new_record["end_time"] = current_time

        # 针对不同事件类型的特殊处理
        if event_type == RoutineTypes.FUTURE.value:
            # 未来事项：移除duration，使用estimated_duration
            if "duration" in new_record:
                duration_value = new_record.pop("duration")  # 移除duration
                if duration_value:  # 只有非空值才设置
                    new_record["estimated_duration"] = duration_value
            # 未来事项不需要has_definition字段

        # 对于非 future 类型的事项，创建事件定义
        if event_type != RoutineTypes.FUTURE.value:
            self._update_event_definition(
                user_id, event_name, dup_business_data, record_id
            )

        # 加载记录数据
        records_data = self.load_event_records(user_id)
        # 根据事件类型决定存储位置
        if event_type in [
            RoutineTypes.START.value,
            RoutineTypes.ONGOING.value,
            RoutineTypes.FUTURE.value,
        ]:
            # 开始、持续、未来事项存储到 active_records
            new_record_field = "active_records"
        else:
            # 其他类型记录添加到records
            new_record_field = "records"

        new_records = OrderedDict()
        new_records[record_id] = new_record
        new_records.update(records_data[new_record_field])
        records_data[new_record_field] = new_records

        records_data["last_updated"] = current_time

        # 保存数据
        if self.save_event_records(user_id, records_data):
            return True, "成功创建记录"

        return False, "保存记录失败"

    def _update_event_definition(
        self,
        user_id: str,
        event_name: str,
        dup_business_data: Dict[str, Any],
        record_id: str,
    ) -> bool:
        """
        从直接记录的business_data创建事件定义

        Args:
            user_id: 用户ID
            event_name: 事件名称
            dup_business_data: 完整business_data数据
            record_id: 记录ID

        Returns:
            bool: 是否成功创建事件定义
        """
        # 加载现有事件定义
        # 逻辑上分成两部分，非stats的，和stats的。
        # 对于properties的，是原子操作，且兼容后续编辑event_definition，直接更新。
        # 对于stats的，是复合操作，从配置里加载，计算，再更新。
        event_definitions = self.load_event_definitions(user_id)
        event_definition = dup_business_data.get("event_definition", {})
        event_type = event_definition.get("type", RoutineTypes.INSTANT.value)
        computed_data = dup_business_data.get("computed_data", {})
        cycle_info = computed_data.get("cycle_info", {})

        record_data = dup_business_data.get("record_data", {})
        target_type = dup_business_data.get("computed_data", {}).get("target_info", {}).get("target_type", "")

        current_time = self._get_formatted_time()

        # 检查事件定义是否已存在
        if event_name in event_definitions.get("definitions", {}):
            # 事件定义已存在
            # 目前这里的效果是更新degree_options，其他是后续功能自动支持。
            existing_def = event_definitions["definitions"][event_name]
            existing_def["properties"] = event_definition.get("properties", {})

            # stats
            existing_def_stats = event_definitions["definitions"][event_name].get("stats", {})

            existing_def_stats["record_count"] = (
                existing_def_stats.get("record_count", 0) + 1
            )

            # 更新耗时统计
            duration = self._safe_parse_number(record_data.get("duration"))
            if duration > 0:
                self._update_duration_stats(existing_def_stats, duration)

            # 更新周期统计信息（如果存在）
            if cycle_info:
                # 在创建事件是包含了预刷新检测，所以要用computed_data里的cycle_info
                if target_type == RoutineTargetTypes.TIME.value:
                    existing_def_stats["cycle_count"] = cycle_info.get("cycle_count", 0) + duration
                else:
                    existing_def_stats["cycle_count"] = cycle_info.get("cycle_count", 0) + 1

                existing_def_stats["last_cycle_count"] = cycle_info.get(
                    "last_cycle_count", 0
                )
                existing_def_stats["last_refresh_date"] = cycle_info.get(
                    "last_refresh_date", ""
                )

            existing_def_stats["last_record_id"] = record_id

            # 更新指标统计
            progress_type = event_definition.get("properties", {}).get("progress_type")
            if progress_type and progress_type != RoutineProgressTypes.NONE.value:
                progress_value = self._safe_parse_number(
                    record_data.get("progress_value")
                )
                self._update_progress_stats(existing_def_stats, progress_type, progress_value)

            existing_def["last_record_time"] = current_time
            existing_def["last_updated"] = current_time

        else:
            # 创建新的事件定义
            new_definition = self._create_event_definition(event_name, event_type)

            # 从表单数据中提取并设置属性
            self._populate_definition_from_business_data(
                new_definition, dup_business_data, current_time
            )

            new_definition["last_record_id"] = record_id
            # 添加到定义集合中
            event_definitions["definitions"][event_name] = new_definition

        # 更新全局时间戳
        event_definitions["last_updated"] = current_time
        event_definitions["last_record_time"] = current_time

        # 保存事件定义
        return self.save_event_definitions(user_id, event_definitions)

    def _populate_definition_from_business_data(
        self, definition: Dict[str, Any], dup_business_data: Dict[str, Any], current_time: str
    ) -> None:
        """
        从表单数据填充事件定义的属性

        Args:
            definition: 事件定义字典
            record_data: 表单数据
            current_time: 当前时间
        """
        event_definition = dup_business_data.get("event_definition", {})
        properties = definition["properties"].update(event_definition.get("properties", {}))

        stats = definition["stats"]
        record_data = dup_business_data.get("record_data", {})

        # 设置程度选项
        degree = record_data.get("degree")
        if degree:
            if degree not in properties["degree_options"]:
                properties["degree_options"].append(degree)

        # 更新统计信息
        stats["record_count"] = 1

        definition["last_record_time"] = current_time

        # 设置耗时统计（数据已在卡片层格式化）
        duration = record_data.get("duration")
        if duration and duration > 0:
            self._update_duration_stats(stats, duration)

        # 设置指标统计（数据已在卡片层格式化）
        progress_type = event_definition.get("properties", {}).get("progress_type")
        if progress_type and progress_type != RoutineProgressTypes.NONE.value:
            progress_value = record_data.get("progress_value")
            if progress_value is not None:
                self._update_progress_stats(stats, progress_type, progress_value)

    def _update_duration_stats(
        self, stats: Dict[str, Any], duration: float
    ) -> None:
        """
        更新事件定义的耗时统计

        Args:
            stats: 事件定义
            duration: 新的耗时值
        """
        duration_info = stats["duration"]
        recent_values = duration_info.get("recent_values", [])

        # 添加新的耗时值
        recent_values.append(duration)
        window_size = duration_info.get("window_size", 10)
        if len(recent_values) > window_size:
            recent_values.pop(0)

        # 更新计数和平均值
        duration_count = duration_info.get("duration_count", 0) + 1
        duration_info["duration_count"] = duration_count

        # 计算新的平均值
        try:
            old_avg = duration_info.get("avg_all_time", 0) or 0
            old_count = duration_count - 1
            total_duration = old_avg * old_count + duration
            duration_info["avg_all_time"] = total_duration / duration_count
        except (TypeError, ZeroDivisionError):
            duration_info["avg_all_time"] = duration

    def _update_progress_stats(
        self, stats: Dict[str, Any], progress_type: str, progress_value: float
    ) -> None:
        """
        更新事件定义的指标统计

        Args:
            stats: 事件定义
            progress_type: 指标类型
            progress_value: 指标值
        """
        # 目前只有modify，value的last_progress_value已经转移到last_record_id的逻辑里
        if progress_type == RoutineProgressTypes.MODIFY.value and progress_value != 0:
            current_total = stats.get("total_progress_value", 0) or 0
            stats["total_progress_value"] = round(current_total + progress_value, 3)

    def _safe_parse_number(self, value, as_int: bool = False) -> float:
        """
        安全解析数值

        Args:
            value: 数值字符串或数值
            as_int: 是否返回整数

        Returns:
            float/int: 解析后的数值，失败返回0
        """
        if value is None or value == "":
            return 0

        try:
            result = float(value)
            return int(result) if as_int else result
        except (ValueError, TypeError):
            return 0

    def _is_valid_number(self, value) -> bool:
        """
        检查值是否为有效数字

        Args:
            value: 待检查的值

        Returns:
            bool: 是否为有效数字
        """
        if value is None or value == "":
            return True  # 空值视为有效（可选字段）

        try:
            float(value)
            return True
        except (ValueError, TypeError):
            return False

    # region 辅助方法
