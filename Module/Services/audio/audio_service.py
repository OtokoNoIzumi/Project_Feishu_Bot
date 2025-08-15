"""
音频服务 (Audio Service)

该模块提供音频处理功能，包括：
1. 文本转语音 (TTS)
2. 音频格式转换 (FFmpeg)
3. 临时文件管理
4. 音频上传处理
"""

import os
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import requests
from groq import Groq
from deepgram import DeepgramClient, PrerecordedOptions, FileSource

from Module.Common.scripts.common import debug_utils
from ..service_decorators import (
    service_operation_safe,
    external_api_safe,
    file_processing_safe,
)


class AudioService:
    """
    音频处理服务

    职责：
    1. TTS语音合成
    2. 音频格式转换
    3. 文件管理和清理
    """

    def __init__(self, app_controller=None):
        """
        初始化音频服务

        Args:
            app_controller: 应用控制器，用于获取配置
        """
        self.app_controller = app_controller
        self._load_config()

        # 初始化TTS服务
        self.tts_service = None
        if self.coze_api_base and self.coze_workflow_id and self.coze_access_token:
            self.tts_service = CozeTTS(
                api_base=self.coze_api_base,
                workflow_id=self.coze_workflow_id,
                access_token=self.coze_access_token,
                voice_id=self.voice_id,
            )

    def _load_config(self):
        """加载配置"""
        if self.app_controller:
            # 从配置服务获取
            config_service = self.app_controller.get_service("config")

            # FFmpeg 配置
            self.ffmpeg_path = (
                config_service.get("FFMPEG_PATH", "")
                if config_service
                else os.getenv("FFMPEG_PATH", "")
            )

            # Coze 配置 - 使用新的统一配置格式
            coze_cfg = config_service.get("coze", {}) if config_service else {}
            self.coze_api_base = coze_cfg.get(
                "api_base", "https://api.coze.cn/v1/workflow/run"
            )
            self.coze_workflow_id = coze_cfg.get("tts_workflow_id", "")
            self.voice_id = coze_cfg.get("voice_id", "peach")

            # Access token 从环境变量获取
            self.coze_access_token = os.getenv("COZE_API_KEY", "")

            # Groq 配置
            self.groq_api_key = os.getenv("GROQ_API_KEY", "")
            self.groq_stt_model = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")

            # Deepgram 配置
            self.deepgram_api_key = os.getenv("DEEPGRAM_API_KEY", "")
            self.deepgram_model = os.getenv("DEEPGRAM_MODEL", "nova-2")

            # 讯飞 配置
            self.xunfei_app_id = os.getenv("XUNFEI_APP_ID", "")
            self.xunfei_api_secret = os.getenv("XUNFEI_API_SECRET", "")
            self.xunfei_api_key = os.getenv("XUNFEI_API_KEY", "")
        else:
            # 从环境变量获取
            self.ffmpeg_path = os.getenv("FFMPEG_PATH", "")
            self.coze_api_base = os.getenv(
                "COZE_API_BASE", "https://api.coze.cn/v1/workflow/run"
            )
            self.coze_workflow_id = os.getenv("TTS_WORKFLOW_ID", "")
            self.coze_access_token = os.getenv("COZE_API_KEY", "")
            self.voice_id = "peach"

            # Groq 配置
            self.groq_api_key = os.getenv("GROQ_API_KEY", "")
            self.groq_stt_model = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")

            # Deepgram 配置
            self.deepgram_api_key = os.getenv("DEEPGRAM_API_KEY", "")
            self.deepgram_model = os.getenv("DEEPGRAM_MODEL", "nova-2")

    @external_api_safe("TTS语音生成失败", return_value=None, api_name="Coze TTS")
    def generate_tts(self, text: str) -> Optional[bytes]:
        """
        文本转语音

        Args:
            text: 要转换的文本

        Returns:
            Optional[bytes]: 音频数据，失败返回None
        """
        if not self.tts_service:
            debug_utils.log_and_print("TTS服务未初始化", log_level="ERROR")
            return None

        audio_data = self.tts_service.generate(text)

        if not audio_data:
            debug_utils.log_and_print("TTS生成失败，返回空数据", log_level="ERROR")
        return audio_data

    @file_processing_safe("音频格式转换失败", return_value=(None, 0))
    def convert_to_opus(
        self, input_path: str, output_dir: str = None, overwrite: bool = True
    ) -> Tuple[Optional[str], int]:
        """
        音频格式转换为opus

        Args:
            input_path: 输入音频文件路径
            output_dir: 输出目录
            overwrite: 是否覆盖已存在文件

        Returns:
            Tuple[Optional[str], int]: (输出文件路径, 音频时长毫秒)
        """
        input_path = Path(input_path)

        # 检查输入文件
        if not input_path.exists():
            debug_utils.log_and_print(
                f"输入文件不存在: {input_path}", log_level="ERROR"
            )
            return None, 0

        # 检查FFmpeg
        ffmpeg_cmd = self._get_ffmpeg_command()
        if not ffmpeg_cmd:
            debug_utils.log_and_print("FFmpeg不可用", log_level="ERROR")
            return None, 0

        # 设置输出路径
        output_path = Path(output_dir or input_path.parent) / f"{input_path.stem}.opus"

        if output_path.exists() and not overwrite:
            debug_utils.log_and_print(
                f"输出文件已存在: {output_path}", log_level="WARNING"
            )
            return str(output_path), 0

        # 构建FFmpeg命令
        cmd = [
            ffmpeg_cmd,
            "-i",
            str(input_path),
            "-strict",
            "-2",
            "-acodec",
            "opus",
            "-ac",
            "1",
            "-ar",
            "48000",
            "-y" if overwrite else "-n",
            str(output_path),
        ]

        # 执行转换
        with subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        ) as process:
            duration_ms = 0

            for line in process.stdout:
                if "Duration:" in line:
                    try:
                        time_str = line.split("Duration: ")[1].split(",")[0].strip()
                        h, m, s = time_str.split(":")
                        duration_ms = int(
                            (int(h) * 3600 + int(m) * 60 + float(s)) * 1000
                        )
                    except:
                        pass

            return_code = process.wait()

            if return_code != 0:
                debug_utils.log_and_print(
                    f"音频转换失败，返回码: {return_code}", log_level="ERROR"
                )
                return None, 0

            return str(output_path), duration_ms

    def _get_ffmpeg_command(self) -> Optional[str]:
        """获取可用的FFmpeg命令"""
        if self.ffmpeg_path:
            ffmpeg_path = Path(self.ffmpeg_path)
            if ffmpeg_path.exists():
                return str(ffmpeg_path)

        # 检查系统PATH中的ffmpeg
        if shutil.which("ffmpeg"):
            return "ffmpeg"

        return None

    @service_operation_safe("TTS请求处理失败", return_value=(False, None, "处理失败"))
    def process_tts_request(self, text: str) -> Tuple[bool, Optional[bytes], str]:
        """
        处理TTS请求的完整流程

        Args:
            text: 要转换的文本

        Returns:
            Tuple[bool, Optional[bytes], str]: (是否成功, 音频数据, 错误信息)
        """
        if not text.strip():
            return False, None, "文本内容为空"

        if not self.tts_service:
            return False, None, "TTS服务未配置"

        audio_data = self.generate_tts(text)
        if audio_data:
            return True, audio_data, ""

        return False, None, "TTS生成失败"

    def create_temp_audio_file(self, audio_data: bytes, suffix: str = ".mp3") -> str:
        """
        创建临时音频文件

        Args:
            audio_data: 音频数据
            suffix: 文件后缀

        Returns:
            str: 临时文件路径
        """
        # 使用with语句确保资源正确释放
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
            temp_file.write(audio_data)
            temp_file.flush()
            temp_file_path = temp_file.name

        return temp_file_path

    @file_processing_safe("清理临时文件失败")
    def cleanup_temp_file(self, file_path: str):
        """
        清理临时文件

        Args:
            file_path: 文件路径
        """
        if os.path.exists(file_path):
            os.unlink(file_path)

    def get_status(self) -> Dict[str, Any]:
        """获取音频服务状态"""
        ffmpeg_available = self._get_ffmpeg_command() is not None
        tts_available = self.tts_service is not None

        return {
            "service_type": "AudioService",
            "ffmpeg_available": ffmpeg_available,
            "ffmpeg_path": self.ffmpeg_path or "system",
            "tts_available": tts_available,
            "stt_available": bool(self.groq_api_key),
            "tts_config": (
                {
                    "api_base": self.coze_api_base,
                    "workflow_id": (
                        self.coze_workflow_id[:10] + "..."
                        if len(self.coze_workflow_id) > 10
                        else self.coze_workflow_id
                    ),
                    "voice_id": self.voice_id,
                }
                if tts_available
                else None
            ),
            "stt_config": {
                "groq": (
                    {
                        "groq_stt_model": self.groq_stt_model,
                        "groq_api_key": "已配置" if self.groq_api_key else "未配置",
                    }
                    if bool(self.groq_api_key)
                    else None
                ),
                "deepgram": (
                    {
                        "deepgram_model": self.deepgram_model,
                        "deepgram_api_key": (
                            "已配置" if self.deepgram_api_key else "未配置"
                        ),
                    }
                    if bool(self.deepgram_api_key)
                    else None
                ),
            },
        }

    @external_api_safe(
        "Groq STT转写失败", return_value=(False, ""), api_name="Groq STT"
    )
    def transcribe_audio_with_groq(
        self, audio_bytes: bytes, prompt: str = "", filename_hint: str = "audio.ogg"
    ) -> Tuple[bool, str]:
        """
        使用 Groq API 进行音频转写

        Args:
            audio_bytes: 音频二进制数据
            filename_hint: 文件名提示，用于 API 调用

        Returns:
            Tuple[bool, str]: (成功标志, 转写文本或错误信息)
        """
        if not self.groq_api_key:
            debug_utils.log_and_print("Groq API Key 未配置", log_level="ERROR")
            return False, "Groq API Key 未配置"

        try:
            # 创建 Groq 客户端
            client = Groq(api_key=self.groq_api_key)

            # 调用 Groq STT API
            # 比较好的做法是至少加点prompt把当前的event name加上？有没有流式回复？
            transcription = client.audio.transcriptions.create(
                model=self.groq_stt_model,
                file=(filename_hint, audio_bytes),
                prompt=prompt,
                response_format="verbose_json",
            )

            return True, transcription.text

        except Exception as e:
            debug_utils.log_and_print(f"Groq STT 调用失败: {e}", log_level="ERROR")
            return False, f"转写失败: {str(e)}"

    @external_api_safe(
        "Deepgram STT转写失败", return_value=(False, ""), api_name="Deepgram STT"
    )
    def transcribe_audio_with_deepgram(
        self, audio_bytes: bytes, filename_hint: str = "audio.ogg"
    ) -> Tuple[bool, str]:
        """
        使用 Deepgram API 进行音频转写

        Args:
            audio_bytes: 音频二进制数据
            filename_hint: 文件名提示，用于 API 调用

        Returns:
            Tuple[bool, str]: (成功标志, 转写文本或错误信息)
        """
        if not self.deepgram_api_key:
            debug_utils.log_and_print("Deepgram API Key 未配置", log_level="ERROR")
            return False, "Deepgram API Key 未配置"

        try:
            # 创建 Deepgram 客户端
            deepgram = DeepgramClient(api_key=self.deepgram_api_key)

            # 准备音频数据
            payload: FileSource = {
                "buffer": audio_bytes,
            }

            # 配置转写选项
            options = PrerecordedOptions(
                model=self.deepgram_model,
                smart_format=True,
                language="zh-CN",  # 指定中文
            )

            # 调用转写 API
            response = deepgram.listen.rest.v("1").transcribe_file(payload, options)

            # 提取转写文本
            if response.results and response.results.channels:
                channel = response.results.channels[0]
                if channel.alternatives:
                    transcript = channel.alternatives[0].transcript
                    if transcript:
                        return True, transcript

            debug_utils.log_and_print("Deepgram STT 返回空文本", log_level="WARNING")
            return False, "转写结果为空"

        except Exception as e:
            debug_utils.log_and_print(f"Deepgram STT 调用失败: {e}", log_level="ERROR")
            return False, f"转写失败: {str(e)}"


class CozeTTS:
    """
    Coze TTS服务

    封装Coze API的TTS功能
    """

    def __init__(
        self,
        api_base: str,
        workflow_id: str,
        access_token: str,
        voice_id: str = "peach",
    ):
        """
        初始化Coze TTS服务

        Args:
            api_base: API基础URL
            workflow_id: 工作流ID
            access_token: 访问令牌
            voice_id: 语音ID
        """
        self.api_base = api_base
        self.workflow_id = workflow_id
        self.access_token = access_token
        self.voice_id = voice_id

    def generate(self, text: str) -> Optional[bytes]:
        """
        生成语音

        Args:
            text: 文本内容

        Returns:
            Optional[bytes]: 音频数据，失败返回None
        """
        if not self.workflow_id:
            debug_utils.log_and_print("Coze workflow_id未配置", log_level="ERROR")
            return None

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        payload = {
            "workflow_id": self.workflow_id,
            "parameters": {
                "input": text,
                "voicebranch": self.voice_id,
                "voice_type": "zh_female_gufengshaoyu_mars_bigtts",
            },
        }

        try:
            # 第一步：调用Coze API获取音频URL
            response = requests.post(
                self.api_base, headers=headers, json=payload, timeout=60
            )
            response.raise_for_status()

            if response.status_code != 200:
                debug_utils.log_and_print(
                    f"Coze API响应错误: {response.status_code}", log_level="ERROR"
                )
                return None

            result = response.json()
            if result.get("code") != 0:
                debug_utils.log_and_print(
                    f"Coze API业务错误: {result}", log_level="ERROR"
                )
                return None

            # 解析响应数据
            data = json.loads(result.get("data", "{}"))
            url_mappings = {"gaoleng": "url", "speech": "link", "ruomei": "url"}

            # 查找第一个可用的音频URL
            audio_url = None
            for source, url_key in url_mappings.items():
                if data.get(source) and data[source].get(url_key):
                    audio_url = data[source][url_key]
                    break

            if not audio_url:
                debug_utils.log_and_print("未找到有效的音频URL", log_level="ERROR")
                return None

            # 第二步：下载音频数据
            audio_response = requests.get(audio_url, timeout=60)
            audio_response.raise_for_status()

            return audio_response.content

        except requests.exceptions.RequestException as e:
            debug_utils.log_and_print(
                f"Coze TTS网络请求失败: {e}，请检查access_token是否过期 {self.access_token}",
                log_level="ERROR",
            )
            return None
        except json.JSONDecodeError as e:
            debug_utils.log_and_print(f"Coze TTS响应解析失败: {e}", log_level="ERROR")
            return None
        except Exception as e:
            debug_utils.log_and_print(f"Coze TTS处理失败: {e}", log_level="ERROR")
            return None
