"""
飞书适配器 - 处理飞书平台特定的协议转换

该模块职责：
1. 飞书WebSocket连接管理
2. 飞书消息格式与标准格式的双向转换
3. 飞书特定的API调用
"""

import json
import pprint
import os
import lark_oapi as lark

from Module.Common.scripts.common import debug_utils
from Module.Services.constants import UITypes, EnvVars
from Module.Services.constants import ServiceNames
from Module.Application.app_utils import custom_serializer
from .cards import initialize_card_managers, get_card_manager
from .handlers import MessageHandler, CardHandler, MenuHandler
from .senders import MessageSender

# P2ImMessageReceiveV1对象调试开关 - 开发调试用
DEBUG_P2IM_OBJECTS = False  # 设置为True启用详细调试输出


def debug_p2im_object(data, object_type: str = "P2ImMessageReceiveV1"):
    """调试P2ImMessageReceiveV1对象的详细信息输出"""
    if not DEBUG_P2IM_OBJECTS:
        return

    debug_utils.log_and_print(f"🔍 {object_type}对象详细信息 (JSON序列化):", log_level="DEBUG")
    try:
        serializable_data = custom_serializer(data)
        json_output = json.dumps(serializable_data, indent=2, ensure_ascii=False)
        debug_utils.log_and_print(json_output, log_level="DEBUG")
        debug_utils.log_and_print(f"🔍 {object_type}对象详细信息 (pprint):", log_level="DEBUG")
        dict_representation = custom_serializer(data)
        pretty_output = pprint.pformat(dict_representation, indent=2, width=120)
        debug_utils.log_and_print(pretty_output, log_level="DEBUG")
    except Exception as e:
        debug_utils.log_and_print(f"  - 序列化失败: {e}", log_level="ERROR")
        debug_utils.log_and_print(f"  - 尝试使用 repr(): {repr(data)}", log_level="DEBUG")


def debug_parent_id_analysis(data):
    """分析并调试parent_id相关信息"""
    if not DEBUG_P2IM_OBJECTS:
        return

    # 特别关注回复消息的关键字段 parent_id
    if hasattr(data, 'event') and hasattr(data.event, 'message') and hasattr(data.event.message, 'parent_id'):
        parent_id = data.event.message.parent_id
        if parent_id:
            debug_utils.log_and_print(f"  - 关键信息: 此消息为回复消息, parent_id = {parent_id}", log_level="INFO")
        else:
            debug_utils.log_and_print("  - 关键信息: 此消息非回复消息 (parent_id is None or empty)", log_level="DEBUG")
    else:
        debug_utils.log_and_print("  - 关键信息: 未找到 parent_id 属性路径", log_level="DEBUG")


class FeishuAdapter:
    """
    飞书平台适配器

    职责：纯粹的协议转换和平台接口封装
    不包含任何业务逻辑，只负责与飞书平台的交互

    支持的交互类型：
    - 消息交互 (文本、图片、音频)
    - 菜单交互 (机器人菜单点击)
    - 卡片交互 (卡片按钮点击)

    回复模式控制：
    - 业务层通过parent_id指定回复关系，适配器根据parent_id决定发送方式
    - 有parent_id: 使用reply模式，关联到指定的消息
    - 无parent_id: 群聊默认reply用户消息，私聊创建新消息
    """

    def __init__(self, message_processor, app_controller=None):
        """
        初始化飞书适配器

        Args:
            message_processor: 消息处理器实例
            app_controller: 应用控制器，用于获取配置
        """
        self.message_processor = message_processor
        self.app_controller = app_controller

        # 导入并初始化新的卡片管理架构
        self.card_registry = initialize_card_managers()

        # 【待优化
        self.bili_card_manager = get_card_manager("bilibili")
        self.admin_card_manager = get_card_manager("admin")
        # 创建各种处理器，并注入依赖
        card_managers = {
            'bili': self.bili_card_manager,
            'admin': self.admin_card_manager
        }

        # 初始化飞书SDK配置
        self._init_feishu_config()

        # 创建飞书客户端
        self.client = lark.Client.builder().app_id(self.app_id).app_secret(self.app_secret).build()

        # 创建消息发送器
        self.sender = MessageSender(self.client, app_controller)

        # 准备调试函数
        debug_functions = {
            'debug_p2im_object': debug_p2im_object,
            'debug_parent_id_analysis': debug_parent_id_analysis
        }

        self.message_handler = MessageHandler(message_processor, self.sender, self.sender.get_user_name, debug_functions)
        self.card_handler = CardHandler(message_processor, self.sender, self.sender.get_user_name, card_managers, debug_functions)
        self.menu_handler = MenuHandler(message_processor, self.sender, self.sender.get_user_name)

        # 注入处理器方法到sender（避免循环依赖）
        self.sender.handle_bili_card_operation = self.card_handler._handle_bili_card_operation
        self.sender.handle_admin_card_operation = self.card_handler._handle_admin_card_operation
        self.sender.handle_bili_video_async = self.message_handler._handle_bili_video_async

        # 注册UI更新回调到pending_cache_service
        self._register_ui_update_callbacks()

        # 创建WebSocket客户端
        self.ws_client = self._create_ws_client()

    def _init_feishu_config(self):
        """初始化飞书配置"""
        if self.app_controller:
            # 从配置服务获取
            config_service = self.app_controller.get_service(ServiceNames.CONFIG)
            if config_service:
                app_id = config_service.get(EnvVars.FEISHU_APP_MESSAGE_ID)
                app_secret = config_service.get(EnvVars.FEISHU_APP_MESSAGE_SECRET)
                log_level_str = config_service.get('log_level', 'INFO')
            else:
                app_id = os.getenv(EnvVars.FEISHU_APP_MESSAGE_ID, "")
                app_secret = os.getenv(EnvVars.FEISHU_APP_MESSAGE_SECRET, "")
                log_level_str = os.getenv('log_level', 'INFO')

            self.app_id = app_id
            self.app_secret = app_secret
            self.log_level = getattr(lark.LogLevel, log_level_str)

        else:
            # 从环境变量获取
            self.app_id = os.getenv(EnvVars.FEISHU_APP_MESSAGE_ID, "")
            self.app_secret = os.getenv(EnvVars.FEISHU_APP_MESSAGE_SECRET, "")
            self.log_level = lark.LogLevel.INFO

        # 设置全局配置
        lark.APP_ID = self.app_id
        lark.APP_SECRET = self.app_secret

    def _create_ws_client(self):
        """创建WebSocket客户端"""
        # 创建事件处理器
        event_handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self.message_handler.handle_feishu_message)
            .register_p2_application_bot_menu_v6(self.menu_handler.handle_feishu_menu)
            .register_p2_card_action_trigger(self.card_handler.handle_feishu_card)
            .build()
        )

        # 创建WebSocket客户端
        return lark.ws.Client(
            self.app_id,
            self.app_secret,
            event_handler=event_handler,
            log_level=self.log_level
        )

    def _register_ui_update_callbacks(self):
        """注册UI更新回调到缓存服务"""
        pending_cache_service = self.app_controller.get_service(ServiceNames.PENDING_CACHE)
        if pending_cache_service:
            # 注册卡片UI更新回调，用来做定时的卡片更新
            card_ui_callback = self.card_handler.create_card_ui_update_callback()
            pending_cache_service.register_ui_update_callback(UITypes.INTERACTIVE_CARD, card_ui_callback)
            debug_utils.log_and_print("✅ 卡片UI更新回调注册成功", log_level="INFO")
        else:
            debug_utils.log_and_print("⚠️ pending_cache_service不可用，跳过UI更新回调注册", log_level="WARNING")

    # ================ 生命周期方法 ================

    def start(self):
        """启动飞书WebSocket连接"""
        debug_utils.log_and_print("🚀 启动飞书适配器...", log_level="INFO")
        self.ws_client.start()

    async def start_async(self):
        """异步启动飞书WebSocket连接"""
        debug_utils.log_and_print("🚀 异步启动飞书适配器...", log_level="INFO")
        await self.ws_client._connect()

    def disconnect(self):
        """断开飞书WebSocket连接"""
        if hasattr(self, 'ws_client') and self.ws_client:
            debug_utils.log_and_print("🛑 断开飞书适配器...", log_level="INFO")
            self.ws_client._disconnect()

    def get_status(self) -> dict:
        """
        获取适配器状态信息

        Returns:
            dict: 包含适配器状态的字典
        """
        return {
            "adapter_type": "feishu",
            "app_id": self.app_id[:8] + "..." if self.app_id else "未配置",
            "client_status": "已连接" if hasattr(self, 'ws_client') and self.ws_client else "未连接",
            "handlers_loaded": {
                "message_handler": self.message_handler is not None,
                "card_handler": self.card_handler is not None,
                "menu_handler": self.menu_handler is not None
            }
        }
