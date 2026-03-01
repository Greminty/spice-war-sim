import json

import pytest

from spice_war.game.battle import resolve_battle
from spice_war.models.configurable import ConfigurableModel
from spice_war.utils.data_structures import Alliance, GameState
from spice_war.utils.validation import ValidationError, load_model_config


def _alliance(aid, faction="red", power=100.0, spice=4_000_000):
    return Alliance(
        alliance_id=aid,
        faction=faction,
        power=power,
        starting_spice=spice,
        daily_spice_rate=50_000,
    )


def _state(alliances, spice_overrides=None):
    spice = {a.alliance_id: a.starting_spice for a in alliances}
    if spice_overrides:
        spice.update(spice_overrides)
    return GameState(
        current_spice=spice,
        brackets={},
        event_number=1,
        day="wednesday",
        event_history=[],
        alliances=alliances,
    )


def _model(matrix, seed=42, alliances=None):
    if alliances is None:
        alliances = [
            _alliance("a1"),
            _alliance("a2"),
            _alliance("d1", faction="blue"),
        ]
    config = {"random_seed": seed, "battle_outcome_matrix": {"wednesday": matrix}}
    return ConfigurableModel(config, alliances), alliances


def _write_json(tmp_path, name, data):
    p = tmp_path / name
    p.write_text(json.dumps(data))
    return str(p)


# ── Test 1: Custom-only pairing ──────────────────────────────────


class TestCustomOnly:
    def test_custom_only_pairing(self):
        """Pairing with only custom: 1.0 always produces 'custom' outcome."""
        matrix = {"a1": {"d1": {"custom": 1.0, "custom_theft_percentage": 15}}}
        model, alliances = _model(matrix)
        a1 = alliances[0]
        d1 = alliances[2]
        state = _state(alliances)

        outcome, probs = model.determine_battle_outcome(
            state, [a1], [d1], "wednesday"
        )
        assert outcome == "custom"
        assert probs["full_success"] == 0.0
        assert probs["partial_success"] == 0.0
        assert probs["custom"] == 1.0
        assert probs["fail"] == 0.0


# ── Test 2: Custom theft percentage applied ──────────────────────


class TestCustomTheftApplied:
    def test_custom_theft_percentage(self):
        """Transfers match defender_spice * 15 / 100."""
        transfers = resolve_battle(
            attackers=["a1"],
            primary_defender="d1",
            outcome_level="custom",
            damage_splits={"a1": 1.0},
            current_spice={"a1": 4_000_000, "d1": 4_000_000},
            custom_theft_percentage=15,
        )
        assert transfers["a1"] == 600_000
        assert transfers["d1"] == -600_000


# ── Test 3: Custom coexists with standard outcomes ───────────────


class TestCustomCoexists:
    def test_custom_and_full_success_both_appear(self):
        """Matrix with full_success: 0.3, custom: 0.5 produces both outcomes."""
        matrix = {
            "a1": {
                "d1": {
                    "full_success": 0.3,
                    "custom": 0.5,
                    "custom_theft_percentage": 10,
                }
            }
        }
        alliances = [_alliance("a1"), _alliance("d1", faction="blue")]
        outcomes = set()
        for seed in range(100):
            config = {
                "random_seed": seed,
                "battle_outcome_matrix": {"wednesday": matrix},
            }
            model = ConfigurableModel(config, alliances)
            state = _state(alliances)
            outcome, probs = model.determine_battle_outcome(
                state, [alliances[0]], [alliances[1]], "wednesday"
            )
            outcomes.add(outcome)

        assert "full_success" in outcomes
        assert "custom" in outcomes
        # partial_success not configured and custom present → defaults to 0
        assert "partial_success" not in outcomes


# ── Test 4: Fail is implicit remainder ───────────────────────────


class TestFailRemainder:
    def test_fail_probability(self):
        """full: 0.2, partial: 0.1, custom: 0.3 → fail = 0.4."""
        matrix = {
            "a1": {
                "d1": {
                    "full_success": 0.2,
                    "partial_success": 0.1,
                    "custom": 0.3,
                    "custom_theft_percentage": 10,
                }
            }
        }
        alliances = [_alliance("a1"), _alliance("d1", faction="blue")]
        model, _ = _model(matrix, alliances=alliances)
        state = _state(alliances)

        _, probs = model.determine_battle_outcome(
            state, [alliances[0]], [alliances[1]], "wednesday"
        )
        assert probs["fail"] == pytest.approx(0.4)


# ── Test 5: Heuristic never produces custom ──────────────────────


class TestHeuristicNoCustom:
    def test_heuristic_no_custom(self):
        """Unconfigured pairing returns only full/partial/fail."""
        alliances = [_alliance("a1"), _alliance("d1", faction="blue")]
        for seed in range(50):
            config = {"random_seed": seed}
            model = ConfigurableModel(config, alliances)
            state = _state(alliances)
            outcome, probs = model.determine_battle_outcome(
                state, [alliances[0]], [alliances[1]], "wednesday"
            )
            assert outcome != "custom"
            assert "custom" not in probs


# ── Test 6: Multi-attacker averaging ─────────────────────────────


class TestMultiAttackerAveraging:
    def test_both_have_custom(self):
        """Two attackers with custom configs → averaged probability and theft %."""
        matrix = {
            "a1": {
                "d1": {
                    "full_success": 0.0,
                    "custom": 0.4,
                    "custom_theft_percentage": 20,
                }
            },
            "a2": {
                "d1": {
                    "full_success": 0.0,
                    "custom": 0.6,
                    "custom_theft_percentage": 10,
                }
            },
        }
        model, alliances = _model(matrix)
        a1, a2, d1 = alliances
        state = _state(alliances)

        _, probs = model.determine_battle_outcome(
            state, [a1, a2], [d1], "wednesday"
        )
        assert probs["custom"] == pytest.approx(0.5)
        assert probs["custom_theft_percentage"] == pytest.approx(15.0)


# ── Test 7: Multi-attacker partial custom ────────────────────────


class TestMultiAttackerPartialCustom:
    def test_one_with_custom_one_without(self):
        """One attacker with custom, one without → probability halved, theft % not diluted."""
        matrix = {
            "a1": {
                "d1": {
                    "full_success": 0.0,
                    "custom": 0.4,
                    "custom_theft_percentage": 20,
                }
            },
            "a2": {
                "d1": {
                    "full_success": 0.0,
                }
            },
        }
        model, alliances = _model(matrix)
        a1, a2, d1 = alliances
        state = _state(alliances)

        _, probs = model.determine_battle_outcome(
            state, [a1, a2], [d1], "wednesday"
        )
        assert probs["custom"] == pytest.approx(0.2)
        assert probs["custom_theft_percentage"] == pytest.approx(20.0)


# ── Test 8: Validation — custom without theft % ──────────────────


class TestValidationCustomNoTheft:
    def test_missing_theft_percentage(self, tmp_path):
        """Config with custom but no custom_theft_percentage raises error."""
        data = {
            "battle_outcome_matrix": {
                "wednesday": {"a1": {"d1": {"custom": 0.5}}}
            }
        }
        path = _write_json(tmp_path, "model.json", data)
        with pytest.raises(ValidationError, match="missing 'custom_theft_percentage'"):
            load_model_config(path, {"a1", "d1"})


# ── Test 9: Validation — probabilities exceed 1.0 ────────────────


class TestValidationProbExceed:
    def test_probabilities_exceed_one(self, tmp_path):
        """full: 0.5, partial: 0.3, custom: 0.4 raises error."""
        data = {
            "battle_outcome_matrix": {
                "wednesday": {
                    "a1": {
                        "d1": {
                            "full_success": 0.5,
                            "partial_success": 0.3,
                            "custom": 0.4,
                            "custom_theft_percentage": 10,
                        }
                    }
                }
            }
        }
        path = _write_json(tmp_path, "model.json", data)
        with pytest.raises(ValidationError, match="exceeding 1.0"):
            load_model_config(path, {"a1", "d1"})


# ── Test 10: Custom theft 0% ─────────────────────────────────────


class TestCustomTheftZero:
    def test_zero_theft(self):
        """custom_theft_percentage: 0 transfers nothing."""
        transfers = resolve_battle(
            attackers=["a1"],
            primary_defender="d1",
            outcome_level="custom",
            damage_splits={"a1": 1.0},
            current_spice={"a1": 4_000_000, "d1": 4_000_000},
            custom_theft_percentage=0,
        )
        assert transfers["a1"] == 0
        assert transfers["d1"] == 0


# ── Test 11: Custom theft 30% ────────────────────────────────────


class TestCustomTheft30:
    def test_thirty_percent_theft(self):
        """custom_theft_percentage: 30 → 1,200,000 transferred."""
        transfers = resolve_battle(
            attackers=["a1"],
            primary_defender="d1",
            outcome_level="custom",
            damage_splits={"a1": 1.0},
            current_spice={"a1": 4_000_000, "d1": 4_000_000},
            custom_theft_percentage=30,
        )
        assert transfers["a1"] == 1_200_000
        assert transfers["d1"] == -1_200_000


# ── Test 12: Custom-only no derived partial ──────────────────────


class TestNoDerivedPartial:
    def test_no_derived_partial(self):
        """Pairing with only custom does not generate partial_success probability."""
        matrix = {"a1": {"d1": {"custom": 0.8, "custom_theft_percentage": 15}}}
        alliances = [_alliance("a1"), _alliance("d1", faction="blue")]
        model, _ = _model(matrix, alliances=alliances)
        state = _state(alliances)

        _, probs = model.determine_battle_outcome(
            state, [alliances[0]], [alliances[1]], "wednesday"
        )
        assert probs["partial_success"] == 0.0
        assert probs["full_success"] == 0.0


# ── Test 13: Deterministic with seed ─────────────────────────────


class TestDeterministicSeed:
    def test_same_seed_same_outcomes(self):
        """Same seed + custom config → identical outcome sequences."""
        matrix = {
            "a1": {
                "d1": {
                    "custom": 0.5,
                    "custom_theft_percentage": 15,
                }
            }
        }
        alliances = [_alliance("a1"), _alliance("d1", faction="blue")]
        state = _state(alliances)

        def run_sequence(seed):
            config = {
                "random_seed": seed,
                "battle_outcome_matrix": {"wednesday": matrix},
            }
            model = ConfigurableModel(config, alliances)
            return [
                model.determine_battle_outcome(
                    state, [alliances[0]], [alliances[1]], "wednesday"
                )[0]
                for _ in range(10)
            ]

        seq1 = run_sequence(42)
        seq2 = run_sequence(42)
        assert seq1 == seq2
