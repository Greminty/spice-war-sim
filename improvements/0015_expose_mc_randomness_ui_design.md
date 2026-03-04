# Expose MC Randomness Controls — Design

## Overview

Surface `targeting_temperature`, `power_noise`, and `outcome_noise` in the
web UI form, CSV pipeline, and validation layer. All three already work in
`ConfigurableModel` (0014); this change makes them first-class config fields
instead of requiring raw JSON editing.

---

## 1. Validation — Allow the Three New Keys

### 1a. `src/spice_war/utils/validation.py` — `_ALLOWED_MODEL_KEYS` (line 15)

Add three entries:

```python
_ALLOWED_MODEL_KEYS = {
    "random_seed",
    "battle_outcome_matrix",
    "event_targets",
    "event_reinforcements",
    "damage_weights",
    "targeting_strategy",
    "default_targets",
    "faction_targeting_strategy",
    "targeting_temperature",
    "power_noise",
    "outcome_noise",
}
```

### 1b. `src/spice_war/utils/validation.py` — `_check_model_references()` (after line 336)

Add a numeric-range check for all three fields at the end of the validation
function, before the final `if errors:` block:

```python
# Check MC randomness parameters
for key in ("targeting_temperature", "power_noise", "outcome_noise"):
    val = data.get(key)
    if val is not None:
        if not isinstance(val, (int, float)):
            errors.append(f"'{key}' must be a number, got {type(val).__name__}")
        elif val < 0:
            errors.append(f"'{key}' must be non-negative, got {val}")
```

### 1c. `src/spice_war/web/bridge.py` — `_ALLOWED_MODEL_KEYS` (line 12)

Mirror the same three additions:

```python
_ALLOWED_MODEL_KEYS = {
    "random_seed",
    "battle_outcome_matrix",
    "event_targets",
    "event_reinforcements",
    "damage_weights",
    "targeting_strategy",
    "default_targets",
    "faction_targeting_strategy",
    "targeting_temperature",
    "power_noise",
    "outcome_noise",
}
```

---

## 2. CSV Importer — Parse New Scalar Keys as Floats

**File:** `src/spice_war/sheets/importer.py`

### 2a. Expand `_SCALAR_KEYS` (line 12)

Add a float-scalar set and merge it into the main set:

```python
_FLOAT_SCALAR_KEYS = {"targeting_temperature", "power_noise", "outcome_noise"}
_SCALAR_KEYS = {"random_seed", "targeting_strategy"} | _FLOAT_SCALAR_KEYS
```

### 2b. Add float parsing branch (lines 57–61)

Update the scalar-value dispatch to handle the three float keys:

```python
if cell_a in _SCALAR_KEYS:
    value = _cell(row, 1).strip()
    if value:
        if cell_a == "random_seed":
            result[cell_a] = int(value)
        elif cell_a in _FLOAT_SCALAR_KEYS:
            result[cell_a] = float(value)
        else:
            result[cell_a] = value
    i += 1
    continue
```

---

## 3. CSV Template — Include New Scalar Rows

**File:** `src/spice_war/sheets/template.py` — scalar section (lines 31–34)

Append three rows after the existing scalars, before the blank separator:

```python
# --- Scalars ---
rows.append(["random_seed", "42"])
rows.append(["targeting_strategy", "expected_value"])
rows.append(["targeting_temperature", "0"])
rows.append(["power_noise", "0"])
rows.append(["outcome_noise", "0"])
rows.append([])
```

---

## 4. Web UI — General Settings Form

**File:** `web/js/app.js`

### 4a. `buildGeneralSettings()` (line 222)

Add three number inputs after the Global Targeting Strategy select, inside the
existing `form-grid` div. Each input uses `step="0.05"`, `min="0"`, and
`placeholder="0"`.

```javascript
function buildGeneralSettings() {
    const seed = modelFormData.random_seed ?? "";
    const strategy = modelFormData.targeting_strategy ?? "expected_value";
    const targTemp = modelFormData.targeting_temperature ?? "";
    const powerNoise = modelFormData.power_noise ?? "";
    const outcomeNoise = modelFormData.outcome_noise ?? "";

    return `
    <details class="model-section" open>
        <summary>General Settings</summary>
        <div class="form-grid">
            <label>Random Seed
                <input type="number" id="form-seed" value="${seed}" placeholder="auto"
                       data-field="random_seed">
            </label>
            <label>Global Targeting Strategy
                <select id="form-strategy" data-field="targeting_strategy">
                    <option value="expected_value" ${strategy === "expected_value" ? "selected" : ""}>
                        expected_value</option>
                    <option value="highest_spice" ${strategy === "highest_spice" ? "selected" : ""}>
                        highest_spice</option>
                </select>
            </label>
            <label>Targeting Temperature
                <span class="help-text">0 = deterministic, higher = more random target selection</span>
                <input type="number" id="form-targeting-temp" value="${targTemp}"
                       placeholder="0" min="0" step="0.05"
                       data-field="targeting_temperature">
            </label>
            <label>Power Noise
                <span class="help-text">Per-event power fluctuation range (e.g. 0.1 = \u00b110%)</span>
                <input type="number" id="form-power-noise" value="${powerNoise}"
                       placeholder="0" min="0" step="0.05"
                       data-field="power_noise">
            </label>
            <label>Outcome Noise
                <span class="help-text">Random offset range for battle outcome probabilities</span>
                <input type="number" id="form-outcome-noise" value="${outcomeNoise}"
                       placeholder="0" min="0" step="0.05"
                       data-field="outcome_noise">
            </label>
        </div>
    </details>`;
}
```

The `help-text` span is styled via existing CSS or a small addition:

```css
.help-text {
    font-size: 0.8em;
    opacity: 0.7;
    font-weight: normal;
}
```

### 4b. `collectFormData()` (after line 833)

Add collection logic for the three float fields. Values of 0 or empty are
omitted from the config (matching default-omission convention):

```javascript
// MC randomness parameters
for (const [id, key] of [
    ["form-targeting-temp", "targeting_temperature"],
    ["form-power-noise", "power_noise"],
    ["form-outcome-noise", "outcome_noise"],
]) {
    const val = document.getElementById(id)?.value;
    if (val !== "" && val != null) {
        const num = parseFloat(val);
        if (num > 0) data[key] = num;
    }
}
```

### 4c. Form ↔ JSON sync

No additional changes needed. The existing sync mechanism works automatically:

- **Form → JSON:** `collectFormData()` writes to `modelFormData`, then
  `syncFormToJson()` serializes it as JSON.
- **JSON → Form:** `syncJsonToForm()` parses the JSON textarea into
  `modelFormData`, then calls `buildModelForm()` which calls
  `buildGeneralSettings()`, which reads from `modelFormData`.

---

## Files Changed

| File | Changes |
|------|---------|
| `src/spice_war/utils/validation.py` | Add 3 keys to `_ALLOWED_MODEL_KEYS`; add non-negative number check in `_check_model_references()` |
| `src/spice_war/web/bridge.py` | Add 3 keys to `_ALLOWED_MODEL_KEYS` |
| `src/spice_war/sheets/importer.py` | Add `_FLOAT_SCALAR_KEYS` set; add float parsing branch |
| `src/spice_war/sheets/template.py` | Append 3 scalar rows with default value `"0"` |
| `web/js/app.js` | Add 3 inputs in `buildGeneralSettings()`; collect them in `collectFormData()` |

---

## Implementation Order

| Step | Area | Files | Complexity |
|------|------|-------|------------|
| 1 | Validation | `validation.py`, `bridge.py` | Low |
| 2 | CSV template + import | `template.py`, `importer.py` | Low |
| 3 | Web UI form | `app.js` | Low |
| 4 | Tests | new test cases | Medium |

---

## Testing

### Validation tests

- Config with `targeting_temperature`, `power_noise`, `outcome_noise` set to
  positive floats passes validation
- Config with negative values for any of the three fails validation
- Config with non-numeric values for any of the three fails validation
- Config with unknown keys still fails validation (regression)

### CSV round-trip tests

- Template includes `targeting_temperature`, `power_noise`, `outcome_noise`
  rows with value `"0"`
- Importing a CSV with `targeting_temperature,0.5` produces
  `{"targeting_temperature": 0.5}` (float, not string)
- Round-trip: template → import produces correct float values (0.0) for all
  three keys
- Existing scalar keys (`random_seed`, `targeting_strategy`) still parse
  correctly (regression)

### Web form tests (manual)

- Form displays three new inputs in General Settings section
- Entering non-zero values updates the JSON textarea
- Editing JSON textarea with the three keys updates the form fields
- Clearing inputs or setting them to 0 omits the keys from JSON output
- Running MC with non-zero values produces varied results across iterations
