from __future__ import annotations

import json

import pytest

from spice_war.game.monte_carlo import MonteCarloResult, run_monte_carlo
from spice_war.utils.validation import load_model_config, load_state

FIXTURES = "tests/fixtures"


def _load_fixtures():
    alliances, schedule = load_state(f"{FIXTURES}/sample_state.json")
    alliance_ids = {a.alliance_id for a in alliances}
    model_config = load_model_config(f"{FIXTURES}/sample_model.json", alliance_ids)
    return alliances, schedule, model_config


@pytest.fixture(scope="module")
def mc_result():
    alliances, schedule, model_config = _load_fixtures()
    return run_monte_carlo(alliances, schedule, model_config, num_iterations=20, base_seed=0)


@pytest.fixture(scope="module")
def alliance_ids(mc_result):
    return list(mc_result.tier_counts.keys())


# ── Test 1: Deterministic with same base seed ──────────────────────

def test_deterministic_same_seed():
    alliances, schedule, model_config = _load_fixtures()
    r1 = run_monte_carlo(alliances, schedule, model_config, num_iterations=5, base_seed=0)
    r2 = run_monte_carlo(alliances, schedule, model_config, num_iterations=5, base_seed=0)
    assert r1.spice_totals == r2.spice_totals
    assert r1.tier_counts == r2.tier_counts


# ── Test 2: Different base seed → different results ─────────────────

def test_different_seed_different_results():
    alliances, schedule, model_config = _load_fixtures()
    r1 = run_monte_carlo(alliances, schedule, model_config, num_iterations=10, base_seed=0)
    r2 = run_monte_carlo(alliances, schedule, model_config, num_iterations=10, base_seed=100)
    assert r1.spice_totals != r2.spice_totals


# ── Test 3: Iteration count respected ──────────────────────────────

def test_iteration_count(mc_result, alliance_ids):
    for aid in alliance_ids:
        assert len(mc_result.spice_totals[aid]) == 20


# ── Test 4: Tier counts sum to num_iterations ──────────────────────

def test_tier_counts_sum(mc_result, alliance_ids):
    for aid in alliance_ids:
        assert sum(mc_result.tier_counts[aid].values()) == 20


# ── Test 5: Tier distribution sums to 1.0 ──────────────────────────

def test_tier_distribution_sums_to_one(mc_result, alliance_ids):
    for aid in alliance_ids:
        total = sum(mc_result.tier_distribution(aid).values())
        assert total == pytest.approx(1.0)


# ── Test 6: Spice stats correctness ────────────────────────────────

def test_spice_stats_correctness():
    alliances, schedule, model_config = _load_fixtures()
    result = run_monte_carlo(alliances, schedule, model_config, num_iterations=5, base_seed=0)

    # Pick first alliance and manually compute expected stats
    aid = alliances[0].alliance_id
    values = sorted(result.spice_totals[aid])
    n = len(values)

    stats = result.spice_stats(aid)
    assert stats["mean"] == round(sum(values) / n)
    assert stats["min"] == values[0]
    assert stats["max"] == values[-1]
    assert stats["p25"] == values[n // 4]
    assert stats["p75"] == values[3 * n // 4]

    # Median for odd n=5 should be the middle value
    assert stats["median"] == values[2]


# ── Test 7: Most likely tier ────────────────────────────────────────

def test_most_likely_tier(mc_result, alliance_ids):
    for aid in alliance_ids:
        counts = mc_result.tier_counts[aid]
        expected = max(range(1, 6), key=lambda t: counts[t])
        assert mc_result.most_likely_tier(aid) == expected


# ── Test 8: CLI runs without error ──────────────────────────────────

def test_cli_runs():
    from scripts.run_monte_carlo import main

    ret = main([
        f"{FIXTURES}/sample_state.json",
        f"{FIXTURES}/sample_model.json",
        "-n", "5",
        "--quiet",
    ])
    assert ret == 0


# ── Test 9: CLI --output writes valid JSON ──────────────────────────

def test_cli_output_json(tmp_path):
    from scripts.run_monte_carlo import main

    output_file = tmp_path / "mc_output.json"
    ret = main([
        f"{FIXTURES}/sample_state.json",
        f"{FIXTURES}/sample_model.json",
        "-n", "5",
        "--output", str(output_file),
        "--quiet",
    ])
    assert ret == 0

    data = json.loads(output_file.read_text())
    assert data["num_iterations"] == 5
    assert data["base_seed"] == 0
    assert "tier_distribution" in data
    assert "spice_stats" in data
    assert "raw_results" in data
    assert len(data["raw_results"]) == 5


# ── Test 10: CLI --quiet suppresses stdout ──────────────────────────

def test_cli_quiet(capsys):
    from scripts.run_monte_carlo import main

    main([
        f"{FIXTURES}/sample_state.json",
        f"{FIXTURES}/sample_model.json",
        "-n", "5",
        "--quiet",
    ])
    captured = capsys.readouterr()
    assert captured.out == ""
