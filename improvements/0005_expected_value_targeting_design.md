# Expected Value Targeting — Design

## Overview

Replaces the default targeting heuristic with an Expected Spice Value (ESV) maximizer. Each attacker evaluates all available defenders, computing the expected stolen spice across all possible outcomes, and picks the defender with the highest ESV. The original "highest spice" heuristic remains available via config. A three-level resolution system (event override → global default → global strategy) lets users pin individual alliances to specific targets or strategies. Changes touch three existing files; no new files.

## ESV Calculation

ESV for an attacker-defender pairing is defined as:

```
ESV = Σ (probability_i × theft_amount_i)  for each outcome i
```

where `theft_amount_i = defender_spice × theft_percentage_i / 100` and `theft_percentage_i` comes from the existing building count + outcome level formula (or custom theft percentage for custom outcomes).

### Worked example

Attacker (12B power) evaluating Defender Y (10B power, 2,000,000 spice, 2 buildings):

Using Wednesday heuristic: `ratio = 12/10 = 1.2`
- `full_success` prob = `max(0, min(1, 2.5 × 1.2 - 2.0))` = 1.0
- `partial_success` prob = `max(0, cumulative_partial - full)` = 0.0
- `fail` prob = 0.0

Theft amounts (2 buildings):
- `full_success`: `(2 × 5 + 10)%` = 20% → `2,000,000 × 0.20` = 400,000
- `partial_success`: `(2 × 5)%` = 10% → `2,000,000 × 0.10` = 200,000
- `fail`: 0

ESV = `1.0 × 400,000 + 0.0 × 200,000 + 0.0 × 0` = **400,000**

Same attacker evaluating Defender X (18B power, 3,000,000 spice, 3 buildings):

`ratio = 12/18 = 0.667`
- `full_success` prob = `max(0, min(1, 2.5 × 0.667 - 2.0))` = 0.0
- `cumulative_partial` = `max(0, min(1, 1.75 × 0.667 - 0.9))` = 0.267
- `partial_success` prob = 0.267
- `fail` prob = 0.733

Theft amounts (3 buildings):
- `full_success`: `(3 × 5 + 10)%` = 25% → `3,000,000 × 0.25` = 750,000
- `partial_success`: `(3 × 5)%` = 15% → `3,000,000 × 0.15` = 450,000
- `fail`: 0

ESV = `0.0 × 750,000 + 0.267 × 450,000 + 0.733 × 0` = **120,150**

The ESV heuristic picks Defender Y (400,000 > 120,150), despite Y having less spice.

---

## Changes by File

### 1. `src/spice_war/utils/validation.py`

Add the new config keys to `_ALLOWED_MODEL_KEYS` and validate the new fields.

```python
_ALLOWED_MODEL_KEYS = {
    "random_seed",
    "battle_outcome_matrix",
    "event_targets",
    "event_reinforcements",
    "damage_weights",
    "targeting_strategy",
    "default_targets",
}

_VALID_STRATEGIES = {"expected_value", "highest_spice"}
```

#### New validation in `_check_model_references()`

After the existing checks, add:

```python
# Check targeting_strategy
strategy = data.get("targeting_strategy")
if strategy is not None and strategy not in _VALID_STRATEGIES:
    errors.append(
        f"targeting_strategy must be one of {sorted(_VALID_STRATEGIES)}, "
        f"got '{strategy}'"
    )

# Check default_targets
for alliance_id, override in data.get("default_targets", {}).items():
    if alliance_id not in alliance_ids:
        errors.append(
            f"default_targets references unknown alliance '{alliance_id}'"
        )
    if not isinstance(override, dict):
        errors.append(
            f"default_targets[{alliance_id}] must be a dict, "
            f"got {type(override).__name__}"
        )
        continue
    if "target" in override:
        if len(override) != 1:
            errors.append(
                f"default_targets[{alliance_id}] has 'target' with extra keys: "
                f"{sorted(set(override.keys()) - {'target'})}"
            )
        if override["target"] not in alliance_ids:
            errors.append(
                f"default_targets[{alliance_id}] references unknown "
                f"target '{override['target']}'"
            )
    elif "strategy" in override:
        if len(override) != 1:
            errors.append(
                f"default_targets[{alliance_id}] has 'strategy' with extra keys: "
                f"{sorted(set(override.keys()) - {'strategy'})}"
            )
        if override["strategy"] not in _VALID_STRATEGIES:
            errors.append(
                f"default_targets[{alliance_id}] strategy must be one of "
                f"{sorted(_VALID_STRATEGIES)}, got '{override['strategy']}'"
            )
    else:
        errors.append(
            f"default_targets[{alliance_id}] must have exactly one key: "
            f"'target' or 'strategy'"
        )
```

#### Updated `event_targets` validation

The existing `event_targets` validation assumes values are plain strings (defender IDs). Now values can be either a string (legacy — still supported but equivalent to `{"target": "..."}`) or a dict with `"target"` or `"strategy"`. Replace the current event_targets loop:

```python
# Check event_targets
for event_num, targets in data.get("event_targets", {}).items():
    for attacker_id, value in targets.items():
        if attacker_id not in alliance_ids:
            errors.append(
                f"event_targets references unknown alliance '{attacker_id}'"
            )
        if isinstance(value, str):
            # Legacy format: plain defender ID
            if value not in alliance_ids:
                errors.append(
                    f"event_targets references unknown alliance '{value}'"
                )
        elif isinstance(value, dict):
            if "target" in value:
                if len(value) != 1:
                    errors.append(
                        f"event_targets[{event_num}][{attacker_id}] has "
                        f"'target' with extra keys: "
                        f"{sorted(set(value.keys()) - {'target'})}"
                    )
                if value["target"] not in alliance_ids:
                    errors.append(
                        f"event_targets[{event_num}][{attacker_id}] references "
                        f"unknown target '{value['target']}'"
                    )
            elif "strategy" in value:
                if len(value) != 1:
                    errors.append(
                        f"event_targets[{event_num}][{attacker_id}] has "
                        f"'strategy' with extra keys: "
                        f"{sorted(set(value.keys()) - {'strategy'})}"
                    )
                if value["strategy"] not in _VALID_STRATEGIES:
                    errors.append(
                        f"event_targets[{event_num}][{attacker_id}] strategy "
                        f"must be one of {sorted(_VALID_STRATEGIES)}, "
                        f"got '{value['strategy']}'"
                    )
            else:
                errors.append(
                    f"event_targets[{event_num}][{attacker_id}] must be a "
                    f"string or dict with 'target' or 'strategy'"
                )
        else:
            errors.append(
                f"event_targets[{event_num}][{attacker_id}] must be a "
                f"string or dict, got {type(value).__name__}"
            )
```

#### Notes

- Legacy `event_targets` format (plain string values) remains valid. The existing `s3_rag3_vs_hot.json` model file uses `"1": {"RAG3": "Hot"}` which will still pass validation.
- Dict-style overrides in `event_targets` follow the same `{"target": ...}` / `{"strategy": ...}` pattern as `default_targets`, keeping the config format consistent.
- Validation catches the error cases from tests 21–22: unrecognized strategy values and override dicts missing both keys.

---

### 2. `src/spice_war/models/configurable.py`

This file gets the most changes: a new ESV calculation method, a reworked `generate_targets()` with three-level resolution, and a helper to compute probabilities for ESV.

#### New method: `_calculate_esv()`

```python
def _calculate_esv(
    self,
    attacker: Alliance,
    defender: Alliance,
    state: GameState,
) -> float:
    matrix = self.config.get("battle_outcome_matrix", {})
    probs = self._lookup_or_heuristic(matrix, attacker, defender, state.day)

    defender_spice = state.current_spice[defender.alliance_id]
    building_count = calculate_building_count(defender_spice)

    esv = 0.0

    full_prob = probs.get("full_success", 0.0)
    if full_prob > 0:
        theft_pct = calculate_theft_percentage("full_success", building_count)
        esv += full_prob * (defender_spice * theft_pct / 100.0)

    partial_prob = probs.get("partial_success", 0.0)
    if partial_prob > 0:
        theft_pct = calculate_theft_percentage("partial_success", building_count)
        esv += partial_prob * (defender_spice * theft_pct / 100.0)

    custom_prob = probs.get("custom", 0.0)
    if custom_prob > 0:
        custom_theft_pct = probs.get("custom_theft_percentage", 0.0)
        esv += custom_prob * (defender_spice * custom_theft_pct / 100.0)

    # fail contributes 0, so no term needed

    return esv
```

Imports `calculate_building_count` and `calculate_theft_percentage` from `spice_war.game.mechanics`. This is a model component calling game mechanics for calculation — consistent with the architecture's "model decisions can use game mechanics for computations" pattern, and the same functions are already imported by `events.py`.

#### New method: `_esv_targets()`

```python
def _esv_targets(
    self,
    bracket_attackers: list[Alliance],
    bracket_defenders: list[Alliance],
    state: GameState,
) -> dict[str, str]:
    attackers = sorted(bracket_attackers, key=lambda a: a.power, reverse=True)

    targets: dict[str, str] = {}
    assigned: set[str] = set()

    for attacker in attackers:
        available = [d for d in bracket_defenders if d.alliance_id not in assigned]
        if not available:
            break

        # Compute ESV for each available defender
        best_defender = max(
            available,
            key=lambda d: (
                self._calculate_esv(attacker, d, state),
                state.current_spice[d.alliance_id],
                d.alliance_id,
            ),
        )
        targets[attacker.alliance_id] = best_defender.alliance_id
        assigned.add(best_defender.alliance_id)

    return targets
```

#### Tie-breaking note

The requirements specify: ties broken by higher current spice, then alphabetical alliance_id. The `max()` key tuple `(esv, spice, alliance_id)` handles this naturally — higher values win for ESV and spice, and alphabetical order means the "later" ID wins in a `max`. However, the requirements say "alphabetical alliance_id" as a deterministic fallback, meaning the first alphabetically should win (not the last).

To get "first alphabetically wins" in a `max` call, we negate the comparison by using a reverse-sort key. But since alliance_id is a string, we can't negate it directly. Instead, we use a two-pass approach: compute ESV for all available defenders, then use `min` on alliance_id for the final tiebreak. Simplest implementation:

```python
best_defender = None
best_key = None
for d in available:
    esv = self._calculate_esv(attacker, d, state)
    spice = state.current_spice[d.alliance_id]
    # Sort key: highest ESV, then highest spice, then lowest (earliest) alliance_id
    key = (esv, spice, d.alliance_id)
    if best_key is None:
        best_defender = d
        best_key = key
    elif (key[0], key[1]) > (best_key[0], best_key[1]):
        best_defender = d
        best_key = key
    elif (key[0], key[1]) == (best_key[0], best_key[1]) and key[2] < best_key[2]:
        best_defender = d
        best_key = key

targets[attacker.alliance_id] = best_defender.alliance_id
```

This is clearer about the tie-breaking semantics but verbose. A cleaner approach: sort the available defenders and pick the first:

```python
available_with_esv = [
    (self._calculate_esv(attacker, d, state), d)
    for d in available
]
# Sort: highest ESV, highest spice, alphabetically earliest id
available_with_esv.sort(
    key=lambda pair: (
        -pair[0],
        -state.current_spice[pair[1].alliance_id],
        pair[1].alliance_id,
    )
)
best_defender = available_with_esv[0][1]
```

**Recommendation:** Use the sort approach. It's one pass through `_calculate_esv` per defender per attacker, and the sort is over at most ~10 defenders (bracket size). The negation trick for numeric values is idiomatic Python.

#### Reworked `generate_targets()` — three-level resolution

```python
def generate_targets(
    self,
    state: GameState,
    bracket_attackers: list[Alliance],
    bracket_defenders: list[Alliance],
    bracket_number: int,
) -> dict[str, str]:
    event_targets_config = self.config.get("event_targets", {})
    default_targets_config = self.config.get("default_targets", {})
    global_strategy = self.config.get("targeting_strategy", "expected_value")

    event_key = str(state.event_number)
    event_overrides = event_targets_config.get(event_key, {})

    defender_ids = {d.alliance_id for d in bracket_defenders}
    attacker_ids = {a.alliance_id for a in bracket_attackers}

    # Phase 1: Resolve pinned targets
    # Pins are resolved first; pinned defenders are removed from the pool
    # for algorithm-based attackers.
    pins: dict[str, str] = {}
    algo_attackers: list[tuple[Alliance, str]] = []  # (alliance, strategy)

    for attacker in bracket_attackers:
        aid = attacker.alliance_id
        resolved_target, resolved_strategy = self._resolve_attacker(
            aid, event_overrides, default_targets_config, global_strategy,
            defender_ids,
        )
        if resolved_target is not None:
            pins[aid] = resolved_target
        else:
            algo_attackers.append((attacker, resolved_strategy))

    # Phase 2: Run algorithms for non-pinned attackers
    pinned_defenders = set(pins.values())
    remaining_defenders = [
        d for d in bracket_defenders
        if d.alliance_id not in pinned_defenders
    ]

    # Group algo attackers by strategy, then assign
    targets = dict(pins)

    # Process algorithm-based attackers in power order (highest first)
    algo_attackers.sort(key=lambda pair: pair[0].power, reverse=True)
    assigned: set[str] = set(pinned_defenders)

    for attacker, strategy in algo_attackers:
        available = [
            d for d in bracket_defenders
            if d.alliance_id not in assigned
        ]
        if not available:
            break

        if strategy == "expected_value":
            best = self._pick_esv_target(attacker, available, state)
        else:  # highest_spice
            best = self._pick_highest_spice_target(available, state)

        targets[attacker.alliance_id] = best.alliance_id
        assigned.add(best.alliance_id)

    return targets
```

#### Helper: `_resolve_attacker()`

Implements the three-level resolution order from Section 2.3 of the requirements.

```python
def _resolve_attacker(
    self,
    attacker_id: str,
    event_overrides: dict,
    default_targets_config: dict,
    global_strategy: str,
    defender_ids: set[str],
) -> tuple[str | None, str]:
    """Returns (pinned_target_or_None, strategy).

    If pinned_target is not None, the attacker is pinned to that defender.
    Otherwise, strategy indicates which algorithm to use.
    """
    # Level 1: event_targets override
    if attacker_id in event_overrides:
        entry = event_overrides[attacker_id]
        target, strategy = self._parse_override(entry)
        if target is not None:
            if target in defender_ids:
                return target, ""
            # Pin invalid for this bracket — fall through to level 2
        else:
            return None, strategy

    # Level 2: default_targets
    if attacker_id in default_targets_config:
        entry = default_targets_config[attacker_id]
        target, strategy = self._parse_override(entry)
        if target is not None:
            if target in defender_ids:
                return target, ""
            # Pin invalid for this bracket — fall through to level 3
        else:
            return None, strategy

    # Level 3: global strategy
    return None, global_strategy


def _parse_override(self, entry) -> tuple[str | None, str]:
    """Parse an override entry (string or dict) into (target, strategy)."""
    if isinstance(entry, str):
        # Legacy format: plain defender ID
        return entry, ""
    if "target" in entry:
        return entry["target"], ""
    return None, entry["strategy"]
```

#### Helper: `_pick_esv_target()`

```python
def _pick_esv_target(
    self,
    attacker: Alliance,
    available: list[Alliance],
    state: GameState,
) -> Alliance:
    available_with_esv = [
        (self._calculate_esv(attacker, d, state), d)
        for d in available
    ]
    available_with_esv.sort(
        key=lambda pair: (
            -pair[0],
            -state.current_spice[pair[1].alliance_id],
            pair[1].alliance_id,
        )
    )
    return available_with_esv[0][1]
```

#### Helper: `_pick_highest_spice_target()`

Extracts the existing logic from `_default_targets` for the single-attacker case:

```python
def _pick_highest_spice_target(
    self,
    available: list[Alliance],
    state: GameState,
) -> Alliance:
    return max(
        available,
        key=lambda d: state.current_spice[d.alliance_id],
    )
```

#### Removed method: `_default_targets()`

The old `_default_targets()` method is replaced by the new resolution logic inside `generate_targets()`. The `highest_spice` strategy option reproduces its behavior.

#### Import additions

Add to the existing imports at the top of the file:

```python
from spice_war.game.mechanics import calculate_building_count, calculate_theft_percentage
```

---

### 3. `src/spice_war/game/events.py`

No changes needed. `coordinate_event()` calls `model.generate_targets()` which now handles all the resolution logic internally. The interface is unchanged.

---

## Resolution Flow Diagram

```
For each attacker in the bracket:

  event_targets[event_number][attacker_id] exists?
    ├─ Yes, is pin (target/string) ─→ target in bracket? ─┬─ Yes → PIN
    │                                                      └─ No  → fall through ↓
    └─ Yes, is strategy ─→ use that strategy ─────────────────────→ ALGORITHM
    └─ No ─→ fall through ↓

  default_targets[attacker_id] exists?
    ├─ Yes, is pin ─→ target in bracket? ─┬─ Yes → PIN
    │                                      └─ No  → fall through ↓
    └─ Yes, is strategy ──────────────────────────────────────────→ ALGORITHM
    └─ No ─→ fall through ↓

  targeting_strategy (global, default "expected_value") ──────────→ ALGORITHM

Phase 1 results: all PINs resolved
Phase 2: remaining attackers assigned by ALGORITHM (from remaining defenders)
```

---

## Tests — `tests/test_expected_value_targeting.py`

New test file. Uses inline fixtures with programmatically constructed alliances and configs.

### Helpers

```python
from spice_war.models.configurable import ConfigurableModel
from spice_war.utils.data_structures import Alliance, GameState


def _make_alliances(specs: list[tuple[str, str, float, int, int]]) -> list[Alliance]:
    """Build alliances from (id, faction, power, starting_spice, daily_rate) tuples."""
    return [
        Alliance(aid, faction, power, spice, rate)
        for aid, faction, power, spice, rate in specs
    ]


def _make_state(
    alliances: list[Alliance],
    event_number: int = 1,
    day: str = "wednesday",
    spice_overrides: dict[str, int] | None = None,
) -> GameState:
    spice = {a.alliance_id: a.starting_spice for a in alliances}
    if spice_overrides:
        spice.update(spice_overrides)
    return GameState(
        current_spice=spice,
        brackets={},
        event_number=event_number,
        day=day,
        event_history=[],
        alliances=alliances,
    )
```

### Test Implementations

| # | Test | Implementation |
|---|------|----------------|
| 1 | **Weak attacker avoids strong defender** | Attacker A (12B power). Defender X (18B power, 3M spice) and Defender Y (10B power, 2M spice). Config: `{}` (default ESV). Call `generate_targets()`. Assert A targets Y, not X. Verify by computing ESV: A vs Y has near-100% full success (~400K ESV), A vs X has ~27% partial (~120K ESV). |
| 2 | **Strong attacker picks richest viable target** | Attacker A (20B power). Defenders: X (15B, 3M spice) and Y (10B, 1M spice). A can beat both easily. Assert A targets X (higher ESV due to more spice). |
| 3 | **Equal-power bracket** | Three attackers and three defenders all with identical power. Assert targets match highest-spice ordering (ESV is proportional to spice when probabilities are equal). |
| 4 | **ESV calculation correctness** | Call `_calculate_esv()` directly with known inputs. Attacker 15B, Defender 15B, 2M spice, Wednesday. Compute expected ESV by hand from heuristic formulas and assert `pytest.approx` match. |
| 5 | **Building count affects ESV** | Two defenders with different spice levels crossing building thresholds. Defender A: 3.2M spice (4 buildings, 30% full theft). Defender B: 600K spice (1 building, 15% full theft). Same power ratio. Assert attacker targets A (higher ESV despite similar probabilities, because theft % is higher). |
| 6 | **Priority order respected** | Two attackers: A (20B power) and B (10B power). Two defenders: X (15B, 3M) and Y (8B, 2M). A picks first (highest power), takes X (richest beatable). B then picks from remaining: Y. Assert A→X, B→Y. |
| 7 | **Tie-breaking by spice then id** | Two defenders with identical power and spice such that ESV is equal. Defender "Alpha" and "Beta" both 2M spice, same power. Assert attacker targets "Alpha" (alphabetically earlier). Then test with different spice: if Alpha has 2.1M and Beta has 2M (same ESV from identical probabilities but Alpha has more spice), assert Alpha targeted. |
| 8 | **Matrix probabilities used when available** | Config with `battle_outcome_matrix` entries for a specific pairing. Verify `_calculate_esv()` uses matrix probabilities, not heuristic. Set matrix to give 100% full success for one defender and 0% for another. Assert ESV reflects matrix values. |
| 9 | **Custom outcome included in ESV** | Matrix entry with `custom: 0.5, custom_theft_percentage: 20`. Verify ESV includes the custom outcome contribution. Compute expected: `0.5 × (spice × 0.20)` plus contributions from other outcomes. |
| 10 | **Single attacker, single defender** | Trivial case — one attacker, one defender. Assert target is the only defender regardless of ESV value. |
| 11 | **All defenders too strong** | All defenders have overwhelming power (ratio < 0.52 on Wednesday → 0% any success). All ESVs are 0. Assert targets still assigned (tie-break by spice, then id). |
| 12 | **targeting_strategy: highest_spice** | Config `{"targeting_strategy": "highest_spice"}`. Three attackers, three defenders. Assert targeting matches the old behavior: sorted by power vs sorted by spice, 1:1. |
| 13 | **targeting_strategy: expected_value** | Config `{"targeting_strategy": "expected_value"}`. Same scenario as test 1. Assert same result as default (omitted). |
| 14 | **default_targets fixed pin** | Config `{"default_targets": {"A1": {"target": "D1"}}}`. Assert A1 targets D1 in every call regardless of ESV. Other attackers use default algorithm. |
| 15 | **default_targets per-alliance strategy** | Config `{"default_targets": {"A1": {"strategy": "highest_spice"}}}`. Assert A1 uses highest-spice targeting while A2 uses default ESV. |
| 16 | **event_targets overrides default_targets pin** | `default_targets` pins A1→D1. `event_targets` for event 3 pins A1→D2. Call with event_number=3 → A1 targets D2. Call with event_number=1 → A1 targets D1. |
| 17 | **event_targets strategy overrides default pin** | `default_targets` pins A1→D1. `event_targets` for event 3 has `{"strategy": "expected_value"}`. Call with event_number=3 → A1 uses ESV algorithm (not pinned). |
| 18 | **Pinned target not in bracket** | `default_targets` pins A1→D_other where D_other is a valid alliance but not in the current bracket's defender list. Assert A1 falls through to algorithm. |
| 19 | **Pins resolved before algorithm** | Two attackers: A1 pinned to D1, A2 uses ESV. D1 is the best ESV target for A2. Assert A1 gets D1 (pinned), A2 gets D2 (D1 already claimed). |
| 20 | **Partial event_targets + default_targets** | Complex config: `default_targets` pins A1→D1 and sets A2 to `highest_spice`. `event_targets[3]` overrides A1 to `expected_value` strategy. Global strategy is `expected_value`. For event 3: A1 uses ESV, A2 uses highest_spice, A3 uses ESV (global). For event 1: A1 targets D1 (pin), A2 uses highest_spice, A3 uses ESV. |
| 21 | **Invalid targeting_strategy** | Config `{"targeting_strategy": "unknown"}`. Call `load_model_config()`. Assert `ValidationError` with message matching `"targeting_strategy"`. |
| 22 | **Invalid override dict** | Config `{"default_targets": {"A1": {"invalid_key": "value"}}}`. Call `load_model_config()`. Assert `ValidationError` with message matching `"'target' or 'strategy'"`. |

### Test details

- Tests 1–11 validate the ESV algorithm in isolation by calling `generate_targets()` on a `ConfigurableModel` with carefully chosen power/spice values.
- Tests 4, 8, 9 access `_calculate_esv()` directly to validate the formula without the assignment layer.
- Tests 12–20 validate the configuration and resolution system by calling `generate_targets()` with various config combinations and checking the returned targets dict.
- Tests 21–22 validate error cases by calling `load_model_config()` with invalid configs wrapped in `pytest.raises(ValidationError)`.
- All tests use inline alliances and configs rather than fixture files — the targeting config is a model-layer feature, so building configs in-test is clearer.
- The `_calculate_esv` method is tested directly (tests 4, 8, 9) even though it's notionally private, because the ESV formula is the core logic and warrants direct validation. This matches the test pattern used in 0004 where `_lookup_or_heuristic` behavior is tested through `determine_battle_outcome`.

---

## Legacy Compatibility

All changes are backward-compatible:

- **`event_targets` plain strings**: The existing format `{"1": {"RAG3": "Hot"}}` remains valid. `_parse_override()` handles string values as equivalent to `{"target": "Hot"}`. The `s3_rag3_vs_hot.json` model file works unchanged.
- **No `targeting_strategy` key**: Defaults to `"expected_value"`. This changes default behavior from the old "highest spice" heuristic, which is the intent. Users who want the old behavior set `"targeting_strategy": "highest_spice"`.
- **No `default_targets` key**: All attackers use the global strategy, which is the same as current behavior when `targeting_strategy` is `"highest_spice"`.
- **Existing `event_targets` with full event coverage**: If every attacker is covered by event_targets for a given event, the resolution never reaches default_targets or global strategy. Existing model files with complete event_targets continue to work identically.

### Default behavior change

The default targeting strategy changes from "highest spice" to "expected value." This is intentional per the requirements. Existing users who rely on the old default and have no `event_targets` config will see different targeting assignments. The `"targeting_strategy": "highest_spice"` option provides an explicit opt-in to the old behavior.

---

## File Changes Summary

| File | Change |
|------|--------|
| `src/spice_war/utils/validation.py` | Add `targeting_strategy` and `default_targets` to allowed keys; validate new fields and update `event_targets` validation for dict-style entries |
| `src/spice_war/models/configurable.py` | Add `_calculate_esv()`, `_esv_targets()`, `_pick_esv_target()`, `_pick_highest_spice_target()`, `_resolve_attacker()`, `_parse_override()`; rework `generate_targets()`; remove `_default_targets()` |
| `tests/test_expected_value_targeting.py` | New file — 22 tests |

No changes to `data_structures.py`, `base.py`, `battle.py`, `mechanics.py`, `events.py`, `simulator.py`, or CLI scripts.
