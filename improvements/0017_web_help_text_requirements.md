# Web Help Text — Requirements

## Goal

Add concise, scannable in-page documentation so a new user can understand the
core workflow and key concepts within a couple of minutes, then start
experimenting. Prioritize **targeting strategies** and **battle outcome
probabilities** — the two things users actually tune when analyzing scenarios.

Keep secondary topics (editing base state, reinforcement, engine internals)
minimal or hidden behind expandable UI. Group non-essential model config sections
into a collapsed Advanced Settings wrapper.

---

## 1. Quick-Start Guide (collapsible, top of page)

### 1a. Add collapsible guide block

A `<details>` block above the Game State section, **open by default on first
visit** (localStorage flag to remember collapse). Title: **"How to Use This
Tool"** or similar.

### 1b. Three-step workflow content

Content — three numbered steps referencing sections by name:

1. **Set targeting strategies** — In **Event Targets**, choose who each alliance
   attacks. Pin specific targets per event, or let an algorithm pick via
   **General Settings**.
2. **Set battle outcome probabilities** — In **Battle Outcomes**, enter the
   chance of full and partial success for key matchups. Leave blank to use the
   power-ratio heuristic.
3. **Run** — Click *Run* for a single deterministic result, or *Run Monte Carlo*
   for a statistical distribution across many iterations.

### 1c. Closing note

Below the steps, a single short paragraph:

> The default state is pre-loaded. You only need to configure the **Model
> Config** section — targeting and outcomes — then hit Run.

Keep the entire block under ~120 words.

---

## 2. Section Layout & Highlighting

### 2a. Key sections at top level

Three primary sections appear at the top level of Model Config, with a blue
left-border accent on their summary bar:

- **General Settings** (collapsed by default)
- **Event Targets** (open by default)
- **Battle Outcomes** (open by default)

### 2b. Advanced Settings wrapper

Remaining sections grouped in a collapsed `<details>` accordion titled
**Advanced Settings**:

- Faction Targeting Strategy
- Default Targets
- Event Reinforcements
- Damage Weights

---

## 3. Section-Level Help (per panel)

Each Model Config subsection gets a short help blurb (1–3 sentences) using the
existing `.help-text` style. Always visible, placed below the section heading.

### 3a. Targeting Strategy (General Settings)

> Fallback algorithm when no explicit target is set. **Expected Value** maximizes
> expected spice stolen; **Highest Spice** targets the richest defender.

### 3b. Noise / Temperature Settings (General Settings)

> These three settings only affect **Monte Carlo** runs. Set all to 0 for fully
> deterministic results.

### 3c. Faction Targeting Strategy

> Override the global strategy for a specific faction. Alliances in that faction
> use this algorithm unless they have an explicit target.

### 3d. Default Targets

> Pin a specific target or strategy for an alliance across all events. Overridden
> by any event-level target.

### 3e. Event Targets

> Pin a target for a specific alliance in a specific event. Highest priority —
> overrides default targets and faction/global strategies.

### 3f. Battle Outcomes

> Set the probability (0–100) of **full success** and optionally **partial
> success** for each attacker–defender pairing and day. If you only enter full
> success, partial is derived automatically. Fail is implicit (100% minus the
> others). Leave fields blank to use the power-ratio heuristic (shown as
> placeholder values).

---

## 4. Targeting Resolution — Collapsible Deep-Dive

### 4a. Add collapsible block

Inside Event Targets, add a collapsible `<details>` block titled **"How
targeting resolution works"** (collapsed by default).

### 4b. Priority chain content

1. **Event target** — checked first. If set for this alliance + event, use it.
2. **Default target** — checked second. If set for this alliance, use it.
3. **Faction strategy** — checked third. Uses the faction's algorithm if
   configured.
4. **Global strategy** — final fallback.

> Within each algorithm, alliances choose targets in descending power order. Ties
> break by higher spice, then alphabetical ID.

---

## 5. Battle Outcomes — Collapsible Deep-Dive

### 5a. Add collapsible block

Inside Battle Outcomes, add a collapsible `<details>` block titled **"How battle
outcomes and lookup priority work"** (collapsed by default).

### 5b. Outcome level content

> **Full success** — all buildings destroyed. Theft up to 30% of defender's
> spice.
>
> **Partial success** — side buildings only. Lower theft (5–20%).
>
> **Custom** — you specify the exact theft percentage directly.
>
> **Fail** (implicit) — the remaining probability after full, partial, and
> custom. No buildings destroyed, 0% theft.
>
> When multiple attackers hit the same defender, stolen spice is split by damage
> weights.

### 5c. Lookup priority

> **Lookup priority:** exact pairing → attacker wildcard (\*) → defender
> wildcard (\*) → heuristic fallback. Wildcards let you set a default for all
> opponents without listing every pairing.

---

## 6. Run Controls — Inline Help

### 6a. Add help text above run buttons

> **Single Run** — one simulation with a fixed seed (leave blank for random).
> Useful for inspecting a specific scenario event-by-event.
>
> **Monte Carlo** — runs many iterations with randomized targeting and outcomes.
> Shows tier probabilities and spice distributions. 1000 iterations is a good
> default.

---

## 7. Results — Inline Help

### 7a. Single run results help

> Expand each event to see targeting decisions, battle outcomes, and spice
> transfers. Rank arrows show movement from the previous event.

### 7b. Monte Carlo results help

> **Tier distribution** shows the % chance each alliance finishes in each tier
> (T1 = rank 1, T2 = ranks 2–3, T3 = 4–10, T4 = 11–20, T5 = 21+). The
> **targeting matrix** shows how often each attacker targeted each defender
> across all iterations.

---

## 8. Scope

### In scope
- `web/js/app.js` — Help text, section reordering, Advanced Settings wrapper,
  collapsible deep-dives, localStorage, key-section highlighting
- `web/css/style.css` — Quick-start, key-section, advanced-settings, deep-dive
  styles
- `web/index.html` — Quick-start guide, run controls help text

### Out of scope
- Python engine or bridge changes
- CLI output changes
- Help text for: game state editor, CSV import/export, share links
