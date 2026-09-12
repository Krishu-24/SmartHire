# InterLoom — Smart Shortlisting Engine

Ranks a batch of resumes against one job description using **both** keyword and
semantic matching, and explains every score down to the sentence that produced it.

No LLM scores anything. The matching is computed locally by our own engine —
`scripts/verify.py` asserts that on every run.

---

## Run it

```bash
# 1. Environment (Python 3.12, NOT 3.14 — the torch path is better travelled there)
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

# 2. Cache the embedding model. Do this FIRST — a cold download mid-demo is fatal.
.venv/bin/python scripts/warm_models.py

# 3. Generate the synthetic corpus (skip if you have the real PDFs — see below)
.venv/bin/python scripts/make_synthetic_corpus.py

# 4. Backend
.venv/bin/python -m uvicorn backend.app:app --port 8000

# 5. Frontend (separate terminal)
cd frontend && npm install && npm run dev
#    open http://localhost:5173
```

### Using the real corpus

Drop the real files in and everything picks them up automatically — no flags, no
code changes:

```
data/jd/Sample_JD.pdf
data/resumes/*.pdf
```

Then re-run `.venv/bin/python scripts/verify.py`. If the score-spread check
fails, recalibrate `TAU_LO` / `TAU_HI` in `backend/config.py` — the current
values were measured against the synthetic corpus and the reasoning is recorded
in the comments there.

---

## Check it works

```bash
.venv/bin/python scripts/verify.py           # 10-check acceptance suite
.venv/bin/python scripts/smoke.py            # ranked table, no server needed
.venv/bin/python scripts/smoke.py --alpha 1.0   # pure keyword
.venv/bin/python scripts/smoke.py --alpha 0.0   # pure semantic
.venv/bin/python scripts/explain_scoring.py --flag HIDDEN_GEM
```

The most important check is **#3: both channels change the ranking.** If
`--alpha 1.0` and `--alpha 0.0` produce the same order, one channel is dead and
35% of the rubric is gone regardless of how good everything else looks.

---

## How it works

Full derivation in **[docs/MATH.md](docs/MATH.md)** — written as a whiteboard
script, because the judges will ask.

The short version: for every skill the JD requires, we compute two independent
pieces of evidence — does the resume *say* it (BM25 + exact/alias/fuzzy), and
does the resume *show* it (per-skill max-chunk cosine over MiniLM embeddings).
Those fuse per skill into one **evidence matrix**, which then produces the score,
the explanations, the chatbot answers, and the charts. One structure, four
deliverables.

```
PDF ─┬─ PyMuPDF ─────┐
     └─ pdfplumber ──┴─ normalise ─ chunk ─┬─ CHANNEL K  BM25 + lexical coverage
                                           └─ CHANNEL M  embeddings + semantic coverage
                                                    │
                                    per-skill soft-OR fusion
                                                    │
                                          ★ EVIDENCE MATRIX
                                                    │
                    ┌───────────────┬───────────────┼──────────────┐
                 explainer        chat         bias detector     score
```

---

## What's interesting here

**Hidden Gem detection.** The problem statement describes a candidate who "built
REST APIs with Express and MongoDB" being relevant to a Node.js role without
using the word. We don't just handle that — we flag it. On the sample corpus,
Priya Nair never writes "Node.js"; the semantic channel finds it at cosine 0.556
from *"Server-side JavaScript runtime handling async I/O"*, and she is labelled
HIDDEN GEM with 27% of required skills demonstrated but unnamed.

**Surface Match detection.** The inverse, and a genuine finding from building
this: whole-document similarity is partly a proxy for lexical overlap, so a
resume that is a bare list of skill names embeds *very* close to a JD that lists
skill names. The planted keyword-stuffer scores the pool maximum on document
similarity while per-skill semantic coverage correctly rates her 0.306. That's
why `M_WEIGHT_DOCSIM` is 0.25, not 0.5.

**Zero-latency weight slider.** Every α-independent sub-score ships in the
payload, so the recruiter's Keyword↔Semantic slider re-ranks the pool in the
browser with no network call. `scripts/check_parity.py` proves `rescore.js` and
`fusion.py` agree to 1e-9 — without it the UI could drift from the engine
silently, with nothing raising.

**Bias detection that measures instead of asserts.** Layer 1 is a lexicon scan.
Layer 2 re-ranks the pool with each requirement removed and reports what it
actually costs: *"5+ years experience on an intern role — 18 of 18 candidates
fall below this threshold."*

---

## Layout

```
backend/
  app.py              FastAPI, in-memory session cache
  config.py           every tuning constant, with the measurements behind it
  models.py           the API contract
  core/
    parser.py         multi-engine PDF cascade; never raises
    normalizer.py     text repair, alias folding, chunking with spans
    skills.py         JD skill extraction and requirement tiering
    engine.py         both channels, independently
    fusion.py         normalisation, soft-OR, blend, RRF sidecar
    explainer.py      templated rationale read from the matrix
    bias_detector.py  lexicon scan + impact simulation
    chat.py           deterministic intent router
frontend/src/
  lib/rescore.js      client-side mirror of fusion.score()
  components/         board, drawer, charts, panels
scripts/
  warm_models.py         cache the model — run first
  make_synthetic_corpus.py
  smoke.py               CLI pipeline
  verify.py              acceptance suite
  check_parity.py        JS/Python agreement
  explain_scoring.py     full derivation, for pitch prep
```

---

## Notes for the team

- **`fusion.score()` must stay pure.** It is mirrored by `rescore.js`. Any hidden
  state creeping in makes the slider quietly wrong with no error anywhere.
- **The design system is one file**, `frontend/src/index.css`. Every colour,
  radius and easing is a token at the top; retheme from there rather than hunting
  through components. Plain CSS rather than Tailwind — fewer build moving parts,
  and the glass/animation work wanted precise control.
- **The four status colours are semantic, not decorative.** emerald = MATCHED,
  cyan = INFERRED, amber = WEAK, rose = MISSING, used identically on cards,
  radar, scatter, chips and diff. Changing one changes the app's whole legend.
- **The synthetic corpus has planted probes** (`fixtures/synthetic/manifest.json`)
  — a hidden gem, a keyword-stuffer, a typo case, a messy-format resume and a
  near-empty one. `verify.py` checks all five still behave after any tuning change.
