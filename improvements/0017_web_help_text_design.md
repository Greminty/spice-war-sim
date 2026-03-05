# Web Help Text — Design

## Overview

Add concise in-page help text and restructure the model config layout so new
users can understand the core workflow quickly. All changes are in `index.html`,
`app.js`, and `style.css` — no Python changes. Three key sections (General
Settings, Event Targets, Battle Outcomes) are promoted to the top level with a
blue accent; secondary sections are grouped in a collapsed Advanced Settings
wrapper. Help text is added in three tiers: a quick-start guide, short blurbs per
section, and collapsible deep-dives.

---

## 1. Quick-Start Guide

### 1a. `web/index.html` — new `<details>` block at top of `<main>`

```html
<details id="quick-start" class="quick-start" open>
    <summary>How to Use This Tool</summary>
    <ol>
        <li><strong>Set targeting strategies</strong> — In
            <strong>Event Targets</strong>, choose who each alliance attacks.
            Pin specific targets per event, or let an algorithm pick via
            <strong>General Settings</strong>.</li>
        <li><strong>Set battle outcome probabilities</strong> — In
            <strong>Battle Outcomes</strong>, enter the chance of full and
            partial success for key matchups. Leave blank to use the
            power-ratio heuristic.</li>
        <li><strong>Run</strong> — Click <em>Run</em> for a single
            deterministic result, or <em>Run Monte Carlo</em> for a
            statistical distribution across many iterations.</li>
    </ol>
    <p class="help-text">The default state is pre-loaded. You only need to
        configure the <strong>Model Config</strong> section — targeting and
        outcomes — then hit Run.</p>
</details>
```

### 1b. `web/js/app.js` — localStorage persistence (in `DOMContentLoaded`, after `setupEventHandlers()`)

```javascript
const quickStart = document.getElementById("quick-start");
if (quickStart) {
    if (localStorage.getItem("hideQuickStart") === "1") {
        quickStart.removeAttribute("open");
    }
    quickStart.addEventListener("toggle", () => {
        localStorage.setItem("hideQuickStart", quickStart.open ? "0" : "1");
    });
}
```

### 1c. `web/css/style.css` — quick-start styling

```css
.quick-start {
    background: #f0f7ff;
    border: 1px solid #cce0ff;
    border-radius: 6px;
    padding: 4px 16px;
    margin-bottom: 20px;
}

.quick-start summary {
    font-weight: 600;
    font-size: 1.1em;
    cursor: pointer;
    padding: 8px 0;
}

.quick-start ol {
    margin: 8px 0;
    padding-left: 24px;
}

.quick-start li {
    margin-bottom: 6px;
    line-height: 1.5;
}
```

---

## 2. Section Layout Restructure

### 2a. `web/js/app.js` — `buildModelForm()` reorder and wrap

Three key sections at top level, secondary sections in Advanced Settings:

```javascript
let html = "";
html += buildGeneralSettings();
html += buildEventTargets(alliances, events);
html += buildOutcomeMatrix(alliances, events);
html += '<details class="model-section advanced-settings">';
html += '<summary>Advanced Settings</summary>';
html += buildFactionTargeting(alliances);
html += buildDefaultTargets(alliances);
html += buildEventReinforcements(alliances, events);
html += buildDamageWeights(alliances);
html += '</details>';
```

### 2b. Default open/collapsed states

- **General Settings**: `<details class="model-section key-section">` (collapsed)
- **Event Targets**: `<details class="model-section key-section" open>` (open)
- **Battle Outcomes**: `<details class="model-section key-section" open>` (open)
- **Advanced Settings**: collapsed by default

### 2c. `web/css/style.css` — key-section and advanced-settings styles

```css
.model-section.key-section > summary {
    border-left: 3px solid #4a90d9;
    padding-left: 10px;
}

.advanced-settings {
    background: #fafafa;
}

.advanced-settings > summary {
    color: #666;
    font-size: 0.95em;
}

.advanced-settings > .model-section {
    border-color: #e8e8e8;
    margin: 8px 12px;
}
```

---

## 3. Section-Level Help Text

Short `.help-text` blurbs in each section builder, always visible.

### 3a. `buildGeneralSettings()` — strategy help and noise note

Strategy dropdown gets an inline explanation:

```javascript
<label>Global Targeting Strategy
    <span class="help-text">Fallback algorithm when no explicit target is set.
        <strong>Expected Value</strong> maximizes expected spice stolen;
        <strong>Highest Spice</strong> targets the richest defender.</span>
    <select ...>
```

MC-only note inserted before the three noise fields:

```javascript
<div class="help-text noise-note">These three settings only affect
    <strong>Monte Carlo</strong> runs. Set all to 0 for fully
    deterministic results.</div>
```

### 3b. `buildFactionTargeting()` — after `<summary>`

```javascript
<p class="help-text">Override the global strategy for a specific faction.
    Alliances in that faction use this algorithm unless they have an
    explicit target.</p>
```

### 3c. `buildDefaultTargets()` — after `<summary>`

```javascript
<p class="help-text">Pin a specific target or strategy for an alliance
    across all events. Overridden by any event-level target below.</p>
```

### 3d. `buildEventTargets()` — after `<summary>`

```javascript
<p class="help-text">Pin a target for a specific alliance in a specific
    event. Highest priority — overrides default targets and
    faction/global strategies.</p>
```

### 3e. `buildOutcomeMatrix()` — section-level help replacing per-day text

Remove the per-day "Lookup priority" paragraphs. Add section-level text:

```javascript
<p class="help-text">Set the probability (0–100) of <strong>full success</strong>
    and optionally <strong>partial success</strong> for each
    attacker–defender pairing and day. If you only enter full success,
    partial is derived automatically. Fail is implicit (100% minus the
    others). Leave fields blank to use the power-ratio heuristic
    (shown as placeholder values).</p>
```

---

## 4. Targeting Resolution Deep-Dive

### 4a. `buildEventTargets()` — collapsible block appended before closing `</details>`

```javascript
<details class="deep-dive">
    <summary>How targeting resolution works</summary>
    <ol>
        <li><strong>Event target</strong> — checked first. If set for
            this alliance + event, use it.</li>
        <li><strong>Default target</strong> — checked second. If set
            for this alliance, use it.</li>
        <li><strong>Faction strategy</strong> — checked third. Uses the
            faction's algorithm if configured.</li>
        <li><strong>Global strategy</strong> — final fallback.</li>
    </ol>
    <p class="help-text">Within each algorithm, alliances choose targets
        in descending power order. Ties break by higher spice, then
        alphabetical ID.</p>
</details>
```

---

## 5. Battle Outcomes Deep-Dive

### 5a. `buildOutcomeMatrix()` — collapsible block appended before closing `</details>`

```javascript
<details class="deep-dive">
    <summary>How battle outcomes and lookup priority work</summary>
    <ul>
        <li><strong>Full success</strong> — all buildings destroyed.
            Theft up to 30% of defender's spice.</li>
        <li><strong>Partial success</strong> — side buildings only.
            Lower theft (5–20%).</li>
        <li><strong>Custom</strong> — you specify the exact theft
            percentage directly.</li>
        <li><strong>Fail</strong> (implicit) — the remaining probability
            after full, partial, and custom. No buildings destroyed, 0%
            theft.</li>
    </ul>
    <p class="help-text">When multiple attackers hit the same defender,
        stolen spice is split by damage weights.</p>
    <p class="help-text"><strong>Lookup priority:</strong> exact pairing → attacker
        wildcard (*) → defender wildcard (*) → heuristic fallback.
        Wildcards let you set a default for all opponents without listing
        every pairing.</p>
</details>
```

---

## 6. Run Controls Help

### 6a. `web/index.html` — after `<h2>Run Simulation</h2>`, before first `run-group`

```html
<p class="help-text"><strong>Single Run</strong> — one simulation with a
    fixed seed (leave blank for random). Useful for inspecting a specific
    scenario event-by-event.<br>
    <strong>Monte Carlo</strong> — runs many iterations with randomized
    targeting and outcomes. Shows tier probabilities and spice distributions.
    1000 iterations is a good default.</p>
```

---

## 7. Results Help

### 7a. `renderSingleResults()` — prepend to results HTML

```javascript
let html = `<p class="help-text">Expand each event to see targeting decisions,
    battle outcomes, and spice transfers. Rank arrows show movement from the
    previous event.</p>`;
```

### 7b. `renderMonteCarloResults()` — prepend to results HTML

```javascript
let html = `<p class="help-text"><strong>Tier distribution</strong> shows the
    % chance each alliance finishes in each tier (T1 = rank 1, T2 = ranks 2–3,
    T3 = 4–10, T4 = 11–20, T5 = 21+). The <strong>targeting matrix</strong>
    below shows how often each attacker targeted each defender across all
    iterations.</p>`;
```

---

## 8. Deep-Dive Styling

### 8a. `web/css/style.css`

```css
.deep-dive {
    margin: 12px 12px 8px;
    padding: 0 12px;
    border-left: 3px solid #ddd;
    border: none;
}

.deep-dive summary {
    font-size: 0.9em;
    color: #666;
    font-weight: 500;
    cursor: pointer;
    padding: 4px 0;
}

.deep-dive ol,
.deep-dive ul {
    margin: 8px 0;
    padding-left: 20px;
    font-size: 0.9em;
    line-height: 1.6;
}

.noise-note {
    width: 100%;
    margin-top: 8px;
}
```

---

## Files Changed

| File | Changes |
|------|---------|
| `web/index.html` | Add quick-start guide at top of `<main>`; add run controls help text |
| `web/js/app.js` | Reorder sections in `buildModelForm()` with Advanced Settings wrapper; add `key-section` class to General Settings, Event Targets, Battle Outcomes; add localStorage for quick-start; add help text in all section builders; remove per-day lookup priority text; add targeting and outcomes deep-dives; add results help text; rename "Battle Outcome Matrix" to "Battle Outcomes" |
| `web/css/style.css` | Add `.quick-start`, `.key-section`, `.advanced-settings`, `.deep-dive`, `.noise-note` styles |

---

## Implementation Order

| Step | Area | Files | Complexity |
|------|------|-------|------------|
| 1 | Quick-start guide | `index.html`, `app.js`, `style.css` | Low |
| 2 | Section restructure + highlighting | `app.js`, `style.css` | Low |
| 3 | Section-level help text | `app.js` | Low |
| 4 | Targeting deep-dive | `app.js` | Low |
| 5 | Outcome deep-dive | `app.js` | Low |
| 6 | Run controls help | `index.html` | Trivial |
| 7 | Results help | `app.js` | Trivial |

---

## Testing (manual)

- Load page — quick-start guide is open with 3-step workflow referencing sections by name
- Collapse quick-start, reload — stays collapsed (localStorage)
- Clear localStorage, reload — opens again
- Model Config — General Settings collapsed, Event Targets and Battle Outcomes open
- Key sections have blue left-border accent on summary bar
- Advanced Settings collapsed, containing Faction Targeting, Default Targets, Event Reinforcements, Damage Weights
- Each section has a short help blurb below the heading
- General Settings — noise fields have "Monte Carlo only" note
- Event Targets — "How targeting resolution works" collapsed; expands to show 4-level priority
- Battle Outcomes — section-level help; "How battle outcomes and lookup priority work" collapsed; expands to show outcome definitions and lookup priority
- Run controls — help text distinguishes Single Run vs Monte Carlo
- Run single — results show event navigation help text
- Run MC — results show tier/targeting matrix help text
