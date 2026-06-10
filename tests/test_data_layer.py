"""Data-layer tests: staleness logic, split adjustment in the fetcher, legacy parity."""

import datetime
import json
from pathlib import Path

import pytest

from fetch_data import split_adjust_prices
from smfd import market_calendar
from smfd.config import TIMEZONE
from smfd.compute.rankings import compute_throne_history
from smfd.compute.returns import compute_scores, total_return_series
from smfd.data import load_game_data

FIXTURES = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).resolve().parent.parent


def _et(y, m, d, h, mi=0):
    return datetime.datetime(y, m, d, h, mi, tzinfo=TIMEZONE)


class TestStaleness:
    # 2026-06-05 is a Friday, 2026-06-08 a Monday
    def test_fresh_evening_fetch_is_not_stale(self):
        assert not market_calendar.is_stale(_et(2026, 6, 8, 21), now=_et(2026, 6, 9, 10))

    def test_weekend_is_not_stale(self):
        # Friday-night data viewed Sunday afternoon: no session missed
        assert not market_calendar.is_stale(_et(2026, 6, 5, 21), now=_et(2026, 6, 7, 15))

    def test_monday_daytime_is_not_stale(self):
        # Friday-night data on Monday 3pm: Monday's session hasn't closed yet
        assert not market_calendar.is_stale(_et(2026, 6, 5, 21), now=_et(2026, 6, 8, 15))

    def test_missed_fetch_flags_next_evening(self):
        # Friday-night data on Tuesday 7pm: Monday's close was >24h ago
        assert market_calendar.is_stale(_et(2026, 6, 5, 21), now=_et(2026, 6, 9, 19))

    def test_missing_as_of_is_stale(self):
        assert market_calendar.is_stale(None)


class TestSplitAdjustPrices:
    def test_forward_split_with_cliff(self):
        prices = {"X": {"2026-03-06": 100.0, "2026-03-09": 104.0,
                        "2026-03-10": 26.0, "2026-03-11": 27.0}}
        splits = {"X": [{"date": "2026-03-10", "ratio": 4.0}]}
        adj = split_adjust_prices(prices, splits)["X"]
        assert adj["2026-03-06"] == pytest.approx(25.0)
        assert adj["2026-03-09"] == pytest.approx(26.0)
        assert adj["2026-03-10"] == pytest.approx(26.0)  # split day untouched
        assert adj["2026-03-11"] == pytest.approx(27.0)

    def test_reverse_split_with_cliff(self):
        prices = {"X": {"2026-03-06": 1.0, "2026-03-09": 1.02, "2026-03-10": 10.0}}
        splits = {"X": [{"date": "2026-03-10", "ratio": 0.1}]}
        adj = split_adjust_prices(prices, splits)["X"]
        assert adj["2026-03-06"] == pytest.approx(10.0)

    def test_already_restated_series_is_untouched(self):
        """Yahoo normally restates history (PPLT's real 10:1 had no cliff) —
        adjusting again would manufacture a phantom +900% return."""
        prices = {"X": {"2026-03-06": 19.3, "2026-05-15": 17.9,
                        "2026-05-18": 17.8, "2026-05-19": 17.4}}
        splits = {"X": [{"date": "2026-05-18", "ratio": 10.0}]}
        adj = split_adjust_prices(prices, splits)["X"]
        assert adj == prices["X"]

    def test_no_splits_passthrough(self):
        prices = {"X": {"2026-03-06": 5.0}}
        assert split_adjust_prices(prices, {"X": []})["X"] == {"2026-03-06": 5.0}


class TestLegacyParity:
    """New compute on the legacy data file must reproduce the legacy app's numbers.

    Legacy total return = adjusted price return + summed-dividend/start * 100
    (the dividend double-count included — fixing that is the v2 format's job).
    """

    @pytest.fixture(scope="class")
    def legacy(self):
        data = load_game_data(
            players_path=ROOT / "players.json",
            stock_data_path=FIXTURES / "legacy_stock_data.json",
            now=_et(2026, 6, 9, 23),
        )
        with open(FIXTURES / "legacy_stock_data.json") as f:
            raw = json.load(f)
        return data, raw

    def test_detected_as_legacy(self, legacy):
        data, _ = legacy
        assert data.legacy_format

    def test_all_picks_match_legacy_formula(self, legacy):
        data, raw = legacy
        scores = compute_scores(data)
        for t in data.valid_tickers:
            series = {k: v for k, v in raw["prices"][t].items()}
            dates = sorted(series)
            start, end = series[dates[0]], series[dates[-1]]
            div = raw["dividends"].get(t, 0.0)
            legacy_total = (end / start - 1) * 100 + (div / start) * 100
            assert scores.loc[t, "total_return_pct"] == pytest.approx(legacy_total, abs=1e-6), t

    def test_throne_holders_match_legacy(self, legacy):
        """MVP and Benchwarmer (the headline) are the same picks the old app showed."""
        data, raw = legacy
        scores = compute_scores(data)
        legacy_totals = {}
        for t in data.valid_tickers:
            series = raw["prices"][t]
            dates = sorted(series)
            div = raw["dividends"].get(t, 0.0)
            legacy_totals[t] = ((series[dates[-1]] / series[dates[0]] - 1) * 100
                                + (div / series[dates[0]]) * 100)
        assert scores.index[0] == max(legacy_totals, key=legacy_totals.get)
        assert scores.index[-1] == min(legacy_totals, key=legacy_totals.get)
        throne = compute_throne_history(total_return_series(data), data.name_map)
        assert throne["mvp_history"][0]["ticker"] == scores.index[0]
        assert throne["bench_history"][0]["ticker"] == scores.index[-1]
