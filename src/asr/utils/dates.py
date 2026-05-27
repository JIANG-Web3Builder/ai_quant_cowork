from __future__ import annotations

from datetime import date, datetime


DATE_FMT = "%Y%m%d"


def parse_yyyymmdd(value: str) -> date:
    return datetime.strptime(value, DATE_FMT).date()


def today_yyyymmdd() -> str:
    return date.today().strftime(DATE_FMT)
