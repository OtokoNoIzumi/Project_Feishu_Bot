"""
HTTP API服务器 (可选)

将AppController的API方法包装为HTTP接口
可以与main_refactored_schedule.py同时运行，提供RESTful API访问
"""

import argparse
import base64
import os
import sys
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from dotenv import load_dotenv
import uvicorn

# 添加项目根目录到Python路径
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

from Module.Application.app_controller import AppController
from Module.Application.app_api_controller import AppApiController

# ================ 安全配置 ================

# 从环境变量获取管理员密钥和允许的IP
ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY", "")  # 管理员密钥
ALLOWED_ADMIN_IPS = ["127.0.0.1", "localhost", "::1"]  # 允许的管理员IP


# ================ 请求模型 ================

class TTSRequest(BaseModel):
    """TTS请求模型"""
    text: str
    admin_secret_key: Optional[str] = None  # 可选的管理员密钥


class ImageGenerationRequest(BaseModel):
    """图像生成请求模型"""
    prompt: str
    admin_secret_key: Optional[str] = None  # 可选的管理员密钥


class ImageProcessingRequest(BaseModel):
    """图像处理请求模型"""
    image_base64: str
    mime_type: str = "image/jpeg"
    file_name: str = "image.jpg"
    file_size: int = 0
    admin_secret_key: Optional[str] = None  # 可选的管理员密钥


class SchedulerTaskRequest(BaseModel):
    """定时任务请求模型"""
    task_name: str
    time_str: str
    task_type: str  # 'daily_schedule' or 'bilibili_updates'
    sources: Optional[List[str]] = None
    admin_secret_key: str  # 必需的管理员密钥


class BilibiliUpdateRequest(BaseModel):
    """B站更新请求模型"""
    sources: Optional[List[str]] = None
    admin_secret_key: str  # 必需的管理员密钥


class BiliVideoMarkReadRequest(BaseModel):
    """B站视频标记已读请求模型"""
    pageid: str
    admin_secret_key: str  # 必需的管理员密钥


# ================ 鉴权辅助函数 ================

def verify_admin_access(request: Request, admin_secret_key: Optional[str] = None) -> bool:
    """
    验证管理员访问权限

    Args:
        request: FastAPI请求对象
        admin_secret_key: 可选的管理员密钥

    Returns:
        bool: 是否有权限访问
    """
    client_ip = request.client.host if request.client else "unknown"

    # 检查IP是否在允许列表中
    is_allowed_ip = client_ip in ALLOWED_ADMIN_IPS

    # 检查密钥是否正确
    is_valid_key = False
    if ADMIN_SECRET_KEY and admin_secret_key:
        is_valid_key = ADMIN_SECRET_KEY == admin_secret_key

    # 满足任一条件即可访问
    has_access = is_allowed_ip or is_valid_key

    # 日志信息优化：显示密钥是否匹配而不是是否提供
    if not has_access:
        print(f"⚠️ 未授权的API访问尝试，IP: {client_ip}, 密钥匹配: {'是' if is_valid_key else '否'}")
    else:
        print(f"✅ 授权的API访问，IP: {client_ip}, 密钥匹配: {'是' if is_valid_key else '否'}")

    return has_access


# ================ HTTP API服务器 ================

class APIRoutesHandler:
    """API路由处理器 - 处理具体的API逻辑"""

    def __init__(self, app_api_controller: AppApiController):
        """
        初始化API路由处理器

        Args:
            app_api_controller: API控制器实例
        """
        self.app_api_controller = app_api_controller

    def handle_health_check(self):
        """处理健康检查"""
        try:
            result = self.app_api_controller.get_system_health()
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    def handle_scheduled_tasks_get(self):
        """处理获取定时任务"""
        try:
            result = self.app_api_controller.get_scheduled_tasks()
            if result['success']:
                return result
            raise HTTPException(status_code=400, detail=result['error'])
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    def handle_bilibili_update(self, sources: Optional[List[str]]):
        """处理B站更新触发"""
        try:
            result = self.app_api_controller.trigger_bilibili_update(sources)
            if result['success']:
                return result
            raise HTTPException(status_code=400, detail=result['error'])
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    def handle_tts_generation(self, text: str):
        """处理TTS生成"""
        try:
            result = self.app_api_controller.generate_tts(text)
            if result['success']:
                # 对音频数据进行base64编码
                result['audio_data'] = base64.b64encode(result['audio_data']).decode('utf-8')
                return result
            raise HTTPException(status_code=400, detail=result['error'])
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    def handle_image_generation(self, prompt: str):
        """处理图像生成"""
        try:
            result = self.app_api_controller.generate_image(prompt)
            if result['success']:
                return result
            raise HTTPException(status_code=400, detail=result['error'])
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    def handle_image_processing(
            self, image_base64: str, mime_type: str,
            file_name: str, file_size: int
    ):
        """处理图像处理"""
        try:
            result = self.app_api_controller.process_image(
                image_base64, mime_type, file_name, file_size
            )
            if result['success']:
                return result
            raise HTTPException(status_code=400, detail=result['error'])
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    def handle_task_creation(
        self, task_name: str, time_str: str,
        task_type: str, sources: Optional[List[str]]
    ):
        """处理任务创建"""
        try:
            result = self.app_api_controller.add_scheduled_task(
                task_name, time_str, task_type, sources=sources
            )
            if result['success']:
                return result
            raise HTTPException(status_code=400, detail=result['error'])
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    def handle_task_removal(self, task_name: str):
        """处理任务移除"""
        try:
            result = self.app_api_controller.remove_scheduled_task(task_name)
            if result['success']:
                return result
            raise HTTPException(status_code=400, detail=result['error'])
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    def handle_bili_video_single(self):
        """处理单个B站视频获取"""
        try:
            result = self.app_api_controller.get_bili_video_single()
            if result['success']:
                return result
            raise HTTPException(status_code=400, detail=result['error'])
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    def handle_bili_videos_multiple(self):
        """处理多个B站视频获取"""
        try:
            result = self.app_api_controller.get_bili_videos_multiple()
            if result['success']:
                return result
            raise HTTPException(status_code=400, detail=result['error'])
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    def handle_bili_videos_statistics(self):
        """处理B站视频统计获取"""
        try:
            result = self.app_api_controller.get_bili_videos_statistics()
            if result['success']:
                return result
            raise HTTPException(status_code=400, detail=result['error'])
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    def handle_bili_video_mark_read(self, pageid: str):
        """处理B站视频标记已读"""
        try:
            result = self.app_api_controller.mark_bili_video_read(pageid)
            if result['success']:
                return result
            raise HTTPException(status_code=400, detail=result['error'])
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e


class HTTPAPIServer:
    """HTTP API服务器"""

    def __init__(self, shared_controller: Optional[AppController] = None):
        """
        初始化HTTP API服务器

        Args:
            shared_controller: 可选的共享AppController实例
        """
        self.app = FastAPI(
            title="飞书机器人API",
            description="飞书机器人后端服务的HTTP API接口",
            version="1.0.0"
        )

        if shared_controller:
            print("🔗 HTTP服务使用共享的AppController实例")
            self.app_controller = shared_controller
            self.app_api_controller = AppApiController(self.app_controller)
            self.is_shared = True
        else:
            print("🆕 HTTP服务创建独立的AppController实例")
            self._init_independent_controller()
            self.is_shared = False

        # 创建路由处理器
        self.routes_handler = APIRoutesHandler(self.app_api_controller)
        self._setup_routes()

    def _init_independent_controller(self):
        """初始化独立的控制器实例"""
        # 加载环境变量
        load_dotenv(os.path.join(current_dir, ".env"))

        # 创建独立的AppController
        self.app_controller = AppController(project_root_path=str(current_dir))
        self.app_api_controller = AppApiController(self.app_controller)

        # 注册服务
        registration_results = self.app_controller.auto_register_services()
        success_count = sum(1 for success in registration_results.values() if success)
        total_count = len(registration_results)
        print(f"📦 HTTP服务独立实例注册: {success_count}/{total_count}")

    def _setup_basic_routes(self):
        """设置基础路由"""
        @self.app.get("/", summary="根路径", description="API服务状态")
        async def root():
            return {
                "service": "飞书机器人API",
                "version": "1.0.0",
                "status": "running",
                "controller_type": "shared" if self.is_shared else "independent"
            }

        @self.app.get("/health", summary="健康检查", description="获取系统健康状态")
        async def health_check():
            return self.routes_handler.handle_health_check()

    def _setup_admin_routes(self):
        """设置需要管理员权限的路由"""
        @self.app.get("/api/scheduler/tasks", summary="获取定时任务",
                      description="获取所有定时任务列表")
        async def get_scheduled_tasks(request: Request, admin_secret_key: Optional[str] = None):
            # 验证管理员权限（敏感信息）
            if not verify_admin_access(request, admin_secret_key):
                raise HTTPException(status_code=403, detail="访问被拒绝：需要管理员权限")
            return self.routes_handler.handle_scheduled_tasks_get()

        @self.app.post("/api/bilibili/update", summary="触发B站更新",
                       description="触发B站内容更新检查")
        async def trigger_bilibili_update(request: Request, data: BilibiliUpdateRequest):
            # 验证管理员权限
            if not verify_admin_access(request, data.admin_secret_key):
                raise HTTPException(status_code=403, detail="访问被拒绝：需要管理员权限")
            return self.routes_handler.handle_bilibili_update(data.sources)

        @self.app.post("/api/audio/tts", summary="生成TTS音频", description="文本转语音")
        async def generate_tts(request: Request, data: TTSRequest):
            # 验证管理员权限（TTS有成本）
            if not verify_admin_access(request, data.admin_secret_key):
                raise HTTPException(status_code=403, detail="访问被拒绝：需要管理员权限")
            return self.routes_handler.handle_tts_generation(data.text)

        @self.app.post("/api/image/generate", summary="生成AI图像", description="AI图像生成")
        async def generate_image(request: Request, data: ImageGenerationRequest):
            # 验证管理员权限（图像生成有成本）
            if not verify_admin_access(request, data.admin_secret_key):
                raise HTTPException(status_code=403, detail="访问被拒绝：需要管理员权限")
            return self.routes_handler.handle_image_generation(data.prompt)

        @self.app.post("/api/image/process", summary="处理图像", description="图像风格转换")
        async def process_image(request: Request, data: ImageProcessingRequest):
            # 验证管理员权限（图像处理有成本）
            if not verify_admin_access(request, data.admin_secret_key):
                raise HTTPException(status_code=403, detail="访问被拒绝：需要管理员权限")
            return self.routes_handler.handle_image_processing(
                data.image_base64, data.mime_type, data.file_name, data.file_size
            )

        @self.app.post("/api/scheduler/tasks", summary="添加定时任务",
                       description="添加新的定时任务")
        async def add_scheduled_task(request: Request, data: SchedulerTaskRequest):
            if not verify_admin_access(request, data.admin_secret_key):
                raise HTTPException(status_code=403, detail="访问被拒绝：需要管理员权限")
            return self.routes_handler.handle_task_creation(
                data.task_name, data.time_str, data.task_type, data.sources
            )

        @self.app.delete("/api/scheduler/tasks/{task_name}", summary="删除定时任务",
                         description="删除指定的定时任务")
        async def remove_scheduled_task(
            request: Request, task_name: str,
            admin_secret_key: Optional[str] = None
        ):
            # 验证管理员权限（系统配置修改）
            if not verify_admin_access(request, admin_secret_key):
                raise HTTPException(status_code=403, detail="访问被拒绝：需要管理员权限")
            return self.routes_handler.handle_task_removal(task_name)

    def _setup_bili_routes(self):
        """设置B站视频相关路由"""
        @self.app.get("/api/bilibili/video/single", summary="获取单个B站视频",
                      description="获取单个B站视频推荐（无需鉴权）")
        async def get_bili_video_single():
            # 无需鉴权：只读操作，无成本
            return self.routes_handler.handle_bili_video_single()

        @self.app.get("/api/bilibili/videos/multiple", summary="获取多个B站视频",
                      description="获取B站视频推荐（1+3模式，无需鉴权）")
        async def get_bili_videos_multiple():
            # 无需鉴权：只读操作，无成本
            return self.routes_handler.handle_bili_videos_multiple()

        @self.app.get("/api/bilibili/videos/statistics", summary="获取B站视频统计",
                      description="获取B站视频统计信息")
        async def get_bili_videos_statistics(
            request: Request, admin_secret_key: Optional[str] = None
        ):
            # 验证管理员权限（统计信息可能敏感）
            if not verify_admin_access(request, admin_secret_key):
                raise HTTPException(status_code=403, detail="访问被拒绝：需要管理员权限")
            return self.routes_handler.handle_bili_videos_statistics()

        @self.app.post("/api/bilibili/video/mark-read", summary="标记B站视频为已读",
                       description="标记指定B站视频为已读状态")
        async def mark_bili_video_read(request: Request, data: BiliVideoMarkReadRequest):
            # 验证管理员权限（数据修改操作）
            if not verify_admin_access(request, data.admin_secret_key):
                raise HTTPException(status_code=403, detail="访问被拒绝：需要管理员权限")
            return self.routes_handler.handle_bili_video_mark_read(data.pageid)

    def _setup_routes(self):
        """设置路由"""
        self._setup_basic_routes()
        self._setup_admin_routes()
        self._setup_bili_routes()


# ================ 启动函数 ================

def start_http_server(
    shared_controller: Optional[AppController] = None,
    host: str = "127.0.0.1",
    port: int = 8000
):
    """
    启动HTTP API服务器

    Args:
        shared_controller: 可选的共享AppController实例
        host: 服务器主机地址
        port: 服务器端口
    """
    server = HTTPAPIServer(shared_controller)

    print("🌐 启动HTTP API服务器")
    print(f"📍 地址: http://{host}:{port}")
    print(f"📚 API文档: http://{host}:{port}/docs")
    print(f"🔗 控制器类型: {'共享实例' if shared_controller else '独立实例'}")

    uvicorn.run(server.app, host=host, port=port)


def main():
    """独立启动HTTP API服务器"""
    parser = argparse.ArgumentParser(description='飞书机器人HTTP API服务器')
    parser.add_argument('--host', default='127.0.0.1', help='服务器主机地址')
    parser.add_argument('--port', type=int, default=8000, help='服务器端口')

    args = parser.parse_args()

    print("🚀 独立模式启动HTTP API服务器")
    start_http_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
