# SmartHire — Smart Shortlisting Engine

Ranks a batch of resumes against one job description using **both** keyword and
semantic matching, and explains every score down to the sentence that produced
it — then goes further than the ranking: how long each gap would take to close,
which claims the candidate's own code backs up, and what to tell the people who
did not get through.

No LLM scores anything. The matching is computed locally by our own engine, and
`scripts/verify.py` asserts that on every run.

---

## How to Run

### One-click

| Platform | Double-click |
|---|---|
| Windows | **[`run.bat`](run.bat)** |
| macOS / Linux | **[`run.command`](run.command)** |

> **macOS first run:** if double-clicking opens the file in a text editor
> instead of running it, make it executable once with `chmod +x run.command`.

Both open **one** terminal. The API runs in the background of that same window
and the UI in the foreground, so closing it or pressing Ctrl+C stops both —
rather than leaving two orphaned consoles to hunt down.

It will:

1. Check Python and Node are installed, and say where to get them if not.
2. Create `.venv/` — skipped if one already exists.
3. Install Python and frontend dependencies — skipped when nothing changed.
4. **Cache the embedding model**, and verify it actually discriminates.
5. Generate the sample corpus if no PDFs are on disk.
6. Check both ports are free, start the API and the UI, and open a browser.

Re-running is always safe, including after a fresh `git pull`. Dependencies are
re-installed only when `requirements.txt` or `package.json` has actually changed,
an existing virtual environment is never re-created, and the model is warmed once.

> **Why step 4 exists.** A cold `SentenceTransformer(...)` is a ~90 MB download.
> Paying that during a live demo on venue wifi is the single most likely way this
> project fails in front of an audience, so `run.bat` pays it up front where a
> slow network is visible and recoverable instead of mysterious.

### Manual setup

```bash
python -m venv .venv
```

```bash
# Windows
.venv\Scripts\python -m pip install -r requirements.txt
# macOS / Linux
.venv/bin/python -m pip install -r requirements.txt
```

```bash
python scripts/warm_models.py            # cache the model — do this FIRST
python scripts/make_synthetic_corpus.py  # skip if you have real PDFs
python -m uvicorn backend.app:app --port 8000
```

```bash
cd frontend && npm install && npm run dev   # separate terminal
# open http://localhost:5173
```

> Open **`localhost`**, not `127.0.0.1` — Vite binds the IPv6 loopback, and the
> IPv4 address can refuse the connection while the server is running perfectly.

### Using the real corpus

Drop the real files in and everything picks them up automatically — no flags, no
code changes:

```
data/jd/Sample_JD.pdf
data/resumes/*.pdf
```

Then re-run `scripts/verify.py`. If the score-spread check fails, recalibrate
`TAU_LO` / `TAU_HI` in `backend/config.py`; the current values were measured
against the synthetic corpus and the reasoning is recorded in the comments there.

### Optional: live GitHub evidence

The external-evidence channel works offline against bundled synthetic profiles.
To point it at real accounts you need a token, and the launcher will offer to
capture one on first run — paste it at the prompt and it is written to `.env`.

To set it up by hand instead:

```bash
cp .env.example .env      # or: copy .env.example .env
```

then edit `GITHUB_TOKEN=` in that file.

> **Create the token with NO scopes ticked.** SmartHire only ever reads public
> repositories, so a token with zero permissions works — and leaks nothing if it
> escapes.

**The token never enters a tracked file.** `.gitignore` excludes `.env`, the
launchers write to `.env` rather than to themselves, and `backend/credentials.py`
is the only thing permitted to render a token for display — always masked
(`ghp_1234…cdef`). `python scripts/check_token.py` reports the current state
without printing the value.

Unauthenticated GitHub allows 60 requests an hour, which is not enough for a
pool of any size; a token lifts it to 5000. Without one the channel degrades to
"no external evidence", which is a normal state and never an error.

---

## Check it works

```bash
python scripts/verify.py           # 11-check acceptance suite
python scripts/verify_formats.py   # does layout change the score?
python scripts/check_parity.py     # browser/engine agreement to 1e-9
python scripts/smoke.py            # ranked table, no server needed
python scripts/smoke.py --alpha 1.0   # pure keyword
python scripts/smoke.py --alpha 0.0   # pure semantic
python scripts/explain_scoring.py --flag HIDDEN_GEM

python scripts/make_format_fixtures.py   # one candidate, six layouts
python scripts/make_sample_jds.py        # three sample job descriptions
python scripts/check_token.py            # GitHub credential state, masked
```

The most important check is **#3: both channels change the ranking.** If
`--alpha 1.0` and `--alpha 0.0` produce the same order, one channel is dead and
35% of the rubric is gone regardless of how good everything else looks.

---

## What you get

### The ranking

For every skill the JD requires, two independent pieces of evidence — does the
resume *say* it (BM25 + exact/alias/fuzzy), and does the resume *show* it
(per-skill max-chunk cosine over MiniLM embeddings). Those fuse per skill into
one **evidence matrix**, which then produces the score, the explanations, the
chat answers and every panel in the UI. One structure, everything else derived.

```
PDF ─┬─ PyMuPDF ─────┐
     └─ pdfplumber ──┴─ redact ─ normalise ─ chunk ─┬─ CHANNEL K  BM25 + lexical coverage
                                                    └─ CHANNEL M  embeddings + semantic coverage
                                                              │
                                              per-skill soft-OR fusion
                                                              │
                                                    ★ EVIDENCE MATRIX
                                                              │
              ┌──────────────┬───────────────┬────────────────┼──────────┬──────────────┐
          explainer    ramp-up/bridge    interview      integrity      bias        feedback
                                                        + verification
```

### Format independence — the template must not be the candidate

`fixtures/formats/` holds the **same person** written six ways: two columns, no
headings at all, ALL-CAPS rules, inline `Skills:` headings, and one continuous
narrative. An engine that ranks them differently is measuring the template, not
the human — and that is the complaint every candidate has about every ATS.

`scripts/verify_formats.py` scores all six inside the real 18-candidate pool and
asserts they find an identical skill set. Three bugs it caught:

- **Two-column resumes lost their entire skills rail.** Raw PDF reading order
  interleaves the columns, so a narrow sidebar landed in the middle of unrelated
  prose. Pages are now checked for a real vertical gutter and each column is read
  in full before the next.
- **Short lines were silently dropped.** A rail listing `React`, `Docker`, `Git`
  one per line is six five-character lines, every one below the chunk minimum.
  Consecutive short lines are now gathered into one list, and a run still too
  short is merged into the chunk above it rather than discarded — nothing the
  candidate wrote is ever thrown away.
- **A vertical list escaped the bare-list discount** because the shape check
  split on commas but not newlines, so the same inventory scored higher purely
  for being in a sidebar.

A known residual is reported rather than hidden: continuous prose scores a few
points high, because long narrative chunks genuinely give the semantic channel
more context than the same facts as bullets.

### Context weighting — where a skill appears, and when

"React" in an internship that ended last month and "React" in a comma-separated
list from a first-year lab are both literal matches, and a keyword engine scores
them identically. Placement is priced as a multiplier on lexical evidence:
worked experience outranks a self-declared inventory, a bare tag in a delimited
run carries no context at all, and a dated mention decays towards a floor rather
than to zero.

On the sample corpus the planted keyword-stuffer's claims are worth **0.20** of
their face value; a genuine candidate sits around 0.90.

The status never changes — a stated skill is always reported as stated, because
that is a fact about the document. Only what the claim is *worth* moves, and the
UI shows the discount with the reason beside it.

### External evidence — GitHub and LinkedIn

A resume is a claim; a dependency manifest is a receipt. GitHub repositories are
read for language stats, config files and dependency manifests, mapped to skills
through `backend/data/library_map.json`. Code carries a score multiplier above 1
— it was executed, not typed into a CV.

LinkedIn is weighted at 0.35 and can only ever *support* a claim the resume
already makes. It has no public profile API and blocks automated access, so that
provider reads a supplied export and otherwise reports itself unavailable rather
than pretending to data it cannot lawfully obtain.

### Imported, or actually used?

A manifest proves someone typed a package name. It does not prove a line of code
was written with it — `package.json` accumulates what a tutorial added, and
`import pandas as pd` above a script that never touches `pd` is a copied header.

So source files are read and every import is classified:

| Verdict | Meaning | Weight |
|---|---|---|
| `CALLED` | invoked — `pd.read_csv(...)`, `<Router>`, `app.use(x)` | 1.00 |
| `REFERENCED` | mentioned but never called — a type, a re-export | 0.60 |
| `IMPORTED` | never seen again after the import line | 0.00 |

An unused import earns nothing, but is still *reported*: "declared, never
called" is more useful to a recruiter than silence, and it is exactly the shape
of a dependency that was never a skill.

Approximate by design — regex over five languages rather than a parser per
language. Where it is unsure it degrades to `REFERENCED`, never to a false
`CALLED`.

### Finding a GitHub account without a link

Most resumes carry an email and no profile URL. When there is no link, the email
is used as a fallback: GitHub's user search for a public profile address, then
commit-authorship search, which is how most accounts are actually discoverable.

Treated as the guess it is. A result is accepted **only** when the search
resolves to exactly one account — two people sharing an address prefix must not
inherit each other's repositories — and evidence from an inferred handle is
damped halfway back towards neutral and labelled as inferred everywhere it
appears. Requires a token; the search endpoints are unusable unauthenticated.

### Claim verification — README against imports

Four verdicts, and the asymmetry between them is the point. **Corroborated**
needs one positive fact. **Contradicted** needs a fact to be *missing* from
where it should have been, which is a far weaker inference — so it is gated
three ways: enough public code for absence to mean anything, a skill the library
map could actually detect, and a claim the resume does not already support with
real project text.

That last gate exists because of a bug this had without it: a candidate whose
bullet read *"containerised the service with Docker and deployed to AWS ECS"*
was marked as contradicting their own CV, because an employer's code is never in
a personal GitHub account. Only an unsupported claim — a bare tag, no project,
no code — can be contradicted now. That is the actual shape of resume padding.

### Bridge time — how long is this gap, really?

"Missing Docker" tells a recruiter almost nothing. For every gap on a
shortlisted candidate the engine finds the nearest thing they already do and
prices the walk using the ontology:

| From | To | Estimate |
|---|---|---|
| React | Vue | ~1 week |
| Python | Node.js | 2–3 weeks |
| Docker | Kubernetes | 3–4 weeks |
| No adjacent experience | Kubernetes | 3+ months |

The springboard is always named, so a recruiter who disagrees can see which
assumption to argue with. Gaps aggregate with decay rather than summing —
someone picking up three adjacent tools does the second and third faster.

### Skill ontology explorer

Every skill hangs off an explicit concept chain terminating at Software
Engineering, so any two skills have a lowest common ancestor and a defensible
distance. When the engine credits a non-identical match, the UI shows the path:

```
FastAPI → Python Backend → Backend Engineering → Software Engineering
```

That structure is also what the bridge-time model measures against, so the
explanation and the estimate cannot drift apart.

### Fusion inspector — Reciprocal Rank Fusion

Rather than asserting that `0.5 × keyword + 0.5 × semantic` is right, the
standard IR merge is computed alongside it and both rankings are shown:

$$\text{RRF}(d) = \frac{1}{k + r_{\text{keyword}}(d)} + \frac{1}{k + r_{\text{semantic}}(d)}$$

RRF uses only positions, so no channel's score scale can dominate — and it is
blind to how far apart candidates actually are, which the blended score knows.
Neither is right alone, and a candidate the two disagree about is exactly the one
worth a second look.

### Blind screening

PII is stripped **before the engine reads the document**, always. It carries no
skill signal, so removing it costs nothing and buys a claim worth making: the
ranking is blind by construction, not blind by policy. The toggle controls only
whether the recruiter can see identity — flipping it cannot move a single score,
which is the whole point and the reason it is safe to flip mid-demo.

Removed: names, emails, phones, addresses, universities, graduation years,
gender markers. Deliberately kept for matching: the GitHub link, because the
code behind it is exactly the signal we want. It is masked from display in
blind mode, since a readable handle would make the whole exercise theatre.

The JD is deliberately **not** redacted — the bias detector hunts for gendered
pronouns and school filters, which are precisely the strings redaction removes.

### Adversarial detection

**Keyword stuffing.** A genuine skill leaves a trace in the work — it appears in
a project or a role as well as in the inventory. A skill living *only* as a tag
is an orphan claim, discounted rather than deleted, because a terse resume is
not a dishonest one.

**Invisible text.** White-on-white and sub-legible keyword dumps, detected by
reading PDF span colour and size rather than the flattened text. Penalised hard:
unlike a thin skills section, there is no innocent reason for it.

### Interview questions and candidate feedback

Questions target exactly what the resume could not settle — a gap, an
unsupported claim, a skill demonstrated but never named, or a repository the
candidate actually pushed. Commodity skills are filtered out: nobody should
spend an interview slot asking about Git.

For candidates below the cut, the evaluation engine runs **backwards**. Each gap
is closed in simulation and the whole pool re-ranked, so "these three together
would have moved you four places" is a measured statement about this pool rather
than a guess — and the draft rejection note carries the roadmap.

---

## Documentation Hub

| Document | What it covers |
|---|---|
| [docs/MATH.md](docs/MATH.md) | Full derivation, written as a whiteboard script |
| [docs/FEATURES.md](docs/FEATURES.md) | Every feature, the decision behind it, and where it lives |
| [docs/ARCHITECTURE_AND_FEATURES.md](docs/ARCHITECTURE_AND_FEATURES.md) | Module-by-module architecture |
| [docs/JUDGE_GUIDE.md](docs/JUDGE_GUIDE.md) | Demo script and what to look at |
| [docs/PROBLEM_STATEMENT_ALIGNMENT.md](docs/PROBLEM_STATEMENT_ALIGNMENT.md) | Rubric mapping |
| [docs/PROBLEM_SOLVING_AND_DECISIONS.md](docs/PROBLEM_SOLVING_AND_DECISIONS.md) | Why things are the way they are |
| [docs/LIMITATIONS_AND_FUTURE_WORK.md](docs/LIMITATIONS_AND_FUTURE_WORK.md) | Honest limits |
| [docs/FRONTEND_GUIDE.md](docs/FRONTEND_GUIDE.md) | UI structure and the design system |

---

## API Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Liveness, backend and pool size |
| `POST` | `/api/analyze` | Full pipeline over an upload |
| `POST` | `/api/analyze/sample` | Analyse whichever corpus is on disk |
| `GET` | `/api/rank` | Re-rank cached pool; also renders blind mode |
| `POST` | `/api/chat` | Deterministic recruiter QA — no LLM in this path |
| `GET` | `/api/bias` | JD bias report with measured impact |
| `GET` | `/api/feedback` | Upskill roadmaps for candidates below the cut |
| `GET` | `/api/taxonomy` | Ontological path and neighbours for one skill |
| `GET` | `/api/taxonomy/relate` | How two skills relate, and the bridge cost |
| `POST` | `/api/enrich` | External evidence for one candidate, on demand |

---

## Repository Layout

```
backend/
  app.py              FastAPI, in-memory session cache
  config.py           every tuning constant, with the measurements behind it
  credentials.py      .env loading, token validation, masking — never logs a secret
  models.py           the API contract
  core/
    parser.py         multi-engine PDF cascade + invisible-text detection; never raises
    blind.py          PII redaction, applied before the engine reads anything
    normalizer.py     text repair, alias folding, chunking with spans
    context.py        recency and depth weighting — where a skill appears, and when
    skills.py         JD skill extraction and requirement tiering
    engine.py         both channels, independently
    fusion.py         normalisation, soft-OR, blend, RRF, adjustment
    assess.py         assembly: integrity + enrichment + verification -> multipliers
    integrity.py      keyword stuffing and unsupported claims
    enrich.py         GitHub and LinkedIn evidence, cached, never blocking
    usage.py          is the library imported, or actually called?
    verification.py   resume claims against the candidate's own code
    taxonomy.py       the ontology: paths, distance, bridge time
    rampup.py         per-candidate ramp-up estimates
    interview.py      targeted interview questions
    feedback.py       upskill roadmaps and rejection notes
    explainer.py      templated rationale read from the matrix
    bias_detector.py  lexicon scan + impact simulation
    chat.py           deterministic intent router
  data/
    skill_gazetteer.json  89 skills with aliases and embedding phrases
    alias_map.json        surface-form folding
    taxonomy.json         the concept tree and pinned bridge estimates
    library_map.json      dependency/import/file -> skill
    coaching.json         interview probes, project ideas, first steps
    bias_lexicon.json     coded and exclusionary wording
frontend/src/
  lib/rescore.js      client-side mirror of fusion.score()
  lib/ui.js           theme, formatting, the status vocabulary
  components/         board, detail inspector, whole-pool views
scripts/
  warm_models.py         cache the model — run first
  make_synthetic_corpus.py
  make_format_fixtures.py  one candidate, six layouts
  make_sample_jds.py       three job descriptions with different shapes
  check_token.py           GitHub credential state; never prints the value
  verify.py              acceptance suite
  verify_formats.py      does layout change the score?
  check_parity.py        JS/Python agreement
  smoke.py               CLI pipeline
  explain_scoring.py     full derivation, for pitch prep
fixtures/
  synthetic/          18 resumes + JD, with planted probes
  formats/            the same candidate in six layouts (make_format_fixtures.py)
  jds/                three sample JDs — generated, gitignored (make_sample_jds.py)
  profiles/           canned GitHub/LinkedIn profiles, so enrichment demos offline
.env.example          the only tracked file that names the secrets; copy to .env
```

---

## Notes for the team

- **`fusion.score()` must stay pure.** It is mirrored by `rescore.js`. Any hidden
  state creeping in makes the slider quietly wrong with no error anywhere, and
  `scripts/check_parity.py` is the only thing standing between us and that.
- **`fusion.aggregate()` is the single accumulation.** `prepare()`, `adjust()`
  and `without_skills()` all call it. Two copies would drift, and a coverage
  number would start disagreeing with the cells shown underneath it.
- **The design system is two files**, `frontend/src/index.css` (tokens) and
  `App.css` (layout). Every colour, radius and easing is a token at the top;
  retheme from there rather than hunting through components.
- **Animation shows a change the user caused**, never decoration: a row
  reordering under the slider, a panel arriving, an evidence bar sliding to its
  new mix. Nothing loops and nothing animates on a timer the user did not start,
  because a dashboard that moves while you read it is harder to read. All of it
  is disabled under `prefers-reduced-motion`.
- **Row actions stay hidden until hover, focus or selection.** Two permanent
  buttons per row is thirty-six controls competing with the eighteen names the
  recruiter came to read.
- **Never put a credential in a tracked file.** The launchers write to `.env`;
  `backend/credentials.py` is the only code that renders a token, always masked.
- **The four status colours are semantic, not decorative.** Green = MATCHED,
  blue = INFERRED, amber = WEAK, red = MISSING, used identically on rows, chips,
  the matrix and the diff. Changing one changes the app's whole legend.
- **Order in `assess.build()` is fixed.** Integrity must run before verification,
  because verification asks the resume whether it stands behind a claim before
  it is willing to call that claim contradicted.
- **The synthetic corpus has planted probes**
  (`fixtures/synthetic/manifest.json`) — a hidden gem, a keyword-stuffer, a typo
  case, a messy-format resume and a near-empty one. `verify.py` checks all five
  still behave after any tuning change.
- **`fixtures/profiles/` is synthetic** and says so in every `message` field.
  Those handles do not exist on real GitHub; they exist so the enrichment channel
  demonstrates with no network and no API token.
