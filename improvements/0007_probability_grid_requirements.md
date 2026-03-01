# Probability Grid — Requirements

## Goal

Display heuristic full-success probability grids for every attacker→defender
pairing in a state file. Gives a quick visual read on which matchups are
favorable before running any simulation.

## Scope

One new CLI script (`scripts/probability_grid.py`). No changes to existing game
logic or model code — the script reimplements the heuristic formula directly to
stay dependency-free.

---

## CLI

```
usage: probability_grid.py STATE_FILE
```

| Argument | Default | Description |
|---|---|---|
| `STATE_FILE` | *(required)* | Path to initial state JSON |

## Output

Four grids printed to stdout, one per (day, attacker faction) combination:

1. Wednesday: Faction A → Faction B
2. Wednesday: Faction B → Faction A
3. Saturday: Faction A → Faction B
4. Saturday: Faction B → Faction A

Each grid is a matrix:

- **Rows** = attacking alliances, sorted by power descending
- **Columns** = defending alliances, sorted by power descending
- **Cells** = heuristic full-success probability as an integer percentage
  (`-` for 0%, `100` for ≥ 99.95%)

### Heuristic Formulas

These match `ConfigurableModel._heuristic_probabilities` in
`models/configurable.py`:

| Day | Full Success |
|---|---|
| Wednesday | `clamp(2.5 × ratio − 2.0)` |
| Saturday | `clamp(3.25 × ratio − 3.0)` |

Where `ratio = attacker_power / defender_power` and
`clamp(x) = max(0, min(1, x))`.

## Non-Goals

- Partial-success or custom outcome probabilities in the grid.
- Incorporating `battle_outcome_matrix` overrides from a model file.
- CSV or JSON output formats.
