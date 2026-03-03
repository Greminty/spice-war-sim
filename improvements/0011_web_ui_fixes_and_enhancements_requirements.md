# Web UI Fixes & Enhancements — Requirements

## Goal

Fix bugs in the model config form, add input validation with user feedback,
display heuristic probability hints, improve results output tables with
faction/ranking context, add result filtering, and enable sharing via URL.

---

## 1. Fix: Add-Row Button Creates Duplicate Rows

**Problem:**
Clicking any "Add" button on model config tables (default targets, event
targets, event reinforcements, outcome matrix, damage weights) adds more
than one row. The number of duplicate rows grows over time — eventually a
single click adds ~5 rows.

**Expected behavior:**
Each click of an "Add" button should add exactly one row, every time,
regardless of how many times the form has been rebuilt or toggled.

---

## 2. Model Input Validation & Error Display

**Problem:**
Invalid model config entries are silently ignored. For example, entering
a full success probability of 100 with no partial value causes the entry
to be silently discarded. The user gets no indication their input was
dropped.

### 2a. Allow full_success-only outcome rows

A row with only `full_success` filled in (and `partial_success` left blank)
is a valid configuration — these will be auto-derived
by the model. Currently these rows are silently dropped.

- If `full_success` is filled but `partial_success` is blank, include in the model config (with no `partial_success` key)
- Only skip a row if *both* full and partial are blank (truly empty row)

### 2b. Inline validation errors on outcome matrix rows

Show inline error messages on outcome matrix rows for the following
conditions:

| Condition | Error message |
|-----------|---------------|
| `full_success` is filled but not a valid number | "Full % must be a number" |
| `partial_success` is filled but not a valid number | "Partial % must be a number" |
| `custom` is filled but `custom_theft` is blank (or vice versa) | "Custom % and Custom Theft % must both be set" |
| Any percentage value < 0 or > 100 | "Percentages must be between 0 and 100" |
| `full + partial + custom > 100` | (existing) "Probabilities exceed 100%" |

Rows with errors should be visually highlighted.

### 2c. Damage weight validation

| Condition | Error message |
|-----------|---------------|
| Weight is blank or not a number | "Weight must be a number" |
| Weight < 0 or > 1 | "Weight must be between 0 and 1" |

### 2d. Default/event target validation

| Condition | Error message |
|-----------|---------------|
| Duplicate alliance in same table section | "Duplicate alliance — only the last entry will apply" |

---

## 3. Heuristic Probability Hints in Outcome Matrix

**Problem:**
When adding outcome matrix rows, users must guess reasonable probability
values. The engine has built-in heuristic formulas that compute fallback
probabilities based on attacker/defender power ratios, but users have no
visibility into these values.

**Required behavior:**

When an outcome matrix row has specific (non-wildcard) attacker and
defender selections, show the heuristic probability values as placeholder
text in the `full_success` and `partial_success` inputs (e.g. `~55`,
`~25`).

- Placeholders should update dynamically when attacker/defender selection
  changes
- When either attacker or defender is `*` (wildcard), no placeholder is
  shown
- Placeholders are purely informational — they do not affect the generated
  JSON. Only actual input values are used.
- The heuristic values should match the engine's heuristic fallback
  formulas (power-ratio-based, day-dependent)

---

## 4. Fix: Spinner Visible Before First Run

**Problem:**
The run-simulation section shows a spinning loading indicator at all
times, even before any simulation has been run.

**Expected behavior:**
The spinner should only be visible while a simulation is actively running.
It should be hidden on page load and after a run completes.

---

## 5. Enhanced Results Tables

### 5a. Add faction and ranking context to output tables

**Current:** Most results tables only show Alliance ID and numeric values.
Users must cross-reference with the state editor to know factions/rankings.

**New — single run results:**

- **Final Rankings table**: Already has Alliance, Tier, Final Spice. Add
  **Faction** column before Alliance, and exact **Rank** before Tier
- **Spice Before/After table** (per-event detail): Add **Faction** and
  **Before Rank** and **After Rank** columns. Rank columns show the relative
  order of the alliance among all factions total spice, before the spice 
  transfer, and after.
- **Targeting table** (per-event detail): Add **Bracket** column for both
  attacker and defender (showing their ranking group (eg **1-10**) going into that event).
  Format: `Attacker | Attacker Bracket | Defender | Defender Bracket`
- **Battle transfers table**: Add **Faction** column.

**New — Monte Carlo results:**

- **Tier Distribution table**: Add **Faction** column before Alliance.
- **Spice Statistics table**: Add **Faction** column before Alliance.

### 5b. Global results filter by faction top-N

Add a filter control above the results section:

```
Filter: [All] [Top 3 per faction] [Top 5 per faction] [Top 10 per faction]
```

- **All**: Show all alliances (default)
- **Top N per faction**: Only show alliances that are in the top N by power
  within their faction (based on state data)
- Filter applies to **all** results tables (final rankings, per-event
  details, Monte Carlo tier/spice tables)
- The filter persists across re-runs until changed
- Filtered alliances are completely hidden from tables (not greyed out)
- Charts should also respect the filter (only show filtered alliances)

---

## 6. Shareable URL for Run/Model/State Configuration

**Goal:** Allow users to share a specific simulation setup (state + model
config + run parameters) via URL.

### 6a. Encode configuration into URL

The current state JSON, model JSON, and run parameters (seed, MC
iterations, MC base seed) should be serializable into the URL so that
opening the link reproduces the same configuration.

- The payload should be compressed to keep URLs manageable
- Use the URL hash fragment (not query params) to avoid server round-trips

### 6b. Load configuration from URL on page load

On page load, if the URL contains shared configuration data:
- Populate the state editor, model editor, and run parameter inputs
- Trigger validation
- Show a brief notification: "Configuration loaded from shared URL"

### 6c. Share button

Add a "Copy Share Link" button in the run controls section. On click:
- Encode current configuration into the URL
- Copy the full URL to clipboard
- Show brief confirmation: "Link copied to clipboard"

### 6d. Size considerations

- If the payload is too large for a URL, show an error message rather
  than producing a broken link

### 6e. Backwards compatibility

- If the URL hash is empty or invalid, silently ignore it and load defaults
- Use a version prefix so future format changes can be detected

---

## 7. Implementation Priority

Recommended order (bugs first, then enhancements):

1. **Issue 1** — Duplicate rows bug
2. **Issue 4** — Spinner bug
3. **Issue 2** — Input validation
4. **Issue 3** — Heuristic hints
5. **Issue 5** — Enhanced results tables + filtering
6. **Issue 6** — Shareable URLs

---

## 8. Scope

### In scope
- All web UI files (`index.html`, `app.js`, `style.css`)
- Client-side validation logic
- Client-side heuristic hint computation
- Results table enhancements and filtering
- URL-based sharing

### Out of scope
- Changes to the Python backend / `bridge.py` (unless needed to expose
  bracket/ranking data in event history)
- Mobile-specific layouts
- Persisting filter preferences across sessions
- Server-side URL shortening
