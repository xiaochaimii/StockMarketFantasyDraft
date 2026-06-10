"""Canonical scoring tests — these protect the number that decides who wins."""

import datetime

import pytest

from smfd.compute.returns import compute_scores, total_return_series
from smfd.data import split_adjust_dividends
from tests.conftest import make_game


def test_no_div_no_split_equals_simple_price_return(fixture_roster):
    """(a) A no-dividend, no-split pick scores exactly its price return."""
    scores = compute_scores(fixture_roster)
    assert scores.loc["UP", "total_return_pct"] == pytest.approx(10.0)
    assert scores.loc["UP", "total_return_pct"] == pytest.approx(scores.loc["UP", "price_return_pct"])
    assert scores.loc["DOWN", "total_return_pct"] == pytest.approx(-20.0)
    assert scores.loc["FLAT", "total_return_pct"] == pytest.approx(0.0)


def test_dividend_adds_exactly_the_cash(fixture_roster):
    """(b) A dividend payer's total return exceeds its price return by exactly the cash."""
    scores = compute_scores(fixture_roster)
    units = 10.0 / 20.0
    expected_cash = units * 0.50
    assert scores.loc["DIVY", "dividend_income"] == pytest.approx(expected_cash)
    assert scores.loc["DIVY", "total_return_pct"] - scores.loc["DIVY", "price_return_pct"] == \
        pytest.approx(expected_cash / 10.0 * 100)
    # And the daily series picks the cash up on the ex-date, not before
    series = total_return_series(fixture_roster)
    assert series.loc["2026-03-09", "DIVY"] == pytest.approx(0.0)        # before ex-date: price flat
    assert series.loc["2026-03-10", "DIVY"] == pytest.approx(5.0 + 2.5)  # +5% price, +2.5% dividend


def test_split_return_is_continuous():
    """(c) A 4:1 split must not create a phantom -75% drop."""
    # Raw prices: 100, 104, then 4:1 split -> trades at ~26, 27
    # Split-adjusted series (what GameData.prices holds): 25, 26, 26, 27
    dates = ["2026-03-06", "2026-03-09", "2026-03-10", "2026-03-11"]
    game = make_game(
        {"SPLITTY": dict(zip(dates, [25.0, 26.0, 26.0, 27.0]))},
        splits={"SPLITTY": [(datetime.date(2026, 3, 10), 4.0)]},
    )
    series = total_return_series(game)["SPLITTY"]
    assert series.iloc[1] == pytest.approx(4.0)   # +4% pre-split
    assert series.iloc[2] == pytest.approx(4.0)   # split day: still +4%, no cliff
    assert series.iloc[3] == pytest.approx(8.0)
    scores = compute_scores(game)
    assert scores.loc["SPLITTY", "total_return_pct"] == pytest.approx(8.0)
    # Units are constant in split-adjusted space
    assert scores.loc["SPLITTY", "units"] == pytest.approx(10.0 / 25.0)


def test_pre_split_dividend_is_basis_adjusted():
    """(d) A dividend paid before a split contributes the right cash.

    $1.00/share paid on pre-split shares == $0.25/share in post-4:1 basis.
    Units are in today's basis, so the as-paid amount must be divided by the
    later split ratio or the cash would be 4x too large.
    """
    splits = [(datetime.date(2026, 3, 10), 4.0)]
    adjusted = split_adjust_dividends([(datetime.date(2026, 3, 9), 1.00)], splits)
    assert adjusted == [(datetime.date(2026, 3, 9), pytest.approx(0.25))]
    # A dividend on/after the split date is untouched
    adjusted = split_adjust_dividends([(datetime.date(2026, 3, 10), 1.00)], splits)
    assert adjusted == [(datetime.date(2026, 3, 10), pytest.approx(1.00))]

    dates = ["2026-03-06", "2026-03-09", "2026-03-10", "2026-03-11"]
    game = make_game(
        {"SPLITTY": dict(zip(dates, [25.0, 26.0, 26.0, 27.0]))},
        splits={"SPLITTY": [(datetime.date(2026, 3, 10), 4.0)]},
        dividends={"SPLITTY": split_adjust_dividends(
            [(datetime.date(2026, 3, 9), 1.00)],
            [(datetime.date(2026, 3, 10), 4.0)],
        )},
    )
    scores = compute_scores(game)
    units = 10.0 / 25.0
    assert scores.loc["SPLITTY", "dividend_income"] == pytest.approx(units * 0.25)


def test_leaderboard_ranks_on_total_return(fixture_roster):
    """DIVY's +10% price +2.5% dividend beats UP's +10% price — dividends count."""
    scores = compute_scores(fixture_roster)
    assert list(scores.index) == ["DIVY", "UP", "FLAT", "DOWN"]


def test_window_subsets_recompute_baseline(fixture_roster):
    """A custom window re-bases units to the window's first close."""
    scores = compute_scores(fixture_roster, start="2026-03-09", end="2026-03-11")
    assert scores.loc["UP", "total_return_pct"] == pytest.approx((106 / 102 - 1) * 100)
    # Dividend ex-date 03-10 falls inside this window, so it still counts
    assert scores.loc["DIVY", "dividend_income"] > 0
    # ...but not in a window that ends before it
    early = compute_scores(fixture_roster, start="2026-03-06", end="2026-03-09")
    assert early.loc["DIVY", "dividend_income"] == 0
