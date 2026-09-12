# Team Reference: Frontend Architecture & UI Component Map

*For whoever is styling, extending, or debugging the UI.*

> **A note on file layout before you go looking for files by these names.**
> The components below are documented individually because each has a distinct
> job, but they are not all one-file-per-component on disk. Several small,
> tightly related presentational pieces are grouped into two files
> (`Charts.jsx`, `Panels.jsx`) because they share imports and are always
> touched together; the larger, independently-owned pieces (`EvidenceDrawer`)
> get their own file. Every heading below states its real source file. If your
> team prefers strict one-file-per-component as you divide up styling work,
> splitting these further is a pure mechanical move — nothing in this doc
> depends on the current grouping.

---

## Directory layout

```
frontend/
├── index.html
├── vite.config.js          proxies /api -> http://127.0.0.1:8000 in dev
└── src/
    ├── main.jsx            React root
    ├── index.css           the ENTIRE design system — see note below
    ├── App.jsx             app shell, data fetching, state, the ranked board
    ├── lib/
    │   └── rescore.js      client-side mirror of backend/core/fusion.py::score()
    └── components/
        ├── Charts.jsx         ScoreRadar, GapScatter, ContribBar, StatusBar
        ├── EvidenceDrawer.jsx the slide-out candidate panel
        └── Panels.jsx         WeightRail, InsightPanel, BiasPanel, ChatDock,
                                DiffPanel, LoadingBoard
```

**`index.css` is the design system.** Every color, radius, easing curve and
font is a CSS custom property declared once at the top of the file (`:root`).
There is no Tailwind and no CSS-in-JS — retheming the entire app means editing
that token block, not hunting through components. The four status colors
(`--matched`, `--inferred`, `--weak`, `--missing`) are used identically across
cards, chips, the radar, the scatter, and the diff view; changing one changes
the app's entire visual legend, so treat them as load-bearing, not decorative.

**State lives in `App.jsx`, not in a store.** There's no Redux/Zustand/Context
— the app has one screen and one shared dataset (`payload`), so `useState` in
the top-level component plus prop-drilling is simpler and has fewer moving
parts than a state library would be. If the app grows a second screen, that's
the point at which to reconsider.

---

## `App.jsx` — shell, data flow, and the ranked board

Holds all top-level state:

| State | Purpose |
|---|---|
| `payload` | the full response from `/api/analyze` (or `null` before first load) |
| `loading` / `error` | request lifecycle |
| `alpha` / `gate` | the two ranking controls; **owned here**, passed down |
| `selected` | the candidate whose drawer is open (or `null`) |
| `compare` | up to two `doc_id`s selected for the diff panel |

**The ranking itself is computed here**, not fetched:

```js
const candidates = useMemo(
  () => rescore(payload.candidates, alpha, gate, payload.meta),
  [payload, alpha, gate],
)
```

This is the entire reason the α slider is instant — moving it changes `alpha`,
React recomputes `candidates` locally via `rescore()` (see below), and nothing
touches the network. The backend's `/api/analyze` response already carries
every alpha-independent sub-score needed to do this.

**The ranked board is rendered inline here**, not as a separate
`CandidateBoard` component — each card is a `motion.article` from Framer
Motion with `layoutId={c.doc_id}`. When `candidates` re-sorts after an `alpha`
change, Framer Motion's FLIP animation (`layout` prop + a spring transition)
animates each card smoothly to its new position rather than snapping. A card
shows: rank, name, a `StatusBar` mini-bar (from `Charts.jsx`), a flag badge if
applicable, required-skill coverage %, a parse-quality warning if under 0.5,
a "compare" toggle button, and the score with its K/M sub-scores.

Two entry points load data: `loadSample()` (POSTs to
`/api/analyze/sample`, which the backend resolves against `data/` if the real
corpus is present, else the synthetic fixtures) and `upload(files)` (builds a
`FormData`, guesses which uploaded file is the JD by filename, POSTs to
`/api/analyze`).

---

## `lib/rescore.js` — the client-side scoring engine

This file's only job is to compute **exactly** what
`backend/core/fusion.py::score()` computes, in JavaScript, so the ranking never
needs a round trip.

```js
export function channelK(p, meta)        // mirrors fusion.channel_k()
export function channelM(p, meta)        // mirrors fusion.channel_m()
export function gateMultiplier(p, on, meta)  // mirrors fusion.gate_multiplier()
export function rescore(candidates, alpha, gate, meta)  // mirrors fusion.score()
export function poolStats(candidates)    // spread/min/max/mean for the top bar
```

`meta` (from the API payload) carries the engine's own tuning weights
(`k_weight_bm25`, `m_weight_docsim`, `gate_floor`, `gate_span`) rather than
hard-coding them here — if `backend/config.py` changes those values, the
frontend picks them up automatically on the next analysis with **zero code
changes**, because the formula shape (not the constants) is what's mirrored.

The one subtlety: `round()` at the bottom re-implements Python's
banker's-rounding behavior (round-half-to-even) instead of JavaScript's
default round-half-away-from-zero, specifically so the two languages can't
disagree on an exact `.5` boundary. `scripts/check_parity.py` runs this file
under Node and diffs its output against the real Python engine at
α ∈ {0, 0.25, 0.5, 0.75, 1} — the check requires agreement to **1e-9**, and
currently passes with **zero** measured difference at every value.

**If you ever change the scoring formula, change it in both files, in the same
commit.** Nothing will error if you don't — the UI will just silently disagree
with the backend. Run `check_parity.py` after any change to either file.

---

## `components/Charts.jsx` — hand-drawn SVG, no charting library

> **Deviation from the original design brief, noted honestly:** the Phase 1
> plan called for a Recharts-based scatter plot. The shipped implementation
> uses plain inline SVG instead — no charting dependency was added. This keeps
> every chart color pinned to the same CSS theme tokens as the rest of the app
> (a library would fight that), keeps the bundle smaller, and made the
> dashed-guideline / click-to-select interactions on the scatter plot trivial
> to hand-tune. If the team wants Recharts' richer interaction set later
> (tooltips, zoom, legends), that's a drop-in replacement for this file only —
> nothing else in the app depends on how these are drawn internally.

### `ScoreRadar({ candidate, size = 250 })`
Groups the candidate's skill cells by `cluster` (Frontend/Backend/Database/…),
computes a weighted coverage value per cluster, and draws a radar polygon.
Returns `null` if there are fewer than 3 clusters (a radar needs at least a
triangle to be legible).

### `GapScatter({ candidates, selectedId, onSelect, width, height })`
One `<circle>` per candidate: x = score, y = `primitives.gap_density`, color =
flag class, radius scaled by evidence volume (`n_chunks`), selected candidate
gets a larger stroked circle. `onSelect(candidate)` fires on click — wired to
`setSelected` in `App.jsx` so clicking a point opens that candidate's drawer.

### `ContribBar({ candidate, alpha })`
The two-segment bar in the evidence drawer showing `alpha * k_score` versus
`(1-alpha) * m_score` as proportional widths, with the percentage printed
inside each segment once it's wide enough to hold text.

### `StatusBar({ candidate })`
The thin mini-bar under each card's name — proportional segments for
MATCHED/INFERRED/WEAK/MISSING weight, using the same four status colors as
everywhere else.

---

## `components/EvidenceDrawer.jsx`

**Props:** `candidate` (or `null` to render nothing), `alpha`, `poolSize`,
`onClose`.

The single most detail-dense component in the app. Its job is turning the
evidence matrix for one candidate into something a recruiter can *check*, not
just read:

- Builds the resume display by walking `candidate.resume_text` and splicing in
  `<mark>` tags at every skill cell's `[start, end)` character span, merging
  overlapping spans (several skills often cite the same sentence).
- Every skill chip is a `<button>`; clicking one calls `jumpTo(skillId)`,
  which sets an `active` skill id (triggering a CSS pulse animation on the
  matching `<mark>`) and calls `scrollIntoView` on it. Chips with no evidence
  span (`start < 0`) render `disabled` — they can't lie about having a
  citation.
- Escape key and a click on the scrim both close it (`onClose`), handled via a
  `keydown` listener in a `useEffect`.
- Renders `ScoreRadar` and `ContribBar` from `Charts.jsx` inline.

Framer Motion's `AnimatePresence` handles the slide-in/slide-out and the scrim
fade; the drawer itself is a plain `motion.aside` with a spring transition.

---

## `components/Panels.jsx`

### `WeightRail({ alpha, setAlpha, gate, setGate, meta, skills })`
The left-rail control panel: the α `<input type="range">` (inverted internally
so the visual left side means "keyword" — see the source comment), the
must-have gate toggle, the job's required/preferred skill chip lists, and an
"Engine" info block (semantic backend name, device, pool size, elapsed time,
τ calibration band). This is the component your Member 1 (frontend/UX) will
touch most when polishing the primary interaction of the demo.

### `InsightPanel({ candidates, selected, onSelect, bias, meta })`
Composes the right column: renders `GapScatter`, a list of flagged
Hidden-Gem/Surface-Match candidates as clickable summary cards, and the
`BiasPanel`. Purely a layout/composition component — no scoring logic lives
here.

### `BiasPanel({ bias })`
Renders the JD's inclusivity score (color-coded: ≥70 green, ≥40 amber, else
red), a one-line summary, and a collapsible list of findings, each showing
severity, the flagged text, the reason, the measured impact (when the finding
came from the counterfactual simulation rather than the lexicon scan), and a
suggested fix.

### `ChatDock({ candidates, alpha, gate })`
A minimal chat UI: message log, an input, and suggested-question chips shown
before the first message. POSTs to `/api/chat?alpha=…&gate=…` with
`{ query }` and renders `{ intent, answer }` from the response. Holds its own
local `log` state — chat history is not persisted anywhere and resets on
reload, which is fine for a live demo.

### `DiffPanel({ a, b, onClose })`
Renders above the board when two candidates are selected via the "compare"
button on their cards. Shows the score/K/M delta as a sentence, then every
skill both candidates have as a row of two status dots, dimming any skill both
share so the eye goes straight to what's genuinely different between them.

### `LoadingBoard()`
The skeleton state shown while `/api/analyze` is in flight. Cycles through a
fixed list of stage labels ("Parsing PDFs" → "Extracting job requirements" →
… ) on a timer purely for perceived-progress purposes — it does not reflect
real backend progress (the backend has no progress-streaming endpoint), and
should not be read as one. It exists so an 8–12 second wait feels engineered
rather than stalled.
