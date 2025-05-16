"""
机器人服务模块

该模块提供机器人的核心业务逻辑服务，不依赖于特定平台
"""

import os
import json
import random
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime
import threading
import requests
import asyncio

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
        self.send_message(
                    receive_id=self.admin_id,
                    content={"text": "Whisk的Cookie已过期，请及时续签"},
                    msg_type="text"
                )
        self.log_and_print("发送每日日程", log_level="INFO")
        # 返回结果由调用者处理

    def _actual_send_bilibili_updates(self, chat_id_to_notify: Optional[str], sources: Optional[List[str]] = None) -> None:
        """
        实际执行B站API调用并发送结果的函数。
        这将在一个单独的线程中运行。
        """
        # 从环境变量获取API基础URL，默认使用localhost
        api_base = os.getenv("BILI_API_BASE", "http://localhost:3000")
        # 从环境变量获取是否验证SSL证书，默认为True
        verify_ssl = os.getenv("BILI_API_VERIFY_SSL", "True").lower() != "false"

        url = f"{api_base}/api/admin/process_sources"
        headers = {
            "Content-Type": "application/json"
        }

        # 优先从配置服务获取参数，若无则使用环境变量或默认值
        admin_secret_key = "izumi_the_beauty" # 默认值
        fav_list_id = 1397395905 # 默认值

        if hasattr(self, 'config_service') and self.config_service:
            admin_secret_key = self.config_service.get("bili_admin_secret_key", admin_secret_key)
            fav_list_id = self.config_service.get("bili_fav_list_id", fav_list_id)
        else: # 尝试从环境变量获取（如果配置服务不可用）
            admin_secret_key = os.getenv("BILI_ADMIN_SECRET_KEY", admin_secret_key)
            fav_list_id = int(os.getenv("BILI_FAV_LIST_ID", str(fav_list_id)))


        data = {
            "admin_secret_key": admin_secret_key,
            "debug_mode": True,
            "skip_deduplication": False,
            "fav_list_id": fav_list_id,
            "delete_after_process": True,
            "dynamic_hours_ago": 24,
            "dynamic_max_videos": 50,
            "homepage_max_videos": 20,
            "blocked_up_list": None,
        }

        if sources is not None:
            data["sources"] = sources

        result_message = ""
        try:
            # 添加verify参数控制是否验证SSL证书, 增加timeout
            proxies_to_use = None
            if os.getenv("BILI_API_NO_PROXY", "false").lower() in ("true", "1"):
                proxies_to_use = {} # 空字典告诉requests不要使用任何系统代理
                self.log_and_print("BILI_API_NO_PROXY已设置，B站API调用将绕过系统代理。", log_level="INFO")

            response = requests.post(url, headers=headers, data=json.dumps(data), verify=verify_ssl, timeout=180, proxies=proxies_to_use) # 3分钟超时

            if not verify_ssl:
                self.log_and_print("警告：B站API调用时SSL证书验证已禁用。", log_level="WARNING")

            self.log_and_print(f"B站更新API状态码: {response.status_code} (URL: {url})", log_level="INFO")

            if response.status_code == 200:
                try:
                    resp_json = response.json()
                    self.log_and_print(f"B站更新API响应内容: {json.dumps(resp_json, ensure_ascii=False)}", log_level="DEBUG")
                    summary = resp_json.get("message", "操作成功完成")
                    if isinstance(summary, (dict, list)):
                        summary = json.dumps(summary, ensure_ascii=False, indent=2)
                    result_message = f"✅ B站更新任务完成。\n源: {sources or '默认'}\n结果: {summary}"
                except json.JSONDecodeError as e:
                    self.log_and_print(f"B站更新API响应内容JSON解析失败: {e}.响应体: {response.text[:500]}", log_level="ERROR")
                    result_message = f"⚠️ B站更新任务执行完毕，但响应内容非标准JSON格式: {response.text[:200]}"
                except Exception as e:
                    self.log_and_print(f"B站更新API响应内容处理失败: {e}", log_level="ERROR")
                    result_message = f"⚠️ B站更新任务执行完毕，但响应处理失败: {e}"
            else:
                error_details = response.text[:500]
                self.log_and_print(f"B站更新API返回错误，状态码: {response.status_code}。响应: {error_details}", log_level="ERROR")
                result_message = f"❌ B站更新任务执行失败。\nAPI状态码: {response.status_code}\n错误详情: {error_details}"

        except requests.exceptions.Timeout:
            self.log_and_print(f"发送B站更新请求超时 (URL: {url})", log_level="ERROR")
            result_message = f"⌛ B站更新任务执行超时 (URL: {url})。"
        except requests.exceptions.ProxyError as e:
            self.log_and_print(f"发送B站更新请求时发生代理错误: {e} (URL: {url})", log_level="ERROR")
            result_message = f"❌ B站更新任务执行时发生代理连接错误: {e}"
        except requests.exceptions.ConnectionError as e:
            self.log_and_print(f"发送B站更新请求时发生连接错误: {e} (URL: {url})", log_level="ERROR")
            result_message = f"❌ B站更新任务执行时发生网络连接错误: {e}"
        except requests.exceptions.RequestException as e:
            self.log_and_print(f"发送B站更新请求失败 (RequestException): {e} (URL: {url})", log_level="ERROR")
            result_message = f"❌ B站更新任务执行时发生请求错误: {e}"
        except Exception as e:
            self.log_and_print(f"处理B站更新时发生未知错误: {e}", log_level="CRITICAL")
            result_message = f"❌ B站更新任务执行时发生未知严重错误: {e}"

        if chat_id_to_notify and hasattr(self, 'platform') and self.platform and hasattr(self.platform, 'send_message_to_chat_async'):
            try:
                loop = None
                if hasattr(self.platform, 'get_event_loop') and callable(self.platform.get_event_loop):
                    loop = self.platform.get_event_loop()

                if loop and loop.is_running():
                    future = asyncio.run_coroutine_threadsafe(
                        self.platform.send_message_to_chat_async(chat_id=chat_id_to_notify, message_content=result_message, msg_type="text"),
                        loop
                    )
                    future.result(timeout=30)
                    self.log_and_print(f"B站更新结果已发送至 chat_id: {chat_id_to_notify}", log_level="INFO")
                elif hasattr(self.platform, 'send_message_sync') and callable(self.platform.send_message_sync): # 备用同步发送
                     self.platform.send_message_sync(chat_id=chat_id_to_notify, message_content=result_message, msg_type="text")
                     self.log_and_print(f"B站更新结果已通过同步方法发送至 chat_id: {chat_id_to_notify}", log_level="INFO")
                else:
                     self.log_and_print(f"无法发送B站更新结果：事件循环未运行或未找到合适的发送方法。", log_level="WARNING")
            except Exception as e:
                self.log_and_print(f"发送B站更新结果通知失败: {e}", log_level="ERROR")
        elif not chat_id_to_notify:
            self.log_and_print(f"未提供chat_id，B站更新结果未发送通知: {result_message}", log_level="INFO")
        else:
            self.log_and_print(f"Platform或其发送方法不可用，无法发送B站更新结果。结果: {result_message}", log_level="WARNING")


    def send_bilibili_updates(self, sources: Optional[List[str]] = None, event: Optional[Dict[str, Any]] = None) -> None:
        """
        异步发送B站更新信息。
        立即回复一个处理中消息，然后在后台线程中调用本地API获取B站内容并回复结果。
        Args:
            sources: 可选的源列表，如 ["favorites", "dynamic"]
            event: 可选的飞书事件对象，用于回复消息上下文。如果为None，则尝试发送到默认通知频道。
        """
        chat_id_to_notify = None

        if event and isinstance(event, dict):
            header = event.get("header", {})
            event_payload = event.get("event", {})
            chat_id_to_notify = header.get("chat_id")
            if not chat_id_to_notify:
                message_details = event_payload.get("message")
                if message_details and isinstance(message_details, dict):
                    chat_id_to_notify = message_details.get("chat_id")

        if not chat_id_to_notify:
            if hasattr(self, 'config_service') and self.config_service:
                chat_id_to_notify = self.config_service.get("default_notification_chat_id")
            if not chat_id_to_notify:
                chat_id_to_notify = os.getenv("DEFAULT_FEISHU_CHAT_ID_FOR_BILI_UPDATES")
                if chat_id_to_notify:
                    self.log_and_print(f"使用环境变量 DEFAULT_FEISHU_CHAT_ID_FOR_BILI_UPDATES: {chat_id_to_notify}", log_level="INFO")

        if not chat_id_to_notify:
            self.log_and_print("未找到可用的chat_id。B站更新任务将在后台执行，但无法发送即时反馈和结果通知。", log_level="ERROR")

        initial_message_content = f"⏳ B站更新任务已启动 (处理源: {sources or '默认'}). 请稍候..."
        if chat_id_to_notify and hasattr(self, 'platform') and self.platform and hasattr(self.platform, 'send_message_to_chat_async'):
            try:
                loop = None
                if hasattr(self.platform, 'get_event_loop') and callable(self.platform.get_event_loop):
                    loop = self.platform.get_event_loop()

                if loop and loop.is_running():
                    future = asyncio.run_coroutine_threadsafe(
                        self.platform.send_message_to_chat_async(chat_id=chat_id_to_notify, message_content=initial_message_content, msg_type="text"),
                        loop
                    )
                    future.result(timeout=30)
                    self.log_and_print(f"初始通知已发送至 chat_id: {chat_id_to_notify}", log_level="INFO")
                elif hasattr(self.platform, 'send_message_sync') and callable(self.platform.send_message_sync): # 备用同步发送
                     self.platform.send_message_sync(chat_id=chat_id_to_notify, message_content=initial_message_content, msg_type="text")
                     self.log_and_print(f"初始通知已通过同步方法发送至 chat_id: {chat_id_to_notify}", log_level="INFO")
                else:
                    self.log_and_print(f"无法发送初始通知：事件循环未运行或未找到合适的发送方法。", log_level="WARNING")
            except Exception as e:
                self.log_and_print(f"发送初始B站更新通知失败: {e}", log_level="ERROR")
        elif chat_id_to_notify:
             self.log_and_print(f"无法发送初始通知至 {chat_id_to_notify}：Platform或其发送方法不可用。", log_level="WARNING")

        self.log_and_print(f"准备在后台线程启动B站更新任务 (源: {sources or '默认'}, 通知至: {chat_id_to_notify or '无'})", log_level="DEBUG")
        thread = threading.Thread(target=self._actual_send_bilibili_updates, args=(chat_id_to_notify, sources))
        thread.daemon = True
        thread.start()
        self.log_and_print(f"B站更新任务已在后台线程中启动 (源: {sources or '默认'}, 通知至: {chat_id_to_notify or '无'})。", log_level="INFO")

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
