"""
文本消息处理器

处理基础的文本指令，如帮助、问候等
"""

from .base_processor import BaseProcessor, MessageContext, ProcessResult
from .temp_move_module import TempMoveModule
from Module.Services.constants import ServiceNames, ResponseTypes


class TextProcessor(BaseProcessor):
    """
    文本消息处理器

    处理基础的文本指令和默认回复
    """

    def get_help(self, context: MessageContext) -> ProcessResult:
        """处理帮助指令"""
        help_text = """<b>🤖 飞书机器人助手 v3.1</b>

<b>核心功能：</b>

<b>🔊 AI配音</b>
• 配音 [文本内容] → 生成高质量中文语音消息

<b>🎨 AI绘图</b>
• 生图 [描述] → AI生成图片
• AI画图 [描述] → AI生成图片
• 直接发送图片 → 自动转换为精美贺卡风格

<b>🖼️ 图片处理</b>
• 上传图片 → 自动转换为精美贺卡风格
• 图片/壁纸 → 分享精美示例图片

<b>📺 B站推荐系统</b>
• 菜单"B站" → 个性化视频推荐（1+3模式，支持已读标记）
• B站/视频 → 快速获取视频推荐
• 支持优先级排序、时长分布、来源统计

<b>📄 富文本演示</b>
• 富文本 → 展示富文本格式示例

<b>📅 定时功能</b>
• 每天07:30 → 自动推送信息汇总（包含B站数据分析）
• 每天15:30和23:55 → 自动推送B站更新
• 夜间静默模式 → 22:00-08:00处理但不通知

<b>💬 基础交互</b>
• 帮助 → 查看功能列表
• 你好 → 问候回复

<b>⚙️ 管理功能（管理员专用）</b>
• whisk令牌 [变量名] [新值] → 更新认证配置（支持cookies、auth_token）
• 更新用户 [用户ID] [类型] → 用户状态管理
• 更新广告 [BVID] [时间戳] → B站广告信息更新

<i>使用示例：</i>
• 配音 你好，这是一段测试语音
• 生图 一只可爱的小猫在花园里玩耍
• AI画图 未来城市的科幻景观
• 富文本 → 查看富文本格式演示
• 图片 → 获取精美壁纸
• B站 → 快速视频推荐
• 直接发送图片 → 自动转换为贺卡风格
• 点击菜单"B站" → 获取个性化视频推荐

<i>系统架构优势：</i>
• 🏗️ 四层架构设计：Adapters→Business→Application→Services
• 🔄 统一服务管理，模块化媒体处理
• 📊 智能B站数据分析和推荐算法
• 🎯 支持富文本卡片交互和状态管理
• 🚀 可扩展的HTTP API和定时任务系统

<i>开发中功能：</i>
• 🔊 语音识别和上下文管理
• 🔗 链接读取和文档处理
• 🎮 游戏版本数据同步
• 📱 消息回复和评论识别优化"""

        return ProcessResult.success_result("text", {"text": help_text}, parent_id=context.message_id)

    def greeting(self, context: MessageContext) -> ProcessResult:
        """处理问候指令"""
        return ProcessResult.success_result("text", {
            "text": f"你好，{context.user_name}！有什么我可以帮你的吗？"
        }, parent_id=context.message_id)

    def default_reply(self, context: MessageContext) -> ProcessResult:
        """处理默认消息（未匹配到特定指令的文本）"""
        user_msg = context.content
        # 限制长度避免过长
        content = user_msg[:50] + "..." if len(user_msg) > 50 else user_msg
        self._log_command(context.user_name, "💬", "发送普通消息", content)
        return ProcessResult.success_result("text", {
            "text": f"收到你发送的消息：{user_msg}"
        }, parent_id=context.message_id)

    def temp_move_report(self, context: MessageContext) -> ProcessResult:
        """处理搬家报告指令（临时功能）"""
        self._log_command(context.user_name, "🏠", "生成搬家报告")

        if not self.app_controller:
            return ProcessResult.error_result("系统服务不可用")

        try:
            # 获取项目根路径
            config_service = self.app_controller.get_service(ServiceNames.CONFIG)
            project_root = config_service.project_root_path

            # 获取LLM服务
            llm_service = self.app_controller.get_service(ServiceNames.LLM)
            if not llm_service or not llm_service.is_available():
                return ProcessResult.error_result("LLM服务不可用")

            # 读取TOML配置
            toml_text = TempMoveModule.read_toml_text(project_root)

            # 生成报告
            report = TempMoveModule.generate_report(llm_service, toml_text)

            return ProcessResult.success_result("text", {
                "text": report
            }, parent_id=context.message_id)

        except Exception as e:
            return ProcessResult.error_result(f"生成搬家报告失败: {str(e)}")

    def temp_move_update(self, context: MessageContext, new_content: str) -> ProcessResult:
        """处理新家内容更新指令（临时功能）"""
        self._log_command(context.user_name, "🏠", "更新搬家项目信息", new_content[:50])

        if not self.app_controller:
            return ProcessResult.error_result("系统服务不可用")

        try:
            # 获取项目根路径
            config_service = self.app_controller.get_service(ServiceNames.CONFIG)
            project_root = config_service.project_root_path

            # 获取LLM服务
            llm_service = self.app_controller.get_service(ServiceNames.LLM)
            if not llm_service or not llm_service.is_available():
                return ProcessResult.error_result("LLM服务不可用")

            # 读取当前TOML配置（保存原始内容用于diff）
            toml_text = TempMoveModule.read_toml_text(project_root)

            # 合并新内容
            merged_toml, suggestions = TempMoveModule.merge_new_content(llm_service, toml_text, new_content)

            if merged_toml is None:
                return ProcessResult.error_result("合并内容失败，请稍后重试")

            # 写回文件
            success = TempMoveModule.write_toml_text(project_root, merged_toml)

            if success:
                # 生成富文本格式的差异报告（使用redline库）
                rich_text_content = TempMoveModule._generate_toml_diff_rich_text(
                    toml_text, merged_toml, new_content, suggestions
                )

                return ProcessResult.success_result(
                    ResponseTypes.RICH_TEXT,
                    {
                        "rich_text_content": rich_text_content
                    },
                    parent_id=context.message_id
                )
            else:
                return ProcessResult.error_result("保存更新失败")

        except Exception as e:
            return ProcessResult.error_result(f"更新搬家项目信息失败: {str(e)}")