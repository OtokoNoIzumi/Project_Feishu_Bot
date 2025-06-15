"""
路由服务 - 智能消息路由

提供2字符快捷指令精确匹配和AI意图识别备选方案
"""

import json
import os
from typing import Dict, Any, Optional
from Module.Common.scripts.common import debug_utils


class RouterService:
    """
    智能路由服务

    职责：
    1. 2字符快捷指令精确匹配（100%准确率）
    2. AI意图识别备选方案（基于IntentProcessor的两阶段处理）
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

        # 加载统一配置
        self.config = self._load_unified_config()
        self.shortcut_commands = self._load_shortcut_commands()
        self.intent_handlers = self._load_intent_handlers()

    def _init_services(self):
        """初始化依赖的服务"""
        if self.app_controller:
            self.llm_service = self.app_controller.get_service('llm')
            debug_utils.log_and_print(f"RouterService 获取 LLM 服务: {'成功' if self.llm_service else '失败'}", log_level="INFO")
        else:
            debug_utils.log_and_print("RouterService 未能获取 app_controller", log_level="WARNING")

    def _load_unified_config(self) -> Dict[str, Any]:
        """
        加载统一的意图配置文件

        Returns:
            Dict[str, Any]: 统一配置
        """
        try:
            config_path = os.path.join(
                os.path.dirname(__file__),
                '..', 'llm', 'intent_config.json'
            )
            config_path = os.path.abspath(config_path)

            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            debug_utils.log_and_print(f"✅ RouterService 加载统一配置成功: {len(config.get('intents', {}))} 个意图", log_level="DEBUG")
            return config
        except Exception as e:
            debug_utils.log_and_print(f"❌ RouterService 加载统一配置失败: {e}", log_level="ERROR")
            return {"intents": {}, "routing": {}, "settings": {}}

    def _load_shortcut_commands(self) -> Dict[str, Dict[str, Any]]:
        """
        从统一配置加载快捷指令配置

        Returns:
            Dict[str, Dict[str, Any]]: 快捷指令配置
        """
        routing_config = self.config.get('routing', {})
        shortcut_commands = routing_config.get('shortcut_commands', {})

        # 为每个快捷指令添加置信度
        commands = {}
        for cmd, config in shortcut_commands.items():
            commands[cmd] = {
                **config,
                "confidence": 100  # 快捷指令100%置信度
            }

        debug_utils.log_and_print(f"✅ 从配置加载快捷指令: {list(commands.keys())}", log_level="DEBUG")
        return commands

    def _load_intent_handlers(self) -> Dict[str, Dict[str, str]]:
        """
        从统一配置加载意图处理器映射

        Returns:
            Dict[str, Dict[str, str]]: 意图到处理器的映射
        """
        routing_config = self.config.get('routing', {})
        intent_handlers = routing_config.get('intent_handlers', {})

        debug_utils.log_and_print(f"✅ 从配置加载意图处理器映射: {list(intent_handlers.keys())}", log_level="DEBUG")
        return intent_handlers

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

            # 第二优先级：AI意图识别（使用新的两阶段处理）
            if self.llm_service and self.llm_service.is_available():
                # 使用process_input_advanced方法获取完整的两阶段处理结果
                ai_result = self.llm_service.process_input_advanced(user_input, self._get_confidence_threshold())

                if ai_result.get('success') and ai_result.get('intent_confidence', 0) >= self._get_confidence_threshold():
                    intent = ai_result.get('determined_intent')
                    # 映射AI识别的意图到处理器
                    handler_info = self._map_intent_to_handler(intent)
                    if handler_info:
                        debug_utils.log_and_print(f"🤖 AI意图识别: {intent} (置信度: {ai_result.get('intent_confidence')})", log_level="INFO")
                        return {
                            'success': True,
                            'route_type': 'ai_intent',
                            'intent': intent,
                            'confidence': ai_result.get('intent_confidence', 0),
                            'handler': handler_info['handler'],
                            'method': handler_info['method'],
                            'content': user_input,  # 保持原始输入
                            'parameters': ai_result.get('parameters', {}),
                            'reasoning': f"AI意图识别: {intent}",
                            'other_intent_name': ai_result.get('other_intent_name', ''),
                            'stage1_scores': ai_result.get('stage1_intent_scores', {})
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

    def _get_confidence_threshold(self) -> int:
        """获取置信度阈值"""
        return self.config.get('settings', {}).get('default_confidence_threshold', 60)

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
        return self.intent_handlers.get(intent)

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
            "intent_handlers_count": len(self.intent_handlers),
            "supported_intents": list(self.intent_handlers.keys()),
            "llm_service_available": self._is_llm_service_available(),
            "ai_intent_enabled": self._is_llm_service_available(),
            "unified_config_loaded": bool(self.config.get('intents')),
            "confidence_threshold": self._get_confidence_threshold()
        }

    def _is_llm_service_available(self) -> bool:
        """检查LLM服务是否可用"""
        if self.llm_service and self.llm_service.is_available():
            return self.llm_service.get_status().get('available', False)
        return False