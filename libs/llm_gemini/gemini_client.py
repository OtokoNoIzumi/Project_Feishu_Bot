"""
Gemini Client.

Provides an async client for interacting with Google's Gemini models,
handling API key management, file uploading, and structured JSON generation.
"""

import asyncio
import hashlib
import json
import logging
import os
import tempfile
import datetime
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

from libs.api_keys.api_key_manager import APIKeyManager

logger = logging.getLogger(__name__)

# --- Stats Logger Setup ---
def setup_stats_logger():
    """配置专门的统计日志记录器 (JSONL)"""
    stats_log_dir = "user_data/logs"
    os.makedirs(stats_log_dir, exist_ok=True)
    stats_log_file = os.path.join(stats_log_dir, "gemini_stats.jsonl")
    
    s_logger = logging.getLogger("gemini_stats")
    s_logger.setLevel(logging.INFO)
    s_logger.propagate = False  # 不传给 root logger，避免重复
    
    if not s_logger.handlers:
        file_handler = logging.FileHandler(stats_log_file, encoding='utf-8')
        file_handler.setFormatter(logging.Formatter('%(message)s'))
        s_logger.addHandler(file_handler)
    
    return s_logger

stats_logger = setup_stats_logger()

def log_stat(data: Dict[str, Any]):
    """记录一条统计数据"""
    data["timestamp"] = datetime.datetime.now().isoformat()
    # 同时输出到控制台 (方便实时看) 和 文件 (方便持久化)
    logger.info(f"[GeminiStats] {json.dumps(data, ensure_ascii=False)}")
    stats_logger.info(json.dumps(data, ensure_ascii=False))
# --------------------------


@dataclass
class GeminiClientConfig:
    """Configuration for Gemini Client."""

    model_name: str
    temperature: float = 0.2
    advice_temperature: float = 0.8


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
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load gemini cache (resetting): %s", e)
                self.cache = {}
        else:
            # Ensure dir exists
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)

    def _save_cache(self):
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.warning("Failed to save gemini cache: %s", e)

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
            "expiration_time": expiration,
        }
        self._save_cache()

    def delete(self, file_hash: str):
        """Delete an item from cache."""
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
        """Check if client is initialized."""
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

    async def _upload_bytes_if_needed(
        self, image_bytes: bytes, mime_type: str = "image/png"
    ) -> tuple[types.File, bool]:
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
            logger.info("Using cached Gemini file: %s", cached["name"])
            file_obj = types.File(
                name=cached["name"], uri=cached["uri"], mime_type=cached["mime_type"]
            )
            return file_obj, True

        # 2. Upload
        logger.info("Uploading new file to Gemini: hash=%s", file_hash[:8])
        # Use tempfile securely
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".png")
        try:
            with os.fdopen(tmp_fd, "wb") as tmp:
                tmp.write(image_bytes)

            try:
                # We use `await asyncio.to_thread` because `files.upload` is synchronous IO
                def _sync_upload():
                    return self.client.files.upload(
                        file=tmp_path, config={"mime_type": mime_type}
                    )

                uploaded_file = await asyncio.to_thread(_sync_upload)

                # 3. Update Cache
                self.file_cache.set(file_hash, key_suffix, uploaded_file)
                return uploaded_file, False
            finally:
                pass  # Internal cleanup handled in outer finally
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    async def _prepare_contents_with_metrics(
        self, prompt: str, images: List[bytes], scene: str = "unknown", user_id: str = "unknown"
    ) -> tuple[List[Any], Dict[str, Any]]:
        """
        统一处理内容准备：并发上传图片（含 Metrics）+ 组装 Prompt。
        这是耗时操作（IO），应独立于 LLM 重试循环之外。
        """
        contents = [prompt]
        metrics = {
            "image_count": 0,
            "upload_duration_ms": 0,
            "cache_hits": 0,
            "new_uploads": 0
        }
        
        if not images:
            return contents, metrics

        metrics["image_count"] = len(images)
        start_time = time.time()
        
        try:
            upload_tasks = [self._upload_bytes_if_needed(b) for b in images]
            results = await asyncio.wait_for(
                asyncio.gather(*upload_tasks), timeout=60
            )
            
            # Unpack results: results is list of (File, bool)
            uploaded_files = [r[0] for r in results]
            hits = sum(1 for r in results if r[1])
            misses = len(results) - hits
            
            metrics["cache_hits"] = hits
            metrics["new_uploads"] = misses
            
            contents.extend(uploaded_files)
        except asyncio.TimeoutError:
            logger.error("[GeminiStats] Image upload timed out after 60s")
            raise  # 让上层处理
            
        metrics["upload_duration_ms"] = (time.time() - start_time) * 1000
        
        log_stat({
            "type": "Upload",
            "scene": scene,
            "user_id": user_id,
            "count": len(images),
            "cache_hits": metrics["cache_hits"],
            "new_uploads": metrics["new_uploads"],
            "duration_ms": metrics["upload_duration_ms"],
            "status": "Success"
        })
        return contents, metrics

    def _handle_auth_error(self, error: Exception) -> None:
        msg = str(error)
        is_auth_error = (
            "API key" in msg or "authentication" in msg.lower() or "403" in msg
        )
        if is_auth_error and self.current_api_key:
            logger.warning("Auth error detected (%s), marking key as failed.", msg)
            self.api_key_manager.mark_failed(self.current_api_key)
            self._init_client()

    async def generate_json_async(
        self, prompt: str, images: List[bytes], schema: Dict[str, Any], 
        scene: str = "unknown", user_id: str = "unknown"
    ) -> Dict[str, Any]:
        """
        Async generation with decoupled Upload and Generation phases.
        """
        if not self.client_ready:
            self._init_client()
            if not self.client_ready:
                return {"error": "Gemini 客户端不可用（无可用 API Key 或初始化失败）"}

        # Phase 1: Upload (Once)
        upload_start = time.time()
        try:
            contents, _ = await self._prepare_contents_with_metrics(prompt, images, scene, user_id)
        except Exception as e:
            return {"error": f"图片上传失败: {e}"}
        upload_duration = (time.time() - upload_start) * 1000

        # Phase 2: Generation (Retry Loop)
        max_retries = 3
        last_error = None
        retry_timeout = max(40, round((145-upload_duration)/max_retries))
        

        for attempt in range(1, max_retries + 1):
            try:
                gen_start = time.time()
                # Guard generation with 30s timeout
                response = await asyncio.wait_for(
                    self.client.aio.models.generate_content(
                        model=self.config.model_name,
                        contents=contents,
                        config={
                            "response_mime_type": "application/json",
                            "response_schema": schema,
                            "temperature": self.config.temperature,
                        },
                    ),
                    timeout=retry_timeout
                )
                gen_duration = (time.time() - gen_start) * 1000
                
                # Extract Token Usage
                usage_str = "N/A"
                if hasattr(response, "usage_metadata"):
                    in_tokens = getattr(response.usage_metadata, "prompt_token_count", 0)
                    out_tokens = getattr(response.usage_metadata, "candidates_token_count", 0)
                    usage_str = f"In:{in_tokens}|Out:{out_tokens}"

                log_stat({
                    "type": "Generate",
                    "scene": scene,
                    "user_id": user_id,
                    "model": self.config.model_name,
                    "duration_ms": gen_duration,
                    "attempt": attempt,
                    "max_retries": max_retries,
                    "tokens_in": getattr(response.usage_metadata, "prompt_token_count", 0) if hasattr(response, "usage_metadata") else 0,
                    "tokens_out": getattr(response.usage_metadata, "candidates_token_count", 0) if hasattr(response, "usage_metadata") else 0,
                    "image_count": len(images),
                    "status": "Success"
                })
                
                # Parse and Validate
                if hasattr(response, "parsed") and response.parsed:
                    return response.parsed

                text = getattr(response, "text", "")
                if not text:
                    debug_info = "Unknown"
                    if hasattr(response, "finish_reason"):
                        debug_info = f"FinishReason:{response.finish_reason}"
                    if hasattr(response, "prompt_feedback"):
                        debug_info += f" | Feedback:{response.prompt_feedback}"
                    raise ValueError(f"响应为空. Debug: {debug_info}")

                # Basic cleanup
                if text.startswith("```json"):
                    text = text[7:-3].strip()
                elif text.startswith("```"):
                    text = text[3:-3].strip()

                return json.loads(text)

            except Exception as e:
                last_error = e
                self._handle_auth_error(e)
                
                error_msg = str(e)
                if isinstance(e, asyncio.TimeoutError):
                    error_msg = f"Generation Timed Out ({retry_timeout}s)"
                
                if attempt < max_retries:
                    logger.warning(
                        "[GeminiStats] Retry generate (attempt %d/%d) error: %s", 
                        attempt, max_retries, error_msg
                    )
                    await asyncio.sleep(1)
                else:
                    logger.error("[GeminiStats] Generate failed after %d attempts: %s", max_retries, error_msg)

        return {"error": f"Gemini 调用失败: {last_error}"}

    async def generate_text_async(
        self, prompt: str, images: List[bytes] = None, 
        scene: str = "unknown", user_id: str = "unknown"
    ) -> str:
        """
        生成纯文本（非结构化 JSON）。用于 Advice 或 Report 场景。
        """
        if not self.client_ready:
            self._init_client()
            if not self.client_ready:
                return "系统错误：Gemini 客户端无法初始化（请检查 API Key）。"
        
        # Phase 1: Upload (Once)
        try:
            contents, _ = await self._prepare_contents_with_metrics(prompt, images, scene, user_id)
        except Exception as e:
            return f"图片上传失败: {e}"

        # Phase 2: Generation (Retry Loop)
        max_retries = 3
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                gen_start = time.time()
                response = await asyncio.wait_for(
                    self.client.aio.models.generate_content(
                        model=self.config.model_name,
                        contents=contents,
                        config={
                            "temperature": self.config.advice_temperature,
                        },
                    ),
                    timeout=40
                )
                gen_duration = (time.time() - gen_start) * 1000

                # Extract Token Usage
                usage_str = "N/A"
                if hasattr(response, "usage_metadata"):
                    in_tokens = getattr(response.usage_metadata, "prompt_token_count", 0)
                    out_tokens = getattr(response.usage_metadata, "candidates_token_count", 0)
                    usage_str = f"In:{in_tokens}|Out:{out_tokens}"

                log_stat({
                    "type": "GenerateText",
                    "scene": scene,
                    "user_id": user_id,
                    "model": self.config.model_name,
                    "duration_ms": gen_duration,
                    "attempt": attempt,
                    "max_retries": max_retries,
                    "tokens_in": getattr(response.usage_metadata, "prompt_token_count", 0) if hasattr(response, "usage_metadata") else 0,
                    "tokens_out": getattr(response.usage_metadata, "candidates_token_count", 0) if hasattr(response, "usage_metadata") else 0,
                    "image_count": len(images) if images else 0,
                    "status": "Success"
                })

                text_content = getattr(response, "text", "")
                if not text_content:
                    debug_info = "Unknown"
                    if hasattr(response, "finish_reason"):
                        debug_info = f"FinishReason:{response.finish_reason}"
                    if hasattr(response, "prompt_feedback"):
                        debug_info += f" | Feedback:{response.prompt_feedback}"
                    raise ValueError(f"响应为空. Debug: {debug_info}")

                return text_content

            except Exception as e:
                last_error = e
                self._handle_auth_error(e)
                
                error_msg = str(e)
                if isinstance(e, asyncio.TimeoutError):
                    error_msg = "Generation Timed Out (40s)"
                
                if attempt < max_retries:
                    logger.warning(
                        "[GeminiStats] Retry text generate (attempt %d/%d) error: %s", 
                        attempt, max_retries, error_msg
                    )
                    await asyncio.sleep(1)
                else:
                    logger.error("[GeminiStats] Text generate failed after %d attempts: %s", max_retries, error_msg)
        
        return f"生成失败: {str(last_error)}"
