"""Immutable daily histories and small, validated SW day updates."""

import gzip
import hashlib
import json
import re

from tushare_fetch import date_chunks

FIELDS = "ts_code,trade_date,name,close,pe,pb,total_mv,float_mv,amount,vol,pct_change"
START_DATE = "20060101"


def load_history(root, snapshot):
    """Read the exact published daily snapshot, including legacy response caches."""
    digest = snapshot.get("rawHistorySnapshot")
    if digest:
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Invalid raw history snapshot identifier")
        target = root / "work/.tushare-cache/sector-history" / (digest + ".json.gz")
        with gzip.open(target, "rb") as stream:
            content = stream.read()
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError("Raw daily history checksum mismatch; use --full-refresh")
        history = json.loads(content)
        if (history.get("version") != 1 or history.get("fields") != FIELDS
                or history.get("startDate") != START_DATE or history.get("endDate") != snapshot["asOf"]
                or set(history["rowsByCode"]) != set(snapshot["codes"].values())):
            raise ValueError("Raw daily history does not match the published snapshot")
        return history

    cache_day = snapshot.get("sourceSnapshotDate") or snapshot["generatedAt"][:10].replace("-", "")
    cache = root / "work/.tushare-cache" / cache_day
    rows_by_code = {}
    for code in snapshot["codes"].values():
        by_date = {}
        for start, end in date_chunks(START_DATE, snapshot["asOf"], years=10):
            params = {"ts_code": code, "start_date": start, "end_date": end}
            request = json.dumps(["sw_daily", params, FIELDS], sort_keys=True)
            target = cache / (hashlib.sha256(request.encode()).hexdigest() + ".json")
            chunk = json.loads(target.read_text(encoding="utf-8"))
            validate_chunk(chunk, code, start, end)
            by_date.update({row["trade_date"]: row for row in chunk})
        rows_by_code[code] = [by_date[day] for day in sorted(by_date)]
    return {"version": 1, "fields": FIELDS, "startDate": START_DATE,
            "endDate": snapshot["asOf"], "rowsByCode": rows_by_code}


def save_history(root, end_date, open_dates, rows_by_code):
    history = {"version": 1, "fields": FIELDS, "startDate": START_DATE,
               "endDate": end_date, "openDates": open_dates, "rowsByCode": rows_by_code}
    content = json.dumps(history, ensure_ascii=False, separators=(",", ":"),
                         sort_keys=True, allow_nan=False).encode("utf-8")
    digest = hashlib.sha256(content).hexdigest()
    target = root / "work/.tushare-cache/sector-history" / (digest + ".json.gz")
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(gzip.compress(content, compresslevel=1, mtime=0))
        temporary.replace(target)
    return digest


def validate_chunk(rows, code, start, end):
    if len(rows) >= 4000:
        raise ValueError(f"SW response reached its row cap: {code}, {start}-{end}")
    seen = set()
    for row in rows:
        day = row.get("trade_date", "")
        if row.get("ts_code") != code or not start <= day <= end or day in seen:
            raise ValueError(f"Invalid or duplicate SW history row: {code}, {day}")
        seen.add(day)


def update_dates(open_dates, previous_date, overlap=2):
    if overlap < 0:
        raise ValueError("Overlap must not be negative")
    prior = [day for day in open_dates if day <= previous_date]
    return (prior[-overlap:] if overlap else []) + [day for day in open_dates if day > previous_date]


def update_history(rows_by_code, dates, fetch_day, required_codes):
    """Fetch one complete cross-section per day; never advance on partial L1 data."""
    by_code = {code: {row["trade_date"]: row for row in rows}
               for code, rows in rows_by_code.items()}
    for day in dates:
        rows = fetch_day(day)
        if not rows or len(rows) >= 4000:
            raise ValueError(f"Empty or truncated SW day: {day}")
        seen = set()
        for row in rows:
            code = row.get("ts_code")
            if not code or row.get("trade_date") != day or code in seen:
                raise ValueError(f"Invalid or duplicate SW day row: {day}, {code}")
            seen.add(code)
        missing = set(required_codes) - seen
        if missing:
            raise ValueError(f"Incomplete SW day {day}; missing L1 indices: {sorted(missing)}")
        for history in by_code.values():
            history.pop(day, None)
        for row in rows:
            if row["ts_code"] in by_code:
                by_code[row["ts_code"]][day] = row
    return {code: [history[day] for day in sorted(history)] for code, history in by_code.items()}
