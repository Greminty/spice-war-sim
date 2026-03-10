# Tier-Aware Targeting — Requirements

## Goal

Add two new targeting strategies — **`rank_aware`** and **`maximize_tier`** —
that optimize for end-of-war reward tier placement rather than immediate spice
gain. `rank_aware` is a cheap single-event scoring function suitable as a
default. `maximize_tier` runs deterministic forward projections of the
remaining war for the top N alliances and falls back to a cheaper strategy for
the rest.

## Motivation

The existing strategies (`expected_value`, `highest_spice`) are myopic — they
maximize immediate spice stolen without considering where an alliance ends up
relative to everyone else at war's end. But reward tiers depend on relative
ranking:

| Tier | Rank |
|------|------|
| 1 | 1st |
| 2 | 2nd–3rd |
| 3 | 4th–10th |
| 4 | 11th–20th |
| 5 | 21st+ |

Stealing 100k from the #1 alliance and 100k from the #30 alliance have the
same ESV, but very different competitive impact. Stealing from a close
competitor above you is doubly valuable — you rise, they fall. The current
strategies can't express this.

**Example:** Alliance at rank 4 (tier 3, 10k behind rank 3) choosing between:
- Defender A: rank 15, 3M spice — ESV 180k
- Defender B: rank 3, 2M spice — ESV 120k

ESV picks Defender A. But attacking B could push you into tier 2 (rank 3) while
pushing them to rank 4 — a tier improvement worth far more than the 60k ESV
difference.

---

## 1. Strategy: `rank_aware`

### 1.1 Overview

A single-event-horizon scoring function that evaluates each candidate target by
projected rank and tier improvement rather than raw spice stolen. Same
computational cost as `expected_value`.

### 1.2 Scoring Algorithm

For each attacker choosing among available defenders, score each candidate
defender D:

1. Compute expected spice transfer using existing ESV math (expected amount
   stolen, not the ESV score itself — the probability-weighted theft amount).
2. Project post-battle standings: attacker gains the expected transfer, defender
   loses it, all other alliances unchanged.
3. Compute attacker's current rank/tier and projected rank/tier from the
   projected standings (rank = position among all alliances sorted by spice,
   tier = from `calculate_final_rankings` thresholds).
4. Score: `tier_improvement * 1000 + rank_improvement`
   - `tier_improvement = current_tier - projected_tier` (positive = better tier)
   - `rank_improvement = current_rank - projected_rank` (positive = better rank)
5. Pick the candidate with the highest score.

### 1.3 Tie-Breaking

When two candidates have equal rank-aware scores:
1. Higher ESV
2. Higher defender spice
3. Alphabetical defender ID

### 1.4 Fallback When No Improvement Possible

If all candidates score <= 0 (no target changes the attacker's rank or tier),
the scores are all zero and tie-breaking selects by ESV. This means
`rank_aware` degrades gracefully to ESV-like behavior for alliances far from
tier boundaries.

### 1.5 Interaction with Existing Systems

- Follows the 4-level targeting resolution. Only applies when resolution yields
  `"rank_aware"` as the strategy.
- Respects `targeting_temperature` for softmax selection over rank-aware scores.
- Greedy by power order: strongest attacker picks first, target removed from
  pool.
- Pinned targets unaffected.

### 1.6 Edge Cases

- **Projected standings are approximate.** They use `current_spice` from
  `GameState` and don't account for other battles in the same event happening
  simultaneously. This is the same limitation ESV has — single-battle horizon.
- **Rank computation includes all alliances** (both factions), not just the
  current bracket. Tier boundaries are global.
- **Single candidate defender**: Selected deterministically regardless of
  score.

---

## 2. Strategy: `maximize_tier`

### 2.1 Overview

For the top N alliances (by current spice), evaluate each candidate target by
running a deterministic forward simulation of the remaining war and picking the
target that yields the best final tier. Alliances outside the top N use a
configurable fallback strategy. This provides a multi-event planning horizon
at moderate computational cost.

### 2.2 Config

```json
{
  "targeting_strategy": "maximize_tier",
  "tier_optimization_top_n": 5,
  "tier_optimization_fallback": "rank_aware"
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `tier_optimization_top_n` | int > 0 | `5` | Number of top alliances (by current spice, across both factions) that use forward projection. |
| `tier_optimization_fallback` | string | `"rank_aware"` | Strategy for alliances outside the top N. One of: `"expected_value"`, `"highest_spice"`, `"rank_aware"`. |

Both fields are invalid when `targeting_strategy` is not `"maximize_tier"` and should be rejected at validation time.

### 2.3 Top-N Determination

At each event, rank alliances **within the attacking faction** by
`current_spice` (descending). An attacker is "top N" if their faction rank is
<= `tier_optimization_top_n`. This uses faction rank rather than global rank
because alliances in the attacking faction are systematically lower in global
rank before they attack (the defending faction just gained spice from their
attack). Faction rank is a better proxy for "who has a realistic shot at
T1/2/3 after this event" and keeps N tight (5–8 captures realistic
contenders).

### 2.4 Resolution Order Within a Bracket

1. **Resolve pinned targets** (existing logic, unchanged).
2. **Resolve top-N attackers** in descending power order. For each:
   a. For each available (unassigned) defender D, run a deterministic forward
      simulation of the remaining war with this attacker assigned to D.
   b. Pick the defender D that yields the best final tier for this attacker.
   c. Lock in the choice; remove D from the available pool.
3. **Resolve fallback attackers** (non-top-N, non-pinned), using the fallback
   strategy, in descending power order.

Top-N attackers resolve first because they are generally the strongest
alliances and benefit most from first pick of defenders.

### 2.5 Forward Simulation

For each candidate target, the forward simulation:

1. Starts from the current `GameState` (current spice, remaining event
   schedule).
2. Applies the hypothetical target assignment for the current battle. Other
   targeting decisions in the current event (same bracket or other brackets)
   use `rank_aware`.
3. Simulates all remaining events using a deterministic model config:
   `random_seed=0`, `targeting_temperature=0`, `power_noise=0`,
   `outcome_noise=0`, `targeting_strategy="rank_aware"`.
4. Returns the final tier for the attacker being evaluated.

The forward sim reuses `simulate_war`. It does not modify any shared state — it
operates on copies. Using `rank_aware` (not `maximize_tier`) in the forward sim
avoids infinite recursion.

### 2.6 Tie-Breaking

When two candidate targets yield the same final tier:
1. Better final rank (lower number)
2. Higher ESV for the immediate battle
3. Alphabetical defender ID

### 2.7 RNG Isolation

The forward simulations use a fresh `ConfigurableModel` with `random_seed=0`
and no noise. This ensures:
- Forward projections are deterministic and don't consume the real model's RNG.
- Targeting decisions are consistent — evaluating the same candidate twice
  gives the same result.
- The outer MC loop's variance comes from outcome rolls and noise parameters
  on the real model, not from forward projections.

### 2.8 Edge Cases

- **Fewer than N alliances in attacking faction**: Top-N is capped at the
  faction size. If the faction has 3 alliances and N=5, all 3 use forward
  projection.
- **Top-N attacker not in bracket 1**: Possible with unusual spice
  distributions. Forward sim still works — the attacker just has fewer
  candidate targets.
- **Last event of the war**: Forward sim covers only this event. Degrades to
  `rank_aware` with deterministic outcome projection rather than
  expected-value projection.
- **First event of the war**: Forward sim covers the whole war — most valuable
  but most speculative.
- **Remaining event schedule**: The forward sim needs to know which events
  remain. It uses the events after the current one from the event schedule
  in `GameState.event_history` (events already completed) and the full
  schedule.

### 2.9 Performance

Benchmarked with the S3 dataset (46 alliances, ~0.7ms/sim):

| Top N | Combos/event | Standalone | Outer MC=500 | Outer MC=1000 |
|-------|-------------|-----------|-------------|--------------|
| 3 | ~20 | 14 ms | 7 s | 14 s |
| 5 | ~40 | 28 ms | 14 s | 28 s |
| 7 | ~60 | 42 ms | 21 s | 42 s |

Top-N is within the attacking faction, so the number of forward projections per
event is predictable: min(N, faction_bracket_1_size) × available_defenders.
Bracket 2+ alliances are unlikely to be top-N in practice, so they use fallback.

---

## 3. Configuration Summary

### 3.1 Valid Targeting Strategies

| Value | Behavior |
|-------|----------|
| `"expected_value"` | Maximize expected spice stolen (existing, default) |
| `"highest_spice"` | Target richest available defender (existing) |
| `"rank_aware"` | Maximize projected rank/tier improvement (new) |
| `"maximize_tier"` | Forward-projected tier optimization for top N (new) |

All four are valid values at every level of the targeting resolution hierarchy:
`event_targets`, `default_targets`, `faction_targeting_strategy`, and
`targeting_strategy`.

### 3.2 Example Configs

**Use rank-aware for everyone:**
```json
{
  "targeting_strategy": "rank_aware"
}
```

**Top 5 use forward projection, rest use rank-aware:**
```json
{
  "targeting_strategy": "maximize_tier",
  "tier_optimization_top_n": 5,
  "tier_optimization_fallback": "rank_aware"
}
```

**Top 3 use forward projection, rest use ESV:**
```json
{
  "targeting_strategy": "maximize_tier",
  "tier_optimization_top_n": 3,
  "tier_optimization_fallback": "expected_value"
}
```

**One faction uses rank-aware, the other uses ESV:**
```json
{
  "faction_targeting_strategy": {
    "Scarlet Legion": "rank_aware",
    "Golden Tribe": "expected_value"
  }
}
```

**Pin one alliance, rank-aware for the rest:**
```json
{
  "default_targets": {
    "VON": {"target": "Ghst"}
  },
  "targeting_strategy": "rank_aware"
}
```

---

## 4. Tests

### `rank_aware` Strategy

| # | Test | Validates |
|---|------|-----------|
| 1 | **Prefers tier-improving target over higher ESV** | Attacker near tier boundary picks defender whose loss pushes attacker into better tier, even though another defender has higher ESV |
| 2 | **Prefers rank-improving target when tier is equal** | Two targets yield same tier — picks the one that improves rank more |
| 3 | **Falls back to ESV when no rank improvement** | Attacker far from any tier boundary — all candidates score 0, selection matches ESV ordering |
| 4 | **Close competitor preferred** | Defender just above attacker in ranking is preferred over a richer defender far away in ranking |
| 5 | **Projected standings account for both gain and loss** | Attacker rises (gains spice) and defender falls (loses spice) — both effects reflected in projected rank |
| 6 | **Rankings are global** | Rank computation includes all alliances across both factions, not just the current bracket |
| 7 | **Tie-breaking by ESV, then spice, then id** | Equal rank-aware scores break to ESV, then defender spice, then alphabetical |
| 8 | **Respects targeting_temperature** | Softmax selection applies over rank-aware scores when temperature > 0 |
| 9 | **Works in 4-level resolution** | `rank_aware` set via `faction_targeting_strategy` or `default_targets` `{"strategy": "rank_aware"}` |
| 10 | **Single defender in bracket** | Trivially selected regardless of score |

### `maximize_tier` Strategy

| # | Test | Validates |
|---|------|-----------|
| 11 | **Picks target that improves final tier** | Forward sim shows target A yields tier 3, target B yields tier 2 — picks B despite lower ESV |
| 12 | **Top-N within faction** | Only top-N alliances by spice within the attacking faction use forward projection; others use fallback strategy |
| 13 | **Top-N attackers resolve first** | Top-N attackers pick targets before fallback attackers, getting first choice of defenders |
| 14 | **Forward sim is deterministic** | Same game state + same candidate → same projected tier every time |
| 15 | **Forward sim doesn't mutate state** | After `generate_targets` returns, `GameState` and model RNG are unchanged |
| 16 | **RNG isolation** | Forward sims don't affect the real model's RNG sequence — subsequent battle outcomes are identical whether or not maximize_tier ran |
| 17 | **Fewer than N in faction** | When attacking faction has fewer alliances than N, all of them use forward projection |
| 18 | **Tie-breaking by rank, then ESV, then id** | Two targets yield same final tier — picks better rank, then higher ESV, then alphabetical |
| 19 | **tier_optimization_top_n config** | Setting `top_n: 3` limits forward projection to top 3 alliances |
| 20 | **tier_optimization_fallback config** | Setting fallback to `"highest_spice"` causes non-top-N attackers to use highest-spice targeting |
| 21 | **Works with outer MC loop** | `maximize_tier` produces correct, varied results across MC seeds |
| 22 | **All top-N pinned** | When all top-N attackers have pinned targets, no forward projections run and fallback attackers use fallback strategy |

### Configuration & Validation

| # | Test | Validates |
|---|------|-----------|
| 23 | **rank_aware accepted everywhere** | Valid in `targeting_strategy`, `default_targets`, `event_targets`, `faction_targeting_strategy` |
| 24 | **maximize_tier accepted everywhere** | Same as above |
| 25 | **Invalid tier_optimization_top_n** | Non-positive integer raises validation error |
| 26 | **Invalid tier_optimization_fallback** | Unrecognized strategy name raises validation error |
| 27 | **maximize_tier fields rejected for other strategies** | `tier_optimization_top_n` present but `targeting_strategy` is `"expected_value"` — raises validation error |

### Backward Compatibility

| # | Test | Validates |
|---|------|-----------|
| 28 | **Default behavior unchanged** | No new config fields → `expected_value` targeting, identical to current behavior |
| 29 | **Existing strategies unaffected** | `expected_value` and `highest_spice` produce identical results to current code |

---

## 5. Non-Goals

- **Monte Carlo within forward projection (Strategy C)** — the outer MC loop
  already handles outcome variance. Nesting MC inside targeting would add
  significant cost (~20x) with marginal benefit.
- **Game-theoretic equilibrium** — alliances pick greedily by power order, not
  via iterated best response or Nash equilibrium computation.
- **Changes to reinforcement logic** — reinforcements remain unchanged.
- **Changes to battle outcome or damage split models** — only target selection
  is affected.
- **Changes to the `BattleModel` interface** — all changes are internal to
  `ConfigurableModel`.
- **Web UI changes** — adding the new strategy options to the web UI strategy
  selector is a separate task.
