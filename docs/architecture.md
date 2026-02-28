# System Architecture

## Overview
This document defines the component structure for the Spice Wars simulation system. The architecture separates pure game mechanics from model-driven decisions, while allowing model components to be invoked mid-simulation with access to current game state.

## Design Principles

1. **No component mixes game mechanics and model logic**: Each component is clearly one or the other
2. **Game mechanics components can call model components**: At decision points, mechanics invoke model components and pass current state
3. **Model components are pluggable**: Can be swapped, configured, or overridden
4. **Model decisions can be state-dependent**: Models receive current game state, allowing decisions like "try harder if rank is at stake"
5. **Testability**: Game mechanics testable with mock model components; model components testable with synthetic state

## Interaction Pattern

```
Game Mechanics Component              Model Component
        │                                    │
        │  "I need a decision"               │
        │  (here's the current state)        │
        ├───────────────────────────────────→│
        │                                    │  considers state,
        │                                    │  config, heuristics
        │         decision result            │
        │←───────────────────────────────────┤
        │                                    │
        │  applies decision using            │
        │  game mechanics rules              │
        │                                    │
```

**Key insight**: The simulation doesn't require all decisions upfront. Model decisions are made just-in-time, with full visibility into how the war is going.

## Game Mechanics Components

These implement core game rules. They contain NO model logic, but they DO call model components at decision points.

### 1. Building Count Calculator
**Purpose**: Determine number of side buildings based on spice amount

**Input**: `spice_amount` (number)
**Output**: `building_count` (0-4)

**Logic**: Uses thresholds from game_mechanics.md
- 0 buildings: < 150k
- 1 building: 150k - 705k
- 2 buildings: 705k - 1,805k
- 3 buildings: 1,805k - 3,165k
- 4 buildings: ≥ 3,165k

### 2. Theft Percentage Mapper
**Purpose**: Convert outcome level to actual theft percentage

**Input**: `outcome_level`, `building_count`
**Output**: `theft_percentage` (0-30)

**Logic**:
- full_success: (building_count × 5%) + 10% (center)
- partial_success: (building_count × 5%)
- fail: 0%

### 3. Bracket Assigner
**Purpose**: Assign alliances to brackets based on spice rankings within faction

**Input**: `alliances` (with current spice), `faction`
**Output**: `brackets` (dict: alliance_id → bracket_number)

**Logic**: Sort by spice descending, bracket = (rank - 1) // 10 + 1

### 4. Final Ranking Calculator
**Purpose**: Determine final success tier

**Input**: `alliances` (with final spice)
**Output**: `rankings` (dict: alliance_id → tier 1-5)

**Logic**: Rank 1→Tier 1, 2-3→Tier 2, 4-10→Tier 3, 11-20→Tier 4, 21+→Tier 5

### 5. Single Battle Resolver
**Purpose**: Resolve one battle and calculate spice transfers

**Input**:
- `attackers` (list of alliance_ids)
- `defenders` (list of alliance_ids, primary defender first)
- `outcome_level` ("full_success", "partial_success", or "fail")
- `damage_splits` (dict: attacker_id → fraction, sum = 1.0)
- `current_spice` (dict: alliance_id → spice)

**Output**: `spice_transfers` (dict: alliance_id → spice change)

**Logic**:
1. Get building count for primary defender (calls Building Count Calculator)
2. Map outcome_level + building_count → theft_percentage (calls Theft Percentage Mapper)
3. Calculate total_stolen = primary_defender_spice × theft_percentage
4. Distribute among attackers using damage_splits
5. Return transfers

### 6. Battle Coordinator
**Purpose**: Orchestrate a single battle by gathering model decisions and invoking resolution

**Calls model components for**:
- Battle outcome
- Damage splits (if multiple attackers)

**Input**:
- `attackers` (list of alliance_ids)
- `defenders` (list of alliance_ids, primary defender first)
- `current_state` (all alliance data, spice totals, event history)
- `day` ("wednesday" or "saturday")
- `model` (model component interface)

**Output**: `spice_transfers` (dict: alliance_id → spice change)

**Logic**:
1. Ask model: determine battle outcome (passing attackers, defenders, current state, day)
2. Ask model: determine damage splits (passing attackers, current state)
3. Call Single Battle Resolver with outcome + splits
4. Return spice transfers

### 7. Event Coordinator
**Purpose**: Resolve all battles in one event

**Calls model components for**:
- Targeting decisions (per bracket)
- Reinforcement assignments (per bracket)

**Input**:
- `current_state` (all alliance data, spice totals, brackets)
- `attacker_faction` (1 or 2)
- `day` ("wednesday" or "saturday")
- `model` (model component interface)

**Output**: `updated_spice` (dict: alliance_id → new spice)

**Logic**:
1. Determine brackets (call Bracket Assigner for each faction)
2. For each bracket:
   a. Get attackers and defenders in this bracket
   b. Ask model: generate targets for this bracket (passing bracket alliances, current state)
   c. Ask model: generate reinforcements for this bracket (passing bracket alliances, targets, current state)
   d. Group battles (attackers targeting same defender)
   e. For each battle: call Battle Coordinator (passing attackers, defenders, state, day, model)
3. Aggregate all spice transfers across all brackets
4. Apply to current_spice and return

### 8. Between-Event Processor
**Purpose**: Apply passive spice generation and update brackets

**Input**:
- `current_spice` (dict)
- `days_elapsed` (number)
- `daily_rates` (dict: alliance_id → rate)

**Output**:
- `updated_spice` (dict)
- `new_brackets` (dict)

**Logic**:
1. For each alliance: spice += daily_rate × days_elapsed
2. Call Bracket Assigner for each faction

### 9. War Simulator
**Purpose**: Run complete 4-week simulation

**Input**:
- `alliances` (list: initial alliance data)
- `event_schedule` (list: which faction attacks each event)
- `model` (model component interface)

**Output**:
- `final_state`:
  - `final_spice`: per alliance
  - `rankings`: tier assignments
  - `event_history`: spice totals after each event

**Logic**:
1. Initialize spice from starting values
2. For each event (1-8):
   a. Call Event Coordinator (passing current state + model)
   b. Call Between-Event Processor
   c. Record state in history
3. Call Final Ranking Calculator
4. Return final state

## Simulation Data Structures

### Alliance Configuration

Each alliance requires:

```json
{
  "alliance_id": "alliance_A",
  "name": "Alliance Alpha",
  "server": "server_1",
  "faction": 1,
  "power": 1000000,
  "gift_level": 50000,
  "starting_spice": 200000,
  "daily_spice_rate": 50000,
  "damage_weight": 1.0
}
```

**Required fields (used by game mechanics):**
- `alliance_id` (string): Unique identifier
- `faction` (1 or 2): Which faction the alliance belongs to
- `starting_spice` (number): Initial spice at event start
- `daily_spice_rate` (number): Passive spice generation per day

**Optional fields (used by model components):**
- `name` (string): Human-readable name
- `server` (string): Server identifier
- `power` (number): Alliance strength
- `gift_level` (number): Spending indicator
- `damage_weight` (number): Relative damage contribution weight

### Event Schedule

Defines which faction attacks on each of the 8 battle events:

```json
{
  "events": [
    {"event_id": 1, "day": "wednesday", "week": 1, "attacker_faction": 1},
    {"event_id": 2, "day": "saturday", "week": 1, "attacker_faction": 2}
  ]
}
```

**Required fields per event:**
- `event_id` (number): 1-8
- `attacker_faction` (1 or 2): Which faction attacks

**Optional fields:**
- `day` (string): "wednesday" or "saturday"
- `week` (number): 1-4

### Game State (Passed to Model)

The model receives current game state at each decision point:

```json
{
  "current_spice": {"alliance_A": 350000, "alliance_B": 280000},
  "brackets": {"alliance_A": 1, "alliance_B": 1},
  "event_number": 5,
  "day": "wednesday",
  "event_history": [
    {"event_id": 1, "spice_after": {}},
    {"event_id": 2, "spice_after": {}}
  ],
  "alliances": []
}
```

This allows models to make state-dependent decisions (e.g., adjust strategy based on current rankings).

## Model Components

These make modeling decisions. They receive current game state and return decisions. They contain NO game mechanics logic.

### Model Construction and Config

The model is instantiated once with user configuration, then passed to the War Simulator:

```python
config = {
    "battle_outcome_matrix": { ... },       # See M3 below
    "event_targets": { ... },               # See M1 below
    "event_reinforcements": { ... },        # See M2 below
    "random_seed": 42                       # For reproducible outcomes
}

model = ConfigurableModel(config, alliances)
simulator = WarSimulator(alliances, event_schedule, model)
```

**Config sources:**
- `battle_outcome_matrix`: User provides probabilities for attacker-defender pairings
- `event_targets`: User provides explicit targeting for specific events (optional)
- `event_reinforcements`: User provides explicit reinforcements for specific events (optional)
- `random_seed`: Controls randomness in outcome rolling
- `alliances`: Alliance data including `power`, `gift_level`, `damage_weight` (used for fallback heuristics)

### M1. Targeting Generator

**Purpose**: Decide which attackers target which defenders within a bracket

**Receives at call time (from Event Coordinator):**
- `state`: Current game state (spice totals, event history, event_number)
- `bracket_attackers`: List of attacking alliances in this bracket
- `bracket_defenders`: List of defending alliances in this bracket
- `bracket_number`: Which bracket (1, 2, 3, etc.)

**Has from construction:**
- `config.event_targets`: User-configured targets per event (optional)

**Returns:**
- `targets` (dict): attacker_id → defender_id

**Logic:**
1. Check if `config.event_targets[current_event_number]` exists for this bracket
   - If yes: use user-configured targets (filtered to this bracket)
   - If no: apply default power-based targeting rule
2. **Default rule (1:1, spice-based)**:
   a. Sort bracket_attackers by power (descending)
   b. Sort bracket_defenders by current spice (descending)
   c. For each attacker (highest power first):
      - Target highest-spice defender with no attackers yet assigned
3. Return targets dict

**User config format for event_targets:**
```json
{
  "event_targets": {
    "1": {
      "alliance_A": "alliance_X",
      "alliance_B": "alliance_X",
      "alliance_C": "alliance_Y"
    },
    "5": {
      "alliance_A": "alliance_Z"
    }
  }
}
```

**Notes:**
- Config is optional per event - unconfigured events use default rule
- Config can be partial within an event - unconfigured attackers in a configured event could use default rule (or require all-or-nothing - decision TBD)

### M2. Reinforcement Generator

**Purpose**: Decide which un-targeted defenders reinforce which battles

**Receives at call time (from Event Coordinator):**
- `state`: Current game state
- `targets`: The targeting decisions just made for this bracket (from M1)
- `bracket_defenders`: All defending alliances in this bracket
- `bracket_number`: Which bracket

**Has from construction:**
- `config.event_reinforcements`: User-configured reinforcements per event (optional)

**Returns:**
- `reinforcements` (dict): un-targeted defender_id → defender_id of battle to reinforce

**Logic:**
1. Determine which defenders are un-targeted (not in `targets.values()`)
2. Check if `config.event_reinforcements[current_event_number]` exists
   - If yes: use user-configured reinforcements
   - If no: apply default reinforcement rule
3. **Default rule (most-attacked)**:
   a. Count how many attackers each defender has
   b. Assign each un-targeted defender to the most-attacked battle
   c. Ties broken by highest spice (reinforce the richest target)
   d. Respect max reinforcement limit (num_attackers - 1 per battle)
4. Return reinforcements dict

**User config format for event_reinforcements:**
```json
{
  "event_reinforcements": {
    "1": {
      "alliance_Z": "alliance_X"
    }
  }
}
```

### M3. Battle Outcome Generator

**Purpose**: Determine the outcome level for a single battle

**Receives at call time (from Battle Coordinator):**
- `state`: Current game state (spice totals, event history, rankings)
- `attackers`: List of attacking alliance data (id, power, gift_level, etc.)
- `defenders`: List of defending alliance data (primary defender first)
- `day`: "wednesday" or "saturday"

**Has from construction:**
- `config.battle_outcome_matrix`: User-configured probabilities per pairing
- `config.random_seed`: For reproducible random rolling
- `alliances`: Alliance power/gift_level data (for fallback heuristic)

**Returns:**
- `outcome_level` (string): "full_success", "partial_success", or "fail"

**Logic:**
1. **Look up probabilities for each attacker-defender pairing**:
   - For each attacker, check `config.battle_outcome_matrix[day][attacker_id][primary_defender_id]`
   - If found with both values: use configured `{full_success: prob, partial_success: prob}`
   - If found with only `full_success`: derive `partial_success = (1 - full_success) * 0.4`
   - If not found: use power-based heuristic fallback (see [model_generation.md](model_generation.md))

2. **Combine probabilities for multiple attackers** (if > 1 attacker):
   - Average the `full_success` probabilities across all attackers
   - Average the `partial_success` probabilities across all attackers

3. **Roll outcome**:
   - Generate random number [0, 1)
   - If < full_success_prob → "full_success"
   - Else if < full_success_prob + partial_success_prob → "partial_success"
   - Else → "fail"

4. Return outcome_level

**Notes:**
- fail probability is always implicit (1 - full - partial)
- Random seed ensures reproducibility across runs with same config
- See [model_generation.md](model_generation.md) for config format, heuristic formulas, and reference tables

### M4. Damage Split Generator

**Purpose**: Determine how stolen spice is split among multiple attackers

**Receives at call time (from Battle Coordinator):**
- `state`: Current game state
- `attackers`: List of attacking alliance data

**Has from construction:**
- `alliances`: Alliance data including `damage_weight` (optional per alliance)

**Returns:**
- `splits` (dict): attacker_id → fraction (sum = 1.0)

**Logic:**
1. Check if ALL attackers in this battle have `damage_weight` configured
   - If yes: use `damage_weight` for each attacker
   - If no: use power-based heuristic fallback (see [model_generation.md](model_generation.md))
2. Calculate total_weight = sum of all attacker weights
3. Return `{attacker_id: weight / total_weight}` for each attacker

**Notes:**
- For single-attacker battles, this is trivially `{attacker_id: 1.0}`
- The Battle Coordinator can skip calling this for single-attacker battles
- Weights and power are never mixed — it's all-or-nothing on user-supplied weights
- See [model_generation.md](model_generation.md) for heuristic formula and reference tables

### Model Implementations

#### ConfigurableModel (Phase 1)
Implements M1-M4 as described above:
- Constructed with user config + alliance data
- Each method checks user config first, falls back to heuristic
- Uses random seed for reproducible outcome rolling

#### StateDependentModel (Phase 2+)
Extends ConfigurableModel with state-aware adjustments:
- Adjust battle outcome probabilities based on how close an alliance is to a tier boundary
- Vary targeting strategy based on current rankings
- Factor in whether an alliance has been losing and might "try harder"
- Could modify heuristic multipliers based on event history

## Data Flow

```
                     ┌──────────────────┐
                     │  User Config /   │
                     │  Model Settings  │
                     └────────┬─────────┘
                              │
                     ┌────────▼─────────┐
                     │   BattleModel    │
                     │  (pluggable)     │
                     └────────┬─────────┘
                              │ called by mechanics
                              │ at decision points
┌─────────────────────────────┼──────────────────────┐
│ War Simulator (9)           │                      │
│  │                          │                      │
│  ├─→ Event Coordinator (7) ←┘                      │
│  │    │  asks model for: targets, reinforcements   │
│  │    │                                            │
│  │    └─→ Battle Coordinator (6)                   │
│  │         │  asks model for: outcome, splits      │
│  │         │                                       │
│  │         └─→ Single Battle Resolver (5)          │
│  │              ├─→ Building Count Calculator (1)  │
│  │              └─→ Theft Percentage Mapper (2)    │
│  │                                                 │
│  ├─→ Between-Event Processor (8)                   │
│  │    └─→ Bracket Assigner (3)                     │
│  │                                                 │
│  └─→ Final Ranking Calculator (4)                  │
│                                                    │
│           Game Mechanics Layer                     │
└────────────────────────────────────────────────────┘
```

## Module Organization

```
src/
├── game/
│   ├── mechanics.py      # Components 1-4: Pure calculations
│   ├── battle.py         # Component 5: Single battle resolution
│   ├── events.py         # Components 6-7: Event coordination
│   └── simulator.py      # Component 8: War simulator
├── models/
│   ├── base.py           # BattleModel interface
│   ├── configurable.py   # ConfigurableModel (Phase 1)
│   └── state_aware.py    # StateDependentModel (Phase 2+)
└── utils/
    └── data_storage.py   # JSON I/O
```

## Testing Strategy

**Game mechanics**: Test with mock model that returns predetermined values
- Verify mechanics apply correctly regardless of what model decides
- Example: "Given model returns full_success, verify correct spice transfer"

**Model components**: Test with synthetic game state
- Verify model makes expected decisions given specific state
- Example: "Given alliance is near tier boundary, verify higher aggression"

**Integration**: Test full simulation with known model + known initial state
- Verify end-to-end results match expectations

## Next Steps

1. Define BattleModel interface in Python
2. Implement game mechanics components (1-5)
3. Implement event coordination (6-7) with model callbacks
4. Implement war simulator (8)
5. Implement ConfigurableModel (Phase 1 model)
6. Integration testing with example scenario