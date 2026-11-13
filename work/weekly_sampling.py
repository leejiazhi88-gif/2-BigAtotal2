"""One common observation date per trading week, independent of index coverage."""
from datetime import datetime


def weekly_dates(open_dates, start_date, end_date):
    """Last open day in each ISO week; the current week ends at the snapshot date."""
    last_by_week = {}
    for day in sorted(set(open_dates)):
        if start_date <= day <= end_date:
            year, week, _ = datetime.strptime(day, "%Y%m%d").isocalendar()
            last_by_week[(year, week)] = day
    return list(last_by_week.values())


def sample_dates(rows, dates):
    """Missing exact dates stay empty, rather than shifting an index to a different day."""
    by_date = {row["trade_date"]: row for row in rows}
    return [by_date.get(day, {"trade_date": day}) for day in dates]
