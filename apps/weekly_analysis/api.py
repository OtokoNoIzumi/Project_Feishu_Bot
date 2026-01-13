"""
Weekly Analysis API Router.

Provides endpoints for weekly diet & keep analysis, reports, and visualizations.
"""

import asyncio
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from apps.deps import get_current_user_id, require_internal_auth
from apps.llm_runtime import get_global_semaphore, get_model_limiter
from apps.settings import BackendSettings
from apps.weekly_analysis.data_collector import (
    WeeklyDataBundle,
    collect_weekly_data,
)
from apps.weekly_analysis.usecases.weekly_analysis_usecase import WeeklyAnalysisUsecase
from libs.utils.rate_limiter import AsyncRateLimiter


# --- Response Models ---


class WeeklyDataResponse(BaseModel):
    """Response model for fetching weekly data (MVP1: raw data only)."""

    success: bool
    data_summary: Optional[Dict[str, Any]] = None
    diet_records: list = Field(default_factory=list)
    scale_records: list = Field(default_factory=list)
    sleep_records: list = Field(default_factory=list)
    dimension_data: Optional[Dict[str, Any]] = None
    profile: Optional[Dict[str, Any]] = None
    preferences: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class WeeklyReportResponse(BaseModel):
    """Response model for weekly analysis report."""

    success: bool
    report: Optional[Dict[str, Any]] = None
    report_text: Optional[str] = None  # For text mode
    data_summary: Optional[Dict[str, Any]] = None
    charts: Optional[Dict[str, Any]] = None  # MVP3: chart configs
    error: Optional[str] = None


def _parse_week_start(week_start_str: Optional[str], week_offset: int) -> date:
    """Parse week_start from string or calculate from offset."""
    if week_start_str:
        return datetime.strptime(week_start_str, "%Y-%m-%d").date()
    
    # Calculate based on offset
    today = date.today()
    days_since_monday = today.weekday()
    this_monday = today - timedelta(days=days_since_monday)
    return this_monday + timedelta(weeks=week_offset)


def build_weekly_analysis_router(settings: BackendSettings) -> APIRouter:
    """Build and return the weekly analysis API router."""
    router = APIRouter()
    auth_dep = require_internal_auth(settings)

    # Initialize usecase
    analysis_uc = WeeklyAnalysisUsecase(gemini_model_name=settings.gemini_model_name)

    def _get_model_limiter() -> AsyncRateLimiter:
        return get_model_limiter(settings)

    # --- Endpoints ---

    @router.get(
        "/api/weekly-analysis/data",
        response_model=WeeklyDataResponse,
        dependencies=[Depends(auth_dep)],
    )
    async def get_weekly_data(
        user_id: str = Depends(get_current_user_id),
        week_offset: int = Query(
            -1,
            description="Week offset from current: 0=this week, -1=last week, -2=two weeks ago...",
        ),
        week_start: Optional[str] = Query(
            None,
            description="Explicit week start date (YYYY-MM-DD, Monday). Overrides week_offset if provided.",
        ),
    ):
        """
        Fetch all raw data for a specified week.
        
        This is MVP1: returns collected data for inspection.
        """
        try:
            parsed_start = _parse_week_start(week_start, week_offset)

            # Collect data
            bundle: WeeklyDataBundle = collect_weekly_data(
                user_id=user_id,
                week_start=parsed_start,
            )

            # Build response
            return WeeklyDataResponse(
                success=True,
                data_summary=bundle.to_summary(),
                diet_records=bundle.diet_records,
                scale_records=bundle.scale_records,
                sleep_records=bundle.sleep_records,
                dimension_data={
                    "current_week": bundle.current_week_dimensions,
                    "baseline": bundle.baseline_dimension,
                },
                profile=bundle.user_profile if bundle.user_profile else None,
                preferences=bundle.user_preferences if bundle.user_preferences else None,
            )

        except ValueError as e:
            return WeeklyDataResponse(
                success=False,
                error=f"Invalid date format: {e}",
            )
        except Exception as e:
            return WeeklyDataResponse(
                success=False,
                error=f"Failed to collect weekly data: {e}",
            )

    @router.get(
        "/api/weekly-analysis/report",
        response_model=WeeklyReportResponse,
        dependencies=[Depends(auth_dep)],
    )
    async def get_weekly_report(
        user_id: str = Depends(get_current_user_id),
        week_offset: int = Query(-1, description="Week offset: 0=this week, -1=last week"),
        week_start: Optional[str] = Query(
            None,
            description="Explicit week start date (YYYY-MM-DD). Overrides week_offset.",
        ),
        output_mode: str = Query(
            "json",
            description="Output mode: 'json' for structured data, 'text' for narrative report.",
        ),
        semaphore: asyncio.Semaphore = Depends(get_global_semaphore),
        limiter: AsyncRateLimiter = Depends(_get_model_limiter),
    ):
        """
        Generate comprehensive weekly analysis report.
        
        Uses AI to analyze diet and keep data for the specified week.
        
        Args:
            week_offset: -1 for last week, 0 for this week, etc.
            week_start: Explicit start date (Monday), overrides offset.
            output_mode: 'json' for structured, 'text' for narrative.
        """
        try:
            parsed_start = _parse_week_start(week_start, week_offset)
        except ValueError as e:
            return WeeklyReportResponse(
                success=False,
                error=f"Invalid date format: {e}",
            )

        # Apply rate limiting and concurrency control
        async with semaphore:
            await limiter.check_and_wait()

            if output_mode == "text":
                result = await analysis_uc.execute_text_async(
                    user_id=user_id,
                    week_start=parsed_start,
                )
                
                if not result.get("success"):
                    return WeeklyReportResponse(
                        success=False,
                        error=result.get("error"),
                        data_summary=result.get("data_summary"),
                    )
                
                return WeeklyReportResponse(
                    success=True,
                    report_text=result.get("report_text"),
                    data_summary=result.get("data_summary"),
                )
            else:
                # Default: structured JSON
                result = await analysis_uc.execute_async(
                    user_id=user_id,
                    week_start=parsed_start,
                )

                if not result.get("success"):
                    return WeeklyReportResponse(
                        success=False,
                        error=result.get("error"),
                        data_summary=result.get("data_summary"),
                    )

                return WeeklyReportResponse(
                    success=True,
                    report=result.get("report"),
                    data_summary=result.get("data_summary"),
                    # charts will be added in MVP3
                )

    return router

