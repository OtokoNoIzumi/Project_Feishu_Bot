"""
Diet Advice Usecase.
"""

from typing import Any, Dict, Optional

from libs.api_keys.api_key_manager import get_default_api_key_manager
from libs.llm_gemini.gemini_client import GeminiClientConfig, GeminiStructuredClient

from apps.common.utils import parse_occurred_at
from apps.diet.context_provider import get_context_bundle
from apps.diet.prompt_builder_advice import build_diet_advice_prompt


class DietAdviceUsecase:
    """
    Usecase for generating diet advice.
    """

    # pylint: disable=too-few-public-methods

    def __init__(self, gemini_model_name: str):
        self.api_keys = get_default_api_key_manager()
        self.client = GeminiStructuredClient(
            api_key_manager=self.api_keys,
            config=GeminiClientConfig(model_name=gemini_model_name, temperature=0.4),
        )

    async def execute_async(
        self, user_id: str, facts: Dict[str, Any], user_note: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        advice 的输入只有3个数据：
        1. context（由 user_id 获取）：包含 target 和 today_so_far（不包含当前 analyze 的数据）
        2. facts（analyze 的完整结果）：包含营养成分和构成
        3. 用户直接输入：user_note + extra_image_summary（如果有）
        """
        # 0. 尝试从 facts 中提取发生时间，以便获取准确的上下文历史
        target_date_str = None
        occurred_at = facts.get("occurred_at")
        if occurred_at:
            dt = parse_occurred_at(occurred_at)
            if dt:
                target_date_str = dt.strftime("%Y-%m-%d")

        # 1. 获取 context（由 user_id 和可选的日期）
        context_bundle = get_context_bundle(user_id=user_id, target_date=target_date_str)

        # 2. facts 是 analyze 的完整结果（已传入）

        # 3. 组合用户直接输入：user_note + extra_image_summary
        extra_image_summary = facts.get("extra_image_summary") or ""
        user_input_parts = []
        if user_note and user_note.strip():
            user_input_parts.append(user_note.strip())
        if extra_image_summary and extra_image_summary.strip():
            user_input_parts.append(extra_image_summary.strip())
        combined_user_input = "\n".join(user_input_parts) if user_input_parts else ""

        prompt = build_diet_advice_prompt(
            facts=facts, context_bundle=context_bundle, user_input=combined_user_input
        )
        print("test-prompt", prompt)
        # 使用不带 schema 的文本生成
        # advice_text = ""
        advice_text = await self.client.generate_text_async(prompt=prompt, images=[])
        if advice_text.startswith("Gemini") and "失败" in advice_text:
            return {"error": advice_text}

        return {"advice_text": advice_text}
