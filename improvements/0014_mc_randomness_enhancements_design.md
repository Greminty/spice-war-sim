# MC Randomness Enhancements — Design

## Overview

Three new optional config fields — `targeting_temperature`, `power_noise`, and
`outcome_noise` — add randomness to targeting, power, and outcome probabilities
in `ConfigurableModel`. All changes are internal to `configurable.py`; no
interface changes. A helper module `src/spice_war/models/noise.py` holds the
offset-generation and probability-perturbation logic.

---

## 1. Config Parsing

**File:** `src/spice_war/models/configurable.py` — `__init__()` (line 12)

Read three new optional fields from `config` and store them as instance
attributes. Generate pairing offsets eagerly if `outcome_noise > 0`.

```python
def __init__(self, config: dict, alliances: list[Alliance]):
    self.config = config
    self.alliances = {a.alliance_id: a for a in alliances}
    seed = config.get("random_seed", 0)
    self.rng = random.Random(seed)

    # MC randomness parameters
    self.targeting_temperature = config.get("targeting_temperature", 0.0)
    self.power_noise = config.get("power_noise", 0.0)
    self.outcome_noise = config.get("outcome_noise", 0.0)

    # Pre-generate per-pairing outcome offsets (deterministic from seed)
    self._pairing_offsets: dict[tuple[str, str], dict[str, float]] = {}
    if self.outcome_noise > 0:
        self._generate_pairing_offsets()

    # Per-event effective powers (populated lazily via set_effective_powers)
    self._effective_powers: dict[str, float] = {}
```

### 1a. `_generate_pairing_offsets()`

Use a **separate RNG** seeded from the main seed so that adding/removing
outcome noise doesn't shift the main RNG sequence for other features. Generate
offsets for every possible attacker-defender pair up front.

```python
def _generate_pairing_offsets(self) -> None:
    seed = self.config.get("random_seed", 0)
    offset_rng = random.Random(seed + 1_000_000)
    noise = self.outcome_noise
    alliance_ids = sorted(self.alliances.keys())
    for att_id in alliance_ids:
        for def_id in alliance_ids:
            if att_id == def_id:
                continue
            self._pairing_offsets[(att_id, def_id)] = {
                "full_success": offset_rng.uniform(-noise, noise),
                "partial_success": offset_rng.uniform(-noise, noise),
                "custom": offset_rng.uniform(-noise, noise),
            }
```

Iterating in sorted order ensures deterministic offset assignment regardless
of dict ordering. The seed offset (`+ 1_000_000`) prevents correlation with
the main RNG stream.

---

## 2. Per-Event Power Fluctuation

**File:** `src/spice_war/models/configurable.py`

### 2a. New method: `set_effective_powers()`

Called once at the start of each event (from the MC loop or simulator). Draws
per-alliance multipliers from the model's main `self.rng` and stores effective
powers for use throughout the event.

```python
def set_effective_powers(self) -> None:
    if self.power_noise <= 0:
        self._effective_powers = {
            aid: a.power for aid, a in self.alliances.items()
        }
        return
    noise = self.power_noise
    self._effective_powers = {}
    for aid in sorted(self.alliances.keys()):
        base = self.alliances[aid].power
        u = self.rng.uniform(-noise, noise)
        self._effective_powers[aid] = base * (1 + u)
```

Sorted iteration keeps RNG consumption order deterministic.

When `power_noise` is 0, no RNG calls are made — effective powers equal base
powers and existing behavior is preserved.

### 2b. New method: `_get_power(alliance_id)`

Returns the effective power for an alliance. All power-dependent code paths
call this instead of reading `alliance.power` directly.

```python
def _get_power(self, alliance_id: str) -> float:
    return self._effective_powers.get(
        alliance_id, self.alliances[alliance_id].power
    )
```

### 2c. Call site: `simulate_war()` in `simulator.py`

**File:** `src/spice_war/game/simulator.py` — inside the event loop (line 45)

After constructing the `GameState` and before calling `coordinate_event()`,
call `set_effective_powers()` if the model supports it:

```python
if hasattr(model, "set_effective_powers"):
    model.set_effective_powers()
```

This keeps the `BattleModel` interface unchanged — only `ConfigurableModel`
gains the method.

### 2d. Update power-dependent code paths

All heuristic methods that read `attacker.power` or `defender.power` must use
`self._get_power(aid)` instead:

**`_heuristic_probabilities()`** (line 358):

```python
def _heuristic_probabilities(
    self, attacker: Alliance, defender: Alliance, day: str
) -> dict[str, float]:
    ratio = self._get_power(attacker.alliance_id) / self._get_power(defender.alliance_id)
    # ... rest unchanged
```

**`determine_damage_splits()` — heuristic branch** (line 397):

```python
ratio = self._get_power(a.alliance_id) / self._get_power(primary_defender.alliance_id)
```

**`generate_targets()` — attacker priority sort** (line 53):

```python
algo_attackers.sort(key=lambda pair: self._get_power(pair[0].alliance_id), reverse=True)
```

---

## 3. Stochastic Targeting

**File:** `src/spice_war/models/configurable.py`

### 3a. New method: `_softmax_select()`

Performs softmax-weighted random selection over scored candidates.

```python
def _softmax_select(
    self,
    candidates: list[Alliance],
    scores: dict[str, float],
) -> Alliance:
    if len(candidates) == 1:
        return candidates[0]

    T = self.targeting_temperature

    # Normalize scores to 0–1 range
    raw = [scores.get(c.alliance_id, 0.0) for c in candidates]
    s_max = max(raw)
    if s_max > 0:
        normalized = [s / s_max for s in raw]
    else:
        # All zero — uniform selection
        return self.rng.choice(candidates)

    # Softmax with overflow protection
    exp_vals = [math.exp((s - max(normalized)) / T) for s in normalized]
    total = sum(exp_vals)
    weights = [e / total for e in exp_vals]

    # Weighted random selection
    roll = self.rng.random()
    cumulative = 0.0
    for i, w in enumerate(weights):
        cumulative += w
        if roll < cumulative:
            return candidates[i]
    return candidates[-1]
```

Add `import math` at the top of the file.

### 3b. Update `_pick_esv_target()`

When `targeting_temperature > 0`, use softmax selection instead of picking the
top-scoring defender:

```python
def _pick_esv_target(
    self,
    attacker: Alliance,
    available: list[Alliance],
    state: GameState,
) -> Alliance:
    scores = {
        d.alliance_id: self._calculate_esv(attacker, d, state)
        for d in available
    }

    if self.targeting_temperature > 0:
        return self._softmax_select(available, scores)

    # Deterministic: sort by ESV desc, spice desc, id asc
    available_sorted = sorted(
        available,
        key=lambda d: (
            -scores[d.alliance_id],
            -state.current_spice[d.alliance_id],
            d.alliance_id,
        ),
    )
    return available_sorted[0]
```

### 3c. Update `_pick_highest_spice_target()`

Same pattern — softmax when temperature > 0:

```python
def _pick_highest_spice_target(
    self,
    available: list[Alliance],
    state: GameState,
) -> Alliance:
    if self.targeting_temperature > 0:
        scores = {
            d.alliance_id: float(state.current_spice[d.alliance_id])
            for d in available
        }
        return self._softmax_select(available, scores)

    return max(
        available,
        key=lambda d: state.current_spice[d.alliance_id],
    )
```

---

## 4. Outcome Probability Noise

**File:** `src/spice_war/models/configurable.py`

### 4a. New method: `_apply_outcome_noise()`

Applies the pre-generated pairing offsets to a probability dict. Called from
`determine_battle_outcome()` after probabilities are resolved.

```python
def _apply_outcome_noise(
    self,
    probs: dict[str, float],
    attacker_id: str,
    defender_id: str,
) -> dict[str, float]:
    offsets = self._pairing_offsets.get((attacker_id, defender_id))
    if offsets is None:
        return probs

    result = dict(probs)

    result["full_success"] = max(0.0, result["full_success"] + offsets["full_success"])
    result["partial_success"] = max(0.0, result["partial_success"] + offsets["partial_success"])

    if "custom" in result:
        result["custom"] = max(0.0, result["custom"] + offsets["custom"])

    # Renormalize if non-fail probabilities exceed 1
    non_fail = result["full_success"] + result["partial_success"] + result.get("custom", 0.0)
    if non_fail > 1.0:
        result["full_success"] /= non_fail
        result["partial_success"] /= non_fail
        if "custom" in result:
            result["custom"] /= non_fail

    return result
```

### 4b. Update `determine_battle_outcome()`

Apply noise to each attacker's probabilities before averaging (for
multi-attacker battles), then apply noise again to the combined result. Per
the requirement: "each attacker's per-pairing offsets are applied to their
individual probabilities first, then the perturbed probabilities are averaged.
Clamping and normalization happen after averaging."

```python
def determine_battle_outcome(
    self,
    state: GameState,
    attackers: list[Alliance],
    defenders: list[Alliance],
    day: str,
) -> tuple[str, dict[str, float]]:
    primary_defender = defenders[0]
    matrix = self.config.get("battle_outcome_matrix", {})

    probs_list = []
    for attacker in attackers:
        probs = self._lookup_or_heuristic(
            matrix, attacker, primary_defender, day
        )
        if self.outcome_noise > 0:
            probs = self._apply_outcome_noise(
                probs, attacker.alliance_id, primary_defender.alliance_id
            )
        probs_list.append(probs)

    if len(probs_list) == 1:
        combined = probs_list[0]
    else:
        combined = {
            "full_success": sum(p["full_success"] for p in probs_list)
            / len(probs_list),
            "partial_success": sum(p["partial_success"] for p in probs_list)
            / len(probs_list),
        }

        custom_probs = [p.get("custom", 0.0) for p in probs_list]
        custom_avg = sum(custom_probs) / len(probs_list)
        if custom_avg > 0:
            combined["custom"] = custom_avg
            theft_pcts = [
                p["custom_theft_percentage"]
                for p in probs_list
                if "custom_theft_percentage" in p
            ]
            combined["custom_theft_percentage"] = (
                sum(theft_pcts) / len(theft_pcts)
            )

        # Clamp and renormalize the averaged result
        combined["full_success"] = max(0.0, combined["full_success"])
        combined["partial_success"] = max(0.0, combined["partial_success"])
        if "custom" in combined:
            combined["custom"] = max(0.0, combined["custom"])
        non_fail = (
            combined["full_success"]
            + combined["partial_success"]
            + combined.get("custom", 0.0)
        )
        if non_fail > 1.0:
            combined["full_success"] /= non_fail
            combined["partial_success"] /= non_fail
            if "custom" in combined:
                combined["custom"] /= non_fail

    combined["fail"] = max(
        0.0,
        1.0
        - combined["full_success"]
        - combined["partial_success"]
        - combined.get("custom", 0.0),
    )

    # Outcome roll (unchanged)
    roll = self.rng.random()
    cumulative = combined["full_success"]
    if roll < cumulative:
        outcome = "full_success"
    else:
        cumulative += combined["partial_success"]
        if roll < cumulative:
            outcome = "partial_success"
        elif "custom" in combined:
            cumulative += combined["custom"]
            if roll < cumulative:
                outcome = "custom"
            else:
                outcome = "fail"
        else:
            outcome = "fail"

    return outcome, combined
```

### 4c. Update `_calculate_esv()`

ESV computation also uses outcome probabilities. Apply pairing noise so that
ESV-based targeting reflects the perturbed probabilities:

```python
def _calculate_esv(
    self,
    attacker: Alliance,
    defender: Alliance,
    state: GameState,
) -> float:
    matrix = self.config.get("battle_outcome_matrix", {})
    probs = self._lookup_or_heuristic(matrix, attacker, defender, state.day)

    if self.outcome_noise > 0:
        probs = self._apply_outcome_noise(
            probs, attacker.alliance_id, defender.alliance_id
        )

    # ... rest unchanged (compute ESV from probs)
```

---

## 5. RNG Discipline

Careful RNG management ensures backward compatibility and determinism:

| Feature | RNG source | When consumed | Zero-value behavior |
|---------|-----------|---------------|---------------------|
| Stochastic targeting | `self.rng` | During `generate_targets()`, one `random()` call per softmax selection | No calls — deterministic pick |
| Power fluctuation | `self.rng` | During `set_effective_powers()`, one `uniform()` per alliance | No calls — effective = base |
| Outcome offsets | Separate `Random(seed + 1_000_000)` | During `__init__()` | No offset RNG created |
| Outcome roll | `self.rng` | During `determine_battle_outcome()` | Unchanged — always consumed |

The outcome offset RNG is separate to avoid shifting the main RNG sequence.
Power noise calls happen before targeting calls (both use `self.rng`), which
happen before outcome rolls — this is safe because the call order is
deterministic for a given seed.

**When all three are 0**: No additional RNG calls are made. The call sequence
is identical to current code. Full backward compatibility.

---

## Files Changed

| File | Changes |
|------|---------|
| `src/spice_war/models/configurable.py` | Read 3 config fields, add `_generate_pairing_offsets()`, `set_effective_powers()`, `_get_power()`, `_softmax_select()`, `_apply_outcome_noise()`; update `_pick_esv_target()`, `_pick_highest_spice_target()`, `_heuristic_probabilities()`, `determine_damage_splits()`, `generate_targets()`, `determine_battle_outcome()`, `_calculate_esv()` |
| `src/spice_war/game/simulator.py` | Add `set_effective_powers()` call before each event |

---

## Implementation Order

| Step | Feature | Methods | Complexity |
|------|---------|---------|------------|
| 1 | Config parsing + `_get_power()` scaffolding | `__init__`, `_get_power`, `set_effective_powers` | Low |
| 2 | Power fluctuation | Update `_heuristic_probabilities`, `determine_damage_splits`, `generate_targets`; add call in `simulator.py` | Medium |
| 3 | Stochastic targeting | `_softmax_select`, update `_pick_esv_target`, `_pick_highest_spice_target` | Medium |
| 4 | Outcome noise | `_generate_pairing_offsets`, `_apply_outcome_noise`, update `determine_battle_outcome`, `_calculate_esv` | Medium |
| 5 | Tests | 35 tests per requirements | High |

---

## Testing

All 35 tests from the requirements, organized into four test classes in
`tests/test_mc_randomness.py`:

- **`TestStochasticTargeting`** (tests 1–10): Temperature 0 backward compat,
  varied targets across seeds, high/low temperature distributions, pinned
  targets, single defender, all-zero scores, determinism, priority order,
  highest_spice strategy
- **`TestPowerFluctuation`** (tests 11–20): Noise 0 backward compat, varied
  outcomes, base power unchanged, effective range, within-event consistency,
  cross-event variation, determinism, matrix unaffected, damage splits,
  heuristic probabilities
- **`TestOutcomeNoise`** (tests 21–32): Noise 0 backward compat, varied
  outcomes, independent offsets, cross-event consistency, seed variation,
  valid probabilities, matrix/heuristic affected, custom outcome, normalization,
  determinism, interaction with power_noise
- **`TestCombined`** (tests 33–35): All features together, backward compat,
  full MC sweep distribution
