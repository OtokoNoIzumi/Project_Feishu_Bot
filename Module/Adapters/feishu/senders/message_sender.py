"""
飞书消息发送器 (Feishu Message Sender)

负责所有飞书消息发送功能，包括：
- 文本、图片、音频等消息发送
- 交互式卡片发送
- 文件上传和处理
- 多种发送模式支持
"""

import json
import os
from typing import Optional, Dict, Any, Tuple, List
from pathlib import Path
import base64
from io import BytesIO

from lark_oapi.api.contact.v3 import GetUserRequest
from lark_oapi.api.im.v1 import (
    CreateMessageRequest, CreateMessageRequestBody,
    ReplyMessageRequest, ReplyMessageRequestBody,
    CreateFileRequest, CreateFileRequestBody,
    GetMessageResourceRequest,
    CreateImageRequest, CreateImageRequestBody,
    PatchMessageRequest, PatchMessageRequestBody
)

from Module.Common.scripts.common import debug_utils
from Module.Business.processors import ProcessResult
from ..decorators import (
    feishu_sdk_safe, file_operation_safe
)
from Module.Services.constants import (
    ServiceNames, ConfigKeys, ReplyModes, ChatTypes, ReceiverIdTypes,
    Messages
)


class MessageSender:
    """飞书消息发送器"""

    def __init__(self, client, app_controller=None):
        """
        初始化消息发送器

        Args:
            client: 飞书SDK客户端
            app_controller: 应用控制器，用于获取配置
        """
        self.client = client
        self.app_controller = app_controller

    @feishu_sdk_safe("获取用户名失败", return_value="用户_未知")
    def get_user_name(self, open_id: str) -> str:
        """
        获取用户昵称

        Args:
            open_id: 用户的open_id

        Returns:
            str: 用户昵称，获取失败时返回默认值
        """
        # 先从缓存获取
        if self.app_controller:
            success, cached_name = self.app_controller.call_service(ServiceNames.CACHE, 'get_user_name', f"user:{open_id}")
            if success and cached_name:
                return cached_name

        request = GetUserRequest.builder().user_id_type(ReceiverIdTypes.OPEN_ID).user_id(open_id).build()
        response = self.client.contact.v3.user.get(request)
        if response.success() and response.data and response.data.user:
            user = response.data.user
            # 优先级：nickname > display_name > name > open_id
            name = (
                getattr(user, 'nickname', None)
                or getattr(user, 'display_name', None)
                or getattr(user, 'name', None)
                or f"用户_{open_id[:8]}"
            )
            # 缓存用户名
            if self.app_controller:
                self.app_controller.call_service(ServiceNames.CACHE, 'update_user', f"user:{open_id}", name)
                self.app_controller.call_service(ServiceNames.CACHE, 'save_user_cache')
            return name

        debug_utils.log_and_print(f"获取用户名失败: {response.code} - {response.msg}", log_level="WARNING")
        return f"用户_{open_id[:8]}"

    @feishu_sdk_safe("发送飞书回复失败", return_value=False)
    def send_feishu_reply(self, original_data, result: ProcessResult, force_reply_mode: str = None) -> bool:
        """
        发送飞书回复消息

        支持3种消息模式：
        1. "new" - 新消息 (CreateMessage)
        2. "reply" - 回复消息 (ReplyMessage)
        3. "thread" - 回复新话题 (ReplyMessage + reply_in_thread)

        Args:
            original_data: 原始飞书消息数据
            result: 处理结果
            force_reply_mode: 强制指定回复模式 ("new"|"reply"|"thread")
        """
        if not result.should_reply:
            return True

        # 转换响应内容为飞书格式
        content_json = json.dumps(result.response_content)

        # 决定消息模式
        reply_mode = self._determine_reply_mode(original_data, result, force_reply_mode)

        # 提取基础信息
        chat_id = original_data.event.message.chat_id
        user_id = original_data.event.sender.sender_id.open_id

        try:
            match reply_mode:
                case ReplyModes.NEW:
                    # 模式1: 新消息
                    return self._send_create_message(user_id, content_json, result.response_type, ReceiverIdTypes.OPEN_ID)[0]

                case ReplyModes.REPLY | ReplyModes.THREAD:
                    # 模式2&3: 回复消息 (含新话题)
                    message_id = original_data.event.message.message_id
                    return self._send_reply_message(message_id, content_json, result.response_type, reply_mode == ReplyModes.THREAD)[0]

                case _:
                    debug_utils.log_and_print(f"❌ 未知的回复模式: {reply_mode}", log_level="ERROR")
                    return False

        except Exception as e:
            debug_utils.log_and_print(f"❌ 发送消息失败: {e}", log_level="ERROR")
            return False

    def _determine_reply_mode(self, original_data, result: ProcessResult, force_mode: str = None) -> str:
        """
        决定回复模式

        优先级:
        1. 强制模式参数
        2. ProcessResult中的parent_id指定
        3. 消息类型和聊天类型的默认策略
        """
        if force_mode in ["new", "reply", "thread"]:
            return force_mode

        # 根据parent_id判断
        if result.parent_id:
            return "reply"

        # 默认策略: 群聊回复，私聊新消息
        chat_type = original_data.event.message.chat_type
        return ReplyModes.REPLY if chat_type == ChatTypes.GROUP else ReplyModes.NEW

    def _send_create_message(self, receive_id: str, content: str, msg_type: str, receive_id_type: str = ReceiverIdTypes.OPEN_ID) -> Tuple[bool, Optional[str]]:
        """发送新消息（支持用户ID和聊天ID）

        Returns:
            Tuple[bool, Optional[str]]: (是否成功, 消息ID)
        """
        request = CreateMessageRequest.builder().receive_id_type(receive_id_type).request_body(
            CreateMessageRequestBody.builder()
            .receive_id(receive_id)
            .msg_type(msg_type)
            .content(content)
            .build()
        ).build()

        response = self.client.im.v1.message.create(request)
        if not response.success():
            debug_utils.log_and_print(f"{Messages.NEW_MESSAGE_SEND_FAILED}: {response.code} - {response.msg}", log_level="ERROR")
            return False, None

        # 获取消息ID
        message_id = response.data.message_id if response.data else None
        return True, message_id

    def _send_reply_message(self, message_id: str, content: str, msg_type: str, reply_in_thread: bool = False) -> Tuple[bool, Optional[str]]:
        """发送回复消息

        Returns:
            Tuple[bool, Optional[str]]: (是否成功, 回复消息ID)
        """
        builder = ReplyMessageRequestBody.builder() \
            .msg_type(msg_type) \
            .content(content)

        if reply_in_thread:
            builder = builder.reply_in_thread(True)

        request = ReplyMessageRequest.builder() \
            .message_id(message_id) \
            .request_body(builder.build()) \
            .build()

        response = self.client.im.v1.message.reply(request)
        if not response.success():
            debug_utils.log_and_print(f"❌ 回复消息发送失败: {response.code} - {response.msg}", log_level="ERROR")
            return False, None

        # 获取回复消息ID
        reply_message_id = response.data.message_id if response.data else None
        return True, reply_message_id

    @feishu_sdk_safe("发送飞书直接消息失败", return_value=False)
    def send_direct_message(self, user_id: str, result: ProcessResult) -> bool:
        """发送直接消息（用于菜单点击等主动发送）"""
        if not result.response_content:
            return True

        # 转换响应内容为飞书格式
        content_json = json.dumps(result.response_content)

        # 复用_send_create_message方法，避免代码重复
        return self._send_create_message(user_id, content_json, result.response_type, "open_id")[0]

    @feishu_sdk_safe("发送交互式卡片失败", return_value=(False, None))
    def send_interactive_card(
        self,
        chat_id: str = None,
        user_id: str = None,
        card_content: Dict[str, Any] = None,
        reply_mode: str = "new",
        message_id: str = None
    ) -> Tuple[bool, Optional[str]]:
        """
        统一的交互式卡片发送方法

        支持3种发送模式：
        1. "new" - 新消息模式 (CreateMessage)
        2. "reply" - 回复模式 (ReplyMessage)
        3. "thread" - 回复新话题模式 (ReplyMessage + reply_in_thread)

        Args:
            chat_id: 聊天ID (new模式使用)
            user_id: 用户ID (new模式的替代方案，兼容旧版本)
            card_content: 卡片内容
            reply_mode: 发送模式 ("new"|"reply"|"thread")
            message_id: 回复的消息ID (reply/thread模式必需)

        Returns:
            Tuple[bool, Optional[str]]: (是否发送成功, 消息ID)
        """
        # 参数验证
        validation_result = self._validate_card_send_params(
            card_content, reply_mode, chat_id, user_id, message_id
        )
        if not validation_result["valid"]:
            debug_utils.log_and_print(f"❌ {validation_result['error']}", log_level="ERROR")
            return False, None

        # 将卡片内容转换为JSON字符串
        content_json = json.dumps(card_content, ensure_ascii=False)

        # 处理不同发送模式
        match reply_mode:
            case "reply" | "thread":
                # 复用_send_reply_message逻辑，统一处理
                return self._send_reply_message(
                    message_id=message_id,
                    content=content_json,
                    msg_type="interactive",
                    reply_in_thread=(reply_mode == "thread")
                )

            case "new":
                # 处理新消息模式
                return self._send_new_interactive_card(chat_id, user_id, content_json)

            case _:
                debug_utils.log_and_print(f"❌ 不支持的发送模式: {reply_mode}", log_level="ERROR")
                return False, None

    def _validate_card_send_params(
        self, card_content, reply_mode: str, chat_id: str, user_id: str, message_id: str
    ) -> Dict[str, Any]:
        """验证卡片发送参数"""
        if not card_content:
            return {"valid": False, "error": "卡片内容为空"}

        match reply_mode:
            case "new":
                if not (chat_id or user_id):
                    return {"valid": False, "error": "新消息模式需要chat_id或user_id"}

            case "reply" | "thread":
                if not message_id:
                    return {"valid": False, "error": "回复模式需要message_id"}

            case _:
                return {"valid": False, "error": f"不支持的发送模式: {reply_mode}"}

        return {"valid": True}

    @feishu_sdk_safe("发送新交互式卡片失败", return_value=(False, None))
    def _send_new_interactive_card(self, chat_id: str, user_id: str, content_json: str) -> Tuple[bool, Optional[str]]:
        """发送新的交互式卡片消息

        Returns:
            Tuple[bool, Optional[str]]: (是否成功, 消息ID)
        """
        # 确定接收者信息
        receive_id = chat_id or user_id
        receive_id_type = "chat_id" if chat_id else "open_id"

        # 复用_send_create_message方法，避免代码重复
        success, message_id = self._send_create_message(receive_id, content_json, "interactive", receive_id_type)

        return success, message_id

    @feishu_sdk_safe("获取图像资源失败", return_value=None)
    def get_image_resource(self, original_data) -> Optional[Tuple[str, str, str, int]]:
        """
        获取图像资源

        Returns:
            Optional[Tuple[str, str, str, int]]: (base64图像数据, MIME类型, 文件名, 文件大小)
        """
        message = original_data.event.message
        image_content = json.loads(message.content)

        if "image_key" not in image_content:
            debug_utils.log_and_print("图片消息格式错误，缺少image_key", log_level="ERROR")
            return None

        image_key = image_content["image_key"]
        message_id = message.message_id

        # 获取图片资源
        request = GetMessageResourceRequest.builder() \
            .message_id(message_id) \
            .file_key(image_key) \
            .type("image") \
            .build()

        response = self.client.im.v1.message_resource.get(request)

        if not response.success():
            debug_utils.log_and_print(f"获取图片资源失败: {response.code} - {response.msg}", log_level="ERROR")
            return None

        # 读取图片数据
        file_content = response.file.read()
        if not file_content:
            debug_utils.log_and_print("图片数据为空", log_level="ERROR")
            return None

        # 获取文件信息
        file_name = getattr(response.file, "file_name", "image.jpg")
        mime_type = getattr(response.file, "content_type", "image/jpeg")
        file_size = len(file_content)

        # 转换为base64
        image_base64 = base64.b64encode(file_content).decode('utf-8')

        debug_utils.log_and_print(f"成功获取图片资源: {file_name}, 大小: {file_size} bytes", log_level="INFO")
        return image_base64, mime_type, file_name, file_size

    @file_operation_safe("批量上传图片失败", return_value=False)
    def upload_and_send_images(self, original_data, image_paths: List[str]) -> bool:
        """上传并发送多张图片"""
        success_count = 0

        for image_path in image_paths:
            if not image_path or not os.path.exists(image_path):
                continue

            # 上传单张图片
            if self.upload_and_send_single_image(original_data, image_path):
                success_count += 1

        if success_count > 0:
            debug_utils.log_and_print(f"成功发送 {success_count}/{len(image_paths)} 张图片", log_level="INFO")
            return True

        debug_utils.log_and_print("没有成功发送任何图片", log_level="ERROR")
        return False

    @file_operation_safe("上传单张图片失败", return_value=False)
    def upload_and_send_single_image(self, original_data, image_path: str) -> bool:
        """上传并发送单张图片"""
        with open(image_path, "rb") as image_file:
            upload_response = self.client.im.v1.image.create(
                CreateImageRequest.builder()
                .request_body(
                    CreateImageRequestBody.builder()
                    .image_type("message")
                    .image(image_file)
                    .build()
                )
                .build()
            )

            if (upload_response.success() and
                upload_response.data and
                upload_response.data.image_key):

                # 发送图片消息
                image_result = ProcessResult.success_result("image", {"image_key": upload_response.data.image_key}, parent_id=original_data.event.message.message_id)
                return self.send_feishu_reply(original_data, image_result)

            debug_utils.log_and_print(f"图片上传失败: {upload_response.code} - {upload_response.msg}", log_level="ERROR")
            return False

    @file_operation_safe("音频上传处理失败", return_value=False)
    def upload_and_send_audio(self, original_data, audio_data: bytes) -> bool:
        """上传音频并发送消息"""
        temp_mp3_path = None
        temp_opus_path = None

        try:
            # 获取音频服务
            if not self.app_controller:
                debug_utils.log_and_print("应用控制器不可用", log_level="ERROR")
                return False

            audio_service = self.app_controller.get_service(ServiceNames.AUDIO)
            if not audio_service:
                debug_utils.log_and_print("音频服务不可用", log_level="ERROR")
                return False

            # 创建临时MP3文件
            temp_mp3_path = audio_service.create_temp_audio_file(audio_data, ".mp3")

            # 转换为opus格式
            temp_opus_path, duration_ms = audio_service.convert_to_opus(temp_mp3_path)

            if not temp_opus_path or not os.path.exists(temp_opus_path):
                debug_utils.log_and_print("音频转换失败", log_level="ERROR")
                return False

            # 上传到飞书
            file_key = self._upload_opus_to_feishu(temp_opus_path, duration_ms)

            if file_key:
                # 发送音频消息
                content_json = json.dumps({"file_key": file_key})
                result = ProcessResult.success_result("audio", json.loads(content_json), parent_id=original_data.event.message.message_id)
                return self.send_feishu_reply(original_data, result)

            debug_utils.log_and_print("音频上传到飞书失败", log_level="ERROR")
            return False

        finally:
            # 清理临时文件 - 使用音频服务的清理方法
            if temp_mp3_path and audio_service:
                audio_service.cleanup_temp_file(temp_mp3_path)
            if temp_opus_path and audio_service:
                audio_service.cleanup_temp_file(temp_opus_path)

    @file_operation_safe("音频上传异常", return_value=None)
    def _upload_opus_to_feishu(self, opus_path: str, duration_ms: int) -> Optional[str]:
        """上传opus音频文件到飞书"""
        with open(opus_path, "rb") as audio_file:
            opus_filename = Path(opus_path).name

            upload_response = self.client.im.v1.file.create(
                CreateFileRequest.builder()
                .request_body(
                    CreateFileRequestBody.builder()
                    .file_type("opus")
                    .file_name(opus_filename)
                    .duration(str(int(duration_ms)))
                    .file(audio_file)
                    .build()
                ).build()
            )

            if upload_response.success() and upload_response.data and upload_response.data.file_key:
                return upload_response.data.file_key

            debug_utils.log_and_print(
                f"音频上传失败: {upload_response.code} - {upload_response.msg}",
                log_level="ERROR"
            )
            return None

    @file_operation_safe("富文本上传发送失败", return_value=False)
    def upload_and_send_rich_text(self, original_data, result: ProcessResult) -> bool:
        """上传并发送富文本"""

        image_data = result.response_content.get("sample_image_data")
        if not image_data:
            # 如果没有图片数据，发送纯文本富文本
            rich_text_content = result.response_content.get("rich_text_content")
            if not rich_text_content:
                debug_utils.log_and_print("富文本内容为空", log_level="ERROR")
                return False
            result = ProcessResult.success_result("post", rich_text_content, parent_id=result.parent_id)
            return self.send_feishu_reply(original_data, result)

        # 上传图片
        image_file = BytesIO(image_data)
        upload_response = self.client.im.v1.image.create(
            CreateImageRequest.builder()
            .request_body(
                CreateImageRequestBody.builder()
                .image_type("message")
                .image(image_file)
                .build()
            )
            .build()
        )

        if not (upload_response.success() and upload_response.data and upload_response.data.image_key):
            debug_utils.log_and_print("富文本图片上传失败", log_level="ERROR")
            return False

        # 在富文本内容中添加图片
        rich_text_content = result.response_content.get("rich_text_content")
        if not rich_text_content:
            debug_utils.log_and_print("富文本内容为空", log_level="ERROR")
            return False

        image_key = upload_response.data.image_key

        # 在第二行插入图片（在链接行后面）
        rich_text_content["zh_cn"]["content"].insert(1, [{"tag": "img", "image_key": image_key}])

        # 使用统一的发送方法
        result = ProcessResult.success_result("post", rich_text_content, parent_id=result.parent_id)
        return self.send_feishu_reply(original_data, result)

    @file_operation_safe("示例图片上传发送失败", return_value=False)
    def upload_and_send_single_image_data(self, original_data, image_data: bytes) -> bool:
        """上传并发送单张图片数据"""
        image_stream = BytesIO(image_data)
        upload_response = self.client.im.v1.image.create(
            CreateImageRequest.builder()
            .request_body(
                CreateImageRequestBody.builder()
                .image_type("message")
                .image(image_stream)
                .build()
            )
            .build()
        )

        if (upload_response.success() and
            upload_response.data and
            upload_response.data.image_key):

            # 发送图片消息
            image_result = ProcessResult.success_result(
                "image",
                {"image_key": upload_response.data.image_key},
                parent_id=original_data.event.message.message_id
            )
            return self.send_feishu_reply(original_data, image_result)

        debug_utils.log_and_print(f"示例图片上传失败: {upload_response.code} - {upload_response.msg}", log_level="ERROR")
        return False

    @feishu_sdk_safe("更新交互式卡片失败", return_value=False)
    def update_interactive_card(self, message_id: str, card_content: Dict[str, Any]) -> bool:
        """更新交互式卡片内容"""
        content_json = json.dumps(card_content, ensure_ascii=False)

        request = PatchMessageRequest.builder().message_id(message_id).request_body(
            PatchMessageRequestBody.builder()
            .content(content_json)
            .build()
        ).build()

        response = self.client.im.v1.message.patch(request)

        if response.success():
            # 移除成功日志，减少噪音
            return True

        debug_utils.log_and_print(f"❌ 交互式卡片更新失败: {response.code} - {response.msg}", log_level="ERROR")
        return False
