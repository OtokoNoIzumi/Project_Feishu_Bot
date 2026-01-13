"""
Weekly Analysis Usecase.

Core business logic for generating weekly diet & keep analysis reports.
"""

import json
import logging
from datetime import date
from typing import Any, Dict, Optional

from libs.api_keys.api_key_manager import get_default_api_key_manager
from libs.llm_gemini.gemini_client import GeminiClientConfig, GeminiStructuredClient

from apps.weekly_analysis.data_collector import (
    WeeklyDataBundle,
    collect_weekly_data,
)
from apps.weekly_analysis.weekly_prompt import build_weekly_analysis_prompt
from apps.weekly_analysis.analysis_schema import get_weekly_analysis_schema

logger = logging.getLogger(__name__)


class WeeklyAnalysisUsecase:
    """
    Usecase for generating comprehensive weekly analysis reports.
    
    Orchestrates:
    1. Data collection (via data_collector)
    2. Prompt building (via weekly_prompt)
    3. AI generation (via gemini_client)
    4. Result parsing
    """

    def __init__(self, gemini_model_name: str):
        self.api_keys = get_default_api_key_manager()
        self.client = GeminiStructuredClient(
            api_key_manager=self.api_keys,
            config=GeminiClientConfig(
                model_name=gemini_model_name,
                temperature=0.3,  # Lower for more consistent analysis
            ),
        )

    async def execute_async(
        self,
        user_id: str,
        week_start: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Execute weekly analysis.

        Args:
            user_id: User identifier.
            week_start: Start of the analysis week (Monday). 
                       Defaults to last week's Monday.

        Returns:
            Dict containing:
            - success: bool
            - report: Analysis result dict (if success)
            - data_summary: Data availability summary
            - error: Error message (if failed)
        """
        # 1. Collect Data
        try:
            bundle = collect_weekly_data(user_id=user_id, week_start=week_start)
        except Exception as e:
            logger.error("Data collection failed: %s", e)
            return {
                "success": False,
                "error": f"数据采集失败: {e}",
            }

        data_summary = bundle.to_summary()

        # 2. Check if we have enough data for any analysis
        if not bundle.has_diet_data and not bundle.has_scale_data:
            return {
                "success": False,
                "error": "数据不足：本周无饮食或体重记录。",
                "data_summary": data_summary,
            }

        # 3. Build Prompt
        prompt = build_weekly_analysis_prompt(bundle)
        logger.debug("Weekly analysis prompt length: %d chars", len(prompt))

        # 4. Generate with AI
        try:
            # Use structured JSON generation with schema
            schema = get_weekly_analysis_schema()
            
            # DEBUG: Print prompt and schema for verification
            print("=" * 80)
            print("test-schema", schema)
            print("=" * 80)
            print("test-prompt", prompt)
            print("=" * 80)
            
            result = await self.client.generate_json_async(
                prompt=prompt,
                images=[],  # No images for weekly analysis
                schema=schema,
            )

            if isinstance(result, dict) and result.get("error"):
                return {
                    "success": False,
                    "error": result["error"],
                    "data_summary": data_summary,
                }

            # 5. Return result directly (schema already defines structure)
            return {
                "success": True,
                "report": result,
                "data_summary": data_summary,
            }

        except Exception as e:
            logger.error("AI generation failed: %s", e)
            return {
                "success": False,
                "error": f"AI分析生成失败: {e}",
                "data_summary": data_summary,
            }

    async def execute_text_async(
        self,
        user_id: str,
        week_start: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Alternative: Generate analysis as free-form text instead of structured JSON.
        
        Useful when schema parsing fails or for simpler use cases.
        """
        # 1. Collect Data
        try:
            bundle = collect_weekly_data(user_id=user_id, week_start=week_start)
        except Exception as e:
            return {"success": False, "error": f"数据采集失败: {e}"}

        data_summary = bundle.to_summary()

        if not bundle.has_diet_data and not bundle.has_scale_data:
            return {
                "success": False,
                "error": "数据不足：本周无饮食或体重记录。",
                "data_summary": data_summary,
            }

        # 2. Build prompt (reuse same prompt, but tell AI to output text)
        prompt = build_weekly_analysis_prompt(bundle)
        prompt += "\n\n请直接用中文自然语言输出分析报告，不要使用JSON格式。"

        # 3. Generate text
        try:
            text = await self.client.generate_text_async(prompt=prompt, images=[])
            
            if text.startswith("生成失败") or "错误" in text[:20]:
                return {
                    "success": False,
                    "error": text,
                    "data_summary": data_summary,
                }

            return {
                "success": True,
                "report_text": text,
                "data_summary": data_summary,
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"AI分析生成失败: {e}",
                "data_summary": data_summary,
            }
