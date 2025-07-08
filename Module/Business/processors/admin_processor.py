"""
管理员处理器

处理所有需要管理员权限的命令和操作
"""

from typing import Dict, Any
from .base_processor import BaseProcessor, MessageContext, ProcessResult, require_service, safe_execute, require_app_controller
from Module.Common.scripts.common import debug_utils
from Module.Services.constants import (
    ServiceNames, OperationTypes, DefaultActions, EnvVars,
    ConfigKeys, DefaultValues, CardActions
)


class AdminProcessor(BaseProcessor):
    """
    管理员处理器

    处理管理员专用的功能
    """

    def __init__(self, app_controller=None):
        """初始化管理员处理器"""
        super().__init__(app_controller)
        self._load_config()
        self._register_pending_operations()

    @property
    def card_mapping_service(self):
        """获取卡片业务映射服务"""
        if self.app_controller:
            return self.app_controller.get_service(ServiceNames.CARD_OPERATION_MAPPING)
        return None

    def _load_config(self):
        """加载配置"""
        # 统一默认值
        self.admin_id = DefaultValues.EMPTY_STRING
        self.update_config_trigger = DefaultValues.DEFAULT_UPDATE_TRIGGER

        if not self.app_controller:
            return

        config_service = self.app_controller.get_service(ServiceNames.CONFIG)
        if not config_service:
            return

        # 获取管理员ID - 优先从环境变量获取，否则用配置文件
        self.admin_id = config_service.get_env(EnvVars.ADMIN_ID, self.admin_id)
        if not self.admin_id:
            self.admin_id = config_service.get(ConfigKeys.ADMIN_ID, self.admin_id)

        # 获取更新触发器配置
        self.update_config_trigger = config_service.get(ConfigKeys.UPDATE_CONFIG_TRIGGER, self.update_config_trigger)

    def _register_pending_operations(self):
        """注册缓存操作执行器"""
        if self.app_controller:
            pending_cache_service = self.app_controller.get_service(ServiceNames.PENDING_CACHE)
            if pending_cache_service:
                # 注册用户更新操作执行器
                pending_cache_service.register_executor(
                    OperationTypes.UPDATE_USER,
                    self._execute_user_update_operation
                )
                # 注册广告更新操作执行器
                pending_cache_service.register_executor(
                    OperationTypes.UPDATE_ADS,
                    self._execute_ads_update_operation
                )

    def is_admin_command(self, user_msg: str) -> bool:
        """检查是否是管理员指令"""
        admin_commands = [
            self.update_config_trigger,
            "更新用户",
            "更新广告"
        ]
        return any(user_msg.startswith(cmd) for cmd in admin_commands)

    def handle_admin_command(self, context: MessageContext, user_msg: str) -> ProcessResult:
        """处理管理员命令（统一入口）"""
        # 验证管理员权限
        if context.user_id != self.admin_id:
            return ProcessResult.success_result("text", {
                "text": f"收到消息：{user_msg}"
            }, parent_id=context.message_id)

        # 根据命令类型分发处理
        if user_msg.startswith(self.update_config_trigger):
            return self.handle_config_update(context, user_msg)
        elif user_msg.startswith("更新用户"):
            return self.handle_update_user_command(context, user_msg)
        elif user_msg.startswith("更新广告"):
            return self.handle_update_ads_command(context, user_msg)
        else:
            return ProcessResult.error_result("未知的管理员命令")

    @safe_execute("更新用户命令解析失败")
    def handle_update_user_command(self, context: MessageContext, user_msg: str) -> ProcessResult:
        """处理更新用户命令"""
        # 解析命令: "更新用户 696423 支持者" 或 "更新用户 696423 1"
        parts = user_msg.split()
        if len(parts) != 3:
            return ProcessResult.error_result(
                "格式错误，请使用：更新用户 <用户ID> <账户类型>\n"
                "账户类型可以是：普通用户/0, 支持者/1, 受邀用户/2"
            )

        uid = parts[1]
        account_type_input = parts[2]

        # 解析账户类型
        account_type_map = {
            "普通用户": 0, "0": 0,
            "支持者": 1, "1": 1,
            "受邀用户": 2, "2": 2
        }

        if account_type_input not in account_type_map:
            return ProcessResult.error_result(
                "无效的账户类型，支持的类型：普通用户/0, 支持者/1, 受邀用户/2"
            )

        account_type = account_type_map[account_type_input]

        # 使用配置化的缓存服务创建确认操作
        return self._create_pending_operation(
            context=context,
            operation_type=OperationTypes.UPDATE_USER,
            business_data={
                'user_id': uid,
                'user_type': account_type,
                'admin_input': ' '.join(parts[1:])
            }
        )

    @safe_execute("更新广告命令解析失败")
    def handle_update_ads_command(self, context: MessageContext, user_msg: str) -> ProcessResult:
        """处理更新广告命令"""
        # 解析命令: "更新广告 BVID1122 06:55 - 07:57, 14:53 - 15:05" 或 "更新广告 BVID1122 " (清除广告)
        parts = user_msg.split(maxsplit=2)
        if len(parts) < 2:
            return ProcessResult.error_result(
                "格式错误，请使用：更新广告 <BVID> [广告时间戳]\n"
                "例如：更新广告 BVID1122 06:55 - 07:57, 14:53 - 15:05\n"
                "或：更新广告 BVID1122 (不写时间戳，清除广告区间)"
            )

        bvid = parts[1]
        # 支持空字符串时间戳（清除广告区间）
        adtime_stamps = parts[2] if len(parts) == 3 else ""

        # 验证BVID格式（简单验证）
        if not bvid.strip():
            return ProcessResult.error_result("BVID不能为空")

        # 数据预处理
        # 1. 全角逗号转换
        if adtime_stamps:
            adtime_stamps = adtime_stamps.replace('，', ',').strip()

        # 2. 合规化预检验——先不实现，后续看情况改成自动化处理，不要拒绝操作

        # 使用配置化的缓存服务创建确认操作
        return self._create_pending_operation(
            context=context,
            operation_type=OperationTypes.UPDATE_ADS,
            business_data={
                'bvid': bvid.strip(),
                'adtime_stamps': adtime_stamps,
                'admin_input': user_msg
            }
        )

    @require_app_controller("应用控制器不可用")
    @require_service(ServiceNames.PENDING_CACHE, "缓存业务服务不可用")
    @safe_execute("创建待处理操作失败")
    def _create_pending_operation(
        self, context: MessageContext,
        operation_type: str, business_data: Dict[str, Any]
    ) -> ProcessResult:
        """
        创建待处理操作（配置化通用方法）

        Args:
            context: 消息上下文
            operation_type: 业务标识 (如 'update_user', 'update_ads')
            business_data: 操作数据

        Returns:
            ProcessResult: 处理结果
        """
        pending_cache_service = self.app_controller.get_service(ServiceNames.PENDING_CACHE)

        # 从卡片业务映射配置获取配置信息
        config = self.card_mapping_service.get_operation_config(operation_type)
        if not config:
            return ProcessResult.error_result(f"未找到业务配置: {operation_type}")

        # 从配置获取超时时间和响应类型
        timeout_seconds = config.get("timeout_seconds", 30)
        response_type = config.get("response_type", "")
        default_action = config.get("default_action", DefaultActions.CONFIRM)

        if not response_type:
            return ProcessResult.error_result(f"业务 {operation_type} 缺少响应类型配置")

        timeout_text = self._format_timeout_text(timeout_seconds)

        # 准备完整的操作数据
        full_operation_data = {
            **business_data,  # 合并传入的业务数据
            'finished': False,
            'result': '确认⏰',
            'hold_time': timeout_text,
            'operation_type': operation_type
        }

        # 创建缓存操作
        operation_id = pending_cache_service.create_operation(
            user_id=context.user_id,
            operation_data=full_operation_data,
            admin_input=full_operation_data.get('admin_input', ''),
            hold_time_seconds=timeout_seconds,
            default_action=default_action
        )

        # 添加操作ID到数据中
        full_operation_data['operation_id'] = operation_id

        # 使用配置化的响应类型返回结果
        return ProcessResult.success_result(
            response_type,
            full_operation_data,
            parent_id=context.message_id
        )

    @require_service(ServiceNames.BILI_ADSKIP, "B站广告跳过服务不可用")
    @safe_execute("执行用户更新操作失败")
    def _execute_user_update_operation(self, operation) -> bool:
        """
        执行用户更新操作（缓存服务回调）

        Args:
            operation: PendingOperation对象

        Returns:
            bool: 是否执行成功
        """
        try:
            user_id = operation.operation_data.get('user_id')
            # 注意：user_type=0 是合法的，这里不能用 if not user_type
            user_type = operation.operation_data.get('user_type')

            if not user_id or user_type is None:
                debug_utils.log_and_print("❌ 用户更新操作缺少必要参数", log_level="ERROR")
                return False

            # 获取bili_adskip_service
            bili_service = self.app_controller.get_service(ServiceNames.BILI_ADSKIP)

            # 调用bili_adskip_service的用户更新方法
            success, response_data = bili_service.update_user_status(user_id, user_type)

            if success:
                debug_utils.log_and_print(f"✅ 用户 {user_id} 状态更新成功 {response_data.get('message', '')}", log_level="INFO")
                return True
            else:
                error_msg = response_data.get("message", "未知错误") if response_data else "API调用失败"
                debug_utils.log_and_print(f"❌ 用户 {user_id} 状态更新失败: {error_msg}", log_level="ERROR")
                return False

        except Exception as e:
            debug_utils.log_and_print(f"❌ 执行用户更新操作异常: {e}", log_level="ERROR")
            return False

    @require_service(ServiceNames.BILI_ADSKIP, "B站广告跳过服务不可用")
    @safe_execute("执行广告更新操作失败")
    def _execute_ads_update_operation(self, operation) -> bool:
        """
        执行广告更新操作（缓存服务回调）

        Args:
            operation: PendingOperation对象

        Returns:
            bool: 是否执行成功
        """
        try:
            bvid = operation.operation_data.get('bvid')
            adtime_stamps = operation.operation_data.get('adtime_stamps', '')

            # 注意：adtime_stamps 可以为空字符串（清除广告区间）
            if not bvid:
                debug_utils.log_and_print("❌ 广告更新操作缺少BVID参数", log_level="ERROR")
                return False

            # 获取bili_adskip_service
            bili_service = self.app_controller.get_service(ServiceNames.BILI_ADSKIP)

            # 调用bili_adskip_service的广告更新方法
            success, response_data = bili_service.update_ads_timestamps(bvid, adtime_stamps)

            if success:
                debug_utils.log_and_print(f"✅ 广告 {bvid} 时间戳更新成功 {response_data.get('message', '')}", log_level="INFO")
                return True
            else:
                error_msg = response_data.get("message", "未知错误") if response_data else "API调用失败"
                debug_utils.log_and_print(f"❌ 广告 {bvid} 时间戳更新失败: {error_msg}", log_level="ERROR")
                return False

        except Exception as e:
            debug_utils.log_and_print(f"❌ 执行广告更新操作异常: {e}", log_level="ERROR")
            return False

    @require_app_controller("应用控制器不可用")
    @require_service(ServiceNames.PENDING_CACHE, "缓存业务服务不可用")
    @safe_execute("处理缓存操作确认失败")
    def handle_pending_operation_action(self, action_value: Dict[str, Any]) -> ProcessResult:
        """
        处理缓存操作的确认、取消等动作

        Args:
            context: 消息上下文
            action_value: 动作参数

        Returns:
            ProcessResult: 处理结果
        """
        pending_cache_service = self.app_controller.get_service(ServiceNames.PENDING_CACHE)

        card_action = action_value.get('card_action', '')
        operation_id = action_value.get('operation_id', '')

        if not operation_id:
            return ProcessResult.error_result("缺少操作ID")

        operation = pending_cache_service.get_operation(operation_id)
        if not operation:
            return ProcessResult.error_result("操作不存在")
        card_update_response_type = action_value.get('process_result_type', '')

        match card_action:
            case CardActions.CONFIRM_USER_UPDATE | CardActions.CONFIRM_ADS_UPDATE:
                # 确认操作（统一处理，出于敏捷考虑是不是应该先响应前端？）
                success = pending_cache_service.confirm_operation(operation_id)

                if success:
                    # 构建成功的卡片更新数据
                    result_data = operation.operation_data.copy()
                    result_data.update({
                        'finished': True,
                        'hold_time': '',
                        'result': " | 已完成",
                        'result_type': 'success'
                    })

                    return ProcessResult.success_result(
                        card_update_response_type,
                        result_data
                    )

                # 构建失败的卡片更新数据
                result_data = operation.operation_data.copy()
                result_data.update({
                    'finished': True,
                    'result': " | ❌ 执行失败",
                    'result_type': 'error'
                })

                return ProcessResult.success_result(
                    card_update_response_type,
                    result_data
                )
            case CardActions.CANCEL_USER_UPDATE | CardActions.CANCEL_ADS_UPDATE:
                # 取消操作（统一处理）
                success = pending_cache_service.cancel_operation(operation_id)

                # 构建取消的卡片更新数据
                result_data = operation.operation_data.copy()
                result_data.update({
                    'finished': True,
                    'hold_time': '',
                    'result': " | 操作取消",
                    'result_type': 'info'
                })

                return ProcessResult.success_result(
                    card_update_response_type,
                    result_data
                )
            case CardActions.ADTIME_EDITOR_CHANGE:
                # 处理广告时间戳编辑器变更
                new_adtime_stamps = action_value.get('value', '')

                # 全角逗号转换处理
                if new_adtime_stamps:
                    new_adtime_stamps = new_adtime_stamps.replace('，', ',').strip()

                # 更新操作数据
                success = pending_cache_service.update_operation_data(
                    operation_id,
                    {'adtime_stamps': new_adtime_stamps}
                )

                if success:
                    # 返回静默成功响应（编辑器交互不需要Toast）
                    return ProcessResult.no_reply_result()
                else:
                    return ProcessResult.error_result("时间戳更新失败")
            case "update_data":
                # 更新操作数据，占位的无效内容【待清理
                new_data = action_value.get('new_data', {})
                pending_cache_service.update_operation_data(operation_id, new_data)

                # 返回简单成功响应（不需要更新卡片）
                return ProcessResult.success_result("toast", {
                    "message": "数据已更新",
                    "type": "success"
                })
            case _:
                return ProcessResult.error_result(f"未知的操作类型: {card_action}")

    @require_service(ServiceNames.IMAGE, "图像服务不可用")
    @safe_execute("配置更新失败")
    def handle_config_update(self, context: MessageContext, user_msg: str) -> ProcessResult:
        """处理配置更新指令"""
        # 解析配置更新指令
        command_parts = user_msg[len(self.update_config_trigger):].strip().split(maxsplit=1)
        if len(command_parts) != 2:
            return ProcessResult.error_result(
                f"格式错误，请使用 '{self.update_config_trigger} 变量名 新值' 格式，"
                f"例如：{self.update_config_trigger} cookies xxxx"
            )

        variable_name, new_value = command_parts

        # 检查是否为支持的变量
        supported_variables = ["cookies", "auth_token"]
        if variable_name not in supported_variables:
            return ProcessResult.error_result(
                f"不支持更新变量 '{variable_name}'，"
                f"只能更新: {', '.join(supported_variables)}"
            )

        # 使用图像服务的原生API更新配置
        image_service = self.app_controller.get_service(ServiceNames.IMAGE)

        # 验证输入
        if variable_name == "cookies":
            is_valid, err_msg = self._verify_cookie(new_value)
        elif variable_name == "auth_token":
            is_valid, err_msg = self._verify_auth_token(new_value)
        else:
            is_valid, err_msg = False, "不支持的变量类型"

        if not is_valid:
            return ProcessResult.error_result(f"'{variable_name}' 更新失败: {err_msg}")

        # 调用图像服务的原生API更新配置
        result = image_service.update_auth_config(variable_name, new_value)

        if result.get("success", False):
            return ProcessResult.success_result("text", {
                "text": result.get("message", f"'{variable_name}' 更新成功")
            }, parent_id=context.message_id)
        else:
            return ProcessResult.error_result(result.get("message", "更新失败"))

    def _verify_cookie(self, cookie_value: str) -> tuple[bool, str]:
        """验证Cookie格式"""
        if not cookie_value or len(cookie_value.strip()) < 10:
            return False, "Cookie值太短，请检查格式"
        return True, "Cookie格式验证通过"

    def _verify_auth_token(self, auth_token_value: str) -> tuple[bool, str]:
        """验证认证Token格式"""
        if not auth_token_value or len(auth_token_value.strip()) < 10:
            return False, "认证Token值太短，请检查格式"
        return True, "认证Token格式验证通过"

    def get_update_trigger(self) -> str:
        """获取更新触发器"""
        return self.update_config_trigger

    def _format_timeout_text(self, seconds: int) -> str:
        """
        格式化超时时间文本

        Args:
            seconds: 秒数

        Returns:
            str: 格式化的时间文本
        """
        if seconds < 60:
            return f"({seconds}s)"
        elif seconds < 3600:
            minutes = seconds // 60
            remaining_seconds = seconds % 60
            if remaining_seconds > 0:
                return f"({minutes}分{remaining_seconds}秒)"
            else:
                return f"({minutes}分)"
        else:
            hours = seconds // 3600
            remaining_minutes = (seconds % 3600) // 60
            if remaining_minutes > 0:
                return f"({hours}时{remaining_minutes}分)"
            else:
                return f"({hours}时)"
