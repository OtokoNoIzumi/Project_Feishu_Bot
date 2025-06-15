"""
管理员处理器

处理配置更新、系统管理等管理员专用功能
"""

from .base_processor import BaseProcessor, MessageContext, ProcessResult


class AdminProcessor(BaseProcessor):
    """
    管理员处理器

    处理管理员专用的功能
    """

    def __init__(self, app_controller=None):
        """初始化管理员处理器"""
        super().__init__(app_controller)
        self._load_config()

    def _load_config(self):
        """加载配置"""
        if self.app_controller:
            # 从配置服务获取配置
            config_service = self.app_controller.get_service('config')
            if config_service:
                # 获取管理员ID - 优先从环境变量获取
                self.admin_id = config_service.get_env("ADMIN_ID", "")
                if not self.admin_id:
                    # 如果环境变量没有，尝试从配置文件获取
                    self.admin_id = config_service.get("admin_id", "")

                # 获取更新触发器配置
                self.update_config_trigger = config_service.get("update_config_trigger", "whisk令牌")
            else:
                # 配置服务不可用，使用默认值
                self.admin_id = ''
                self.update_config_trigger = 'whisk令牌'
        else:
            # 默认配置
            self.admin_id = ''
            self.update_config_trigger = 'whisk令牌'

    def handle_config_update(self, context: MessageContext, user_msg: str) -> ProcessResult:
        """处理配置更新指令"""
        # 验证管理员权限
        if context.user_id != self.admin_id:
            return ProcessResult.success_result("text", {
                "text": f"收到消息：{user_msg}"
            }, parent_id=context.message_id)

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
        if not self.app_controller:
            return ProcessResult.error_result("系统服务不可用")

        image_service = self.app_controller.get_service('image')
        if not image_service:
            return ProcessResult.error_result("图像服务不可用")

        try:
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

        except Exception as e:
            return ProcessResult.error_result(f"配置更新失败: {str(e)}")

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

    def is_admin_command(self, user_msg: str) -> bool:
        """检查是否是管理员指令"""
        return user_msg.startswith(self.update_config_trigger)

    def get_update_trigger(self) -> str:
        """获取更新触发器"""
        return self.update_config_trigger