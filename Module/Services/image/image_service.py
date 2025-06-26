"""
图像服务 (Image Service)

该模块提供图像处理功能，包括：
1. AI图像生成 (文本转图像)
2. 图像风格转换 (图像转图像)
3. 与gradio服务的集成
4. 错误处理和状态管理
"""

import os
import json
import base64
from typing import Optional, List, Dict, Any, Union
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont

from Module.Common.scripts.common import debug_utils
from ..service_decorators import service_operation_safe, external_api_safe, file_processing_safe


class ImageService:
    """
    图像处理服务

    职责：
    1. AI图像生成 (文本转图像)
    2. 图像风格转换 (图像转图像)
    3. gradio服务调用管理
    4. 图像处理结果管理
    5. 二维码生成
    """

    def __init__(self, app_controller=None):
        """
        初始化图像服务

        Args:
            app_controller: 应用控制器，用于获取配置
        """
        self.app_controller = app_controller
        self.gradio_client = None
        self._load_config()

        # 健康状态检查
        self.is_healthy = self._check_service_health()

        # 初始化二维码生成器
        self.qr_generator = QRCodeGenerator()

    @service_operation_safe("图像服务配置加载失败")
    def _load_config(self):
        """加载配置"""
        # 从应用控制器获取配置
        if self.app_controller:
            config_service = self.app_controller.get_service('config')
            if config_service:
                self.server_id = config_service.get("SERVER_ID", "")
                if self.server_id:
                    self._init_gradio_client()
                return

        # 从环境变量获取配置
        self.server_id = os.getenv("SERVER_ID", "")
        if self.server_id:
            self._init_gradio_client()

    def _init_gradio_client(self):
        """初始化Gradio客户端"""
        # 设置默认值
        self.gradio_client = None
        self.is_healthy = False

        if not self.server_id:
            debug_utils.log_and_print("SERVER_ID未配置，图像服务不可用", log_level="WARNING")
            return

        # 检查模块依赖
        try:
            from gradio_client import Client
        except ImportError:
            debug_utils.log_and_print("gradio_client模块未安装，图像服务不可用", log_level="ERROR")
            return

        try:
            gradio_url = f"https://{self.server_id}"
            self.gradio_client = Client(gradio_url)
            self.is_healthy = True
            debug_utils.log_and_print(f"Gradio客户端连接成功: {gradio_url}", log_level="INFO")
        except Exception as e:
            debug_utils.log_and_print(f"Gradio客户端连接失败: {e}", log_level="WARNING")

    @service_operation_safe("重新初始化Gradio客户端失败")
    def _reinit_gradio_client(self):
        """重新初始化Gradio客户端"""
        # 清理旧连接
        self.gradio_client = None
        self.is_healthy = False

        # 重新初始化
        self._init_gradio_client()

    def _check_service_health(self) -> bool:
        """检查服务健康状态"""
        return self.gradio_client is not None

    @external_api_safe("获取Gradio认证状态失败", return_value={"error": "认证状态获取失败", "available": False}, api_name="Gradio")
    def get_auth_status(self) -> Dict[str, Any]:
        """获取gradio服务的认证状态"""
        if not self.gradio_client:
            return {"error": "Gradio客户端未连接", "available": False}

        # 调用gradio的认证状态API
        auth_status = self.gradio_client.predict(api_name="/get_auth_status")
        return auth_status

    @external_api_safe("更新Gradio认证配置失败", return_value={"success": False, "message": "配置更新失败"}, api_name="Gradio")
    def update_auth_config(self, variable_name: str, new_value: str) -> Dict[str, Any]:
        """更新gradio服务的认证配置"""
        if not self.gradio_client:
            return {"success": False, "message": "Gradio客户端未连接"}

        # 调用gradio的配置更新API
        result = self.gradio_client.predict(
            variable_name,
            new_value,
            os.getenv("ADMIN_SECRET_KEY", ""),
            api_name="/update_auth_config"
        )

        return result

    def get_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        return {
            "service_name": "image",
            "is_healthy": self.is_healthy,
            "gradio_connected": self.gradio_client is not None,
            "server_id_configured": bool(self.server_id) if hasattr(self, 'server_id') else False
        }

    def generate_ai_image(self, prompt: str = None, image_input: Dict = None) -> Optional[List[str]]:
        """
        使用AI生成图片或处理图片

        Args:
            prompt: 文本提示词，用于AI生图
            image_input: 图片输入参数，用于图片处理

        Returns:
            Optional[List[str]]: 生成的图片文件路径列表
            - 返回None表示系统故障，需要管理员修复
            - 返回空列表表示提示词不合适或处理失败
        """
        try:
            # 准备调用参数
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

            # 调用gradio服务
            result = self.gradio_client.predict(**predict_kwargs)

            # 解析结果
            return self._parse_generation_result(result)

        except Exception as e:
            debug_utils.log_and_print(f"AI图像处理失败: {e}", log_level="ERROR")

            # 如果是连接相关错误，标记客户端为无效
            error_str = str(e).lower()
            if any(keyword in error_str for keyword in ['connection', 'timeout', 'ssl', 'handshake', 'network']):
                debug_utils.log_and_print("检测到网络连接错误，标记Gradio客户端为无效", log_level="WARNING")
                self.gradio_client = None
                self.is_healthy = False

            return None

    @service_operation_safe("解析图像生成结果失败", return_value=None)
    def _parse_generation_result(self, result) -> Optional[List[str]]:
        """
        解析图像生成结果

        Args:
            result: gradio API返回结果

        Returns:
            Optional[List[str]]: 处理后的图片路径列表
        """
        # 系统级错误：结果无效或为空元组
        if not isinstance(result, tuple) or len(result) == 0:
            debug_utils.log_and_print("图像生成返回无效结果", log_level="ERROR")
            return None

        # 检查特殊情况：close_auth.png 表示需要管理员修复
        for path in result:
            if path and "close_auth.png" in str(path):
                debug_utils.log_and_print("图像生成需要管理员修复权限", log_level="ERROR")
                return None

        # 检查特殊情况：close_filter.png 表示处理失败
        for path in result:
            if path and "close_filter.png" in str(path):
                debug_utils.log_and_print("图像生成被内容过滤器拦截", log_level="WARNING")
                return []

        # 检查是否所有结果都为None
        if all(x is None for x in result):
            debug_utils.log_and_print("图像生成失败，所有结果为空", log_level="WARNING")
            return []

        # 返回所有非None的图片路径
        valid_paths = []
        for image_path in result:
            if image_path is not None:
                valid_paths.append(image_path)

        return valid_paths

    def process_text_to_image(self, prompt: str) -> Optional[List[str]]:
        """
        文本转图像

        Args:
            prompt: 文本提示词

        Returns:
            Optional[List[str]]: 生成的图片路径列表
        """
        if not prompt or not prompt.strip():
            debug_utils.log_and_print("文本提示词为空", log_level="WARNING")
            return []

        return self.generate_ai_image(prompt=prompt.strip())

    @service_operation_safe("图像转换处理失败", return_value=None)
    def process_image_to_image(self, image_base64: str, mime_type: str = "image/jpeg",
                              file_name: str = "image.jpg", file_size: int = 0) -> Optional[List[str]]:
        """
        图像转图像（风格转换）

        Args:
            image_base64: base64编码的图像数据
            mime_type: 图像MIME类型
            file_name: 文件名
            file_size: 文件大小

        Returns:
            Optional[List[str]]: 处理后的图片路径列表
        """
        # 构建图像输入对象，兼容原有格式
        image_url = f"data:{mime_type};base64,{image_base64}"

        image_input = {
            "path": None,
            "url": image_url,
            "size": file_size,
            "orig_name": file_name,
            "mime_type": mime_type,
            "is_stream": False,
            "meta": {}
        }

        return self.generate_ai_image(image_input=image_input)

    def is_available(self, need_reinit: bool = False) -> bool:
        """检查服务是否可用，如果不可用会尝试重新初始化"""
        # 如果gradio客户端不可用，尝试重新初始化
        if not self.gradio_client and hasattr(self, 'server_id') and self.server_id and need_reinit:
            debug_utils.log_and_print("检测到Gradio服务不可用，尝试重新连接", log_level="INFO")
            self._reinit_gradio_client()

        return self.is_healthy and self.gradio_client is not None

    @service_operation_safe("生成二维码失败")
    def generate_qrcode(self, data_to_encode: str) -> Optional[Image.Image]:
        """
        生成基础二维码图片

        Args:
            data_to_encode: 要编码到二维码中的数据

        Returns:
            Optional[Image.Image]: 生成的二维码图片，失败时返回None
        """
        return self.qr_generator.generate_qrcode(data_to_encode)

    @service_operation_safe("生成设计方案二维码失败")
    def generate_design_plan_qrcode(self, data_to_encode: str, customer_name: str) -> Optional[Image.Image]:
        """
        生成带有客户姓名的设计方案二维码

        Args:
            data_to_encode: 要编码到二维码中的数据 (JSON格式)
            customer_name: 客户姓名，用于显示在二维码下方

        Returns:
            Optional[Image.Image]: 生成的二维码图片，失败时返回None
        """
        return self.qr_generator.generate_design_plan_qrcode(data_to_encode, customer_name)


class QRCodeGenerator:
    """
    一个独立的、功能更强大的二维码生成器，基于用户提供的代码示例
    """
    def __init__(self):
        self.font_path = self._get_font_path()

    def _get_font_path(self):
        """获取系统字体路径，提供降级方案"""
        try:
            # 优先使用Windows下的微软雅黑
            path = os.path.join(os.environ.get('SystemRoot', 'C:/Windows'), 'Fonts', 'msyh.ttc')
            if os.path.exists(path):
                return path
            # 备选字体
            for font_name in ["simhei.ttf", "simsun.ttc"]:
                fallback_path = os.path.join(os.environ.get('SystemRoot', 'C:/Windows'), 'Fonts', font_name)
                if os.path.exists(fallback_path):
                    return fallback_path
        except Exception:
            pass
        return None

    def _get_optimal_font_size(self, text: str, max_width: int, start_size: int = 28, min_size: int = 20) -> int:
        """根据文字长度动态计算最佳字号"""
        current_size = start_size
        while current_size >= min_size:
            try:
                font = ImageFont.truetype(self.font_path, current_size) if self.font_path else ImageFont.load_default()
                # 使用 textlength 计算宽度，兼容性更好
                text_width = ImageDraw.Draw(Image.new('RGB', (1, 1))).textlength(text, font=font)
                if text_width <= max_width:
                    return current_size
            except Exception:
                # 字体加载失败等问题
                pass
            current_size -= 2
        return min_size

    def _add_text_to_image(self, img: Image, text: str, qr_height: int) -> None:
        """在图片上添加文字说明"""
        draw = ImageDraw.Draw(img)

        # 计算最佳字号并添加文字
        optimal_size = self._get_optimal_font_size(text, max_width=img.width - 20)
        font = ImageFont.truetype(self.font_path, optimal_size) if self.font_path else ImageFont.load_default()

        text_width = draw.textlength(text, font=font)
        # 文本位置微调，使其更美观
        text_position = ((img.width - text_width) / 2, qr_height + 15)
        draw.text(text_position, text, font=font, fill="black")

    @service_operation_safe("生成二维码图片失败")
    def generate_qrcode(self, data_to_encode: str) -> Optional[Image.Image]:
        """
        生成二维码图片
        """
        qr = qrcode.QRCode(version=1, box_size=10, border=4, error_correction=qrcode.constants.ERROR_CORRECT_L)
        qr.add_data(data_to_encode)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')

        return qr_img

    @service_operation_safe("生成二维码图片失败")
    def generate_design_plan_qrcode(self, data_to_encode: str, customer_name: str) -> Optional[Image.Image]:
        """
        生成带有文字说明的二维码图片

        Args:
            data_to_encode: 要编码到二维码中的字符串 (JSON格式)
            customer_name: 用于显示在二维码下方的客户姓名

        Returns:
            PIL.Image: 生成的图片对象, 或在失败时返回None
        """
        # 1. 生成基础二维码
        qr = qrcode.QRCode(version=1, box_size=10, border=4, error_correction=qrcode.constants.ERROR_CORRECT_L)
        qr.add_data(data_to_encode)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
        qr_width, qr_height = qr_img.size

        # 2. 创建用于粘贴二维码和文字的最终画布
        text_area_height = 60
        final_img = Image.new('RGB', (qr_width, qr_height + text_area_height), color='white')
        final_img.paste(qr_img, (0, 0))

        # 3. 在图片下方添加说明文字
        text_to_add = f"尊敬的{customer_name}，扫码打开您专属的方案"
        self._add_text_to_image(final_img, text_to_add, qr_height)

        return final_img
