from __future__ import annotations

from datetime import datetime, timedelta, timezone


class DateTimeUtils:
    @staticmethod
    def utcnowIso() -> str:
        now = datetime.now(timezone.utc)
        return now.strftime("%Y-%m-%dT%H:%M:%S") + f".{now.microsecond // 1000:03d}Z"

    @staticmethod
    def epochSeconds() -> int:
        return int(datetime.now(timezone.utc).timestamp())

    @staticmethod
    def utcDatePath() -> str:
        return datetime.now(timezone.utc).strftime("%Y/%m/%d")

    @staticmethod
    def utcIsoAfter(hours: int = 1) -> str:
        after = datetime.now(timezone.utc) + timedelta(hours=hours)
        return after.strftime("%Y-%m-%dT%H:%M:%S") + f".{after.microsecond // 1000:03d}Z"
