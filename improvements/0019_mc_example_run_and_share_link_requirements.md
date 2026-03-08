# MC Example Run & Share Link — Requirements

## Goal

Two independent web UI improvements:

1. **MC Example Run** — Click a cell in the Monte Carlo tier distribution table
   to see one example simulation where that outcome occurred. Shows the full
   event-by-event breakdown in a modal overlay.

2. **Model-Only Share Link** — Shorten the share URL dramatically by encoding
   only the model config (not the game state). Move the share button to the
   model section and label it clearly.

---

## 1. MC Example Run

### 1a. Clickable tier distribution cells

Each percentage cell in the tier distribution table should be clickable when the
percentage is > 0%. On hover, show a pointer cursor and a tooltip (e.g. "Click
to see an example run"). Cells at 0% should not be clickable.

### 1b. Find a matching iteration

When a cell is clicked, filter `raw_results` (the per-iteration data already
returned by the MC bridge) to find all iterations where the clicked alliance
finished in the clicked tier. Pick one at random from the matching set.

### 1c. Run a single simulation with that seed

Use the selected iteration's seed to run a single simulation via the existing
`PyBridge.runSingle()` call. This produces the full event-by-event result.

### 1d. Display in a modal overlay

Show the single-run result in a modal/popup overlay on top of the MC results.
The modal should include:

- A header explaining the context (e.g. "Example: Ghst finishing T1 — seed 42")
- The full event-by-event breakdown (same format as a normal single run result)
- Final rankings and spice totals
- A close button (X) and click-outside-to-close behavior
- Scrollable content if the result is long

### 1e. Visual affordance on the table

Add subtle styling to indicate cells are clickable:

- Pointer cursor on non-zero cells
- Light background highlight on hover
- Optional: underline or dotted-underline on the percentage text

---

## 2. Model-Only Share Link

### 2a. Exclude game state from share URL

Change the share payload from `{state, model, seed, mcIterations, mcBaseSeed}`
to `{model, seed, mcIterations, mcBaseSeed}` only. Bump the version field to
`v: 2` so old v1 links still decode correctly (v1 includes state; v2 does not).

Expected URL reduction: ~3,100 chars → ~700 chars.

### 2b. Move share button to model section

Remove the share button from the run controls area. Add it to the model config
section header area, near the existing download/upload buttons. Label it
"Share Model" or "Copy Model Link".

### 2c. Label and notification

The button label and copy-success notification should make it clear that only the
model config is shared, not the game state. E.g.:

- Button: "Copy Model Link"
- Notification: "Model link copied — recipient will need the same game state loaded"

### 2d. Loading a v2 shared link

When a v2 hash is detected on page load:

1. Load the default game state (or keep whatever state is already loaded)
2. Apply the shared model config
3. Apply run parameters (seed, iterations, base seed)
4. Show a notification: "Model config loaded from shared link"

### 2e. Backward compatibility with v1 links

Existing v1 links (which include state) should continue to work. The decode
function should handle both versions:

- `v1:` — decode state + model + params, apply all
- `v2:` — decode model + params only, leave state as-is

---

## 3. Scope

### In scope
- `web/js/app.js` — Clickable tier cells, modal rendering, share link encoding
  (v2), share link decoding (v1 + v2), button relocation
- `web/css/style.css` — Modal overlay styles, clickable cell styles

### Out of scope
- Python engine or bridge changes (the existing `runSingle` and MC `raw_results`
  provide everything needed)
- CLI changes
- Compact/minified model encoding (standard JSON with deflate compression is
  sufficient at ~700 chars)
- Changes to the tier distribution table layout or columns

---

## 4. Testing (manual)

### MC Example Run
- Run MC — tier distribution table appears with percentage cells
- Hover a non-zero cell — pointer cursor and highlight appear
- Click a non-zero cell — modal opens showing a single-run example
- Verify the example run's final ranking matches the clicked tier for that
  alliance
- Close modal via X button — modal closes, MC results still visible
- Close modal via clicking outside — same behavior
- Click a 0% cell — nothing happens
- Scroll within modal if content is long

### Share Link
- Click "Copy Model Link" — notification says model link copied
- URL in address bar updates with v2 hash
- Paste URL in new tab — model config loads, default state is used, notification
  shown
- Verify old v1 links still load both state and model correctly
- Compare URL length: should be ~700 chars vs previous ~3,100
