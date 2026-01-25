"""
Keep Unified Parse Usecase.
"""

from typing import Any, Dict, List

from apps.keep.llm_schema_unified import build_keep_unified_llm_schema
from apps.keep.prompt_builder_unified import build_keep_unified_prompt
from apps.keep.usecases.base import KeepBaseParseUsecase


class KeepUnifiedParseUsecase(KeepBaseParseUsecase):
    """Usecase for parsing Unified Keep screenshots (mixed content)."""

    def __init__(self, gemini_model_name: str):
        super().__init__(gemini_model_name, temperature=0.1)

    async def execute_with_image_bytes_async(
        self,
        user_note: str,
        images_bytes: List[bytes],
        use_limited: bool = False,
        scene: str = "unknown", 
        user_id: str = "unknown"
    ) -> Dict[str, Any]:
        if not user_note and not images_bytes:
            return {"error": "No input provided (text or images required)."}

        prompt = build_keep_unified_prompt(
            user_note=user_note, use_limited=use_limited
        )
        schema = build_keep_unified_llm_schema(use_limited=use_limited)

        # 使用统一 Schema 进行混合解析
        llm_result = await self.client.generate_json_async(
            prompt=prompt, 
            images=images_bytes or [], 
            schema=schema,
            scene=scene,
            user_id=user_id
        )

        if isinstance(llm_result, dict) and llm_result.get("error"):
            return {"error": llm_result.get("error")}

        # 这里不需要 finalize_scale_event，因为 unified 返回的是 list，保持原样即可
        # 如果需要对 scale_events 里的每一项做 postprocess，可以遍历处理
        # 暂时先原样返回
        return llm_result
