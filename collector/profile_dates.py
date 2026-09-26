"""Optional career dates from explicit ISO strings or Unix seconds/milliseconds."""
from datetime import datetime, timezone
import math
import re


def profile_date(value):
    if value is None or isinstance(value, bool) or value == '':
        return None
    try:
        if isinstance(value, (int, float)):
            number = float(value)
            if not math.isfinite(number) or number <= 0:
                return None
            seconds = number / 1000 if number >= 100_000_000_000 else number
            return datetime.fromtimestamp(seconds, timezone.utc).date().isoformat()
        if isinstance(value, str) and re.match(r'^\d{4}-\d{2}-\d{2}(?:$|T| )', value):
            return datetime.fromisoformat(value[:10]).date().isoformat()
    except (OverflowError, OSError, ValueError):
        pass
    return None
