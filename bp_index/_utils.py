from datetime import datetime, timezone
from typing import Optional


def get_latest_date(*dates: Optional[datetime]) -> datetime:
    return max(filter(None, dates), default=datetime.now(timezone.utc))
