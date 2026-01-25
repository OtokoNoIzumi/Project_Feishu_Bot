"""
Keep Sleep Parse Usecase.
"""

from typing import Any, Dict, List

from apps.keep.llm_schema_sleep import KEEP_SLEEP_LLM_SCHEMA
from apps.keep.prompt_builder_sleep import build_keep_sleep_prompt
from apps.keep.usecases.base import KeepBaseParseUsecase


class KeepSleepParseUsecase(KeepBaseParseUsecase):
    """Usecase for parsing Keep sleep screenshots."""

    def __init__(self, gemini_model_name: str):
        super().__init__(gemini_model_name, temperature=0.1)

    async def execute_with_image_bytes_async(
        self, 
        user_note: str, 
        images_bytes: List[bytes],
        scene: str = "unknown", 
        user_id: str = "unknown"
    ) -> Dict[str, Any]:

        prompt = build_keep_sleep_prompt(user_note=user_note)

        # 暂时不进行复杂的后处理，直接返回 LLM 结果，后续可增加 finalize_sleep_event
        llm_result = await self.client.generate_json_async(
            prompt=prompt, 
            images=images_bytes, 
            schema=KEEP_SLEEP_LLM_SCHEMA,
            scene=scene,
            user_id=user_id
        )

        if isinstance(llm_result, dict) and llm_result.get("error"):
            return {"error": llm_result.get("error")}
        return llm_result
