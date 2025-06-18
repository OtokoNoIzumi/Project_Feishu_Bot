"""
管理员处理器

处理所有需要管理员权限的命令和操作
"""

import os
import re
import requests
import json
from typing import Tuple, Dict, Any, Optional
from .base_processor import BaseProcessor, MessageContext, ProcessResult, require_service, safe_execute, require_app_controller
from Module.Common.scripts.common import debug_utils


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

                # 获取B站API配置 - 修正环境变量名称
                self.bili_api_base_url = config_service.get_env("BILI_API_BASE", "https://localhost:3000")
                self.bili_admin_secret = config_service.get_env("ADMIN_SECRET_KEY", "izumi_the_beauty")

                # 获取pending_cache配置
                pending_cache_config = config_service.get("pending_cache", {})
                self.operation_timeouts = pending_cache_config.get("operation_timeouts", {})
                self.default_timeout = pending_cache_config.get("default_timeout", 30)
            else:
                # 配置服务不可用，使用默认值
                self.admin_id = ''
                self.update_config_trigger = 'whisk令牌'
                self.bili_api_base_url = 'https://localhost:3000'
                self.bili_admin_secret = 'izumi_the_beauty'
                self.operation_timeouts = {"update_user": 30, "update_ads": 45, "system_config": 60}
                self.default_timeout = 30
        else:
            # 默认配置
            self.admin_id = ''
            self.update_config_trigger = 'whisk令牌'
            self.bili_api_base_url = 'https://localhost:3000'
            self.bili_admin_secret = 'izumi_the_beauty'

    def _register_pending_operations(self):
        """注册缓存操作执行器"""
        if self.app_controller:
            pending_cache_service = self.app_controller.get_service('pending_cache')
            if pending_cache_service:
                # 注册用户更新操作执行器
                pending_cache_service.register_executor(
                    "update_user",
                    self._execute_user_update_operation
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
        account_type_display = {0: "普通用户", 1: "支持者", 2: "受邀用户"}[account_type]

        # 使用新的缓存服务创建确认操作
        return self._create_pending_user_update_operation(
            context, uid, account_type + 1, ' '.join(parts[1:])  # 转换为1-3的用户类型
        )

    @safe_execute("更新广告命令解析失败")
    def handle_update_ads_command(self, context: MessageContext, user_msg: str) -> ProcessResult:
        """处理更新广告命令"""
        # 解析命令: "更新广告 BV1phM1zMEdK 04:50-06:05"
        parts = user_msg.split(maxsplit=2)
        if len(parts) != 3:
            return ProcessResult.error_result(
                "格式错误，请使用：更新广告 <BVID> <广告时间戳>\n"
                "例如：更新广告 BV1phM1zMEdK 04:50-06:05"
            )

        bvid = parts[1]
        ad_timestamps = parts[2]

        # 验证BVID格式
        if not bvid.startswith('BV'):
            return ProcessResult.error_result("BVID格式错误，应以'BV'开头")

        # 验证时间戳格式（简单检查）
        if not re.match(r'^\d{2}:\d{2}[\s]*-[\s]*\d{2}:\d{2}$', ad_timestamps):
            return ProcessResult.error_result(
                "时间戳格式错误，请使用格式：MM:SS-MM:SS\n"
                "例如：04:50-06:05"
            )

        # 通过卡片管理器生成确认卡片
        card_content = self._create_update_ads_confirmation_card(bvid, ad_timestamps)

        return ProcessResult.success_result("interactive", card_content, parent_id=context.message_id)

    @safe_execute("处理更新用户操作失败")
    def handle_confirm_update_user(self, context: MessageContext, action_value: Dict[str, Any]) -> ProcessResult:
        """处理确认更新用户操作"""
        uid = action_value.get("uid")
        account_type = action_value.get("account_type")

        if not uid or account_type is None:
            return ProcessResult.error_result("缺少必要参数")

        # 调用B站API
        success, response_data = self._call_update_user_api(uid, account_type)

        if success:
            message = response_data.get("message", "更新成功")
            account_type_display = response_data.get("account_type_display", "未知")

            return ProcessResult.success_result("text", {
                "text": f"✅ 用户账户更新成功\n\n"
                       f"用户ID: {uid}\n"
                       f"新账户类型: {account_type_display}\n"
                       f"详细信息: {message}"
            }, parent_id=context.message_id)
        else:
            error_msg = response_data.get("message", "未知错误") if response_data else "API调用失败"
            return ProcessResult.error_result(f"❌ 用户账户更新失败: {error_msg}")

    @safe_execute("处理更新广告操作失败")
    def handle_confirm_update_ads(self, context: MessageContext, action_value: Dict[str, Any]) -> ProcessResult:
        """处理确认更新广告操作"""
        bvid = action_value.get("bvid")
        ad_timestamps = action_value.get("ad_timestamps")

        if not bvid or not ad_timestamps:
            return ProcessResult.error_result("缺少必要参数")

        # 调用B站API
        success, response_data = self._call_update_ads_api(bvid, ad_timestamps)

        if success:
            message = response_data.get("message", "更新成功")
            video_title = response_data.get("video_title", "")
            old_timestamps = response_data.get("old_ad_timestamps", "")
            new_timestamps = response_data.get("new_ad_timestamps", "")

            return ProcessResult.success_result("text", {
                "text": f"✅ 广告时间戳更新成功\n\n"
                       f"视频: {bvid}\n"
                       f"标题: {video_title}\n"
                       f"原时间戳: {old_timestamps or '(空)'}\n"
                       f"新时间戳: {new_timestamps}\n"
                       f"详细信息: {message}"
            }, parent_id=context.message_id)
        else:
            error_msg = response_data.get("message", "未知错误") if response_data else "API调用失败"
            return ProcessResult.error_result(f"❌ 广告时间戳更新失败: {error_msg}")

    @safe_execute("处理交互式卡片动作失败")
    def handle_interactive_card_action(self, context: MessageContext, action: str, action_value: Dict[str, Any]) -> ProcessResult:
        """处理交互式卡片动作"""
        if action == "confirm_update_user_interactive":
            return self.handle_confirm_update_user_interactive(context, action_value)
        elif action == "confirm_update_ads_interactive":
            return self.handle_confirm_update_ads_interactive(context, action_value)
        elif action == "cancel_admin_operation":
            return self.handle_cancel_admin_operation(context)
        else:
            return ProcessResult.error_result(f"未知的交互式卡片动作: {action}")

    @safe_execute("处理用户更新失败")
    def handle_confirm_update_user_interactive(self, context: MessageContext, action_value: Dict[str, Any]) -> ProcessResult:
        """处理交互式用户更新确认"""
        # 从卡片表单获取实际输入值
        form_data = context.metadata.get('form_data', {})
        uid = form_data.get('user_id_input', action_value.get('original_uid'))

        # 由于select_static在action中，可能需要从action值或form_data中获取
        # 先尝试从action_value中获取，如果没有则使用原始值
        if 'selected_account_type' in action_value:
            account_type_str = action_value.get('selected_account_type')
        elif 'account_type_select' in form_data:
            account_type_str = form_data.get('account_type_select')
        else:
            account_type_str = str(action_value.get('original_account_type', 0))

        account_type = int(account_type_str)

        if not uid:
            return ProcessResult.error_result("用户ID不能为空")

        # 调用B站API
        success, response_data = self._call_update_user_api(uid, account_type)

        if success:
            message = response_data.get("message", "更新成功")
            account_type_display = response_data.get("account_type_display", "未知")

            # 使用Toast更新卡片
            return ProcessResult.success_result("toast", {
                "type": "success",
                "message": f"用户 {uid} 账户类型已更新为: {account_type_display}",
                "card_update": {
                    "action": "disable_buttons",
                    "message": f"✅ 操作已完成\n\n用户ID: {uid}\n新账户类型: {account_type_display}"
                }
            }, parent_id=context.message_id)
        else:
            error_msg = response_data.get("message", "未知错误") if response_data else "API调用失败"
            return ProcessResult.success_result("toast", {
                "type": "error",
                "message": f"更新失败: {error_msg}"
            }, parent_id=context.message_id)

    @safe_execute("处理广告更新失败")
    def handle_confirm_update_ads_interactive(self, context: MessageContext, action_value: Dict[str, Any]) -> ProcessResult:
        """处理交互式广告更新确认"""
        # 从卡片表单获取实际输入值
        form_data = context.metadata.get('form_data', {})
        bvid = form_data.get('bvid_input', action_value.get('original_bvid'))
        ad_timestamps = form_data.get('timestamp_input', action_value.get('original_timestamps'))

        if not bvid or not ad_timestamps:
            return ProcessResult.error_result("BVID和时间戳不能为空")

        # 验证时间戳格式
        if not re.match(r'^\d{2}:\d{2}[\s]*-[\s]*\d{2}:\d{2}$', ad_timestamps):
            return ProcessResult.error_result("时间戳格式错误，请使用格式：MM:SS-MM:SS")

        # 调用B站API
        success, response_data = self._call_update_ads_api(bvid, ad_timestamps)

        if success:
            message = response_data.get("message", "更新成功")
            video_title = response_data.get("video_title", "")
            old_timestamps = response_data.get("old_ad_timestamps", "")
            new_timestamps = response_data.get("new_ad_timestamps", "")

            # 使用Toast更新卡片
            return ProcessResult.success_result("toast", {
                "type": "success",
                "message": f"视频 {bvid} 广告时间戳更新成功",
                "card_update": {
                    "action": "disable_buttons",
                    "message": f"✅ 操作已完成\n\n视频: {bvid}\n标题: {video_title}\n新时间戳: {new_timestamps}"
                }
            }, parent_id=context.message_id)
        else:
            error_msg = response_data.get("message", "未知错误") if response_data else "API调用失败"
            return ProcessResult.success_result("toast", {
                "type": "error",
                "message": f"更新失败: {error_msg}"
            }, parent_id=context.message_id)

    def handle_cancel_admin_operation(self, context: MessageContext) -> ProcessResult:
        """处理取消管理员操作"""
        return ProcessResult.success_result("toast", {
            "type": "info",
            "message": "操作已取消",
            "card_update": {
                "action": "disable_buttons",
                "message": "❌ 操作已取消"
            }
        }, parent_id=context.message_id)

    def _create_update_user_confirmation_card(self, uid: str, account_type: int, account_type_display: str) -> Dict[str, Any]:
        """创建更新用户确认卡片（交互式）"""
        # 账户类型选项
        account_options = [
            {
                "text": {"tag": "plain_text", "content": "普通用户"},
                "value": "0",
                "icon": {"tag": "standard_icon", "token": "user_outlined"}
            },
            {
                "text": {"tag": "plain_text", "content": "支持者"},
                "value": "1",
                "icon": {"tag": "standard_icon", "token": "like_outlined"}
            },
            {
                "text": {"tag": "plain_text", "content": "受邀用户"},
                "value": "2",
                "icon": {"tag": "standard_icon", "token": "invite_outlined"}
            }
        ]

        return {
            "config": {"wide_screen_mode": True},
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**操作确认**\n\n**操作类型:** 更新用户账户类型\n**当前用户ID:** {uid}\n**当前选择账户类型:** {account_type_display}"
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "plain_text",
                        "content": "用户ID:"
                    }
                },
                {
                    "tag": "input",
                    "name": "user_id_input",
                    "required": True,
                    "placeholder": {"tag": "plain_text", "content": "请输入用户ID"},
                    "default_value": uid
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "plain_text",
                        "content": "账户类型:"
                    }
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "select_static",
                            "placeholder": {
                                "tag": "plain_text",
                                "content": "请选择账户类型"
                            },
                            "options": account_options,
                            "type": "default",
                            "width": "default",
                            "initial_option": account_type_display
                        }
                    ]
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "✅ 确认执行"},
                            "type": "primary",
                            "value": {
                                "action": "confirm_update_user_interactive",
                                "original_uid": uid,
                                "original_account_type": account_type
                            }
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "❌ 取消"},
                            "type": "default",
                            "value": {"action": "cancel_admin_operation"}
                        }
                    ]
                }
            ],
            "header": {
                "template": "orange",
                "title": {"tag": "plain_text", "content": "🔧 管理员确认"}
            }
        }

    def _create_update_ads_confirmation_card(self, bvid: str, ad_timestamps: str) -> Dict[str, Any]:
        """创建更新广告确认卡片（交互式）"""
        try:
            # 解析和计算时间信息
            time_info = self._parse_timestamp_info(ad_timestamps)

            return {
                "config": {"wide_screen_mode": True},
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**🔧 管理员操作确认**\n\n**操作类型:** 更新视频广告时间戳\n**当前视频ID:** {bvid}"
                        }
                    },
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**⏰ 时间戳信息**\n**原始输入:** {ad_timestamps}\n**标准格式:** {time_info['formatted']}\n**广告总时长:** {time_info['duration']}"
                        }
                    },
                    {
                        "tag": "hr"
                    },
                    {
                        "tag": "div",
                        "text": {
                            "tag": "plain_text",
                            "content": "视频ID:"
                        }
                    },
                    {
                        "tag": "input",
                        "name": "bvid_input",
                        "required": true,
                        "placeholder": {"tag": "plain_text", "content": "请输入BVID"},
                        "default_value": bvid
                    },
                    {
                        "tag": "div",
                        "text": {
                            "tag": "plain_text",
                            "content": "广告时间戳 (格式: MM:SS-MM:SS):"
                        }
                    },
                    {
                        "tag": "input",
                        "name": "timestamp_input",
                        "required": true,
                        "placeholder": {"tag": "plain_text", "content": "例如: 04:50-06:05"},
                        "default_value": time_info['formatted']
                    },
                    {
                        "tag": "hr"
                    },
                    {
                        "tag": "action",
                        "actions": [
                            {
                                "tag": "button",
                                "text": {"tag": "plain_text", "content": "✅ 确认执行"},
                                "type": "primary",
                                "value": {
                                    "action": "confirm_update_ads_interactive",
                                    "original_bvid": bvid,
                                    "original_timestamps": ad_timestamps
                                }
                            },
                            {
                                "tag": "button",
                                "text": {"tag": "plain_text", "content": "❌ 取消"},
                                "type": "default",
                                "value": {"action": "cancel_admin_operation"}
                            }
                        ]
                    }
                ],
                "header": {
                    "template": "orange",
                    "title": {"tag": "plain_text", "content": "🔧 管理员确认"}
                }
            }
        except Exception as e:
            # 如果解析失败，返回简化版本
            return {
                "config": {"wide_screen_mode": True},
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**🔧 管理员操作确认**\n\n**操作类型:** 更新视频广告时间戳\n**视频ID:** {bvid}\n**时间戳:** {ad_timestamps}"
                        }
                    },
                    {
                        "tag": "action",
                        "actions": [
                            {
                                "tag": "button",
                                "text": {"tag": "plain_text", "content": "✅ 确认执行"},
                                "type": "primary",
                                "value": {
                                    "action": "confirm_update_ads_interactive",
                                    "original_bvid": bvid,
                                    "original_timestamps": ad_timestamps
                                }
                            },
                            {
                                "tag": "button",
                                "text": {"tag": "plain_text", "content": "❌ 取消"},
                                "type": "default",
                                "value": {"action": "cancel_admin_operation"}
                            }
                        ]
                    }
                ],
                "header": {
                    "template": "orange",
                    "title": {"tag": "plain_text", "content": "🔧 管理员确认"}
                }
            }

    def _parse_timestamp_info(self, ad_timestamps: str) -> Dict[str, str]:
        """解析时间戳信息，支持多种格式"""
        try:
            # 尝试解析不同格式的时间戳
            if '-' in ad_timestamps:
                parts = ad_timestamps.split('-')
                start_str = parts[0].strip()
                end_str = parts[1].strip()

                # 如果是秒数格式，转换为MM:SS
                if ':' not in start_str and start_str.isdigit():
                    start_seconds = int(start_str)
                    start_formatted = f"{start_seconds//60:02d}:{start_seconds%60:02d}"
                else:
                    start_formatted = start_str

                if ':' not in end_str and end_str.isdigit():
                    end_seconds = int(end_str)
                    end_formatted = f"{end_seconds//60:02d}:{end_seconds%60:02d}"
                else:
                    end_formatted = end_str

                formatted_timestamp = f"{start_formatted}-{end_formatted}"

                # 计算广告时长
                def time_to_seconds(time_str):
                    if ':' in time_str:
                        mm, ss = map(int, time_str.split(':'))
                        return mm * 60 + ss
                    else:
                        return int(time_str) if time_str.isdigit() else 0

                start_sec = time_to_seconds(start_str)
                end_sec = time_to_seconds(end_str)
                duration_sec = end_sec - start_sec
                duration_formatted = f"{duration_sec//60:02d}:{duration_sec%60:02d}"

                return {
                    'formatted': formatted_timestamp,
                    'duration': f"{duration_formatted} ({duration_sec}秒)"
                }
            else:
                return {
                    'formatted': ad_timestamps,
                    'duration': "无法计算"
                }
        except Exception:
            return {
                'formatted': ad_timestamps,
                'duration': "格式错误"
            }

    def _call_update_user_api(self, uid: str, account_type: int) -> Tuple[bool, Dict[str, Any]]:
        """调用更新用户API"""
        try:
            if not self.bili_api_base_url or not self.bili_admin_secret:
                return False, {"message": "B站API配置缺失"}

            url = f"{self.bili_api_base_url}/api/admin/update_user"
            headers = {"Content-Type": "application/json"}
            data = {
                "admin_secret_key": self.bili_admin_secret,
                "uid": uid,
                "account_type": account_type
            }

            response = requests.post(url, headers=headers, data=json.dumps(data), timeout=10)

            if response.status_code == 200:
                response_data = response.json()
                return response_data.get("success", False), response_data
            else:
                return False, {"message": f"HTTP错误: {response.status_code}"}

        except requests.exceptions.Timeout:
            return False, {"message": "请求超时"}
        except requests.exceptions.RequestException as e:
            return False, {"message": f"网络错误: {str(e)}"}
        except Exception as e:
            return False, {"message": f"API调用异常: {str(e)}"}

    def _call_update_ads_api(self, bvid: str, ad_timestamps: str) -> Tuple[bool, Dict[str, Any]]:
        """调用更新广告API"""
        try:
            if not self.bili_api_base_url or not self.bili_admin_secret:
                return False, {"message": "B站API配置缺失"}

            url = f"{self.bili_api_base_url}/api/admin/update_ads"
            headers = {
                "Content-Type": "application/json",
                "Connection": "close"
            }
            data = {
                "admin_secret_key": self.bili_admin_secret,
                "bvid": bvid,
                "ad_timestamps": ad_timestamps
            }
            response = requests.post(url, headers=headers, data=json.dumps(data), timeout=10)

            if response.status_code == 200:
                response_data = response.json()
                return response_data.get("success", False), response_data
            else:
                return False, {"message": f"HTTP错误: {response.status_code}"}

        except requests.exceptions.Timeout:
            return False, {"message": "请求超时"}
        except requests.exceptions.RequestException as e:
            return False, {"message": f"网络错误: {str(e)}"}
        except Exception as e:
            return False, {"message": f"API调用异常: {str(e)}"}

    @require_app_controller("应用控制器不可用")
    @require_service('pending_cache', "缓存业务服务不可用")
    @safe_execute("创建待处理用户更新操作失败")
    def _create_pending_user_update_operation(self, context: MessageContext, user_id: str, user_type: int, admin_input: str) -> ProcessResult:
        """
        创建待处理的用户更新操作

        Args:
            context: 消息上下文
            user_id: 用户ID
            user_type: 用户类型 (1-3)
            admin_input: 管理员原始输入

        Returns:
            ProcessResult: 处理结果
        """
        pending_cache_service = self.app_controller.get_service('pending_cache')

        # 从配置获取超时时间
        timeout_seconds = self.get_operation_timeout("update_user")
        timeout_text = self._format_timeout_text(timeout_seconds)

        # 准备操作数据
        operation_data = {
            'user_id': user_id,
            'user_type': user_type,
            'admin_input': admin_input,
            'finished': False,
            'result': '确认⏰',
            'hold_time': timeout_text
        }

        # 创建缓存操作
        operation_id = pending_cache_service.create_operation(
            user_id=context.user_id,  # 管理员用户ID
            operation_type="update_user",
            operation_data=operation_data,
            admin_input=admin_input,
            hold_time_seconds=timeout_seconds,
            default_action="confirm"
        )

        # 添加操作ID到数据中
        operation_data['operation_id'] = operation_id

        # 使用admin卡片管理器生成卡片
        return ProcessResult.success_result(
            "admin_card_send",
            operation_data,
            parent_id=context.message_id
        )

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
            user_type = operation.operation_data.get('user_type')

            if not user_id or not user_type:
                debug_utils.log_and_print("❌ 用户更新操作缺少必要参数", log_level="ERROR")
                return False

            # 转换用户类型 (1-3 -> 0-2)
            account_type = user_type - 1

            # 调用B站API
            success, response_data = self._call_update_user_api(user_id, account_type)

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

    @require_app_controller("应用控制器不可用")
    @require_service('pending_cache', "缓存业务服务不可用")
    @safe_execute("处理缓存操作确认失败")
    def handle_pending_operation_action(self, context: MessageContext, action_value: Dict[str, Any]) -> ProcessResult:
        """
        处理缓存操作的确认、取消等动作

        Args:
            context: 消息上下文
            action_value: 动作参数

        Returns:
            ProcessResult: 处理结果
        """
        pending_cache_service = self.app_controller.get_service('pending_cache')

        action = action_value.get('action', '')
        operation_id = action_value.get('operation_id', '')

        if not operation_id:
            return ProcessResult.error_result("缺少操作ID")

        operation = pending_cache_service.get_operation(operation_id)
        if not operation:
            return ProcessResult.error_result("操作不存在")

        if action == "confirm_user_update":
            # 更新操作数据（可能有表单修改）
            if 'user_id' in action_value:
                operation.operation_data['user_id'] = action_value['user_id']
            if 'user_type' in action_value:
                operation.operation_data['user_type'] = action_value['user_type']

            # 确认操作
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
                    "admin_card_update",
                    result_data
                )
            else:
                # 构建失败的卡片更新数据
                result_data = operation.operation_data.copy()
                result_data.update({
                    'finished': True,
                    'result': " | ❌ 执行失败",
                    'result_type': 'error'
                })

                return ProcessResult.success_result(
                    "admin_card_update",
                    result_data
                )

        elif action == "cancel_user_update":
            # 取消操作
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
                "admin_card_update",
                result_data
            )

        elif action == "update_data":
            # 更新操作数据
            new_data = action_value.get('new_data', {})
            pending_cache_service.update_operation_data(operation_id, new_data)

            # 返回简单成功响应（不需要更新卡片）
            return ProcessResult.success_result("toast", {
                "message": "数据已更新",
                "type": "success"
            })

        else:
            return ProcessResult.error_result(f"未知的操作类型: {action}")

    @require_service('image', "图像服务不可用")
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
        image_service = self.app_controller.get_service('image')

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

    def get_operation_timeout(self, operation_type: str) -> int:
        """
        获取操作类型对应的超时时间

        Args:
            operation_type: 操作类型

        Returns:
            int: 超时时间（秒）
        """
        return self.operation_timeouts.get(operation_type, self.default_timeout)

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
                return f"({minutes}m{remaining_seconds}s)"
            else:
                return f"({minutes}m)"
        else:
            hours = seconds // 3600
            remaining_minutes = (seconds % 3600) // 60
            if remaining_minutes > 0:
                return f"({hours}h{remaining_minutes}m)"
            else:
                return f"({hours}h)"