"""Current SW2021 constituents and company market caps for the dashboard."""

import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from build_real_sector_data import call_api, get_token, observation_value
from build_market_modules_data import latest_daily_basic_date
from tushare_fetch import cached_call

ROOT = Path(__file__).resolve().parents[1]
MEMBER_FIELDS = "l1_code,l1_name,l2_code,l2_name,ts_code,name,in_date,out_date,is_new"
CAP_FIELDS = "ts_code,trade_date,total_mv,circ_mv"


def main():
    token = get_token()
    sector = json.loads((ROOT / "outputs/sector_real_data.json").read_text())
    date = latest_daily_basic_date(token)
    print(f"Latest company market cap date: {date}", flush=True)
    members = cached_call(call_api, token, "index_member_all", {"is_new": "Y"}, MEMBER_FIELDS)
    if len(members) >= 7000:
        members = []
        for name, level in sector["levels"].items():
            if level != 1:
                continue
            rows = cached_call(call_api, token, "index_member_all",
                               {"is_new": "Y", "l1_code": sector["codes"][name]}, MEMBER_FIELDS)
            if len(rows) >= 7000:
                raise RuntimeError(f"Truncated constituents: {name}")
            members.extend(rows)
    stocks = cached_call(call_api, token, "stock_basic", {"list_status": "L"}, "ts_code,name,list_date")
    caps = cached_call(call_api, token, "daily_basic", {"trade_date": date}, CAP_FIELDS)
    if not members or not stocks or len(stocks) >= 10000 or not caps or len(caps) >= 6000:
        raise RuntimeError("Missing or truncated membership, stock list, or market cap response")
    listed = {r["ts_code"]: r for r in stocks if r.get("list_date") and r["list_date"] <= date}
    cap_by_code = {r["ts_code"]: r for r in caps}
    indices = {code: set() for code in sector["codes"].values()}
    included = set()
    for row in members:
        code = row["ts_code"]
        if code not in listed or (row.get("in_date") and row["in_date"] > date):
            continue
        if row.get("out_date") and row["out_date"] <= date:
            continue
        for key in ("l1_code", "l2_code"):
            if row.get(key) in indices:
                indices[row[key]].add(code)
                included.add(code)
    if not included:
        raise RuntimeError("No listed companies matched dashboard sector codes")
    # Suspended stocks may not have today's observation; retain the true date.
    missing = sorted(code for code in included if cap_by_code.get(code, {}).get("total_mv") is None)
    print(f"Listed constituents: {len(included)}; checking {len(missing)} missing caps", flush=True)
    start = (datetime.strptime(date, "%Y%m%d") - timedelta(days=370)).strftime("%Y%m%d")
    for code in missing:
        rows = cached_call(call_api, token, "daily_basic",
                           {"ts_code": code, "start_date": start, "end_date": date}, CAP_FIELDS)
        valid = [r for r in rows if r.get("trade_date") and r["trade_date"] <= date
                 and observation_value(r, "total_mv") is not None]
        if valid:
            cap_by_code[code] = max(valid, key=lambda r: r["trade_date"])
    companies = {}
    for code in sorted(included):
        cap = cap_by_code.get(code, {})
        total = observation_value(cap, "total_mv")
        floating = observation_value(cap, "circ_mv")
        companies[code] = {
            "name": listed[code]["name"], "date": cap.get("trade_date"),
            "totalMvYi": round(total / 10000, 4) if total is not None else None,
            "circMvYi": round(floating / 10000, 4) if floating is not None else None,
        }
    def order(code):
        value = companies[code]["totalMvYi"]
        return (value is None, -(value or 0), code)
    payload = {
        "source": "Tushare index_member_all (SW2021, current) / stock_basic (listed) / daily_basic",
        "asOf": date, "generatedAt": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "units": {"totalMvYi": "亿元", "circMvYi": "亿元"},
        "companies": companies,
        "indices": {code: sorted(codes, key=order) for code, codes in indices.items()},
        "missingMarketCaps": [code for code, row in companies.items() if row["totalMvYi"] is None],
    }
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    (ROOT / "outputs/company_details_data.json").write_text(text)
    (ROOT / "outputs/company_details_data.js").write_text("window.COMPANY_DETAILS_DATA = " + text + ";\n")
    page = ROOT / "outputs/index.html"
    html = page.read_text()
    html = re.sub(r"(company_details_data\.js\?v=)[^\"\s]+",
                  lambda m: m[1] + hashlib.sha256(text.encode()).hexdigest()[:12], html)
    page.write_text(html)
    print(json.dumps({"companies": len(companies), "indices": len(indices),
                      "missingCaps": len(payload["missingMarketCaps"]), "asOf": date}), flush=True)


if __name__ == "__main__":
    main()
