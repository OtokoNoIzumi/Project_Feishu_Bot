"""
媒体处理器

处理TTS配音、图像生成、图像转换、富文本等媒体相关功能
"""

import os
from datetime import datetime
import time

from .base_processor import (
    BaseProcessor,
    MessageContext,
    ProcessResult,
    require_service,
    safe_execute,
)
from Module.Business.routine_record import RoutineRecord
from Module.Services.constants import (
    ResponseTypes,
    ProcessResultConstKeys,
    ProcessResultNextAction,
    ServiceNames,
    RouteTypes,
    RoutineRecordModes,
)
from Module.Common.scripts.common.translation import extract_phonetics
from Module.Business.processors import RouteResult


class MediaProcessor(BaseProcessor):
    """
    媒体处理器

    处理各种媒体相关的功能
    """

    # region TTS配音模块

    @require_service("audio", "音频服务未启动")
    @safe_execute("配音指令处理失败")
    def handle_tts_command(
        self, context: MessageContext, user_msg: str
    ) -> ProcessResult:
        """处理TTS配音指令"""
        # 提取配音文本
        tts_text = user_msg.split("配音", 1)[1].strip()
        if not tts_text:
            return ProcessResult.error_result(
                "配音文本不能为空，请使用格式：配音 文本内容"
            )

        # 先发送处理中提示
        return ProcessResult.success_result(
            ResponseTypes.TEXT,
            {
                "text": "正在生成配音，请稍候...",
                ProcessResultConstKeys.NEXT_ACTION: ProcessResultNextAction.PROCESS_TTS,
                "tts_text": tts_text,
            },
        )

    @require_service("audio", "音频服务未启动")
    @safe_execute("TTS异步处理失败")
    def process_tts_async(self, tts_text: str) -> ProcessResult:
        """
        异步处理TTS生成

        Args:
            tts_text: 要转换的文本

        Returns:
            ProcessResult: 处理结果
        """
        # 获取音频服务
        audio_service = self.app_controller.get_service(ServiceNames.AUDIO)

        # 生成TTS音频
        success, audio_data, error_msg = audio_service.process_tts_request(tts_text)

        if not success:
            return ProcessResult.error_result(f"TTS生成失败: {error_msg}")

        # 返回音频数据，由适配器处理上传
        return ProcessResult.success_result(
            ResponseTypes.AUDIO,
            {
                "audio_data": audio_data,
                "text": tts_text[:50] + ("..." if len(tts_text) > 50 else ""),
            },
        )

    # endregion

    # region 图像生成模块

    @require_service("image", "图像生成服务未启动或不可用", check_available=True)
    @safe_execute("图像生成指令处理失败")
    def handle_image_generation_command(
        self, context: MessageContext, user_msg: str
    ) -> ProcessResult:
        """处理图像生成指令"""
        # 提取生图文本
        if "生图" in user_msg:
            prompt = user_msg.split("生图", 1)[1].strip()
        elif "AI画图" in user_msg:
            prompt = user_msg.split("AI画图", 1)[1].strip()
        else:
            prompt = ""

        if not prompt:
            return ProcessResult.error_result(
                "图像生成文本不能为空，请使用格式：生图 描述内容 或 AI画图 描述内容"
            )

        # 先发送处理中提示
        return ProcessResult.success_result(
            ResponseTypes.TEXT,
            {
                "text": "正在生成图片，请稍候...",
                ProcessResultConstKeys.NEXT_ACTION: ProcessResultNextAction.PROCESS_IMAGE_GENERATION,
                "generation_prompt": prompt,
            },
        )

    @require_service("image", "图像生成服务未启动或不可用", check_available=True)
    @safe_execute("图像生成异步处理失败")
    def process_image_generation_async(self, prompt: str) -> ProcessResult:
        """
        异步处理图像生成

        Args:
            prompt: 图像生成提示词

        Returns:
            ProcessResult: 处理结果
        """
        # 获取图像服务
        image_service = self.app_controller.get_service(ServiceNames.IMAGE)

        # 生成图像
        image_paths = image_service.process_text_to_image(prompt)

        error_msg = ""
        if image_paths is None:
            error_msg = "默认图片生成服务故障，已经通知管理员修复咯！"
        elif len(image_paths) == 0:
            error_msg = "默认图片生成失败了，建议您换个提示词再试试"

        if error_msg:
            image_paths = image_service.process_text_to_image_hunyuan(prompt)
            if image_paths is None:
                error_msg += "\n备用方案：混元图片生成服务也故障了！"
            else:
                error_msg += "\n备用方案：混元图片生成成功！"

        # 返回图像路径列表，由适配器处理上传
        return ProcessResult.success_result(
            ResponseTypes.IMAGE_LIST,
            {
                "image_paths": image_paths,
                "prompt": prompt[:50] + ("..." if len(prompt) > 50 else ""),
                "error_msg": error_msg,
            },
        )

    @require_service("image", "图像处理服务未启动或不可用")
    @safe_execute("图像消息处理失败")
    def handle_image_message(self, context: MessageContext) -> ProcessResult:
        """处理图片消息 - 图像风格转换"""
        # 检查图像服务是否可用（包含特殊的首次初始化逻辑）
        first_init = (
            "image" in self.app_controller.initialized_services
        )  # 根据启动特征，避免首次启动时双倍初始化
        image_service = self.app_controller.get_service(ServiceNames.IMAGE)
        if not image_service.is_available(need_reinit=first_init):
            return ProcessResult.error_result("图像处理服务未启动或不可用")

        # 先发送处理中提示
        return ProcessResult.success_result(
            ResponseTypes.TEXT,
            {
                "text": "正在转换图片风格，请稍候...",
                ProcessResultConstKeys.NEXT_ACTION: ProcessResultNextAction.PROCESS_IMAGE_CONVERSION,
                "image_data": context.content,  # 图像数据将由适配器传递
            },
        )

    @require_service("image", "图像转换服务未启动或不可用", check_available=True)
    @safe_execute("图像转换异步处理失败")
    def process_image_conversion_async(
        self, image_base64: str, mime_type: str, file_name: str, file_size: int
    ) -> ProcessResult:
        """
        异步处理图像风格转换

        Args:
            image_base64: base64编码的图像数据
            mime_type: 图像MIME类型
            file_name: 文件名
            file_size: 文件大小

        Returns:
            ProcessResult: 处理结果
        """
        # 获取图像服务
        image_service = self.app_controller.get_service(ServiceNames.IMAGE)

        # 处理图像转换
        image_paths = image_service.process_image_to_image(
            image_base64, mime_type, file_name, file_size
        )

        if image_paths is None:
            return ProcessResult.error_result("图片处理故障，已经通知管理员修复咯！")
        elif len(image_paths) == 0:
            return ProcessResult.error_result("图片处理失败了，请尝试使用其他图片")

        # 返回处理后的图像路径列表
        return ProcessResult.success_result(
            ResponseTypes.IMAGE_LIST,
            {"image_paths": image_paths, "original_file": file_name},
        )

    # endregion

    # region 示例多媒体

    def sample_rich_text(self, context: MessageContext) -> ProcessResult:
        """处理富文本指令"""
        try:
            # 获取示例图片路径
            sample_pic_path = os.getenv("SAMPLE_PIC_PATH", "")

            if not sample_pic_path or not os.path.exists(sample_pic_path):
                return ProcessResult.error_result("示例图片不存在，无法创建富文本消息")

            # 读取图片文件
            with open(sample_pic_path, "rb") as f:
                image_data = f.read()

            # 生成富文本内容
            rich_text_content = {
                "zh_cn": {
                    "title": "富文本示例",
                    "content": [
                        [
                            {
                                "tag": "text",
                                "text": "第一行:",
                                "style": ["bold", "underline"],
                            },
                            {
                                "tag": "a",
                                "href": "https://open.feishu.cn",
                                "text": "飞书开放平台",
                                "style": ["italic"],
                            },
                            {"tag": "at", "user_id": "all", "style": ["lineThrough"]},
                        ],
                        [{"tag": "text", "text": "🔍 飞书URL解析规律发现："}],
                        [
                            {
                                "tag": "text",
                                "text": "✅ B站视频BV号会自动解析为卡片: https://www.bilibili.com/video/BV1eG411C755",
                            }
                        ],
                        [
                            {
                                "tag": "text",
                                "text": "❌ 个人网站保持文本格式: https://otokonoizumi.github.io/",
                            }
                        ],
                        [
                            {
                                "tag": "text",
                                "text": "❌ B站番剧链接也仅显示文本: https://www.bilibili.com/bangumi/play/ss28747",
                            }
                        ],
                        [
                            {
                                "tag": "text",
                                "text": "💡 规律：多链接时需悬停查看预览，单链接时直接显示卡片。普通文本类型的消息规律一致。",
                            }
                        ],
                        [
                            {"tag": "emotion", "emoji_type": "BLUSH"},
                            {"tag": "emotion", "emoji_type": "FINGERHEART"},
                        ],
                        [{"tag": "hr"}],
                        [{"tag": "text", "text": "代码示例:"}],
                        [
                            {
                                "tag": "code_block",
                                "language": "PYTHON",
                                "text": "print('Hello World')",
                            }
                        ],
                        [{"tag": "hr"}],
                        [
                            {
                                "tag": "md",
                                "text": "**Markdown内容**\n- 列表项1\n- 列表项2\n```python\nprint('代码块')\n```",
                            }
                        ],
                    ],
                }
            }

            return ProcessResult.success_result(
                ResponseTypes.RICH_TEXT,
                {
                    "rich_text_content": rich_text_content,
                    "sample_image_data": image_data,
                    "sample_image_name": os.path.basename(sample_pic_path),
                },
                parent_id=context.message_id,
            )

        except Exception as e:
            return ProcessResult.error_result(f"富文本指令处理失败: {str(e)}")

    def sample_image(self, context: MessageContext) -> ProcessResult:
        """处理图片/壁纸指令"""
        try:
            # 获取示例图片路径
            sample_pic_path = os.getenv("SAMPLE_PIC_PATH", "")

            if not sample_pic_path or not os.path.exists(sample_pic_path):
                return ProcessResult.error_result("示例图片不存在")

            # 读取图片文件
            with open(sample_pic_path, "rb") as f:
                image_data = f.read()

            return ProcessResult.success_result(
                ResponseTypes.IMAGE,
                {
                    "image_data": image_data,
                    "image_name": os.path.basename(sample_pic_path),
                },
                parent_id=context.message_id,
            )

        except Exception as e:
            return ProcessResult.error_result(f"图片指令处理失败: {str(e)}")

    # endregion

    # region STT输入模块

    @require_service("audio", "音频服务未启动")
    @safe_execute("音频消息处理失败")
    def handle_audio_message(self, context: MessageContext) -> ProcessResult:
        """处理音频消息 - 立即返回处理提示，触发异步STT处理"""

        # 从 context 中获取音频文件信息
        audio_content = context.content

        if "file_key" not in audio_content:
            return ProcessResult.error_result("音频消息格式错误，缺少file_key")

        # 立即返回处理提示，触发异步处理
        return ProcessResult.async_result(
            ProcessResultNextAction.PROCESS_AUDIO_STT,
            "正在识别语音指令，请稍候",
            reply_message_type="card",  # 设置回复消息类型，为后续卡片切换预留
        )

    @require_service("audio", "音频服务未启动")
    @safe_execute("音频STT异步处理失败")
    def process_audio_stt_async(
        self, file_bytes: bytes, user_id: str, timestamp: datetime
    ) -> ProcessResult:
        """
        异步处理音频STT转写

        Args:
            file_bytes: 文件字节流
            user_id: 用户ID
            timestamp: 消息时间戳

        Returns:
            ProcessResult: 处理结果
        """

        # 获取音频服务
        audio_service = self.app_controller.get_service(ServiceNames.AUDIO)

        # 记录开始时间
        # 哪怕是一开始的时间戳也有before>context的异常情况，这个先不深究了，把代码清理一下move to next
        routine_business = RoutineRecord(self.app_controller)
        event_data = routine_business.load_event_definitions(user_id)
        event_name = event_data.get("definitions", {}).keys()
        if event_name:
            prompt = (
                "如果识别结果与以下事件名称发音相似，"
                f"请直接返回事件名称：\n{'、'.join(event_name)}。\n"
            )
        else:
            prompt = ""

        # ========= 拼音匹配准备 =========
        MATCH_TYPES = {
            "EXACT": "全文匹配",
            "PINYIN": "全拼匹配",
            "UNMATCHED": "无法匹配",
            "NORMAL_TEXT": "正常识别",
        }

        definitions = event_data.get("definitions", {})

        # 拼音触发阈值：所有事件名的最大长度 + 2
        max_event_len = max((len(name) for name in definitions.keys()), default=0)
        pinyin_threshold = max_event_len + 2

        def _classify_stt(raw_text: str):
            """精确匹配STT结果"""
            if not raw_text or not raw_text.strip():
                return MATCH_TYPES["UNMATCHED"], None

            text = raw_text.strip()

            # 全文匹配
            for event_name in definitions.keys():
                if text == event_name:
                    return MATCH_TYPES["EXACT"], event_name

            # 长文本直接返回正常识别
            if len(text) > pinyin_threshold:
                return MATCH_TYPES["NORMAL_TEXT"], None

            # 拼音匹配（仅对短文本）
            stt_phonetics = extract_phonetics(text)
            stt_full_list = stt_phonetics.get("pinyin_full_list", [])

            for event_name, event_def in definitions.items():
                event_full_list = event_def.get("pinyin_full_list", [])

                # 精确拼音匹配
                if stt_full_list and event_full_list:
                    if any(
                        stt_pinyin in event_full_list for stt_pinyin in stt_full_list
                    ):
                        return MATCH_TYPES["PINYIN"], event_name

            return MATCH_TYPES["UNMATCHED"], None

        # ========= 准备结束 =========

        # STT 服务配置：按优先级排序（先 deepgram，后 groq）
        stt_services = [
            {
                "name": "Deepgram",
                "method": audio_service.transcribe_audio_with_deepgram,
                "args": (file_bytes, "audio.ogg"),
                "kwargs": {},
                "start_time": None,
                "end_time": None,
                "duration": None,
                "success": False,
                "text": "",
                "match_type": MATCH_TYPES["UNMATCHED"],
                "matched_event": None,
            },
            {
                "name": "Groq",
                "method": audio_service.transcribe_audio_with_groq,
                "args": (file_bytes,),
                "kwargs": {"prompt": prompt, "filename_hint": "audio.ogg"},
                "start_time": None,
                "end_time": None,
                "duration": None,
                "success": False,
                "text": "",
                "match_type": MATCH_TYPES["UNMATCHED"],
                "matched_event": None,
            },
        ]

        # 循环调用 STT 服务，直到找到匹配结果或所有服务都尝试完
        final_result = None
        for service_config in stt_services:
            # 记录开始时间
            service_config["start_time"] = time.time()

            # 调用 STT 服务
            service_config["success"], service_config["text"] = service_config[
                "method"
            ](*service_config["args"], **service_config["kwargs"])

            # 记录结束时间和耗时
            service_config["end_time"] = time.time()
            service_config["duration"] = (
                service_config["end_time"] - service_config["start_time"]
            )

            if service_config["success"]:
                # 分析匹配结果
                service_config["match_type"], service_config["matched_event"] = (
                    _classify_stt(service_config["text"])
                )

                # 如果找到匹配结果，直接使用，不再尝试下一个服务
                if service_config["match_type"] in [
                    MATCH_TYPES["EXACT"],
                    MATCH_TYPES["PINYIN"],
                ]:
                    final_result = service_config
                    break
            else:
                # 如果服务调用失败，继续尝试下一个
                continue

        # 如果没有找到匹配结果，使用最后一个成功的服务结果
        if not final_result:
            for service_config in reversed(stt_services):
                if service_config["success"]:
                    final_result = service_config
                    break

        # 构建结果文本
        result_text = "🎵 语音识别结果:\n\n"

        if final_result:
            service_name = final_result["name"]
            result_text += (
                f"📊 by {service_name} (耗时: {final_result['duration']:.2f}s):\n"
            )
            result_text += f"✅ {final_result['text']}\n"

            match final_result["match_type"]:
                case "全文匹配" | "全拼匹配":
                    result_text += f"🔎 匹配类型: {final_result['match_type']} → 事件: {final_result['matched_event']}\n\n"
                    if final_result["match_type"] == "全拼匹配":
                        result_text += f"📝 说明：STT识别为『{final_result['text']}』，根据拼音匹配到事件『{final_result['matched_event']}』\n\n"

                    record_data = routine_business.load_event_records(user_id)
                    active_records = record_data.get("active_records", {})
                    active_record_data = {}
                    for record in active_records.values():
                        if record.get("event_name") == final_result["matched_event"]:
                            active_record_data = record
                            break

                    if active_record_data:
                        business_data = routine_business.build_record_business_data(
                            user_id,
                            final_result["matched_event"],
                            record_mode=RoutineRecordModes.EDIT,
                            current_record_data=active_record_data,
                        )

                    else:
                        business_data = routine_business.build_record_business_data(
                            user_id, final_result["matched_event"]
                        )

                    route_result = RouteResult.create_route_result(
                        route_type=RouteTypes.ROUTINE_RECORD_CARD,
                        route_params={
                            "business_data": business_data,
                        },
                    )
                    return route_result
                case "正常识别":
                    # 可以在这里引入llm的router处理，回复做完发回去，然后配音在外面调用。这样就需要增加一个组件了。
                    # 姑且先跑一个记录+多反思的结构？那一开始的组件就需要至少两个=w=。。。
                    # 至少1级路由应该用groq，不然多级了顶不住。
                    # 先不弄流式，就是先跑通
                    # 今天到跑通常规的流式回复
                    # 语音没办法承载未来茫茫多的router，而且先跑通，就用语音自己router一下好了
                    result_text += f"🔎 匹配类型: {final_result['match_type']}\n\n"
                    llm_service = self.app_controller.get_service(ServiceNames.LLM)
                    router_result = llm_service.process_stt_input(
                        final_result["text"], user_id
                    )
                    return router_result

                case _:
                    result_text += f"🔎 匹配类型: {final_result['match_type']}\n\n"

            # 生成安全文件名
            safe_filename = "".join(
                c for c in final_result["text"] if c.isalnum() or c in (" ", "-", "_")
            ).rstrip()[:50]
        else:
            result_text += "❌ 所有 STT 服务都失败了\n\n"
            safe_filename = ""

        # 保存音频：只有在没有全文匹配时才保存
        should_save_audio = (
            not final_result or final_result["match_type"] != MATCH_TYPES["EXACT"]
        )

        if safe_filename and should_save_audio:
            audio_file_path = f"cache/voice_{safe_filename}.ogg"
            try:
                with open(audio_file_path, "wb") as f:
                    f.write(file_bytes)
                print(f"原始音频已保存: {audio_file_path}")
            except Exception as save_error:
                print(f"保存音频文件失败: {save_error}")

        return ProcessResult.success_result(
            ResponseTypes.TEXT,
            {"text": result_text},
        )

    # endregion
