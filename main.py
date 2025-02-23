"""
飞书机器人服务模块

该模块实现了一个基于飞书开放平台的机器人服务，主要功能包括：
- 消息接收与回复
- 图片、音频等多媒体处理
- AI图像生成与处理
- 定时任务调度
- 配置文件管理

依赖:
- lark_oapi: 飞书开放平台SDK
- gradio_client: Gradio客户端，用于AI服务调用
- schedule: 定时任务调度
"""

import time
import os
import sys
import json
import asyncio
import random
import subprocess
import shutil
from pathlib import Path
import datetime
import base64
from typing import Optional, Dict
# 第三方库
import tempfile
import requests
from dotenv import load_dotenv
import lark_oapi as lark
# from lark_oapi.api.im.v1 import *
# 替换原来的通配符导入
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    ReplyMessageRequest,
    ReplyMessageRequestBody,
    CreateImageRequest,
    CreateImageRequestBody,
    CreateFileRequest,
    CreateFileRequestBody,
    GetMessageResourceRequest,
)

# from lark_oapi.api.contact.v3 import *
from lark_oapi.api.contact.v3 import (
    GetUserRequest
)
from gradio_client import Client
import schedule

# 初始化配置
is_not_jupyter = "__file__" in globals()
if is_not_jupyter:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.normpath(os.path.join(current_dir, ".."))
else:
    current_dir = os.getcwd()
    current_dir = os.path.join(current_dir, "..")
    root_dir = os.path.normpath(os.path.join(current_dir))

current_dir = os.path.normpath(current_dir)
sys.path.append(current_dir)

# 从公共库中导入日志服务
from Module.Common.scripts.common import debug_utils


# 封装一下，方便以后替换
def log_and_print(*messages, log_level="INFO"):
    """    日志和打印函数    """
    debug_utils.log_and_print(*messages, log_level=log_level)


# 加载项目配置文件
with open(os.path.join(current_dir, "config.json"), encoding="utf-8") as file:
    config = json.load(file)

load_dotenv(os.path.join(current_dir, ".env"))
gradio_client = Client(f"http://{os.getenv('SERVER_ID', '')}/")
lark.APP_ID = os.getenv("FEISHU_APP_MESSAGE_ID", "")
lark.APP_SECRET = os.getenv("FEISHU_APP_MESSAGE_SECRET", "")

CACHE_DIR = os.path.join(current_dir, "cache")
PROCESSED_EVENTS_FILE = os.path.join(CACHE_DIR, "processed_events.json")
USER_CACHE_FILE = os.path.join(CACHE_DIR, "user_cache.json")

UPDATE_CONFIG_TRIGGER = "whisk令牌"
SUPPORTED_VARIABLES = ["cookies", "auth_token"]
AUTH_CONFIG_FILE_PATH = os.getenv("AUTH_CONFIG_FILE_PATH", "")

custom_ffmpeg = os.getenv("FFMPEG_PATH", "")

COZE_ACCESS_TOKEN = os.getenv("COZE_API_KEY")

# 配置参数（替换为你的实际参数）
COZE_API_BASE = "https://api.coze.cn"
BOT_ID = config.get("bot_id", "")
VOICE_ID = config.get("voice_id", "peach")  # 中文女声音色


class CozeTTS:
    """Coze TTS 类"""
    def __init__(self, api_base: str, workflow_id: str, access_token: str):
        self.api_base = api_base
        self.workflow_id = workflow_id
        self.access_token = access_token

    def generate(self, text: str) -> Optional[bytes]:
        """返回音频字节流，不保存文件"""
        if self.workflow_id == "":
            return None
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "workflow_id": self.workflow_id,
            "parameters": {
                "input": text,
                "voicebranch": VOICE_ID,
                "voice_type": "zh_female_gufengshaoyu_mars_bigtts"
            }
        }

        try:
            # 第一步：获取音频URL

            # print(f"test-payload: {payload}")
            # print(f"test-headers: {headers}")
            # print(f"test-url: {self.api_base}")
            response = requests.post(self.api_base, headers=headers, json=payload, timeout=60)
            response.raise_for_status()

            if response.status_code == 200:
                result = response.json()
                if result.get("code") == 0:
                    data = json.loads(result.get("data", "{}"))
                    url_mappings = {
                        "gaoleng": "url",
                        "speech": "link",
                        "ruomei": "url"
                    }
                    # Find the first valid audio URL
                    audio_url = None
                    for source, url_key in url_mappings.items():
                        if data.get(source):
                            audio_url = data[source].get(url_key)
                            if audio_url:
                                break

                    if audio_url:
                        # 第二步：下载音频
                        audio_response = requests.get(audio_url, timeout=60)
                        audio_response.raise_for_status()
                        return audio_response.content
            return None
        except Exception as e:
            log_and_print(f"TTS流程失败: {e}", log_level="ERROR")
            return None


# 初始化（放在全局作用域）
coze_tts = CozeTTS(
    api_base=config.get("coze_bot_url", "https://api.coze.cn/v1/workflow/run"),
    workflow_id=BOT_ID,
    access_token=COZE_ACCESS_TOKEN
)


class CacheManager:
    """缓存管理器"""
    def __init__(self, user_cache_file: str, event_cache_file: str):
        self.user_cache_file = user_cache_file
        self.event_cache_file = event_cache_file

        # 用户缓存结构：{open_id: {"name": str, "timestamp": float}}
        self.user_cache: Dict[str, Dict] = self._load_user_cache()

        # 事件缓存结构：{event_id: timestamp}
        self.event_cache: Dict[str, float] = self._load_event_cache()

    def _load_user_cache(self) -> Dict:
        """加载用户缓存"""
        try:
            if os.path.exists(self.user_cache_file):
                with open(self.user_cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                cutoff = time.time() - 604800  # 7天
                return {
                    k: v for k, v in data.items()
                    if v.get("timestamp", 0) > cutoff
                }
        except Exception as e:
            print(f"[Cache] 加载用户缓存失败: {e}")
        return {}

    def _load_event_cache(self) -> Dict:
        """加载事件缓存，兼容旧格式"""
        try:
            if os.path.exists(self.event_cache_file):
                with open(self.event_cache_file, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)

                # 兼容旧版事件缓存格式（列表转字典）
                if isinstance(raw_data, list):
                    return {k: time.time() for k in raw_data}

                cutoff = time.time() - 32 * 3600
                return {k: float(v) for k, v in raw_data.items() if float(v) > cutoff}

        except Exception as e:
            print(f"[Cache] 加载事件缓存失败: {e}")
        return {}

    def save_all(self):
        """保存所有缓存"""
        self.save_user_cache()
        self.save_event_cache()

    def save_user_cache(self):
        """保存用户缓存"""
        self._atomic_save(self.user_cache_file, self.user_cache)

    def save_event_cache(self):
        """保存事件缓存，保持与旧格式兼容"""
        processed_events = {k: str(v) for k, v in self.event_cache.items()}
        self._atomic_save(self.event_cache_file, processed_events)

    def _atomic_save(self, filename: str, data: Dict):
        """原子化保存"""
        try:
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            temp_file = filename + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(temp_file, filename)
        except Exception as e:
            print(f"[Cache] 保存失败 {filename}: {e}")

    # 用户缓存方法
    def get_user_name(self, open_id: str) -> str:
        """获取缓存的用户名"""
        entry = self.user_cache.get(open_id, {})
        if entry:
            return entry["name"]
        return None

    def update_user(self, open_id: str, name: str):
        """更新用户缓存"""
        self.user_cache[open_id] = {
            "name": name,
            "timestamp": time.time()
        }

    # 事件缓存方法
    def check_event(self, event_id: str) -> bool:
        """检查事件是否已处理"""
        return event_id in self.event_cache

    def add_event(self, event_id: str):
        """记录已处理事件"""
        self.event_cache[event_id] = time.time()


cache = CacheManager(
    user_cache_file=USER_CACHE_FILE,
    event_cache_file=PROCESSED_EVENTS_FILE
)


def verify_cookie(cookie_value: str) -> tuple[bool, str]:
    """
    验证cookies字符串有效性
    """
    if not isinstance(cookie_value, str) or "__Secure-next-auth.session-token" not in cookie_value:
        return False, "Cookies 值无效，必须包含 __Secure-next-auth.session-token 字段。"
    return True, None


def verify_auth_token(auth_token_value: str) -> tuple[bool, str]:
    """
    验证auth_token字符串有效性
    """
    if not isinstance(auth_token_value, str) or not auth_token_value.strip():
        return False, "Auth Token 值无效，不能为空。"
    if "Bearer " not in auth_token_value:
        return False, "Auth Token 值无效，必须以 'Bearer ' 开头 (注意 Bearer 后有一个空格)。"
    return True, None


handle_error = {
    "cookies": verify_cookie,
    "auth_token": verify_auth_token,
}


def update_config_value(config_file_path, variable_name, new_value):
    """
    更新配置文件中指定变量的值，并自动更新 expires_at。

    Args:
        config_file_path: 配置文件路径.
        variable_name: 要更新的变量名 (cookies 或 auth_token).
        new_value: 变量的新值.

    Returns:
        tuple: (更新是否成功: bool, 回复消息: str).
               成功时返回 (True, 成功消息)，失败时返回 (False, 错误消息).
    """
    if variable_name in handle_error:
        is_valid, err_msg = handle_error[variable_name](new_value)
        if not is_valid:
            return False, f"'{variable_name}' 更新失败: {err_msg}"

    try:
        with open(config_file_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)

        if variable_name in config_data and config_data[variable_name] == new_value:
            return False, f"变量 '{variable_name}' 的新值与旧值相同，无需更新。"

        config_data[variable_name] = new_value
        current_time = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
        expires_at_time = current_time + datetime.timedelta(hours=8)
        config_data["expires_at"] = expires_at_time.isoformat()

        with open(config_file_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)

        return True, f"'{variable_name}' 已成功更新，令牌有效至 {expires_at_time.strftime('%Y-%m-%d %H:%M')}"

    except FileNotFoundError:
        return False, f"配置文件 '{config_file_path}' 未找到，更新失败。"
    except json.JSONDecodeError:
        return False, f"配置文件 '{config_file_path}' JSON 格式错误，更新失败。"
    except Exception as e:
        return False, f"更新配置文件时发生未知错误: {e}"


def convert_to_opus(
    input_path: str,
    ffmpeg_path: str = None,
    output_dir: str = None,
    overwrite: bool = False
) -> tuple:
    """
    将音频文件转换为opus格式。

    Args:
        input_path: 输入音频文件路径
        ffmpeg_path: ffmpeg可执行文件路径，默认使用系统PATH中的ffmpeg
        output_dir: 输出目录，默认与输入文件相同目录
        overwrite: 是否覆盖已存在的输出文件

    Returns:
        tuple: (输出文件路径, 音频时长(毫秒))

    Raises:
        FileNotFoundError: ffmpeg或输入文件不存在
        RuntimeError: 转换失败
        FileExistsError: 输出文件已存在且不允许覆盖
    """
    input_path = Path(input_path)
    ffmpeg_path = Path(ffmpeg_path) if ffmpeg_path else None

    if ffmpeg_path and not ffmpeg_path.exists():
        raise FileNotFoundError(f"ffmpeg未找到: {ffmpeg_path}")
    if not ffmpeg_path and not shutil.which("ffmpeg"):
        raise RuntimeError("未找到系统ffmpeg，请安装或指定自定义路径")

    if not input_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {input_path}")

    output_path = Path(output_dir or input_path.parent) / f"{input_path.stem}.opus"
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"输出文件已存在: {output_path}")

    cmd = [
        str(ffmpeg_path) if ffmpeg_path else "ffmpeg",
        "-i", str(input_path),
        "-strict", "-2",
        "-acodec", "opus",
        "-ac", "1",
        "-ar", "48000",
        "-y" if overwrite else "-n",
        str(output_path)
    ]

    try:
        with subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        ) as process:
            duration = None
            for line in process.stdout:  # 实时读取输出
                if "Duration:" in line:
                    time_str = line.split("Duration: ")[1].split(",")[0].strip()
                    h, m, s = time_str.split(":")
                    duration = int((int(h)*3600 + int(m)*60 + float(s)) * 1000)

            return_code = process.wait()

            if return_code != 0:
                raise RuntimeError(f"转换失败，返回码: {return_code}")

        return str(output_path), duration

    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"转换失败: {e.stderr.strip()}") from e


def send_message_to_feishu(
    message_text: str,
    receive_id: str = "ou_bb1ec32fbd4660b4d7ca36b3640f6fde"
) -> None:
    """
    发送文本消息到飞书。

    Args:
        message_text: 要发送的消息文本
        receive_id: 接收者的open_id，默认为预设ID
    """
    content = json.dumps({"text": message_text})
    request = (
        CreateMessageRequest.builder()
        .receive_id_type("open_id")
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(receive_id)
            .msg_type("text")
            .content(content)
            .build()
        )
        .build()
    )
    response = client.im.v1.message.create(request)
    if not response.success():
        log_and_print(f"发送消息失败: {response.code}, {response.msg}")
    else:
        log_and_print("消息已发送")


def send_daily_schedule():
    """
    发送当日日程信息到飞书。

    TODO:
    1. 获取当日日程信息 (例如从日历 API 或本地文件读取)
    2. 发送日程信息到飞书
    """
    schedule_text = "今日日程:\n- 上午 9:00  会议\n- 下午 2:00  代码 Review"
    send_message_to_feishu(schedule_text)


def send_bilibili_updates():
    """
    发送 B 站更新信息到飞书。

    TODO:
    1. 获取 B 站更新信息 (例如调用 B站 API)
    2. 发送更新信息到飞书
    """
    update_text = "B站更新:\n- XXX up主发布了新视频：[视频标题](视频链接)"
    send_message_to_feishu(update_text)


def send_daily_summary():
    """
    生成并发送每日工作总结到飞书。

    TODO:
    1. 从日志系统获取今日完成的任务数据
    2. 从监控系统获取发现的问题和告警
    3. 从代码仓库获取今日提交记录
    4. 整合数据生成结构化总结
    """
    summary_text = "每日总结:\n- 今日完成 XX 任务\n- 发现 XX 问题"
    send_message_to_feishu(summary_text)


# 修改后的用户信息获取函数
def get_user_name(open_id: str) -> str:
    """    获取用户名    """
    cached_name = cache.get_user_name(open_id)
    if cached_name:
        return cached_name+"(缓存)"

    request = GetUserRequest.builder() \
        .user_id(open_id) \
        .user_id_type("open_id") \
        .department_id_type("department_id") \
        .build()

    try:
        response = client.contact.v3.user.get(request)
        if response.success() and response.data and response.data.user:
            name = response.data.user.name
            cache.update_user(open_id, name)
            cache.save_user_cache()
            return name
    except Exception as e:
        print(f"获取用户信息失败: {e}")

    return "未知用户"


def do_p2_im_message_receive_v1(data) -> None:
    """
    处理飞书机器人接收到的消息事件。

    Args:
        data: 飞书消息事件数据对象，包含消息内容、发送者等信息
    """
    # 获取事件基本信息
    event_time = data.header.create_time or time.time()
    event_id = data.header.event_id

    # 处理时间戳
    try:
        # 尝试将字符串转换为整数
        if isinstance(event_time, str):
            event_time = int(event_time)
        timestamp = int(event_time/1000) if event_time > 1e10 else int(event_time)
        formatted_time = datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        # 如果转换失败，使用当前时间
        formatted_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 获取发送者信息
    sender_name = get_user_name(data.event.sender.sender_id.open_id)

    # 检查事件是否已处理过
    # 修改后的事件处理检查
    if cache.check_event(event_id):
        log_and_print(f"重复事件，发送者: {sender_name} ，跳过处理。ID: {event_id}", log_level="INFO")
        return

    # 记录事件信息
    log_and_print(
        f"收到消息事件 - ID: {event_id}",
        f"时间: {formatted_time}",
        f"发送者: {sender_name} ({data.event.sender.sender_id.open_id})",
        f"消息类型: {data.event.message.message_type}",
        log_level="INFO"
    )
    # 记录新事件
    cache.add_event(event_id)
    cache.save_event_cache()

    def send_message(msg_type: str, content: str) -> None:
        """发送消息的通用函数"""
        if data.event.message.chat_type == "p2p":
            request = CreateMessageRequest.builder().receive_id_type("chat_id").request_body(
                CreateMessageRequestBody.builder()
                .receive_id(data.event.message.chat_id)
                .msg_type(msg_type)
                .content(content)
                .build()
            ).build()
            response = client.im.v1.chat.create(request)
        else:
            request = (
                ReplyMessageRequest.builder()
                .message_id(data.event.message.message_id)
                .request_body(
                    ReplyMessageRequestBody.builder()
                    .content(content)
                    .msg_type(msg_type)
                    .build()
                )
                .build()
            )
            response = client.im.v1.message.reply(request)

        if not response.success():
            log_and_print(f"消息发送失败: {response.code} - {response.msg}", log_level="ERROR")
        return response

    def handle_image_upload(image_path: str) -> tuple[str, str]:
        """处理图片上传,返回消息类型和内容"""
        with open(image_path, "rb") as image_file:
            upload_response = client.im.v1.image.create(
                CreateImageRequest.builder()
                .request_body(
                    CreateImageRequestBody.builder()
                    .image_type("message")
                    .image(image_file)
                    .build()
                )
                .build()
            )
            if (
                upload_response.success() and
                upload_response.data and
                upload_response.data.image_key
            ):
                return "image", json.dumps({"image_key": upload_response.data.image_key})
            error_msg = f"图片上传失败: {upload_response.code} - {upload_response.msg}"
            return "text", json.dumps({"text": error_msg})

    def handle_audio_upload(audio_path: str) -> tuple[str, str]:
        """处理音频上传,返回消息类型和内容"""
        opus_path, duration_ms = convert_to_opus(audio_path, custom_ffmpeg, overwrite=True)
        with open(opus_path, "rb") as audio_file:
            opus_filename = Path(audio_path).stem + '.opus'
            upload_response = client.im.v1.file.create(
                CreateFileRequest.builder()
                .request_body(
                    CreateFileRequestBody.builder()
                    .file_type("opus")
                    .file_name(opus_filename)
                    .duration(str(int(duration_ms)))
                    .file(audio_file)
                    .build()
                ).build()
            )
            if upload_response.success() and upload_response.data and upload_response.data.file_key:
                return "audio", json.dumps({"file_key": upload_response.data.file_key})
            error_msg = f"音频上传失败: {upload_response.code} - {upload_response.msg}"
            return "text", json.dumps({"text": error_msg})

    def handle_ai_image_generation(prompt: str = None, image_input: dict = None) -> tuple[str, str]:
        """
        处理AI生图或图片处理请求

        Args:
            prompt: 文本提示词,用于AI生图
            image_input: 图片输入参数,用于图片处理

        Returns:
            tuple: 消息类型和内容
        """
        predict_kwargs = {
            "image_input1": None,
            "image_input2": None,
            "style_key": "贺卡",
            "additional_text": "",
            "api_name": "/generate_images"
        }
        if image_input:
            predict_kwargs["image_input1"] = image_input

        elif prompt:
            predict_kwargs["additional_text"] = "/img " + prompt

        result = gradio_client.predict(**predict_kwargs)

        if not isinstance(result, tuple) or len(result) == 0:
            return "text", json.dumps({"text": "图片失败，已经通知管理员修复咯！"})

        if all(x is None for x in result):
            return "text", json.dumps({"text": "图片生成失败了，建议您换个提示词再试试"})

        for image_path in result:
            if image_path is not None:
                msg_type, content = handle_image_upload(image_path)
                if msg_type == "image":
                    send_message(msg_type, content)

        return None, None

    def handle_message_resource(
        message_id: str,
        file_key: str,
        resource_type: str
    ) -> tuple[bytes, str, dict]:
        """
        获取消息中的资源文件

        Args:
            message_id: 消息ID
            file_key: 文件key
            resource_type: 资源类型

        Returns:
            tuple: 文件内容、文件名和元信息
        """
        request = GetMessageResourceRequest.builder() \
            .message_id(message_id) \
            .file_key(file_key) \
            .type(resource_type) \
            .build()

        response = client.im.v1.message_resource.get(request)

        if not response.success():
            log_and_print(f"获取资源文件失败: {response.code} - {response.msg}", log_level="ERROR")
            return None, None, None

        file_content = response.file.read()
        file_name = response.file_name
        meta = {
            "size": len(file_content),
            "mime_type": (
                response.file.content_type
                if hasattr(response.file, "content_type")
                else None
            )
        }

        return file_content, file_name, meta

    bili_videos = [
        {"title": "【中字】蔚蓝的难度设计为什么这么完美", "bvid": "BV1BAABeKEoJ"},
        {"title": "半年减重100斤靠什么？首先排除毅力 | 果壳专访", "bvid": "BV1WHAaefEEV"},
        {"title": "作为普通人我们真的需要使用Dify吗？", "bvid": "BV16fKWeGEv1"},
    ]

    # 获取消息内容
    msg_type = "text"
    content = None
    user_msg = None

    # 解析消息内容
    if data.event.message.message_type == "text":
        user_msg = json.loads(data.event.message.content)["text"]
    elif data.event.message.message_type == "image":
        log_and_print("收到图片消息，调用whisk图片处理API", log_level="INFO")
        image_content = json.loads(data.event.message.content)
        if "image_key" in image_content:
            file_content, file_name, meta = handle_message_resource(
                data.event.message.message_id,
                image_content["image_key"],
                "image"
            )
            if file_content:
                base64_image = base64.b64encode(file_content).decode('utf-8')
                image_url = f"data:{meta['mime_type']};base64,{base64_image}"
                image_input = {
                    "path": None,
                    "url": image_url,
                    "size": meta["size"],
                    "orig_name": file_name,
                    "mime_type": meta["mime_type"],
                    "is_stream": False,
                    "meta": {}
                }
                send_message("text", json.dumps({"text": "正在转换图片风格，请稍候..."}))

                try:
                    msg_type, content = handle_ai_image_generation(image_input=image_input)
                except Exception as e:
                    content = json.dumps({"text": f"AI 图片处理错误: {str(e)}"})
            else:
                content = json.dumps({"text": "获取图片资源失败"})
        else:
            content = json.dumps({"text": "图片消息格式错误"})
    elif data.event.message.message_type == "audio":
        log_and_print("收到音频消息", log_level="INFO")
        audio_content = json.loads(data.event.message.content)
        if "file_key" in audio_content:
            file_content, file_name, meta = handle_message_resource(
                data.event.message.message_id,
                audio_content["file_key"],
                "file"
            )
            if file_content:
                content = json.dumps({"text": "这是一个待开发的音频处理流程"})
            else:
                content = json.dumps({"text": "获取音频资源失败"})
        else:
            content = json.dumps({"text": "音频消息格式错误"})
    else:
        log_and_print(f"收到未知类型消息: {data.event.message.message_type}", log_level="WARNING")
        content = json.dumps({"text": "解析消息失败，请发送文本消息"})

    # 处理文本消息
    if not content and user_msg:

        if user_msg.startswith(UPDATE_CONFIG_TRIGGER):
            log_and_print(f"收到 [令牌更新指令] 文本消息: {user_msg}", log_level="INFO")
            if data.event.sender.sender_id.open_id != os.getenv("ADMIN_ID"):
                content = json.dumps({"text": f"Received message:{user_msg}"})
            else:
                command_parts = user_msg[len(UPDATE_CONFIG_TRIGGER):].strip().split(maxsplit=1)
                if len(command_parts) == 2:
                    variable_name = command_parts[0].strip()
                    new_value = command_parts[1].strip()
                    if variable_name in SUPPORTED_VARIABLES:
                        _, reply_text_update = update_config_value(
                            AUTH_CONFIG_FILE_PATH,
                            variable_name,
                            new_value
                        )
                        content = json.dumps({"text": reply_text_update})
                    else:
                        error_msg = (
                            f"不支持更新变量 '{variable_name}'，"
                            f"只能更新: {', '.join(SUPPORTED_VARIABLES)}"
                        )
                        content = json.dumps({"text": error_msg})
                else:
                    error_msg = (
                        f"格式错误，请使用 '{UPDATE_CONFIG_TRIGGER} 变量名 新值' 格式，"
                        f"例如：{UPDATE_CONFIG_TRIGGER} cookies xxxx"
                    )
                    content = json.dumps({"text": error_msg})

        elif "帮助" in user_msg:
            log_and_print(f"收到 [帮助demo指令] 文本消息: {user_msg}", log_level="INFO")

            content = json.dumps({
                "text": "<b>我可以帮你做这些事情：</b>\n\n"
                        "1. <b>图片风格转换</b>\n"
                        "上传任意照片，我会把照片转换成<i>剪纸贺卡</i>风格的图片\n\n"
                        "2. <b>视频推荐</b>\n"
                        "输入\"B站\"或\"视频\"，我会<i>随机推荐</i>B站视频给你\n\n"
                        "3. <b>图片分享</b>\n"
                        "输入\"图片\"或\"壁纸\"，我会分享<u>精美图片</u>\n\n"
                        "4. <b>音频播放</b>\n"
                        "输入\"音频\"，我会发送<u>语音消息</u>\n\n"
                        "<at user_id=\"all\"></at> 随时输入\"帮助\"可以<i>再次查看</i>此菜单"
            })

        elif "富文本" in user_msg:
            log_and_print(f"收到 [富文本demo指令] 消息: {user_msg}", log_level="INFO")
            try:
                msg_type, content = handle_image_upload(os.getenv("SAMPLE_PIC_PATH", ""))
                if msg_type == "image" and content:
                    image_key = json.loads(content)["image_key"]
                    msg_type = "post"
                    content = json.dumps({
                        "zh_cn": {
                            "title": "富文本示例",
                            "content": [
                                [
                                    {"tag": "text", "text": "第一行:", "style": ["bold", "underline"]},
                                    {"tag": "a", "href": "https://open.feishu.cn", "text": "飞书开放平台", "style": ["italic"]},
                                    {"tag": "at", "user_id": "all", "style": ["lineThrough"]}
                                ],
                                [{"tag": "img", "image_key": image_key}],
                                [
                                    {"tag": "text", "text": "代码示例:"},
                                    {"tag": "code_block", "language": "PYTHON", "text": "print('Hello World')"}
                                ],
                                [{"tag": "hr"}],
                                [{"tag": "md", "text": "**Markdown内容**\n- 列表项1\n- 列表项2\n```python\nprint('代码块')\n```"}]
                            ]
                        }
                    })
            except Exception as e:
                content = json.dumps({"text": f"富文本处理错误: {str(e)}"})

        elif "B站" in user_msg or "视频" in user_msg:
            log_and_print(f"收到 [视频推荐demo指令] 文本消息: {user_msg}", log_level="INFO")
            video = random.choice(bili_videos)
            content = json.dumps({
                "text": (
                    f"为你推荐B站视频：\n"
                    f"{video['title']}\n"
                    f"https://www.bilibili.com/video/{video['bvid']}"
                )
            })

        elif "生图" in user_msg or "AI画图" in user_msg:
            log_and_print(f"收到 [AI生图指令] 文本消息: {user_msg}", log_level="INFO")
            send_message("text", json.dumps({"text": "正在生成图片，请稍候..."}))
            try:
                prompt = user_msg.replace("生图", "").replace("AI画图", "").strip()
                msg_type, content = handle_ai_image_generation(prompt)
            except Exception as e:
                content = json.dumps({"text": f"AI生图错误: {str(e)}"})

        elif "图片" in user_msg or "壁纸" in user_msg:
            log_and_print(f"收到 [图片demo指令] 文本消息: {user_msg}", log_level="INFO")
            send_message("text", json.dumps({"text": "正在处理图片，请稍候..."}))
            try:
                msg_type, content = handle_image_upload(os.getenv("SAMPLE_PIC_PATH", ""))
            except Exception as e:
                content = json.dumps({"text": f"图片处理错误: {str(e)}"})

        elif "音频" in user_msg:
            log_and_print(f"收到 [音频demo指令] 文本消息: {user_msg}", log_level="INFO")
            send_message("text", json.dumps({"text": "正在处理音频，请稍候..."}))
            try:
                msg_type, content = handle_audio_upload(os.getenv("SAMPLE_AUDIO_PATH", ""))
            except Exception as e:
                content = json.dumps({"text": f"音频处理错误: {str(e)}"})

        elif "配音" in user_msg:
            log_and_print(f"收到 [配音指令] 文本消息: {user_msg}", log_level="INFO")
            send_message("text", json.dumps({"text": "正在生成配音，请稍候..."}))
            try:
                tts_text = user_msg.split("配音", 1)[1].strip()

                # 直接获取音频字节流
                audio_data = coze_tts.generate(tts_text)
                if not audio_data:
                    raise ValueError("TTS故障，请联系管理员检查API配置")

                # 使用内存文件避免磁盘IO
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                    tmp.write(audio_data)
                    tmp.flush()  # 确保数据写入
                    tmp_path = tmp.name

                try:
                    msg_type, content = handle_audio_upload(tmp_path)
                except Exception as upload_err:
                    raise Exception(f"音频上传失败: {str(upload_err)}") from upload_err
                finally:
                    # 清理临时文件
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)

            except Exception as e:
                error_msg = str(e)
                if "音频上传失败" not in error_msg:
                    error_msg = f"配音生成失败: {error_msg}"
                send_message("text", json.dumps({"text": error_msg}))

        elif "你好" in user_msg:
            log_and_print(f"收到 [问候demo指令] 文本消息: {user_msg}", log_level="INFO")
            content = json.dumps({"text": "你好呀！有什么我可以帮你的吗？"})
        else:
            log_and_print(f"收到 [文本消息] ，启用默认回复: {user_msg}", log_level="INFO")
            content = json.dumps({"text": f"收到你发送的消息：{user_msg}"})

    # 发送最终消息
    if content:
        send_message(msg_type, content)


# 注册事件处理
event_handler = (
    lark.EventDispatcherHandler.builder("", "")
    .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1)
    .build()
)

# 创建客户端
ws_log_level = lark.LogLevel[config.get('log_level', 'DEBUG')]
client = lark.Client.builder().app_id(lark.APP_ID).app_secret(lark.APP_SECRET).build()
wsClient = lark.ws.Client(
    lark.APP_ID,
    lark.APP_SECRET,
    event_handler=event_handler,
    log_level=ws_log_level
)


async def main_jupyter():
    """Jupyter环境下的主函数，建立WebSocket连接并保持运行"""
    await wsClient._connect()
    print("WebSocket 连接已建立，等待接收消息...")

    # now = datetime.datetime.now()
    # test_time_schedule = (now + datetime.timedelta(seconds=5)).strftime("%H:%M:%S") # 15秒后的时间
    # test_time_bilibili = (now + datetime.timedelta(seconds=15)).strftime("%H:%M:%S") # 30秒后的时间
    # test_time_summary = (now + datetime.timedelta(seconds=25)).strftime("%H:%M:%S")  # 45秒后的时间

    # schedule.every().day.at(test_time_schedule).do(send_daily_schedule) # 每天
    # schedule.every().day.at(test_time_bilibili).do(send_bilibili_updates) # 测试
    # schedule.every().day.at(test_time_summary).do(send_daily_summary)  #

    # schedule.every().day.at("07:30").do(send_daily_schedule) #  每天 7:30 发送日程
    # schedule.every().day.at("15:00").do(send_bilibili_updates) #  每天 15:00 发送 B站更新
    # schedule.every().day.at("22:00").do(send_daily_summary)  #  每天 22:00 发送每日总结
    try:
        while True:
            schedule.run_pending()
            await asyncio.sleep(10)
    except KeyboardInterrupt:
        print("程序已停止")
    finally:
        await wsClient._disconnect()


def main():
    """主函数，建立WebSocket连接并保持运行"""
    wsClient.start()
    print("WebSocket 连接已建立，等待接收消息...")

    try:
        while True:
            schedule.run_pending()
            time.sleep(10)
    except KeyboardInterrupt:
        print("程序已停止")


if __name__ == "__main__":
    if is_not_jupyter:
        main()
    else:
        print("Jupyter环境")
        # await main_jupyter()  # 导出时要注释掉
