"""Shared quote validity policy for PDFs and new signing links."""

from datetime import datetime, timedelta

import holidays


QUOTE_VALIDITY_BUSINESS_DAYS = 14


def quote_valid_until(issued_at: datetime) -> datetime:
    """Count 14 Israeli business days after issue, preserving the time of day.

    Business days are Sunday through Thursday, excluding Israeli public
    holidays. The issue date itself is not counted.
    """
    public_holidays = holidays.country_holidays("IL")
    deadline = issued_at
    remaining = QUOTE_VALIDITY_BUSINESS_DAYS
    while remaining:
        deadline += timedelta(days=1)
        if deadline.weekday() not in (4, 5) and deadline.date() not in public_holidays:
            remaining -= 1
    return deadline
