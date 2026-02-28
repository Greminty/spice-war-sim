# run_battle.py — Requirements

## Summary

A command-line script that runs a full multi-event war simulation from two input files: an initial state config and an optional model config. Replaces the existing `ScenarioRunner` and `run_single_battle.py`.

## CLI Interface

```
python scripts/run_battle.py <state_file> [model_file] [options]
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `state_file` | Yes | Path to initial state JSON |
| `model_file` | No | Path to model config JSON. If omitted, all model decisions use power-ratio heuristics. If provided, the file may be empty (`{}`) — heuristics fill any gaps. |

### Options

| Flag | Description |
|------|-------------|
| `--output PATH` | Write a rich JSON replay log to PATH |
| `--seed N` | Override the random seed from model config (or set one if no model config is provided) |
| `--quiet` | Suppress stdout summary (only useful with `--output`) |

## Input File Formats

### Initial State Config (`state_file`)

Contains the factual setup of the war — alliance definitions and event schedule.

```json
{
  "alliances": [
    {
      "alliance_id": "RedWolves",
      "faction": "red",
      "power": 110,
      "starting_spice": 2000000,
      "daily_rate": 50000
    },
    {
      "alliance_id": "BlueLions",
      "faction": "blue",
      "power": 95,
      "starting_spice": 1800000,
      "daily_rate": 45000
    }
  ],
  "event_schedule": [
    {"attacker_faction": "red", "day": "wednesday", "days_before": 3},
    {"attacker_faction": "blue", "day": "saturday", "days_before": 4}
  ]
}
```

#### Alliance Fields

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `alliance_id` | Yes | string | Unique identifier |
| `faction` | Yes | string | Faction membership (e.g. `"red"`, `"blue"`) |
| `power` | Yes | number | Alliance strength, used by model heuristics |
| `starting_spice` | Yes | number | Initial spice amount |
| `daily_rate` | Yes | number | Passive spice income per day |

#### Event Schedule Fields

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `attacker_faction` | Yes | string | Which faction attacks this event |
| `day` | Yes | string | `"wednesday"` or `"saturday"` — affects outcome probabilities |
| `days_before` | Yes | number | Days of passive income applied before this event |

### Model Config (`model_file`)

Contains all optional modeling assumptions the user can supply. Every field is optional — omitted fields fall back to power-ratio heuristics.

```json
{
  "random_seed": 42,
  "battle_outcome_matrix": {
    "wednesday": {
      "RedWolves": {
        "BlueLions": {"full_success": 0.9, "partial_success": 0.1}
      }
    },
    "saturday": {
      "BlueLions": {
        "RedWolves": {"full_success": 0.6, "partial_success": 0.3}
      }
    }
  },
  "event_targets": {
    "1": {
      "RedWolves": "BlueLions",
      "RedFalcons": "BlueShields"
    }
  },
  "event_reinforcements": {
    "1": {
      "BlueShields": "BlueLions"
    }
  },
  "damage_weights": {
    "RedWolves": 0.6,
    "RedFalcons": 0.4
  }
}
```

#### Model Config Fields

| Field | Type | Description |
|-------|------|-------------|
| `random_seed` | integer | Seed for reproducible RNG. Overridden by `--seed` CLI flag. |
| `battle_outcome_matrix` | nested dict | Per-day, per-attacker, per-defender outcome probabilities for M3. Keys: `day -> attacker_id -> defender_id -> {full_success, partial_success}`. |
| `event_targets` | dict | Per-event targeting overrides for M1. Keys: `event_number (string) -> attacker_id -> defender_id`. |
| `event_reinforcements` | dict | Per-event reinforcement overrides for M2. Keys: `event_number (string) -> untargeted_id -> targeted_id`. |
| `damage_weights` | dict | Per-alliance damage split weights for M4. Keys: `alliance_id -> weight (number)`. Replaces the old per-alliance `damage_weight` field. |

`damage_weight` is no longer an alliance property in the state file. It belongs here as part of `damage_weights`.

## Stdout Output

Unless `--quiet` is set, the script prints a human-readable summary covering every stage of the simulation.

### Structure

#### 1. Header

Files loaded and seed in use.

```
State: data/scenarios/war_state.json
Model: data/scenarios/war_model.json
Seed:  42
```

#### 2. Initial State

All alliances with their starting attributes.

```
Initial State:
  RedWolves      faction=red   power=110  spice=   2,000,000  daily_rate= 50,000
  RedFalcons     faction=red   power= 85  spice=   1,500,000  daily_rate= 40,000
  BlueLions      faction=blue  power= 95  spice=   1,800,000  daily_rate= 45,000
  BlueShields    faction=blue  power= 70  spice=     900,000  daily_rate= 30,000
```

#### 3. Per-Event Block (repeated for each event)

##### Event Header and Pre-Battle Spice

```
Event 1: red attacks on wednesday (+3 days income)
  Pre-battle spice:
    RedWolves      2,150,000
    RedFalcons     1,620,000
    BlueLions      1,935,000
    BlueShields    990,000
```

##### Bracket Assignments, Targeting, and Reinforcements (combined)

```
  Bracket 1:
    RedWolves (2,150,000)    -> BlueLions (1,935,000)
    RedFalcons (1,620,000)   -> BlueLions (1,935,000)
                                reinforced by: BlueShields (990,000)
```

##### Per-Battle Results

```
  Battle: RedWolves + RedFalcons vs BlueLions (+ BlueShields)
    Outcome: full_success (80%)
    Defender buildings: 3, Theft: 25%
    Splits: RedWolves 60%, RedFalcons 40%
    Transfers:
      RedWolves    +270,000
      RedFalcons   +180,000
      BlueLions    -450,000
      BlueShields        +0
```

The percentage shown after the outcome (e.g. `80%`) is the probability the model assigned to that outcome before rolling.

##### Post-Event Spice

```
  Post-event spice:
    RedWolves      2,420,000
    RedFalcons     1,800,000
    BlueLions      1,485,000
    BlueShields      990,000
```

#### 4. Final Summary

```
Final Results:
  RedWolves      spice=   3,200,000  tier=1
  RedFalcons     spice=   2,100,000  tier=2
  BlueLions      spice=   1,200,000  tier=3
  BlueShields    spice=     800,000  tier=4
```

## JSON Output (--output)

A rich replay log containing all the information shown on stdout in structured form.

```json
{
  "seed": 42,
  "initial_state": {
    "alliances": [ ... ],
    "event_schedule": [ ... ]
  },
  "events": [
    {
      "event_number": 1,
      "attacker_faction": "red",
      "day": "wednesday",
      "days_before": 3,
      "spice_before": {"RedWolves": 2150000, "...": "..."},
      "brackets": {
        "1": {
          "attackers": ["RedWolves", "RedFalcons"],
          "defenders": ["BlueLions", "BlueShields"]
        }
      },
      "targeting": {"RedWolves": "BlueLions", "RedFalcons": "BlueLions"},
      "reinforcements": {"BlueShields": "BlueLions"},
      "battles": [
        {
          "attackers": ["RedWolves", "RedFalcons"],
          "defenders": ["BlueLions"],
          "reinforcements": ["BlueShields"],
          "outcome": "full_success",
          "outcome_probabilities": {
            "full_success": 0.80,
            "partial_success": 0.15,
            "fail": 0.05
          },
          "defender_buildings": 3,
          "theft_percentage": 25,
          "damage_splits": {"RedWolves": 0.6, "RedFalcons": 0.4},
          "transfers": {
            "RedWolves": 270000,
            "RedFalcons": 180000,
            "BlueLions": -450000,
            "BlueShields": 0
          }
        }
      ],
      "spice_after": {"RedWolves": 2420000, "...": "..."}
    }
  ],
  "final_spice": {"RedWolves": 3200000, "...": "..."},
  "rankings": {"RedWolves": 1, "...": "..."}
}
```

## Input Validation

Input files should be validated before simulation is run. Validation errors halt execution with a clear message.

### Required Checks

1. **Both factions present** — the state file must contain at least one alliance per faction referenced in the event schedule.
2. **Non-empty event schedule** — `event_schedule` must contain at least one event.
3. **Cross-file reference check** — if the model config references alliance_ids (in `event_targets`, `event_reinforcements`, `damage_weights`, or `battle_outcome_matrix`) that don't exist in the state file, report an error.
4. **Unknown key detection** — unknown or misspelled keys in either file produce an error. This catches typos like `"starting_spise"` or `"battle_outcom_matrix"`.
5. **Required field presence** — all required alliance and event schedule fields must be present.
