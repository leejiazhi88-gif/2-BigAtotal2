import unittest

from build_real_sector_data import build_history, valuation_percentile_series
from weekly_sampling import sample_dates, weekly_dates


class WeeklySamplingTests(unittest.TestCase):
    def test_holiday_week_and_unfinished_week(self):
        # Friday is closed; the following week is only published through Tuesday.
        opens = ['20260427', '20260428', '20260429', '20260430', '20260504', '20260505']
        self.assertEqual(weekly_dates(opens, '20260427', '20260505'), ['20260430', '20260505'])

    def test_iso_week_crosses_calendar_year(self):
        self.assertEqual(weekly_dates(['20251229', '20251230', '20251231', '20260102', '20260105'],
                                     '20251229', '20260105'), ['20260102', '20260105'])

    def test_missing_friday_does_not_carry_thursday(self):
        rows = [{'trade_date': '20261105', 'pe': 6}, {'trade_date': '20261110', 'pe': 7}]
        self.assertEqual(sample_dates(rows, ['20261106', '20261110']),
                         [{'trade_date': '20261106'}, {'trade_date': '20261110', 'pe': 7}])

    def test_percentile_uses_daily_observations_not_weekly_points(self):
        rows = [{'trade_date': day, 'close': 100 + i, 'pe': pe, 'pb': 1, 'total_mv': 1000}
                for i, (day, pe) in enumerate(zip(
                    ['20261102', '20261103', '20261104', '20261105', '20261106', '20261109', '20261110'],
                    [2, 2, 3, 4, 8, 10, 5]))]
        metric = build_history(rows, [r['trade_date'] for r in rows], '20261110')
        p = metric['periods']['1']
        self.assertEqual(p['dates'], ['20261106', '20261110'])
        self.assertEqual(p['pe'], [8, 5])
        # Weekly-only ranks would be 100% and 50%, which are wrong for this page.
        self.assertEqual(p['pePercentileSeries'], [86, 71])
        self.assertEqual(p['pePercentile'], 71)
        self.assertEqual(valuation_percentile_series(rows, 'pe', rows)[-1], 71)

    def test_all_history_normalization_and_gaps(self):
        rows = [{'trade_date': '20261106', 'close': 50, 'pe': 5, 'total_mv': 1000},
                {'trade_date': '20261110', 'close': 60, 'pe': 6, 'total_mv': 1200}]
        metric = build_history(rows, ['20261030', '20261106', '20261110'], '20261110')
        self.assertEqual(metric['periods']['all']['price'], [None, 100, 120])
        self.assertEqual(metric['periods']['all']['pePercentileSeries'], [None, 50, 100])


if __name__ == '__main__':
    unittest.main()
