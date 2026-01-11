"""
Keep Scale Parse Usecase.
"""

from typing import Any, Dict, List

from apps.keep.llm_schema_scale import KEEP_SCALE_LLM_SCHEMA
from apps.keep.postprocess_scale import finalize_scale_event
from apps.keep.prompt_builder_scale import build_keep_scale_prompt
from apps.keep.usecases.base import KeepBaseParseUsecase


class KeepScaleParseUsecase(KeepBaseParseUsecase):
    """Usecase for parsing Keep scale screenshots."""

    def __init__(self, gemini_model_name: str):
        super().__init__(gemini_model_name, temperature=0.1)

    async def execute_with_image_bytes_async(
        self, user_note: str, images_bytes: List[bytes]
    ) -> Dict[str, Any]:

        prompt = build_keep_scale_prompt(user_note=user_note)
        llm_result = await self.client.generate_json_async(
            prompt=prompt, images=images_bytes, schema=KEEP_SCALE_LLM_SCHEMA
        )
        if isinstance(llm_result, dict) and llm_result.get("error"):
            return {"error": llm_result.get("error")}
        return finalize_scale_event(llm_result)
