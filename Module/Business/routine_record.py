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
from Module.Services.constants import ServiceNames, ResponseTypes, RoutineTypes
from Module.Business.processors.base_processor import BaseProcessor, ProcessResult, require_service, safe_execute


class RoutineRecord(BaseProcessor):
    """
    日常事项记录业务

    负责处理日常事项记录的完整业务流程，支持：
    - 事件定义与记录分离
    - 复杂属性管理（分类、程度、关联等）
    - 适配器无关的数据模型
    - 向后兼容
    """

    def __init__(self, app_controller):
        """初始化日常事项记录业务"""
        super().__init__(app_controller)
        self.config_service = self.app_controller.get_service(ServiceNames.CONFIG)
        self.user_permission_service = self.app_controller.get_service(ServiceNames.USER_BUSINESS_PERMISSION)

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
            "event_id": str(uuid.uuid4()),
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
                "check_cycle": "daily",
                "custom_cycle_config": None,

                # 程度/层次属性
                "has_degrees": False,
                "degree_options": [],
                "default_degree": None,

                # 时间属性
                "future_date": None,
                "estimated_duration": None,

                # 目标属性
                "target_type": None, #次数/时长
                "target_value": None #目标值
            },
            "created_time": current_time,
            "record_count": 0, # 避免聚合方法？最多也要每天一次聚合避免膨胀？
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
        count = definitions_data.get("definitions", {}).get(event_name, {}).get("record_count", 0)

        # 生成新的序号（从00001开始）
        next_num = count + 1
        return f"{event_name}_{next_num:05d}"

    def _create_event_record(self, event_id: str, event_name: str, user_id: str, degree: str = None, note: str = "", related_records: List[str] = None) -> Dict[str, Any]:
        """
        创建事件记录

        Args:
            event_id: 事件定义ID
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
            "event_id": event_id,
            "event_name": event_name,
            "timestamp": current_time,
            "degree": degree,
            "note": note,
            "related_records": related_records or [],
            "location": None,
            "duration": None
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
                # 大概就是这里，其实没必要一来Route，再由前端回调process_routine_create；而是自己处理完业务之后返回结果信息给前端。，由前端去触发sender。
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

    @safe_execute("处理事项创建失败")
    def process_routine_create(self, user_id: str, item_name: str) -> ProcessResult:
        """
        处理事项创建或记录

        Args:
            user_id: 用户ID
            item_name: 事项名称

        Returns:
            ProcessResult: 处理结果
        """
        # 检查权限
        if not self.check_user_permission(user_id):
            return ProcessResult.error_result("您暂无使用日常事项记录功能的权限")

        # 直接使用新架构加载数据
        definitions_data = self._load_event_definitions(user_id)
        records_data = self._load_event_records(user_id)

        if not definitions_data:
            return ProcessResult.error_result("加载事件定义失败")

        current_time = self._get_formatted_time()

        # 检查事项是否已存在
        if item_name in definitions_data.get("definitions", {}):
            # 事项已存在，直接记录
            event_def = definitions_data["definitions"][item_name]
            event_id = event_def["event_id"]

            # 创建新记录
            record_id = self._get_next_record_id(user_id, item_name)
            new_record = self._create_event_record(event_id, item_name, user_id)
            new_record["record_id"] = record_id
            new_record["timestamp"] = current_time

            # 添加记录到records_data
            records_data["records"].append(new_record)

            # 更新事件定义的记录计数和最后更新时间
            event_def["record_count"] = event_def.get("record_count", 0) + 1
            event_def["last_updated"] = current_time

            # 保存数据
            if self._save_event_definitions(user_id, definitions_data) and self._save_event_records(user_id, records_data):
                response_text = f"✅ 已记录 '{item_name}' - {current_time[11:16]}"  # 只显示时分
                return ProcessResult.success_result(ResponseTypes.TEXT, {"text": response_text})
            else:
                return ProcessResult.error_result("保存记录失败")

        else:
            # 新事项，需要设置属性
            response_text = f"🆕 检测到新事项 '{item_name}'\n\n请选择事项类型：\n1. 瞬时事件（如：吃维生素D）\n2. 开始事件（如：开始工作）\n3. 结束事件（如：洗完澡）\n\n请回复数字选择"

            # 设置查询上下文用于后续处理
            self._set_query_context(user_id, "new_item_setup", [item_name])

            return ProcessResult.success_result(ResponseTypes.TEXT, {"text": response_text})

    @safe_execute("处理查询请求失败")
    def process_routine_query(self, user_id: str) -> ProcessResult:
        """
        处理事项查询

        Args:
            user_id: 用户ID

        Returns:
            ProcessResult: 处理结果
        """
        # 检查权限
        if not self.check_user_permission(user_id):
            return ProcessResult.error_result("您暂无使用日常事项记录功能的权限")

        # 直接使用新架构加载数据
        definitions_data = self._load_event_definitions(user_id)
        records_data = self._load_event_records(user_id)

        if not definitions_data:
            return ProcessResult.error_result("加载事件定义失败")

        definitions = definitions_data.get("definitions", {})

        if not definitions:
            return ProcessResult.success_result(ResponseTypes.TEXT, {"text": "📝 您还没有任何日常事项记录\n\n使用 'r 事项名称' 或 '日程 事项名称' 来创建第一个记录"})

        # 获取最近活动的事项（按最后更新时间排序）
        max_items = self.config_service.get("routine_record.max_recent_items", 10)

        sorted_definitions = sorted(
            definitions.items(),
            key=lambda x: x[1].get("last_updated", ""),
            reverse=True
        )[:max_items]

        # 构建查询结果
        response_lines = ["📋 最近的日常事项：\n"]

        routine_names = []
        for i, (event_name, event_def) in enumerate(sorted_definitions, 1):
            # 查找该事件的最新记录
            event_records = [r for r in records_data.get("records", []) if r["event_name"] == event_name]

            if event_records:
                # 按时间排序，取最新的
                event_records.sort(key=lambda x: x["timestamp"], reverse=True)
                last_time = event_records[0]["timestamp"]
                # 提取月日时分显示
                try:
                    if len(last_time) >= 16:  # "2025-07-10 09:07:30"
                        time_str = f"{last_time[5:10]} {last_time[11:16]}"  # "07-10 09:07"
                    else:
                        time_str = last_time
                except:
                    time_str = "时间格式错误"
            else:
                time_str = "无记录"

            event_type = event_def.get("type", "instant")
            type_emoji = {"instant": "⚡", "start": "▶️", "end": "⏹️", "ongoing": "🔄", "future": "📅"}.get(event_type, "📝")

            response_lines.append(f"{i}. {type_emoji} {event_name} (最近: {time_str})")
            routine_names.append(event_name)

        response_lines.append("\n💡 回复数字查看详情，或发送新指令")

        # 设置查询上下文
        self._set_query_context(user_id, "routine_list", routine_names)

        response_text = "\n".join(response_lines)
        return ProcessResult.success_result(ResponseTypes.TEXT, {"text": response_text})

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
        new_record = self._create_event_record(new_event_def["event_id"], item_name, user_id)
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
