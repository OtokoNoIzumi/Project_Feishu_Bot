"""
应用控制器

提供服务注册、统一调用接口和多服务协同功能
设计原则：简单、实用、高性能，支持MVP快速验证
"""

import os
import sys
from typing import Dict, Any, Optional, Tuple, Union
from Module.Common.scripts.common import debug_utils


class AppController:
    """
    应用控制器 - 统一管理和调用各种服务

    功能：
    1. 服务注册和管理
    2. 统一的服务调用接口
    3. 服务状态监控
    4. 简单的错误处理和恢复
    """

    def __init__(self, project_root_path: str = ""):
        """
        初始化应用控制器

        Args:
            project_root_path: 项目根路径，用于服务初始化
        """
        self.project_root_path = project_root_path or self._get_project_root()
        self.services: Dict[str, Any] = {}
        self.service_configs: Dict[str, Dict] = {}
        self.initialized_services: set = set()



    def _get_project_root(self) -> str:
        """获取项目根路径（与配置服务逻辑一致）"""
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # Module/Application -> Module -> 项目根
            root_dir = os.path.normpath(os.path.join(current_dir, "..", ".."))
            return root_dir
        except:
            return os.getcwd()

    def register_service(self, service_name: str, service_class: type, config: Dict[str, Any] = None) -> bool:
        """
        注册服务

        Args:
            service_name: 服务名称
            service_class: 服务类
            config: 服务配置参数

        Returns:
            bool: 注册是否成功
        """
        try:
            if service_name in self.services:
                debug_utils.log_and_print(f"服务 '{service_name}' 已存在，将被覆盖", log_level="WARNING")

            self.service_configs[service_name] = config or {}

            # 暂时只注册类，不立即初始化（懒加载）
            self.services[service_name] = {
                'class': service_class,
                'instance': None,
                'status': 'registered'
            }

            return True

        except Exception as e:
            debug_utils.log_and_print(f"注册服务 '{service_name}' 失败: {e}", log_level="ERROR")
            return False

    def _initialize_service(self, service_name: str) -> bool:
        """
        初始化特定服务（懒加载）

        Args:
            service_name: 服务名称

        Returns:
            bool: 初始化是否成功
        """
        if service_name not in self.services:
            debug_utils.log_and_print(f"服务 '{service_name}' 未注册", log_level="ERROR")
            return False

        if service_name in self.initialized_services:
            return True  # 已初始化

        try:
            service_info = self.services[service_name]
            service_class = service_info['class']
            config = self.service_configs[service_name]

            # 根据服务类型进行特定初始化
            if service_name == 'config':
                instance = service_class(
                    project_root_path=self.project_root_path,
                    **config
                )
            elif service_name == 'cache':
                # 确保缓存目录存在
                cache_dir = config.get('cache_dir', os.path.join(self.project_root_path, "cache"))
                os.makedirs(cache_dir, exist_ok=True)
                instance = service_class(cache_dir)
            elif service_name == 'audio':
                # 音频服务需要传入应用控制器引用
                instance = service_class(app_controller=self)
            elif service_name == 'scheduler':
                # 调度器服务需要传入应用控制器引用
                instance = service_class(app_controller=self)
            elif service_name == 'notion':
                # notion服务需要cache服务作为依赖
                cache_service = self.get_service('cache')
                if not cache_service:
                    raise Exception("notion服务需要cache服务，但cache服务初始化失败")
                instance = service_class(cache_service)
            else:
                # 通用初始化
                instance = service_class(**config)

            service_info['instance'] = instance
            service_info['status'] = 'initialized'
            self.initialized_services.add(service_name)

            return True

        except Exception as e:
            debug_utils.log_and_print(f"初始化服务 '{service_name}' 失败: {e}", log_level="ERROR")
            self.services[service_name]['status'] = 'failed'
            return False

    def get_service(self, service_name: str) -> Optional[Any]:
        """
        获取服务实例

        Args:
            service_name: 服务名称

        Returns:
            Optional[Any]: 服务实例，如果失败返回None
        """
        if service_name not in self.services:
            debug_utils.log_and_print(f"服务 '{service_name}' 未注册", log_level="ERROR")
            return None

        # 懒加载：如果还未初始化，先初始化
        if service_name not in self.initialized_services:
            if not self._initialize_service(service_name):
                return None

        return self.services[service_name]['instance']

    def call_service(self, service_name: str, method_name: str, *args, **kwargs) -> Tuple[bool, Any]:
        """
        统一的服务调用接口

        Args:
            service_name: 服务名称
            method_name: 方法名称
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            Tuple[bool, Any]: (是否成功, 返回值或错误信息)
        """
        try:
            service = self.get_service(service_name)
            if service is None:
                return False, f"服务 '{service_name}' 不可用"

            if not hasattr(service, method_name):
                return False, f"服务 '{service_name}' 没有方法 '{method_name}'"

            method = getattr(service, method_name)
            result = method(*args, **kwargs)

            return True, result

        except Exception as e:
            error_msg = f"调用 {service_name}.{method_name} 失败: {e}"
            debug_utils.log_and_print(error_msg, log_level="ERROR")
            return False, error_msg

    def get_service_status(self, service_name: str = None) -> Dict[str, Any]:
        """
        获取服务状态

        Args:
            service_name: 服务名称，如果为None则返回所有服务状态

        Returns:
            Dict[str, Any]: 服务状态信息
        """
        if service_name:
            if service_name not in self.services:
                return {"error": f"服务 '{service_name}' 未注册"}

            service_info = self.services[service_name]
            status = {
                "name": service_name,
                "status": service_info['status'],
                "initialized": service_name in self.initialized_services,
                "available": service_info['instance'] is not None
            }

            # 如果服务已初始化，尝试获取详细状态
            if service_name in self.initialized_services and service_info['instance']:
                try:
                    if hasattr(service_info['instance'], 'get_status'):
                        status["details"] = service_info['instance'].get_status()
                except:
                    pass

            return status
        else:
            # 返回所有服务状态
            all_status = {
                "controller": {
                    "project_root": self.project_root_path,
                    "total_services": len(self.services),
                    "initialized_services": len(self.initialized_services)
                },
                "services": {}
            }

            for name in self.services:
                all_status["services"][name] = self.get_service_status(name)

            return all_status

    def initialize_all_services(self) -> Dict[str, bool]:
        """
        初始化所有注册的服务

        Returns:
            Dict[str, bool]: 各服务初始化结果
        """
        results = {}

        for service_name in self.services:
            results[service_name] = self._initialize_service(service_name)

        debug_utils.log_and_print(
            f"批量初始化完成，成功: {sum(results.values())}/{len(results)}",
            log_level="INFO"
        )

        return results

    def auto_register_services(self) -> Dict[str, bool]:
        """
        自动注册可用的服务

        Returns:
            Dict[str, bool]: 各服务注册结果
        """
        results = {}

        try:
            # 导入服务注册表
            from Module.Services import AVAILABLE_SERVICES

            for service_name, service_class in AVAILABLE_SERVICES.items():
                # 根据服务类型设置默认配置
                if service_name == 'config':
                    config = {
                        'static_config_file_path': 'config.json',
                        'auth_config_file_path': os.getenv('AUTH_CONFIG_FILE_PATH', '')
                    }
                elif service_name == 'cache':
                    config = {
                        'cache_dir': os.path.join(self.project_root_path, 'cache')
                    }
                else:
                    config = {}

                results[service_name] = self.register_service(service_name, service_class, config)

            debug_utils.log_and_print(
                f"自动注册完成，成功: {sum(results.values())}/{len(results)}",
                log_level="INFO"
            )

        except ImportError as e:
            debug_utils.log_and_print(f"自动注册失败，无法导入服务: {e}", log_level="ERROR")

        return results

    def health_check(self) -> Dict[str, Any]:
        """
        健康检查

        Returns:
            Dict[str, Any]: 健康状态信息
        """
        health_status = {
            "timestamp": "TODO: 添加时间戳",
            "overall_status": "healthy",
            "controller_status": "running",
            "services": {},
            "summary": {
                "total": len(self.services),
                "healthy": 0,
                "unhealthy": 0,
                "uninitialized": 0
            }
        }

        for service_name in self.services:
            try:
                service_status = self.get_service_status(service_name)

                if service_status.get("available", False):
                    status = "healthy"
                    health_status["summary"]["healthy"] += 1
                elif service_status.get("initialized", False):
                    status = "unhealthy"
                    health_status["summary"]["unhealthy"] += 1
                else:
                    status = "uninitialized"
                    health_status["summary"]["uninitialized"] += 1

                health_status["services"][service_name] = {
                    "status": status,
                    "details": service_status
                }

            except Exception as e:
                health_status["services"][service_name] = {
                    "status": "error",
                    "error": str(e)
                }
                health_status["summary"]["unhealthy"] += 1

        # 更新总体状态
        if health_status["summary"]["unhealthy"] > 0:
            health_status["overall_status"] = "degraded"
        elif health_status["summary"]["healthy"] == 0:
            health_status["overall_status"] = "initializing"

        return health_status

    # ================ 独立API接口方法 ================

    def api_get_schedule_data(self) -> Dict[str, Any]:
        """
        API: 获取日程数据
        独立接口，可被任何前端调用

        Returns:
            Dict[str, Any]: 日程数据或错误信息
        """
        try:
            scheduler_service = self.get_service('scheduler')
            if not scheduler_service:
                return {"success": False, "error": "调度器服务不可用"}

            return {
                "success": True,
                "data": scheduler_service.get_schedule_data()
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def api_trigger_bilibili_update(self, sources=None) -> Dict[str, Any]:
        """
        API: 触发B站更新检查
        独立接口，可被任何前端调用

        Args:
            sources: 可选的数据源列表

        Returns:
            Dict[str, Any]: 处理结果
        """
        try:
            scheduler_service = self.get_service('scheduler')
            if not scheduler_service:
                return {"success": False, "error": "调度器服务不可用"}

            return scheduler_service.trigger_bilibili_update_check(sources)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def api_generate_tts(self, text: str) -> Dict[str, Any]:
        """
        API: 生成TTS音频
        独立接口，可被任何前端调用

        Args:
            text: 要转换的文本

        Returns:
            Dict[str, Any]: 音频数据或错误信息
        """
        try:
            audio_service = self.get_service('audio')
            if not audio_service:
                return {"success": False, "error": "音频服务不可用"}

            success, audio_data, error_msg = audio_service.process_tts_request(text)

            if success:
                return {
                    "success": True,
                    "audio_data": audio_data,
                    "text": text
                }
            else:
                return {"success": False, "error": error_msg}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def api_generate_image(self, prompt: str) -> Dict[str, Any]:
        """
        API: 生成AI图像
        独立接口，可被任何前端调用

        Args:
            prompt: 图像生成提示词

        Returns:
            Dict[str, Any]: 图像路径列表或错误信息
        """
        try:
            image_service = self.get_service('image')
            if not image_service or not image_service.is_available():
                return {"success": False, "error": "图像服务不可用"}

            image_paths = image_service.process_text_to_image(prompt)

            if image_paths is None:
                return {"success": False, "error": "图像生成故障"}
            elif len(image_paths) == 0:
                return {"success": False, "error": "图像生成失败"}
            else:
                return {
                    "success": True,
                    "image_paths": image_paths,
                    "prompt": prompt
                }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def api_process_image(self, image_base64: str, mime_type: str = "image/jpeg",
                         file_name: str = "image.jpg", file_size: int = 0) -> Dict[str, Any]:
        """
        API: 处理图像转换
        独立接口，可被任何前端调用

        Args:
            image_base64: base64编码的图像数据
            mime_type: 图像MIME类型
            file_name: 文件名
            file_size: 文件大小

        Returns:
            Dict[str, Any]: 处理后的图像路径列表或错误信息
        """
        try:
            image_service = self.get_service('image')
            if not image_service or not image_service.is_available():
                return {"success": False, "error": "图像服务不可用"}

            image_paths = image_service.process_image_to_image(
                image_base64, mime_type, file_name, file_size
            )

            if image_paths is None:
                return {"success": False, "error": "图像处理故障"}
            elif len(image_paths) == 0:
                return {"success": False, "error": "图像处理失败"}
            else:
                return {
                    "success": True,
                    "image_paths": image_paths,
                    "original_file": file_name
                }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def api_get_scheduled_tasks(self) -> Dict[str, Any]:
        """
        API: 获取定时任务列表
        独立接口，可被任何前端调用

        Returns:
            Dict[str, Any]: 任务列表或错误信息
        """
        try:
            scheduler_service = self.get_service('scheduler')
            if not scheduler_service:
                return {"success": False, "error": "调度器服务不可用"}

            return {
                "success": True,
                "tasks": scheduler_service.list_tasks(),
                "status": scheduler_service.get_status()
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def api_add_scheduled_task(self, task_name: str, time_str: str, task_type: str, **kwargs) -> Dict[str, Any]:
        """
        API: 添加定时任务
        独立接口，可被任何前端调用

        Args:
            task_name: 任务名称
            time_str: 时间字符串
            task_type: 任务类型 ('daily_schedule', 'bilibili_updates')
            **kwargs: 其他参数

        Returns:
            Dict[str, Any]: 添加结果
        """
        try:
            scheduler_service = self.get_service('scheduler')
            if not scheduler_service:
                return {"success": False, "error": "调度器服务不可用"}

            # 根据任务类型选择对应的处理函数
            if task_type == "daily_schedule":
                task_func = scheduler_service.trigger_daily_schedule_reminder
                success = scheduler_service.add_daily_task(task_name, time_str, task_func)
            elif task_type == "bilibili_updates":
                task_func = scheduler_service.trigger_bilibili_updates_reminder
                sources = kwargs.get('sources')
                success = scheduler_service.add_daily_task(
                    task_name, time_str, task_func, sources=sources
                )
            else:
                return {"success": False, "error": f"不支持的任务类型: {task_type}"}

            return {
                "success": success,
                "message": f"任务 '{task_name}' {'添加成功' if success else '添加失败'}"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def api_remove_scheduled_task(self, task_name: str) -> Dict[str, Any]:
        """
        移除定时任务的API接口

        Args:
            task_name: 任务名称

        Returns:
            Dict[str, Any]: API响应
        """
        try:
            success, result = self.call_service('scheduler', 'remove_task', task_name)

            if success and result:
                return {
                    "success": True,
                    "message": f"任务 '{task_name}' 已移除",
                    "data": {"task_name": task_name}
                }
            else:
                return {
                    "success": False,
                    "error": f"移除任务失败: {result}",
                    "data": None
                }
        except Exception as e:
            debug_utils.log_and_print(f"API移除定时任务失败: {e}", log_level="ERROR")
            return {
                "success": False,
                "error": f"移除任务出错: {str(e)}",
                "data": None
            }

    # ================ B站视频API方法 ================

    def api_get_bili_video_single(self) -> Dict[str, Any]:
        """
        获取单个B站视频推荐的API接口

        Returns:
            Dict[str, Any]: API响应
        """
        try:
            success, result = self.call_service('notion', 'get_bili_video')

            if success and result and result.get("success", False):
                return {
                    "success": True,
                    "message": "成功获取B站视频推荐",
                    "data": result
                }
            else:
                return {
                    "success": False,
                    "error": "获取B站视频推荐失败",
                    "data": None
                }
        except Exception as e:
            debug_utils.log_and_print(f"API获取B站视频失败: {e}", log_level="ERROR")
            return {
                "success": False,
                "error": f"获取B站视频出错: {str(e)}",
                "data": None
            }

    def api_get_bili_videos_multiple(self) -> Dict[str, Any]:
        """
        获取多个B站视频推荐（1+3模式）的API接口

        Returns:
            Dict[str, Any]: API响应
        """
        try:
            success, result = self.call_service('notion', 'get_bili_videos_multiple')

            if success and result and result.get("success", False):
                return {
                    "success": True,
                    "message": f"成功获取B站视频推荐：1个主推荐+{len(result.get('additional_videos', []))}个额外推荐",
                    "data": result
                }
            else:
                return {
                    "success": False,
                    "error": "获取B站视频推荐失败",
                    "data": None
                }
        except Exception as e:
            debug_utils.log_and_print(f"API获取B站视频列表失败: {e}", log_level="ERROR")
            return {
                "success": False,
                "error": f"获取B站视频列表出错: {str(e)}",
                "data": None
            }

    def api_get_bili_videos_statistics(self) -> Dict[str, Any]:
        """
        获取B站视频统计信息的API接口

        Returns:
            Dict[str, Any]: API响应
        """
        try:
            success, result = self.call_service('notion', 'get_bili_videos_statistics')

            if success and result and result.get("success", False):
                total_count = result.get("总未读数", 0)
                return {
                    "success": True,
                    "message": f"成功获取B站视频统计：共{total_count}个未读视频",
                    "data": result
                }
            else:
                return {
                    "success": False,
                    "error": "获取B站视频统计失败",
                    "data": None
                }
        except Exception as e:
            debug_utils.log_and_print(f"API获取B站视频统计失败: {e}", log_level="ERROR")
            return {
                "success": False,
                "error": f"获取B站视频统计出错: {str(e)}",
                "data": None
            }

    def api_mark_bili_video_read(self, pageid: str) -> Dict[str, Any]:
        """
        标记B站视频为已读的API接口

        Args:
            pageid: 视频页面ID

        Returns:
            Dict[str, Any]: API响应
        """
        try:
            success, result = self.call_service('notion', 'mark_video_read', pageid)

            if success and result:
                return {
                    "success": True,
                    "message": f"视频已标记为已读",
                    "data": {"pageid": pageid, "read_status": True}
                }
            else:
                return {
                    "success": False,
                    "error": f"标记视频已读失败: {result}",
                    "data": None
                }
        except Exception as e:
            debug_utils.log_and_print(f"API标记视频已读失败: {e}", log_level="ERROR")
            return {
                "success": False,
                "error": f"标记视频已读出错: {str(e)}",
                "data": None
            }