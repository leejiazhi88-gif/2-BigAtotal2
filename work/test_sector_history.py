import copy
import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from build_real_sector_data import build_history
from sector_history import FIELDS, START_DATE, load_history, save_history, update_dates, update_history
from tushare_fetch import date_chunks


def row(code, day, pe=5):
    return {"ts_code": code, "trade_date": day, "close": 100 + pe,
            "pe": pe, "pb": 1, "total_mv": 1000}


class IncrementalHistoryTests(unittest.TestCase):
    def test_three_days_use_five_requests_and_match_full_daily_ranks(self):
        days = ["20261106", "20261109", "20261110", "20261111", "20261112", "20261113"]
        full = {code: [row(code, day, i + 2) for i, day in enumerate(days)] for code in ["A", "B"]}
        old = {code: copy.deepcopy(rows[:3]) for code, rows in full.items()}
        old["A"][-1]["pe"] = 99  # A delayed correction must replace the old observation.
        old["C"] = []  # Indices without published history remain unavailable.
        calls = []

        def fetch(day):
            calls.append(day)
            return [r for rows in full.values() for r in rows if r["trade_date"] == day] + [row("OTHER", day)]

        merged = update_history(old, update_dates(days, "20261110"), fetch, {"A"})
        self.assertEqual(calls, days[1:])
        self.assertEqual(merged, {**full, "C": []})
        self.assertEqual(old["A"][-1]["pe"], 99)  # Never mutate the saved baseline.
        for code in full:
            self.assertEqual(build_history(copy.deepcopy(merged[code]), days, days[-1]),
                             build_history(copy.deepcopy(full[code]), days, days[-1]))

    def test_rejects_empty_partial_truncated_duplicate_and_wrong_date(self):
        invalid = [[], [row("B", "20261113")], [row("A", "20261112")],
                   [row("A", "20261113")] * 2, [row("A", "20261113")] * 4000]
        for response in invalid:
            with self.subTest(count=len(response)), self.assertRaises(ValueError):
                update_history({"A": []}, ["20261113"], lambda day: response, {"A"})

    def test_failure_does_not_change_previously_published_rows(self):
        original = {"A": [row("A", "20261110")]}
        baseline = copy.deepcopy(original)
        with self.assertRaises(ValueError):
            update_history(original, ["20261111", "20261112"],
                           lambda day: [row("A", day)] if day == "20261111" else [], {"A"})
        self.assertEqual(original, baseline)

    def test_repeat_still_rechecks_recent_days_without_duplicate_dates(self):
        days = ["20261111", "20261112", "20261113"]
        old = {"A": [row("A", day) for day in days]}
        result = update_history(old, update_dates(days, days[-1]), lambda day: [row("A", day)], {"A"})
        self.assertEqual(result, old)
        self.assertEqual(update_dates(days, days[-1]), days[-2:])
        self.assertEqual(update_dates(days, "20261112", overlap=0), ["20261113"])


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.snapshot = {"asOf": "20261113", "codes": {"Example": "A"},
                         "sourceSnapshotDate": "20261113", "generatedAt": "2026-11-13T20:00:00+08:00"}

    def test_immutable_compressed_snapshot_round_trip_and_checksum(self):
        rows = {"A": [row("A", "20261113")]}
        digest = save_history(self.root, "20261113", ["20261113"], rows)
        self.snapshot["rawHistorySnapshot"] = digest
        rows["A"][0]["pe"] = 99
        loaded = load_history(self.root, self.snapshot)
        self.assertEqual(loaded["rowsByCode"]["A"][0]["pe"], 5)
        self.assertEqual(loaded["openDates"], ["20261113"])
        target = self.root / "work/.tushare-cache/sector-history" / (digest + ".json.gz")
        content = gzip.decompress(target.read_bytes()).replace(b'"pe":5', b'"pe":9')
        target.write_bytes(gzip.compress(content))
        with self.assertRaisesRegex(ValueError, "checksum"):
            load_history(self.root, self.snapshot)

    def test_legacy_cache_migrates_without_network_or_weekly_approximations(self):
        cache = self.root / "work/.tushare-cache/20261113"
        cache.mkdir(parents=True)
        for start, end in date_chunks(START_DATE, "20261113", years=10):
            params = {"ts_code": "A", "start_date": start, "end_date": end}
            key = hashlib.sha256(json.dumps(["sw_daily", params, FIELDS], sort_keys=True).encode()).hexdigest()
            rows = [row("A", "20261112"), row("A", "20261113")] if start <= "20261113" <= end else []
            (cache / (key + ".json")).write_text(json.dumps(rows))
        history = load_history(self.root, self.snapshot)
        self.assertEqual(len(history["rowsByCode"]["A"]), 2)
        self.assertEqual(history["endDate"], "20261113")

    def test_missing_cache_fails_instead_of_substituting_other_snapshot(self):
        with self.assertRaises(FileNotFoundError):
            load_history(self.root, self.snapshot)

    def test_snapshot_date_must_match(self):
        digest = save_history(self.root, "20261112", ["20261112"], {"A": [row("A", "20261112")]})
        self.snapshot["rawHistorySnapshot"] = digest
        with self.assertRaisesRegex(ValueError, "does not match"):
            load_history(self.root, self.snapshot)


if __name__ == "__main__":
    unittest.main()
