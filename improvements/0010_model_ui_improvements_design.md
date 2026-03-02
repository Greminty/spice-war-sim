# Model Config UI Improvements — Design

## Overview

Replace the model config raw JSON textarea with a structured, section-based form editor built from seven accordion panels (General Settings, Faction Targeting, Default Targets, Event Targets, Event Reinforcements, Battle Outcome Matrix, Damage Weights). Add a collapsible "Edit JSON" toggle to the state editor so the textarea is hidden by default while the summary tables remain always visible. A "Edit as JSON" / "Back to form" toggle on the model editor provides a raw-JSON escape hatch. All form changes regenerate JSON and re-validate through the existing `PyBridge.validateModelConfig` path. No Python backend changes are needed — all modifications are confined to `web/index.html`, `web/js/app.js`, and `web/css/style.css`.

---

## 1. Collapsible State Editor

### Modified markup in `web/index.html`

The state section is restructured so the summary tables and controls sit outside a `<details>` element, while the textarea is wrapped inside it. The upload button, validation badge, and error message remain always visible.

```html
<!-- State Editor -->
<section id="state-editor">
    <h2>Game State <span id="state-status" class="status"></span></h2>
    <div class="editor-controls">
        <button id="state-upload-btn">Upload JSON</button>
        <input type="file" id="state-file-input" accept=".json" class="hidden">
    </div>
    <div id="state-error" class="error-msg hidden"></div>
    <div id="state-summary" class="hidden"></div>
    <details id="state-json-toggle">
        <summary>Edit JSON</summary>
        <textarea id="state-textarea" rows="20" spellcheck="false"></textarea>
    </details>
</section>
```

The `<details>` element is collapsed by default (no `open` attribute). The existing `validateState()`, `onStateInput()`, and `renderStateSummary()` functions are unchanged — the textarea retains its `id` and event wiring. The only JS change is moving the summary container (`#state-summary`) before the `<details>` element in the DOM, which the new HTML already reflects.

---

## 2. Model Config — Sectioned Form

### Modified markup in `web/index.html`

The model editor section replaces the single textarea with a form container and a hidden JSON textarea that appears on toggle.

```html
<!-- Model Editor -->
<section id="model-editor">
    <h2>Model Config <span id="model-status" class="status"></span></h2>
    <div class="editor-controls">
        <button id="model-upload-btn">Upload JSON</button>
        <input type="file" id="model-file-input" accept=".json" class="hidden">
        <button id="csv-import-btn">Import CSV</button>
        <input type="file" id="csv-file-input" accept=".csv" class="hidden">
        <button id="csv-template-btn">Download CSV Template</button>
        <button id="model-view-toggle" class="toggle-btn">Edit as JSON</button>
        <button id="download-model-btn">Download Model JSON</button>
    </div>
    <div id="model-error" class="error-msg hidden"></div>

    <!-- Form view (default) -->
    <div id="model-form"></div>

    <!-- JSON view (hidden) -->
    <div id="model-json-view" class="hidden">
        <textarea id="model-textarea" rows="20" spellcheck="false"></textarea>
    </div>
</section>
```

The "Download Model JSON" button moves up into the editor controls so it's always accessible regardless of view mode.

### Form structure

`#model-form` is populated by JS. Each section is a `<details>` element that can open/close independently (multiple can be open at once). The initial render generates all seven sections. Sections that depend on alliance/event data show a "Load valid state first" placeholder when `stateIsValid` is false.

---

## 3. Model Form State

### New module-level state in `web/js/app.js`

```javascript
// Current model form data, mirrors the JSON structure.
// null when form hasn't been populated yet.
let modelFormData = null;

// Tracks which view is active: "form" or "json"
let modelViewMode = "form";
```

`modelFormData` is a plain object with the same shape as a model config JSON. Every form interaction mutates this object and calls `syncFormToJson()`.

---

## 4. Building the Form

#### `buildModelForm()`

Called on initialization (after state is validated) and whenever the state changes. Reads `modelFormData` and populates `#model-form` with seven accordion sections.

```javascript
function buildModelForm() {
    const container = document.getElementById("model-form");

    if (!stateIsValid) {
        container.innerHTML = '<p class="muted">Load a valid game state to configure the model.</p>';
        return;
    }

    const alliances = getAlliancesFromState();
    const events = getEventsFromState();

    let html = "";
    html += buildGeneralSettings();
    html += buildFactionTargeting(alliances);
    html += buildDefaultTargets(alliances);
    html += buildEventTargets(alliances, events);
    html += buildEventReinforcements(alliances, events);
    html += buildOutcomeMatrix(alliances, events);
    html += buildDamageWeights(alliances);

    container.innerHTML = html;
    attachFormHandlers();
}
```

#### `getAlliancesFromState()` / `getEventsFromState()`

Helpers that extract structured data from `currentStateDict` for use by form builders. These avoid re-parsing the raw textarea.

```javascript
function getAlliancesFromState() {
    if (!currentStateDict) return [];
    return currentStateDict.alliances.map(a => ({
        id: a.alliance_id,
        faction: a.faction,
    }));
}

function getEventsFromState() {
    if (!currentStateDict) return [];
    return currentStateDict.event_schedule.map((e, i) => ({
        number: i + 1,
        attacker_faction: e.attacker_faction,
        day: e.day,
    }));
}
```

#### Helper: faction-partitioned alliance lists

Many sections need the alliances split by faction. This helper is used repeatedly by the section builders.

```javascript
function alliancesByFaction(alliances) {
    const factions = {};
    for (const a of alliances) {
        if (!factions[a.faction]) factions[a.faction] = [];
        factions[a.faction].push(a.id);
    }
    return factions;
}
```

---

## 5. Section Builders

Each section builder returns an HTML string for one `<details>` accordion panel. All inputs use `data-field` attributes to identify which model config key they affect. Interactive rows (add/remove) use a consistent pattern.

### 5a. General Settings

```javascript
function buildGeneralSettings() {
    const seed = modelFormData.random_seed ?? "";
    const strategy = modelFormData.targeting_strategy ?? "expected_value";

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
        </div>
    </details>`;
}
```

### 5b. Faction Targeting Strategy

One row per faction. `(use global default)` emits no key.

```javascript
function buildFactionTargeting(alliances) {
    const factions = [...new Set(alliances.map(a => a.faction))];
    const fts = modelFormData.faction_targeting_strategy || {};

    let rows = "";
    for (const faction of factions) {
        const val = fts[faction] || "";
        rows += `
        <tr>
            <td>${esc(faction)}</td>
            <td>
                <select data-field="faction_targeting_strategy" data-faction="${esc(faction)}">
                    <option value="" ${val === "" ? "selected" : ""}>(use global default)</option>
                    <option value="expected_value" ${val === "expected_value" ? "selected" : ""}>
                        expected_value</option>
                    <option value="highest_spice" ${val === "highest_spice" ? "selected" : ""}>
                        highest_spice</option>
                </select>
            </td>
        </tr>`;
    }

    return `
    <details class="model-section">
        <summary>Faction Targeting Strategy</summary>
        <table class="form-table">
            <tr><th>Faction</th><th>Strategy</th></tr>
            ${rows}
        </table>
    </details>`;
}
```

### 5c. Default Targets

Dynamic rows with add/remove. Each row lets the user pick an alliance and either pin a target or select a strategy.

```javascript
function buildDefaultTargets(alliances) {
    const dt = modelFormData.default_targets || {};
    const aids = alliances.map(a => a.id);

    let rows = "";
    for (const [aid, val] of Object.entries(dt)) {
        const isPinned = typeof val === "string" || (typeof val === "object" && val.target);
        const target = typeof val === "string" ? val : val.target || "";
        const strategy = val.strategy || "";
        rows += defaultTargetRow(aids, aid, isPinned, target, strategy);
    }

    return `
    <details class="model-section">
        <summary>Default Targets</summary>
        <table class="form-table" id="default-targets-table">
            <tr><th>Alliance</th><th>Type</th><th>Value</th><th></th></tr>
            ${rows}
        </table>
        <button class="add-row-btn" data-action="add-default-target">+ Add default target</button>
    </details>`;
}

function defaultTargetRow(aids, selectedAid, isPinned, target, strategy) {
    return `
    <tr class="dynamic-row" data-section="default_targets">
        <td>${allianceDropdown(aids, selectedAid, "dt-alliance")}</td>
        <td>
            <select class="dt-type">
                <option value="pin" ${isPinned ? "selected" : ""}>Pin to target</option>
                <option value="strategy" ${!isPinned ? "selected" : ""}>Use strategy</option>
            </select>
        </td>
        <td>
            <span class="dt-pin-value ${isPinned ? "" : "hidden"}">
                ${allianceDropdown(aids, target, "dt-target")}
            </span>
            <span class="dt-strategy-value ${isPinned ? "hidden" : ""}">
                ${strategyDropdown(strategy, "dt-strategy")}
            </span>
        </td>
        <td><button class="remove-row-btn" title="Remove">&times;</button></td>
    </tr>`;
}
```

### 5d. Event Targets

One sub-section per event. Alliance dropdown shows only attacking-faction alliances; target dropdown shows only defending-faction alliances.

```javascript
function buildEventTargets(alliances, events) {
    const et = modelFormData.event_targets || {};
    const byFaction = alliancesByFaction(alliances);
    const factions = Object.keys(byFaction);

    let sections = "";
    for (const event of events) {
        const eventKey = String(event.number);
        const attackerFaction = event.attacker_faction;
        const defenderFaction = factions.find(f => f !== attackerFaction);
        const attackerIds = byFaction[attackerFaction] || [];
        const defenderIds = byFaction[defenderFaction] || [];
        const overrides = et[eventKey] || {};

        let rows = "";
        for (const [aid, val] of Object.entries(overrides)) {
            const isPinned = typeof val === "string" || (typeof val === "object" && val.target);
            const target = typeof val === "string" ? val : val.target || "";
            const strategy = val.strategy || "";
            rows += eventTargetRow(attackerIds, defenderIds, aid, isPinned, target, strategy, eventKey);
        }

        sections += `
        <div class="event-subsection" data-event="${eventKey}">
            <h4>Event ${event.number} — ${esc(attackerFaction)} attacks (${esc(event.day)})</h4>
            <table class="form-table">
                <tr><th>Alliance</th><th>Type</th><th>Value</th><th></th></tr>
                ${rows}
            </table>
            <button class="add-row-btn" data-action="add-event-target" data-event="${eventKey}">
                + Add override</button>
        </div>`;
    }

    return `
    <details class="model-section">
        <summary>Event Targets</summary>
        ${sections}
    </details>`;
}
```

`eventTargetRow()` follows the same pattern as `defaultTargetRow()` but constrains the alliance dropdown to `attackerIds` and the target dropdown to `defenderIds`.

### 5e. Event Reinforcements

One sub-section per event. Both dropdowns show defending-faction alliances.

```javascript
function buildEventReinforcements(alliances, events) {
    const er = modelFormData.event_reinforcements || {};
    const byFaction = alliancesByFaction(alliances);
    const factions = Object.keys(byFaction);

    let sections = "";
    for (const event of events) {
        const eventKey = String(event.number);
        const defenderFaction = factions.find(f => f !== event.attacker_faction);
        const defenderIds = byFaction[defenderFaction] || [];
        const overrides = er[eventKey] || {};

        let rows = "";
        for (const [defender, target] of Object.entries(overrides)) {
            rows += `
            <tr class="dynamic-row" data-section="event_reinforcements" data-event="${eventKey}">
                <td>${allianceDropdown(defenderIds, defender, "er-defender")}</td>
                <td>${allianceDropdown(defenderIds, target, "er-target")}</td>
                <td><button class="remove-row-btn" title="Remove">&times;</button></td>
            </tr>`;
        }

        sections += `
        <div class="event-subsection" data-event="${eventKey}">
            <h4>Event ${event.number} — ${esc(event.attacker_faction)} attacks (${esc(event.day)})</h4>
            <table class="form-table">
                <tr><th>Defender</th><th>Reinforce (join battle of)</th><th></th></tr>
                ${rows}
            </table>
            <button class="add-row-btn" data-action="add-event-reinforcement" data-event="${eventKey}">
                + Add</button>
        </div>`;
    }

    return `
    <details class="model-section">
        <summary>Event Reinforcements</summary>
        ${sections}
    </details>`;
}
```

### 5f. Battle Outcome Matrix

Grouped by day. Each row has attacker/defender dropdowns (including `*` wildcard), percentage inputs, and optional custom fields.

```javascript
function buildOutcomeMatrix(alliances, events) {
    const matrix = modelFormData.battle_outcome_matrix || {};
    const aids = alliances.map(a => a.id);
    const aidsWithWildcard = ["*", ...aids];
    const days = [...new Set(events.map(e => e.day))];

    let sections = "";
    for (const day of days) {
        const dayMatrix = matrix[day] || {};
        let rows = "";

        for (const [attacker, defenders] of Object.entries(dayMatrix)) {
            for (const [defender, probs] of Object.entries(defenders)) {
                const full = (probs.full_success * 100).toFixed(1);
                const partial = (probs.partial_success * 100).toFixed(1);
                const custom = probs.custom != null ? (probs.custom * 100).toFixed(1) : "";
                const customTheft = probs.custom_theft_percentage != null
                    ? probs.custom_theft_percentage : "";

                rows += `
                <tr class="dynamic-row" data-section="battle_outcome_matrix" data-day="${day}">
                    <td>${wildcardDropdown(aidsWithWildcard, attacker, "bom-attacker")}</td>
                    <td>${wildcardDropdown(aidsWithWildcard, defender, "bom-defender")}</td>
                    <td><input type="number" class="bom-full pct-input" value="${full}"
                               min="0" max="100" step="0.1"></td>
                    <td><input type="number" class="bom-partial pct-input" value="${partial}"
                               min="0" max="100" step="0.1"></td>
                    <td><input type="number" class="bom-custom pct-input" value="${custom}"
                               min="0" max="100" step="0.1" placeholder="—"></td>
                    <td><input type="number" class="bom-custom-theft pct-input" value="${customTheft}"
                               min="0" max="100" step="0.1" placeholder="—"></td>
                    <td><button class="remove-row-btn" title="Remove">&times;</button></td>
                </tr>`;
            }
        }

        sections += `
        <div class="day-subsection" data-day="${day}">
            <h4>${capitalize(day)} outcomes</h4>
            <p class="help-text">Lookup priority: exact match &rarr; attacker wildcard &rarr;
                defender wildcard &rarr; heuristic fallback</p>
            <table class="form-table outcome-table">
                <tr>
                    <th>Attacker</th><th>Defender</th>
                    <th>Full %</th><th>Partial %</th>
                    <th>Custom %</th><th>Custom Theft %</th><th></th>
                </tr>
                ${rows}
            </table>
            <div id="bom-validation-${day}" class="validation-inline hidden"></div>
            <button class="add-row-btn" data-action="add-outcome-row" data-day="${day}">
                + Add row</button>
        </div>`;
    }

    return `
    <details class="model-section">
        <summary>Battle Outcome Matrix</summary>
        ${sections}
    </details>`;
}
```

#### Inline validation for outcome rows

When a row's full + partial + custom exceeds 100%, a red inline message appears below the table for that day. This is computed in `collectFormData()` and displayed via the `#bom-validation-{day}` div.

```javascript
function validateOutcomeRow(full, partial, custom) {
    const total = (full || 0) + (partial || 0) + (custom || 0);
    if (total > 100) {
        return `Probabilities sum to ${total.toFixed(1)}% (must be <= 100%)`;
    }
    return null;
}
```

### 5g. Damage Weights

Simple dynamic table with alliance dropdown and weight input.

```javascript
function buildDamageWeights(alliances) {
    const dw = modelFormData.damage_weights || {};
    const aids = alliances.map(a => a.id);

    let rows = "";
    for (const [aid, weight] of Object.entries(dw)) {
        rows += `
        <tr class="dynamic-row" data-section="damage_weights">
            <td>${allianceDropdown(aids, aid, "dw-alliance")}</td>
            <td><input type="number" class="dw-weight" value="${weight}"
                       min="0" max="1" step="0.05"></td>
            <td><button class="remove-row-btn" title="Remove">&times;</button></td>
        </tr>`;
    }

    return `
    <details class="model-section">
        <summary>Damage Weights</summary>
        <p class="help-text">Only relevant when multiple attackers target the same defender.
            Weights are normalized to sum to 1.</p>
        <table class="form-table" id="damage-weights-table">
            <tr><th>Alliance</th><th>Weight</th><th></th></tr>
            ${rows}
        </table>
        <button class="add-row-btn" data-action="add-damage-weight">+ Add</button>
    </details>`;
}
```

---

## 6. Shared Dropdown Helpers

Small functions that return `<select>` HTML strings. Used by all section builders.

```javascript
function allianceDropdown(aids, selected, className) {
    let html = `<select class="${className}">`;
    for (const aid of aids) {
        html += `<option value="${esc(aid)}" ${aid === selected ? "selected" : ""}>${esc(aid)}</option>`;
    }
    html += "</select>";
    return html;
}

function wildcardDropdown(aids, selected, className) {
    let html = `<select class="${className}">`;
    for (const aid of aids) {
        const label = aid === "*" ? "* (any)" : aid;
        html += `<option value="${esc(aid)}" ${aid === selected ? "selected" : ""}>${esc(label)}</option>`;
    }
    html += "</select>";
    return html;
}

function strategyDropdown(selected, className) {
    return `
    <select class="${className}">
        <option value="expected_value" ${selected === "expected_value" ? "selected" : ""}>
            expected_value</option>
        <option value="highest_spice" ${selected === "highest_spice" ? "selected" : ""}>
            highest_spice</option>
    </select>`;
}

function capitalize(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
}
```

---

## 7. Form Event Handling

#### `attachFormHandlers()`

Uses event delegation on `#model-form` to handle all input changes, add/remove actions, and type toggles with a single listener.

```javascript
function attachFormHandlers() {
    const form = document.getElementById("model-form");

    form.addEventListener("input", (e) => {
        collectFormData();
        scheduleModelValidation();
    });

    form.addEventListener("change", (e) => {
        // Handle type toggle (pin/strategy) visibility
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

#### `handleAddRow(button)`

Reads `data-action` and `data-event`/`data-day` from the button to determine which section to append to. Inserts a new empty row before the button's parent table's last `<tr>` position (or appends to the `<tbody>`). After insertion, calls `collectFormData()` and `scheduleModelValidation()`.

```javascript
function handleAddRow(button) {
    const action = button.dataset.action;
    const table = button.previousElementSibling?.tagName === "DIV"
        ? button.parentElement.querySelector("table")
        : button.previousElementSibling;
    const alliances = getAlliancesFromState();
    const aids = alliances.map(a => a.id);

    let newRow = "";
    switch (action) {
        case "add-default-target":
            newRow = defaultTargetRow(aids, aids[0], true, aids[0], "");
            break;
        case "add-event-target": {
            const eventKey = button.dataset.event;
            const events = getEventsFromState();
            const event = events.find(e => String(e.number) === eventKey);
            const byFaction = alliancesByFaction(alliances);
            const factions = Object.keys(byFaction);
            const defenderFaction = factions.find(f => f !== event.attacker_faction);
            newRow = eventTargetRow(
                byFaction[event.attacker_faction], byFaction[defenderFaction],
                byFaction[event.attacker_faction][0], true, byFaction[defenderFaction][0], "",
                eventKey
            );
            break;
        }
        case "add-event-reinforcement": {
            const eventKey = button.dataset.event;
            const events = getEventsFromState();
            const event = events.find(e => String(e.number) === eventKey);
            const byFaction = alliancesByFaction(alliances);
            const factions = Object.keys(byFaction);
            const defenderFaction = factions.find(f => f !== event.attacker_faction);
            const defenderIds = byFaction[defenderFaction];
            newRow = `
            <tr class="dynamic-row" data-section="event_reinforcements" data-event="${eventKey}">
                <td>${allianceDropdown(defenderIds, defenderIds[0], "er-defender")}</td>
                <td>${allianceDropdown(defenderIds, defenderIds[0], "er-target")}</td>
                <td><button class="remove-row-btn" title="Remove">&times;</button></td>
            </tr>`;
            break;
        }
        case "add-outcome-row": {
            const day = button.dataset.day;
            const aidsWithWildcard = ["*", ...aids];
            newRow = `
            <tr class="dynamic-row" data-section="battle_outcome_matrix" data-day="${day}">
                <td>${wildcardDropdown(aidsWithWildcard, aids[0], "bom-attacker")}</td>
                <td>${wildcardDropdown(aidsWithWildcard, aids[0], "bom-defender")}</td>
                <td><input type="number" class="bom-full pct-input" value="" min="0" max="100" step="0.1"></td>
                <td><input type="number" class="bom-partial pct-input" value="" min="0" max="100" step="0.1"></td>
                <td><input type="number" class="bom-custom pct-input" value="" min="0" max="100" step="0.1" placeholder="—"></td>
                <td><input type="number" class="bom-custom-theft pct-input" value="" min="0" max="100" step="0.1" placeholder="—"></td>
                <td><button class="remove-row-btn" title="Remove">&times;</button></td>
            </tr>`;
            break;
        }
        case "add-damage-weight":
            newRow = `
            <tr class="dynamic-row" data-section="damage_weights">
                <td>${allianceDropdown(aids, aids[0], "dw-alliance")}</td>
                <td><input type="number" class="dw-weight" value="0.5" min="0" max="1" step="0.05"></td>
                <td><button class="remove-row-btn" title="Remove">&times;</button></td>
            </tr>`;
            break;
    }

    if (newRow && table) {
        table.querySelector("tr:last-child").insertAdjacentHTML("afterend", newRow);
        collectFormData();
        scheduleModelValidation();
    }
}
```

---

## 8. Collecting Form Data

#### `collectFormData()`

Walks the DOM inside `#model-form` and reconstructs `modelFormData` from the current form values. This is the single source of truth for form-to-JSON conversion.

```javascript
function collectFormData() {
    const data = {};

    // General settings
    const seedVal = document.getElementById("form-seed")?.value;
    if (seedVal !== "" && seedVal != null) {
        data.random_seed = parseInt(seedVal, 10);
    }
    const strategyVal = document.getElementById("form-strategy")?.value;
    if (strategyVal) {
        data.targeting_strategy = strategyVal;
    }

    // Faction targeting strategy
    const ftsSelects = document.querySelectorAll('[data-field="faction_targeting_strategy"]');
    const fts = {};
    for (const sel of ftsSelects) {
        if (sel.value) {
            fts[sel.dataset.faction] = sel.value;
        }
    }
    if (Object.keys(fts).length > 0) data.faction_targeting_strategy = fts;

    // Default targets
    const dtRows = document.querySelectorAll('#default-targets-table .dynamic-row');
    const dt = {};
    for (const row of dtRows) {
        const aid = row.querySelector(".dt-alliance").value;
        const type = row.querySelector(".dt-type").value;
        if (type === "pin") {
            dt[aid] = { target: row.querySelector(".dt-target").value };
        } else {
            dt[aid] = { strategy: row.querySelector(".dt-strategy").value };
        }
    }
    if (Object.keys(dt).length > 0) data.default_targets = dt;

    // Event targets
    const etContainers = document.querySelectorAll(
        '[data-action="add-event-target"]');
    const et = {};
    for (const btn of etContainers) {
        const eventKey = btn.dataset.event;
        const rows = btn.parentElement.querySelectorAll('.dynamic-row');
        const overrides = {};
        for (const row of rows) {
            const aid = row.querySelector("[class*='et-alliance']")?.value
                     || row.querySelector("select:first-child")?.value;
            const type = row.querySelector("[class*='dt-type']")?.value;
            if (type === "pin") {
                const target = row.querySelector("[class*='dt-target']")?.value
                            || row.querySelector("[class*='et-target']")?.value;
                overrides[aid] = target;
            } else {
                overrides[aid] = { strategy: row.querySelector("[class*='dt-strategy']")?.value
                                          || row.querySelector("[class*='et-strategy']")?.value };
            }
        }
        if (Object.keys(overrides).length > 0) et[eventKey] = overrides;
    }
    if (Object.keys(et).length > 0) data.event_targets = et;

    // Event reinforcements
    const erContainers = document.querySelectorAll(
        '[data-action="add-event-reinforcement"]');
    const er = {};
    for (const btn of erContainers) {
        const eventKey = btn.dataset.event;
        const rows = btn.parentElement.querySelectorAll('.dynamic-row');
        const overrides = {};
        for (const row of rows) {
            const defender = row.querySelector(".er-defender").value;
            const target = row.querySelector(".er-target").value;
            overrides[defender] = target;
        }
        if (Object.keys(overrides).length > 0) er[eventKey] = overrides;
    }
    if (Object.keys(er).length > 0) data.event_reinforcements = er;

    // Battle outcome matrix
    const bomDays = document.querySelectorAll(".day-subsection");
    const matrix = {};
    for (const daySection of bomDays) {
        const day = daySection.dataset.day;
        const rows = daySection.querySelectorAll(".dynamic-row");
        const dayMatrix = {};
        for (const row of rows) {
            const attacker = row.querySelector(".bom-attacker").value;
            const defender = row.querySelector(".bom-defender").value;
            const full = parseFloat(row.querySelector(".bom-full").value);
            const partial = parseFloat(row.querySelector(".bom-partial").value);
            const customVal = row.querySelector(".bom-custom").value;
            const customTheftVal = row.querySelector(".bom-custom-theft").value;

            if (isNaN(full) || isNaN(partial)) continue;

            const probs = {
                full_success: full / 100,
                partial_success: partial / 100,
            };
            if (customVal !== "" && !isNaN(parseFloat(customVal))) {
                probs.custom = parseFloat(customVal) / 100;
            }
            if (customTheftVal !== "" && !isNaN(parseFloat(customTheftVal))) {
                probs.custom_theft_percentage = parseFloat(customTheftVal);
            }

            // Inline validation
            const error = validateOutcomeRow(full, partial,
                customVal !== "" ? parseFloat(customVal) : 0);
            row.classList.toggle("validation-error", error != null);

            if (!dayMatrix[attacker]) dayMatrix[attacker] = {};
            dayMatrix[attacker][defender] = probs;
        }
        if (Object.keys(dayMatrix).length > 0) matrix[day] = dayMatrix;
    }
    if (Object.keys(matrix).length > 0) data.battle_outcome_matrix = matrix;

    // Damage weights
    const dwRows = document.querySelectorAll('#damage-weights-table .dynamic-row');
    const dw = {};
    for (const row of dwRows) {
        const aid = row.querySelector(".dw-alliance").value;
        const weight = parseFloat(row.querySelector(".dw-weight").value);
        if (!isNaN(weight)) dw[aid] = weight;
    }
    if (Object.keys(dw).length > 0) data.damage_weights = dw;

    modelFormData = data;
    syncFormToJson();
}
```

---

## 9. Form <-> JSON Synchronization

#### `syncFormToJson()`

Writes the current `modelFormData` to the hidden textarea. Called after every form change.

```javascript
function syncFormToJson() {
    const textarea = document.getElementById("model-textarea");
    textarea.value = JSON.stringify(modelFormData, null, 2);
}
```

#### `syncJsonToForm()`

Parses the textarea content and rebuilds the form. Called when switching from JSON view to form view, or after file upload / CSV import.

```javascript
function syncJsonToForm() {
    const textarea = document.getElementById("model-textarea");
    let parsed;
    try {
        parsed = JSON.parse(textarea.value);
    } catch {
        // If JSON is invalid, stay in JSON view and show error
        return false;
    }

    modelFormData = parsed;
    buildModelForm();
    return true;
}
```

#### `scheduleModelValidation()`

Replaces the existing `onModelInput()` for form-originated changes. Same 300ms debounce, but validates from `modelFormData` rather than re-parsing the textarea.

```javascript
function scheduleModelValidation() {
    clearTimeout(modelValidationTimer);
    modelValidationTimer = setTimeout(() => {
        // Textarea is already synced by syncFormToJson(), reuse existing validateModel()
        validateModel();
    }, 300);
}
```

---

## 10. View Toggle

#### Toggle button handler

Switches between form view and JSON view. When switching to form view, parses the textarea and rebuilds the form. If the JSON contains values the form can't represent (e.g. unknown keys), shows a warning and stays in JSON view.

```javascript
function toggleModelView() {
    const toggleBtn = document.getElementById("model-view-toggle");
    const formDiv = document.getElementById("model-form");
    const jsonDiv = document.getElementById("model-json-view");

    if (modelViewMode === "form") {
        // Switching to JSON view — form is already synced
        modelViewMode = "json";
        formDiv.classList.add("hidden");
        jsonDiv.classList.remove("hidden");
        toggleBtn.textContent = "Back to form";
    } else {
        // Switching to form view — parse JSON and rebuild
        const success = syncJsonToForm();
        if (!success) {
            // JSON is invalid, can't switch. The validation error is already visible.
            return;
        }
        modelViewMode = "form";
        jsonDiv.classList.add("hidden");
        formDiv.classList.remove("hidden");
        toggleBtn.textContent = "Edit as JSON";
    }
}
```

When in JSON view, the textarea's existing `onModelInput()` handler fires on edits, preserving the current debounced validation behavior.

---

## 11. Initialization Changes

The `DOMContentLoaded` handler is updated to populate `modelFormData` and build the form after state validation succeeds.

```javascript
document.addEventListener("DOMContentLoaded", async () => {
    const loadingStatus = document.getElementById("loading-status");
    await PyBridge.init((msg) => {
        loadingStatus.textContent = msg;
    });

    document.getElementById("loading-screen").classList.add("hidden");
    document.getElementById("app").classList.remove("hidden");

    // Load default state
    const defaultState = PyBridge.getDefaultState();
    document.getElementById("state-textarea").value = JSON.stringify(defaultState, null, 2);
    validateState();

    // Load default model — populate both form and textarea
    const defaultModel = PyBridge.getDefaultModelConfig();
    modelFormData = defaultModel;
    document.getElementById("model-textarea").value = JSON.stringify(defaultModel, null, 2);
    buildModelForm();
    validateModel();

    updateRunButtons();
    setupEventHandlers();
});
```

The `validateState()` function is extended: when state transitions from invalid to valid, or when the state content changes, it calls `buildModelForm()` to refresh the alliance/event dropdowns.

```javascript
// In validateState(), after stateIsValid = true:
if (result.ok) {
    // ... existing status/summary logic ...
    buildModelForm();   // <-- added
}
```

---

## 12. Event Handler Updates

#### `setupEventHandlers()` additions

```javascript
// View toggle
document.getElementById("model-view-toggle").addEventListener("click", toggleModelView);

// JSON textarea still gets direct input handler for JSON-view editing
document.getElementById("model-textarea").addEventListener("input", onModelInput);
```

#### Upload / CSV import integration

The existing file upload and CSV import handlers are updated to sync to the form after populating the textarea.

```javascript
// Model file upload — updated
document.getElementById("model-file-input").addEventListener("change", (e) => {
    readFileToTextarea(e.target.files[0], "model-textarea", () => {
        syncJsonToForm();   // <-- added: populate form from uploaded JSON
        validateModel();
    });
});

// CSV import — updated
reader.onload = () => {
    const result = PyBridge.importCsv(reader.result);
    if (result.ok) {
        document.getElementById("model-textarea").value =
            JSON.stringify(result.config, null, 2);
        syncJsonToForm();   // <-- added: populate form from imported CSV
        validateModel();
    } else {
        alert("CSV import error: " + result.error);
    }
};
```

---

## 13. CSS Additions

New styles added to `web/css/style.css`. Existing styles are unchanged.

```css
/* Model form sections */
.model-section {
    margin-bottom: 8px;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    padding: 0;
}

.model-section > summary {
    padding: 10px 12px;
    background: #f5f5f5;
    border-radius: 4px;
    font-weight: 600;
    cursor: pointer;
}

.model-section[open] > summary {
    border-bottom: 1px solid #e0e0e0;
    border-radius: 4px 4px 0 0;
}

.model-section > :not(summary) {
    padding: 12px;
}

/* Form grid for inline controls */
.form-grid {
    display: flex;
    gap: 24px;
    flex-wrap: wrap;
    padding: 12px;
}

.form-grid label {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 0.9em;
    font-weight: 500;
}

.form-grid select,
.form-grid input[type="number"] {
    padding: 4px 8px;
    border: 1px solid #ccc;
    border-radius: 4px;
    font-size: 13px;
}

/* Form tables */
.form-table {
    width: 100%;
    margin: 0;
}

.form-table select {
    width: 100%;
    padding: 3px 6px;
    border: 1px solid #ccc;
    border-radius: 3px;
    font-size: 13px;
}

/* Percentage inputs in outcome matrix */
.pct-input {
    width: 80px;
    padding: 3px 6px;
    border: 1px solid #ccc;
    border-radius: 3px;
    font-size: 13px;
    text-align: right;
}

/* Add/remove row buttons */
.add-row-btn {
    margin: 8px 12px;
    padding: 4px 12px;
    border: 1px dashed #aaa;
    border-radius: 4px;
    background: transparent;
    cursor: pointer;
    color: #555;
    font-size: 0.85em;
}

.add-row-btn:hover {
    background: #f0f0f0;
    border-color: #888;
}

.remove-row-btn {
    border: none;
    background: transparent;
    color: #999;
    cursor: pointer;
    font-size: 1.2em;
    padding: 2px 6px;
}

.remove-row-btn:hover {
    color: #dc3545;
}

/* Event subsections within accordion panels */
.event-subsection,
.day-subsection {
    margin-bottom: 12px;
    padding: 0 12px 12px;
}

.event-subsection h4,
.day-subsection h4 {
    margin: 8px 0;
    font-size: 0.95em;
    color: #555;
}

/* Help text */
.help-text {
    font-size: 0.85em;
    color: #888;
    margin: 4px 12px 8px;
}

.muted {
    color: #999;
    font-style: italic;
    padding: 12px;
}

/* View toggle button */
.toggle-btn {
    font-weight: 500;
}

/* Validation highlight on outcome rows */
.validation-error {
    background: #fff3f3;
}

.validation-error .pct-input {
    border-color: #dc3545;
}

.validation-inline {
    color: #dc3545;
    font-size: 0.85em;
    margin: 4px 12px;
}

/* State JSON toggle */
#state-json-toggle {
    margin-top: 8px;
}

#state-json-toggle summary {
    cursor: pointer;
    color: #555;
    font-size: 0.9em;
}
```

---

## File Changes Summary

| File | Change |
|------|--------|
| `web/index.html` | Restructure state section (wrap textarea in `<details>`), restructure model section (add `#model-form` div, view toggle button, move download button) |
| `web/js/app.js` | Add form state (`modelFormData`, `modelViewMode`), form builders (sections 5a-5g), dropdown helpers, `collectFormData()`, `syncFormToJson()`/`syncJsonToForm()`, `toggleModelView()`, `attachFormHandlers()`, `handleAddRow()`, update init and event handlers |
| `web/css/style.css` | Add accordion section styles, form-table/grid styles, percentage inputs, add/remove buttons, validation highlights, help text, view toggle, state JSON toggle |

No changes to Python files. No new files created.

---

## Backward Compatibility

All existing functionality is preserved. The raw JSON textarea remains accessible via the "Edit as JSON" toggle, and the state textarea is still fully functional inside its collapsible. Upload, CSV import, CSV template download, run single, and run Monte Carlo all work identically. Users who prefer raw JSON editing can toggle to it immediately and never interact with the form.
