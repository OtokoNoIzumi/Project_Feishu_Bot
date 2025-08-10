"""
飞书适配器 - 处理飞书平台特定的协议转换

该模块职责：
1. 飞书WebSocket连接管理
2. 飞书消息格式与标准格式的双向转换
3. 飞书特定的API调用
"""

import os
import lark_oapi as lark

from Module.Common.scripts.common import debug_utils
from Module.Services.constants import UITypes, EnvVars, ServiceNames
from .cards import initialize_card_managers
from .handlers import MessageHandler, CardHandler, MenuHandler
from .senders import MessageSender
from .document import FeishuDocument
from .utils import create_debug_functions


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

    def __init__(self, message_router, app_controller):
        """
        初始化飞书适配器，作为前端层，要有能力在这一层直接访问所有后端服务
        pending和scheduler的依赖关系是一个特殊情况，需要单独处理

        Args:
            message_router: 消息路由器实例
            app_controller: 应用控制器，用于获取配置
        """
        # 来自已经初始化好的外部组件，按照定义的顺序
        self.app_controller = app_controller
        self.message_router = message_router

        # ----第一层依赖关系，需要app_controller----
        # 初始化飞书SDK配置
        self._init_feishu_config()

        # 创建飞书客户端
        self.client = lark.Client.builder().app_id(self.app_id).app_secret(self.app_secret).build()

        # ----第二层依赖关系，需要sender----
        # 创建消息发送器，这里的逻辑是sender通过app_controller访问服务，而不是反过来
        self.sender = MessageSender(self.client, app_controller)
        # document大概率也类似，但需要观察一下
        self.cloud_manager = FeishuDocument(self.client, app_controller, self.sender)

        # 导入并初始化新的卡片管理架构，这些每个卡片都是业务属地和整合的前端终端，完备独立的调用服务
        # message_router承载了部分未来要service化的业务，但这里不重构了，直接传进来【待优化
        self.card_registry = initialize_card_managers(app_controller=app_controller, sender=self.sender, message_router=message_router)

        # 从配置服务获取verbose设置并准备调试函数
        verbose_config = False  # 默认值
        if self.app_controller:
            config_service = self.app_controller.get_service(ServiceNames.CONFIG)
            if config_service:
                verbose_config = config_service.get('debug_verbose', False)

        debug_functions = create_debug_functions(verbose_config)

        # ----第三层依赖关系，需要sender、message_processor----
        self.message_handler = MessageHandler(
            app_controller, message_router, self.sender, debug_functions
        )
        self.card_handler = CardHandler(
            app_controller, message_router, self.sender, debug_functions, self.card_registry
        )
        self.menu_handler = MenuHandler(app_controller, message_router, self.sender)

        # 注入handler依赖，实现解耦
        self.message_handler.set_card_handler(self.card_handler)
        self.menu_handler.set_message_handler(self.message_handler)

        # 注册UI更新回调到pending_cache_service——后续【待优化
        self._register_ui_update_callbacks()

        # 创建WebSocket客户端
        self.ws_client = self._create_ws_client()

    def _init_feishu_config(self):
        """初始化飞书配置"""
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
