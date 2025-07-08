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
import requests
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, Union

from Module.Common.scripts.common import debug_utils
from ..service_decorators import service_operation_safe, external_api_safe, file_processing_safe


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
                voice_id=self.voice_id
            )

    def _load_config(self):
        """加载配置"""
        if self.app_controller:
            # 从配置服务获取
            success, ffmpeg = self.app_controller.call_service('config', 'get', 'FFMPEG_PATH', '')
            self.ffmpeg_path = ffmpeg if success else os.getenv("FFMPEG_PATH", "")

            success, coze_url = self.app_controller.call_service('config', 'get', 'coze_bot_url', '')
            self.coze_api_base = coze_url if success else os.getenv("COZE_API_BASE", "https://api.coze.cn/v1/workflow/run")

            success, bot_id = self.app_controller.call_service('config', 'get', 'bot_id', '')
            self.coze_workflow_id = bot_id if success else ''

            success, voice_id = self.app_controller.call_service('config', 'get', 'voice_id', 'peach')
            self.voice_id = voice_id if success else 'peach'

            self.coze_access_token = os.getenv("COZE_API_KEY", "")
        else:
            # 从环境变量获取
            self.ffmpeg_path = os.getenv("FFMPEG_PATH", "")
            self.coze_api_base = os.getenv("COZE_API_BASE", "https://api.coze.cn/v1/workflow/run")
            self.coze_workflow_id = os.getenv("BOT_ID", "")
            self.coze_access_token = os.getenv("COZE_API_KEY", "")
            self.voice_id = "peach"

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
        self,
        input_path: str,
        output_dir: str = None,
        overwrite: bool = True
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
            debug_utils.log_and_print(f"输入文件不存在: {input_path}", log_level="ERROR")
            return None, 0

        # 检查FFmpeg
        ffmpeg_cmd = self._get_ffmpeg_command()
        if not ffmpeg_cmd:
            debug_utils.log_and_print("FFmpeg不可用", log_level="ERROR")
            return None, 0

        # 设置输出路径
        output_path = Path(output_dir or input_path.parent) / f"{input_path.stem}.opus"

        if output_path.exists() and not overwrite:
            debug_utils.log_and_print(f"输出文件已存在: {output_path}", log_level="WARNING")
            return str(output_path), 0

        # 构建FFmpeg命令
        cmd = [
            ffmpeg_cmd,
            "-i", str(input_path),
            "-strict", "-2",
            "-acodec", "opus",
            "-ac", "1",
            "-ar", "48000",
            "-y" if overwrite else "-n",
            str(output_path)
        ]

        # 执行转换
        with subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        ) as process:
            duration_ms = 0

            for line in process.stdout:
                if "Duration:" in line:
                    try:
                        time_str = line.split("Duration: ")[1].split(",")[0].strip()
                        h, m, s = time_str.split(":")
                        duration_ms = int((int(h)*3600 + int(m)*60 + float(s)) * 1000)
                    except:
                        pass

            return_code = process.wait()

            if return_code != 0:
                debug_utils.log_and_print(f"音频转换失败，返回码: {return_code}", log_level="ERROR")
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
        else:
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
        temp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        temp_file.write(audio_data)
        temp_file.flush()
        temp_file.close()

        return temp_file.name

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
            "tts_config": {
                "api_base": self.coze_api_base,
                "workflow_id": self.coze_workflow_id[:10] + "..." if len(self.coze_workflow_id) > 10 else self.coze_workflow_id,
                "voice_id": self.voice_id
            } if tts_available else None
        }


class CozeTTS:
    """
    Coze TTS服务

    封装Coze API的TTS功能
    """

    def __init__(self, api_base: str, workflow_id: str, access_token: str, voice_id: str = "peach"):
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
            "Content-Type": "application/json"
        }

        payload = {
            "workflow_id": self.workflow_id,
            "parameters": {
                "input": text,
                "voicebranch": self.voice_id,
                "voice_type": "zh_female_gufengshaoyu_mars_bigtts"
            }
        }

        try:
            # 第一步：调用Coze API获取音频URL
            response = requests.post(self.api_base, headers=headers, json=payload, timeout=60)
            response.raise_for_status()

            if response.status_code != 200:
                debug_utils.log_and_print(f"Coze API响应错误: {response.status_code}", log_level="ERROR")
                return None

            result = response.json()
            if result.get("code") != 0:
                debug_utils.log_and_print(f"Coze API业务错误: {result}", log_level="ERROR")
                return None

            # 解析响应数据
            data = json.loads(result.get("data", "{}"))
            url_mappings = {
                "gaoleng": "url",
                "speech": "link",
                "ruomei": "url"
            }

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
            debug_utils.log_and_print(f"Coze TTS网络请求失败: {e}，请检查access_token是否过期 {self.access_token}", log_level="ERROR")
            return None
        except json.JSONDecodeError as e:
            debug_utils.log_and_print(f"Coze TTS响应解析失败: {e}", log_level="ERROR")
            return None
        except Exception as e:
            debug_utils.log_and_print(f"Coze TTS处理失败: {e}", log_level="ERROR")
            return None