"""
配置服务模块

该模块提供配置管理功能，用于处理配置文件的读取、更新等操作
"""

import os
import json
import datetime
from typing import Dict, Any, Tuple, List
from Module.Common.scripts.common import debug_utils


class ConfigService:
    """配置管理服务 - 支持多配置源"""

    def __init__(self, auth_config_file_path: str = "", static_config_file_path: str = "config.json"):
        """
        初始化配置服务

        Args:
            auth_config_file_path: 认证配置文件路径（动态、敏感信息）
            static_config_file_path: 静态配置文件路径（非敏感信息）
        """
        self.auth_config_file_path = auth_config_file_path
        self.static_config_file_path = static_config_file_path

        # 加载两种配置
        self.auth_config = self._load_config(auth_config_file_path) if auth_config_file_path.strip() else {}
        self.static_config = self._load_config(static_config_file_path)

        # 合并配置：auth_config优先级更高
        self.config = {**self.static_config, **self.auth_config}

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
        获取配置项，优先从auth_config获取，然后从static_config获取

        Args:
            key: 配置键
            default: 默认值

        Returns:
            Any: 配置值或默认值
        """
        # 优先从auth_config获取
        if key in self.auth_config:
            return self.auth_config[key]

        # 然后从static_config获取
        if key in self.static_config:
            return self.static_config[key]

        return default

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

        # 确定更新目标文件
        sensitive_vars = ["cookies", "auth_token"]  # 敏感变量列表
        if variable_name in sensitive_vars:
            target_file = self.auth_config_file_path
            target_config = self.auth_config
        else:
            target_file = self.static_config_file_path
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
            self.config = {**self.static_config, **self.auth_config}

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