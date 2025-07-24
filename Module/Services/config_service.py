"""
配置服务

提供配置管理功能，用于处理配置文件的读取、更新等操作
原位置：Module/Core/config_service.py

支持多配置源：
1. 环境变量(.env) - 开发/生产环境差异配置
2. 静态配置(config.json) - 业务配置

注意：适配conda虚拟环境项目架构，正确处理项目根路径
"""

import os
import json
import datetime
from typing import Dict, Any, Tuple, List, Optional
from dotenv import load_dotenv
from Module.Common.scripts.common import debug_utils
from .service_decorators import file_processing_safe


class ConfigService:
    """配置管理服务 - 支持环境变量、静态配置多源"""

    def __init__(self, static_config_file_path: str = "config.json", project_root_path: str = ""):
        """
        初始化配置服务

        Args:
            static_config_file_path: 静态配置文件路径（非敏感信息）
            project_root_path: 项目根路径（用于conda虚拟环境），如果为空则自动检测
        """
        # 获取项目根路径（与main_new.py保持一致的逻辑）
        self.project_root_path = self._get_project_root_path(project_root_path)

        # 加载环境变量（使用项目根路径，与main_new.py保持一致）
        self._load_env_variables()

        self.static_config_file_path = static_config_file_path

        # 加载配置源
        self.env_config = self._load_env_config()
        self.static_config = self._load_config(self._resolve_config_path(static_config_file_path))

        # 合并配置：env_config > static_config
        self.config = {**self.static_config, **self.env_config}

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
            "FEISHU_APP_MESSAGE_ID",
            "FEISHU_APP_MESSAGE_SECRET",
            "COZE_API_KEY",
            "SERVER_ID",
            "ADMIN_ID",
            "ADMIN_SECRET_KEY",
            "FFMPEG_PATH",
            # B站API配置
            "BILI_API_BASE"
        ]

        for key in env_keys:
            value = os.getenv(key)
            if value is not None:
                env_config[key] = value

        return env_config

    @file_processing_safe("配置文件加载失败", return_value={})
    def _load_config(self, config_file_path: str) -> Dict[str, Any]:
        """
        加载配置

        Args:
            config_file_path: 配置文件路径

        Returns:
            Dict[str, Any]: 配置数据
        """
        if config_file_path and os.path.exists(config_file_path):
            with open(config_file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置项，支持点号分隔的嵌套访问，优先级：环境变量 > 静态配置

        Args:
            key: 配置键，支持点号分隔的嵌套路径（如："routine_record.storage_path"）
            default: 默认值

        Returns:
            Any: 配置值或默认值
        """
        # 最高优先级：环境变量（不支持嵌套）
        if key in self.env_config:
            return self.env_config[key]

        # 静态配置：支持点号分隔的嵌套访问
        return get_nested_value(self.static_config, key, default)

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
        更新静态配置文件中指定变量的值
        注意：敏感认证信息（cookies、auth_token）现在通过gradio API直接处理

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
        env_keys = ["FEISHU_APP_MESSAGE_ID", "FEISHU_APP_MESSAGE_SECRET",
                   "COZE_API_KEY", "SERVER_ID", "ADMIN_ID", "ADMIN_SECRET_KEY", "FFMPEG_PATH"]
        if variable_name in env_keys:
            return False, f"'{variable_name}' 是环境变量，请在.env文件中修改"

        # 敏感认证变量现在通过gradio API处理
        sensitive_vars = ["cookies", "auth_token"]
        if variable_name in sensitive_vars:
            return False, f"'{variable_name}' 现在通过图像服务API处理，请使用相应命令更新"

        # 更新静态配置文件
        target_file = self._resolve_config_path(self.static_config_file_path)
        if not target_file.strip():
            return False, "未配置静态配置文件路径"

        try:
            # 加载目标配置文件
            config_data = self._load_config(target_file)

            if variable_name in config_data and config_data[variable_name] == new_value:
                return False, f"变量 '{variable_name}' 的新值与旧值相同，无需更新。"

            config_data[variable_name] = new_value

            # 保存到目标文件
            with open(target_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)

            # 更新内存中的配置
            self.static_config = config_data

            # 重新合并配置
            self.config = {**self.static_config, **self.env_config}

            return True, f"'{variable_name}' 已成功更新"

        except FileNotFoundError:
            return False, f"配置文件 '{target_file}' 未找到，更新失败。"
        except json.JSONDecodeError:
            return False, f"配置文件 '{target_file}' JSON 格式错误，更新失败。"
        except Exception as e:
            return False, f"更新配置文件时发生未知错误: {e}"

    def get_status(self) -> Dict[str, Any]:
        """获取配置服务状态信息"""
        env_file_path = os.path.join(self.project_root_path, ".env")

        return {
            "project_root_path": self.project_root_path,
            "env_file_path": env_file_path,
            "env_file_exists": os.path.exists(env_file_path),
            "static_config_path": self._resolve_config_path(self.static_config_file_path),
            "static_config_exists": os.path.exists(self._resolve_config_path(self.static_config_file_path)) if self.static_config_file_path else False,
            "env_config_keys": list(self.env_config.keys()),
            "static_config_keys": list(self.static_config.keys()),
            "total_config_keys": len(self.config),
            "config_priority": "env_vars > static_config"
        }


def get_nested_value(data: Dict[str, Any], key: str, default: Any = None) -> Any:
    """
    从嵌套字典中获取值，支持点号分隔的路径

    Args:
        data: 数据字典
        key: 键路径，支持点号分隔（如："routine_record.storage_path"）
        default: 默认值

    Returns:
        Any: 配置值或默认值
    """
    if '.' not in key:
        return data.get(key, default)

    keys = key.split('.')
    current = data
    for k in keys:
        if isinstance(current, dict) and k in current:
            current = current[k]
        else:
            return default
    return current

def set_nested_value(data: Dict, path: str, value: Any) -> None:
    """
    更新嵌套字典中的值，支持任意深度的路径。
    自动初始化缺失的中间字典。

    Args:
        data: 要更新的字典
        path: 字段路径，字符串（如 "a.b.c"）
        value: 要设置的值
    """
    keys = path.split(".")
    current = data
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]

    current[keys[-1]] = value