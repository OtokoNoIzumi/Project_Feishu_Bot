"""
配置服务

提供配置管理功能，用于处理配置文件的读取、更新等操作
原位置：Module/Core/config_service.py

支持多配置源：
1. 环境变量(.env) - 开发/生产环境差异配置
2. 静态配置(config.json) - 业务配置
3. 认证配置文件 - 通过环境变量AUTH_CONFIG_FILE_PATH指定的敏感信息文件

注意：适配conda虚拟环境项目架构，正确处理项目根路径
"""

import os
import json
import datetime
from typing import Dict, Any, Tuple, List, Optional
from dotenv import load_dotenv
from Module.Common.scripts.common import debug_utils


class ConfigService:
    """配置管理服务 - 支持环境变量、静态配置、认证配置多源"""

    def __init__(self, auth_config_file_path: str = "", static_config_file_path: str = "config.json", project_root_path: str = ""):
        """
        初始化配置服务

        Args:
            auth_config_file_path: 认证配置文件路径（动态、敏感信息）
            static_config_file_path: 静态配置文件路径（非敏感信息）
            project_root_path: 项目根路径（用于conda虚拟环境），如果为空则自动检测
        """
        # 获取项目根路径（与main_new.py保持一致的逻辑）
        self.project_root_path = self._get_project_root_path(project_root_path)

        # 加载环境变量（使用项目根路径，与main_new.py保持一致）
        self._load_env_variables()

        self.auth_config_file_path = auth_config_file_path
        self.static_config_file_path = static_config_file_path

        # 加载配置源
        self.env_config = self._load_env_config()
        self.auth_config = self._load_config(auth_config_file_path) if auth_config_file_path.strip() else {}
        self.static_config = self._load_config(self._resolve_config_path(static_config_file_path))

        # 合并配置：env_config > auth_config > static_config
        self.config = {**self.static_config, **self.auth_config, **self.env_config}

    def _get_project_root_path(self, provided_path: str = "") -> str:
        """
        获取项目根路径（模拟main_new.py的逻辑）

        Args:
            provided_path: 提供的路径，如果为空则自动检测

        Returns:
            str: 项目根路径
        """
        if provided_path:
            return os.path.normpath(provided_path)

        # 模拟main_new.py的路径检测逻辑
        try:
            # 检查是否在Jupyter环境
            is_not_jupyter = "__file__" in globals()

            if is_not_jupyter:
                # 常规Python环境
                current_dir = os.path.dirname(os.path.abspath(__file__))
                # 向上两级到项目根目录 (Module/Services -> Module -> 项目根)
                root_dir = os.path.normpath(os.path.join(current_dir, "..", ".."))
            else:
                # Jupyter环境
                current_dir = os.getcwd()
                root_dir = os.path.normpath(current_dir)

            return root_dir
        except:
            # fallback: 使用当前工作目录
            return os.getcwd()

    def _load_env_variables(self):
        """加载环境变量（与main_new.py保持一致的逻辑）"""
        env_file_path = os.path.join(self.project_root_path, ".env")
        if os.path.exists(env_file_path):
            load_dotenv(env_file_path, override=True)
            debug_utils.log_and_print(f"已加载环境变量文件: {env_file_path}", log_level="DEBUG")
        else:
            debug_utils.log_and_print(f"环境变量文件不存在: {env_file_path}", log_level="WARNING")

    def _resolve_config_path(self, config_path: str) -> str:
        """
        解析配置文件路径

        Args:
            config_path: 配置文件路径

        Returns:
            str: 完整的配置文件路径
        """
        if not config_path:
            return ""

        # 如果是相对路径，基于项目根路径解析
        if not os.path.isabs(config_path):
            return os.path.join(self.project_root_path, config_path)

        return config_path

    def _load_env_config(self) -> Dict[str, Any]:
        """
        加载环境变量配置

        Returns:
            Dict[str, Any]: 环境变量配置
        """
        env_config = {}

        # 定义需要从环境变量读取的配置项
        env_keys = [
            "AUTH_CONFIG_FILE_PATH",
            "FEISHU_APP_MESSAGE_ID",
            "FEISHU_APP_MESSAGE_SECRET",
            "COZE_API_KEY",
            "SERVER_ID",
            "ADMIN_ID",
            "FFMPEG_PATH"
        ]

        for key in env_keys:
            value = os.getenv(key)
            if value is not None:
                env_config[key] = value

        return env_config

    def _load_config(self, config_file_path: str) -> Dict[str, Any]:
        """
        加载配置

        Args:
            config_file_path: 配置文件路径

        Returns:
            Dict[str, Any]: 配置数据
        """
        try:
            if config_file_path and os.path.exists(config_file_path):
                with open(config_file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            debug_utils.log_and_print(f"加载配置失败 ({config_file_path}): {e}", log_level="ERROR")
        return {}

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置项，优先级：环境变量 > 认证配置 > 静态配置

        Args:
            key: 配置键
            default: 默认值

        Returns:
            Any: 配置值或默认值
        """
        # 最高优先级：环境变量
        if key in self.env_config:
            return self.env_config[key]

        # 中等优先级：认证配置
        if key in self.auth_config:
            return self.auth_config[key]

        # 最低优先级：静态配置
        if key in self.static_config:
            return self.static_config[key]

        return default

    def get_env(self, key: str, default: Any = None) -> Any:
        """
        直接获取环境变量

        Args:
            key: 环境变量名
            default: 默认值

        Returns:
            Any: 环境变量值或默认值
        """
        return os.getenv(key, default)

    def update_config(self, variable_name: str, new_value: str, validators: Dict[str, callable] = None) -> Tuple[bool, str]:
        """
        更新配置文件中指定变量的值
        敏感信息更新到auth_config_file，其他信息更新到static_config_file

        Args:
            variable_name: 要更新的变量名
            new_value: 变量的新值
            validators: 验证器字典 {变量名: 验证函数}

        Returns:
            Tuple[bool, str]: (更新是否成功, 回复消息)
        """
        # 验证输入
        if validators and variable_name in validators:
            is_valid, err_msg = validators[variable_name](new_value)
            if not is_valid:
                return False, f"'{variable_name}' 更新失败: {err_msg}"

        # 环境变量不允许通过此方法更新
        env_keys = ["AUTH_CONFIG_FILE_PATH", "FEISHU_APP_MESSAGE_ID", "FEISHU_APP_MESSAGE_SECRET",
                   "COZE_API_KEY", "SERVER_ID", "ADMIN_ID", "FFMPEG_PATH"]
        if variable_name in env_keys:
            return False, f"'{variable_name}' 是环境变量，请在.env文件中修改"

        # 确定更新目标文件
        sensitive_vars = ["cookies", "auth_token"]  # 敏感变量列表
        if variable_name in sensitive_vars:
            target_file = self.auth_config_file_path
            target_config = self.auth_config
        else:
            target_file = self._resolve_config_path(self.static_config_file_path)
            target_config = self.static_config

        if not target_file.strip():
            return False, f"未配置目标配置文件路径"

        try:
            # 加载目标配置文件
            config_data = self._load_config(target_file)

            if variable_name in config_data and config_data[variable_name] == new_value:
                return False, f"变量 '{variable_name}' 的新值与旧值相同，无需更新。"

            config_data[variable_name] = new_value

            # 如果是敏感配置，添加过期时间
            if variable_name in sensitive_vars:
                current_time = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
                expires_at_time = current_time + datetime.timedelta(hours=8)
                config_data["expires_at"] = expires_at_time.isoformat()

            # 保存到目标文件
            with open(target_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)

            # 更新内存中的配置
            if variable_name in sensitive_vars:
                self.auth_config = config_data
            else:
                self.static_config = config_data

            # 重新合并配置
            self.config = {**self.static_config, **self.auth_config, **self.env_config}

            expires_msg = ""
            if variable_name in sensitive_vars and "expires_at" in config_data:
                expires_msg = f"，令牌有效至 {expires_at_time.strftime('%Y-%m-%d %H:%M')}"

            return True, f"'{variable_name}' 已成功更新{expires_msg}"

        except FileNotFoundError:
            return False, f"配置文件 '{target_file}' 未找到，更新失败。"
        except json.JSONDecodeError:
            return False, f"配置文件 '{target_file}' JSON 格式错误，更新失败。"
        except Exception as e:
            return False, f"更新配置文件时发生未知错误: {e}"

    # 新增：简单的状态查询方法（为后续API做准备）
    def get_status(self) -> Dict[str, Any]:
        """获取配置服务状态信息"""
        env_file_path = os.path.join(self.project_root_path, ".env")

        return {
            "project_root_path": self.project_root_path,
            "env_file_path": env_file_path,
            "env_file_exists": os.path.exists(env_file_path),
            "static_config_path": self._resolve_config_path(self.static_config_file_path),
            "auth_config_path": self.auth_config_file_path,
            "static_config_exists": os.path.exists(self._resolve_config_path(self.static_config_file_path)) if self.static_config_file_path else False,
            "auth_config_exists": os.path.exists(self.auth_config_file_path) if self.auth_config_file_path.strip() else False,
            "env_config_keys": list(self.env_config.keys()),
            "static_config_keys": list(self.static_config.keys()),
            "auth_config_keys": list(self.auth_config.keys()),
            "total_config_keys": len(self.config),
            "config_priority": "env_vars > auth_config > static_config"
        }

    def get_safe_config(self) -> Dict[str, Any]:
        """获取安全的配置信息（不包含敏感信息）"""
        # 敏感键列表
        sensitive_keys = ["cookies", "auth_token", "expires_at", "password", "secret", "key", "api_key", "app_secret"]

        safe_config = {}

        # 处理静态配置
        for key, value in self.static_config.items():
            is_sensitive = any(sensitive_key in key.lower() for sensitive_key in sensitive_keys)
            if not is_sensitive:
                safe_config[f"static.{key}"] = value
            else:
                safe_config[f"static.{key}"] = "***" if value else None

        # 处理环境变量（隐藏敏感信息）
        for key, value in self.env_config.items():
            is_sensitive = any(sensitive_key in key.lower() for sensitive_key in sensitive_keys)
            if not is_sensitive:
                safe_config[f"env.{key}"] = value
            else:
                safe_config[f"env.{key}"] = "***" if value else None

        return safe_config

    def reload_all_configs(self) -> Tuple[bool, str]:
        """重新加载所有配置文件"""
        try:
            # 重新加载环境变量
            self._load_env_variables()

            # 重新加载配置
            self.env_config = self._load_env_config()
            self.auth_config = self._load_config(self.auth_config_file_path) if self.auth_config_file_path.strip() else {}
            self.static_config = self._load_config(self._resolve_config_path(self.static_config_file_path))

            # 重新合并配置
            self.config = {**self.static_config, **self.auth_config, **self.env_config}

            return True, "所有配置文件已重新加载（包括环境变量）"
        except Exception as e:
            return False, f"重新加载配置失败: {str(e)}"

    def validate_config(self) -> Dict[str, Any]:
        """验证配置完整性"""
        result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "summary": {}
        }

        # 检查关键配置项
        required_keys = ["log_level"]
        for key in required_keys:
            if key not in self.config:
                result["errors"].append(f"缺少必需配置项: {key}")
                result["valid"] = False

        # 检查重要的环境变量
        important_env_vars = ["FEISHU_APP_MESSAGE_ID", "FEISHU_APP_MESSAGE_SECRET"]
        for var in important_env_vars:
            if not os.getenv(var):
                result["warnings"].append(f"重要环境变量未设置: {var}")

        # 检查文件路径
        static_config_full_path = self._resolve_config_path(self.static_config_file_path)
        if self.static_config_file_path and not os.path.exists(static_config_full_path):
            result["warnings"].append(f"静态配置文件不存在: {static_config_full_path}")

        if self.auth_config_file_path.strip() and not os.path.exists(self.auth_config_file_path):
            result["warnings"].append(f"认证配置文件不存在: {self.auth_config_file_path}")

        # 检查.env文件
        env_file_path = os.path.join(self.project_root_path, ".env")
        if not os.path.exists(env_file_path):
            result["warnings"].append(f"环境变量文件不存在: {env_file_path}")

        # 汇总信息
        result["summary"] = {
            "total_keys": len(self.config),
            "env_keys": len(self.env_config),
            "static_keys": len(self.static_config),
            "auth_keys": len(self.auth_config),
            "files_loaded": {
                "env": os.path.exists(env_file_path),
                "static": os.path.exists(static_config_full_path) if self.static_config_file_path else False,
                "auth": os.path.exists(self.auth_config_file_path) if self.auth_config_file_path.strip() else False
            }
        }

        return result

    def get_config_source(self, key: str) -> Optional[str]:
        """
        获取配置项的来源

        Args:
            key: 配置键

        Returns:
            Optional[str]: 配置来源 ("env", "auth", "static") 或 None
        """
        if key in self.env_config:
            return "env"
        elif key in self.auth_config:
            return "auth"
        elif key in self.static_config:
            return "static"
        else:
            return None

    def get_project_info(self) -> Dict[str, Any]:
        """
        获取项目环境信息（用于调试和规范化）

        Returns:
            Dict[str, Any]: 项目环境信息
        """
        return {
            "project_root_path": self.project_root_path,
            "env_file_path": os.path.join(self.project_root_path, ".env"),
            "python_version": f"{os.sys.version_info.major}.{os.sys.version_info.minor}.{os.sys.version_info.micro}",
            "working_directory": os.getcwd(),
            "config_service_location": __file__ if "__file__" in globals() else "未知",
            "conda_env": os.getenv("CONDA_DEFAULT_ENV", "未知"),
            "virtual_env": os.getenv("VIRTUAL_ENV", "无")
        }