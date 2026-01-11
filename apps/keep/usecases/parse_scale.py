import base64
from typing import Any, Dict, List

from libs.api_keys.api_key_manager import get_default_api_key_manager
from libs.llm_gemini.gemini_client import GeminiClientConfig, GeminiStructuredClient

from apps.keep.llm_schema_scale import KEEP_SCALE_LLM_SCHEMA
from apps.keep.postprocess_scale import finalize_scale_event
from apps.keep.prompt_builder_scale import build_keep_scale_prompt


def _decode_images_b64(images_b64: List[str]) -> List[bytes]:
    out: List[bytes] = []
    for s in images_b64 or []:
        if not s:
            continue
        try:
            out.append(base64.b64decode(s))
        except Exception:
            continue
    return out


class KeepScaleParseUsecase:
    def __init__(self, gemini_model_name: str):
        self.api_keys = get_default_api_key_manager()
        self.client = GeminiStructuredClient(
            api_key_manager=self.api_keys,
            config=GeminiClientConfig(model_name=gemini_model_name, temperature=0.1),
        )

    async def execute_async(
        self, user_note: str, images_b64: List[str]
    ) -> Dict[str, Any]:
        images_bytes = _decode_images_b64(images_b64)
        return await self.execute_with_image_bytes_async(
            user_note=user_note, images_bytes=images_bytes
        )

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
