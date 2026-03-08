# MC Example Run & Share Link — Design

## Overview

Two independent changes to `app.js`, `style.css`, and `index.html` — no Python
changes. Feature 1 makes tier distribution cells clickable to show a full
single-run example in a modal. Feature 2 switches the share link to model-only
encoding (v2) and moves the button to the model editor section.

---

## 1. MC Example Run

### 1a. Store raw results reference

The MC result already includes `raw_results` (per-iteration seed + rankings).
Store it alongside `lastResult` so the click handler can access it.

`web/js/app.js` — no change needed; `lastResult` already holds the full MC
result including `raw_results`.

### 1b. Clickable tier cells — `renderMonteCarloResults()` (line ~1477)

Replace the plain `<td>` cells in the tier distribution table with clickable
elements. Add a `data-aid` and `data-tier` attribute to each non-zero cell,
and a `tier-cell-clickable` CSS class:

```javascript
for (let t = 1; t <= 5; t++) {
    const frac = parseFloat(dist[String(t)] || 0);
    const pct = (frac * 100).toFixed(1);
    if (frac > 0) {
        html += `<td class="tier-cell-clickable" data-aid="${esc(aid)}" data-tier="${t}">${pct}%</td>`;
    } else {
        html += `<td>${pct}%</td>`;
    }
}
```

### 1c. Click handler — delegated event listener

After setting `container.innerHTML` in `renderMonteCarloResults()`, attach a
delegated click handler on the results container (or use a single persistent
listener). When a `.tier-cell-clickable` cell is clicked:

1. Read `data-aid` and `data-tier` from the clicked element
2. Filter `lastResult.raw_results` to find iterations where
   `rankings[aid] === tier`
3. Pick one at random from the matching set
4. Call `PyBridge.runSingle(stateDict, modelDict, seed)` with that iteration's
   seed
5. Render the result in a modal via `showExampleRunModal(aid, tier, singleResult)`

```javascript
container.addEventListener("click", async (e) => {
    const cell = e.target.closest(".tier-cell-clickable");
    if (!cell || !lastResult || !lastResult.raw_results) return;

    const aid = cell.dataset.aid;
    const tier = parseInt(cell.dataset.tier, 10);

    const matching = lastResult.raw_results.filter(r => r.rankings[aid] === tier);
    if (!matching.length) return;

    const pick = matching[Math.floor(Math.random() * matching.length)];

    const stateDict = JSON.parse(document.getElementById("state-textarea").value);
    const modelDict = JSON.parse(document.getElementById("model-textarea").value);
    const result = await PyBridge.runSingle(stateDict, modelDict, pick.seed);
    if (!result.ok) return;

    showExampleRunModal(aid, tier, result);
});
```

### 1d. Modal rendering — `showExampleRunModal(aid, tier, result)`

New function that creates a modal overlay. Reuses the existing
`renderEventDetail()` helper (lines ~1340–1428) to build the event-by-event
HTML, and the final rankings table from `renderSingleResults()`.

```javascript
function showExampleRunModal(aid, tier, result) {
    // Remove any existing modal
    const existing = document.getElementById("example-run-modal");
    if (existing) existing.remove();

    const factions = getAllianceFaction();
    const factionName = factions[aid] || "";

    const overlay = document.createElement("div");
    overlay.id = "example-run-modal";
    overlay.className = "modal-overlay";

    let html = '<div class="modal-content">';
    html += '<button class="modal-close">&times;</button>';
    html += `<h2>Example: ${esc(aid)} finishing T${tier} — seed ${result.seed}</h2>`;
    if (factionName) {
        html += `<p class="help-text">Faction: ${esc(factionName)}</p>`;
    }

    // Final rankings table (same structure as renderSingleResults)
    const entries = Object.entries(result.final_spice)
        .map(([id, spice]) => ({ id, spice, tier: result.rankings[id] }));
    entries.sort((a, b) => a.tier - b.tier || b.spice - a.spice);

    html += "<h3>Final Rankings</h3>";
    html += "<table><tr><th>Faction</th><th>Alliance</th><th>Rank</th><th>Tier</th><th>Final Spice</th></tr>";
    for (const e of entries) {
        const highlight = e.id === aid ? ' style="background:#fffde7"' : "";
        html += `<tr${highlight}>
            <td>${esc(factions[e.id] || "")}</td>
            <td>${esc(e.id)}</td>
            <td>${e.tier <= 1 ? 1 : "..."}</td>
            <td>T${e.tier}</td>
            <td>${e.spice.toLocaleString()}</td>
        </tr>`;
    }
    html += "</table>";

    // Event-by-event breakdown (reuse renderEventDetail)
    html += "<h3>Event History</h3>";
    // Render with no filter (show all alliances in the example)
    for (let i = 0; i < result.event_history.length; i++) {
        const event = result.event_history[i];
        html += `<details><summary>Event ${event.event_number} — ${esc(event.attacker_faction)} attacks (${esc(event.day)})</summary>`;
        html += renderEventDetail(event, factions, null);
        html += "</details>";
    }

    html += "</div>";
    overlay.innerHTML = html;
    document.body.appendChild(overlay);

    // Close handlers
    overlay.querySelector(".modal-close").addEventListener("click", () => overlay.remove());
    overlay.addEventListener("click", (e) => {
        if (e.target === overlay) overlay.remove();
    });
}
```

Note: `renderEventDetail()` already exists as a helper that builds the
targeting table, battles, and spice summary for a single event (lines
~1340–1428). The modal calls it with `allowed = null` to show all alliances
in the example context, regardless of the current filter.

### 1e. Rank display in modal

The final rankings table in the modal should show actual rank numbers (not
tier). Compute ranks from `result.final_spice` using the existing
`computeRanks()` helper:

```javascript
const ranks = computeRanks(result.final_spice);
// In the table row:
html += `<td>${ranks[e.id]}</td>`;  // instead of tier
```

### 1f. Filtering the modal rankings

Since the modal shows a specific example, apply the current `resultFilter`
to keep the table manageable (many alliances). Use `getFilteredAlliances()`
to filter.

---

## 2. Model-Only Share Link

### 2a. New encoding function — `encodeModelToHash()` (replaces `encodeConfigToHash`)

```javascript
async function encodeModelToHash() {
    const payload = {
        v: 2,
        model: JSON.parse(document.getElementById("model-textarea").value),
        seed: document.getElementById("single-seed").value || null,
        mcIterations: parseInt(document.getElementById("mc-iterations").value, 10) || 1000,
        mcBaseSeed: parseInt(document.getElementById("mc-base-seed").value, 10) || 0,
    };

    const json = JSON.stringify(payload);
    const bytes = new TextEncoder().encode(json);

    const cs = new CompressionStream("deflate");
    const writer = cs.writable.getWriter();
    writer.write(bytes);
    writer.close();

    const compressed = await new Response(cs.readable).arrayBuffer();
    const compressedBytes = new Uint8Array(compressed);

    let base64 = btoa(String.fromCharCode(...compressedBytes));
    base64 = base64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

    return `v2:${base64}`;
}
```

### 2b. Update `shareConfig()` (line ~1699)

Replace `encodeConfigToHash()` call with `encodeModelToHash()`. Update the
success notification:

```javascript
async function shareConfig() {
    try {
        const hash = await encodeModelToHash();
        const url = `${window.location.origin}${window.location.pathname}#${hash}`;

        if (url.length > 8000) {
            showNotification("Configuration too large to share via URL", "error");
            return;
        }

        window.location.hash = hash;
        await navigator.clipboard.writeText(url);
        showNotification("Model link copied — recipient needs the same game state loaded");
    } catch (e) {
        showNotification("Failed to generate share link: " + e.message, "error");
    }
}
```

### 2c. Update `decodeHashToConfig()` — handle v1 and v2 (line ~1679)

The existing function checks for `v1:` prefix. Extend to also handle `v2:`:

```javascript
async function decodeHashToConfig(hash) {
    let version, base64url;
    if (hash.startsWith("v2:")) {
        version = 2;
        base64url = hash.slice(3);
    } else if (hash.startsWith("v1:")) {
        version = 1;
        base64url = hash.slice(3);
    } else {
        return null;
    }

    let base64 = base64url.replace(/-/g, "+").replace(/_/g, "/");
    while (base64.length % 4) base64 += "=";

    const compressed = Uint8Array.from(atob(base64), c => c.charCodeAt(0));

    const ds = new DecompressionStream("deflate");
    const writer = ds.writable.getWriter();
    writer.write(compressed);
    writer.close();

    const decompressed = await new Response(ds.readable).arrayBuffer();
    const json = new TextDecoder().decode(decompressed);

    const config = JSON.parse(json);
    config.v = version;  // Ensure version is set from prefix
    return config;
}
```

### 2d. Update hash loading logic — `DOMContentLoaded` (line ~61)

Handle both v1 (state + model) and v2 (model only):

```javascript
const hash = window.location.hash.slice(1);
if (hash) {
    try {
        const config = await decodeHashToConfig(hash);
        if (config) {
            if (config.v === 1 && config.state) {
                // v1: load state + model
                document.getElementById("state-textarea").value = JSON.stringify(config.state, null, 2);
                validateState();
            }
            // v1 and v2: load model + params
            if (config.model) {
                modelFormData = config.model;
                document.getElementById("model-textarea").value = JSON.stringify(config.model, null, 2);
                buildModelForm();
                validateModel();
            }
            if (config.seed != null) {
                document.getElementById("single-seed").value = config.seed;
            }
            document.getElementById("mc-iterations").value = config.mcIterations || 1000;
            document.getElementById("mc-base-seed").value = config.mcBaseSeed || 0;

            const msg = config.v === 1
                ? "Configuration loaded from shared URL"
                : "Model config loaded from shared link";
            showNotification(msg);
        }
    } catch {
        // Invalid hash — silently ignore
    }
}
```

### 2e. Move share button — `web/index.html`

Remove from run-controls section (line 104):

```html
<!-- DELETE: <button id="share-btn">Copy Share Link</button> -->
```

Add to model editor controls (after line 70, alongside other buttons):

```html
<button id="share-btn">Copy Model Link</button>
```

### 2f. Remove old `encodeConfigToHash()`

Delete the `encodeConfigToHash()` function (lines 1652–1677) since it's
replaced by `encodeModelToHash()`.

---

## 3. CSS — Modal Styles

### 3a. `web/css/style.css` — modal overlay and content

```css
/* Modal overlay */
.modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.5);
    z-index: 2000;
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding: 32px 16px;
    overflow-y: auto;
}

.modal-content {
    background: #fff;
    border-radius: 8px;
    padding: 24px;
    max-width: 900px;
    width: 100%;
    position: relative;
    max-height: calc(100vh - 64px);
    overflow-y: auto;
}

.modal-close {
    position: absolute;
    top: 12px;
    right: 16px;
    background: none;
    border: none;
    font-size: 1.5em;
    cursor: pointer;
    color: #666;
    padding: 4px 8px;
    line-height: 1;
}

.modal-close:hover {
    color: #333;
}
```

### 3b. `web/css/style.css` — clickable tier cells

```css
/* Clickable tier distribution cells */
.tier-cell-clickable {
    cursor: pointer;
    position: relative;
}

.tier-cell-clickable:hover {
    background: #e8f0fe;
}
```

---

## 4. CSS — Share button in model section

### 4a. `web/css/style.css`

The `#share-btn` selector in the existing button styles (lines 94–112) already
covers `.editor-controls button`, so no new CSS is needed — the share button
will inherit the same styling as the other model editor buttons once it's moved
to `.editor-controls`.

Remove `#share-btn` from the existing selector lists (lines 97 and 110) since
it will now be covered by `.editor-controls button`.

---

## Files Changed

| File | Changes |
|------|---------|
| `web/js/app.js` | Clickable tier cells in `renderMonteCarloResults()`; click handler with `raw_results` filtering; `showExampleRunModal()` function; replace `encodeConfigToHash()` with `encodeModelToHash()`; update `decodeHashToConfig()` for v1/v2; update hash loading in `DOMContentLoaded`; update `shareConfig()` notification text |
| `web/css/style.css` | Add `.modal-overlay`, `.modal-content`, `.modal-close` styles; add `.tier-cell-clickable` styles; clean up `#share-btn` from selector lists |
| `web/index.html` | Move `#share-btn` from run-controls to model editor controls; change label to "Copy Model Link" |

---

## Implementation Order

| Step | Area | Files | Complexity |
|------|------|-------|------------|
| 1 | Modal CSS | `style.css` | Low |
| 2 | Clickable tier cells + click handler | `app.js` | Medium |
| 3 | `showExampleRunModal()` | `app.js` | Medium |
| 4 | v2 share encoding + decoding | `app.js` | Low |
| 5 | Move share button + relabel | `index.html`, `style.css` | Trivial |

Steps 1–3 (MC example run) and 4–5 (share link) are independent and can be
done in either order.

---

## Testing (manual)

### MC Example Run
- Run MC with 1000 iterations
- Hover a non-zero tier cell — pointer cursor, blue highlight
- Hover a 0% cell — no cursor change, no highlight
- Click a non-zero cell — modal opens after brief pause (single run executes)
- Modal header shows alliance ID, tier, and seed
- Modal contains final rankings table with the clicked alliance highlighted
- The clicked alliance's rank in the example matches the tier that was clicked
- Event history shows expandable event details
- Close via X button — modal removed
- Close via clicking backdrop — modal removed
- Click another cell — new modal replaces any existing one

### Share Link
- "Copy Model Link" button appears in model editor controls (not run controls)
- Click button — notification says "Model link copied — recipient needs the
  same game state loaded"
- URL hash starts with `v2:`
- Open the URL in a new tab — model loads, default game state is used,
  notification says "Model config loaded from shared link"
- Test a saved v1 URL — still loads both state and model correctly
- Inspect URL length — should be ~700 chars total
