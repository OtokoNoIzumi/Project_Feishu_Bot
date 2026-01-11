"""
Diet Analyze Usecase.

Analyzes diet records from images and user notes using Gemini LLM.
"""

from typing import Any, Dict, List

from libs.api_keys.api_key_manager import get_default_api_key_manager
from libs.llm_gemini.gemini_client import GeminiClientConfig, GeminiStructuredClient

from apps.common.utils import decode_images_b64
from apps.diet.llm_schema import DIET_LLM_SCHEMA
from apps.diet.prompt_builder import build_diet_prompt
from apps.diet.postprocess import finalize_record
from apps.diet.memory_service import get_product_memories


class DietAnalyzeUsecase:
    """Usecase for analyzing diet records."""

    def __init__(self, gemini_model_name: str):
        self.api_keys = get_default_api_key_manager()
        self.client = GeminiStructuredClient(
            api_key_manager=self.api_keys,
            config=GeminiClientConfig(model_name=gemini_model_name, temperature=0.2),
        )

    async def execute_async(
        self, user_note: str, images_b64: List[str]
    ) -> Dict[str, Any]:
        """异步版本（用于 FastAPI 异步接口）"""
        images_bytes = decode_images_b64(images_b64)
        return await self.execute_with_image_bytes_async(
            user_note=user_note, images_bytes=images_bytes
        )

    async def execute_with_image_bytes_async(
        self, user_note: str, images_bytes: List[bytes], user_id: str = ""
    ) -> Dict[str, Any]:
        """异步版本（用于 FastAPI 异步接口）"""

        # 获取产品记忆 (Decoupled from generic context)
        recent_products_str = ""
        if user_id:
            mems = get_product_memories(user_id)
            if mems:
                recent_products_str = "\n".join(mems)
        prompt = build_diet_prompt(
            user_note=user_note, recent_products_str=recent_products_str
        )

        llm_result = await self.client.generate_json_async(
            prompt=prompt, images=images_bytes, schema=DIET_LLM_SCHEMA
        )
        if isinstance(llm_result, dict) and llm_result.get("error"):
            return {"error": llm_result.get("error")}
        return finalize_record(llm_result)
