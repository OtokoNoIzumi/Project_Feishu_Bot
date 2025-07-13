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
import uuid
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from Module.Common.scripts.common import debug_utils
from Module.Services.constants import ServiceNames, ResponseTypes, RoutineTypes, RouteTypes, RoutineCheckCycle
from Module.Business.processors.base_processor import BaseProcessor, ProcessResult, require_service, safe_execute
from Module.Business.processors import RouteResult


# 从一开始就用抽象层
class EventStorage:
    def save_event(self, event_data): pass
    def load_events(self): pass
    def query_events(self, filter_func): pass

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
        self.user_permission_service = self.app_controller.get_service(ServiceNames.USER_BUSINESS_PERMISSION)
        self.storage = JSONEventStorage()

        # 内存中的查询上下文，按用户ID存储
        self.query_contexts = {}

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
        storage_path = self.config_service.get("routine_record.storage_path", "user_data/")

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

    def _create_event_definition(self, event_name: str, event_type: str = RoutineTypes.INSTANT) -> Dict[str, Any]:
        """
        创建事件定义

        Args:
            event_name: 事件名称
            event_type: 事件类型

        Returns:
            Dict[str, Any]: 事件定义
        """
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
                "default_degree": '',

                # 时间属性
                "future_date": None,
                "estimated_duration": None,

                # 目标属性
                "check_cycle": None,
                "custom_cycle_config": None,
                "target_type": None, #次数/时长
                "target_value": None #目标值
            },
            "stats": {
                "record_count": 0,
                "cycle_count": 0,
                "last_target_count": 0,
                "duration": {
                    "recent_values": [],        # 最近N次的耗时值
                    "window_size": 10,          # 滑动窗口大小
                    "duration_count": 0,        # 有耗时记录的次数
                    "avg_all_time": None        # 历史平均耗时
                },
                "last_refresh_date": None,
                "last_progress_value": None,
                "last_note": ""  # 记录最近一次的备注
            },
            "created_time": current_time,
            "last_updated": current_time
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
        definitions_data = self._load_event_definitions(user_id)

        # 计算该事件的现有记录数量
        count = definitions_data.get("definitions", {}).get(event_name, {}).get("stats",{}).get("record_count", 0)

        # 生成新的序号（从00001开始）
        next_num = count + 1
        return f"{event_name}_{next_num:05d}"

    def _create_event_record(self, event_name: str, user_id: str, degree: str = None, note: str = "", related_records: List[str] = None) -> Dict[str, Any]:
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
    def _load_event_definitions(self, user_id: str) -> Dict[str, Any]:
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
                "last_updated": current_time
            }
            self._save_event_definitions(user_id, default_data)
            return default_data

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 确保基本字段存在
                if "categories" not in data:
                    data["categories"] = []
                return data
        except (json.JSONDecodeError, FileNotFoundError) as e:
            debug_utils.log_and_print(f"读取事件定义文件失败: {e}", log_level="ERROR")
            return {}

    @safe_execute("加载事件记录失败")
    def _load_event_records(self, user_id: str) -> Dict[str, Any]:
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
                "records": [],
                "created_time": current_time,
                "last_updated": current_time
            }
            self._save_event_records(user_id, default_data)
            return default_data

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        except (json.JSONDecodeError, FileNotFoundError) as e:
            debug_utils.log_and_print(f"读取事件记录文件失败: {e}", log_level="ERROR")
            return {}

    @safe_execute("保存事件定义失败")
    def _save_event_definitions(self, user_id: str, data: Dict[str, Any]) -> bool:
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
        data["last_updated"] = self._get_formatted_time()

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            debug_utils.log_and_print(f"保存事件定义文件失败: {e}", log_level="ERROR")
            return False

    @safe_execute("保存事件记录失败")
    def _save_event_records(self, user_id: str, data: Dict[str, Any]) -> bool:
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
        data["last_updated"] = self._get_formatted_time()

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            debug_utils.log_and_print(f"保存事件记录文件失败: {e}", log_level="ERROR")
            return False

    def _get_query_context(self, user_id: str) -> Dict[str, Any]:
        """
        获取用户的查询上下文

        Args:
            user_id: 用户ID

        Returns:
            Dict[str, Any]: 查询上下文
        """
        return self.query_contexts.get(user_id, {
            "last_query_type": None,
            "last_query_results": [],
            "last_query_time": None
        })

    def _set_query_context(self, user_id: str, query_type: str, results: List[str]) -> None:
        """
        设置用户的查询上下文

        Args:
            user_id: 用户ID
            query_type: 查询类型
            results: 查询结果
        """
        self.query_contexts[user_id] = {
            "last_query_type": query_type,
            "last_query_results": results,
            "last_query_time": self._get_formatted_time()
        }

    def _clear_query_context(self, user_id: str) -> None:
        """
        清除用户的查询上下文

        Args:
            user_id: 用户ID
        """
        if user_id in self.query_contexts:
            del self.query_contexts[user_id]

    @safe_execute("获取关联开始事项失败")
    def get_related_start_events(self, user_id: str) -> List[Dict[str, Any]]:
        """
        获取可作为关联开始事项的列表

        Args:
            user_id: 用户ID

        Returns:
            List[Dict[str, Any]]: 开始事项选项列表
        """
        definitions_data = self._load_event_definitions(user_id)
        if not definitions_data:
            return []

        definitions = definitions_data.get("definitions", {})
        start_events = []

        for event_name, event_def in definitions.items():
            if event_def.get('type') == RoutineTypes.START:
                start_events.append({
                    "text": {"tag": "plain_text", "content": event_name},
                    "value": event_name
                })

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

        return self.user_permission_service.check_business_permission(user_id, "routine_record")

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
            item_name = message_text[2:].strip()
            if item_name:
                return ("create", item_name)

        if message_text.startswith("日程 "):
            item_name = message_text[3:].strip()
            if item_name:
                return ("create", item_name)

        # 检测查询指令
        if message_text == "rs" or message_text == "查看日程":
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

            if command_type == "create":
                debug_utils.log_and_print(f"📝 {context.user_name} 触发日程创建指令：{item_name}", log_level="INFO")
                # 只有一种情况需要分离一下，也就是异步操作需要提前调用sender发消息。
                return self.process_routine_create(context.user_id, item_name)
            elif command_type == "query":
                debug_utils.log_and_print(f"📋 {context.user_name} 触发日程查询指令", log_level="INFO")
                return self.process_routine_query(context.user_id)

        # 2. 检查数字选择
        if user_msg.strip().isdigit():
            try:
                number = int(user_msg.strip())
                result = self.process_number_selection(context.user_id, number, user_msg)

                # 如果routine_record能处理这个数字选择，直接返回ProcessResult
                if result:
                    return result

            except ValueError:
                pass

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

        card_data = self.build_query_results_card_data(user_id)
        # 构建路由结果，指向查询结果卡片
        route_result = RouteResult.create_route_result(
            route_type=RouteTypes.ROUTINE_QUERY_RESULTS_CARD,
            route_params={
                "card_type": "query_results",
                "business_data": card_data
            }
        )

        return route_result

    @safe_execute("构建查询结果卡片数据失败")
    def build_query_results_card_data(self, user_id: str, query_type: str = "recent") -> Dict[str, Any]:
        """
        构建查询结果卡片数据

        Args:
            user_id: 用户ID
            query_type: 查询类型
            operation_id: 操作ID

        Returns:
            Dict[str, Any]: 卡片数据
        """
        # 获取查询结果
        results = self.get_query_results_data(user_id, max_items=10)

        return {
            "user_id": user_id,
            "query_type": query_type,
            "results": results
        }

    @safe_execute("获取查询结果数据失败")
    def get_query_results_data(self, user_id: str, max_items: int = 10) -> List[Dict[str, Any]]:
        """
        获取查询结果数据，用于卡片展示

        Args:
            user_id: 用户ID
            max_items: 最大返回数量

        Returns:
            List[Dict[str, Any]]: 查询结果数据
        """
        definitions_data = self._load_event_definitions(user_id)
        records_data = self._load_event_records(user_id)

        if not definitions_data:
            return []

        definitions = definitions_data.get("definitions", {})
        if not definitions:
            return []

        # 按最后更新时间排序
        sorted_definitions = sorted(
            definitions.items(),
            key=lambda x: x[1].get("last_updated", ""),
            reverse=True
        )[:max_items]

        results = []
        for event_name, event_def in sorted_definitions:
            # 获取该事件的最新记录
            event_records = [r for r in records_data.get("records", []) if r["event_name"] == event_name]
            last_record = None

            if event_records:
                event_records.sort(key=lambda x: x["timestamp"], reverse=True)
                last_record = event_records[0]

            results.append({
                "event_name": event_name,
                "event_definition": event_def,
                "last_record": last_record
            })

        return results

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
        definitions_data = self._load_event_definitions(user_id)

        if not definitions_data:
            return ProcessResult.error_result("加载事件定义失败")

        # 检查事项是否已存在
        if item_name in definitions_data.get("definitions", {}):
            # 事项已存在，直接记录，这里要封装原始数据
            event_def = definitions_data["definitions"][item_name]
            # 这里出现了第一个要澄清的card相关的概念。按照架构，这里应该是完备的业务数据，不涉及前端逻辑。
            # 并且这里要能够直接绕过前端直接对接业务——本来前端就是多一层中转和丰富信息，也就是如果这个不routeresult，而是直接到业务也应该OK。
            routine_record_data = self.build_quick_record_data(user_id, item_name, event_def)
            route_result = RouteResult.create_route_result(
                route_type=RouteTypes.ROUTINE_QUICK_RECORD_CARD,
                route_params={
                    "card_type": "quick_record_confirm",
                    "business_data": routine_record_data
                }
            )
            return route_result
        else:
            # 新事项，展示事件定义卡片
            card_data = self.build_new_event_card_data(user_id, item_name)
            route_result = RouteResult.create_route_result(
                route_type=RouteTypes.ROUTINE_NEW_EVENT_CARD,
                route_params={
                    "card_type": "new_event_definition",
                    "business_data": card_data
                }
            )
            return route_result

    @safe_execute("构建新事件定义卡片数据失败")
    def build_new_event_card_data(self, user_id: str, initial_event_name: str = '') -> Dict[str, Any]:
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
                "notes": ""
            }
        }

    @safe_execute("构建快速记录确认卡片数据失败")
    def build_quick_record_data(self, user_id: str, event_name: str, event_def: Dict[str, Any]) -> Dict[str, Any]:
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
        # 动态的属性逻辑有哪些——
        # 距离累计目标如何，包括每天第一次更新的数值重置和历史成果的说明
        # 预计的时间
        # 不同的程度，后面还有需求再加就好了。关键是数据结构了。
        record_id = self._get_next_record_id(user_id, event_name)
        new_record = self._create_event_record(event_name, user_id)
        new_record["record_id"] = record_id
        new_record["timestamp"] = self._get_formatted_time()
        # 先不继续加字段了，反正event_def里也有。
        # new_record["last_progress_value"] = event_def.get('stats',{}).get('last_progress_value', None)
        # new_record["last_note"] = event_def.get('stats',{}).get('last_note', "")

        avg_duration = self._calculate_average_duration(user_id, event_name)
        has_degrees = event_def.get('properties',{}).get('has_degrees',False)
        if has_degrees:
            degree_info = {
                "degree_options": event_def.get('properties',{}).get('degree_options',[]),
                "default_degree": event_def.get('properties',{}).get('default_degree',""),
                "selected_degree": "",
            }
        else:
            degree_info = {}

        # 这里的顺序要改一下，首先是累计值和重置，然后是有没有目标。
        check_cycle = event_def.get('properties',{}).get('check_cycle',None)
        if check_cycle:
            cycle_count = event_def.get('stats',{}).get('cycle_count',0)
            last_refresh_date = event_def.get('stats',{}).get('last_refresh_date',None)
            if self._check_need_refresh_cycle(last_refresh_date, check_cycle):
                last_cycle_count = cycle_count
                last_refresh_date = self._get_formatted_time()
                cycle_count = 0
            else:
                last_cycle_count = event_def.get('stats',{}).get('last_cycle_count',0)

            target_type = event_def.get('properties',{}).get('target_type',None) # 决定了是不是要输入值，所以要保留的。
            target_value = event_def.get('properties',{}).get('target_value',0)

            if target_type:
                last_cycle_info = f'前一{check_cycle}的情况：{last_cycle_count}/{target_value}'
            else:
                last_cycle_info = f'前一{check_cycle}的情况：{last_cycle_count}'

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

        return {
            "user_id": user_id,
            "event_name": event_name,
            "event_definition": event_def, # 这里有一个问题是 definition里已经包含了上面处理的信息，只是没计算。所以最好这里传出去的都是处理好的原始信息？ 留给AI判断
            "new_record": new_record,
            "avg_duration": avg_duration,
            "degree_info": degree_info,
            "cycle_info": cycle_info,
        }

    def _calculate_average_duration(self, user_id: str, event_name: str) -> float:
        """
        计算事项的平均耗时
        """
        definitions_data = self._load_event_definitions(user_id)
        event_duration_records = definitions_data.get("definitions", {}).get(event_name, {}).get('stats',{}).get('duration',{}).get('recent_values',[])
        if not event_duration_records:
            return 0.0
        avg_duration = sum(event_duration_records) / len(event_duration_records)
        return avg_duration

    def _check_need_refresh_cycle(self, last_refresh_date: str, check_cycle: str) -> bool:
        """
        检查事项的检查周期是否需要刷新
        """
        if not check_cycle:
            return False
        if not last_refresh_date:
            return True
        last_refresh_date = datetime.strptime(last_refresh_date, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()

        match check_cycle:
            case RoutineCheckCycle.DAILY:
                return last_refresh_date.date() != now.date()
            case RoutineCheckCycle.WEEKLY:
                return last_refresh_date.isocalendar()[1] != now.isocalendar()[1] or last_refresh_date.year != now.year
            case RoutineCheckCycle.MONTHLY:
                return last_refresh_date.month != now.month or last_refresh_date.year != now.year
            case RoutineCheckCycle.SEASONALLY:
                last_season = (last_refresh_date.month - 1) // 3
                current_season = (now.month - 1) // 3
                return last_season != current_season or last_refresh_date.year != now.year
            case RoutineCheckCycle.YEARLY:
                return last_refresh_date.year != now.year
            case _:
                raise ValueError(f"不支持的 check_cycle: {check_cycle}")

    @safe_execute("处理数字选择失败")
    def process_number_selection(self, user_id: str, number: int, message_text: str) -> Optional[ProcessResult]:
        """
        处理数字选择回复

        Args:
            user_id: 用户ID
            number: 选择的数字
            message_text: 原始消息文本

        Returns:
            Optional[ProcessResult]: 处理结果，如果不是数字选择则返回None
        """
        # 检查是否是纯数字
        if not message_text.strip().isdigit():
            return None

        # 获取查询上下文
        query_context = self._get_query_context(user_id)
        last_query_type = query_context.get("last_query_type")
        last_query_results = query_context.get("last_query_results", [])
        last_query_time = query_context.get("last_query_time")

        # 检查查询上下文是否有效（5分钟内）
        if last_query_time:
            try:
                # 解析时间字符串
                query_time = datetime.strptime(last_query_time, "%Y-%m-%d %H:%M:%S")
                timeout = self.config_service.get("routine_record.query_context_timeout", 300)
                if (datetime.now() - query_time).total_seconds() > timeout:
                    return None
            except:
                return None

        # 处理不同类型的数字选择
        if last_query_type == "routine_list":
            return self._handle_routine_selection(user_id, number, last_query_results)
        elif last_query_type == "new_item_setup":
            return self._handle_new_item_type_selection(user_id, number, last_query_results)

        return None

    def _handle_routine_selection(self, user_id: str, number: int, routine_names: List[str]) -> ProcessResult:
        """处理事项选择"""
        if number < 1 or number > len(routine_names):
            return ProcessResult.error_result(f"无效选择，请输入 1-{len(routine_names)} 之间的数字")

        selected_routine = routine_names[number - 1]

        # 使用新架构加载数据
        definitions_data = self._load_event_definitions(user_id)
        records_data = self._load_event_records(user_id)

        if selected_routine not in definitions_data.get("definitions", {}):
            return ProcessResult.error_result("选择的事项不存在")

        event_def = definitions_data["definitions"][selected_routine]

        # 构建详细信息
        response_lines = [f"📋 {selected_routine} 详情："]
        response_lines.append(f"类型: {event_def.get('type', 'instant')}")

        if event_def["properties"].get("related_start_event"):
            response_lines.append(f"关联开始事件: {event_def['properties']['related_start_event']}")

        response_lines.append(f"加入日常检查清单: {'是' if event_def['properties'].get('include_in_daily_check', False) else '否'}")

        # 获取该事件的记录
        event_records = [r for r in records_data.get("records", []) if r["event_name"] == selected_routine]

        if event_records:
            # 按时间排序
            event_records.sort(key=lambda x: x["timestamp"], reverse=True)
            response_lines.append(f"\n📊 最近5次记录:")
            for record in event_records[:5]:
                timestamp = record["timestamp"]
                try:
                    if len(timestamp) >= 16:
                        time_str = f"{timestamp[5:10]} {timestamp[11:16]}"
                    else:
                        time_str = timestamp
                except:
                    time_str = "时间格式错误"
                response_lines.append(f"• {time_str}")
        else:
            response_lines.append("\n暂无记录")

        response_text = "\n".join(response_lines)
        return ProcessResult.success_result(ResponseTypes.TEXT, {"text": response_text})

    def _handle_new_item_type_selection(self, user_id: str, number: int, item_names: List[str]) -> ProcessResult:
        """处理新事项类型选择"""
        if not item_names:
            return ProcessResult.error_result("无效的事项设置状态")

        item_name = item_names[0]
        match number:
            case 1:
                item_type = RoutineTypes.INSTANT
                type_name = "瞬时事件"
            case 2:
                item_type = RoutineTypes.START
                type_name = "开始事件"
            case 3:
                item_type = RoutineTypes.END
                type_name = "结束事件"
            case _:
                return ProcessResult.error_result("无效选择，请输入 1-3 之间的数字")



        # 使用新架构创建事项
        definitions_data = self._load_event_definitions(user_id)
        records_data = self._load_event_records(user_id)

        current_time = self._get_formatted_time()

        # 创建新的事件定义（record_count从0开始）
        new_event_def = self._create_event_definition(item_name, item_type)
        new_event_def["created_time"] = current_time
        new_event_def["last_updated"] = current_time

        # 添加到definitions
        definitions_data["definitions"][item_name] = new_event_def

        # 创建首次记录（这时record_count是0，所以生成的ID是00001）
        record_id = self._get_next_record_id(user_id, item_name)
        new_record = self._create_event_record(item_name, user_id)
        new_record["record_id"] = record_id
        new_record["timestamp"] = current_time

        # 添加到records
        records_data["records"].append(new_record)

        # 现在更新record_count为1
        new_event_def["record_count"] = 1

        # 清除查询上下文
        self._clear_query_context(user_id)

        # 保存数据
        if self._save_event_definitions(user_id, definitions_data) and self._save_event_records(user_id, records_data):
            response_text = f"✅ 已创建 '{item_name}' ({type_name}) 并记录首次使用 - {current_time[11:16]}"
            return ProcessResult.success_result(ResponseTypes.TEXT, {"text": response_text})
        else:
            return ProcessResult.error_result("保存事项失败")

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

        card_data = self.build_quick_select_card_data(user_id)
        # 构建路由结果，指向routine卡片的快速选择模式
        route_result = RouteResult.create_route_result(
            route_type=RouteTypes.ROUTINE_QUICK_SELECT_CARD,
            route_params={
                "card_type": "quick_select_record",
                "business_data": card_data
            }
        )

        return route_result

    @safe_execute("构建快速选择记录卡片数据失败")
    def build_quick_select_card_data(self, user_id: str) -> Dict[str, Any]:
        """
        构建快速选择记录卡片数据

        Args:
            user_id: 用户ID
            operation_id: 操作ID

        Returns:
            Dict[str, Any]: 卡片数据
        """
        # 获取快速事项列表
        quick_events = self.get_quick_access_events(user_id, max_items=5)

        return {
            "user_id": user_id,
            "quick_events": quick_events
        }

    @safe_execute("获取快速事项列表失败")
    def get_quick_access_events(self, user_id: str, max_items: int = 5) -> List[Dict[str, Any]]:
        """
        获取用户的快速访问事项列表

        Args:
            user_id: 用户ID
            max_items: 最大返回数量

        Returns:
            List[Dict[str, Any]]: 快速事项列表
        """
        definitions_data = self._load_event_definitions(user_id)
        if not definitions_data:
            return []

        definitions = definitions_data.get("definitions", {})
        if not definitions:
            return []

        # 1. 先获取快捷访问事项（最多3个）
        quick_access_events = []
        recent_events = []

        for event_name, event_def in definitions.items():
            if event_def.get('properties', {}).get('quick_access', False):
                quick_access_events.append({
                    'name': event_name,
                    'type': event_def.get('type', RoutineTypes.INSTANT),
                    'properties': event_def.get('properties', {}),
                    'last_updated': event_def.get('last_updated', '')
                })
            else:
                recent_events.append({
                    'name': event_name,
                    'type': event_def.get('type', RoutineTypes.INSTANT),
                    'properties': event_def.get('properties', {}),
                    'last_updated': event_def.get('last_updated', '')
                })

        # 2. 按最后更新时间排序
        quick_access_events.sort(key=lambda x: x['last_updated'], reverse=True)
        recent_events.sort(key=lambda x: x['last_updated'], reverse=True)

        # 3. 组合结果：最多3个快捷访问 + 填充到5个的最近事项
        result = quick_access_events[:3]
        remaining_slots = max_items - len(result)

        if remaining_slots > 0:
            result.extend(recent_events[:remaining_slots])

        return result


    @safe_execute("处理事件创建业务逻辑失败")
    def create_new_event_from_form(self, user_id: str, form_data: Dict[str, Any]) -> Tuple[bool, str]:
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
            event_name = form_data.get('event_name', '').strip()
            if not event_name:
                return False, "事项名称不能为空"

            event_type = form_data.get('event_type', RoutineTypes.INSTANT)
            if type(event_type) != RoutineTypes:
                return False, "无效的事项类型"

            # 加载数据
            definitions_data = self._load_event_definitions(user_id)
            if event_name in definitions_data.get("definitions", {}):
                return False, f"事项 '{event_name}' 已存在"

            # 创建事件定义
            current_time = self._get_formatted_time()
            new_event_def = self._create_event_definition(event_name, event_type)

            # 更新属性
            new_event_def["category"] = form_data.get('category', '')
            new_event_def["description"] = form_data.get('notes', '')

            # 根据事项类型设置特定属性
            properties = new_event_def["properties"]

            if event_type == RoutineTypes.END:
                properties["related_start_event"] = form_data.get('related_start_event')

            if event_type in [RoutineTypes.INSTANT, RoutineTypes.ONGOING]:
                properties["include_in_daily_check"] = form_data.get('include_in_daily_check', False)

            if event_type == RoutineTypes.FUTURE:
                properties["future_date"] = form_data.get('future_date')

            if event_type != RoutineTypes.FUTURE:
                # 处理程度选项
                degree_options_str = form_data.get('degree_options', '').strip()
                if degree_options_str:
                    degree_options = [opt.strip() for opt in degree_options_str.split(',') if opt.strip()]
                    properties["has_degrees"] = len(degree_options) > 0
                    properties["degree_options"] = degree_options
                    if degree_options:
                        properties["default_degree"] = degree_options[0]

            # 保存数据
            definitions_data["definitions"][event_name] = new_event_def
            if self._save_event_definitions(user_id, definitions_data):
                return True, f"成功创建事项 '{event_name}'"
            else:
                return False, "保存事项失败"

        except Exception as e:
            debug_utils.log_and_print(f"创建事项失败: {e}", log_level="ERROR")
            return False, f"创建事项失败: {str(e)}"

    @safe_execute("处理记录创建业务逻辑失败")
    def create_record_from_form(self, user_id: str, event_name: str, form_data: Dict[str, Any]) -> Tuple[bool, str]:
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
            definitions_data = self._load_event_definitions(user_id)
            records_data = self._load_event_records(user_id)

            if event_name not in definitions_data.get("definitions", {}):
                return False, f"事项 '{event_name}' 不存在"

            # 创建新记录
            current_time = self._get_formatted_time()
            new_record = self._create_event_record(
                event_name=event_name,
                user_id=user_id,
                degree=form_data.get('selected_degree', ''),
                note=form_data.get('record_note', '')
            )

            # 添加记录
            records_data["records"].append(new_record)

            # 更新事件定义的统计信息
            event_def = definitions_data["definitions"][event_name]
            event_def["record_count"] = event_def.get("record_count", 0) + 1
            event_def["last_updated"] = current_time

            # 保存数据
            if self._save_event_definitions(user_id, definitions_data) and self._save_event_records(user_id, records_data):
                return True, f"成功记录 '{event_name}' - {current_time[11:16]}"
            else:
                return False, "保存记录失败"

        except Exception as e:
            debug_utils.log_and_print(f"创建记录失败: {e}", log_level="ERROR")
            return False, f"创建记录失败: {str(e)}"
