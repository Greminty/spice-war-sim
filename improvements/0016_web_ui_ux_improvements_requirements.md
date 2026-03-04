# Web UI UX Improvements — Requirements

## Goal

Improve the web UI experience by defaulting Monte Carlo results to Top 10
filtering and adding collapsible sections to the game state editor panels,
with the alliances section collapsed by default to reduce visual clutter.

---

## 1. Default Result Filter to Top 10

### 1a. Change initial filter

The MC results filter (currently defaulting to "All") should default to
"Top 10" when results are first displayed.

### 1b. Preserve manual override

If the user explicitly selects a different filter (All, Top 3, Top 5), that
selection should be respected for subsequent re-renders until the page is
reloaded.

---

## 2. Collapsible Game State Sections

### 2a. Make sections collapsible

The game state editor area contains distinct UI sections (e.g. Alliances,
Event Schedule). Each section should be collapsible — clicking the section
heading toggles visibility of the section content.

### 2b. Default alliances to collapsed

The Alliances section should be collapsed by default on page load, since it
is the largest section and rarely needs manual editing.

### 2c. Event Schedule defaults expanded

The Event Schedule section should remain expanded by default. Other
sections (e.g. Edit JSON) should remain collapsed as they already are.

### 2d. Visual indicator

Each collapsible heading should include a toggle indicator (e.g. a
chevron/triangle) showing whether the section is expanded or collapsed.

---

## 3. Scope

### In scope
- `app.js` — Result filter default, collapsible section logic
- `style.css` — Collapsible toggle styling (if needed)
- `index.html` — Section heading markup changes (if needed)

### Out of scope
- Python engine changes
- CLI output changes
- Model config sections
- Changes to result table content or formatting

---

## 4. Testing (manual)

- Load page — alliances section is collapsed, other state sections expanded
- Click alliance heading — section expands; click again — collapses
- Run MC — results appear with Top 10 filter active
- Select "All" filter — results update; re-run MC — filter stays on "All"
- Reload page — filter resets to Top 10, alliances re-collapsed
