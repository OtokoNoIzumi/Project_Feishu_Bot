"""
Keep Dimensions Parse Usecase.
"""

from typing import Any, Dict, List

from apps.keep.llm_schema_dimensions import KEEP_DIMENSIONS_LLM_SCHEMA
from apps.keep.prompt_builder_dimensions import build_keep_dimensions_prompt
from apps.keep.usecases.base import KeepBaseParseUsecase


class KeepDimensionsParseUsecase(KeepBaseParseUsecase):
    """Usecase for parsing Keep dimensions screenshots."""

    def __init__(self, gemini_model_name: str):
        super().__init__(gemini_model_name, temperature=0.1)

    async def execute_with_image_bytes_async(
        self, user_note: str, images_bytes: List[bytes]
    ) -> Dict[str, Any]:

        prompt = build_keep_dimensions_prompt(user_note=user_note)

        # 暂时不进行复杂的后处理
        llm_result = await self.client.generate_json_async(
            prompt=prompt, images=images_bytes, schema=KEEP_DIMENSIONS_LLM_SCHEMA
        )

        if isinstance(llm_result, dict) and llm_result.get("error"):
            return {"error": llm_result.get("error")}
        return llm_result
