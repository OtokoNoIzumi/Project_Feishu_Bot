import asyncio
import hashlib
import json
import logging
import mimetypes
import os
import tempfile
import time
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import PIL.Image
from google import genai
from google.genai import types

from libs.api_keys.api_key_manager import APIKeyManager

logger = logging.getLogger(__name__)


@dataclass
class GeminiClientConfig:
    model_name: str
    temperature: float = 0.2


class GeminiFilesCache:
    """
    简易的文件缓存管理器，用于 Gemini Files API。
    记录 SHA256 -> Gemini File URI 的映射，并处理过期（48小时）。
    为了支持多 Key，Key 必须与 API Key 的特征绑定。
    """

    def __init__(self, cache_file: str = "user_data/.gemini_files_cache.json"):
        self.cache_file = cache_file
        self.cache: Dict[str, Dict[str, Any]] = {}
        self._load_cache()

    def _load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load gemini cache: {e}")
                self.cache = {}
        else:
            # Ensure dir exists
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)

    def _save_cache(self):
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save gemini cache: {e}")

    def get(self, file_hash: str, api_key_suffix: str) -> Optional[Dict[str, Any]]:
        """
        获取缓存。如果 Key 不匹配或已过期，返回 None 并清理。
        """
        item = self.cache.get(file_hash)
        if not item:
            return None

        # Check API Key binding (Files are private to the key's project)
        if item.get("key_suffix") != api_key_suffix:
            return None

        # Check expiration (buffer 5 mins)
        if time.time() > item.get("expiration_time", 0) - 300:
            self.delete(file_hash)
            return None

        return item

    def set(self, file_hash: str, api_key_suffix: str, gemini_file: types.File):
        """
        更新缓存。Gemini Files 默认有效期 48 小时。
        """
        # Calculate expiration: now + 47.5 hours (conservative)
        expiration = int(time.time() + 47.5 * 3600)
        
        self.cache[file_hash] = {
            "key_suffix": api_key_suffix,
            "name": gemini_file.name,
            "uri": gemini_file.uri,
            "mime_type": gemini_file.mime_type,
            "expiration_time": expiration
        }
        self._save_cache()

    def delete(self, file_hash: str):
        if file_hash in self.cache:
            del self.cache[file_hash]
            self._save_cache()


class GeminiStructuredClient:
    """
    Updated Gemini Client using `google-genai` SDK and Files API.
    """

    def __init__(self, api_key_manager: APIKeyManager, config: GeminiClientConfig):
        self.api_key_manager = api_key_manager
        self.config = config
        self.current_api_key: Optional[str] = None
        self.client: Optional[genai.Client] = None
        self.file_cache = GeminiFilesCache()
        self._init_client()

    @property
    def client_ready(self) -> bool:
        return self.client is not None

    def _init_client(self) -> None:
        self.client = None
        self.current_api_key = None

        api_key = self.api_key_manager.get_key()
        if not api_key:
            return

        try:
            self.client = genai.Client(api_key=api_key)
            self.current_api_key = api_key
        except Exception as e:
            logger.error("Gemini client init failed: %s", e)
            self.api_key_manager.mark_failed(api_key)
            self.client = None

    def _get_api_key_suffix(self) -> str:
        if self.current_api_key:
            return self.current_api_key[-6:]
        return "unknown"

    async def _upload_bytes_if_needed(self, image_bytes: bytes, mime_type: str = "image/png") -> types.File:
        """
        Upload logic with caching.
        """
        file_hash = hashlib.sha256(image_bytes).hexdigest()
        key_suffix = self._get_api_key_suffix()

        # 1. Check Cache
        cached = self.file_cache.get(file_hash, key_suffix)
        if cached:
            # Return a File object constructed from cache info
            # Note: We don't verify if it really exists on server to save one RTT.
            # If it fails later, the error handler should invalidate cache.
            logger.debug(f"Using cached Gemini file: {cached['name']}")
            return types.File(
                name=cached["name"],
                uri=cached["uri"],
                mime_type=cached["mime_type"]
            )

        # 2. Upload
        logger.debug(f"Uploading new file to Gemini: hash={file_hash[:8]}")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp: # Assuming PNG for bytes usually
            tmp.write(image_bytes)
            tmp_path = tmp.name

        try:
            # We use `await asyncio.to_thread` because `files.upload` might be synchronous IO
            # The new SDK might have an async upload? client.aio.files.upload?
            # Checking docs: client.files.upload is sync.
            # Let's wrap it.
            
            def _sync_upload():
                return self.client.files.upload(file=tmp_path, config={"mime_type": mime_type})

            uploaded_file = await asyncio.to_thread(_sync_upload)
            
            # 3. Update Cache
            self.file_cache.set(file_hash, key_suffix, uploaded_file)
            return uploaded_file

        finally:
            # Cleanup temp file
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except:
                    pass

    def _handle_auth_error(self, error: Exception) -> None:
        msg = str(error)
        is_auth_error = "API key" in msg or "authentication" in msg.lower() or "403" in msg
        if is_auth_error and self.current_api_key:
            logger.warning(f"Auth error detected ({msg}), marking key as failed.")
            self.api_key_manager.mark_failed(self.current_api_key)
            self._init_client()

    async def generate_json_async(self, prompt: str, images: List[bytes], schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Async generation with Files API support.
        Args:
            images: List[bytes]. NOW we accept bytes directly, not PIL.Image.
        """
        if not self.client_ready:
            self._init_client()
            if not self.client_ready:
                return {"error": "Gemini 客户端不可用（无可用 API Key 或初始化失败）"}

        try:
            # 1. Prepare Contents
            contents = [prompt]
            
            # Upload images concurrently
            if images:
                upload_tasks = [self._upload_bytes_if_needed(b) for b in images]
                uploaded_files = await asyncio.gather(*upload_tasks)
                contents.extend(uploaded_files)

            # 2. Generate
            # Using new SDK structure: client.aio.models.generate_content
            response = await self.client.aio.models.generate_content(
                model=self.config.model_name,
                contents=contents,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": schema,
                    "temperature": self.config.temperature,
                },
            )

            # 3. Parse
            if hasattr(response, "parsed") and response.parsed:
                 return response.parsed
            
            text = getattr(response, "text", "")
            if not text:
                return {"error": "响应为空"}
            
            # Basic cleanup if not automatically parsed
            if text.startswith("```json"):
                text = text[7:-3].strip()
            elif text.startswith("```"):
                text = text[3:-3].strip()
            
            return json.loads(text)

        except Exception as e:
            self._handle_auth_error(e)
            return {"error": f"Gemini 异步调用失败: {e}"}

    # --- Backward Compatibility (Sync Logic is simplified or deprecated) ---
    # Since existing logic heavily relies on async, we focus on async.
    # If synchronous usage is needed, we should implement it similarly or wrap async.
