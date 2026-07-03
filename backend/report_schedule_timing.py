"""
Next-run date arithmetic for scheduled report delivery.
"""

import calendar
from datetime import datetime, timezone, timedelta


def calculate_next_run(
    frequency: str, hour: int = 8, day_of_week: int = 1, day_of_month: int = 1,
) -> datetime:
    now = datetime.now(timezone.utc)
    base = now.replace(minute=0, second=0, microsecond=0)

    if frequency == "daily":
        next_dt = base.replace(hour=hour)
        if next_dt <= now:
            next_dt += timedelta(days=1)
        return next_dt

    elif frequency == "weekly":
        # Schedule storage convention: day_of_week 1=Monday ... 7=Sunday.
        # Python's datetime.weekday(): Monday=0 ... Sunday=6.
        target_weekday = (int(day_of_week) - 1) % 7
        days_ahead = (target_weekday - now.weekday()) % 7
        next_dt = (base + timedelta(days=days_ahead)).replace(hour=hour)
        if next_dt <= now:
            next_dt += timedelta(days=7)
        return next_dt

    elif frequency == "monthly":
        target_month = 1 if now.month == 12 else now.month + 1
        target_year = now.year + 1 if now.month == 12 else now.year
        last_day = calendar.monthrange(target_year, target_month)[1]
        target_day = max(1, min(int(day_of_month), last_day))
        return base.replace(year=target_year, month=target_month, day=target_day, hour=hour)

    else:  # quarterly
        quarter_starts = [1, 4, 7, 10]
        next_month = next((m for m in quarter_starts if m > now.month), 1)
        next_year = now.year if next_month > now.month else now.year + 1
        last_day = calendar.monthrange(next_year, next_month)[1]
        target_day = max(1, min(int(day_of_month), last_day))
        return base.replace(year=next_year, month=next_month, day=target_day, hour=hour)
