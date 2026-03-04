"""Tests for MC randomness enhancements (0014).

35 tests covering stochastic targeting, power fluctuation, outcome noise,
and their combinations.
"""

from __future__ import annotations

from collections import Counter

import pytest

from spice_war.game.simulator import simulate_war
from spice_war.models.configurable import ConfigurableModel
from spice_war.utils.data_structures import Alliance, EventConfig, GameState
from spice_war.utils.validation import load_model_config, load_state

FIXTURES = "tests/fixtures"


def _alliance(aid, faction="red", power=100, spice=1_000_000):
    return Alliance(
        alliance_id=aid,
        faction=faction,
        power=power,
        starting_spice=spice,
        daily_spice_rate=50_000,
    )


def _state(alliances, spice=None, event_number=1, day="wednesday"):
    if spice is None:
        spice = {a.alliance_id: a.starting_spice for a in alliances}
    return GameState(
        current_spice=spice,
        brackets={},
        event_number=event_number,
        day=day,
        event_history=[],
        alliances=alliances,
    )


def _sample_alliances():
    """Two red attackers, two blue defenders with distinct powers."""
    return [
        _alliance("r1", "red", power=110, spice=2_000_000),
        _alliance("r2", "red", power=85, spice=1_500_000),
        _alliance("b1", "blue", power=95, spice=1_800_000),
        _alliance("b2", "blue", power=70, spice=900_000),
    ]


def _sample_schedule():
    return [
        EventConfig(attacker_faction="red", day="wednesday", days_before=3),
        EventConfig(attacker_faction="blue", day="saturday", days_before=4),
    ]


def _run_war(config, alliances=None, schedule=None):
    if alliances is None:
        alliances = _sample_alliances()
    if schedule is None:
        schedule = _sample_schedule()
    model = ConfigurableModel(config, alliances)
    return simulate_war(alliances, schedule, model)


# ── Stochastic Targeting (tests 1–10) ───────────────────────────────


class TestStochasticTargeting:
    def test_01_temperature_zero_matches_current(self):
        """With targeting_temperature: 0, targeting is identical to existing deterministic behavior."""
        config_base = {"random_seed": 42}
        config_t0 = {"random_seed": 42, "targeting_temperature": 0.0}
        r1 = _run_war(config_base)
        r2 = _run_war(config_t0)
        assert r1["final_spice"] == r2["final_spice"]
        assert r1["rankings"] == r2["rankings"]

    def test_02_temperature_produces_varied_targets(self):
        """Different seeds with temperature > 0 produce different target assignments."""
        alliances = _sample_alliances()
        targets_seen = set()
        for seed in range(50):
            config = {"random_seed": seed, "targeting_temperature": 0.5}
            model = ConfigurableModel(config, alliances)
            model.set_effective_powers()
            state = _state(alliances)
            attackers = [a for a in alliances if a.faction == "red"]
            defenders = [a for a in alliances if a.faction == "blue"]
            targets = model.generate_targets(state, attackers, defenders, 1)
            targets_seen.add(tuple(sorted(targets.items())))
        assert len(targets_seen) > 1

    def test_03_high_temperature_approaches_uniform(self):
        """With very high temperature, target distribution is approximately uniform."""
        alliances = _sample_alliances()
        target_counts: Counter[str] = Counter()
        n_trials = 500
        for seed in range(n_trials):
            config = {"random_seed": seed, "targeting_temperature": 100.0}
            model = ConfigurableModel(config, alliances)
            model.set_effective_powers()
            state = _state(alliances)
            attackers = [a for a in alliances if a.faction == "red"]
            defenders = [a for a in alliances if a.faction == "blue"]
            targets = model.generate_targets(state, attackers, defenders, 1)
            # The strongest attacker picks first — track what they pick
            target_counts[targets["r1"]] += 1
        # With uniform selection, each defender should get ~50%
        for count in target_counts.values():
            assert 0.30 * n_trials < count < 0.70 * n_trials

    def test_04_low_temperature_strongly_favors_best(self):
        """With low temperature, the best target is selected almost always."""
        alliances = _sample_alliances()
        target_counts: Counter[str] = Counter()
        n_trials = 200
        for seed in range(n_trials):
            config = {"random_seed": seed, "targeting_temperature": 0.01}
            model = ConfigurableModel(config, alliances)
            model.set_effective_powers()
            state = _state(alliances)
            attackers = [a for a in alliances if a.faction == "red"]
            defenders = [a for a in alliances if a.faction == "blue"]
            targets = model.generate_targets(state, attackers, defenders, 1)
            target_counts[targets["r1"]] += 1
        # The best target should dominate
        best_target = target_counts.most_common(1)[0][0]
        assert target_counts[best_target] > 0.90 * n_trials

    def test_05_pinned_targets_unaffected(self):
        """Explicit target pins are always respected regardless of temperature."""
        alliances = _sample_alliances()
        config = {
            "random_seed": 42,
            "targeting_temperature": 100.0,
            "event_targets": {"1": {"r1": "b2"}},
        }
        model = ConfigurableModel(config, alliances)
        model.set_effective_powers()
        state = _state(alliances)
        attackers = [a for a in alliances if a.faction == "red"]
        defenders = [a for a in alliances if a.faction == "blue"]
        targets = model.generate_targets(state, attackers, defenders, 1)
        assert targets["r1"] == "b2"

    def test_06_single_defender_deterministic(self):
        """Only one candidate defender — selected regardless of temperature."""
        alliances = [
            _alliance("r1", "red", power=110),
            _alliance("b1", "blue", power=95),
        ]
        config = {"random_seed": 42, "targeting_temperature": 1.0}
        model = ConfigurableModel(config, alliances)
        model.set_effective_powers()
        state = _state(alliances)
        targets = model.generate_targets(state, [alliances[0]], [alliances[1]], 1)
        assert targets["r1"] == "b1"

    def test_07_all_scores_zero_uniform(self):
        """All defenders have 0 ESV — selection is uniform random."""
        alliances = [
            _alliance("r1", "red", power=110),
            _alliance("b1", "blue", power=95, spice=0),
            _alliance("b2", "blue", power=70, spice=0),
        ]
        config = {"random_seed": 42, "targeting_temperature": 0.5}
        model = ConfigurableModel(config, alliances)
        model.set_effective_powers()
        state = _state(alliances, spice={"r1": 1_000_000, "b1": 0, "b2": 0})
        attackers = [alliances[0]]
        defenders = [alliances[1], alliances[2]]
        # With 0 spice, ESV is 0 for all — should get uniform random
        target_counts: Counter[str] = Counter()
        for seed in range(200):
            config["random_seed"] = seed
            model = ConfigurableModel(config, alliances)
            model.set_effective_powers()
            targets = model.generate_targets(state, attackers, defenders, 1)
            target_counts[targets["r1"]] += 1
        # Both should be picked roughly equally
        assert target_counts["b1"] > 50
        assert target_counts["b2"] > 50

    def test_08_deterministic_with_seed(self):
        """Same seed + same temperature → identical target assignments."""
        alliances = _sample_alliances()
        config = {"random_seed": 42, "targeting_temperature": 0.5}
        results = []
        for _ in range(3):
            model = ConfigurableModel(config, alliances)
            model.set_effective_powers()
            state = _state(alliances)
            attackers = [a for a in alliances if a.faction == "red"]
            defenders = [a for a in alliances if a.faction == "blue"]
            targets = model.generate_targets(state, attackers, defenders, 1)
            results.append(targets)
        assert results[0] == results[1] == results[2]

    def test_09_priority_order_preserved(self):
        """Strongest attacker still picks first."""
        alliances = _sample_alliances()
        # r1 (power=110) should pick before r2 (power=85)
        # With temperature, r1 picks from both defenders; r2 picks from remainder
        config = {"random_seed": 42, "targeting_temperature": 0.5}
        model = ConfigurableModel(config, alliances)
        model.set_effective_powers()
        state = _state(alliances)
        attackers = [a for a in alliances if a.faction == "red"]
        defenders = [a for a in alliances if a.faction == "blue"]
        targets = model.generate_targets(state, attackers, defenders, 1)
        # Both attackers should have targets assigned
        assert "r1" in targets
        assert "r2" in targets
        # Targets should be different defenders
        assert targets["r1"] != targets["r2"]

    def test_10_works_with_highest_spice_strategy(self):
        """Temperature applies to spice-based scores, not just ESV."""
        alliances = _sample_alliances()
        target_counts: Counter[str] = Counter()
        for seed in range(100):
            config = {
                "random_seed": seed,
                "targeting_temperature": 0.5,
                "targeting_strategy": "highest_spice",
            }
            model = ConfigurableModel(config, alliances)
            model.set_effective_powers()
            state = _state(alliances)
            attackers = [a for a in alliances if a.faction == "red"]
            defenders = [a for a in alliances if a.faction == "blue"]
            targets = model.generate_targets(state, attackers, defenders, 1)
            target_counts[targets["r1"]] += 1
        # b1 has more spice so should be favored, but b2 should appear sometimes
        assert target_counts["b1"] > target_counts["b2"]
        assert target_counts["b2"] > 0


# ── Power Fluctuation (tests 11–20) ─────────────────────────────────


class TestPowerFluctuation:
    def test_11_noise_zero_matches_current(self):
        """With power_noise: 0, all results identical to existing behavior."""
        config_base = {"random_seed": 42}
        config_n0 = {"random_seed": 42, "power_noise": 0.0}
        r1 = _run_war(config_base)
        r2 = _run_war(config_n0)
        assert r1["final_spice"] == r2["final_spice"]
        assert r1["rankings"] == r2["rankings"]

    def test_12_noise_produces_varied_outcomes(self):
        """Same scenario with different seeds and power_noise produces different outcomes."""
        results = set()
        for seed in range(20):
            r = _run_war({"random_seed": seed, "power_noise": 0.1})
            results.add(tuple(sorted(r["final_spice"].items())))
        assert len(results) > 1

    def test_13_base_power_unchanged(self):
        """After simulation, Alliance.power values are identical to their original values."""
        alliances = _sample_alliances()
        original_powers = {a.alliance_id: a.power for a in alliances}
        _run_war({"random_seed": 42, "power_noise": 0.2}, alliances=alliances)
        for a in alliances:
            assert a.power == original_powers[a.alliance_id]

    def test_14_effective_power_within_range(self):
        """With power_noise: 0.1, effective powers are within [0.9*base, 1.1*base]."""
        alliances = _sample_alliances()
        for seed in range(50):
            config = {"random_seed": seed, "power_noise": 0.1}
            model = ConfigurableModel(config, alliances)
            model.set_effective_powers()
            for a in alliances:
                eff = model._get_power(a.alliance_id)
                assert 0.9 * a.power <= eff <= 1.1 * a.power, (
                    f"seed={seed}, {a.alliance_id}: eff={eff}, base={a.power}"
                )

    def test_15_within_event_consistency(self):
        """Same event uses same effective powers for targeting, battle, and damage."""
        alliances = _sample_alliances()
        config = {"random_seed": 42, "power_noise": 0.1}
        model = ConfigurableModel(config, alliances)
        model.set_effective_powers()
        # Read effective powers twice — should be the same
        powers_1 = {a.alliance_id: model._get_power(a.alliance_id) for a in alliances}
        powers_2 = {a.alliance_id: model._get_power(a.alliance_id) for a in alliances}
        assert powers_1 == powers_2

    def test_16_different_events_different_powers(self):
        """Event 1 and event 2 use different effective power values."""
        alliances = _sample_alliances()
        config = {"random_seed": 42, "power_noise": 0.1}
        model = ConfigurableModel(config, alliances)

        model.set_effective_powers()
        powers_event1 = {a.alliance_id: model._get_power(a.alliance_id) for a in alliances}

        model.set_effective_powers()
        powers_event2 = {a.alliance_id: model._get_power(a.alliance_id) for a in alliances}

        assert powers_event1 != powers_event2

    def test_17_deterministic_with_seed(self):
        """Same seed + same noise → identical effective powers and results."""
        alliances = _sample_alliances()
        config = {"random_seed": 42, "power_noise": 0.1}
        r1 = _run_war(config, alliances=list(alliances))
        alliances2 = _sample_alliances()
        r2 = _run_war(config, alliances=alliances2)
        assert r1["final_spice"] == r2["final_spice"]

    def test_18_matrix_probabilities_unaffected(self):
        """Explicit matrix entries are used as-is; only heuristic paths use effective power."""
        alliances = _sample_alliances()
        matrix = {
            "wednesday": {
                "r1": {"b1": {"full_success": 0.9, "partial_success": 0.08}},
            }
        }
        config = {"random_seed": 42, "power_noise": 0.5, "battle_outcome_matrix": matrix}
        model = ConfigurableModel(config, alliances)
        model.set_effective_powers()
        state = _state(alliances)
        # Matrix entry should be returned unchanged by lookup
        probs = model._lookup_or_heuristic(matrix, alliances[0], alliances[2], "wednesday")
        assert probs["full_success"] == 0.9
        assert probs["partial_success"] == 0.08

    def test_19_damage_splits_use_effective_power(self):
        """Heuristic damage splits reflect fluctuated power, not base power."""
        alliances = _sample_alliances()
        # Run with different noise levels — splits should differ
        splits_seen = set()
        for seed in range(20):
            config = {"random_seed": seed, "power_noise": 0.3}
            model = ConfigurableModel(config, alliances)
            model.set_effective_powers()
            state = _state(alliances)
            attackers = [alliances[0], alliances[1]]  # r1, r2
            defender = alliances[2]  # b1
            splits = model.determine_damage_splits(state, attackers, defender)
            splits_seen.add(round(splits["r1"], 4))
        assert len(splits_seen) > 1

    def test_20_heuristic_probabilities_use_effective_power(self):
        """Power ratio in heuristic formula uses effective power values."""
        alliances = _sample_alliances()
        probs_seen = set()
        for seed in range(20):
            config = {"random_seed": seed, "power_noise": 0.3}
            model = ConfigurableModel(config, alliances)
            model.set_effective_powers()
            probs = model._heuristic_probabilities(alliances[0], alliances[2], "wednesday")
            probs_seen.add(round(probs["full_success"], 4))
        assert len(probs_seen) > 1


# ── Outcome Probability Noise (tests 21–32) ─────────────────────────


class TestOutcomeNoise:
    def test_21_noise_zero_matches_current(self):
        """With outcome_noise: 0, all results identical to existing behavior."""
        config_base = {"random_seed": 42}
        config_n0 = {"random_seed": 42, "outcome_noise": 0.0}
        r1 = _run_war(config_base)
        r2 = _run_war(config_n0)
        assert r1["final_spice"] == r2["final_spice"]
        assert r1["rankings"] == r2["rankings"]

    def test_22_noise_produces_varied_outcomes(self):
        """Same scenario with different seeds and outcome_noise produces different outcomes."""
        results = set()
        for seed in range(20):
            r = _run_war({"random_seed": seed, "outcome_noise": 0.05})
            results.add(tuple(sorted(r["final_spice"].items())))
        assert len(results) > 1

    def test_23_per_pairing_offsets_independent(self):
        """Two different attacker-defender pairings get different perturbation offsets."""
        alliances = _sample_alliances()
        config = {"random_seed": 42, "outcome_noise": 0.1}
        model = ConfigurableModel(config, alliances)
        offsets_r1_b1 = model._pairing_offsets[("r1", "b1")]
        offsets_r1_b2 = model._pairing_offsets[("r1", "b2")]
        # Offsets should differ (extremely unlikely to be identical)
        assert offsets_r1_b1 != offsets_r1_b2

    def test_24_same_pairing_consistent_across_events(self):
        """If the same attacker fights the same defender in two events, same offsets apply."""
        alliances = _sample_alliances()
        config = {"random_seed": 42, "outcome_noise": 0.1}
        model = ConfigurableModel(config, alliances)
        probs_base = {"full_success": 0.5, "partial_success": 0.3}
        p1 = model._apply_outcome_noise(probs_base, "r1", "b1")
        p2 = model._apply_outcome_noise(dict(probs_base), "r1", "b1")
        assert p1["full_success"] == p2["full_success"]
        assert p1["partial_success"] == p2["partial_success"]

    def test_25_different_seeds_different_offsets(self):
        """Two simulations with different seeds get different offsets for the same pairing."""
        alliances = _sample_alliances()
        m1 = ConfigurableModel({"random_seed": 1, "outcome_noise": 0.1}, alliances)
        m2 = ConfigurableModel({"random_seed": 2, "outcome_noise": 0.1}, alliances)
        assert m1._pairing_offsets[("r1", "b1")] != m2._pairing_offsets[("r1", "b1")]

    def test_26_perturbed_probabilities_stay_valid(self):
        """After perturbation, all probabilities are >= 0 and sum to <= 1 (plus fail)."""
        alliances = _sample_alliances()
        for seed in range(50):
            config = {"random_seed": seed, "outcome_noise": 0.2}
            model = ConfigurableModel(config, alliances)
            model.set_effective_powers()
            state = _state(alliances)
            attackers = [alliances[0]]
            defenders = [alliances[2]]
            _, combined = model.determine_battle_outcome(
                state, attackers, defenders, "wednesday"
            )
            assert combined["full_success"] >= 0
            assert combined["partial_success"] >= 0
            assert combined["fail"] >= 0
            total = (
                combined["full_success"]
                + combined["partial_success"]
                + combined.get("custom", 0.0)
                + combined["fail"]
            )
            assert total == pytest.approx(1.0, abs=1e-9)

    def test_27_applies_to_matrix_configured(self):
        """Explicit matrix entries are perturbed, unlike power_noise."""
        alliances = _sample_alliances()
        matrix = {
            "wednesday": {
                "r1": {"b1": {"full_success": 0.5, "partial_success": 0.3}},
            }
        }
        config = {
            "random_seed": 42,
            "outcome_noise": 0.1,
            "battle_outcome_matrix": matrix,
        }
        model = ConfigurableModel(config, alliances)
        model.set_effective_powers()
        state = _state(alliances)
        _, combined = model.determine_battle_outcome(
            state, [alliances[0]], [alliances[2]], "wednesday"
        )
        # With noise, the probabilities should differ from the matrix values
        offsets = model._pairing_offsets[("r1", "b1")]
        # At least one should be perturbed away from exact matrix values
        assert combined["full_success"] != 0.5 or combined["partial_success"] != 0.3

    def test_28_applies_to_heuristic(self):
        """Heuristic-derived probabilities are also perturbed."""
        alliances = _sample_alliances()
        # No matrix — heuristic path
        probs_seen = set()
        for seed in range(20):
            config = {"random_seed": seed, "outcome_noise": 0.1}
            model = ConfigurableModel(config, alliances)
            model.set_effective_powers()
            state = _state(alliances)
            _, combined = model.determine_battle_outcome(
                state, [alliances[0]], [alliances[2]], "wednesday"
            )
            probs_seen.add(round(combined["full_success"], 4))
        # Different seeds → different offsets → different perturbed heuristics
        assert len(probs_seen) > 1

    def test_29_custom_outcome_perturbed(self):
        """Custom probability is perturbed; custom_theft_percentage is not."""
        alliances = _sample_alliances()
        matrix = {
            "wednesday": {
                "r1": {
                    "b1": {
                        "full_success": 0.3,
                        "partial_success": 0.0,
                        "custom": 0.4,
                        "custom_theft_percentage": 25.0,
                    }
                }
            }
        }
        config = {
            "random_seed": 42,
            "outcome_noise": 0.1,
            "battle_outcome_matrix": matrix,
        }
        model = ConfigurableModel(config, alliances)
        model.set_effective_powers()
        state = _state(alliances)
        _, combined = model.determine_battle_outcome(
            state, [alliances[0]], [alliances[2]], "wednesday"
        )
        # custom_theft_percentage should be unchanged
        assert combined["custom_theft_percentage"] == 25.0
        # custom probability may be shifted
        offsets = model._pairing_offsets[("r1", "b1")]
        if offsets["custom"] != 0.0:
            assert combined.get("custom", 0.0) != 0.4 or combined["full_success"] != 0.3

    def test_30_normalization_when_sum_exceeds_1(self):
        """Large noise that pushes total above 1 results in proportional normalization."""
        alliances = _sample_alliances()
        # Use high noise so some seed produces sum > 1
        config = {"random_seed": 42, "outcome_noise": 0.5}
        model = ConfigurableModel(config, alliances)
        # Manually test with high base probabilities
        probs = {"full_success": 0.8, "partial_success": 0.5}
        result = model._apply_outcome_noise(probs, "r1", "b1")
        total = result["full_success"] + result["partial_success"]
        assert total <= 1.0 + 1e-9
        assert result["full_success"] >= 0
        assert result["partial_success"] >= 0

    def test_31_deterministic_with_seed(self):
        """Same seed + same noise → identical offsets and results."""
        config = {"random_seed": 42, "outcome_noise": 0.05}
        r1 = _run_war(config)
        r2 = _run_war(config)
        assert r1["final_spice"] == r2["final_spice"]

    def test_32_interaction_with_power_noise(self):
        """Both active — power_noise changes base heuristic per event, outcome_noise applies fixed offsets on top."""
        results_both = set()
        results_outcome_only = set()
        for seed in range(20):
            r = _run_war({"random_seed": seed, "power_noise": 0.1, "outcome_noise": 0.05})
            results_both.add(tuple(sorted(r["final_spice"].items())))
            r2 = _run_war({"random_seed": seed, "outcome_noise": 0.05})
            results_outcome_only.add(tuple(sorted(r2["final_spice"].items())))
        # Adding power_noise on top should change some results
        assert results_both != results_outcome_only


# ── Combined (tests 33–35) ──────────────────────────────────────────


class TestCombined:
    def test_33_all_three_features_together(self):
        """All features active — simulation runs without error and produces varied results."""
        results = set()
        for seed in range(20):
            config = {
                "random_seed": seed,
                "targeting_temperature": 0.5,
                "power_noise": 0.1,
                "outcome_noise": 0.05,
            }
            r = _run_war(config)
            results.add(tuple(sorted(r["final_spice"].items())))
        assert len(results) > 1

    def test_34_no_features_backward_compat(self):
        """Config with no noise/temperature fields produces identical results to current code."""
        config_empty = {"random_seed": 42}
        config_zeros = {
            "random_seed": 42,
            "targeting_temperature": 0.0,
            "power_noise": 0.0,
            "outcome_noise": 0.0,
        }
        r1 = _run_war(config_empty)
        r2 = _run_war(config_zeros)
        assert r1["final_spice"] == r2["final_spice"]
        assert r1["rankings"] == r2["rankings"]

    def test_35_full_mc_sweep_distribution(self):
        """Running N simulations with all features produces a distribution of final rankings."""
        from spice_war.game.monte_carlo import run_monte_carlo

        alliances = _sample_alliances()
        schedule = _sample_schedule()
        config = {
            "random_seed": 0,
            "targeting_temperature": 0.5,
            "power_noise": 0.1,
            "outcome_noise": 0.05,
        }
        result = run_monte_carlo(alliances, schedule, config, num_iterations=30, base_seed=0)
        # At least one alliance should have more than one tier in its distribution
        has_variation = False
        for aid in result.tier_counts:
            if len(result.tier_counts[aid]) > 1:
                has_variation = True
                break
        assert has_variation, "MC sweep with all features should produce ranking variation"
