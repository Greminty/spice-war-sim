# Tier-Aware Targeting — Design

## Overview

Add two targeting strategies — `rank_aware` and `maximize_tier` — to
`ConfigurableModel`. `rank_aware` is a scoring function that evaluates
targets by projected rank/tier improvement. `maximize_tier` runs
deterministic forward simulations of the remaining war for top-N
alliances and falls back to a cheaper strategy for the rest.

Changes span 5 files: `data_structures.py` (GameState gets event
schedule), `validation.py` + `bridge.py` (new config keys), `simulator.py`
(thread schedule into GameState), and `configurable.py` (all new logic).

---

## 1. GameState: Add Event Schedule

### 1a. `src/spice_war/utils/data_structures.py` — new optional field

The forward simulation in `maximize_tier` needs the remaining event
schedule. `GameState` is the natural place — it already holds
`event_history` (past) and `alliances`.

```python
@dataclass
class GameState:
    current_spice: dict[str, int]
    brackets: dict[str, int]
    event_number: int
    day: str
    event_history: list[dict]
    alliances: list[Alliance]
    event_schedule: list[EventConfig] | None = None  # NEW
```

Default `None` preserves backward compatibility — all existing callers
and tests continue to work unchanged.

### 1b. `src/spice_war/game/simulator.py` — populate the field

In `simulate_war`, pass the schedule when constructing GameState:

```python
state = GameState(
    current_spice=current_spice,
    brackets={},
    event_number=event_number,
    day=event_config.day,
    event_history=event_history,
    alliances=alliances,
    event_schedule=event_schedule,  # NEW
)
```

No other changes to simulator.py.

---

## 2. Validation

### 2a. `src/spice_war/utils/validation.py` — strategy set and allowed keys

```python
_VALID_STRATEGIES = {"expected_value", "highest_spice", "rank_aware", "maximize_tier"}

_ALLOWED_MODEL_KEYS = {
    ...,
    "tier_optimization_top_n",
    "tier_optimization_fallback",
}
```

### 2b. `src/spice_war/utils/validation.py` — new field validation

Add to `_check_model_references`, after the MC randomness checks:

```python
# Check tier_optimization_* fields
top_n = data.get("tier_optimization_top_n")
fallback = data.get("tier_optimization_fallback")
strategy = data.get("targeting_strategy", "expected_value")

# Reject if either field is present but strategy is not maximize_tier
if (top_n is not None or fallback is not None) \
        and strategy != "maximize_tier":
    errors.append(
        "'tier_optimization_top_n' and 'tier_optimization_fallback' "
        "are only valid when targeting_strategy is 'maximize_tier', "
        f"got targeting_strategy='{strategy}'"
    )

# Validate field values (even if strategy check fails, report all errors)
if top_n is not None:
    if not isinstance(top_n, int) or isinstance(top_n, bool) or top_n <= 0:
        errors.append(
            "'tier_optimization_top_n' must be a positive integer, "
            f"got {top_n!r}"
        )

_VALID_FALLBACK_STRATEGIES = {"expected_value", "highest_spice", "rank_aware"}
if fallback is not None:
    if fallback not in _VALID_FALLBACK_STRATEGIES:
        errors.append(
            f"'tier_optimization_fallback' must be one of "
            f"{sorted(_VALID_FALLBACK_STRATEGIES)}, got '{fallback}'"
        )
```

### 2c. `src/spice_war/web/bridge.py` — mirror allowed keys

```python
_ALLOWED_MODEL_KEYS = {
    ...,
    "tier_optimization_top_n",
    "tier_optimization_fallback",
}
```

---

## 3. `rank_aware` Strategy

All changes in `src/spice_war/models/configurable.py`.

### 3a. Helper: `_rank_and_tier()`

Compute an alliance's global rank and reward tier from a spice
dictionary. Duplicates the tier thresholds from
`calculate_final_rankings` but returns both rank and tier for a
single alliance — used by both `rank_aware` scoring and
`maximize_tier` tie-breaking.

```python
@staticmethod
def _rank_and_tier(
    alliance_id: str, spice_dict: dict[str, int]
) -> tuple[int, int]:
    """Return (rank, tier) for alliance_id given current spice standings."""
    sorted_ids = sorted(
        spice_dict.keys(),
        key=lambda aid: (-spice_dict[aid], aid),
    )
    rank = sorted_ids.index(alliance_id) + 1
    if rank == 1:
        tier = 1
    elif rank <= 3:
        tier = 2
    elif rank <= 10:
        tier = 3
    elif rank <= 20:
        tier = 4
    else:
        tier = 5
    return rank, tier
```

Tie-breaking by alphabetical alliance_id ensures deterministic rank
when two alliances have equal spice.

### 3b. `_pick_rank_aware_target()`

```python
def _pick_rank_aware_target(
    self,
    attacker: Alliance,
    available: list[Alliance],
    state: GameState,
) -> Alliance:
    cur_rank, cur_tier = self._rank_and_tier(
        attacker.alliance_id, state.current_spice
    )

    scores: dict[str, int] = {}
    esvs: dict[str, float] = {}

    for d in available:
        esv = self._calculate_esv(attacker, d, state)
        esvs[d.alliance_id] = esv
        transfer = round(esv)

        # Project post-battle standings
        projected = dict(state.current_spice)
        projected[attacker.alliance_id] += transfer
        projected[d.alliance_id] -= transfer

        proj_rank, proj_tier = self._rank_and_tier(
            attacker.alliance_id, projected
        )

        tier_improvement = cur_tier - proj_tier   # positive = better tier
        rank_improvement = cur_rank - proj_rank   # positive = better rank
        scores[d.alliance_id] = tier_improvement * 1000 + rank_improvement

    if self.targeting_temperature > 0:
        return self._softmax_select(available, scores)

    # Deterministic tie-break: score desc → ESV desc → spice desc → id asc
    return sorted(
        available,
        key=lambda d: (
            -scores[d.alliance_id],
            -esvs[d.alliance_id],
            -state.current_spice[d.alliance_id],
            d.alliance_id,
        ),
    )[0]
```

**Key behaviors:**

- The expected transfer (`round(esv)`) is the probability-weighted
  theft amount — the same value `_calculate_esv` already computes.
- Projected standings modify only the attacker and defender. All other
  alliances keep their current spice. This is the single-event-horizon
  approximation (same limitation as ESV).
- When all scores are ≤ 0 (no rank/tier improvement possible), all
  scores are 0 and tie-breaking falls through to ESV — graceful
  degradation to ESV-like behavior.
- Softmax selection with `targeting_temperature > 0` applies over
  rank-aware scores, using the existing `_softmax_select` method.
  When all scores are 0, `_softmax_select` returns uniform random.

---

## 4. `maximize_tier` Strategy

All changes in `src/spice_war/models/configurable.py`.

### 4a. `_get_top_n_ids()`

Determine which alliances in the attacking faction qualify for forward
projection. Uses faction rank (by `current_spice`, descending) per
requirements §2.3.

```python
def _get_top_n_ids(
    self,
    state: GameState,
    attacking_faction: str,
) -> set[str]:
    n = self.config.get("tier_optimization_top_n", 5)
    faction_alliances = [
        a for a in state.alliances if a.faction == attacking_faction
    ]
    sorted_by_spice = sorted(
        faction_alliances,
        key=lambda a: (-state.current_spice[a.alliance_id], a.alliance_id),
    )
    return {a.alliance_id for a in sorted_by_spice[:n]}
```

### 4b. `_forward_sim_tier()`

Run a deterministic forward simulation of the remaining war with a
hypothetical target assignment. Returns `(tier, rank)` for the
attacker.

```python
def _forward_sim_tier(
    self,
    attacker_id: str,
    defender_id: str,
    state: GameState,
) -> tuple[int, int]:
    from spice_war.game.simulator import simulate_war

    # Synthetic alliances with current spice as starting spice
    synthetic = [
        Alliance(
            alliance_id=a.alliance_id,
            faction=a.faction,
            power=a.power,
            starting_spice=state.current_spice[a.alliance_id],
            daily_spice_rate=a.daily_spice_rate,
            name=a.name,
            server=a.server,
        )
        for a in state.alliances
    ]

    # Remaining schedule: current event (0 income days) + future events
    current_ec = state.event_schedule[state.event_number - 1]
    forward_schedule = [
        EventConfig(
            attacker_faction=current_ec.attacker_faction,
            day=current_ec.day,
            days_before=0,
        )
    ] + list(state.event_schedule[state.event_number:])

    # Deterministic config: rank_aware strategy, no noise, pin hypothesis
    forward_config = {
        "random_seed": 0,
        "targeting_strategy": "rank_aware",
        "targeting_temperature": 0,
        "power_noise": 0,
        "outcome_noise": 0,
        "battle_outcome_matrix": self.config.get("battle_outcome_matrix", {}),
        "damage_weights": self.config.get("damage_weights", {}),
        "event_targets": {"1": {attacker_id: defender_id}},
    }

    forward_model = ConfigurableModel(forward_config, synthetic)
    result = simulate_war(synthetic, forward_schedule, forward_model)

    tier = result["rankings"][attacker_id]
    rank = self._rank_and_tier(attacker_id, result["final_spice"])[0]
    return tier, rank
```

**Design decisions:**

- **Lazy import** of `simulate_war` avoids adding a new top-level
  dependency from `configurable.py` → `simulator.py`. No circular
  import exists (simulator imports events/mechanics/base, not
  configurable), but the lazy import keeps coupling explicit.
- **Forward sim config inherits `battle_outcome_matrix` and
  `damage_weights`** from the outer model. The calibrated outcome
  probabilities are important for accurate projection. The matrix is
  keyed by day (wednesday/saturday), so each simulated event
  automatically gets the right probabilities.
- **`days_before=0` for the current event** because passive income has
  already been applied by `simulate_war` before `generate_targets` is
  called.
- **`event_targets: {"1": ...}`** pins the hypothesis in the forward
  sim's event 1 (the current real event). All other targeting in the
  forward sim uses `rank_aware`.
- **Using `rank_aware` (not `maximize_tier`)** in the forward sim
  avoids infinite recursion and keeps forward projections fast.

### 4c. `_pick_maximize_tier_target()`

Evaluate each available defender via forward simulation. Pick the one
that yields the best final tier for the attacker.

```python
def _pick_maximize_tier_target(
    self,
    attacker: Alliance,
    available: list[Alliance],
    state: GameState,
) -> Alliance:
    candidates = []
    for d in available:
        tier, rank = self._forward_sim_tier(
            attacker.alliance_id, d.alliance_id, state
        )
        esv = self._calculate_esv(attacker, d, state)
        candidates.append((d, tier, rank, esv))

    # Sort: best tier (lowest) → best rank (lowest) → highest ESV → alpha id
    candidates.sort(
        key=lambda x: (x[1], x[2], -x[3], x[0].alliance_id)
    )
    return candidates[0][0]
```

No softmax for `maximize_tier` — it's always deterministic. The outer
MC loop provides variance through outcome rolls and noise parameters.

---

## 5. `generate_targets()` Restructure

Replace the current Phase 2 (single loop sorted by power) with a
two-group system: **priority** (top-N `maximize_tier` attackers) picks
first, then **regular** (everyone else).

### 5a. Strategy dispatcher

Extract a `_pick_by_strategy` method to replace the inline if/else:

```python
def _pick_by_strategy(
    self,
    attacker: Alliance,
    available: list[Alliance],
    state: GameState,
    strategy: str,
) -> Alliance:
    if strategy == "expected_value":
        return self._pick_esv_target(attacker, available, state)
    elif strategy == "highest_spice":
        return self._pick_highest_spice_target(available, state)
    elif strategy == "rank_aware":
        return self._pick_rank_aware_target(attacker, available, state)
    else:
        return self._pick_esv_target(attacker, available, state)
```

`maximize_tier` is not in the dispatcher — it's handled via
`_pick_maximize_tier_target` in the priority group. Non-top-N
`maximize_tier` attackers are remapped to the fallback strategy before
entering the dispatcher.

### 5b. `generate_targets()` — full revised Phase 2

```python
def generate_targets(self, state, bracket_attackers, bracket_defenders,
                     bracket_number):
    # Phase 1: Resolve pinned targets (UNCHANGED)
    ...
    targets = dict(pins)
    assigned: set[str] = set(pins.values())

    # Phase 2: Split algo_attackers into priority + regular groups
    priority_attackers: list[Alliance] = []
    regular_attackers: list[tuple[Alliance, str]] = []

    has_maximize_tier = any(
        s == "maximize_tier" for _, s in algo_attackers
    )

    if has_maximize_tier:
        attacking_faction = bracket_attackers[0].faction
        top_n_ids = self._get_top_n_ids(state, attacking_faction)
        fallback = self.config.get(
            "tier_optimization_fallback", "rank_aware"
        )
        for attacker, strategy in algo_attackers:
            if strategy == "maximize_tier" \
                    and attacker.alliance_id in top_n_ids:
                priority_attackers.append(attacker)
            else:
                effective = fallback if strategy == "maximize_tier" \
                    else strategy
                regular_attackers.append((attacker, effective))
    else:
        regular_attackers = list(algo_attackers)

    # Priority group picks first (forward sim, by power desc)
    priority_attackers.sort(
        key=lambda a: self._get_power(a.alliance_id), reverse=True
    )
    for attacker in priority_attackers:
        available = [
            d for d in bracket_defenders
            if d.alliance_id not in assigned
        ]
        if not available:
            break
        best = self._pick_maximize_tier_target(attacker, available, state)
        targets[attacker.alliance_id] = best.alliance_id
        assigned.add(best.alliance_id)

    # Regular group picks next (by power desc)
    regular_attackers.sort(
        key=lambda pair: self._get_power(pair[0].alliance_id),
        reverse=True,
    )
    for attacker, strategy in regular_attackers:
        available = [
            d for d in bracket_defenders
            if d.alliance_id not in assigned
        ]
        if not available:
            break
        best = self._pick_by_strategy(attacker, available, state, strategy)
        targets[attacker.alliance_id] = best.alliance_id
        assigned.add(best.alliance_id)

    return targets
```

**Ordering guarantee:** When no `maximize_tier` is active,
`priority_attackers` is empty and `regular_attackers` contains all
algo attackers — the loop degenerates to the current behavior (single
group sorted by power). The only change for non-maximize_tier
strategies is the if/else dispatch now goes through `_pick_by_strategy`.

**When `maximize_tier` is active:**
1. Pinned targets resolve first (unchanged).
2. Top-N `maximize_tier` attackers pick next, by power desc, using
   forward sim.
3. Remaining attackers pick last, by power desc, using their
   resolved strategy (fallback for `maximize_tier` non-top-N,
   or whatever the 4-level resolution yielded).

---

## 6. `_resolve_attacker` — No Changes Needed

The 4-level resolution already returns a strategy string. Adding
`"rank_aware"` and `"maximize_tier"` to `_VALID_STRATEGIES` in
validation is sufficient — `_resolve_attacker` passes the string
through without inspecting it.

---

## Files Changed

| File | Changes |
|------|---------|
| `src/spice_war/utils/data_structures.py` | Add `event_schedule` optional field to `GameState` |
| `src/spice_war/game/simulator.py` | Pass `event_schedule` to `GameState` constructor |
| `src/spice_war/utils/validation.py` | Add `rank_aware`, `maximize_tier` to valid strategies; add `tier_optimization_top_n`, `tier_optimization_fallback` to allowed keys; add validation for new fields |
| `src/spice_war/web/bridge.py` | Add `tier_optimization_top_n`, `tier_optimization_fallback` to allowed keys |
| `src/spice_war/models/configurable.py` | Add `_rank_and_tier()`, `_pick_rank_aware_target()`, `_get_top_n_ids()`, `_forward_sim_tier()`, `_pick_maximize_tier_target()`, `_pick_by_strategy()`; restructure `generate_targets()` for priority/regular groups |

---

## Implementation Order

| Step | Area | Files | Complexity |
|------|------|-------|------------|
| 1 | GameState event_schedule | `data_structures.py`, `simulator.py` | Trivial |
| 2 | Validation + bridge keys | `validation.py`, `bridge.py` | Low |
| 3 | `_rank_and_tier` helper | `configurable.py` | Trivial |
| 4 | `_pick_rank_aware_target` | `configurable.py` | Moderate |
| 5 | `_pick_by_strategy` dispatcher | `configurable.py` | Low |
| 6 | `generate_targets` restructure | `configurable.py` | Moderate |
| 7 | `_get_top_n_ids` | `configurable.py` | Low |
| 8 | `_forward_sim_tier` | `configurable.py` | Moderate |
| 9 | `_pick_maximize_tier_target` | `configurable.py` | Low |
| 10 | Tests | `tests/test_tier_targeting.py` | High |

Steps 1-2 can be done first and tested independently. Steps 3-6
deliver `rank_aware` as a usable strategy. Steps 7-9 add
`maximize_tier` on top.

---

## Test Mapping

Tests from the requirements doc, mapped to implementation details:

### `rank_aware` (steps 3-6)

| # | Test | What to assert |
|---|------|----------------|
| 1 | Tier-improving target over higher ESV | Set up attacker near tier 3/2 boundary. Defender B is just above in rank, lower ESV. Defender A is far away, higher ESV. Verify `rank_aware` picks B. |
| 2 | Rank-improving target when tier equal | Two defenders yield same tier improvement. One yields better rank. Verify the better-rank target is picked. |
| 3 | Falls back to ESV when no rank improvement | Attacker at rank 40 (tier 5). All defenders far away. All scores 0. Verify target matches ESV ordering. |
| 4 | Close competitor preferred | Defender just above attacker preferred over richer defender far away. |
| 5 | Both gain and loss reflected | Verify attacker rises AND defender falls in projected standings. |
| 6 | Rankings are global | Include alliances from both factions. Verify rank computation uses all alliances. |
| 7 | Tie-breaking chain | Equal rank-aware scores → break by ESV → spice → id. |
| 8 | Targeting temperature | `temperature > 0` → `_softmax_select` called with rank-aware scores. Multiple runs with same seed produce same result; different seeds can produce different results. |
| 9 | 4-level resolution | Set `rank_aware` via `faction_targeting_strategy` and via `default_targets` `{"strategy": "rank_aware"}`. Verify correct resolution. |
| 10 | Single defender | Only one available → selected regardless of score. |

### `maximize_tier` (steps 7-9)

| # | Test | What to assert |
|---|------|----------------|
| 11 | Picks tier-improving target | Construct state where forward sim with target A yields tier 3, target B yields tier 2. Verify B picked despite lower ESV. |
| 12 | Top-N within faction | Only top-N by faction spice use forward sim. Verify via mock or spy that `_forward_sim_tier` is called only for top-N attackers. |
| 13 | Top-N resolve first | Top-N attacker with lower power picks before non-top-N with higher power. |
| 14 | Forward sim deterministic | Same state + same candidate → same result. Call `_forward_sim_tier` twice, verify identical. |
| 15 | Forward sim doesn't mutate state | Save `state.current_spice` before, verify identical after `generate_targets`. |
| 16 | RNG isolation | Run battle outcomes after `maximize_tier` targeting. Verify outcomes match what they would be without maximize_tier (same seed, same RNG sequence). |
| 17 | Fewer than N in faction | Faction has 3 alliances, N=5. All 3 use forward sim. |
| 18 | Tie-breaking | Same final tier → better rank → higher ESV → alpha id. |
| 19 | `top_n` config | Set `tier_optimization_top_n: 3`. Verify only 3 alliances use forward sim. |
| 20 | Fallback config | Set `tier_optimization_fallback: "highest_spice"`. Verify non-top-N use highest_spice. |
| 21 | Works with outer MC | Run MC with `maximize_tier`. Verify results vary across seeds and tiers are computed correctly. |
| 22 | All top-N pinned | All top-N have pinned targets. No forward sims run. Fallback attackers use fallback strategy. |

### Configuration & Validation (step 2)

| # | Test | What to assert |
|---|------|----------------|
| 23 | `rank_aware` accepted everywhere | Valid in `targeting_strategy`, `default_targets.strategy`, `event_targets.strategy`, `faction_targeting_strategy` |
| 24 | `maximize_tier` accepted everywhere | Same as above |
| 25 | Invalid `top_n` | `tier_optimization_top_n: 0` or `-1` or `"five"` → `ValidationError` |
| 26 | Invalid fallback | `tier_optimization_fallback: "maximize_tier"` or `"invalid"` → `ValidationError` |
| 27 | Fields rejected for other strategies | `tier_optimization_top_n: 5` with `targeting_strategy: "expected_value"` → `ValidationError` |

### Backward Compatibility (step 6)

| # | Test | What to assert |
|---|------|----------------|
| 28 | Default unchanged | Empty config → `expected_value` → identical results to current code |
| 29 | Existing strategies unaffected | `expected_value` and `highest_spice` produce identical results to current code. Run with known seed, compare targeting output. |
