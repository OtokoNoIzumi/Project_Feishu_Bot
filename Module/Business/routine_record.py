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
import copy
import math
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from collections import OrderedDict


from Module.Common.scripts.common import debug_utils
from Module.Business.shared_process import (
    hex_to_hsl,
    safe_parse_number,
    hsl_to_hex,
)
from Module.Services.constants import (
    ServiceNames,
    RoutineTypes,
    RouteTypes,
    RoutineCheckCycle,
    RoutineProgressTypes,
    RoutineTargetTypes,
    RoutineRecordModes,
    ColorTypes,
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

    def load_events(self, user_data_path, user_id):
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

    def __init__(self, app_controller, developer_mode_path=None):
        """初始化日常事项记录业务"""
        super().__init__(app_controller)
        self.developer_mode_path = developer_mode_path
        if not self.developer_mode_path:
            self.config_service = self.app_controller.get_service(ServiceNames.CONFIG)
            self.user_permission_service = self.app_controller.get_service(
                ServiceNames.USER_BUSINESS_PERMISSION
            )
        self.storage = JSONEventStorage()

    # region Route和入口

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

    # endregion

    # region 用户相关方法
    def check_user_permission(self, user_id: str) -> bool:
        """
        检查用户是否有routine_record权限

        Args:
            user_id: 用户ID

        Returns:
            bool: 是否有权限
        """
        if self.developer_mode_path:
            return True

        if not self.user_permission_service:
            debug_utils.log_and_print("用户权限服务不可用", log_level="WARNING")
            return False

        return self.user_permission_service.check_business_permission(
            user_id, "routine_record"
        )

    def _get_user_data_path(self, user_id: str) -> str:
        """
        获取用户数据存储路径

        Args:
            user_id: 用户ID

        Returns:
            str: 用户数据文件夹路径
        """
        if self.developer_mode_path:
            return f"{self.developer_mode_path}/user_data/{user_id}"

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

    # endregion

    # region 定义和数据结构
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
            case RoutineRecordModes.ADD | RoutineRecordModes.QUERY:
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

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data

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

    # endregion

    # region record_id相关

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

                # 如果统计不准确，回退到扫描方式并修复统计
                return self._generate_id_with_scan_and_fix(user_id, event_name)

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

    # endregion

    # region 事项创建或记录

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
        return route_result

    @safe_execute("构建日程记录卡片数据失败")
    def build_record_business_data(
        self,
        user_id: str,
        event_name: str,
        record_mode: str = "",
        current_record_data: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        构建日程记录卡片数据
        不做权限校验，就是生产数据
        """
        definitions_data = self.load_event_definitions(user_id)
        event_definition = definitions_data["definitions"].get(event_name, {})

        # query/record/add
        record_mode = record_mode or (
            RoutineRecordModes.RECORD if event_definition else RoutineRecordModes.ADD
        )

        # 基础数据
        business_data = {
            "record_mode": record_mode,
            "user_id": user_id,
            "event_name": event_name,
        }

        if record_mode == RoutineRecordModes.QUERY and current_record_data:
            # 因为数据缓存和操作的间隔，需要深拷贝，防止操作时污染数据
            new_record_data = copy.deepcopy(current_record_data)
            last_record_time = new_record_data.get("create_time", None)
        else:
            new_record_data = self._create_event_record(
                event_name, user_id, record_mode
            )
            last_record_time = event_definition.get("last_record_time", None)

        # 公共的计算可以放在外面
        computed_data = {}
        # 计算时间差
        if last_record_time:
            last_time = datetime.strptime(last_record_time, "%Y-%m-%d %H:%M")
            diff_minutes = round((datetime.now() - last_time).total_seconds() / 60, 1)
            computed_data["diff_minutes"] = diff_minutes

        match record_mode:
            case RoutineRecordModes.ADD:
                event_definition["type"] = RoutineTypes.INSTANT.value

            case RoutineRecordModes.RECORD | RoutineRecordModes.QUERY:
                last_record_id = event_definition.get("stats", {}).get(
                    "last_record_id", ""
                )
                if last_record_id:
                    event_records = self.load_event_records(user_id)
                    last_record_data = event_records.get("records", {}).get(
                        last_record_id
                    )
                    if not last_record_data:
                        last_record_data = event_records.get("active_records", {}).get(
                            last_record_id, {}
                        )
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
                        target_progress_value = self._calculate_total_duration(
                            user_id, event_name
                        )
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

        # 构建分类选项
        categories_data = definitions_data.get("categories", [])
        category_names = set()

        # 从分类数据中收集分类名称
        for category_obj in categories_data:
            category_name = category_obj.get("name", "")
            if category_name:
                category_names.add(category_name)

        # 从所有事件定义中收集分类
        for _, definition in definitions_data.get("definitions", {}).items():
            category = definition.get("category")
            if category:
                category_names.add(category)

        # 返回分类名称列表（用于前端构建选项）
        category_options = sorted(c for c in category_names if c)

        business_data["event_definition"] = event_definition
        business_data["record_data"] = new_record_data
        business_data["computed_data"] = computed_data
        business_data["category_options"] = category_options
        business_data["categories"] = definitions_data.get(
            "categories", []
        )  # 传递完整的分类数据

        return business_data

    def _calculate_average_duration(self, user_id: str, event_name: str) -> float:
        """
        计算事项的平均耗时
        """
        definitions_data = self.load_event_definitions(user_id)
        event_definition = definitions_data.get("definitions", {}).get(event_name, {})
        return self._calculate_avg_duration(event_definition)

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
        return round(avg_duration * duration_count, 1)

    @safe_execute("创建直接记录失败")
    def create_direct_record(
        self, user_id: str, dup_business_data: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        创建并保存记录到 event_records.json
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
        record_mode = dup_business_data.get("record_mode", "")
        source_record_id = dup_business_data.get("source_record_id", "")

        # 生成记录ID
        event_name = record_data.get("event_name", "").strip()

        # 构建记录数据
        current_time = self._get_formatted_time()
        event_type = event_definition.get("type", RoutineTypes.FUTURE.value)

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

        if (event_type == RoutineTypes.INSTANT.value) or (
            record_mode == RoutineRecordModes.QUERY
        ):
            new_record["end_time"] = current_time

        # 针对不同事件类型的特殊处理
        if event_type == RoutineTypes.FUTURE.value:
            # 未来事项：移除duration，使用estimated_duration
            if "duration" in new_record:
                duration_value = new_record.pop("duration")  # 移除duration
                if duration_value:  # 只有非空值才设置
                    new_record["estimated_duration"] = duration_value
            # 未来事项不需要has_definition字段

        # 加载记录数据
        records_data = self.load_event_records(user_id)
        source_record_data = {}
        if source_record_id:
            source_record_data = records_data.get("active_records", {}).get(
                source_record_id, {}
            ) or records_data.get("records", {}).get(source_record_id, {})
            if source_record_data:
                source_record_data.setdefault("related_records", {})
                source_record_data["related_records"].setdefault(event_name, [])
                if record_id not in source_record_data["related_records"][event_name]:
                    source_record_data["related_records"][event_name].append(record_id)
                source_record_data["last_updated"] = current_time

        # 对于非 future 类型的事项，创建事件定义
        if event_type != RoutineTypes.FUTURE.value:
            self._update_event_definition(
                user_id,
                event_name,
                dup_business_data,
                record_id,
                record_mode,
                source_record_data.get("event_name", ""),
            )

        # 特殊处理 QUERY 模式：编辑已有的 active_record
        if record_mode == RoutineRecordModes.QUERY:
            # 从 active_records 中移除原记录
            if record_id in records_data.get("active_records", {}):
                del records_data["active_records"][record_id]

            # 将更新后的记录添加到 records 的最前面
            new_records = OrderedDict()
            new_records[record_id] = new_record
            new_records.update(records_data.get("records", {}))
            records_data["records"] = new_records

            records_data["last_updated"] = current_time

            # 保存数据
            if self.save_event_records(user_id, records_data):
                return True, "成功完成记录"

            return False, "保存记录失败"

        # 常规处理：根据事件类型决定存储位置
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

    # endregion

    # region 菜单卡片相关
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
        self, user_id: str, max_items: int = 6
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

        # 加载active_records数据
        records_data = self.load_event_records(user_id)
        active_records = records_data.get("active_records", {})

        # 构建基础卡片数据
        quick_select_data = {
            "user_id": user_id,
            "quick_events": quick_events,
            "active_records": active_records,
        }

        return quick_select_data

    # endregion

    # region 查询相关
    # 因为要支持前端过滤，所以数据提取到缓存里会比较好？
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

        query_business_data = self.build_query_business_data(user_id)

        # 构建路由结果，指向查询结果卡片
        route_result = RouteResult.create_route_result(
            route_type=RouteTypes.ROUTINE_QUERY_RESULTS_CARD,
            route_params={"business_data": query_business_data},
        )

        return route_result

    def build_query_business_data(self, user_id: str) -> Dict[str, Any]:
        """
        构建查询数据
        """
        # 前端不应该组装，所以这里要组装，对于active_records，一个event可能可以有多个，那就要保留多个做备选
        event_data = self.load_event_definitions(user_id)
        records_data = self.load_event_records(user_id)
        active_records = records_data.get("active_records", {})

        # 收集active_records中的事件名称和分类
        active_event_names = set()
        categories_data = event_data.get("categories", [])
        category_names = set()

        # 从分类数据中收集分类名称
        for category_obj in categories_data:
            category_name = category_obj.get("name", "")
            if category_name:
                category_names.add(category_name)

        # 一次遍历active_records，按类型分组，同时收集分类
        today = datetime.now().strftime("%Y-%m-%d")
        start_events = []
        future_today = []
        future_other = []
        ongoing_events = []

        for record_id, record in active_records.items():
            event_name = record.get("event_name", "")
            active_event_names.add(event_name)
            event_def = event_data.get("definitions", {}).get(event_name, {})
            event_type = event_def.get("type", RoutineTypes.FUTURE.value)
            category = event_def.get("category", "未分类")
            category_names.add(category)

            record_element = {
                "record_type": "active_record",
                "record_id": record_id,
                "event_name": event_name,
                "event_type": event_type,
                "category": category,
                "data": record,
                "related_events": event_def.get("properties", {}).get(
                    "related_events", []
                ),
            }

            match event_type:
                case RoutineTypes.START.value:
                    start_events.append(record_element)
                case RoutineTypes.FUTURE.value:
                    scheduled_date = record.get("scheduled_start_time", "")[
                        :10
                    ]  # "2025-07-28 10:00" -> "2025-07-28"
                    if scheduled_date == today:
                        future_today.append(record_element)
                    else:
                        future_other.append(record_element)
                case RoutineTypes.ONGOING.value:
                    ongoing_events.append(record_element)

        merged_records = []
        merged_records.extend(start_events)
        merged_records.extend(future_today)
        merged_records.extend(future_other)
        merged_records.extend(ongoing_events)

        # 处理definitions：所有未在active_records中的definitions，按quick_access和last_updated排序
        definitions = event_data.get("definitions", {})
        priority_definitions = []

        for event_name, definition in definitions.items():
            # 跳过已经在active_records中的事件
            if event_name in active_event_names:
                continue

            # 收集分类
            category = definition.get("category")
            if category:
                category_names.add(category)

            # 为event_definition计算相关数据
            avg_duration = self._calculate_avg_duration(definition)
            definition["avg_duration"] = avg_duration

            # 获取最后记录数据
            last_record_id = definition.get("stats", {}).get("last_record_id", "")
            if last_record_id:
                last_record_data = records_data.get("records", {}).get(last_record_id)
                if not last_record_data:
                    last_record_data = active_records.get(last_record_id, {})
                definition["last_record_data"] = last_record_data

            priority_definitions.append((event_name, definition))

        # 按quick_access和last_updated排序definitions
        priority_definitions.sort(
            key=lambda x: (
                not x[1].get("quick_access", False),
                x[1].get("last_updated", ""),
            ),
            reverse=True,
        )

        # 限制处理数量，避免过多计算
        for event_name, definition in priority_definitions:
            event_type = definition.get("type", "")

            definition_element = {
                "record_type": "event_definition",
                "event_name": event_name,
                "event_type": event_type,
                "category": definition.get("category", "未分类"),
                "data": definition,
                "last_updated": definition.get("last_updated", ""),
                "quick_access": definition.get("quick_access", False),
            }
            merged_records.append(definition_element)

        # 先分离"未分类"，其余排序后拼接，"未分类"放最后
        category_list = [c for c in category_names if c]
        if "未分类" in category_list:
            category_list.remove("未分类")
            category_options = ["全部"] + sorted(category_list) + ["未分类"]
        else:
            category_options = ["全部"] + sorted(category_list)

        query_business_data = {
            "category_options": category_options,
            "query_data": merged_records,
            "categories": event_data.get("categories", []),  # 传递完整的分类数据
        }

        return query_business_data

    # endregion

    # region 更新event定义

    def _update_event_definition(
        self,
        user_id: str,
        event_name: str,
        dup_business_data: Dict[str, Any],
        record_id: str,
        record_mode: str = "",
        source_record_name: str = "",
    ) -> bool:
        """
        从直接记录的business_data创建事件定义

        Args:
            user_id: 用户ID
            event_name: 事件名称
            dup_business_data: 完整business_data数据
            record_id: 记录ID
            record_mode: 记录模式
            source_record_name: 源记录名称

        Returns:
            bool: 是否成功创建事件定义
        """
        # 加载现有事件定义
        # 分离一份临时的聚合数据导致编辑模式有挺大的问题，但不特别致命，备注一下。
        # 逻辑上分成两部分，非stats的，和stats的。
        # 对于properties的，是原子操作，且兼容后续编辑event_definition，直接更新。
        # 对于stats的，是复合操作，从配置里加载，计算，再更新。
        event_definitions = self.load_event_definitions(user_id)
        event_definition = dup_business_data.get("event_definition", {})
        catagory_options = dup_business_data.get("category_options", [])
        event_type = event_definition.get("type", RoutineTypes.INSTANT.value)
        computed_data = dup_business_data.get("computed_data", {})
        cycle_info = computed_data.get("cycle_info", {})

        record_data = dup_business_data.get("record_data", {})
        target_type = (
            dup_business_data.get("computed_data", {})
            .get("target_info", {})
            .get("target_type", "")
        )

        current_time = self._get_formatted_time()

        # 检查事件定义是否已存在
        if event_name in event_definitions.get("definitions", {}):
            # 事件定义已存在
            # 目前这里的效果是更新degree_options，其他是后续功能自动支持。
            existing_def = event_definitions["definitions"][event_name]
            existing_def["properties"] = event_definition.get("properties", {})
            existing_def["category"] = event_definition.get(
                "category", existing_def["category"]
            )

            # stats
            existing_def_stats = event_definitions["definitions"][event_name].get(
                "stats", {}
            )

            if record_mode != RoutineRecordModes.QUERY:
                existing_def_stats["record_count"] = (
                    existing_def_stats.get("record_count", 0) + 1
                )

            # 更新耗时统计
            duration = safe_parse_number(record_data.get("duration"))
            if duration > 0:
                self._update_duration_stats(existing_def_stats, duration)

            # 更新周期统计信息（如果存在）
            if cycle_info:
                # 在创建事件是包含了预刷新检测，所以要用computed_data里的cycle_info
                if target_type == RoutineTargetTypes.TIME.value:
                    existing_def_stats["cycle_count"] = (
                        cycle_info.get("cycle_count", 0) + duration
                    )
                else:
                    existing_def_stats["cycle_count"] = (
                        cycle_info.get("cycle_count", 0) + 1
                    )

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
                progress_value = safe_parse_number(record_data.get("progress_value"))
                self._update_progress_stats(
                    existing_def_stats, progress_type, progress_value
                )

            existing_def["last_record_time"] = current_time
            existing_def["last_updated"] = current_time

        else:
            # 创建新的事件定义
            new_definition = self._create_event_definition(event_name, event_type)

            # 从表单数据中提取并设置属性
            self._populate_definition_from_business_data(
                new_definition, dup_business_data, current_time
            )

            category = event_definition.get("category", "")
            new_definition["category"] = category

            new_definition["last_record_id"] = record_id
            # 添加到定义集合中
            event_definitions["definitions"][event_name] = new_definition

            if category and category not in catagory_options:
                categories_data = dup_business_data.get("categories", [])
                # 从分类数据中查找对应的颜色
                for category_obj in categories_data:
                    if category_obj.get("name") == category:
                        new_color = category_obj.get("color", "")
                        break
                if not new_color:
                    new_color = ColorTypes.get_random_color().value
                event_definitions["categories"].append(
                    {
                        "name": category,
                        "color": new_color,
                    }
                )

        if source_record_name:
            source_definition = event_definitions["definitions"].get(
                source_record_name, {}
            )
            if event_name not in source_definition["properties"]["related_events"]:
                source_definition["properties"]["related_events"].append(event_name)
            source_definition["last_updated"] = current_time
        # 更新全局时间戳
        event_definitions["last_updated"] = current_time
        event_definitions["last_record_time"] = current_time

        # 保存事件定义
        return self.save_event_definitions(user_id, event_definitions)

    def _populate_definition_from_business_data(
        self,
        definition: Dict[str, Any],
        dup_business_data: Dict[str, Any],
        current_time: str,
    ) -> None:
        """
        从表单数据填充事件定义的属性

        Args:
            definition: 事件定义字典
            record_data: 表单数据
            current_time: 当前时间
        """
        event_definition = dup_business_data.get("event_definition", {})
        properties = definition["properties"].update(
            event_definition.get("properties", {})
        )

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

    def _update_duration_stats(self, stats: Dict[str, Any], duration: float) -> None:
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

    # endregion

    # region 辅助方法
    # 不需要 user_id 、self等信息，合适的情况可以迁移出去
    def _get_formatted_time(self) -> str:
        """
        获取格式化的时间字符串

        Returns:
            str: 格式化时间 "2025-07-10 09:07"
        """
        return datetime.now().strftime("%Y-%m-%d %H:%M")

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
            case RoutineCheckCycle.DAILY.value:
                days_diff = (now.date() - last_refresh.date()).days
                cycle_gap = max(0, days_diff)
                need_refresh = days_diff > 0
            case RoutineCheckCycle.WEEKLY.value:
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
            case RoutineCheckCycle.MONTHLY.value:
                months_diff = (current_year - last_year) * 12 + (
                    now.month - last_refresh.month
                )
                cycle_gap = max(0, months_diff)
                need_refresh = cycle_gap > 0
            case RoutineCheckCycle.SEASONALLY.value:
                last_season = (last_refresh.month - 1) // 3
                current_season = (now.month - 1) // 3
                seasons_diff = (current_year - last_year) * 4 + (
                    current_season - last_season
                )
                cycle_gap = max(0, seasons_diff)
                need_refresh = cycle_gap > 0
            case RoutineCheckCycle.YEARLY.value:
                cycle_gap = max(0, current_year - last_year)
                need_refresh = cycle_gap > 0
            case _:
                raise ValueError(f"不支持的 check_cycle: {check_cycle}")
        # 生成描述
        gap_description = "前一" if cycle_gap <= 1 else f"前{cycle_gap}"

        # 使用集中的描述单位
        description_unit = RoutineCheckCycle.get_description_unit(check_cycle)
        description = f"{gap_description}{description_unit}"

        return {
            "need_refresh": need_refresh,
            "cycle_gap": cycle_gap,
            "description": description,
        }

    def _calculate_avg_duration(self, event_definition: Dict[str, Any]) -> float:
        """
        计算事件定义的平均耗时

        Args:
            event_definition: 事件定义

        Returns:
            float: 平均耗时，如果没有数据则返回0
        """
        event_duration_records = (
            event_definition.get("stats", {})
            .get("duration", {})
            .get("recent_values", [])
        )
        if event_duration_records:
            return round(sum(event_duration_records) / len(event_duration_records), 1)
        return 0

    # endregion

    # region 报表计算

    def preprocess_and_filter_records(
        self, all_records_dict: Dict[str, Any], start_range, end_range
    ):
        """
        预处理和过滤记录数据
        1. 将字典转为列表，并转换时间格式
        2. 筛选出与时间范围有交集的记录
        3. 按开始时间升序排序
        """
        record_list = []
        for record in all_records_dict.values():
            try:
                # 兼容不同的时间字段名
                create_time_str = record.get("create_time") or record.get(
                    "created_time", ""
                )
                end_time_str = record.get("end_time", "")

                if not create_time_str:
                    continue

                start_time = datetime.fromisoformat(create_time_str.replace(" ", "T"))

                # 如果没有end_time，使用create_time作为end_time（即时事件）
                if not end_time_str:
                    end_time = start_time
                    start_time = start_time - timedelta(
                        minutes=record.get("duration", 0)
                    )
                else:
                    end_time = datetime.fromisoformat(end_time_str.replace(" ", "T"))

                if start_time < end_range and end_time > start_range:
                    record["start_dt"] = start_time
                    record["end_dt"] = end_time
                    record_list.append(record)
            except (ValueError, KeyError) as e:
                print(
                    f"Skipping record due to error: {record.get('record_id', 'N/A')}, {e}"
                )
                continue

        record_list.sort(key=lambda x: x["start_dt"])
        return record_list

    def generate_atomic_timeline(self, sorted_records, start_range, end_range):
        """
        生成一个由不重叠的"原子时间块"构成的有序列表。
        每个块都包含其归属的原始事件信息。
        """
        if not sorted_records:
            return []

        # 1. 收集所有不重复的时间点，并限制在分析范围内
        time_points = {start_range, end_range}
        for r in sorted_records:
            clamped_start = max(r["start_dt"], start_range)
            clamped_end = min(r["end_dt"], end_range)
            if clamped_start < clamped_end:
                time_points.add(clamped_start)
                time_points.add(clamped_end)

        sorted_points = sorted(list(time_points))
        atomic_timeline = []

        # 2. 遍历由时间点切割出的每个微小时间段
        for i in range(len(sorted_points) - 1):
            segment_start, segment_end = sorted_points[i], sorted_points[i + 1]

            if segment_start >= segment_end:
                continue

            # 3. 找出覆盖这个时间段的、开始时间最晚的事件 ("顶层事件")
            top_event = None
            for record in sorted_records:
                if (
                    record["start_dt"] <= segment_start
                    and record["end_dt"] >= segment_end
                ):
                    top_event = record  # 因为已排序，最后一个匹配的就是最顶层的

            # 4. 如果找到归属事件，则创建原子块
            if top_event:
                atomic_block = {
                    "start_time": segment_start,
                    "end_time": segment_end,
                    "duration_minutes": (segment_end - segment_start).total_seconds()
                    / 60.0,
                    "source_event": top_event,  # 关键！保留完整的原始事件引用
                }
                atomic_timeline.append(atomic_block)

        return atomic_timeline

    def aggregate_for_color_blending(self, atomic_timeline, event_map):
        """
        聚合原子时间线，按颜色分类聚合数据
        """
        # 按颜色类型聚合
        color_aggregated_data = {}

        for block in atomic_timeline:
            event_name = block["source_event"]["event_name"]
            record_id = block["source_event"]["record_id"]
            duration = block["duration_minutes"]

            # 获取原始记录的duration，如果存在的话
            original_duration = block["source_event"].get("duration", None)

            # 获取颜色类型——对于未来事件这样没有definition的，设置灰色
            color_type = event_map.get(event_name, {}).get("color", ColorTypes.GREY)

            # 找到对应的分类名称
            category_name = event_map.get(event_name, {}).get("category", "无分类")

            # 使用分类名称作为聚合键
            if category_name not in color_aggregated_data:
                color_aggregated_data[category_name] = {
                    "duration": 0,
                    "count": 0,
                    "records": set(),
                    "color_type": color_type,
                    "record_durations": {},
                }

            # 累计时间，但每个记录不超过其原始duration
            if original_duration is not None:
                # 检查这个record_id是否已经被处理过
                if record_id not in color_aggregated_data[category_name]["records"]:
                    # 第一次处理这个记录
                    color_aggregated_data[category_name]["records"].add(record_id)
                    color_aggregated_data[category_name]["count"] += 1
                    color_aggregated_data[category_name]["record_durations"][
                        record_id
                    ] = 0

                # 计算这个记录ID已经累计的时间
                current_record_duration = color_aggregated_data[category_name][
                    "record_durations"
                ].get(record_id, 0)
                # 计算还能累计多少时间（不超过原始duration）
                remaining_duration = max(0, original_duration - current_record_duration)
                # 实际累计的时间
                actual_duration = min(duration, remaining_duration)

                color_aggregated_data[category_name]["duration"] += actual_duration
                color_aggregated_data[category_name]["record_durations"][
                    record_id
                ] += actual_duration
            else:
                # 没有原始duration限制，直接累计
                color_aggregated_data[category_name]["duration"] += duration
                if record_id not in color_aggregated_data[category_name]["records"]:
                    color_aggregated_data[category_name]["records"].add(record_id)
                    color_aggregated_data[category_name]["count"] += 1

        # 格式化为最终输出
        final_list = []
        for category_name, data in color_aggregated_data.items():
            final_list.append(
                {
                    "category_color": data["color_type"],
                    "category_name": category_name,
                    "duration": data["duration"],
                    "count": data["count"],
                }
            )
        return final_list

    def _calculate_nonlinear_weight(
        self, duration, count, duration_importance=0.7, count_importance=0.3
    ):
        """
        使用加权求和的方式计算影响力。
        duration_importance 和 count_importance 的和应该为1。
        """
        if duration <= 0 or count <= 0:
            return 0

        # 1. 对时长和次数进行归一化或函数变换，使其处于可比较的范围
        #    我们仍然使用之前的函数变换来压缩数值
        duration_component = math.sqrt(duration)
        #    次数分量可以稍微加强一下，因为它的原始数值小
        count_component = (1 + math.log2(count)) * 5  # 乘以一个系数来放大它的基础值

        # 2. 加权求和
        #    这里，我们假设时长的重要性占70%，次数的重要性占30%
        #    你可以根据你的感觉来调整这两个系数！
        additive_score = (duration_component * duration_importance) + (
            count_component * count_importance
        )

        # 乘以一个常数让数值变大
        return additive_score * 5

    # endregion

    # region 颜色计算

    def calculate_daily_color(
        self, user_id: str, target_date: str = None
    ) -> Dict[str, Any]:
        """
        计算指定日期的颜色值（使用原子时间线算法）

        Args:
            user_id: 用户ID
            target_date: 目标日期 (YYYY-MM-DD)，默认为昨天

        Returns:
            str: 计算出的颜色值
        """

        # 确定目标日期
        if target_date is None:
            yesterday = datetime.now() - timedelta(days=1)
            target_date = yesterday.strftime("%Y-%m-%d")

        # 定义分析范围
        target_date_dt = datetime.strptime(target_date, "%Y-%m-%d")
        day_start = target_date_dt
        day_end = day_start + timedelta(days=1)
        return self.calculate_color_palette(user_id, day_start, day_end)

    def calculate_weekly_color(
        self, user_id: str, target_week_start: str = None
    ) -> str:
        """
        计算指定周的颜色值

        Args:
            user_id: 用户ID
            target_week_start: 目标周开始日期 (YYYY-MM-DD)，默认为上周

        Returns:
            str: 计算出的颜色值
        """

        # 确定目标周
        if target_week_start is None:
            today = datetime.now()
            days_since_monday = today.weekday()
            last_monday = today - datetime.timedelta(days=days_since_monday + 7)
            target_week_start = last_monday.strftime("%Y-%m-%d")

        # 计算周结束日期
        start_date = datetime.strptime(target_week_start, "%Y-%m-%d")
        end_date = start_date + datetime.timedelta(days=6)
        return self.calculate_color_palette(user_id, start_date, end_date)

    def calculate_color_palette(
        self,
        user_id: str,
        day_start: datetime = None,
        day_end: datetime = None,
    ) -> Dict[str, Any]:
        """
        计算颜色调色盘
        """

        default_return = {
            "type": "default",
            "name": "蓝色",
            "hex": ColorTypes.BLUE.light_color,
            "distance": 0,
        }

        # 获取记录数据
        records_data = self.load_event_records(user_id)
        records = records_data.get("records", {})

        if not records:
            return default_return  # 默认颜色

        # 加载分类数据
        definitions_data = self.load_event_definitions(user_id)
        categories_data = definitions_data.get("categories", [])

        # 创建事件名到颜色类型的映射
        event_to_color_map = {}
        for event_name, event_def in definitions_data.get("definitions", {}).items():
            category = event_def.get("category", "")
            cata_info = {}
            if category:
                # 查找分类对应的颜色
                cata_info["category"] = category
                for category_obj in categories_data:
                    if category_obj.get("name") == category:
                        color_value = category_obj.get("color", ColorTypes.BLUE.value)
                        cata_info["color"] = ColorTypes.get_by_value(color_value)
                        break
            else:
                cata_info["category"] = "无分类"
                cata_info["color"] = ColorTypes.GREY
            event_to_color_map[event_name] = cata_info

        # 1. 预处理和排序
        relevant_records = self.preprocess_and_filter_records(
            records, day_start, day_end
        )
        if not relevant_records:
            return default_return

        # 2. 生成核心数据结构：原子时间线
        atomic_timeline = self.generate_atomic_timeline(
            relevant_records, day_start, day_end
        )

        # 3. 聚合数据用于颜色混合
        category_data = self.aggregate_for_color_blending(
            atomic_timeline, event_to_color_map
        )

        if not category_data:
            return default_return

        # 4. 计算分类权重
        category_weights = {}
        max_weight_category = None
        max_weight = 0
        for item in category_data:
            category_name = item["category_name"]
            duration = item["duration"]
            count = item["count"]

            weight = self._calculate_nonlinear_weight(duration, count)
            if category_name not in category_weights:
                category_weights[category_name] = {}
                category_weights[category_name]["color"] = item["category_color"]
                category_weights[category_name]["weight"] = 0

            category_weights[category_name]["weight"] += weight
            if category_weights[category_name]["weight"] > max_weight:
                max_weight = category_weights[category_name]["weight"]
                max_weight_category = category_name

        # 5. 计算最终颜色
        final_color = self._blend_colors_by_weights(category_weights)
        if max_weight_category:
            final_color["max_weight_category"] = max_weight_category
        palette_data = self.prepare_palette_data(category_weights)

        return final_color, palette_data

    def _blend_colors_by_weights(
        self, category_weights: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        根据权重混合颜色（在HSL色彩空间中进行计算）

        Args:
            category_weights: 分类权重字典

        Returns:
            str: 混合后的颜色值
        """
        # 在HSL色彩空间中混合颜色
        blended_hsl = self._blend_colors_in_hsl_space(category_weights)

        # 找到最接近的预定义颜色
        return self._find_closest_color_from_hsl(blended_hsl)

    def _blend_colors_in_hsl_space(self, category_weights: Dict[str, float]) -> tuple:
        """
        在HSL色彩空间中混合颜色

        Args:
            category_weights: 分类权重字典
            categories_data: 分类数据列表

        Returns:
            tuple: (H, S, L) 混合后的HSL值
        """
        sum_h_x, sum_h_y = 0, 0
        total_s, total_l, total_h = 0, 0, 0
        total_weight = sum(
            category_info["weight"] for category_info in category_weights.values()
        )

        if total_weight == 0:
            return 0, 0, 0.5  # 返回一个中性灰色

        for _, category_info in category_weights.items():
            # 查找分类对应的颜色
            weight = category_info["weight"]
            category_color = category_info["color"]

            # 获取颜色对应的HSL值
            color_type = ColorTypes.get_by_value(category_color.value)
            hex_color = color_type.light_color  # 使用亮色

            # 转换十六进制为HSL
            color_h, color_s, color_l = hex_to_hsl(hex_color)

            # 按权重累加HSL值
            total_s += color_s * weight
            total_l += color_l * weight
            total_h += color_h * weight

            # 2. 对色相(H)进行向量加权平均
            #    首先将角度转换为弧度
            color_h_rad = math.radians(color_h)
            #    计算向量的x, y分量并按权重累加
            sum_h_x += math.cos(color_h_rad) * weight
            sum_h_y += math.sin(color_h_rad) * weight

        final_s = total_s / total_weight
        final_l = total_l / total_weight
        final_h_rad = math.atan2(sum_h_y, sum_h_x)
        # 将弧度转换回角度（0-360度）
        final_h_deg = math.degrees(final_h_rad)
        if final_h_deg < 0:
            final_h_deg += 360

        return (final_h_deg, final_s, final_l)

    def _find_closest_color_from_hsl(
        self, target_hsl: tuple, threshold: float = 10
    ) -> Dict[str, Any]:
        """
        从HSL值找到最接近的预定义颜色

        Args:
            target_hsl: 目标HSL值 (H, S, L)

        Returns:
            str: 最接近的颜色值
        """
        min_distance = float("inf")
        closest_color = ColorTypes.BLUE

        for color_type in ColorTypes:
            if color_type.value == "grey":  # 跳过灰色
                continue

            hex_color = color_type.light_color
            color_hsl = hex_to_hsl(hex_color)

            # 计算HSL距离
            distance = self._calculate_hsl_distance(target_hsl, color_hsl)

            if distance < min_distance:
                min_distance = distance
                closest_color = color_type

        if closest_color and min_distance < threshold:
            return {
                "type": "predefined",
                "name": closest_color.value,
                "hex": closest_color.light_color,
                "distance": round(min_distance, 2),
            }

        hex_color = hsl_to_hex(target_hsl[0], target_hsl[1], target_hsl[2])
        return {
            "type": "unique",
            "name": "独特的颜色",  # 临时名字
            "hex": hex_color,
            "closest_to": closest_color.value if closest_color else "N/A",
            "distance_to_closest": round(min_distance, 2),
        }

    def _calculate_hsl_distance(self, hsl1: tuple, hsl2: tuple) -> float:
        """
        计算两个HSL颜色之间的距离

        Args:
            hsl1, hsl2: HSL值元组

        Returns:
            float: 颜色距离
        """
        h1, s1, l1 = hsl1
        h2, s2, l2 = hsl2

        # 色相距离（考虑环形）
        h_diff = min(abs(h1 - h2), 360 - abs(h1 - h2))

        # 饱和度和亮度距离
        s_diff = s1 - s2
        l_diff = l1 - l2

        # 加权距离（色相权重更高）
        distance = math.sqrt(
            (h_diff * 1.5) ** 2 + (s_diff * 1.0) ** 2 + (l_diff * 1.0) ** 2
        )
        return distance

    def prepare_palette_data(self, category_weights):
        """
        将权重字典转换为用于绘图的调色盘数据列表。
        """
        total_weight = sum(info["weight"] for info in category_weights.values())
        if total_weight == 0:
            return []

        palette_data = []
        for category_name, info in category_weights.items():
            palette_data.append(
                {
                    "name": category_name,
                    "color_enum": info["color"],
                    "color_hex": info["color"].light_color,
                    "weight": info["weight"],
                    "percentage": (info["weight"] / total_weight) * 100.0,
                }
            )

        # 按百分比降序排序，方便后续绘图
        palette_data.sort(key=lambda x: x["percentage"], reverse=True)

        return palette_data

    # endregion


# region 绘图提示词
def color_desc(color_name, color_hex):
    """根据颜色名和色值生成英文描述"""
    color_map = {
        "turquoise": "brilliant turquoise",
        "blue": "soft light pastel blue",
        "wathet": "serene sky blue",
        "carmine": "gentle pink",
        "orange": "warm vibrant apricot orange",
        "purple": "soft lavender purple",
        "grey": "pearlescent off-white",
        "red": "delicate soft rose red",
        "green": "fresh lively mint green",
        "lime": "zesty lime green",
        "sunflower": "bright sunflower yellow",
    }
    # 优先使用预设的描述
    description = color_map.get(color_name.lower())
    if description:
        return description
    # 如果没有预设，则提供一个基于通用名称的备用描述
    elif color_name:
        return f"shade of {color_name.lower()}"
    # 最后才使用HEX值作为备用
    else:
        return f"color with hex code {color_hex}"


def subject_desc(subject_name):
    """
    生成印章内主体造型的英文描述
    例如 subject_name="book"，返回 "The center of the seal features a detailed relief of an open book."
    """
    # 注释: 所有的值都从完整的句子修改为了名词短语，例如 "a book" 而不是 "the seal has a book"。
    subject_map = {
        "book": "an open book with finely etched lines representing pages and text",
        "star": "a classic five-pointed star with clean, raised edges",
        "cat": "a stylized silhouette of a sitting cat with a gracefully curved tail",
        "flower": "elegant curved lines forming a rose silhouette",
        "工作与创作": "the clean, modern outline of a laptop computer, its screen displaying a simple line graph",
        "学习": "a charming relief of a graduation cap, with a tassel dangling to the side",
        "运动": "a graceful female yoga pose line representing a feminine silhouette",
        "家务": "the simple, iconic outline of a house with a small chimney",
        "个人护理": "a minimalist design of a shower head with delicate droplets appearing to fall from it",
        "饮食": "simple, elegant lines forming fruits shapes",
        "休息": "a serene crescent moon hanging over a soft, puffy pillow",
        "娱乐": "a musical note and a game controller, side-by-side",
    }
    return subject_map.get(
        subject_name.lower(),
        f"a clean {subject_name} silhouette",
    )


def generate_intelligent_color_description(color_list: list) -> str:
    """
    (智能版) 分析权重分布，用最多三层量级来动态生成颜色描述。
    """
    if not color_list:
        return ""

    num_colors = len(color_list)
    descriptive_colors = [
        color_desc(c.get("color_enum").value, c.get("color_hex", ""))
        for c in color_list
    ]

    # --- 核心分析逻辑 ---

    # 情况1: 只有一个颜色
    if num_colors == 1:
        return f"a solid {descriptive_colors[0]} color"

    # 情况2: 只有两种颜色
    if num_colors == 2:
        # 比较权重，如果差距不大，则为并列主色
        if (
            color_list[0]["percentage"] / color_list[1]["percentage"] < 1.2
        ):  # 权重比小于1.2倍，视为并列
            return f"a marbled blend of {descriptive_colors[0]} and {descriptive_colors[1]}"
        else:
            return f"{descriptive_colors[0]} marbled with {descriptive_colors[1]}"

    # 情况3: 三个及以上颜色，进行层级分析
    # Tier 1: 主色调 (The main players)
    tier1 = [descriptive_colors[0]]
    # 检查第二名是否与第一名差距不大，如果是，则并入主色调
    if (
        color_list[1]["percentage"] / color_list[0]["percentage"] > 0.8
    ):  # 第二名权重超过第一名的70%
        tier1.append(descriptive_colors[1])
        # 检查第三名是否与第二名差距不大
        if (
            num_colors > 2
            and color_list[2]["percentage"] / color_list[1]["percentage"] > 0.7
        ):
            tier1.append(descriptive_colors[2])

    tier1_text = f"a rich marble of {' and '.join(tier1)}"

    # Tier 2 & 3: 次要色和点缀色
    remaining_colors = descriptive_colors[len(tier1) :]
    if not remaining_colors:
        return tier1_text  # 只有主色调

    # Tier 2: 次要色 (The supporting cast)
    tier2 = []
    if remaining_colors:
        tier2.append(remaining_colors.pop(0))
        # 检查下一个是否与当前差距不大
        if (
            remaining_colors
            and color_list[len(tier1) + 1]["percentage"]
            / color_list[len(tier1)]["percentage"]
            > 0.6
        ):
            tier2.append(remaining_colors.pop(0))

    tier2_text = f"swirled with prominent streaks of {' and '.join(tier2)}"

    if not remaining_colors:
        return f"{tier1_text}, {tier2_text}"

    # Tier 3: 点缀色 (The final touches)
    tier3 = remaining_colors
    tier3_text = f"and subtle hints of {', '.join(tier3)}"

    return f"{tier1_text}, {tier2_text}, {tier3_text}"


def wax_stamp_prompt(color_palette, subject_name=None):
    """
    根据color_palette结果组装英文画图提示词，并根据subject_name智能插入主体造型描述
    color_palette: (unique_color_info, color_list)
    subject_name: 印章内主体造型的名称（可为None或空字符串）
    """
    color_list = color_palette
    # 颜色按比例排序
    color_list = (
        sorted(color_list, key=lambda x: -x.get("percentage", 0)) if color_list else []
    )

    # color_detail_text = generate_color_details_text(color_list)
    # 注释: 调用我们全新的、智能的颜色描述函数。
    color_text = generate_intelligent_color_description(color_list)

    # 主体造型描述
    subject_name = subject_name or color_list[0].get("name") if color_list else ""
    subject_text = subject_desc(subject_name) if subject_name else ""

    # --- 4. 全新Prompt结构化组装 ---
    # --- 3. 终极Prompt组装 ---
    # 注释: 完全采用你提供的、经过验证的极简模板结构。
    prompt = (
        "Macro photograph of a wax seal on cream textured paper. "
        "Semi-translucent wax with organic, irregular, molten edges. "
    )

    if subject_text:
        # 注释: 插入主体图案描述
        prompt += f"The raised seal pattern shows {subject_text}. "

    # 注释: 插入由智能算法生成的颜色描述，并加入金色闪粉
    prompt += f"Marbled colors: {color_text}, with shimmering gold dust particles suspended within. "

    # 注释: 插入光照和风格描述
    prompt += (
        "Dramatic lighting highlights the translucent, glossy surface. "
        "Professional photography, shallow depth of field."
    )

    return prompt


# endregion
