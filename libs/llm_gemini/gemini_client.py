import json
import logging
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Dict, List, Optional

import PIL.Image
from google import genai

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
        self.client: Optional[genai.Client] = None
        self._init_client()

    @property
    def client_ready(self) -> bool:
        return self.client is not None

    def _init_client(self) -> None:
        """初始化客户端，如果获取不到 Key 则 client 保持为 None"""
        self.client = None
        self.current_api_key = None

        api_key = self.api_key_manager.get_key()
        if not api_key:
            return

        try:
            # 使用 genai.Client 模式（支持 client.aio）
            self.client = genai.Client(api_key=api_key)
            self.current_api_key = api_key
        except Exception as e:
            logger.error("Gemini client init failed: %s", e)
            self.api_key_manager.mark_failed(api_key)
            self.client = None

    @staticmethod
    def load_images_from_bytes(images: List[bytes]) -> List[PIL.Image.Image]:
        out: List[PIL.Image.Image] = []
        for b in images or []:
            try:
                out.append(PIL.Image.open(BytesIO(b)))
            except Exception:
                continue
        return out

    def _build_generation_config(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """构造生成配置（公共逻辑）"""
        return {
            "response_mime_type": "application/json",
            "response_schema": schema,
            "temperature": self.config.temperature,
        }

    def _build_contents(self, prompt: str, images: List[PIL.Image.Image]) -> List[Any]:
        """构造请求内容（公共逻辑）"""
        contents: List[Any] = [prompt]
        if images:
            contents.extend(images)
        return contents

    def _clean_json_text(self, text: str) -> str:
        """去除可能存在的 Markdown 代码块标记"""
        pattern = r"^```(?:json)?\s*(.*?)\s*```$"
        match = re.search(pattern, text, re.DOTALL | re.MULTILINE)
        if match:
            return match.group(1)
        return text

    def _parse_response(self, response: Any) -> Dict[str, Any]:
        """解析响应（公共逻辑），增强鲁棒性"""
        if hasattr(response, "parsed") and response.parsed is not None:
             return response.parsed
             
        text = ""
        if hasattr(response, "text"):
            text = response.text
        
        if not text:
             return {"error": "无法解析 Gemini 响应：内容为空"}

        try:
            cleaned_text = self._clean_json_text(text)
            return json.loads(cleaned_text)
        except json.JSONDecodeError as e:
            return {"error": f"Gemini JSON 解析失败: {e}\n原始返回: {text[:200]}..."}

    def _handle_auth_error(self, error: Exception) -> None:
        """处理认证错误：标记 Key 失败并尝试重新初始化"""
        msg = str(error)
        is_auth_error = "API key" in msg or "authentication" in msg.lower() or "403" in msg
        
        if is_auth_error and self.current_api_key:
            logger.warning(f"Auth error detected ({msg}), marking key as failed.")
            self.api_key_manager.mark_failed(self.current_api_key)
            self._init_client()

    def generate_json(self, prompt: str, images: List[PIL.Image.Image], schema: Dict[str, Any]) -> Dict[str, Any]:
        """同步版本（保留向后兼容）"""
        if not self.client_ready:
            self._init_client()
            if not self.client_ready:
                return {"error": "Gemini 客户端不可用（无可用 API Key 或初始化失败）"}

        try:
            response = self.client.models.generate_content(
                model=self.config.model_name,
                contents=self._build_contents(prompt, images),
                config=self._build_generation_config(schema),
            )
            return self._parse_response(response)

        except Exception as e:
            self._handle_auth_error(e)
            return {"error": f"Gemini 调用失败: {e}"}

    async def generate_text_async(
        self, prompt: str, images: List[PIL.Image.Image] = None, max_tokens: int = 1500
    ) -> str:
        """异步文本生成（不带 schema，返回自然文本）"""
        if not self.client_ready:
            self._init_client()
            if not self.client_ready:
                return "Gemini 客户端不可用（无可用 API Key 或初始化失败）"

        try:
            response = await self.client.aio.models.generate_content(
                model=self.config.model_name,
                contents=self._build_contents(prompt, images or []),
                config={
                    "temperature": self.config.temperature,
                    "max_output_tokens": max_tokens,
                },
            )
            if hasattr(response, "text"):
                return response.text
            return "无法解析 Gemini 响应格式"

        except Exception as e:
            self._handle_auth_error(e)
            return f"Gemini 异步调用失败: {e}"

    async def generate_json_async(self, prompt: str, images: List[PIL.Image.Image], schema: Dict[str, Any]) -> Dict[str, Any]:
        """异步版本（使用 client.aio 原生异步 API）"""
        if not self.client_ready:
            self._init_client()
            if not self.client_ready:
                return {"error": "Gemini 客户端不可用（无可用 API Key 或初始化失败）"}

        try:
            response = await self.client.aio.models.generate_content(
                model=self.config.model_name,
                contents=self._build_contents(prompt, images),
                config=self._build_generation_config(schema),
            )
            return self._parse_response(response)

        except Exception as e:
            self._handle_auth_error(e)
            return {"error": f"Gemini 异步调用失败: {e}"}


