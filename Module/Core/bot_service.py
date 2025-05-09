"""
机器人服务模块

该模块提供机器人的核心业务逻辑服务，不依赖于特定平台
"""

import os
import json
import random
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from Module.Interface.message import Message, MessageType, MessageResponse
from Module.Core.cache_service import CacheService
from Module.Core.config_service import ConfigService
from Module.Core.media_service import MediaService
from Module.Core.notion_service import NotionService
from Module.Common.scripts.common import debug_utils


class BotService:
    """机器人服务"""

    def __init__(
        self,
        cache_service: CacheService,
        config_service: ConfigService,
        media_service: MediaService,
        admin_id: str = ""
    ):
        """
        初始化机器人服务

        Args:
            cache_service: 缓存服务
            config_service: 配置服务
            media_service: 媒体服务
            admin_id: 管理员ID
        """
        self.cache_service = cache_service
        self.config_service = config_service
        self.media_service = media_service
        self.admin_id = admin_id or os.getenv("ADMIN_ID", "")

        # 初始化Notion服务
        self.notion_service = NotionService(cache_service)

        # 日志记录变量
        self.last_log_time = 0
        self.log_cooldown = 60  # 秒

        # 令牌更新相关配置
        self.update_config_trigger = "whisk令牌"
        self.supported_variables = ["cookies", "auth_token"]
        self.auth_config_file_path = os.getenv("AUTH_CONFIG_FILE_PATH", "")

        # 验证函数
        self.validators = {
            "cookies": self.verify_cookie,
            "auth_token": self.verify_auth_token,
        }

        # 示例数据
        self.bili_videos = [
            {"title": "【中字】蔚蓝的难度设计为什么这么完美", "bvid": "BV1BAABeKEoJ"},
            {"title": "半年减重100斤靠什么？首先排除毅力 | 果壳专访", "bvid": "BV1WHAaefEEV"},
            {"title": "作为普通人我们真的需要使用Dify吗？", "bvid": "BV16fKWeGEv1"},
        ]

    def verify_cookie(self, cookie_value: str) -> Tuple[bool, str]:
        """
        验证cookies字符串有效性

        Args:
            cookie_value: cookie值

        Returns:
            Tuple[bool, str]: (是否有效, 错误信息)
        """
        if not isinstance(cookie_value, str) or "__Secure-next-auth.session-token" not in cookie_value:
            return False, "Cookies 值无效，必须包含 __Secure-next-auth.session-token 字段。"
        return True, None

    def verify_auth_token(self, auth_token_value: str) -> Tuple[bool, str]:
        """
        验证auth_token字符串有效性

        Args:
            auth_token_value: token值

        Returns:
            Tuple[bool, str]: (是否有效, 错误信息)
        """
        if not isinstance(auth_token_value, str) or not auth_token_value.strip():
            return False, "Auth Token 值无效，不能为空。"
        if "Bearer " not in auth_token_value:
            return False, "Auth Token 值无效，必须以 'Bearer ' 开头 (注意 Bearer 后有一个空格)。"
        return True, None

    def log_and_print(self, *messages, log_level="INFO"):
        """
        日志和打印函数

        Args:
            *messages: 消息内容
            log_level: 日志级别
        """
        debug_utils.log_and_print(*messages, log_level=log_level)

    def handle_message(self, message: Message) -> Optional[MessageResponse]:
        """
        处理接收到的消息

        Args:
            message: 接收到的消息

        Returns:
            Optional[MessageResponse]: 响应消息，若无需响应则返回None
        """
        # 记录事件
        event_id = message.extra_data.get("event_id", "")
        if event_id and self.cache_service.check_event(event_id):
            self.log_and_print(f"重复事件，跳过处理。ID: {event_id}", log_level="INFO")
            return None

        if event_id:
            self.cache_service.add_event(event_id)
            self.cache_service.save_event_cache()

        # 根据消息类型处理
        if message.msg_type == MessageType.TEXT:
            return self._handle_text_message(message)

        if message.msg_type == MessageType.IMAGE:
            return self._handle_image_message(message)

        if message.msg_type == MessageType.AUDIO:
            return self._handle_audio_message(message)

        if message.msg_type == MessageType.MENU_CLICK:
            return self._handle_menu_click_message(message)

        return MessageResponse(
            MessageType.TEXT,
            json.dumps({"text": "无法处理该类型的消息"}),
            success=True
        )

    def _handle_menu_click_message(self, message: Message) -> MessageResponse:
        """
        处理菜单点击消息
        """
        event_key = message.extra_data.get("event_key", "")
        if event_key == "get_bili_url":
            # 调用Notion服务获取B站视频推荐
            response_message = MessageResponse(
                MessageType.TEXT,
                json.dumps({"text": "__GET_BILI_VIDEO__"}),
                success=True,
                extra_data={"action": "get_bili_video"}
            )
        else:
            content = "收到菜单点击消息"
            response_message = MessageResponse(
                MessageType.TEXT,
                json.dumps({"text": content}),
                success=True
            )
        response_message.extra_data['receive_id'] = message.sender_id
        return response_message

    def _handle_text_message(self, message: Message) -> MessageResponse:
        """
        处理文本消息

        Args:
            message: 文本消息

        Returns:
            MessageResponse: 响应消息
        """
        user_msg = message.content

        # 令牌更新指令
        if user_msg.startswith(self.update_config_trigger):
            self.log_and_print(f"收到 [令牌更新指令] 文本消息: {user_msg}", log_level="INFO")
            if message.sender_id != self.admin_id:
                return MessageResponse(
                    MessageType.TEXT,
                    json.dumps({"text": f"收到消息: {user_msg}"}),
                    success=True
                )
            # 不需要else了，直接返回错误信息
            command_parts = user_msg[len(self.update_config_trigger):].strip().split(maxsplit=1)
            if len(command_parts) == 2:
                variable_name = command_parts[0].strip()
                new_value = command_parts[1].strip()
                if variable_name in self.supported_variables:
                    success, reply_text = self.config_service.update_config(
                        variable_name,
                        new_value,
                        self.validators
                    )
                    return MessageResponse(
                        MessageType.TEXT,
                        json.dumps({"text": reply_text}),
                        success=success
                    )
                # 不需要else了，直接返回错误信息
                error_msg = (
                    f"不支持更新变量 '{variable_name}'，"
                    f"只能更新: {', '.join(self.supported_variables)}"
                )
                return MessageResponse(
                    MessageType.TEXT,
                    json.dumps({"text": error_msg}),
                    success=False
                )
            # 不需要else了，直接返回错误信息
            error_msg = (
                f"格式错误，请使用 '{self.update_config_trigger} 变量名 新值' 格式，"
                f"例如：{self.update_config_trigger} cookies xxxx"
            )
            return MessageResponse(
                MessageType.TEXT,
                json.dumps({"text": error_msg}),
                success=False
            )

        # 帮助指令
        if "帮助" in user_msg:
            self.log_and_print(f"收到 [帮助demo指令] 文本消息: {user_msg}", log_level="INFO")
            help_text = (
                "<b>我可以帮你做这些事情：</b>\n\n"
                "1. <b>图片风格转换</b>\n"
                "上传任意照片，我会把照片转换成<i>剪纸贺卡</i>风格的图片\n\n"
                "2. <b>视频推荐</b>\n"
                "输入\"B站\"或\"视频\"，我会<i>随机推荐</i>B站视频给你\n\n"
                "3. <b>图片分享</b>\n"
                "输入\"图片\"或\"壁纸\"，我会分享<u>精美图片</u>\n\n"
                "4. <b>音频播放</b>\n"
                "输入\"音频\"，我会发送<u>语音消息</u>\n\n"
                "<at user_id=\"all\"></at> 随时输入\"帮助\"可以<i>再次查看</i>此菜单"
            )
            return MessageResponse(
                MessageType.TEXT,
                json.dumps({"text": help_text}),
                success=True
            )

        # 富文本指令
        if "富文本" in user_msg:
            self.log_and_print(f"收到 [富文本demo指令] 消息: {user_msg}", log_level="INFO")
            # 富文本示例在具体平台实现中处理，这里返回一个标记
            return MessageResponse(
                MessageType.TEXT,
                json.dumps({"text": "__RICH_TEXT_DEMO__"}),
                success=True,
                extra_data={"action": "rich_text_demo"}
            )

        # B站视频推荐
        if "B站" in user_msg or "视频" in user_msg:
            self.log_and_print(f"收到 [视频推荐demo指令] 文本消息: {user_msg}", log_level="INFO")
            video = random.choice(self.bili_videos)
            response_text = (
                f"为你推荐B站视频：\n"
                f"{video['title']}\n"
                f"https://www.bilibili.com/video/{video['bvid']}"
            )
            return MessageResponse(
                MessageType.TEXT,
                json.dumps({"text": response_text}),
                success=True
            )

        # AI生图指令
        if "生图" in user_msg or "AI画图" in user_msg:
            self.log_and_print(f"收到 [AI生图指令] 文本消息: {user_msg}", log_level="INFO")

            # 发送等待消息
            prompt = user_msg.replace("生图", "").replace("AI画图", "").strip()

            return MessageResponse(
                MessageType.TEXT,
                json.dumps({"text": "__AI_IMAGE_GENERATION__"}),
                success=True,
                extra_data={"action": "generate_image", "prompt": prompt}
            )

        # 图片分享
        if "图片" in user_msg or "壁纸" in user_msg:
            self.log_and_print(f"收到 [图片demo指令] 文本消息: {user_msg}", log_level="INFO")
            return MessageResponse(
                MessageType.TEXT,
                json.dumps({"text": "__SAMPLE_IMAGE__"}),
                success=True,
                extra_data={"action": "share_sample_image"}
            )

        # 音频分享
        if "音频" in user_msg:
            self.log_and_print(f"收到 [音频demo指令] 文本消息: {user_msg}", log_level="INFO")
            return MessageResponse(
                MessageType.TEXT,
                json.dumps({"text": "__SAMPLE_AUDIO__"}),
                success=True,
                extra_data={"action": "share_sample_audio"}
            )

        # 配音生成
        if "配音" in user_msg:
            self.log_and_print(f"收到 [配音指令] 文本消息: {user_msg}", log_level="INFO")
            tts_text = user_msg.split("配音", 1)[1].strip()

            return MessageResponse(
                MessageType.TEXT,
                json.dumps({"text": "__GENERATE_TTS__"}),
                success=True,
                extra_data={"action": "generate_tts", "text": tts_text}
            )

        # 问候
        if "你好" in user_msg:
            self.log_and_print(f"收到 [问候demo指令] 文本消息: {user_msg}", log_level="INFO")
            return MessageResponse(
                MessageType.TEXT,
                json.dumps({"text": "你好呀！有什么我可以帮你的吗？"}),
                success=True
            )

        # 默认回复
        self.log_and_print(f"收到 [文本消息] ，启用默认回复: {user_msg}", log_level="INFO")
        return MessageResponse(
            MessageType.TEXT,
            json.dumps({"text": f"收到你发送的消息：{user_msg}"}),
            success=True
        )

    def _handle_image_message(self, message: Message) -> MessageResponse:
        """
        处理图片消息

        Args:
            message: 图片消息

        Returns:
            MessageResponse: 响应消息
        """
        self.log_and_print("收到图片消息，调用whisk图片处理API", log_level="INFO")

        # 通知开始处理
        return MessageResponse(
            MessageType.TEXT,
            json.dumps({"text": "__PROCESS_IMAGE__"}),
            success=True,
            extra_data={"action": "process_image", "image_data": message.extra_data.get("image_data")}
        )

    def _handle_audio_message(self, message: Message) -> MessageResponse:
        """
        处理音频消息（临时）

        Args:
            message: 音频消息

        Returns:
            MessageResponse: 响应消息
        """
        self.log_and_print("收到音频消息", log_level="INFO")

        # 返回通用回复
        return MessageResponse(
            MessageType.TEXT,
            json.dumps({"text": "这是一个待开发的音频处理流程"}),
            success=True
        )

    def send_daily_schedule(self) -> None:
        """发送每日日程信息（临时）"""
        schedule_text = "今日日程:\n- 上午 9:00  会议\n- 下午 2:00  代码 Review"
        self.log_and_print("发送每日日程", log_level="INFO")
        # 返回结果由调用者处理

    def send_bilibili_updates(self, sources: Optional[List[str]] = None) -> None:
        """
        发送B站更新信息，调用本地API获取B站收藏夹/动态等内容
        Args:
            sources: 可选的源列表，如 ["favorites", "dynamic"]
        """
        import requests
        import json
        url = os.getenv("BILI_API_BASE", "http://localhost:3000") + "/api/admin/process_sources"
        headers = {
            "Content-Type": "application/json"
        }
        data = {
            "admin_secret_key": "izumi_the_beauty",
            "debug_mode": True,
            "skip_deduplication": False,
            "fav_list_id": 1397395905,
            "delete_after_process": True,
            "dynamic_hours_ago": 24,
            "dynamic_max_videos": 50,
            "homepage_max_videos": 20,
            "blocked_up_list": None,
            # "sources": ["favorites", "dynamic"] # 旧的硬编码或注释掉的行
            # "sources": ["favorites"]             # 旧的硬编码或注释掉的行
        }

        if sources is not None:
            data["sources"] = sources

        try:
            response = requests.post(url, headers=headers, data=json.dumps(data))
            self.log_and_print(f"B站更新API状态码: {response.status_code}", log_level="INFO")
            try:
                resp_json = response.json()
                self.log_and_print(f"B站更新API响应内容: {json.dumps(resp_json, ensure_ascii=False)}", log_level="DEBUG")
            except Exception as e:
                self.log_and_print(f"B站更新API响应内容解析失败: {e}", log_level="ERROR")
        except Exception as e:
            self.log_and_print(f"发送B站更新请求失败: {e}", log_level="ERROR")

    def send_daily_summary(self) -> None:
        """发送每日工作总结（临时）"""
        summary_text = "每日总结:\n- 今日完成 XX 任务\n- 发现 XX 问题"
        self.log_and_print("发送每日总结", log_level="INFO")
        # 返回结果由调用者处理

    def process_ai_image(self, prompt: str = None, image_input: Dict = None) -> Optional[List[str]]:
        """
        处理AI图像生成

        Args:
            prompt: 提示词
            image_input: 图片输入

        Returns:
            Optional[List[str]]: 生成的图片路径列表
        """
        return self.media_service.generate_ai_image(prompt, image_input)

    def generate_tts(self, text: str) -> Optional[bytes]:
        """
        生成语音

        Args:
            text: 文本内容

        Returns:
            Optional[bytes]: 音频数据
        """
        return self.media_service.generate_tts(text)
