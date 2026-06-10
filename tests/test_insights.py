"""Block 2 tests: groups, race, risk — hand-verified on the fixture roster."""

import datetime

import numpy as np
import pytest

from smfd.compute import groups, race, risk
from smfd.compute.returns import compute_scores, total_return_series


@pytest.fixture
def computed(fixture_roster):
    total = total_return_series(fixture_roster)
    scores = compute_scores(fixture_roster)
    return fixture_roster, total, scores


class TestGroups:
    def test_group_series_is_member_average(self, computed):
        game, total, _ = computed
        series = groups.group_return_series(total, game.group_map)
        # ANTY = mean(UP, FLAT); final day: (10 + 0) / 2 = 5
        assert series["ANTY"].iloc[-1] == pytest.approx(5.0)
        # UNCL = DOWN alone = -20; KIDZ = DIVY alone = 12.5 (10 price + 2.5 div)
        assert series["UNCL"].iloc[-1] == pytest.approx(-20.0)
        assert series["KIDZ"].iloc[-1] == pytest.approx(12.5)

    def test_standings_rank_and_fields(self, computed):
        game, total, scores = computed
        standings = groups.group_standings(total, scores, game.group_map)
        assert [s["etf"] for s in standings] == ["KIDZ", "ANTY", "UNCL"]
        kidz = standings[0]
        assert kidz["rank"] == 1
        assert kidz["members"] == 1
        assert kidz["best_ticker"] == "DIVY"
        anty = standings[1]
        assert anty["best_ticker"] == "UP"
        assert anty["worst_ticker"] == "FLAT"
        assert anty["winners"] == 2  # UP positive, FLAT exactly 0 counts as not-losing

    def test_spread(self, computed):
        game, total, scores = computed
        standings = groups.group_standings(total, scores, game.group_map)
        assert groups.group_spread(standings) == pytest.approx(12.5 - (-20.0))


class TestRace:
    def test_days_remaining(self):
        assert race.days_remaining(datetime.date(2027, 4, 14)) == 1
        assert race.days_remaining(datetime.date(2027, 4, 15)) == 0
        assert race.days_remaining(datetime.date(2027, 4, 16)) == 0  # never negative
        assert race.days_remaining(datetime.date(2026, 6, 9)) == 310  # PRD's own example

    def test_gap_to_leader(self, computed):
        game, total, scores = computed
        table = race.race_table(total, scores, today=datetime.date(2026, 6, 9))
        assert table.loc["DIVY", "gap_to_leader"] == pytest.approx(0.0)
        assert table.loc["UP", "gap_to_leader"] == pytest.approx(2.5)
        assert table.loc["DOWN", "gap_to_leader"] == pytest.approx(32.5)
        assert table.loc["DOWN", "gap_to_safety"] == pytest.approx(0.0)
        assert table.loc["DIVY", "gap_to_safety"] == pytest.approx(32.5)

    def test_projection_is_linear_extrapolation(self, computed):
        game, total, scores = computed
        today = datetime.date(2026, 6, 9)
        table = race.race_table(total, scores, today=today)
        remaining = race.trading_days_remaining(today)
        # UP gains exactly 10% over 4 steps -> slope 2.5%/day on a perfect line
        slope = np.polyfit(np.arange(5), total["UP"].values, 1)[0]
        assert table.loc["UP", "projected_final_pct"] == pytest.approx(10.0 + slope * remaining)

    def test_leader_can_always_catch_leader(self, computed):
        game, total, scores = computed
        table = race.race_table(total, scores, today=datetime.date(2026, 6, 9))
        assert bool(table.loc["DIVY", "can_catch_leader"]) is True

    def test_zero_vol_laggard_cannot_catch(self):
        # FLAT never moves -> volatility 0 -> any gap is uncatchable
        from tests.conftest import make_game
        dates = ["2026-03-06", "2026-03-09", "2026-03-10"]
        game = make_game({
            "LEAD": dict(zip(dates, [10.0, 11.0, 12.0])),
            "FLAT": dict(zip(dates, [10.0, 10.0, 10.0])),
        })
        total = total_return_series(game)
        scores = compute_scores(game)
        table = race.race_table(total, scores, today=datetime.date(2026, 6, 9))
        assert bool(table.loc["FLAT", "can_catch_leader"]) is False


class TestRisk:
    def test_flat_pick_has_zero_vol_and_drawdown(self, computed):
        game, total, scores = computed
        table = risk.risk_table(total, scores)
        assert table.loc["FLAT", "annualized_vol_pct"] == pytest.approx(0.0)
        assert table.loc["FLAT", "max_drawdown_pct"] == pytest.approx(0.0)

    def test_max_drawdown_hand_checked(self, computed):
        game, total, scores = computed
        table = risk.risk_table(total, scores)
        # DOWN only declines: 50 -> 40 means max drawdown -20%
        assert table.loc["DOWN", "max_drawdown_pct"] == pytest.approx(-20.0)
        # UP only rises: no drawdown
        assert table.loc["UP", "max_drawdown_pct"] == pytest.approx(0.0)

    def test_annualized_vol_hand_checked(self, computed):
        game, total, scores = computed
        table = risk.risk_table(total, scores)
        # UP daily value returns: 102/100, 104/102, 106/104, 110/106 minus 1
        daily = np.array([102 / 100, 104 / 102, 106 / 104, 110 / 106]) - 1
        expected = daily.std(ddof=1) * np.sqrt(252) * 100
        assert table.loc["UP", "annualized_vol_pct"] == pytest.approx(expected)

    def test_dividend_vs_price_split(self, computed):
        game, total, scores = computed
        table = risk.risk_table(total, scores)
        assert table.loc["DIVY", "price_return_pct"] == pytest.approx(10.0)
        assert table.loc["DIVY", "dividend_return_pct"] == pytest.approx(2.5)
        assert table.loc["DIVY", "dividend_share_pct"] == pytest.approx(2.5 / 12.5 * 100)
        assert table.loc["UP", "dividend_share_pct"] == pytest.approx(0.0)

    def test_group_risk_aggregates(self, computed):
        game, total, scores = computed
        table = risk.risk_table(total, scores)
        agg = risk.group_risk(table, game.group_map)
        assert agg.loc["ANTY", "total_return_pct"] == pytest.approx(5.0)
        assert list(agg.index) == ["KIDZ", "ANTY", "UNCL"]
