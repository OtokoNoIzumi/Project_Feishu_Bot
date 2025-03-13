"""
飞书平台操作处理模块

该模块提供飞书平台特定操作的处理实现，如图片处理、语音生成、富文本等
"""

import os
import json
import base64
import tempfile
import subprocess
import shutil
import traceback
from pathlib import Path

from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    CreateChatRequest,
    CreateChatRequestBody,
    CreateImageRequest,
    CreateImageRequestBody,
    CreateFileRequest,
    CreateFileRequestBody,
    GetMessageResourceRequest,
)

# from Module.Common.scripts.common import debug_utils
# from Module.Interface.message import MessageType


class FeishuActionHandler:
    """飞书平台操作处理基类"""

    def __init__(self, client, bot_service=None):
        """
        初始化处理器

        Args:
            client: 飞书API客户端
            bot_service: 机器人服务实例
        """
        self.client = client
        self.bot_service = bot_service

    def _create_message(self, receive_id: str, receive_id_type: str, msg_type: str, content: str, **kwargs) -> bool:
        """
        创建消息

        Args:
            receive_id: 接收者ID
            receive_id_type: 接收者ID类型
            msg_type: 消息类型
            content: 消息内容
            **kwargs: 其他参数，包括可能的data

        Returns:
            bool: 是否成功
        """
        # print(f"[DEBUG] 发送消息 - 类型: {msg_type}")
        # print(f"[DEBUG] 消息内容: {content}")

        # 检查是否有原始消息数据
        message_data = kwargs.get("data")

        try:
            if message_data and hasattr(message_data, "extra_data"):
                # 获取聊天类型
                chat_type = message_data.extra_data.get("chat_type", "")
                # print(f"[DEBUG] 聊天类型: {chat_type}")
                # print(f"[DEBUG] 原始消息数据: {message_data}")
                # print(f"[DEBUG] 原始消息数据: {message_data.__dict__}")

                # 按照main.py的逻辑实现，使用chat_type决定发送方式
                if chat_type == "p2p":
                    # 对于p2p对话，使用chat_id发送

                    request = CreateMessageRequest.builder().receive_id_type("chat_id").request_body(
                        CreateMessageRequestBody.builder()
                        .receive_id(message_data.chat_id)
                        .msg_type(msg_type)
                        .content(content)
                        .build()
                    ).build()

                    # print(f"[DEBUG] 使用chat.create API发送p2p消息到chat_id: {message_data.chat_id}")
                    response = self.client.im.v1.chat.create(request)
                else:
                    # 对于群聊，使用消息回复
                    from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody

                    request = (
                        ReplyMessageRequest.builder()
                        .message_id(message_data.message_id)
                        .request_body(
                            ReplyMessageRequestBody.builder()
                            .content(content)
                            .msg_type(msg_type)
                            .build()
                        )
                        .build()
                    )

                    # print(f"[DEBUG] 使用message.reply API回复消息message_id: {message_data.message_id}")
                    response = self.client.im.v1.message.reply(request)
            else:
                # 兼容旧逻辑，根据receive_id_type决定发送方式
                # print(f"[DEBUG] 无原始消息数据，使用receive_id_type: {receive_id_type}")
                # print(f"[DEBUG 旧版本调用排查] 无原始消息数据，使用receive_id_type: {receive_id_type}")
                if receive_id_type == "chat_id":
                    # 对于chat_id使用chat.create API

                    request = CreateChatRequest.builder().request_body(
                        CreateChatRequestBody.builder()
                        .chat_id(receive_id)  # 这里可能有问题？
                        .msg_type(msg_type)
                        .content(content)
                        .build()
                    ).build()

                    response = self.client.im.v1.chat.create(request)
                else:
                    # 对于其他类型使用标准message.create API
                    request = CreateMessageRequest.builder().receive_id_type(receive_id_type).request_body(
                        CreateMessageRequestBody.builder()
                        .receive_id(receive_id)
                        .msg_type(msg_type)
                        .content(content)
                        .build()
                    ).build()

                    response = self.client.im.v1.message.create(request)

            # 打印响应信息
            # print(f"[DEBUG] 响应类型: {type(response).__name__}")
            # print(f"[DEBUG] 响应成功: {response.success()}")

            # if not response.success():
            #     print(f"[ERROR] 错误码: {response.code}")
            #     print(f"[ERROR] 错误信息: {response.msg}")
            #     if hasattr(response, 'request_id'):
            #         print(f"[ERROR] 请求ID: {response.request_id}")

            # if hasattr(response, 'data') and response.data:
            #     print(f"[DEBUG] 响应数据: {response.data}")
            #     print(f"[DEBUG] 数据属性: {dir(response.data)}")

            return response.success()

        except Exception as e:
            print(f"[ERROR] 发送消息异常: {str(e)}")
            print(f"[ERROR] 异常堆栈: {traceback.format_exc()}")
            return False

    def send_notification(self, receive_id: str, receive_id_type: str, text: str, **kwargs) -> bool:
        """
        发送通知消息

        Args:
            receive_id: 接收者ID
            receive_id_type: 接收者ID类型
            text: 通知文本
            **kwargs: 其他参数，包括可能的data

        Returns:
            bool: 是否成功
        """
        content = json.dumps({"text": text})
        return self._create_message(receive_id, receive_id_type, "text", content, **kwargs)


class RichTextHandler(FeishuActionHandler):
    """富文本处理"""

    def handle(self, receive_id: str, receive_id_type: str, **kwargs) -> bool:
        """处理富文本生成请求"""
        # 获取原始消息数据
        message_data = kwargs.get("data")
        # print(f"[DEBUG] 富文本处理器收到原始消息数据: {message_data is not None}")

        # 获取示例图片
        sample_pic_path = os.getenv("SAMPLE_PIC_PATH", "")
        if not sample_pic_path or not os.path.exists(sample_pic_path):
            return self.send_notification(receive_id, receive_id_type, "示例图片不存在，无法创建富文本消息", data=message_data)

        # 上传图片
        with open(sample_pic_path, "rb") as image_file:
            upload_response = self.client.im.v1.image.create(
                CreateImageRequest.builder()
                .request_body(
                    CreateImageRequestBody.builder()
                    .image_type("message")
                    .image(image_file)
                    .build()
                )
                .build()
            )

            if not (upload_response.success() and upload_response.data and upload_response.data.image_key):
                return self.send_notification(receive_id, receive_id_type, "图片上传失败，无法创建富文本消息", data=message_data)

            image_key = upload_response.data.image_key

            # 创建富文本消息
            post_content = json.dumps({
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

            return self._create_message(receive_id, receive_id_type, "post", post_content, data=message_data)


class ImageGenerationHandler(FeishuActionHandler):
    """AI图像生成处理"""

    def handle(self, receive_id: str, receive_id_type: str, **kwargs) -> bool:
        """处理AI图像生成请求"""
        prompt = kwargs.get("prompt", "")
        message_data = kwargs.get("data")
        # print(f"[DEBUG] AI图像生成处理器收到原始消息数据: {message_data is not None}")

        if not self.bot_service or not self.bot_service.media_service:
            return self.send_notification(receive_id, receive_id_type, "系统未配置图像生成服务", data=message_data)

        # 先发送处理中的提示
        self.send_notification(receive_id, receive_id_type, "正在生成图片，请稍候...", data=message_data)

        try:
            # 使用BotService的媒体服务生成图像
            image_paths = self.bot_service.process_ai_image(prompt=prompt)

            if not image_paths or len(image_paths) == 0:
                # 区分不同的错误情况
                if image_paths is None:
                    # 结果是None，对应main.py中的图片生成故障情况
                    return self.send_notification(receive_id, receive_id_type, "图片生成故障，已经通知管理员修复咯！", data=message_data)
                # else:
                # 结果是空列表，对应main.py中的全部为None的情况
                return self.send_notification(receive_id, receive_id_type, "图片生成失败了，建议您换个提示词再试试", data=message_data)

            # 跟踪是否至少有一个图片成功处理
            success_count = 0

            # 处理所有生成的图片
            for image_path in image_paths:
                # print(f"[DEBUG] 准备上传图片: {image_path}")
                if not image_path or not os.path.exists(image_path):
                    continue

                # 上传图片
                with open(image_path, "rb") as image_file:
                    upload_response = self.client.im.v1.image.create(
                        CreateImageRequest.builder()
                        .request_body(
                            CreateImageRequestBody.builder()
                            .image_type("message")
                            .image(image_file)
                            .build()
                        )
                        .build()
                    )

                    # print(f"[DEBUG] 上传响应成功: {upload_response.success()}")
                    # print(f"[DEBUG] 上传响应代码: {upload_response.code}")
                    # print(f"[DEBUG] 上传响应消息: {upload_response.msg}")
                    # if hasattr(upload_response, 'data'):
                    #     print(f"[DEBUG] 上传响应数据: {upload_response.data}")
                    #     if hasattr(upload_response.data, 'image_key'):
                    #         print(f"【DEBUG】图片键值: {upload_response.data.image_key}")
                    # print(f"【DEBUG】TRIGGERED: {upload_response.success() and upload_response.data and upload_response.data.image_key}")
                    if (
                        upload_response.success() and
                        upload_response.data and
                        upload_response.data.image_key
                    ):
                        # 发送图片消息
                        content = json.dumps({"image_key": upload_response.data.image_key})
                        # print(f"[DEBUG] 发送图片消息: {content}")
                        self._create_message(receive_id, receive_id_type, "image", content, data=message_data)
                        success_count += 1
                    else:
                        print(f"图片上传失败: {upload_response.code} - {upload_response.msg}")

            # 所有图片处理完成后检查结果
            if success_count > 0:
                return True
            # else:
            return self.send_notification(receive_id, receive_id_type, "没有成功处理任何图片", data=message_data)

        except Exception as e:
            return self.send_notification(
                receive_id,
                receive_id_type,
                f"图像生成出错: {str(e)}",
                data=message_data
            )


class ImageProcessHandler(FeishuActionHandler):
    """图片处理"""

    def handle(self, receive_id: str, receive_id_type: str, **kwargs) -> bool:
        """处理图片"""
        # print(f"[DEBUG] 图片处理器收到原始消息数据: {kwargs}")
        message_data = kwargs.get("data")
        image_key = message_data.extra_data.get("image_key", {})
        message_id = kwargs.get("message_id", "")
        # print(f"[DEBUG] 图片处理器收到原始消息数据: {message_data is not None}")

        if not image_key or not message_id:
            return self.send_notification(receive_id, receive_id_type, "图片信息不完整，无法处理", data=message_data)

        if not self.bot_service or not self.bot_service.media_service:
            return self.send_notification(receive_id, receive_id_type, "系统未配置图像处理服务", data=message_data)

        # 先发送处理中的提示
        self.send_notification(receive_id, receive_id_type, "正在转换图片风格，请稍候...", data=message_data)

        # 获取图片内容

        request = GetMessageResourceRequest.builder() \
            .message_id(message_id) \
            .file_key(image_key) \
            .type("image") \
            .build()

        response = self.client.im.v1.message_resource.get(request)
        # print(f"[DEBUG] 获取图片资源响应: {response}")
        # print(f"[DEBUG] 获取图片资源响应: {response.__dict__}")

        if not response.success():
            return self.send_notification(
                receive_id,
                receive_id_type,
                f"获取图片资源失败: {response.code} - {response.msg}",
                data=message_data
            )

        # 将图片数据转为可处理格式
        file_content = response.file.read()
        if not file_content:
            return self.send_notification(receive_id, receive_id_type, "图片数据为空", data=message_data)

        # 准备图片输入
        file_name = response.file_name
        # print(f"[DEBUG] 图片文件名: {file_name}")
        # print(f"[DEBUG] response.file属性: {dir(response.file)}")

        has_content_type = hasattr(response.file, "content_type")
        # print(f"[DEBUG] 是否有content_type属性: {has_content_type}")

        if has_content_type:
            # print(f"[DEBUG] 原始content_type值: {response.file.content_type}")
            mime_type = response.file.content_type
        else:
            # print(f"[DEBUG] 未找到content_type，使用默认值: image/jpeg")
            mime_type = "image/jpeg"

        meta = {
            "size": len(file_content),
            "mime_type": mime_type
        }
        # print(f"[DEBUG] 最终meta数据: {meta}")

        base64_image = base64.b64encode(file_content).decode('utf-8')
        image_url = f"data:{meta['mime_type']};base64,{base64_image}"

        # 创建与原项目一致的图片输入对象
        image_input = {
            "path": None,
            "url": image_url,
            "size": meta["size"],
            "orig_name": file_name or "image.jpg",
            "mime_type": meta["mime_type"],
            "is_stream": False,
            "meta": {}
        }

        try:
            # 处理图片
            image_paths = self.bot_service.process_ai_image(image_input=image_input)
            if not image_paths or len(image_paths) == 0:
                # 区分不同的错误情况
                if image_paths is None:
                    # 结果是None，对应main.py中的图片处理故障情况
                    return self.send_notification(receive_id, receive_id_type, "图片处理故障，已经通知管理员修复咯！", data=message_data)
                # else:
                    # 结果是空列表，对应main.py中的处理失败情况
                return self.send_notification(receive_id, receive_id_type, "图片处理失败了，请尝试使用其他图片", data=message_data)

            # 跟踪是否至少有一个图片成功处理
            success_count = 0

            # 处理所有生成的图片
            for image_path in image_paths:
                if not image_path or not os.path.exists(image_path):
                    continue

                # 上传处理后的图片
                with open(image_path, "rb") as image_file:
                    upload_response = self.client.im.v1.image.create(
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
                        # 发送图片消息
                        content = json.dumps({"image_key": upload_response.data.image_key})
                        self._create_message(receive_id, receive_id_type, "image", content, data=message_data)
                        success_count += 1
                    else:
                        print(f"处理后图片上传失败: {upload_response.code} - {upload_response.msg}")

            # 所有图片处理完成后检查结果
            if success_count > 0:
                return True
            # else:
            return self.send_notification(receive_id, receive_id_type, "没有成功处理任何图片", data=message_data)

        except Exception as e:
            return self.send_notification(
                receive_id,
                receive_id_type,
                f"图片处理出错: {str(e)}",
                data=message_data
            )


class SampleImageHandler(FeishuActionHandler):
    """示例图片分享"""

    def handle(self, receive_id: str, receive_id_type: str, **kwargs) -> bool:
        """分享示例图片"""
        message_data = kwargs.get("data")
        # print(f"[DEBUG] 示例图片处理器收到原始消息数据: {message_data is not None}")

        sample_pic_path = os.getenv("SAMPLE_PIC_PATH", "")
        if not sample_pic_path or not os.path.exists(sample_pic_path):
            return self.send_notification(receive_id, receive_id_type, "示例图片不存在", data=message_data)

        # 上传并发送图片
        with open(sample_pic_path, "rb") as image_file:
            upload_response = self.client.im.v1.image.create(
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
                content = json.dumps({"image_key": upload_response.data.image_key})
                return self._create_message(receive_id, receive_id_type, "image", content, data=message_data)
            # else:
            return self.send_notification(
                receive_id,
                receive_id_type,
                f"图片上传失败: {upload_response.code} - {upload_response.msg}",
                data=message_data
            )


class SampleAudioHandler(FeishuActionHandler):
    """示例音频分享"""

    def handle(self, receive_id: str, receive_id_type: str, **kwargs) -> bool:
        """分享示例音频"""
        message_data = kwargs.get("data")
        # print(f"[DEBUG] 示例音频处理器收到原始消息数据: {message_data is not None}")

        sample_audio_path = os.getenv("SAMPLE_AUDIO_PATH", "")
        if not sample_audio_path or not os.path.exists(sample_audio_path):
            return self.send_notification(receive_id, receive_id_type, "示例音频不存在", data=message_data)

        # 转换音频为opus格式
        input_path = Path(sample_audio_path)
        output_path = Path(input_path.parent) / f"{input_path.stem}.opus"

        # 检查ffmpeg
        ffmpeg_path = os.getenv("FFMPEG_PATH", "ffmpeg")
        if not shutil.which(ffmpeg_path):
            return self.send_notification(receive_id, receive_id_type, "未找到ffmpeg，无法处理音频", data=message_data)

        # 转换音频
        cmd = [
            ffmpeg_path,
            "-i", str(input_path),
            "-strict", "-2",
            "-acodec", "opus",
            "-ac", "1",
            "-ar", "48000",
            "-y",
            str(output_path)
        ]

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )

            duration = None
            for line in process.stdout:  # 实时读取输出
                if "Duration:" in line:
                    time_str = line.split("Duration: ")[1].split(",")[0].strip()
                    h, m, s = time_str.split(":")
                    duration = int((int(h)*3600 + int(m)*60 + float(s)) * 1000)

            return_code = process.wait()

            if return_code != 0:
                return self.send_notification(
                    receive_id, receive_id_type, f"音频转换失败，返回码: {return_code}", data=message_data
                )

            # 上传并发送音频
            with open(str(output_path), "rb") as audio_file:
                opus_filename = os.path.basename(output_path)
                upload_response = self.client.im.v1.file.create(
                    CreateFileRequest.builder()
                    .request_body(
                        CreateFileRequestBody.builder()
                        .file_type("opus")
                        .file_name(opus_filename)
                        .duration(str(int(duration) if duration else 0))
                        .file(audio_file)
                        .build()
                    ).build()
                )

                if upload_response.success() and upload_response.data and upload_response.data.file_key:
                    content = json.dumps({"file_key": upload_response.data.file_key})
                    return self._create_message(receive_id, receive_id_type, "audio", content, data=message_data)
                # else:
                return self.send_notification(
                    receive_id,
                    receive_id_type,
                    f"音频上传失败: {upload_response.code} - {upload_response.msg}",
                    data=message_data
                )

        except Exception as e:
            return self.send_notification(receive_id, receive_id_type, f"音频处理错误: {str(e)}", data=message_data)


class TTSGenerationHandler(FeishuActionHandler):
    """TTS语音生成"""

    def handle(self, receive_id: str, receive_id_type: str, **kwargs) -> bool:
        """处理TTS生成请求"""
        text = kwargs.get("text", "")
        message_data = kwargs.get("data")
        # print(f"[DEBUG] TTS处理器收到原始消息数据: {message_data is not None}")

        if not text:
            return self.send_notification(receive_id, receive_id_type, "TTS文本内容为空", data=message_data)

        if not self.bot_service or not self.bot_service.media_service:
            return self.send_notification(receive_id, receive_id_type, "系统未配置TTS服务", data=message_data)

        # 先发送处理中的提示
        self.send_notification(receive_id, receive_id_type, "正在生成配音，请稍候...", data=message_data)

        # 生成TTS音频
        audio_data = self.bot_service.generate_tts(text)

        if not audio_data:
            return self.send_notification(receive_id, receive_id_type, "TTS生成失败", data=message_data)

        # 保存为临时MP3文件
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
            temp_mp3_path = temp_file.name
            temp_file.write(audio_data)
        # print('test_temp_mp3_path', temp_mp3_path)
        try:
            # 转换为opus格式
            opus_path, duration = self.bot_service.media_service.convert_to_opus(
                temp_mp3_path,
                overwrite=True
            )
            # print('test_opus_path', opus_path)
            # print('test_duration', duration)
            # print('test_opus_path_exists', os.path.exists(opus_path))

            if not opus_path or not os.path.exists(opus_path):
                os.unlink(temp_mp3_path)
                return self.send_notification(receive_id, receive_id_type, "音频格式转换失败", data=message_data)

            # 上传并发送音频
            file_key = None
            with open(opus_path, "rb") as audio_file:
                opus_filename = os.path.basename(opus_path)
                # print('test_opus_filename', opus_filename)
                upload_response = self.client.im.v1.file.create(
                    CreateFileRequest.builder()
                    .request_body(
                        CreateFileRequestBody.builder()
                        .file_type("opus")
                        .file_name(opus_filename)
                        .duration(str(int(duration)))
                        .file(audio_file)
                        .build()
                    ).build()
                )

                # 保存file_key以便在with块外使用
                if upload_response.success() and upload_response.data and upload_response.data.file_key:
                    file_key = upload_response.data.file_key

            # 在with块外处理响应和清理文件
            if file_key:
                content = json.dumps({"file_key": file_key})
                # 删除临时文件
                try:
                    os.unlink(temp_mp3_path)
                    os.unlink(opus_path)
                except Exception as e:
                    print(f"[WARNING] 清理临时文件失败: {e}")

                return self._create_message(receive_id, receive_id_type, "audio", content, data=message_data)
            # 清理临时文件
            try:
                os.unlink(temp_mp3_path)
                os.unlink(opus_path)
            except Exception as e:
                print(f"[WARNING] 清理临时文件失败: {e}")

            return self.send_notification(
                receive_id,
                receive_id_type,
                f"TTS音频上传失败: {upload_response.code if hasattr(upload_response, 'code') else 'Unknown'} - {upload_response.msg if hasattr(upload_response, 'msg') else 'Unknown error'}",
                data=message_data
            )
        except Exception as e:
            # 清理临时文件
            if os.path.exists(temp_mp3_path):
                try:
                    os.unlink(temp_mp3_path)
                except:
                    pass
            return self.send_notification(
                receive_id,
                receive_id_type,
                f"TTS处理出错: {str(e)}",
                data=message_data
            )


class BiliVideoHandler(FeishuActionHandler):
    """B站视频推荐处理器"""

    async def handle(self, receive_id: str, receive_id_type: str, **kwargs) -> bool:
        """
        处理B站视频推荐请求

        Args:
            receive_id: 接收者ID
            receive_id_type: 接收者ID类型
            **kwargs: 其他参数

        Returns:
            bool: 是否成功
        """
        if not self.bot_service or not self.bot_service.notion_service:
            return self._create_message(
                receive_id,
                receive_id_type,
                "text",
                json.dumps({"text": "抱歉，B站视频推荐服务暂时不可用"})
            )

        try:
            # 获取B站视频推荐
            video = await self.bot_service.notion_service.get_bili_video()

            if not video["success"]:
                return self._create_message(
                    receive_id,
                    receive_id_type,
                    "text",
                    json.dumps({"text": "暂时没有找到适合你的B站视频，请稍后再试"})
                )

            # 构建卡片消息，优化布局使排版更加统一
            card = {
                "config": {
                    "wide_screen_mode": True
                },
                "elements": [
                    # 视频标题
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**📽️ {video['title']}**"
                        }
                    },
                    # 视频基本信息 - 作者、优先级
                    {
                        "tag": "div",
                        "fields": [
                            {
                                "is_short": True,
                                "text": {
                                    "tag": "lark_md",
                                    "content": f"**作者:** {video.get('author', '未知')}"
                                }
                            },
                            {
                                "is_short": True,
                                "text": {
                                    "tag": "lark_md",
                                    "content": f"**优先级:** {video.get('chinese_priority', '未知')}"
                                }
                            }
                        ]
                    },
                    # 视频基本信息 - 时长、来源
                    {
                        "tag": "div",
                        "fields": [
                            {
                                "is_short": True,
                                "text": {
                                    "tag": "lark_md",
                                    "content": f"**时长:** {video.get('duration_str', '未知')}"
                                }
                            },
                            {
                                "is_short": True,
                                "text": {
                                    "tag": "lark_md",
                                    "content": f"**来源:** {video.get('chinese_source', '未知')}"
                                }
                            }
                        ]
                    },
                    # 投稿日期
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**投稿日期:** {video.get('upload_date', '未知')}"
                        }
                    },
                    # 分隔线
                    {
                        "tag": "hr"
                    },
                    # 推荐概要
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**推荐理由:**\n{video.get('summary', '无')}"
                        }
                    },
                    # 分隔线
                    {
                        "tag": "hr"
                    },
                    # 视频链接
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"[🔗 点击观看视频]({video['url']})"
                        }
                    },
                    # 按钮区域
                    {
                        "tag": "action",
                        "actions": [
                            {
                                "tag": "button",
                                "text": {
                                    "tag": "plain_text",
                                    "content": "👍 标记为已读"
                                },
                                "type": "primary",
                                "value": {
                                    "action": "mark_bili_read",
                                    "pageid": video["pageid"]
                                }
                            }
                        ]
                    }
                ],
                "header": {
                    "template": "blue",
                    "title": {
                        "tag": "plain_text",
                        "content": "📺 B站视频推荐"
                    }
                }
            }

            # 发送卡片消息
            return self._create_message(
                receive_id,
                receive_id_type,
                "interactive",
                json.dumps(card)
            )

        except Exception as e:
            error_msg = f"处理B站视频推荐失败: {str(e)}"
            print(error_msg)
            print(traceback.format_exc())

            return self._create_message(
                receive_id,
                receive_id_type,
                "text",
                json.dumps({"text": "抱歉，获取B站视频推荐时出现错误，请稍后再试"})
            )


class MarkBiliReadHandler(FeishuActionHandler):
    """标记B站视频为已读处理器"""

    async def handle(self, receive_id: str, receive_id_type: str, **kwargs) -> bool:
        """
        处理标记B站视频为已读请求

        Args:
            receive_id: 接收者ID
            receive_id_type: 接收者ID类型
            **kwargs: 其他参数，包含pageid

        Returns:
            bool: 是否成功
        """
        # 调试信息
        print(f"[DEBUG] MarkBiliReadHandler.handle - 接收到请求，参数: {kwargs}")

        if not self.bot_service or not self.bot_service.notion_service:
            print("[ERROR] MarkBiliReadHandler - Bot服务或Notion服务未初始化")
            return self._create_message(
                receive_id,
                receive_id_type,
                "text",
                json.dumps({"text": "抱歉，标记服务暂时不可用"})
            )

        try:
            # 获取页面ID
            value = kwargs.get("value", {})
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except Exception as e:
                    print(f"[ERROR] MarkBiliReadHandler - 无法解析value字符串: {value}, 错误: {e}")
                    value = {}

            pageid = value.get("pageid", "")

            if not pageid:
                print("[ERROR] MarkBiliReadHandler - 未找到pageid")
                return self._create_message(
                    receive_id,
                    receive_id_type,
                    "text",
                    json.dumps({"text": "缺少页面ID，无法标记为已读"})
                )

            # 标记为已读
            success = await self.bot_service.notion_service.mark_video_as_read(pageid)

            if success:
                return self._create_message(
                    receive_id,
                    receive_id_type,
                    "text",
                    json.dumps({"text": "👍 已将视频标记为已读"})
                )
            else:
                return self._create_message(
                    receive_id,
                    receive_id_type,
                    "text",
                    json.dumps({"text": "标记失败，请稍后再试"})
                )

        except Exception as e:
            error_msg = f"标记B站视频为已读失败: {str(e)}"
            print(f"[ERROR] {error_msg}")
            print(traceback.format_exc())

            return self._create_message(
                receive_id,
                receive_id_type,
                "text",
                json.dumps({"text": f"抱歉，标记为已读时出现错误: {str(e)}"})
            )


class ActionHandlerFactory:
    """操作处理器工厂"""

    @staticmethod
    def create_handler(action: str, client, bot_service=None):
        """
        创建对应的操作处理器

        Args:
            action: 操作类型
            client: 飞书API客户端
            bot_service: 机器人服务实例

        Returns:
            FeishuActionHandler: 操作处理器实例
        """
        handlers = {
            "rich_text_demo": RichTextHandler,
            "generate_image": ImageGenerationHandler,
            "process_image": ImageProcessHandler,
            "share_sample_image": SampleImageHandler,
            "share_sample_audio": SampleAudioHandler,
            "generate_tts": TTSGenerationHandler,
            "get_bili_video": BiliVideoHandler,
            "mark_bili_read": MarkBiliReadHandler,
        }

        handler_class = handlers.get(action)
        if handler_class:
            return handler_class(client, bot_service)
        return None
