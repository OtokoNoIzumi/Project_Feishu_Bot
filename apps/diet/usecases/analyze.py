import base64
from typing import Any, Dict, List

from libs.api_keys.api_key_manager import APIKeyManager
from libs.llm_gemini.gemini_client import GeminiClientConfig, GeminiStructuredClient

from apps.diet.llm_schema import DIET_LLM_SCHEMA
from apps.diet.prompt_builder import build_diet_prompt
from apps.diet.postprocess import finalize_record


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


class DietAnalyzeUsecase:
    def __init__(self, gemini_model_name: str):
        self.api_keys = APIKeyManager()
        self.client = GeminiStructuredClient(
            api_key_manager=self.api_keys,
            config=GeminiClientConfig(model_name=gemini_model_name, temperature=0.2),
        )

    def execute(self, user_note: str, images_b64: List[str]) -> Dict[str, Any]:
        """同步版本（保留向后兼容）"""
        images_bytes = _decode_images_b64(images_b64)
        return self.execute_with_image_bytes(user_note=user_note, images_bytes=images_bytes)

    def execute_with_image_bytes(self, user_note: str, images_bytes: List[bytes]) -> Dict[str, Any]:
        """同步版本（保留向后兼容）"""
        images = self.client.load_images_from_bytes(images_bytes)
        prompt = build_diet_prompt(user_note=user_note)
        llm_result = self.client.generate_json(prompt=prompt, images=images, schema=DIET_LLM_SCHEMA)
        if isinstance(llm_result, dict) and llm_result.get("error"):
            return {"error": llm_result.get("error")}
        return finalize_record(llm_result)

    async def execute_async(self, user_note: str, images_b64: List[str]) -> Dict[str, Any]:
        """异步版本（用于 FastAPI 异步接口）"""
        images_bytes = _decode_images_b64(images_b64)
        return await self.execute_with_image_bytes_async(user_note=user_note, images_bytes=images_bytes)

    async def execute_with_image_bytes_async(self, user_note: str, images_bytes: List[bytes]) -> Dict[str, Any]:
        """异步版本（用于 FastAPI 异步接口）"""
        images = self.client.load_images_from_bytes(images_bytes)
        prompt = build_diet_prompt(user_note=user_note)
        llm_result = await self.client.generate_json_async(prompt=prompt, images=images, schema=DIET_LLM_SCHEMA)
        if isinstance(llm_result, dict) and llm_result.get("error"):
            return {"error": llm_result.get("error")}
        return finalize_record(llm_result)


