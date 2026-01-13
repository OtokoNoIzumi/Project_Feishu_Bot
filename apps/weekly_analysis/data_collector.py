"""
Weekly Analysis Data Collector.

Collects all relevant data for a specified week from Diet and Keep records.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from libs.storage_lib import global_storage
from libs.core.config_loader import load_json
from libs.core.project_paths import get_project_root
from apps.common.record_service import RecordService


@dataclass
class WeeklyDataBundle:
    """Data bundle containing all data for weekly analysis."""

    user_id: str
    week_start: date
    week_end: date

    # Diet data
    diet_records: List[Dict] = field(default_factory=list)
    dish_library: List[Dict] = field(default_factory=list)

    # Keep data
    scale_records: List[Dict] = field(default_factory=list)
    sleep_records: List[Dict] = field(default_factory=list)

    # Dimensions (special handling: current week + baseline)
    current_week_dimensions: List[Dict] = field(default_factory=list)
    baseline_dimension: Optional[Dict] = None
    
    # Scale Baseline
    baseline_scale_record: Optional[Dict] = None

    # User profile & preferences
    user_profile: Dict = field(default_factory=dict)
    user_preferences: Dict = field(default_factory=dict)

    # Reserved for future
    cgm_data: Optional[List[Dict]] = None

    # Computed properties for analysis trigger conditions
    @property
    def has_diet_data(self) -> bool:
        return len(self.diet_records) > 0

    @property
    def has_scale_data(self) -> bool:
        return len(self.scale_records) >= 2 or (len(self.scale_records) == 1 and self.baseline_scale_record is not None)

    @property
    def can_calibrate_calories(self) -> bool:
        """Need at least 3 diet days and 2 scale points (including baseline) for calibration."""
        total_scale_points = len(self.scale_records) + (1 if self.baseline_scale_record else 0)
        if total_scale_points < 2:
            return False
        # Check diet coverage
        diet_dates = set()
        for r in self.diet_records:
            occ = r.get("occurred_at", "")[:10]
            if occ:
                diet_dates.add(occ)
        return len(diet_dates) >= 3

    @property
    def has_dimension_comparison(self) -> bool:
        """Need at least 2 different dates of dimension data."""
        all_dims = (
            [self.baseline_dimension] if self.baseline_dimension else []
        ) + self.current_week_dimensions

        dates = set()
        for d in all_dims:
            if d:
                occ = d.get("occurred_at", "")[:10]
                if occ:
                    dates.add(occ)
        return len(dates) >= 2

    @property
    def has_profile(self) -> bool:
        return bool(self.user_profile)

    def to_summary(self) -> Dict[str, Any]:
        """Return a summary of data availability for debugging/logging."""
        return {
            "user_id": self.user_id,
            "week_range": f"{self.week_start} ~ {self.week_end}",
            "diet_record_count": len(self.diet_records),
            "dish_library_count": len(self.dish_library),
            "scale_record_count": len(self.scale_records),
            "has_baseline_scale": self.baseline_scale_record is not None,
            "sleep_record_count": len(self.sleep_records),
            "current_week_dimensions_count": len(self.current_week_dimensions),
            "has_baseline_dimension": self.baseline_dimension is not None,
            "has_profile": self.has_profile,
            "has_preferences": bool(self.user_preferences),
            # Trigger flags
            "can_analyze_diet": self.has_diet_data,
            "can_suggest_meals": self.has_diet_data and len(self.dish_library) > 0,
            "can_calibrate_calories": self.can_calibrate_calories,
            "can_analyze_dimensions": self.has_dimension_comparison,
            "can_track_goals": self.has_profile,
        }


def get_last_week_monday(reference_date: date = None) -> date:
    """Get the Monday of the previous week."""
    if reference_date is None:
        reference_date = date.today()
    # Go back to this week's Monday, then subtract 7 days
    days_since_monday = reference_date.weekday()  # Monday = 0
    this_monday = reference_date - timedelta(days=days_since_monday)
    last_monday = this_monday - timedelta(days=7)
    return last_monday


def collect_weekly_data(
    user_id: str,
    week_start: date = None,
    dish_library_limit: int = 100,
) -> WeeklyDataBundle:
    """
    Collect all data for a specified week.

    Args:
        user_id: User identifier
        week_start: Start of the week (Monday). Defaults to last week's Monday.
        dish_library_limit: Maximum number of dish library entries to include.

    Returns:
        WeeklyDataBundle with all collected data.
    """
    if week_start is None:
        week_start = get_last_week_monday()

    week_end = week_start + timedelta(days=6)

    bundle = WeeklyDataBundle(
        user_id=user_id,
        week_start=week_start,
        week_end=week_end,
    )

    # Convert to string format for RecordService
    start_str = week_start.strftime("%Y-%m-%d")
    end_str = week_end.strftime("%Y-%m-%d")

    # 1. Collect Diet Records
    bundle.diet_records = RecordService.get_diet_records_range(
        user_id, start_str, end_str
    )

    # 2. Collect Dish Library (most recent N entries)
    all_dishes = global_storage.read_dataset(
        user_id, "diet", "dish_library.jsonl", limit=dish_library_limit * 2
    )
    # read_dataset returns newest first, take the first N
    bundle.dish_library = all_dishes[:dish_library_limit]

    # 3. Collect Keep Records (Scale, Sleep, Dimensions separately)
    week_start_dt = datetime.combine(week_start, datetime.min.time())
    week_end_dt = datetime.combine(week_end, datetime.max.time().replace(microsecond=0))

    all_keep = RecordService._read_keep_records_for_period(
        user_id, week_start_dt, week_end_dt
    )

    for rec in all_keep:
        event_type = rec.get("event_type")
        if event_type == "scale":
            bundle.scale_records.append(rec)
        elif event_type == "sleep":
            bundle.sleep_records.append(rec)
        elif event_type == "dimensions":
            bundle.current_week_dimensions.append(rec)

    # Sort by occurred_at
    def sort_by_occurred(recs: List[Dict]) -> List[Dict]:
        return sorted(recs, key=lambda x: x.get("occurred_at", ""))

    bundle.diet_records = sort_by_occurred(bundle.diet_records)

    bundle.scale_records = sort_by_occurred(bundle.scale_records)
    bundle.sleep_records = sort_by_occurred(bundle.sleep_records)
    bundle.current_week_dimensions = sort_by_occurred(bundle.current_week_dimensions)

    # 4. Get Baseline Data (last record before week_start)
    bundle.baseline_dimension = _get_baseline_record(user_id, week_start, "dimensions")
    bundle.baseline_scale_record = _get_baseline_record(user_id, week_start, "scale")

    # 5. Load User Profile
    bundle.user_profile = _load_user_profile(user_id)

    # 6. Load User Preferences
    bundle.user_preferences = _load_user_preferences(user_id)

    return bundle


def _get_baseline_record(user_id: str, before_date: date, event_type: str) -> Optional[Dict]:
    """
    Get the most recent record of a specific type before the specified date.
    """
    # Look back up to 30 days for baseline (shorter than dimension because weight fluctuates more)
    # But dimensions are slow moving, so 90 days.
    lookback_days = 90 if event_type == "dimensions" else 30
    
    search_start = before_date - timedelta(days=lookback_days)
    search_end = before_date - timedelta(days=1)

    start_dt = datetime.combine(search_start, datetime.min.time())
    end_dt = datetime.combine(search_end, datetime.max.time().replace(microsecond=0))

    all_keep = RecordService._read_keep_records_for_period(user_id, start_dt, end_dt)

    # Filter for event type
    records = [r for r in all_keep if r.get("event_type") == event_type]

    if not records:
        return None

    # Sort by occurred_at descending, take the most recent
    records.sort(key=lambda x: x.get("occurred_at", ""), reverse=True)
    return records[0]


def _load_user_profile(user_id: str) -> Dict:
    """Load user profile (goals, targets) from profile.json."""
    root = get_project_root()
    profile_path = root / "user_data" / user_id / "diet" / "profile.json"
    if profile_path.exists():
        return load_json(profile_path) or {}
    return {}


def _load_user_preferences(user_id: str) -> Dict:
    """Load user preferences (fixed meals, restrictions) from preferences.json."""
    root = get_project_root()
    prefs_path = root / "user_data" / user_id / "diet" / "preferences.json"
    if prefs_path.exists():
        return load_json(prefs_path) or {}
    return {}
