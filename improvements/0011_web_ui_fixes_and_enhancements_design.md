# Web UI Fixes & Enhancements — Design

## Overview

Six changes to the Spice War web UI, implemented entirely in `web/js/app.js`, `web/css/style.css`, and `web/index.html`. Two are bug fixes (duplicate add-row, spinner visible before first run), two are form enhancements (input validation with error display, heuristic probability placeholders), and two are results/sharing enhancements (enriched tables with faction/rank/bracket columns plus top-N filtering, and URL-based config sharing via compressed hash fragment). One Python change is needed: `bridge.py` must expose per-alliance bracket assignments in the event history so the frontend can display bracket columns in results tables. No other backend changes are required.

---

## 1. Fix: Duplicate Add-Row Bug

### Root cause

`attachFormHandlers()` is called every time `buildModelForm()` runs. It calls `form.addEventListener(...)` on `#model-form`, stacking duplicate listeners. After N rebuilds, a single click dispatches N `handleAddRow()` calls.

Rebuilds happen on: state change (re-validation), JSON-to-form toggle, file upload, CSV import. Each adds another layer of listeners.

### Fix

Guard `attachFormHandlers()` so it only attaches once. Use a module-level flag.

```javascript
let formHandlersAttached = false;

function attachFormHandlers() {
    if (formHandlersAttached) return;
    formHandlersAttached = true;

    const form = document.getElementById("model-form");

    form.addEventListener("input", () => {
        collectFormData();
        scheduleModelValidation();
    });

    form.addEventListener("change", (e) => {
        if (e.target.classList.contains("dt-type")) {
            const row = e.target.closest("tr");
            row.querySelector(".dt-pin-value").classList.toggle("hidden", e.target.value !== "pin");
            row.querySelector(".dt-strategy-value").classList.toggle("hidden", e.target.value === "pin");
        }
        collectFormData();
        scheduleModelValidation();
    });

    form.addEventListener("click", (e) => {
        if (e.target.classList.contains("remove-row-btn")) {
            e.target.closest("tr").remove();
            collectFormData();
            scheduleModelValidation();
        }

        if (e.target.classList.contains("add-row-btn")) {
            handleAddRow(e.target);
        }
    });
}
```

This works because the listeners use event delegation — they listen on the parent `#model-form` element, which persists across rebuilds (only its `innerHTML` changes). The delegated handlers correctly match new DOM elements via class checks.

---

## 2. Fix: Spinner Visible Before First Run

### Root cause

The `#run-spinner` element has the `hidden` class in HTML and starts invisible. However, there is a CSS specificity issue: the `.spinner` class in `style.css` sets `display: inline-block`, which can override the `.hidden` class if `.hidden` uses `display: none` with lower specificity.

### Fix

Ensure `.hidden` always wins. Add `!important` to the hidden class, or use a more specific selector.

```css
.hidden {
    display: none !important;
}
```

If `.hidden` already has `!important`, the real issue may be that `setRunning(false)` is never called on initialization (only on run completion). Verify that the initial state is correct by checking that the `hidden` class is present and not removed by any initialization code. The HTML already has `class="spinner hidden"` on `#run-spinner`, so the CSS fix is sufficient.

---

## 3. Model Input Validation & Error Display

### 3a. Allow full_success-only outcome rows

Currently `collectFormData()` skips rows where `isNaN(full) || isNaN(partial)`. Change the condition to only skip rows where both are blank (truly empty).

```javascript
// In collectFormData(), battle outcome matrix section:
const fullVal = row.querySelector(".bom-full").value;
const partialVal = row.querySelector(".bom-partial").value;
const full = parseFloat(fullVal);
const partial = parseFloat(partialVal);
const customVal = row.querySelector(".bom-custom").value;
const customTheftVal = row.querySelector(".bom-custom-theft").value;

// Only skip if both full and partial are blank (truly empty row)
if (fullVal === "" && partialVal === "") continue;

const probs = {};
if (!isNaN(full)) {
    probs.full_success = full / 100;
}
if (!isNaN(partial)) {
    probs.partial_success = partial / 100;
}
if (customVal !== "" && !isNaN(parseFloat(customVal))) {
    probs.custom = parseFloat(customVal) / 100;
}
if (customTheftVal !== "" && !isNaN(parseFloat(customTheftVal))) {
    probs.custom_theft_percentage = parseFloat(customTheftVal);
}
```

### 3b. Inline validation errors on outcome matrix rows

Add a `validateOutcomeRowFull()` function that returns an array of error messages for a single row. Errors are displayed in a `<div class="row-errors">` appended inside the row's last `<td>` (or in a spanning cell below).

```javascript
function validateOutcomeRowFull(row) {
    const errors = [];
    const fullVal = row.querySelector(".bom-full").value;
    const partialVal = row.querySelector(".bom-partial").value;
    const customVal = row.querySelector(".bom-custom").value;
    const customTheftVal = row.querySelector(".bom-custom-theft").value;

    const full = parseFloat(fullVal);
    const partial = parseFloat(partialVal);
    const custom = parseFloat(customVal);
    const customTheft = parseFloat(customTheftVal);

    // Type checks (only if filled)
    if (fullVal !== "" && isNaN(full)) {
        errors.push("Full % must be a number");
    }
    if (partialVal !== "" && isNaN(partial)) {
        errors.push("Partial % must be a number");
    }

    // Range checks (only if valid number)
    const pctFields = [
        [fullVal, full, "Full %"],
        [partialVal, partial, "Partial %"],
        [customVal, custom, "Custom %"],
        [customTheftVal, customTheft, "Custom Theft %"],
    ];
    for (const [raw, num, label] of pctFields) {
        if (raw !== "" && !isNaN(num) && (num < 0 || num > 100)) {
            errors.push("Percentages must be between 0 and 100");
            break;  // One message covers all range violations
        }
    }

    // Custom/custom_theft pairing
    const hasCustom = customVal !== "" && !isNaN(custom);
    const hasCustomTheft = customTheftVal !== "" && !isNaN(customTheft);
    if (hasCustom !== hasCustomTheft) {
        errors.push("Custom % and Custom Theft % must both be set");
    }

    // Sum check
    const fVal = (!isNaN(full) && fullVal !== "") ? full : 0;
    const pVal = (!isNaN(partial) && partialVal !== "") ? partial : 0;
    const cVal = (!isNaN(custom) && customVal !== "") ? custom : 0;
    if (fVal + pVal + cVal > 100) {
        errors.push(`Probabilities exceed 100%`);
    }

    return errors;
}
```

Call this from `collectFormData()` and display errors. Each outcome matrix row gets a `<td>` for errors at the end.

#### Updated outcome row HTML

Add an error column to the outcome table header and each row:

```javascript
// In buildOutcomeMatrix() table header:
<tr>
    <th>Attacker</th><th>Defender</th>
    <th>Full %</th><th>Partial %</th>
    <th>Custom %</th><th>Custom Theft %</th><th></th><th></th>
</tr>

// In each row (builder and handleAddRow), append:
<td class="row-error-cell"></td>
```

#### Displaying errors in collectFormData()

After collecting all outcome matrix rows, run validation and update error display:

```javascript
// After processing each outcome row in collectFormData():
const rowErrors = validateOutcomeRowFull(row);
const errorCell = row.querySelector(".row-error-cell");
if (rowErrors.length > 0) {
    row.classList.add("validation-error");
    errorCell.innerHTML = rowErrors.map(e => `<div class="row-error-msg">${esc(e)}</div>`).join("");
} else {
    row.classList.remove("validation-error");
    errorCell.innerHTML = "";
}
```

### 3c. Damage weight validation

Similar per-row validation in `collectFormData()` for the damage weights section.

```javascript
function validateDamageWeightRow(row) {
    const errors = [];
    const weightVal = row.querySelector(".dw-weight").value;
    const weight = parseFloat(weightVal);

    if (weightVal === "" || isNaN(weight)) {
        errors.push("Weight must be a number");
    } else if (weight < 0 || weight > 1) {
        errors.push("Weight must be between 0 and 1");
    }

    return errors;
}
```

Add an error cell to each damage weight row, same pattern as outcome matrix. The damage weight table header and row builders are updated to include a `<td class="row-error-cell"></td>` column.

### 3d. Default/event target duplicate detection

After collecting default target rows, check for duplicate alliance IDs:

```javascript
// In collectFormData(), after building the dt object:
const dtSeen = new Set();
for (const row of dtRows) {
    const aid = row.querySelector(".dt-alliance").value;
    const errorCell = row.querySelector(".row-error-cell");
    if (dtSeen.has(aid)) {
        row.classList.add("validation-error");
        if (errorCell) errorCell.textContent = "Duplicate alliance — only the last entry will apply";
    } else {
        row.classList.remove("validation-error");
        if (errorCell) errorCell.textContent = "";
    }
    dtSeen.add(aid);
}
```

Same logic for each event target subsection.

### CSS for row errors

```css
.row-error-cell {
    min-width: 140px;
    vertical-align: top;
}

.row-error-msg {
    color: #dc3545;
    font-size: 0.8em;
    line-height: 1.3;
    white-space: nowrap;
}

.validation-error {
    background: #fff3f3;
}

.validation-error input,
.validation-error select {
    border-color: #dc3545;
}
```

---

## 4. Heuristic Probability Hints in Outcome Matrix

### Approach

When an outcome matrix row has specific (non-wildcard) attacker and defender selections, compute the heuristic probability values from the engine's formula and show them as `placeholder` text in the `full_success` and `partial_success` inputs.

### Power lookup

Build a power map from `currentStateDict`:

```javascript
function getAlliancePower() {
    if (!currentStateDict) return {};
    const power = {};
    for (const a of currentStateDict.alliances) {
        power[a.alliance_id] = a.power;
    }
    return power;
}
```

### Heuristic formula (port from Python)

Port the exact formula from `configurable.py:_heuristic_probabilities`:

```javascript
function computeHeuristicHints(attackerId, defenderId, day) {
    const power = getAlliancePower();
    const aPower = power[attackerId];
    const dPower = power[defenderId];
    if (!aPower || !dPower) return null;

    const ratio = aPower / dPower;
    let full, cumulativePartial;

    if (day === "wednesday") {
        full = Math.max(0, Math.min(1, 2.5 * ratio - 2.0));
        cumulativePartial = Math.max(0, Math.min(1, 1.75 * ratio - 0.9));
    } else {
        full = Math.max(0, Math.min(1, 3.25 * ratio - 3.0));
        cumulativePartial = Math.max(0, Math.min(1, 1.75 * ratio - 1.1));
    }

    const partial = Math.max(0, cumulativePartial - full);
    return {
        full: Math.round(full * 100),
        partial: Math.round(partial * 100),
    };
}
```

### Updating placeholders

After any change to attacker/defender dropdowns in an outcome matrix row, update the placeholder text:

```javascript
function updateHeuristicPlaceholders(row, day) {
    const attacker = row.querySelector(".bom-attacker").value;
    const defender = row.querySelector(".bom-defender").value;
    const fullInput = row.querySelector(".bom-full");
    const partialInput = row.querySelector(".bom-partial");

    if (attacker === "*" || defender === "*") {
        fullInput.placeholder = "";
        partialInput.placeholder = "";
        return;
    }

    const hints = computeHeuristicHints(attacker, defender, day);
    if (hints) {
        fullInput.placeholder = `~${hints.full}`;
        partialInput.placeholder = `~${hints.partial}`;
    } else {
        fullInput.placeholder = "";
        partialInput.placeholder = "";
    }
}
```

### Integration points

1. **On form build** — After `buildOutcomeMatrix()` populates the DOM, iterate over all outcome rows and call `updateHeuristicPlaceholders()`.

2. **On dropdown change** — In `attachFormHandlers()`, the existing `change` listener checks for `bom-attacker` or `bom-defender` class changes and calls `updateHeuristicPlaceholders()` on the changed row.

```javascript
// In the existing change handler, add:
if (e.target.classList.contains("bom-attacker") || e.target.classList.contains("bom-defender")) {
    const row = e.target.closest("tr");
    const day = row.dataset.day || row.closest(".day-subsection")?.dataset.day;
    if (day) updateHeuristicPlaceholders(row, day);
}
```

3. **On add-row** — After inserting a new outcome row in `handleAddRow()`, call `updateHeuristicPlaceholders()` on the new row.

### Post-build placeholder initialization

After `buildModelForm()` sets `container.innerHTML`, walk all existing outcome rows and set placeholders:

```javascript
function initHeuristicPlaceholders() {
    const daySections = document.querySelectorAll(".day-subsection");
    for (const section of daySections) {
        const day = section.dataset.day;
        const rows = section.querySelectorAll(".dynamic-row");
        for (const row of rows) {
            updateHeuristicPlaceholders(row, day);
        }
    }
}
```

Call `initHeuristicPlaceholders()` at the end of `buildModelForm()`, after `attachFormHandlers()`.

### Placeholder styling

Placeholders already render in a lighter color by browser default, which provides sufficient visual distinction. No additional CSS needed.

---

## 5. Enhanced Results Tables

### 5a. Faction and ranking context

All results rendering functions need access to faction information. Build a lookup from `currentStateDict`:

```javascript
function getAllianceFaction() {
    if (!currentStateDict) return {};
    const factions = {};
    for (const a of currentStateDict.alliances) {
        factions[a.alliance_id] = a.faction;
    }
    return factions;
}
```

#### Rank computation helper

Compute ordinal rank from a spice map (position 1 = highest spice):

```javascript
function computeRanks(spiceMap) {
    const sorted = Object.entries(spiceMap)
        .sort((a, b) => b[1] - a[1]);
    const ranks = {};
    for (let i = 0; i < sorted.length; i++) {
        ranks[sorted[i][0]] = i + 1;
    }
    return ranks;
}
```

#### Bracket lookup helper

Derive per-alliance bracket from the event's `brackets` object (which maps bracket number to `{attackers, defenders}`):

```javascript
function getAllianceBracket(eventBrackets) {
    const bracketMap = {};
    for (const [bracketNum, group] of Object.entries(eventBrackets)) {
        const num = parseInt(bracketNum, 10);
        const label = `${(num - 1) * 10 + 1}-${num * 10}`;
        for (const aid of group.attackers) {
            bracketMap[aid] = label;
        }
        for (const aid of group.defenders) {
            bracketMap[aid] = label;
        }
    }
    return bracketMap;
}
```

#### Single run — Final Rankings table

Add **Faction** before Alliance and **Rank** before Tier:

```javascript
function renderSingleResults(result) {
    const factions = getAllianceFaction();
    // ... existing sort logic ...

    let html = `<h3>Final Rankings (seed: ${result.seed})</h3>`;
    html += "<table><tr><th>Rank</th><th>Faction</th><th>Alliance</th><th>Tier</th><th>Final Spice</th></tr>";
    for (let i = 0; i < entries.length; i++) {
        const e = entries[i];
        html += `<tr>
            <td>${i + 1}</td>
            <td>${esc(factions[e.id] || "")}</td>
            <td>${esc(e.id)}</td>
            <td>${e.tier}</td>
            <td>${e.spice.toLocaleString()}</td>
        </tr>`;
    }
    html += "</table>";
    // ...
}
```

#### Single run — Spice Before/After table

Add **Faction**, **Before Rank**, and **After Rank** columns:

```javascript
function renderEventDetail(event) {
    const factions = getAllianceFaction();
    const beforeRanks = computeRanks(event.spice_before);
    const afterRanks = computeRanks(event.spice_after);

    let html = "<h4>Spice</h4><table>";
    html += "<tr><th>Faction</th><th>Alliance</th><th>Before Rank</th><th>Before</th>"
          + "<th>After</th><th>After Rank</th><th>Change</th></tr>";
    for (const [id, before] of Object.entries(event.spice_before)) {
        const after = event.spice_after[id];
        const change = after - before;
        const sign = change >= 0 ? "+" : "";
        html += `<tr>
            <td>${esc(factions[id] || "")}</td>
            <td>${esc(id)}</td>
            <td>${beforeRanks[id]}</td>
            <td>${before.toLocaleString()}</td>
            <td>${after.toLocaleString()}</td>
            <td>${afterRanks[id]}</td>
            <td>${sign}${change.toLocaleString()}</td>
        </tr>`;
    }
    html += "</table>";
    // ...
}
```

#### Single run — Targeting table

Add **Attacker Bracket** and **Defender Bracket** columns. The bracket data comes from `event.brackets`.

```javascript
// In renderEventDetail(), targeting section:
const bracketMap = getAllianceBracket(event.brackets);

html += "<h4>Targeting</h4><table>";
html += "<tr><th>Attacker</th><th>Attacker Bracket</th><th>Defender</th><th>Defender Bracket</th></tr>";
for (const [att, def_] of Object.entries(event.targeting)) {
    html += `<tr>
        <td>${esc(att)}</td>
        <td>${bracketMap[att] || "—"}</td>
        <td>${esc(def_)}</td>
        <td>${bracketMap[def_] || "—"}</td>
    </tr>`;
}
html += "</table>";
```

#### Single run — Battle transfers table

Add **Faction** column:

```javascript
// In renderEventDetail(), battle transfers section:
if (Object.keys(battle.transfers).length > 0) {
    html += "<table><tr><th>Faction</th><th>Alliance</th><th>Transfer</th></tr>";
    for (const [id, amount] of Object.entries(battle.transfers)) {
        const sign = amount >= 0 ? "+" : "";
        html += `<tr>
            <td>${esc(factions[id] || "")}</td>
            <td>${esc(id)}</td>
            <td>${sign}${amount.toLocaleString()}</td>
        </tr>`;
    }
    html += "</table>";
}
```

#### Monte Carlo — Tier Distribution table

Add **Faction** column before Alliance:

```javascript
// In renderMonteCarloResults():
const factions = getAllianceFaction();

html += "<table><tr><th>Faction</th><th>Alliance</th>";
for (let t = 1; t <= 5; t++) html += `<th>T${t}</th>`;
html += "</tr>";
for (const aid of aids) {
    html += `<tr><td>${esc(factions[aid] || "")}</td><td>${esc(aid)}</td>`;
    // ... tier columns unchanged ...
}
```

#### Monte Carlo — Spice Statistics table

Add **Faction** column before Alliance:

```javascript
html += "<table><tr><th>Faction</th><th>Alliance</th><th>Mean</th><th>Median</th>";
html += "<th>Min</th><th>Max</th><th>P25</th><th>P75</th></tr>";
for (const aid of aids) {
    const s = result.spice_stats[aid];
    html += `<tr>
        <td>${esc(factions[aid] || "")}</td>
        <td>${esc(aid)}</td>
        // ... stats columns unchanged ...
    </tr>`;
}
```

### 5b. Global results filter by faction top-N

#### Filter state

New module-level variable:

```javascript
let resultFilter = "all";  // "all" | "top3" | "top5" | "top10"
```

#### Computing filtered alliance set

Build a set of alliance IDs that pass the filter:

```javascript
function getFilteredAlliances(filter) {
    if (filter === "all" || !currentStateDict) return null;  // null means "show all"

    const n = parseInt(filter.replace("top", ""), 10);
    const byFaction = {};
    for (const a of currentStateDict.alliances) {
        if (!byFaction[a.faction]) byFaction[a.faction] = [];
        byFaction[a.faction].push(a);
    }

    const allowed = new Set();
    for (const faction of Object.keys(byFaction)) {
        const sorted = byFaction[faction].sort((a, b) => b.power - a.power);
        for (let i = 0; i < Math.min(n, sorted.length); i++) {
            allowed.add(sorted[i].alliance_id);
        }
    }
    return allowed;
}
```

#### Filter control HTML

Added above the results content, inside the `#results` section:

```html
<div id="result-filter" class="result-filter hidden">
    <span>Filter:</span>
    <button class="filter-btn active" data-filter="all">All</button>
    <button class="filter-btn" data-filter="top3">Top 3 per faction</button>
    <button class="filter-btn" data-filter="top5">Top 5 per faction</button>
    <button class="filter-btn" data-filter="top10">Top 10 per faction</button>
</div>
```

The filter bar is added to `index.html` inside `<section id="results">`, between the `<h2>` and `<div id="results-content">`. It starts hidden and becomes visible when results are first rendered.

#### Filter button handler

```javascript
// In setupEventHandlers():
document.getElementById("result-filter").addEventListener("click", (e) => {
    if (!e.target.classList.contains("filter-btn")) return;

    // Update active state
    for (const btn of document.querySelectorAll(".filter-btn")) {
        btn.classList.toggle("active", btn === e.target);
    }

    resultFilter = e.target.dataset.filter;

    // Re-render current results
    if (lastResult) {
        if (lastResult.event_history) {
            renderSingleResults(lastResult);
        } else {
            renderMonteCarloResults(lastResult);
        }
    }
});
```

#### Applying the filter

Every rendering function calls `getFilteredAlliances(resultFilter)` and skips alliances not in the set:

```javascript
// Example in renderSingleResults():
const allowed = getFilteredAlliances(resultFilter);

const entries = Object.entries(result.final_spice)
    .filter(([id]) => !allowed || allowed.has(id))
    .map(([id, spice]) => ({ id, spice, tier: result.rankings[id] }));
entries.sort((a, b) => a.tier - b.tier || b.spice - a.spice);
```

For event detail tables, the filter applies to each table's rows:

```javascript
// In renderEventDetail() — spice table:
for (const [id, before] of Object.entries(event.spice_before)) {
    if (allowed && !allowed.has(id)) continue;
    // ... render row ...
}
```

For charts, pass only filtered alliance IDs:

```javascript
// In renderMonteCarloResults():
const allAids = Object.keys(result.tier_distribution);
const allowed = getFilteredAlliances(resultFilter);
const aids = allAids.filter(aid => !allowed || allowed.has(aid));
aids.sort(/* existing sort */);
```

**Note on ranking computation**: Ranks are computed over *all* alliances (not filtered ones), then the display is filtered. This ensures rank numbers remain consistent regardless of filter.

#### Filter CSS

```css
.result-filter {
    margin: 8px 0 16px;
    display: flex;
    align-items: center;
    gap: 8px;
}

.result-filter span {
    font-weight: 600;
    font-size: 0.9em;
}

.filter-btn {
    padding: 4px 12px;
    border: 1px solid #ccc;
    border-radius: 4px;
    background: #fff;
    cursor: pointer;
    font-size: 0.85em;
}

.filter-btn.active {
    background: #333;
    color: #fff;
    border-color: #333;
}

.filter-btn:hover:not(.active) {
    background: #f0f0f0;
}
```

#### Show filter bar on results render

Both `renderSingleResults()` and `renderMonteCarloResults()` add this at the top:

```javascript
document.getElementById("result-filter").classList.remove("hidden");
```

---

## 6. Shareable URL for Configuration

### 6a. Encoding configuration into URL

#### Payload structure

```javascript
{
    v: 1,                    // Version prefix for future-proofing
    state: { ... },          // Full state JSON
    model: { ... },          // Full model JSON
    seed: 42,                // Single-run seed (null if blank)
    mcIterations: 1000,      // Monte Carlo iterations
    mcBaseSeed: 0,           // Monte Carlo base seed
}
```

#### Compression pipeline

1. `JSON.stringify()` the payload
2. Encode to UTF-8 bytes
3. Compress with `CompressionStream("deflate")` (built-in browser API, no library needed)
4. Base64url-encode the compressed bytes
5. Set as URL hash: `#v1:<base64url>`

```javascript
async function encodeConfigToHash() {
    const payload = {
        v: 1,
        state: JSON.parse(document.getElementById("state-textarea").value),
        model: JSON.parse(document.getElementById("model-textarea").value),
        seed: document.getElementById("single-seed").value || null,
        mcIterations: parseInt(document.getElementById("mc-iterations").value, 10) || 1000,
        mcBaseSeed: parseInt(document.getElementById("mc-base-seed").value, 10) || 0,
    };

    const json = JSON.stringify(payload);
    const bytes = new TextEncoder().encode(json);

    // Compress using CompressionStream
    const cs = new CompressionStream("deflate");
    const writer = cs.writable.getWriter();
    writer.write(bytes);
    writer.close();

    const compressed = await new Response(cs.readable).arrayBuffer();
    const compressedBytes = new Uint8Array(compressed);

    // Base64url encode
    let base64 = btoa(String.fromCharCode(...compressedBytes));
    base64 = base64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

    return `v1:${base64}`;
}
```

#### Size check

URLs have a practical limit of ~2000 characters in some browsers and ~8000 in others. Check before applying:

```javascript
async function shareConfig() {
    try {
        const hash = await encodeConfigToHash();
        const url = `${window.location.origin}${window.location.pathname}#${hash}`;

        if (url.length > 8000) {
            showNotification("Configuration too large to share via URL", "error");
            return;
        }

        window.location.hash = hash;
        await navigator.clipboard.writeText(url);
        showNotification("Link copied to clipboard");
    } catch (e) {
        showNotification("Failed to generate share link: " + e.message, "error");
    }
}
```

### 6b. Load configuration from URL on page load

#### Decoding

```javascript
async function decodeHashToConfig(hash) {
    if (!hash || !hash.startsWith("v1:")) return null;

    const base64url = hash.slice(3);
    // Restore standard base64
    let base64 = base64url.replace(/-/g, "+").replace(/_/g, "/");
    while (base64.length % 4) base64 += "=";

    const compressed = Uint8Array.from(atob(base64), c => c.charCodeAt(0));

    // Decompress
    const ds = new DecompressionStream("deflate");
    const writer = ds.writable.getWriter();
    writer.write(compressed);
    writer.close();

    const decompressed = await new Response(ds.readable).arrayBuffer();
    const json = new TextDecoder().decode(decompressed);

    return JSON.parse(json);
}
```

#### Integration into initialization

After default state/model loading, check for hash:

```javascript
// In DOMContentLoaded handler, after defaults are loaded:
const hash = window.location.hash.slice(1);  // Remove leading #
if (hash) {
    try {
        const config = await decodeHashToConfig(hash);
        if (config && config.v === 1) {
            // Populate state
            document.getElementById("state-textarea").value = JSON.stringify(config.state, null, 2);
            validateState();

            // Populate model
            modelFormData = config.model;
            document.getElementById("model-textarea").value = JSON.stringify(config.model, null, 2);
            buildModelForm();
            validateModel();

            // Populate run params
            if (config.seed != null) {
                document.getElementById("single-seed").value = config.seed;
            }
            document.getElementById("mc-iterations").value = config.mcIterations || 1000;
            document.getElementById("mc-base-seed").value = config.mcBaseSeed || 0;

            showNotification("Configuration loaded from shared URL");
        }
    } catch {
        // Invalid hash — silently ignore
    }
}
```

### 6c. Share button

Add a button in the run controls section:

```html
<!-- In #run-controls, after the run groups -->
<button id="share-btn">Copy Share Link</button>
```

Handler:

```javascript
// In setupEventHandlers():
document.getElementById("share-btn").addEventListener("click", shareConfig);
```

### 6d. Notification system

A simple toast notification for share/load feedback:

```javascript
function showNotification(message, type = "info") {
    const existing = document.querySelector(".notification");
    if (existing) existing.remove();

    const el = document.createElement("div");
    el.className = `notification notification-${type}`;
    el.textContent = message;
    document.body.appendChild(el);

    setTimeout(() => el.remove(), 3000);
}
```

```css
.notification {
    position: fixed;
    top: 16px;
    right: 16px;
    padding: 10px 20px;
    border-radius: 6px;
    font-size: 0.9em;
    z-index: 1000;
    animation: fadeInOut 3s ease;
}

.notification-info {
    background: #d4edda;
    color: #155724;
    border: 1px solid #c3e6cb;
}

.notification-error {
    background: #f8d7da;
    color: #721c24;
    border: 1px solid #f5c6cb;
}

@keyframes fadeInOut {
    0% { opacity: 0; transform: translateY(-10px); }
    10% { opacity: 1; transform: translateY(0); }
    80% { opacity: 1; }
    100% { opacity: 0; }
}
```

### 6e. Backwards compatibility

- If `hash` is empty or doesn't start with `v1:`, skip loading entirely (silent no-op)
- If `decodeHashToConfig()` throws (bad base64, bad JSON, decompression failure), catch and ignore
- Future versions would use `v2:`, `v3:`, etc. The decoder checks `config.v === 1` before applying

---

## 7. Python Backend Change: Per-Alliance Bracket Map in Event History

### Problem

The current `event.brackets` structure groups alliances by bracket number:

```json
{
    "1": {"attackers": ["VON", "UTW"], "defenders": ["Ghst", "Hot"]},
    "2": {"attackers": ["RAG3"], "defenders": ["SPXP"]}
}
```

The frontend needs to quickly look up any alliance's bracket for the targeting table. While this can be derived client-side from the grouped structure (as shown in `getAllianceBracket()` above), a flat per-alliance map is also useful. The grouped format is sufficient for the frontend's needs, so **no Python change is strictly required** — the `getAllianceBracket()` helper in section 5a handles the inversion client-side.

However, if a flat format is desired for simplicity, `coordinate_event()` in `events.py` could add an `alliance_brackets` field:

```python
# Optional — in coordinate_event(), add to event_info:
"alliance_brackets": all_brackets,  # {alliance_id: bracket_number}
```

This field already exists as `all_brackets` on line 80 of `events.py`. Adding it to `event_info` is a one-line change but would increase the event_history payload size. **Recommended approach: use client-side inversion from the existing `brackets` field to avoid backend changes.**

---

## File Changes Summary

| File | Change |
|------|--------|
| `web/index.html` | Add result filter bar in `#results` section, add share button in `#run-controls` |
| `web/js/app.js` | Fix duplicate listener bug (guard flag), add validation functions and error display, add heuristic hint computation and placeholder updates, add faction/rank/bracket columns to all results tables, add filter state and re-render logic, add URL encode/decode and share functions, add notification system |
| `web/css/style.css` | Ensure `.hidden` wins over `.spinner`, add `.row-error-cell`/`.row-error-msg` styles, add `.result-filter`/`.filter-btn` styles, add `.notification` toast styles |

No Python backend changes required. No new files created.

---

## Implementation Order

1. **Issue 1** — Duplicate rows bug (add `formHandlersAttached` flag)
2. **Issue 4** — Spinner bug (CSS specificity fix)
3. **Issue 2** — Input validation (new validation functions, error cells in form tables, updated `collectFormData()`)
4. **Issue 3** — Heuristic hints (new `computeHeuristicHints()`, placeholder updates on build/change/add)
5. **Issue 5** — Enhanced results (new helpers `getAllianceFaction()`, `computeRanks()`, `getAllianceBracket()`, updated render functions, filter bar and re-render logic)
6. **Issue 6** — Shareable URLs (compress/decompress, hash encode/decode, share button, init-time load, notification toast)

Each issue can be implemented and tested independently. Issues 1–4 touch the model form code, issues 5–6 touch the results/run code, so they have minimal overlap.
