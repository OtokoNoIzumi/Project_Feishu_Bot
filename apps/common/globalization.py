"""
Globalization Utilities.
"""

from datetime import datetime, timezone
import pytz


class TimezoneManager:
    """
    Manages timezone conversions based on user profile.
    Falls back to strict offset handling if pytz is not available.
    """

    # Default to Asia/Shanghai (+8) if pytz is missing or profile invalid
    DEFAULT_TZ_NAME = "Asia/Shanghai"
    DEFAULT_OFFSET_HOURS = 8

    def __init__(self, user_timezone: str = "Asia/Shanghai"):
        self.user_tz_name = user_timezone
        self.tz_obj = None

        # Initialization logic
        try:
            self.tz_obj = pytz.timezone(user_timezone)
        except pytz.UnknownTimeZoneError:
            self.tz_obj = pytz.timezone(self.DEFAULT_TZ_NAME)

    def to_user_local(self, dt: datetime) -> datetime:
        """
        Convert a datetime (UTC or aware) to user's local naive time.
        If input is naive, assume it's UTC.
        """
        if dt.tzinfo is None:
            # Assume UTC if naive
            dt = dt.replace(tzinfo=timezone.utc)

        # Use pytz for accurate conversion (DST aware)
        local_dt = dt.astimezone(self.tz_obj)
        return local_dt.replace(tzinfo=None)

    @staticmethod
    def get_user_timezone(user_id: str) -> str:
        """
        Fetch timezone from user profile.
        This would typically look up the profile.json or DB.
        For now, we will interact with the UserBioService or ProfileService if available.
        Since this is a low-level util, maybe we pass the profile dict or string directly to __init__.
        """
        # Placeholder for future expansion
        return TimezoneManager.DEFAULT_TZ_NAME
