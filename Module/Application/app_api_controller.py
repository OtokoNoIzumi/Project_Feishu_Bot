"""
应用API控制器

专门处理HTTP API接口调用，与AppController解耦
"""

from typing import Dict, Any, Optional, List
from Module.Common.scripts.common import debug_utils
from Module.Services.constants import ServiceNames, SchedulerTaskTypes


class AppApiController:
    """
    应用API控制器 - 专门处理API接口

    职责：
    1. 提供RESTful API接口
    2. 统一API响应格式
    3. API参数验证和错误处理
    """

    def __init__(self, app_controller=None):
        """
        初始化API控制器

        Args:
            app_controller: 核心应用控制器实例
        """
        self.app_controller = app_controller

    def _create_api_response(self, success: bool, data: Any = None, error: str = None, message: str = None) -> Dict[str, Any]:
        """
        创建标准API响应格式

        Args:
            success: 操作是否成功
            data: 响应数据
            error: 错误信息
            message: 成功消息

        Returns:
            Dict[str, Any]: 标准API响应
        """
        response = {"success": success}

        if success:
            if data is not None:
                response["data"] = data
            if message:
                response["message"] = message
        else:
            response["error"] = error or "操作失败"

        return response

    def _validate_required_service(self, service_name: str) -> Optional[Any]:
        """
        验证并获取必需的服务

        Args:
            service_name: 服务名称

        Returns:
            Optional[Any]: 服务实例，如果不可用则返回None
        """
        if not self.app_controller:
            return None

        service = self.app_controller.get_service(service_name)
        if not service:
            debug_utils.log_and_print(f"服务 {service_name} 不可用", log_level="WARNING")

        return service

    # ================ 系统API ================

    def get_system_health(self) -> Dict[str, Any]:
        """获取系统健康状态"""
        try:
            if not self.app_controller:
                return self._create_api_response(False, error="应用控制器不可用")

            health_status = self.app_controller.health_check()
            return self._create_api_response(True, data=health_status, message="系统状态检查完成")

        except Exception as e:
            return self._create_api_response(False, error=f"健康检查失败: {str(e)}")

    # ================ 媒体API ================

    def generate_tts(self, text: str) -> Dict[str, Any]:
        """生成TTS音频"""
        try:
            if not text or not text.strip():
                return self._create_api_response(False, error="文本内容不能为空")

            audio_service = self._validate_required_service(ServiceNames.AUDIO)
            if not audio_service:
                return self._create_api_response(False, error="音频服务不可用")

            success, audio_data, error_msg = audio_service.process_tts_request(text)

            if success:
                return {
                    "success": True,
                    "audio_data": audio_data,
                    "text": text
                }

            return self._create_api_response(False, error=error_msg or "TTS音频生成失败")

        except Exception as e:
            return self._create_api_response(False, error=f"异常: {str(e)}")

    def generate_image(self, prompt: str) -> Dict[str, Any]:
        """生成AI图像"""
        try:
            if not prompt or not prompt.strip():
                return self._create_api_response(False, error="图像提示词不能为空")

            image_service = self._validate_required_service(ServiceNames.IMAGE)
            if not image_service or not image_service.is_available():
                return self._create_api_response(False, error="图像服务不可用")

            image_paths = image_service.process_text_to_image(prompt)

            if image_paths is None:
                return self._create_api_response(False, error="图像生成故障")

            if len(image_paths) == 0:
                return self._create_api_response(False, error="图像生成失败")

            return {
                "success": True,
                "image_paths": image_paths,
                "prompt": prompt
            }

        except Exception as e:
            return self._create_api_response(False, error=f"异常: {str(e)}")

    def process_image(self, image_base64: str, mime_type: str = "image/jpeg",
                     file_name: str = "image.jpg", file_size: int = 0) -> Dict[str, Any]:
        """处理图像转换"""
        try:
            if not image_base64:
                return self._create_api_response(False, error="图像数据不能为空")

            image_service = self._validate_required_service(ServiceNames.IMAGE)
            if not image_service or not image_service.is_available():
                return self._create_api_response(False, error="图像服务不可用")

            image_paths = image_service.process_image_to_image(
                image_base64, mime_type, file_name, file_size
            )

            if image_paths is None:
                return self._create_api_response(False, error="图像处理故障")
            if len(image_paths) == 0:
                return self._create_api_response(False, error="图像处理失败")

            return {
                "success": True,
                "image_paths": image_paths,
                "original_file": file_name
            }

        except Exception as e:
            return self._create_api_response(False, error=f"异常: {str(e)}")

    # ================ 定时任务API ================

    def trigger_bilibili_update(self, sources: Optional[List[str]] = None) -> Dict[str, Any]:
        """触发B站更新检查"""
        try:
            scheduler_service = self._validate_required_service(ServiceNames.SCHEDULER)
            if not scheduler_service:
                return self._create_api_response(False, error="调度器服务不可用")

            result = scheduler_service.trigger_bilibili_update_check(sources)
            return result

        except Exception as e:
            return self._create_api_response(False, error=f"异常: {str(e)}")

    def get_scheduled_tasks(self) -> Dict[str, Any]:
        """获取定时任务列表"""
        try:
            scheduler_service = self._validate_required_service(ServiceNames.SCHEDULER)
            if not scheduler_service:
                return self._create_api_response(False, error="调度器服务不可用")

            status = scheduler_service.get_status()

            return {
                "success": True,
                "status": status
            }

        except Exception as e:
            return self._create_api_response(False, error=f"异常: {str(e)}")

    def add_scheduled_task(self, task_name: str, time_str: str, task_type: str, **kwargs) -> Dict[str, Any]:
        """添加定时任务"""
        try:
            if not all([task_name, time_str, task_type]):
                return self._create_api_response(False, error="任务名称、时间和类型不能为空")

            scheduler_service = self._validate_required_service(ServiceNames.SCHEDULER)
            if not scheduler_service:
                return self._create_api_response(False, error="调度器服务不可用")

            # 根据任务类型选择对应的处理函数
            task_func = None
            match task_type:
                case SchedulerTaskTypes.DAILY_SCHEDULE:
                    task_func = scheduler_service.trigger_daily_schedule_reminder
                    success = scheduler_service.add_daily_task(task_name, time_str, task_func)
                case SchedulerTaskTypes.BILI_UPDATES:
                    task_func = scheduler_service.trigger_bilibili_updates_reminder
                    sources = kwargs.get('sources')
                    success = scheduler_service.add_daily_task(
                        task_name, time_str, task_func, sources=sources
                    )
                case _:
                    return self._create_api_response(False, error=f"不支持的任务类型: {task_type}")

            return {
                "success": success,
                "message": f"任务 '{task_name}' {'添加成功' if success else '添加失败'}"
            }

        except Exception as e:
            return self._create_api_response(False, error=f"异常: {str(e)}")

    def remove_scheduled_task(self, task_name: str) -> Dict[str, Any]:
        """移除定时任务"""
        try:
            if not task_name:
                return self._create_api_response(False, error="任务名称不能为空")

            scheduler_service = self._validate_required_service(ServiceNames.SCHEDULER)
            if not scheduler_service:
                return self._create_api_response(False, error="调度器服务不可用")

            success = scheduler_service.remove_task(task_name)

            if success:
                return self._create_api_response(
                    True,
                    data={"task_name": task_name},
                    message=f"任务 '{task_name}' 已移除"
                )

            return self._create_api_response(False, error=f"移除任务 '{task_name}' 失败")

        except Exception as e:
            return self._create_api_response(False, error=f"异常: {str(e)}")

    # ================ B站视频API ================

    def get_bili_video_single(self) -> Dict[str, Any]:
        """获取单个B站视频推荐"""
        try:
            notion_service = self._validate_required_service(ServiceNames.NOTION)
            if not notion_service:
                return self._create_api_response(False, error="Notion服务不可用")

            result = notion_service.get_bili_video()

            if result and result.get("success", False):
                return self._create_api_response(
                    True,
                    data=result,
                    message="成功获取B站视频推荐"
                )

            return self._create_api_response(False, error="获取B站视频推荐失败")

        except Exception as e:
            return self._create_api_response(False, error=f"异常: {str(e)}")

    def get_bili_videos_multiple(self) -> Dict[str, Any]:
        """获取多个B站视频推荐（1+3模式）"""
        try:
            notion_service = self._validate_required_service(ServiceNames.NOTION)
            if not notion_service:
                return self._create_api_response(False, error="Notion服务不可用")

            result = notion_service.get_bili_videos_multiple()

            if result and result.get("success", False):
                additional_count = len(result.get('additional_videos', []))
                return self._create_api_response(
                    True,
                    data=result,
                    message=f"成功获取B站视频推荐：1个主推荐+{additional_count}个额外推荐"
                )

            return self._create_api_response(False, error="获取B站视频推荐失败")

        except Exception as e:
            return self._create_api_response(False, error=f"异常: {str(e)}")

    def get_bili_videos_statistics(self) -> Dict[str, Any]:
        """获取B站视频统计信息"""
        try:
            notion_service = self._validate_required_service(ServiceNames.NOTION)
            if not notion_service:
                return self._create_api_response(False, error="Notion服务不可用")

            result = notion_service.get_bili_videos_statistics()

            if result and result.get("success", False):
                total_count = result.get("总未读数", 0)
                return self._create_api_response(
                    True,
                    data=result,
                    message=f"成功获取B站视频统计：共{total_count}个未读视频"
                )

            return self._create_api_response(False, error="获取B站视频统计失败")

        except Exception as e:
            return self._create_api_response(False, error=f"异常: {str(e)}")

    def mark_bili_video_read(self, pageid: str) -> Dict[str, Any]:
        """标记B站视频为已读"""
        try:
            if not pageid:
                return self._create_api_response(False, error="视频页面ID不能为空")

            notion_service = self._validate_required_service(ServiceNames.NOTION)
            if not notion_service:
                return self._create_api_response(False, error="Notion服务不可用")

            success = notion_service.mark_video_read(pageid)

            if success:
                return self._create_api_response(
                    True,
                    data={"pageid": pageid, "read_status": True},
                    message="视频已标记为已读"
                )

            return self._create_api_response(False, error="标记视频已读失败")

        except Exception as e:
            return self._create_api_response(False, error=f"异常: {str(e)}")
