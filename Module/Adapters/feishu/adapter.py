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
from .cards import initialize_card_managers, get_card_manager
from .handlers import MessageHandler, CardHandler, MenuHandler
from .senders import MessageSender

# P2ImMessageReceiveV1对象调试开关 - 开发调试用
DEBUG_P2IM_OBJECTS = False  # 设置为True启用详细调试输出


def custom_serializer(obj):
    """
    自定义序列化函数，用于json.dumps。
    它会尝试获取对象的__dict__，如果对象没有__dict__（例如内置类型或使用__slots__的对象），
    或者__dict__中的某些值无法直接序列化，则回退到str(obj)。
    """
    # 处理特殊类型
    if isinstance(obj, bytes):
        return f"<bytes data len={len(obj)}>"

    # 处理复合类型
    if isinstance(obj, (list, tuple)):
        return [custom_serializer(item) for item in obj]

    if isinstance(obj, dict):
        return {k: custom_serializer(v) for k, v in obj.items()}

    # 处理有__dict__的对象
    if hasattr(obj, '__dict__'):
        return {
            k: custom_serializer(v)
            for k, v in vars(obj).items()
            if not k.startswith('_')
        }

    # 尝试JSON序列化，失败则转为字符串
    try:
        json.dumps(obj)  # 测试是否可序列化
        return obj
    except TypeError:
        return str(obj)


def debug_p2im_object(data, object_type: str = "P2ImMessageReceiveV1"):
    """
    调试P2ImMessageReceiveV1对象的详细信息输出

    Args:
        data: 需要调试的对象
        object_type: 对象类型名称（用于日志标识）
    """
    if not DEBUG_P2IM_OBJECTS:
        return

    debug_utils.log_and_print(f"🔍 {object_type}对象详细信息 (JSON序列化):", log_level="DEBUG")
    try:
        # 使用自定义序列化器进行转换
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
    """
    分析并调试parent_id相关信息

    Args:
        data: 需要分析的消息对象
    """
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
        self.bili_card_manager = get_card_manager("bilibili")
        self.admin_card_manager = get_card_manager("admin")

        # 初始化飞书SDK配置
        self._init_feishu_config()

        # 创建飞书客户端
        self.client = lark.Client.builder().app_id(self.app_id).app_secret(self.app_secret).build()

        # 创建消息发送器
        self.sender = MessageSender(self.client, app_controller)

        # 创建各种处理器，并注入依赖
        card_managers = {
            'bili': self.bili_card_manager,
            'admin': self.admin_card_manager
        }

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

        # 创建WebSocket客户端
        self.ws_client = self._create_ws_client()

    def _init_feishu_config(self):
        """初始化飞书配置"""
        if self.app_controller:
            # 从配置服务获取
            success, app_id = self.app_controller.call_service('config', 'get', 'FEISHU_APP_MESSAGE_ID')
            success2, app_secret = self.app_controller.call_service('config', 'get', 'FEISHU_APP_MESSAGE_SECRET')
            success3, log_level_str = self.app_controller.call_service('config', 'get', 'log_level', 'INFO')

            self.app_id = app_id if success else os.getenv("FEISHU_APP_MESSAGE_ID", "")
            self.app_secret = app_secret if success2 else os.getenv("FEISHU_APP_MESSAGE_SECRET", "")
            self.log_level = getattr(lark.LogLevel, log_level_str) if success3 else lark.LogLevel.INFO
        else:
            # 从环境变量获取
            self.app_id = os.getenv("FEISHU_APP_MESSAGE_ID", "")
            self.app_secret = os.getenv("FEISHU_APP_MESSAGE_SECRET", "")
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

    # ================ 生命周期方法 ================

    def start(self):
        """启动飞书WebSocket连接"""
        debug_utils.log_and_print("🚀 启动飞书适配器...", log_level="INFO")
        self.ws_client.start()

    async def start_async(self):
        """异步启动飞书WebSocket连接"""
        debug_utils.log_and_print("🚀 异步启动飞书适配器...", log_level="INFO")
        await self.ws_client.start_async()

    def stop(self):
        """停止飞书WebSocket连接"""
        if hasattr(self, 'ws_client') and self.ws_client:
            debug_utils.log_and_print("🛑 停止飞书适配器...", log_level="INFO")
            self.ws_client.stop()

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
