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
    """配置管理服务"""

    def __init__(self, config_file_path: str = "config.json"):
        """
        初始化配置服务

        Args:
            config_file_path: 配置文件路径
        """
        self.config_file_path = config_file_path
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """
        加载配置

        Returns:
            Dict[str, Any]: 配置数据
        """
        try:
            if os.path.exists(self.config_file_path):
                with open(self.config_file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            debug_utils.log_and_print(f"加载配置失败: {e}", log_level="ERROR")
        return {}

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置项

        Args:
            key: 配置键
            default: 默认值

        Returns:
            Any: 配置值或默认值
        """
        return self.config.get(key, default)

    def update_config(self, variable_name: str, new_value: str, validators: Dict[str, callable] = None) -> Tuple[bool, str]:
        """
        更新配置文件中指定变量的值，并自动更新expires_at

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

        try:
            config_data = self._load_config()

            if variable_name in config_data and config_data[variable_name] == new_value:
                return False, f"变量 '{variable_name}' 的新值与旧值相同，无需更新。"

            config_data[variable_name] = new_value
            current_time = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
            expires_at_time = current_time + datetime.timedelta(hours=8)
            config_data["expires_at"] = expires_at_time.isoformat()

            with open(self.config_file_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)

            # 更新内存中的配置
            self.config = config_data

            return True, f"'{variable_name}' 已成功更新，令牌有效至 {expires_at_time.strftime('%Y-%m-%d %H:%M')}"

        except FileNotFoundError:
            return False, f"配置文件 '{self.config_file_path}' 未找到，更新失败。"
        except json.JSONDecodeError:
            return False, f"配置文件 '{self.config_file_path}' JSON 格式错误，更新失败。"
        except Exception as e:
            return False, f"更新配置文件时发生未知错误: {e}"