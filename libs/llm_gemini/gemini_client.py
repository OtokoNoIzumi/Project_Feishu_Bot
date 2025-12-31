import json
import logging
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Dict, List, Optional

import PIL.Image
import google.generativeai as genai

from libs.api_keys.api_key_manager import APIKeyManager

logger = logging.getLogger(__name__)


@dataclass
class GeminiClientConfig:
    model_name: str
    temperature: float = 0.2


class GeminiStructuredClient:
    """
    Gemini 多模态 + 结构化输出封装（原子能力）

    约定：
    - 只负责“调用模型并按 schema 返回 JSON”
    - 不包含任何业务 prompt/schema
    """

    def __init__(self, api_key_manager: APIKeyManager, config: GeminiClientConfig):
        self.api_key_manager = api_key_manager
        self.config = config
        self.current_api_key: Optional[str] = None
        self.client_ready: bool = False
        self._init_client()

    def _init_client(self) -> None:
        api_key = self.api_key_manager.get_key()
        if not api_key:
            self.client_ready = False
            return
        try:
            genai.configure(api_key=api_key)
            self.current_api_key = api_key
            self.client_ready = True
        except Exception as e:
            logger.error("Gemini client init failed: %s", e)
            self.api_key_manager.mark_failed(api_key)
            self.current_api_key = None
            self.client_ready = False

    @staticmethod
    def load_images_from_bytes(images: List[bytes]) -> List[PIL.Image.Image]:
        out: List[PIL.Image.Image] = []
        for b in images or []:
            try:
                out.append(PIL.Image.open(BytesIO(b)))
            except Exception:
                continue
        return out

    def generate_json(self, prompt: str, images: List[PIL.Image.Image], schema: Dict[str, Any]) -> Dict[str, Any]:
        if not self.client_ready:
            self._init_client()
            if not self.client_ready:
                return {"error": "Gemini 客户端不可用（无可用 API Key 或初始化失败）"}

        try:
            model = genai.GenerativeModel(self.config.model_name)
            input_content: List[Any] = [prompt] + (images or [])
            generation_config = genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=schema,
                temperature=self.config.temperature,
            )
            response = model.generate_content(input_content, generation_config=generation_config)
            return json.loads(response.text)
        except json.JSONDecodeError as e:
            return {"error": f"Gemini JSON 解析失败: {e}"}
        except Exception as e:
            msg = str(e)
            if "API key" in msg or "authentication" in msg.lower():
                if self.current_api_key:
                    self.api_key_manager.mark_failed(self.current_api_key)
                self.client_ready = False
            return {"error": f"Gemini 调用失败: {e}"}


