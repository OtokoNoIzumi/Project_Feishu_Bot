import base64
from typing import Any, Dict, List

from libs.api_keys.api_key_manager import get_default_api_key_manager
from libs.llm_gemini.gemini_client import GeminiClientConfig, GeminiStructuredClient

from apps.keep.llm_schema_unified import KEEP_UNIFIED_LLM_SCHEMA
from apps.keep.prompt_builder_unified import build_keep_unified_prompt


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


class KeepUnifiedParseUsecase:
    def __init__(self, gemini_model_name: str):
        self.api_keys = get_default_api_key_manager()
        self.client = GeminiStructuredClient(
            api_key_manager=self.api_keys,
            config=GeminiClientConfig(model_name=gemini_model_name, temperature=0.1),
        )

    async def execute_async(self, user_note: str, images_b64: List[str]) -> Dict[str, Any]:
        images_bytes = _decode_images_b64(images_b64)
        return await self.execute_with_image_bytes_async(user_note=user_note, images_bytes=images_bytes)

    async def execute_with_image_bytes_async(self, user_note: str, images_bytes: List[bytes]) -> Dict[str, Any]:
        if not images_bytes:
            return {"error": "No images provided"}


        prompt = build_keep_unified_prompt(user_note=user_note)
        
        # 使用统一 Schema 进行混合解析
        llm_result = await self.client.generate_json_async(prompt=prompt, images=images_bytes, schema=KEEP_UNIFIED_LLM_SCHEMA)
        
        if isinstance(llm_result, dict) and llm_result.get("error"):
            return {"error": llm_result.get("error")}
        
        # 这里不需要 finalize_scale_event，因为 unified 返回的是 list，保持原样即可
        # 如果需要对 scale_events 里的每一项做 postprocess，可以遍历处理
        # 暂时先原样返回
        return llm_result
