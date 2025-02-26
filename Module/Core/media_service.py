"""
媒体服务模块

该模块提供媒体处理功能，包括音频转换、文本转语音等
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, Union
import requests
import base64
import json


class MediaService:
    """媒体处理服务"""

    def __init__(self, ffmpeg_path: str = None, gradio_client=None, coze_api_settings: Dict[str, str] = None):
        """
        初始化媒体服务

        Args:
            ffmpeg_path: ffmpeg可执行文件路径
            gradio_client: Gradio客户端实例
            coze_api_settings: Coze API设置
        """
        self.ffmpeg_path = ffmpeg_path
        self.gradio_client = gradio_client
        self.coze_api_settings = coze_api_settings or {}

        # 如果提供了Coze API设置，初始化TTS服务
        if self.coze_api_settings:
            self.tts_service = CozeTTS(
                api_base=self.coze_api_settings.get("api_base", ""),
                workflow_id=self.coze_api_settings.get("workflow_id", ""),
                access_token=self.coze_api_settings.get("access_token", ""),
                voice_id=self.coze_api_settings.get("voice_id", "peach")
            )
        else:
            self.tts_service = None

    def convert_to_opus(
        self,
        input_path: str,
        output_dir: str = None,
        overwrite: bool = False
    ) -> Tuple[str, int]:
        """
        将音频文件转换为opus格式

        Args:
            input_path: 输入音频文件路径
            output_dir: 输出目录
            overwrite: 是否覆盖已存在的输出文件

        Returns:
            Tuple[str, int]: (输出文件路径, 音频时长(毫秒))

        Raises:
            FileNotFoundError: ffmpeg或输入文件不存在
            RuntimeError: 转换失败
            FileExistsError: 输出文件已存在且不允许覆盖
        """
        input_path = Path(input_path)
        ffmpeg_path = Path(self.ffmpeg_path) if self.ffmpeg_path else None

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

            return str(output_path), duration or 0

        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"转换失败: {e.stderr.strip()}") from e

    def generate_ai_image(self, prompt: str = None, image_input: Dict = None) -> Optional[str]:
        """
        使用AI生成图片或处理图片

        Args:
            prompt: 文本提示词,用于AI生图
            image_input: 图片输入参数,用于图片处理

        Returns:
            Optional[str]: 生成的图片文件路径，若生成失败则返回None
        """
        if self.gradio_client is None:
            return None

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

        try:
            result = self.gradio_client.predict(**predict_kwargs)

            if not isinstance(result, tuple) or len(result) == 0:
                return None

            # 返回所有非None的图片路径
            valid_paths = []
            for image_path in result:
                if image_path is not None:
                    valid_paths.append(image_path)
            return valid_paths if valid_paths else None

        except Exception as e:
            print(f"AI图像生成失败: {e}")
            return None

    def generate_tts(self, text: str) -> Optional[bytes]:
        """
        将文本转换为语音

        Args:
            text: 文本内容

        Returns:
            Optional[bytes]: 音频数据，若转换失败则返回None
        """
        if self.tts_service is None:
            return None

        try:
            return self.tts_service.generate(text)
        except Exception as e:
            print(f"TTS生成失败: {e}")
            return None


class CozeTTS:
    """Coze TTS 服务"""

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
            Optional[bytes]: 音频数据，若生成失败则返回None
        """
        if not self.workflow_id:
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
        print('test_payload', payload)
        try:
            # 获取音频URL
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
                    print('test_data', data)
                    # 查找第一个有效的音频URL
                    audio_url = None
                    for source, url_key in url_mappings.items():
                        if data.get(source):
                            audio_url = data[source].get(url_key)
                            if audio_url:
                                break

                    if audio_url:
                        # 下载音频
                        audio_response = requests.get(audio_url, timeout=60)
                        audio_response.raise_for_status()
                        return audio_response.content

            return None
        except Exception as e:
            print(f"TTS流程失败: {e}")
            return None