# Statistical Fairness Test — Design

## Overview

Single test file `tests/test_statistical_fairness.py` that runs 1000 simulations of a symmetric 10v10 scenario and asserts statistical fairness properties. A module-scoped pytest fixture runs all simulations once; individual test functions assert different properties against the shared results.

## Dependencies

The chi-squared test requires computing a p-value from a chi-squared statistic. Two options:

**Option A — Add scipy as a dev dependency.** Use `scipy.stats.chisquare` directly. Clean, one-liner, well-tested. scipy is heavy (~130MB) but only needed for tests.

**Option B — Critical value lookup.** Hardcode the chi-squared critical value for df=9 at p=0.001 (27.877). Compare the test statistic against it directly. No new dependency. Downside: can't print exact p-values in the summary output, only pass/fail.

Recommendation: **Option A** — add `scipy` to `[project.optional-dependencies] dev`. The printed p-values are useful for inspection and the dependency cost is test-only.

## Module Structure

```
tests/test_statistical_fairness.py
```

### Constants

```python
NUM_SEEDS = 1000

# Assertion thresholds
MAX_WITHIN_FACTION_CV = 0.02           # 2%
CHI_SQUARED_MIN_P = 0.001              # reject uniformity below this
OUTCOME_RATE_TOLERANCE = 0.05          # 5 percentage points

# Expected heuristic outcome rates (power ratio 1.0)
EXPECTED_RATES = {
    "wednesday": {"full_success": 0.50, "partial_success": 0.35, "fail": 0.15},
    "saturday":  {"full_success": 0.25, "partial_success": 0.40, "fail": 0.35},
}
```

### Data Container

```python
@dataclass
class FairnessResults:
    alliances: list[Alliance]
    final_spice: dict[str, list[int]]        # alliance_id -> [spice per seed]
    intra_faction_ranks: dict[str, list[int]] # alliance_id -> [rank per seed]
    tiers: dict[str, list[int]]              # alliance_id -> [tier per seed]
    battle_outcomes: dict[str, Counter]       # day -> Counter{"full_success": n, ...}
    num_seeds: int
```

## Scenario Construction

```python
def _build_alliances() -> list[Alliance]:
```

Creates 20 `Alliance` objects: `red_01`–`red_10` and `blue_01`–`blue_10`, all with identical attributes (power=100, starting_spice=1_000_000, daily_spice_rate=50_000).

```python
def _build_schedule() -> list[EventConfig]:
```

Returns the 8-event symmetric schedule from the requirements doc. Hardcoded, not generated.

## Simulation Loop

```python
def _run_simulations(alliances, schedule, num_seeds) -> FairnessResults:
```

For each seed 0 through `num_seeds - 1`:

1. Create `ConfigurableModel({"random_seed": seed}, alliances)`.
2. Call `simulate_war(alliances, schedule, model)`.
3. From the result, collect:
   - `final_spice[aid]` — append to per-alliance list.
   - Intra-faction rank — sort each faction's alliances by final spice descending, tiebreak by alliance_id ascending. Assign ranks 1–10 within each faction. Append to per-alliance list.
   - `tiers[aid]` — from `result["rankings"]`, append to per-alliance list.
   - Battle outcomes — iterate `result["event_history"]`, for each battle append the outcome to `battle_outcomes[day]`.

### Intra-Faction Rank Computation

```python
for faction in ("red", "blue"):
    faction_aids = [a.alliance_id for a in alliances if a.faction == faction]
    sorted_aids = sorted(faction_aids, key=lambda aid: (-final_spice[aid], aid))
    for rank, aid in enumerate(sorted_aids, 1):
        intra_faction_ranks[aid].append(rank)
```

Tiebreaker on alliance_id means `red_01` wins ties over `red_02`, but exact ties should be rare across 1000 seeds, so this won't introduce measurable bias.

## Statistics & Assertions

### Test 1: Within-Faction Spice Symmetry

```python
def test_within_faction_spice_cv(fairness_results):
```

For each faction:
1. Compute the mean final spice per alliance (mean of that alliance's 1000 values).
2. Collect the 10 per-alliance means into a list.
3. Compute the coefficient of variation: `std(means) / mean(means)`.
4. Assert CV < `MAX_WITHIN_FACTION_CV` (2%).

### Test 2: Rank Uniformity

```python
def test_rank_uniformity(fairness_results):
```

For each alliance:
1. Count how many times it appeared in each intra-faction rank (1–10) across all seeds.
2. Expected count per rank = `num_seeds / 10` = 100.
3. Run `scipy.stats.chisquare(observed, expected)` → returns `(statistic, p_value)`.
4. Assert `p_value >= CHI_SQUARED_MIN_P` (0.001).

### Test 3: Battle Outcome Rates

```python
def test_battle_outcome_rates(fairness_results):
```

For each day (`"wednesday"`, `"saturday"`):
1. Compute observed rates: `count / total` for each outcome.
2. Compare against `EXPECTED_RATES[day]`.
3. Assert each rate is within `OUTCOME_RATE_TOLERANCE` (5pp) of expected.

## Summary Output

Printed by the fixture (or a dedicated helper called from the fixture) so it appears once regardless of how many test functions run. Uses `print()` — visible with `pytest -s` or `pytest -v`.

```python
def _print_summary(results: FairnessResults):
```

Sections:
1. **Header** — seed count.
2. **Final Spice** — per-alliance mean ± std, faction means.
3. **Rank Distribution** — per-alliance chi-squared p-values.
4. **Battle Outcomes** — per-day observed vs expected rates.

Format matches the requirements doc example output.

## Fixture

```python
@pytest.fixture(scope="module")
def fairness_results():
    alliances = _build_alliances()
    schedule = _build_schedule()
    results = _run_simulations(alliances, schedule, NUM_SEEDS)
    _print_summary(results)
    return results
```

`scope="module"` ensures simulations run once, shared across all test functions in the file.

## Pytest Marker

```python
pytestmark = pytest.mark.slow
```

Applied at module level so all tests in the file inherit the marker. Requires registering the marker in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = ["slow: long-running statistical tests"]
```

## Performance

Each `simulate_war` call processes 8 events with ~10 battles each. At 1000 seeds, that's ~80,000 battles total. The simulation is pure arithmetic — no I/O, no sleeps. Expected runtime: well under 60 seconds.

## Changes Required

| File | Change |
|------|--------|
| `pyproject.toml` | Add `scipy` to dev dependencies |
| `pyproject.toml` | Register `slow` pytest marker |
| `tests/test_statistical_fairness.py` | New file — the full test |
