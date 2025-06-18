"""
媒体处理器

处理TTS配音、图像生成、图像转换、富文本等媒体相关功能
"""

import os
from .base_processor import BaseProcessor, MessageContext, ProcessResult, require_service, safe_execute


class MediaProcessor(BaseProcessor):
    """
    媒体处理器

    处理各种媒体相关的功能
    """

    @require_service('audio', "音频服务未启动")
    @safe_execute("配音指令处理失败")
    def handle_tts_command(self, context: MessageContext, user_msg: str) -> ProcessResult:
        """处理TTS配音指令"""
        # 提取配音文本
        tts_text = user_msg.split("配音", 1)[1].strip()
        if not tts_text:
            return ProcessResult.error_result("配音文本不能为空，请使用格式：配音 文本内容")

        # 先发送处理中提示
        return ProcessResult.success_result("text", {
            "text": "正在生成配音，请稍候...",
            "next_action": "process_tts",
            "tts_text": tts_text
        })

    @require_service('audio', "音频服务未启动")
    @safe_execute("TTS异步处理失败")
    def process_tts_async(self, tts_text: str) -> ProcessResult:
        """
        异步处理TTS生成（由FeishuAdapter调用）

        Args:
            tts_text: 要转换的文本

        Returns:
            ProcessResult: 处理结果
        """
        # 获取音频服务
        audio_service = self.app_controller.get_service('audio')

        # 生成TTS音频
        success, audio_data, error_msg = audio_service.process_tts_request(tts_text)

        if not success:
            return ProcessResult.error_result(f"TTS生成失败: {error_msg}")

        # 返回音频数据，由适配器处理上传
        return ProcessResult.success_result("audio", {
            "audio_data": audio_data,
            "text": tts_text[:50] + ("..." if len(tts_text) > 50 else "")
        })

    @require_service('image', "图像生成服务未启动或不可用", check_available=True)
    @safe_execute("图像生成指令处理失败")
    def handle_image_generation_command(self, context: MessageContext, user_msg: str) -> ProcessResult:
        """处理图像生成指令"""
        # 提取生图文本
        if "生图" in user_msg:
            prompt = user_msg.split("生图", 1)[1].strip()
        elif "AI画图" in user_msg:
            prompt = user_msg.split("AI画图", 1)[1].strip()
        else:
            prompt = ""

        if not prompt:
            return ProcessResult.error_result("图像生成文本不能为空，请使用格式：生图 描述内容 或 AI画图 描述内容")

        # 先发送处理中提示
        return ProcessResult.success_result("text", {
            "text": "正在生成图片，请稍候...",
            "next_action": "process_image_generation",
            "generation_prompt": prompt
        })

    @require_service('image', "图像生成服务未启动或不可用", check_available=True)
    @safe_execute("图像生成异步处理失败")
    def process_image_generation_async(self, prompt: str) -> ProcessResult:
        """
        异步处理图像生成（由FeishuAdapter调用）

        Args:
            prompt: 图像生成提示词

        Returns:
            ProcessResult: 处理结果
        """
        # 获取图像服务
        image_service = self.app_controller.get_service('image')

        # 生成图像
        image_paths = image_service.process_text_to_image(prompt)

        if image_paths is None:
            return ProcessResult.error_result("图片生成故障，已经通知管理员修复咯！")
        elif len(image_paths) == 0:
            return ProcessResult.error_result("图片生成失败了，建议您换个提示词再试试")

        # 返回图像路径列表，由适配器处理上传
        return ProcessResult.success_result("image_list", {
            "image_paths": image_paths,
            "prompt": prompt[:50] + ("..." if len(prompt) > 50 else "")
        })

    @require_service('image', "图像处理服务未启动或不可用")
    @safe_execute("图像消息处理失败")
    def handle_image_message(self, context: MessageContext) -> ProcessResult:
        """处理图片消息 - 图像风格转换"""
        # 检查图像服务是否可用（包含特殊的首次初始化逻辑）
        first_init = 'image' in self.app_controller.initialized_services # 根据启动特征，避免首次启动时双倍初始化
        image_service = self.app_controller.get_service('image')
        if not image_service.is_available(need_reinit=first_init):
            return ProcessResult.error_result("图像处理服务未启动或不可用")

        # 先发送处理中提示
        return ProcessResult.success_result("text", {
            "text": "正在转换图片风格，请稍候...",
            "next_action": "process_image_conversion",
            "image_data": context.content  # 图像数据将由适配器传递
        })

    @require_service('image', "图像转换服务未启动或不可用", check_available=True)
    @safe_execute("图像转换异步处理失败")
    def process_image_conversion_async(self, image_base64: str, mime_type: str,
                                     file_name: str, file_size: int) -> ProcessResult:
        """
        异步处理图像风格转换（由FeishuAdapter调用）

        Args:
            image_base64: base64编码的图像数据
            mime_type: 图像MIME类型
            file_name: 文件名
            file_size: 文件大小

        Returns:
            ProcessResult: 处理结果
        """
        # 获取图像服务
        image_service = self.app_controller.get_service('image')

        # 处理图像转换
        image_paths = image_service.process_image_to_image(
            image_base64, mime_type, file_name, file_size
        )

        if image_paths is None:
            return ProcessResult.error_result("图片处理故障，已经通知管理员修复咯！")
        elif len(image_paths) == 0:
            return ProcessResult.error_result("图片处理失败了，请尝试使用其他图片")

        # 返回处理后的图像路径列表
        return ProcessResult.success_result("image_list", {
            "image_paths": image_paths,
            "original_file": file_name
        })

    def handle_rich_text_command(self, context: MessageContext) -> ProcessResult:
        """处理富文本指令"""
        try:
            # 获取示例图片路径
            sample_pic_path = os.getenv("SAMPLE_PIC_PATH", "")

            if not sample_pic_path or not os.path.exists(sample_pic_path):
                return ProcessResult.error_result("示例图片不存在，无法创建富文本消息")

            # 读取图片文件
            with open(sample_pic_path, "rb") as f:
                image_data = f.read()

            # 生成富文本内容
            rich_text_content = {
                "zh_cn": {
                    "title": "富文本示例",
                    "content": [
                        [
                            {"tag": "text", "text": "第一行:", "style": ["bold", "underline"]},
                            {"tag": "a", "href": "https://open.feishu.cn", "text": "飞书开放平台", "style": ["italic"]},
                            {"tag": "at", "user_id": "all", "style": ["lineThrough"]}
                        ],
                        [{"tag": "text", "text": "代码示例:"}],
                        [{"tag": "code_block", "language": "PYTHON", "text": "print('Hello World')"}],
                        [{"tag": "hr"}],
                        [{"tag": "md", "text": "**Markdown内容**\n- 列表项1\n- 列表项2\n```python\nprint('代码块')\n```"}]
                    ]
                }
            }

            return ProcessResult.success_result("rich_text", {
                "rich_text_content": rich_text_content,
                "sample_image_data": image_data,
                "sample_image_name": os.path.basename(sample_pic_path)
            }, parent_id=context.message_id)

        except Exception as e:
            return ProcessResult.error_result(f"富文本指令处理失败: {str(e)}")

    def handle_sample_image_command(self, context: MessageContext) -> ProcessResult:
        """处理图片/壁纸指令"""
        try:
            # 获取示例图片路径
            sample_pic_path = os.getenv("SAMPLE_PIC_PATH", "")

            if not sample_pic_path or not os.path.exists(sample_pic_path):
                return ProcessResult.error_result("示例图片不存在")

            # 读取图片文件
            with open(sample_pic_path, "rb") as f:
                image_data = f.read()

            return ProcessResult.success_result("image", {
                "image_data": image_data,
                "image_name": os.path.basename(sample_pic_path)
            }, parent_id=context.message_id)

        except Exception as e:
            return ProcessResult.error_result(f"图片指令处理失败: {str(e)}")

    def handle_audio_message(self, context: MessageContext) -> ProcessResult:
        """处理音频消息"""
        return ProcessResult.success_result("text", {
            "text": "收到音频消息，音频处理功能将在后续版本实现"
        })