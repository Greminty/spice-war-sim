# Monte Carlo Simulation — Design

## Overview

New module `src/spice_war/game/monte_carlo.py` runs the existing war simulation many times with varying seeds and aggregates results. New CLI script `scripts/run_monte_carlo.py` exposes this via the command line. No changes to existing code.

## Data Structure — `MonteCarloResult`

**Location:** `src/spice_war/game/monte_carlo.py`

Co-located with the engine rather than in `data_structures.py` to keep the shared module lean — `MonteCarloResult` is only produced and consumed by Monte Carlo code.

```python
from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class MonteCarloResult:
    num_iterations: int
    base_seed: int
    tier_counts: dict[str, Counter[int]] = field(default_factory=dict)
    spice_totals: dict[str, list[int]] = field(default_factory=dict)

    def tier_distribution(self, alliance_id: str) -> dict[int, float]:
        counts = self.tier_counts[alliance_id]
        return {tier: counts[tier] / self.num_iterations for tier in range(1, 6)}

    def spice_stats(self, alliance_id: str) -> dict[str, int]:
        values = sorted(self.spice_totals[alliance_id])
        n = len(values)
        return {
            "mean": round(statistics.mean(values)),
            "median": round(statistics.median(values)),
            "min": values[0],
            "max": values[-1],
            "p25": values[n // 4],
            "p75": values[3 * n // 4],
        }

    def rank_summary(self) -> dict[str, dict[int, float]]:
        return {aid: self.tier_distribution(aid) for aid in self.tier_counts}

    def most_likely_tier(self, alliance_id: str) -> int:
        counts = self.tier_counts[alliance_id]
        return max(range(1, 6), key=lambda t: counts[t])
```

### Notes

- `tier_distribution` always returns all 5 tiers (1–5), using 0 counts for tiers never reached. This keeps the output shape uniform.
- `spice_stats` returns rounded ints for consistency with the rest of the codebase (spice is always integral).
- Percentile computation uses simple indexing (`values[n // 4]`). For `n=1000`, this gives index 250 for p25 and 750 for p75, which is standard nearest-rank behavior. No need for `statistics.quantiles` (Python 3.8+ only provides interpolated quartiles, which would return floats).

## Core Engine — `run_monte_carlo()`

**Location:** `src/spice_war/game/monte_carlo.py`

```python
from spice_war.game.simulator import simulate_war
from spice_war.models.configurable import ConfigurableModel
from spice_war.utils.data_structures import Alliance, EventConfig


def run_monte_carlo(
    alliances: list[Alliance],
    event_schedule: list[EventConfig],
    model_config: dict,
    num_iterations: int,
    base_seed: int = 0,
) -> MonteCarloResult:
    result = MonteCarloResult(
        num_iterations=num_iterations,
        base_seed=base_seed,
    )

    # Initialize collection structures
    alliance_ids = [a.alliance_id for a in alliances]
    for aid in alliance_ids:
        result.tier_counts[aid] = Counter()
        result.spice_totals[aid] = []

    for i in range(num_iterations):
        # Copy config and override seed
        iter_config = dict(model_config)
        iter_config["random_seed"] = base_seed + i

        model = ConfigurableModel(iter_config, alliances)
        war_result = simulate_war(alliances, event_schedule, model)

        for aid in alliance_ids:
            result.spice_totals[aid].append(war_result["final_spice"][aid])
            result.tier_counts[aid][war_result["rankings"][aid]] += 1

    return result
```

### Notes

- `dict(model_config)` is a shallow copy — sufficient because we only replace `random_seed` (a scalar), and no nested dicts are mutated.
- Each iteration constructs a fresh `ConfigurableModel` with a new `random.Random` instance, so iterations are fully independent.
- The original `random_seed` in `model_config` (if present) is overwritten by `base_seed + i`.

## CLI — `scripts/run_monte_carlo.py`

Follows the same structure as `run_battle.py`: `main(argv)` function, argument parsing, validation, then either print or write JSON.

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys

from spice_war.game.monte_carlo import run_monte_carlo
from spice_war.utils.validation import ValidationError, load_model_config, load_state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Monte Carlo simulation")
    parser.add_argument("state_file", help="Path to initial state JSON")
    parser.add_argument("model_file", nargs="?", default=None, help="Path to model config JSON")
    parser.add_argument("-n", "--num-iterations", type=int, default=1000, help="Number of simulation runs")
    parser.add_argument("--base-seed", type=int, default=0, help="Starting seed")
    parser.add_argument("--output", metavar="PATH", help="Write JSON results to file")
    parser.add_argument("--quiet", action="store_true", help="Suppress summary table")
    args = parser.parse_args(argv)

    try:
        alliances, schedule = load_state(args.state_file)
        alliance_ids = {a.alliance_id for a in alliances}
        model_config = load_model_config(args.model_file, alliance_ids)
    except ValidationError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    result = run_monte_carlo(
        alliances, schedule, model_config,
        num_iterations=args.num_iterations,
        base_seed=args.base_seed,
    )

    if not args.quiet:
        _print_summary(alliances, result)

    if args.output:
        _write_json(args.output, result)

    return 0
```

### `_print_summary`

Sorts alliances by mean final spice (descending) for display. Computes column widths from alliance IDs.

```python
def _print_summary(alliances: list, result: MonteCarloResult) -> None:
    n = result.num_iterations
    end_seed = result.base_seed + n - 1
    print(f"Monte Carlo Simulation — {n} iterations (seeds {result.base_seed}–{end_seed})")
    print()

    # Sort alliances by mean spice descending
    sorted_aids = sorted(
        [a.alliance_id for a in alliances],
        key=lambda aid: result.spice_stats(aid)["mean"],
        reverse=True,
    )
    name_width = max(len(aid) for aid in sorted_aids)

    # Tier distribution table
    print("Tier Distribution (% of iterations):")
    print(f"{'':>{name_width}}    Tier 1    Tier 2    Tier 3    Tier 4    Tier 5")
    for aid in sorted_aids:
        dist = result.tier_distribution(aid)
        parts = [f"{dist[t] * 100:>7.1f}%" for t in range(1, 6)]
        print(f"{aid:>{name_width}}  {'  '.join(parts)}")
    print()

    # Spice summary table
    print("Spice Summary:")
    print(f"{'':>{name_width}}        Mean      Median         Min         Max")
    for aid in sorted_aids:
        stats = result.spice_stats(aid)
        print(
            f"{aid:>{name_width}}"
            f"  {stats['mean']:>11,}"
            f"  {stats['median']:>11,}"
            f"  {stats['min']:>11,}"
            f"  {stats['max']:>11,}"
        )
```

### `_write_json`

```python
def _write_json(path: str, result: MonteCarloResult) -> None:
    data = {
        "num_iterations": result.num_iterations,
        "base_seed": result.base_seed,
        "tier_distribution": {
            aid: {str(tier): frac for tier, frac in dist.items()}
            for aid, dist in result.rank_summary().items()
        },
        "spice_stats": {
            aid: result.spice_stats(aid)
            for aid in result.tier_counts
        },
        "raw_results": _build_raw_results(result),
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _build_raw_results(result: MonteCarloResult) -> list[dict]:
    alliance_ids = list(result.tier_counts.keys())
    n = result.num_iterations
    raw = []
    for i in range(n):
        entry = {
            "seed": result.base_seed + i,
            "final_spice": {aid: result.spice_totals[aid][i] for aid in alliance_ids},
            "rankings": {},
        }
        # Reconstruct per-iteration tier from spice rank
        # We don't store per-iteration tiers, so recompute from spice
        raw.append(entry)
    return raw
```

**Problem:** The requirements spec shows `rankings` in each raw result entry, but `MonteCarloResult` only stores aggregate `tier_counts`, not per-iteration tiers. Two options:

**Option A — Store per-iteration rankings.** Add a `per_iteration` field: `list[dict]` where each entry is `{"final_spice": {...}, "rankings": {...}}`. Increases memory proportional to `num_iterations * num_alliances`, but for typical runs (1000 iterations, 4–20 alliances) this is negligible.

**Option B — Recompute rankings from spice in `_build_raw_results`.** Use `calculate_final_rankings()` on the stored per-iteration spice values. Avoids extra storage but adds a dependency on mechanics and duplicates the ranking call.

**Recommendation: Option A** — store per-iteration data. It's cleaner, trivially small in memory, and means the raw results exactly match what `simulate_war` returned. Implementation: add a `per_iteration` field to `MonteCarloResult`:

```python
@dataclass
class MonteCarloResult:
    num_iterations: int
    base_seed: int
    tier_counts: dict[str, Counter[int]] = field(default_factory=dict)
    spice_totals: dict[str, list[int]] = field(default_factory=dict)
    per_iteration: list[dict] = field(default_factory=list)
```

Each iteration appends:
```python
result.per_iteration.append({
    "seed": base_seed + i,
    "final_spice": dict(war_result["final_spice"]),
    "rankings": dict(war_result["rankings"]),
})
```

Then `_build_raw_results` simply returns `result.per_iteration`.

## Tests — `tests/test_monte_carlo.py`

All tests use the existing `tests/fixtures/sample_state.json` and `tests/fixtures/sample_model.json`. A module-scoped fixture runs a small simulation (n=20) for tests that need shared results. Individual determinism/correctness tests run their own smaller simulations.

### Fixture

```python
import pytest
from spice_war.game.monte_carlo import run_monte_carlo, MonteCarloResult
from spice_war.utils.validation import load_state, load_model_config

FIXTURES = "tests/fixtures"

@pytest.fixture(scope="module")
def mc_result():
    alliances, schedule = load_state(f"{FIXTURES}/sample_state.json")
    alliance_ids = {a.alliance_id for a in alliances}
    model_config = load_model_config(f"{FIXTURES}/sample_model.json", alliance_ids)
    return run_monte_carlo(alliances, schedule, model_config, num_iterations=20, base_seed=0)
```

### Test Implementations

| # | Test | Implementation |
|---|------|----------------|
| 1 | **Deterministic with same base seed** | Run `run_monte_carlo` twice with identical args (n=5, base_seed=0). Assert `result1.spice_totals == result2.spice_totals` and `result1.tier_counts == result2.tier_counts`. |
| 2 | **Different base seed → different results** | Run with base_seed=0 and base_seed=100 (n=10). Assert `result1.spice_totals != result2.spice_totals`. |
| 3 | **Iteration count respected** | Use `mc_result` fixture. For each alliance_id, assert `len(result.spice_totals[aid]) == 20`. |
| 4 | **Tier counts sum to num_iterations** | Use `mc_result` fixture. For each alliance_id, assert `sum(result.tier_counts[aid].values()) == 20`. |
| 5 | **Tier distribution sums to 1.0** | Use `mc_result` fixture. For each alliance_id, assert `sum(result.tier_distribution(aid).values()) ≈ 1.0` (pytest.approx). |
| 6 | **Spice stats correctness** | Run with n=5, base_seed=0. Manually collect the 5 final_spice values for one alliance. Compute expected mean/median/min/max/p25/p75 and compare with `result.spice_stats(aid)`. |
| 7 | **Most likely tier** | Use `mc_result` fixture. For each alliance, verify `most_likely_tier(aid)` equals the tier with the max count in `tier_counts[aid]`. |
| 8 | **CLI runs without error** | Call `main(["tests/fixtures/sample_state.json", "tests/fixtures/sample_model.json", "-n", "5", "--quiet"])`. Assert return value is 0. |
| 9 | **CLI --output writes valid JSON** | Call `main` with `--output` pointing to a `tmp_path` file, `-n 5`. Parse the output file, assert keys `num_iterations`, `base_seed`, `tier_distribution`, `spice_stats`, `raw_results` exist. Assert `len(raw_results) == 5`. |
| 10 | **CLI --quiet suppresses stdout** | Call `main` with `--quiet`, `-n 5`. Use `capsys.readouterr()` and assert `out == ""`. |

### Test details

- Tests 1, 2, 6 run their own small simulations (n=5 or n=10) rather than using the shared fixture, because they need specific seed/iteration configurations.
- Tests 3, 4, 5, 7 share the `mc_result` fixture (n=20) to avoid redundant simulation runs.
- Tests 8, 9, 10 test the CLI's `main()` function directly (no subprocess), matching the pattern used in the existing test suite.
- Test 6 (spice stats correctness): run `simulate_war` 5 times manually with seeds 0–4 to get expected spice values, then compare against `run_monte_carlo(n=5)`. This validates that the aggregation logic matches individual runs.

## File Changes Summary

| File | Change |
|------|--------|
| `src/spice_war/game/monte_carlo.py` | New file — `MonteCarloResult` dataclass + `run_monte_carlo()` |
| `scripts/run_monte_carlo.py` | New file — CLI entry point |
| `tests/test_monte_carlo.py` | New file — 10 tests |

No changes to any existing files.

## Performance

Each `simulate_war` call is pure arithmetic (~80 battles for 8 events with the 4-alliance fixture, more for 20-alliance scenarios). At n=1000 with 4 alliances: well under 10 seconds. At n=1000 with 20 alliances and 8 events: under 60 seconds. No parallelism needed for v1.
