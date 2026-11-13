import argparse
import hashlib
import json
import math
import re
import ssl
import time
import urllib.request
from bisect import bisect_right
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from tushare_fetch import cached_call, date_chunks
from weekly_sampling import sample_dates, weekly_dates


ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path.home() / ".codex" / "config.toml"
OUTPUT = ROOT / "outputs" / "sector_real_data.json"
OUTPUT_JS = ROOT / "outputs" / "sector_real_data.js"
START_DATE = "20060101"
PERIOD_YEARS = ("1", "3", "5", "10", "20")


def get_token():
    text = CONFIG.read_text(encoding="utf-8")
    match = re.search(r"https://api\.tushare\.pro/mcp/\?token=([^'\"&\s]+)", text)
    if not match:
        raise RuntimeError("Tushare token was not found in the local Codex config.")
    return match.group(0)


def parse_sse_json(text):
    for line in text.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])
    raise RuntimeError(f"MCP response did not contain JSON data: {text[:200]}")


def call_mcp(endpoint, api_name, params, fields):
    arguments = dict(params or {})
    if fields:
        arguments["fields"] = [field.strip() for field in fields.split(",") if field.strip()]
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": api_name, "arguments": arguments}},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60, context=ssl._create_unverified_context()) as response:
        result = parse_sse_json(response.read().decode("utf-8"))
    if "error" in result:
        raise RuntimeError(f"{api_name}: {result['error']}")
    tool_result = result.get("result", {})
    if tool_result.get("isError"):
        content = tool_result.get("content") or []
        message = content[0].get("text") if content else "unknown MCP error"
        raise RuntimeError(f"{api_name}: {message}")
    content = tool_result.get("content") or []
    if not content:
        return []
    return json.loads(content[0].get("text") or "[]")


def call_api(token, api_name, params, fields):
    if token.startswith("https://api.tushare.pro/mcp/"):
        return call_mcp(token, api_name, params, fields)
    payload = json.dumps(
        {"api_name": api_name, "token": token, "params": params, "fields": fields},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.tushare.pro",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        result = json.loads(response.read().decode("utf-8"))
    if result.get("code") != 0:
        raise RuntimeError(f"{api_name}: {result.get('msg')}")
    data = result["data"]
    return [dict(zip(data["fields"], row)) for row in data["items"]]


def shift_years(date_text, years):
    date = ymd(date_text)
    try:
        shifted = date.replace(year=date.year - years)
    except ValueError:
        shifted = date.replace(year=date.year - years, day=28)
    return shifted.strftime("%Y%m%d")


def latest_sw_date(token):
    today = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d")
    # Use a liquid SW level-1 index as the availability probe; SW index data can lag
    # the exchange calendar, so the latest open day is not always enough.
    rows = call_api(
        token,
        "sw_daily",
        {"ts_code": "801080.SI", "start_date": shift_years(today, 1), "end_date": today},
        "trade_date,close",
    )
    dates = sorted(row["trade_date"] for row in rows if row.get("trade_date") and row.get("close"))
    if not dates:
        raise RuntimeError("No recent SW daily rows found.")
    return dates[-1]


def clean_name(name):
    return re.sub(r"[ⅠⅡⅢ]+$", "", name or "")


def ymd(date_text):
    return datetime.strptime(date_text, "%Y%m%d")


def normalize_series(rows, key):
    vals = []
    for row in rows:
        value = row.get(key)
        if value is None:
            vals.append(None)
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            vals.append(None)
            continue
        vals.append(value if math.isfinite(value) else None)
    if key in ("close", "profit"):
        valid = next((value for value in vals if value and value > 0), None)
        if valid:
            return [None if value is None else round(value / valid * 100, 2) for value in vals]
    return [None if value is None else round(value, 2) for value in vals]


def implied_profit(row):
    pe = row.get("pe")
    mv = row.get("total_mv")
    if pe is None or mv is None:
        return None
    try:
        pe = float(pe)
        mv = float(mv)
    except (TypeError, ValueError):
        return None
    if pe <= 0 or not math.isfinite(pe) or not math.isfinite(mv):
        return None
    return mv / pe


def observation_value(row, key):
    try:
        value = float(row.get(key))
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def valuation_percentile(rows, key, latest):
    values = [observation_value(row, key) for row in rows]
    values = [value for value in values if value is not None and value > 0]
    current = observation_value(latest, key)
    if current is None or current <= 0 or not values:
        return None
    return round(sum(value <= current for value in values) / len(values) * 100)


def valuation_percentile_series(rows, key, sample):
    """Rank each observation against all valid daily values in this interval."""
    values = sorted(value for row in rows
                    if (value := observation_value(row, key)) is not None and value > 0)
    result = []
    for row in sample:
        current = observation_value(row, key)
        result.append(round(bisect_right(values, current) / len(values) * 100)
                      if values and current is not None and current > 0 else None)
    return result


def build_history(rows, open_dates, end_date):
    rows = [row for row in rows if row.get("trade_date")]
    rows.sort(key=lambda row: row["trade_date"])
    for row in rows:
        row["profit"] = implied_profit(row)
        amount = observation_value(row, "amount")
        volume = observation_value(row, "vol")
        float_mv = observation_value(row, "float_mv")
        row["amountYi"] = amount / 10000 if amount is not None else None
        row["volumeYi"] = volume / 10000 if volume is not None else None
        row["amountFloatRatio"] = amount / float_mv * 100 if amount is not None and float_mv and float_mv > 0 else None
    latest = rows[-1] if rows else {}
    periods = {}
    for years in (*PERIOD_YEARS, "all"):
        start = START_DATE if years == "all" else shift_years(end_date, int(years))
        dates = weekly_dates(open_dates, start, end_date)
        sample = sample_dates(rows, dates)
        valid_rows = [row for row in sample if row.get("close")]
        # Retain the existing full-history requirement for numbered time ranges.
        raw_period = [row for row in rows if start <= row["trade_date"] <= end_date and row.get("close")]
        if years != "all" and int(years) > 1 and (not raw_period or (ymd(raw_period[0]["trade_date"]) - ymd(start)).days > 90):
            periods[years] = None
            continue
        ret = (float(valid_rows[-1]["close"]) / float(valid_rows[0]["close"]) - 1) * 100 if valid_rows else None
        full_period = [row for row in rows if start <= row["trade_date"] <= end_date]
        periods[years] = {
            "dates": [row["trade_date"] for row in sample],
            "labels": [ymd(row["trade_date"]).strftime("%Y-%m-%d") for row in sample],
            "price": normalize_series(sample, "close"),
            "profit": normalize_series(sample, "profit"),
            "pe": normalize_series(sample, "pe"),
            "pePercentileSeries": valuation_percentile_series(full_period, "pe", sample),
            "pb": normalize_series(sample, "pb"),
            "amountYi": normalize_series(sample, "amountYi"),
            "volumeYi": normalize_series(sample, "volumeYi"),
            "amountFloatRatio": normalize_series(sample, "amountFloatRatio"),
            "return": round(ret, 2) if ret is not None else None,
            "startDate": start,
            "endDate": end_date,
            "observedStartDate": valid_rows[0]["trade_date"] if valid_rows else None,
            "observedEndDate": valid_rows[-1]["trade_date"] if valid_rows else None,
            "pePercentile": valuation_percentile(full_period, "pe", latest),
            "pbPercentile": valuation_percentile(full_period, "pb", latest),
        }
    return {
        "latest": {
            "date": latest.get("trade_date"),
            "close": round(float(latest["close"]), 2) if latest.get("close") is not None else None,
            "pe": round(float(latest["pe"]), 2) if latest.get("pe") is not None else None,
            "totalMv": round(float(latest["total_mv"]), 2) if latest.get("total_mv") is not None else None,
            "profit": round(implied_profit(latest), 2) if implied_profit(latest) else None,
            **{key: round(observation_value(latest, field), 4)
               if observation_value(latest, field) is not None else None
               for key, field in {
                   "pb": "pb", "amountYi": "amountYi", "volumeYi": "volumeYi",
                   "amountFloatRatio": "amountFloatRatio", "pctChange": "pct_change",
               }.items()},
        },
        "periods": periods,
    }


def main():
    parser = argparse.ArgumentParser(description="Build sector data with common weekly observations and daily valuation ranks.")
    parser.add_argument("--reuse-snapshot", action="store_true", help="Resample the existing published snapshot without advancing its as-of date.")
    args = parser.parse_args()
    token = get_token()
    previous = json.loads(OUTPUT.read_text()) if args.reuse_snapshot else None
    end_date = previous["asOf"] if previous else latest_sw_date(token)
    calendar_rows = cached_call(call_api, token, "trade_cal", {
        "exchange": "SSE", "start_date": START_DATE, "end_date": end_date, "is_open": "1",
    }, "cal_date,is_open")
    open_dates = sorted(row["cal_date"] for row in calendar_rows if str(row["is_open"]) == "1")
    if not open_dates:
        raise RuntimeError("No trading dates in the requested calendar")
    periods = {years: shift_years(end_date, int(years)) for years in PERIOD_YEARS}
    periods["all"] = START_DATE
    print(f"SW data as of {end_date}; common weekly observations", flush=True)
    l1_rows = [] if previous else call_api(token, "index_classify", {"src": "SW2021", "level": "L1"}, "index_code,industry_name,parent_code,level,industry_code")
    l2_rows = [] if previous else call_api(token, "index_classify", {"src": "SW2021", "level": "L2"}, "index_code,industry_name,parent_code,level")

    l1_by_code = {row["industry_code"]: clean_name(row["industry_name"]) for row in l1_rows}
    children = {name: [] for name in l1_by_code.values()}
    code_by_name = {}
    level_by_name = {}
    for row in l1_rows:
        name = clean_name(row["industry_name"])
        code_by_name[name] = row["index_code"]
        level_by_name[name] = 1
    for row in l2_rows:
        parent = l1_by_code.get(row["parent_code"])
        if not parent:
            continue
        name = clean_name(row["industry_name"])
        # A few SW names collide after removing level suffixes, e.g. L1/L2 "综合".
        # Keep the original L2 suffix in those cases so metrics are not overwritten.
        if name in code_by_name:
            name = row["industry_name"]
        children[parent].append(name)
        code_by_name[name] = row["index_code"]
        level_by_name[name] = 2

    if previous:
        children, code_by_name, level_by_name = previous["industries"], previous["codes"], previous["levels"]

    metrics = {}
    fields = "ts_code,trade_date,name,close,pe,pb,total_mv,float_mv,amount,vol,pct_change"
    items = list(code_by_name.items())
    for idx, (name, code) in enumerate(items, 1):
        print(f"[{idx}/{len(items)}] {name} {code}", flush=True)
        by_date = {}
        for start, end in date_chunks(START_DATE, end_date, years=10):
            params = {"ts_code": code, "start_date": start, "end_date": end}
            if previous:
                request = json.dumps(["sw_daily", params, fields], sort_keys=True)
                key = hashlib.sha256(request.encode()).hexdigest() + ".json"
                cache_day = previous.get("sourceSnapshotDate", previous["generatedAt"][:10].replace("-", ""))
                path = ROOT / "work" / ".tushare-cache" / cache_day / key
                chunk = json.loads(path.read_text(encoding="utf-8"))
            else:
                chunk = cached_call(call_api, token, "sw_daily", params, fields)
            if len(chunk) >= 4000:
                raise RuntimeError(f"SW response reached its row cap: {code}, {start}-{end}")
            by_date.update({row["trade_date"]: row for row in chunk})
        rows = list(by_date.values())
        if rows and max(by_date) != end_date:
            print(f"  Last published SW date for {name}: {max(by_date)}", flush=True)
        if not rows:
            print(f"  No published SW history for {name}; values remain unavailable.", flush=True)
        metrics[name] = build_history(rows, open_dates, end_date)
        if not previous:
            time.sleep(0.08)

    # Sort using latest total market value, descending.
    sorted_industries = {}
    for parent in sorted(children, key=lambda n: (metrics.get(n, {}).get("latest", {}).get("totalMv") or 0), reverse=True):
        sorted_industries[parent] = sorted(
            children[parent],
            key=lambda n: (metrics.get(n, {}).get("latest", {}).get("totalMv") or 0),
            reverse=True,
        )

    payload = {
        "source": "Tushare sw_daily / index_classify, SW2021",
        "asOf": end_date,
        "chartAsOf": end_date,
        "sampling": {
            "frequency": "week", "rule": "每周最后一个交易日，当前周取快照最新交易日；各指数使用共同日期，缺失留空",
            "periodDates": {years: weekly_dates(open_dates, start, end_date) for years, start in periods.items()},
            "percentileRule": "所选区间全部有效正日度数据，含相等值；不因曲线改用周打点而改成周样本排名",
        },
        "sourceSnapshotDate": previous.get("sourceSnapshotDate", previous["generatedAt"][:10].replace("-", "")) if previous else datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d"),
        "periodStarts": periods,
        "generatedAt": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "industries": sorted_industries,
        "codes": code_by_name,
        "levels": level_by_name,
        "metrics": metrics,
        "unavailableIndustries": [name for name, value in metrics.items() if not value["latest"]["date"]],
        "historicalOnlyIndustries": {
            name: value["latest"]["date"] for name, value in metrics.items()
            if value["latest"]["date"] and value["latest"]["date"] != end_date
        },
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    OUTPUT_JS.write_text("window.SECTOR_REAL_DATA = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
