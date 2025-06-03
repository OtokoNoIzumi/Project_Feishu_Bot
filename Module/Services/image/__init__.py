"""
图像服务模块 (Image Service Module)

该模块提供图像处理功能，包括：
1. AI图像生成 (通过Gradio服务)
2. 图像风格转换处理
3. 图像上传和资源管理
4. 与现有gradio服务的集成
"""

from .image_service import ImageService

__all__ = ['ImageService']