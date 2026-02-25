import time
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

import dateparser


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_mention_date(raw_date: Any) -> Optional[datetime]:
    if raw_date is None:
        return None

    try:
        if isinstance(raw_date, datetime):
            return _to_utc(raw_date)

        if isinstance(raw_date, time.struct_time):
            parsed = datetime(
                raw_date.tm_year,
                raw_date.tm_mon,
                raw_date.tm_mday,
                raw_date.tm_hour,
                raw_date.tm_min,
                raw_date.tm_sec,
                tzinfo=timezone.utc,
            )
            return _to_utc(parsed)

        if isinstance(raw_date, (tuple, list)):
            date_tuple: Tuple[Any, ...] = tuple(raw_date)
            if len(date_tuple) >= 6:
                parsed = datetime(
                    int(date_tuple[0]),
                    int(date_tuple[1]),
                    int(date_tuple[2]),
                    int(date_tuple[3]),
                    int(date_tuple[4]),
                    int(date_tuple[5]),
                    tzinfo=timezone.utc,
                )
                return _to_utc(parsed)
            return None

        if isinstance(raw_date, str):
            parsed = dateparser.parse(
                raw_date,
                settings={
                    "TIMEZONE": "UTC",
                    "RETURN_AS_TIMEZONE_AWARE": True,
                    "PREFER_DATES_FROM": "past",
                },
            )
            if parsed is None:
                return None
            return _to_utc(parsed)

        return None
    except Exception:
        return None


def is_within_interval(parsed_date: datetime, from_date: datetime) -> bool:
    parsed_date_utc = _to_utc(parsed_date)
    from_date_utc = _to_utc(from_date)
    return parsed_date_utc >= from_date_utc
