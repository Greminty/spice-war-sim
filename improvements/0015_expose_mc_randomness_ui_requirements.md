# Expose MC Randomness Controls — Requirements

## Goal

Surface the three 0014 MC randomness parameters (`targeting_temperature`,
`power_noise`, `outcome_noise`) in the web UI, CSV pipeline, and validation
layer. Currently these can only be set via raw JSON editing; they should be
first-class form controls with help text.

---

## 1. Web UI — General Settings Form

### 1a. Add three number inputs to General Settings

Add `targeting_temperature`, `power_noise`, and `outcome_noise` as number
inputs in the General Settings section, below the existing Random Seed and
Global Targeting Strategy fields.

Each input should:
- Accept non-negative decimal values (step 0.05)
- Default to 0 when empty
- Include a brief inline help label

Suggested labels and help text:

| Field | Label | Help text |
|-------|-------|-----------|
| `targeting_temperature` | Targeting Temperature | 0 = deterministic, higher = more random target selection |
| `power_noise` | Power Noise | Per-event power fluctuation range (e.g. 0.1 = ±10%) |
| `outcome_noise` | Outcome Noise | Random offset range for battle outcome probabilities |

### 1b. Form ↔ JSON synchronization

The three new fields must participate in the existing two-way sync between
the form view and the JSON textarea. Values of 0 or empty should be omitted
from the JSON config (matching existing behavior for default values).

---

## 2. Validation

The three new config keys must be accepted as valid model config fields.
Currently a config containing any of them is rejected as unknown. When
present, each value should be a non-negative number.

---

## 3. CSV Import

The CSV importer must recognize `targeting_temperature`, `power_noise`, and
`outcome_noise` as scalar config keys and parse their values as floats.

---

## 4. CSV Template

The CSV template must include the three new keys with their default values
(0), so users can discover and edit them.

---

## 5. Scope

### In scope
- Web UI form controls and form/JSON sync
- Model config validation
- CSV import parsing
- CSV template generation

### Out of scope
- Changes to `ConfigurableModel` or simulation logic (already complete in 0014)
- Changes to MC results display
- Changes to CLI output
- New tests for simulation behavior (covered by 0014 tests)

---

## 6. Testing

### 6a. Validation

- Config containing the three new keys passes validation
- Config with unknown keys still fails validation

### 6b. CSV round-trip

- CSV template includes the three new scalar rows
- CSV import parses them as floats
- Round-trip: template → import produces correct float values in the config

### 6c. Web form (manual)

- Form displays three new inputs in General Settings
- Entering values updates the JSON textarea
- Editing JSON textarea updates the form fields
- Omitting values (empty/0) produces a config without those keys
- Running MC with non-zero values produces varied results across iterations
