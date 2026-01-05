import json
import logging
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
        self.client: Optional[Any] = None
        self.client_ready: bool = False
        self._init_client()

    def _init_client(self) -> None:
        api_key = self.api_key_manager.get_key()
        if not api_key:
            self.client_ready = False
            return
        try:
            # 使用 genai.Client 模式（支持 client.aio）
            self.client = genai.Client(api_key=api_key)
            self.current_api_key = api_key
            self.client_ready = True
        except Exception as e:
            logger.error("Gemini client init failed: %s", e)
            self.api_key_manager.mark_failed(api_key)
            self.current_api_key = None
            self.client = None
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

    def _parse_response(self, response: Any) -> Dict[str, Any]:
        """解析响应（公共逻辑）"""
        if hasattr(response, "text"):
            return json.loads(response.text)
        elif hasattr(response, "parsed"):
            return response.parsed
        else:
            return {"error": "无法解析 Gemini 响应格式"}

    def _handle_auth_error(self, reset_client: bool = False) -> None:
        """处理认证错误（公共逻辑）"""
        if self.current_api_key:
            self.api_key_manager.mark_failed(self.current_api_key)
        if reset_client:
            self.client = None
        self.client_ready = False
        self._init_client()

    def generate_json(self, prompt: str, images: List[PIL.Image.Image], schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        同步版本（保留向后兼容）

        注意：同步版本使用 genai.Client，但调用同步方法（非 aio）
        """
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

        except json.JSONDecodeError as e:
            return {"error": f"Gemini JSON 解析失败: {e}"}
        except Exception as e:
            msg = str(e)
            if "API key" in msg or "authentication" in msg.lower():
                self._handle_auth_error(reset_client=False)
            return {"error": f"Gemini 调用失败: {e}"}

    async def generate_json_async(self, prompt: str, images: List[PIL.Image.Image], schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        异步版本（使用 client.aio 原生异步 API）

        对齐 BiliTools 的 call_gemini_with_retry 逻辑
        用于 FastAPI 异步接口，支持高并发

        API Key 管理逻辑：
        1. 初始化时：从 api_key_manager 获取 key，创建 genai.Client(api_key=key)
        2. 调用时：如果 client 未就绪，重新初始化（可能获取到新 key）
        3. 认证失败时：
           - 标记当前 key 为失败（api_key_manager.mark_failed()）
           - 重新初始化 client（_init_client() 会从 api_key_manager 获取新 key）
           - 如果重新初始化成功，下次调用会自动使用新 key
           - 如果所有 key 都失败，client_ready 保持 False，下次调用会再次尝试初始化
        """
        if not self.client_ready:
            self._init_client()
            if not self.client_ready:
                return {"error": "Gemini 客户端不可用（无可用 API Key 或初始化失败）"}

        try:
            # 【关键】使用 client.aio 原生异步接口
            response = await self.client.aio.models.generate_content(
                model=self.config.model_name,
                contents=self._build_contents(prompt, images),
                config=self._build_generation_config(schema),
            )
            return self._parse_response(response)

        except json.JSONDecodeError as e:
            return {"error": f"Gemini JSON 解析失败: {e}"}
        except Exception as e:
            msg = str(e)
            if "API key" in msg or "authentication" in msg.lower():
                self._handle_auth_error(reset_client=True)
            return {"error": f"Gemini 异步调用失败: {e}"}


