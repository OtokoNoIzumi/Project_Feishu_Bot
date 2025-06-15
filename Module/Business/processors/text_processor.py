"""
文本消息处理器

处理基础的文本指令，如帮助、问候等
"""

from .base_processor import BaseProcessor, MessageContext, ProcessResult


class TextProcessor(BaseProcessor):
    """
    文本消息处理器

    处理基础的文本指令和默认回复
    """

    def handle_help_command(self, context: MessageContext) -> ProcessResult:
        """处理帮助指令"""
        help_text = """<b>🤖 飞书机器人助手 v3.0</b>

<b>核心功能：</b>

<b>🔊 AI配音</b>
• 配音 [文本内容] → 生成语音消息

<b>🎨 AI绘图</b>
• 生图 [描述] → AI生成图片
• AI画图 [描述] → AI生成图片

<b>🖼️ 图片处理</b>
• 上传图片 → 自动转换为精美贺卡风格
• 图片/壁纸 → 分享精美示例图片

<b>📺 B站推荐</b>
• 菜单"B站" → 个性化视频推荐（支持1+3模式显示）
• B站/视频 → 快速获取视频推荐

<b>📄 富文本演示</b>
• 富文本 → 展示富文本格式示例

<b>📅 定时功能</b>
• 每天07:30 → 自动推送B站信息汇总
• 每天15:30和23:55 → 自动推送B站更新

<b>💬 基础交互</b>
• 帮助 → 查看功能列表
• 你好 → 问候回复

<b>⚙️ 管理功能</b>
• whisk令牌 [变量名] [新值] → 更新配置（管理员专用）

<i>使用示例：</i>
• 配音 你好，这是一段测试语音
• 生图 一只可爱的小猫在花园里玩耍
• AI画图 未来城市的科幻景观
• 富文本 → 查看富文本格式演示
• 图片 → 获取精美壁纸
• B站 → 快速视频推荐
• 直接发送图片 → 自动转换为贺卡风格
• 点击菜单"B站" → 获取个性化视频推荐

<i>定时任务特性：</i>
• 📅 每天07:30自动发送B站信息汇总（包含推荐视频摘要）
• 📺 每天15:30和23:55自动推送B站更新
• 🎯 支持富文本卡片交互，可查看详细信息

<i>架构优势：统一的服务管理，模块化的媒体处理和B站数据分析</i>"""

        return ProcessResult.success_result("text", {"text": help_text}, parent_id=context.message_id)

    def handle_greeting_command(self, context: MessageContext) -> ProcessResult:
        """处理问候指令"""
        return ProcessResult.success_result("text", {
            "text": f"你好，{context.user_name}！有什么我可以帮你的吗？"
        }, parent_id=context.message_id)

    def handle_default_message(self, context: MessageContext) -> ProcessResult:
        """处理默认消息（未匹配到特定指令的文本）"""
        user_msg = context.content
        # 限制长度避免过长
        content = user_msg[:50] + "..." if len(user_msg) > 50 else user_msg
        self._log_command(context.user_name, "💬", "发送普通消息", content)
        return ProcessResult.success_result("text", {
            "text": f"收到你发送的消息：{user_msg}"
        }, parent_id=context.message_id)