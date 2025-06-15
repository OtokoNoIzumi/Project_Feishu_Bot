"""
路由服务 - 智能消息路由

提供2字符快捷指令精确匹配和AI意图识别备选方案
"""

from typing import Dict, Any, Optional, Tuple
from Module.Common.scripts.common import debug_utils


class RouterService:
    """
    智能路由服务

    职责：
    1. 2字符快捷指令精确匹配（100%准确率）
    2. AI意图识别备选方案（置信度>60%）
    3. 路由结果统一封装
    """

    def __init__(self, app_controller=None):
        """
        初始化路由服务

        Args:
            app_controller: 应用控制器，用于访问其他服务
        """
        self.app_controller = app_controller
        self.llm_service = None

        # 初始化依赖服务
        self._init_services()

        # 加载快捷指令配置
        self.shortcut_commands = self._load_shortcut_commands()

    def _init_services(self):
        """初始化依赖的服务"""
        if self.app_controller:
            self.llm_service = self.app_controller.get_service('llm')
            debug_utils.log_and_print(f"RouterService 获取 LLM 服务: {'成功' if self.llm_service else '失败'}", log_level="INFO")
        else:
            debug_utils.log_and_print("RouterService 未能获取 app_controller", log_level="WARNING")

    def _load_shortcut_commands(self) -> Dict[str, Dict[str, Any]]:
        """
        加载快捷指令配置

        Returns:
            Dict[str, Dict[str, Any]]: 快捷指令配置
        """
        return {
            "jl": {
                "intent": "记录思考",
                "description": "记录想法、思考、感悟",
                "handler": "note_service",
                "method": "record_thought",
                "confidence": 100
            },
            "rc": {
                "intent": "记录日程",
                "description": "记录日程安排、任务",
                "handler": "note_service",
                "method": "record_schedule",
                "confidence": 100
            },
            "cx": {
                "intent": "查询内容",
                "description": "查询已记录的内容",
                "handler": "note_service",
                "method": "query_content",
                "confidence": 100
            },
            "dc": {
                "intent": "点餐",
                "description": "点餐或餐饮查询",
                "handler": "food_service",
                "method": "order_food",
                "confidence": 100
            }
        }

    def route_message(self, user_input: str, user_id: str) -> Dict[str, Any]:
        """
        路由消息到对应的处理器

        Args:
            user_input: 用户输入内容
            user_id: 用户ID

        Returns:
            Dict[str, Any]: 路由结果
        """
        debug_utils.log_and_print(f"🚀 开始路由消息: '{user_input[:50]}...'", log_level="DEBUG")

        try:
            # 第一优先级：检查快捷指令
            shortcut_result = self._match_shortcut_command(user_input)
            if shortcut_result:
                debug_utils.log_and_print(f"🎯 快捷指令匹配: {shortcut_result['command']} -> {shortcut_result['intent']}", log_level="INFO")
                return {
                    'success': True,
                    'route_type': 'shortcut',
                    'command': shortcut_result['command'],
                    'intent': shortcut_result['intent'],
                    'confidence': shortcut_result['confidence'],
                    'handler': shortcut_result['handler'],
                    'method': shortcut_result['method'],
                    'content': shortcut_result['content'],
                    'reasoning': f"快捷指令 '{shortcut_result['command']}' 精确匹配"
                }
            # 第二优先级：AI意图识别
            if self.llm_service and self.llm_service.is_available():
                ai_result = self.llm_service.identify_intent(user_input, user_id)
                if ai_result.get('success') and ai_result.get('confidence', 0) >= 60:
                    # 映射AI识别的意图到处理器
                    handler_info = self._map_intent_to_handler(ai_result['intent'])
                    if handler_info:
                        debug_utils.log_and_print(f"🤖 AI意图识别: {ai_result['intent']} (置信度: {ai_result['confidence']})", log_level="INFO")
                        return {
                            'success': True,
                            'route_type': 'ai_intent',
                            'intent': ai_result['intent'],
                            'confidence': ai_result['confidence'],
                            'handler': handler_info['handler'],
                            'method': handler_info['method'],
                            'content': ai_result.get('extracted_content', user_input),
                            'parameters': ai_result.get('parameters', {}),
                            'reasoning': ai_result.get('reasoning', 'AI意图识别')
                        }

            # 无法路由：返回未知意图
            debug_utils.log_and_print(f"❓ 无法路由消息: {user_input[:50]}...", log_level="INFO")
            return {
                'success': True,
                'route_type': 'unknown',
                'intent': '其他',
                'confidence': 0,
                'handler': 'default',
                'method': 'handle_unknown',
                'content': user_input,
                'reasoning': '无匹配的快捷指令或AI识别置信度不足'
            }

        except Exception as e:
            debug_utils.log_and_print(f"❌ 路由处理失败: {e}", log_level="ERROR")
            return {
                'success': False,
                'error': str(e),
                'route_type': 'error',
                'intent': 'unknown',
                'confidence': 0
            }

    def _match_shortcut_command(self, user_input: str) -> Optional[Dict[str, Any]]:
        """
        匹配快捷指令

        Args:
            user_input: 用户输入

        Returns:
            Optional[Dict[str, Any]]: 匹配结果，None表示无匹配
        """
        user_input = user_input.strip()

        # 检查是否以2字符快捷指令开头
        for command, config in self.shortcut_commands.items():
            if user_input.startswith(command + " ") or user_input == command:
                # 提取指令后的内容
                if user_input == command:
                    content = ""
                else:
                    content = user_input[len(command):].strip()

                return {
                    'command': command,
                    'intent': config['intent'],
                    'handler': config['handler'],
                    'method': config['method'],
                    'confidence': config['confidence'],
                    'content': content
                }

        return None

    def _map_intent_to_handler(self, intent: str) -> Optional[Dict[str, str]]:
        """
        将AI识别的意图映射到处理器

        Args:
            intent: 意图类型

        Returns:
            Optional[Dict[str, str]]: 处理器信息
        """
        intent_handler_map = {
            "记录思考": {"handler": "note_service", "method": "record_thought"},
            "记录日程": {"handler": "note_service", "method": "record_schedule"},
            "点餐": {"handler": "food_service", "method": "order_food"},
            "其他": {"handler": "default", "method": "handle_unknown"}
        }

        return intent_handler_map.get(intent)

    def get_supported_commands(self) -> Dict[str, str]:
        """
        获取支持的快捷指令列表

        Returns:
            Dict[str, str]: 指令和描述的映射
        """
        return {cmd: config['description'] for cmd, config in self.shortcut_commands.items()}

    def get_status(self) -> Dict[str, Any]:
        """获取路由服务状态"""
        return {
            "service_name": "RouterService",
            "shortcut_commands_count": len(self.shortcut_commands),
            "supported_commands": list(self.shortcut_commands.keys()),
            "llm_service_available": self._is_llm_service_available(),
            "ai_intent_enabled": self._is_llm_service_available()
        }

    def _is_llm_service_available(self) -> bool:
        """检查LLM服务是否可用"""
        if self.llm_service and self.llm_service.is_available():
            return self.llm_service.get_status().get('available', False)
        return False