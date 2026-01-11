"""
Keep Base Parse Usecase.

Abstract base class for Keep parsing usecases to reduce code duplication.
"""

from typing import Any, Dict, List

from libs.api_keys.api_key_manager import get_default_api_key_manager
from libs.llm_gemini.gemini_client import GeminiClientConfig, GeminiStructuredClient
from apps.common.utils import decode_images_b64


class KeepBaseParseUsecase:
    """Base class for Keep parsing logic."""

    def __init__(self, gemini_model_name: str, temperature: float = 0.1):
        self.api_keys = get_default_api_key_manager()
        self.client = GeminiStructuredClient(
            api_key_manager=self.api_keys,
            config=GeminiClientConfig(
                model_name=gemini_model_name, temperature=temperature
            ),
        )

    async def execute_async(
        self, user_note: str, images_b64: List[str]
    ) -> Dict[str, Any]:
        """Async execution with Base64 images."""
        images_bytes = decode_images_b64(images_b64)
        return await self.execute_with_image_bytes_async(
            user_note=user_note, images_bytes=images_bytes
        )

    async def execute_with_image_bytes_async(
        self, user_note: str, images_bytes: List[bytes]
    ) -> Dict[str, Any]:
        """
        Execute parsing with image bytes.
        Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement this method")
