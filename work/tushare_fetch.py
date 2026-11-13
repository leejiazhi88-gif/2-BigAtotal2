"""Bounded date ranges and resumable, credential-free response caches."""

import hashlib
import json
import time
import urllib.error
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def cached_call(call, token, api, params, fields, *, force=False):
    day = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d")
    cache = Path(__file__).parent / ".tushare-cache" / day
    request = json.dumps([api, params, fields], sort_keys=True)
    target = cache / (hashlib.sha256(request.encode()).hexdigest() + ".json")
    mutable = str(params.get("trade_date") or params.get("end_date") or "") >= day
    if target.is_file() and not mutable and not force:
        return json.loads(target.read_text(encoding="utf-8"))
    for attempt in range(3):
        try:
            rows = call(token, api, params, fields)
            break
        except (urllib.error.URLError, TimeoutError) as exc:
            if isinstance(exc, urllib.error.HTTPError) and exc.code not in (408, 429, 500, 502, 503, 504):
                raise
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    cache.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(rows, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    temporary.replace(target)
    return rows


def date_chunks(start, end, years=1):
    """Yield inclusive, nonoverlapping year ranges, always below API row caps."""
    year = int(start[:4])
    while year <= int(end[:4]):
        last_year = min(year + years - 1, int(end[:4]))
        yield max(start, f"{year}0101"), min(end, f"{last_year}1231")
        year = last_year + 1
