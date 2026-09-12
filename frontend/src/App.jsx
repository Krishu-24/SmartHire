/**
 * Application shell.
 *
 * Two pieces of state deserve a note, because they behave differently on purpose:
 *
 *   alpha   never touches the network. The backend ships every alpha-independent
 *           sub-score, so dragging the weight slider re-ranks in the browser via
 *           lib/rescore.js. scripts/check_parity.py proves that arithmetic
 *           matches fusion.py to 1e-9.
 *
 *   blind   DOES round-trip, and cannot change a single score. Identity is
 *           stripped at parse time and never reaches the engine, so the server
 *           only re-renders which name goes on a row. That is the whole claim,
 *           and the reason it is safe to flip mid-demo: the numbers do not move.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import './App.css'
import { rescore, poolStats } from './lib/rescore'
import { useTheme } from './lib/ui'
import Board from './components/Board'
import Detail from './components/Detail'
import ChatDock from './components/Chat'
import Intake from './components/Intake'
import Report from './components/Report'
import { DiffPanel, SignalsView, FusionInspector, TaxonomyExplorer, JobAudit, FeedbackView }
  from './components/Views'

const TABS = [
  ['board', 'Shortlist'],
  ['signals', 'Signals'],
  ['fusion', 'Fusion inspector'],
  ['taxonomy', 'Skill ontology'],
  ['audit', 'JD audit'],
  ['feedback', 'Candidate feedback'],
]

function Toggle({ checked, onChange, label, title }) {
  return (
    <button className="toggle" role="switch" aria-checked={checked}
            onClick={() => onChange(!checked)} title={title}>
      <span className="toggle__track"><span className="toggle__thumb" /></span>
      <span className="toggle__label">{label}</span>
    </button>
  )
}

export default function App() {
  const [payload, setPayload] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const [alpha, setAlpha] = useState(0.5)
  const [gate, setGate] = useState(false)
  const [blind, setBlind] = useState(false)
  const [enrichment, setEnrichment] = useState(true)

  const [tab, setTab] = useState('board')
  const [selected, setSelected] = useState(null)
  // At most two, most-recently-picked wins — a diff of three is a table, not a diff.
  const [compare, setCompare] = useState([])

  // The staged batch, before anything is sent. Kept here rather than inside
  // Intake so "New batch" can drop the recruiter back into a populated screen.
  const [jdFile, setJdFile] = useState(null)
  const [resumeFiles, setResumeFiles] = useState([])

  // null when nothing is printing. Set, then window.print() once React has
  // painted the report — printing before the paint gives a blank page.
  const [printMode, setPrintMode] = useState(null)

  const [theme, toggleTheme] = useTheme()
  const jdSwapRef = useRef(null)
  const addRef = useRef(null)

  /* Ranking recomputed in the browser from sub-scores already in the payload. */
  const candidates = useMemo(() => {
    if (!payload) return []
    return rescore(payload.candidates, alpha, gate, payload.meta)
  }, [payload, alpha, gate])

  const stats = useMemo(() => poolStats(candidates), [candidates])

  // Keep an open inspector pointed at fresh numbers as the slider moves.
  const liveSelected = selected
    ? candidates.find((c) => c.doc_id === selected.doc_id) ?? null
    : null

  const run = useCallback(async (fetcher) => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetcher()
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || `Request failed (${res.status})`)
      }
      const data = await res.json()
      setPayload(data)
      setAlpha(data.meta.alpha)
      setGate(data.meta.gate)
      setBlind(data.meta.blind)
      setSelected(null)
      setCompare([])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  const loadSample = () => run(() => fetch(
    `/api/analyze/sample?enrichment=${enrichment}&blind_mode=${blind}`, { method: 'POST' }))

  /* Analyse the batch staged on the intake screen. The JD is chosen explicitly
     there, so nothing here has to guess which file it was from its name. */
  const analyseStaged = () => {
    if (!jdFile || !resumeFiles.length) {
      setError('Choose a job description and at least one resume.')
      return
    }
    const form = new FormData()
    form.append('jd', jdFile)
    for (const r of resumeFiles) form.append('resumes', r)
    form.append('enrichment', String(enrichment))
    form.append('blind_mode', String(blind))
    run(() => fetch('/api/analyze', { method: 'POST', body: form }))
  }

  /* ── Live pool edits ──────────────────────────────────────────────────
     These three re-score on the server, but the resumes are already parsed and
     already embedded, so each is a fraction of a second rather than a re-ingest.
     Scores DO move for everyone: the normalisation anchors are pool-relative,
     so changing who is in the room genuinely changes where people stand. */

  const swapJd = (file) => {
    if (!file) return
    const form = new FormData()
    form.append('jd', file)
    form.append('alpha', String(alpha))
    form.append('gate', String(gate))
    form.append('blind_mode', String(blind))
    run(() => fetch('/api/jd', { method: 'POST', body: form }))
  }

  const addCandidates = (files) => {
    const list = [...files].filter((f) => /\.pdf$/i.test(f.name))
    if (!list.length) return
    const form = new FormData()
    for (const f of list) form.append('resumes', f)
    form.append('alpha', String(alpha))
    form.append('gate', String(gate))
    form.append('blind_mode', String(blind))
    run(() => fetch('/api/candidates', { method: 'POST', body: form }))
  }

  const removeCandidate = useCallback((docId) => {
    setSelected((cur) => (cur?.doc_id === docId ? null : cur))
    setCompare((prev) => prev.filter((d) => d !== docId))
    run(() => fetch(
      `/api/candidates/${encodeURIComponent(docId)}?alpha=${alpha}&gate=${gate}&blind_mode=${blind}`,
      { method: 'DELETE' }))
  }, [run, alpha, gate, blind])

  /* Print: mount the report (outside .app so the print stylesheet can hide the
     UI without also hiding the report), wait for paint, then open the dialog.
     Clear only after print finishes — clearing on a zero timeout unmounted the
     report before the browser captured it. */
  const print = useCallback((mode) => {
    setPrintMode(mode)
  }, [])

  useEffect(() => {
    if (!printMode) return undefined
    let cancelled = false
    const clear = () => { if (!cancelled) setPrintMode(null) }
    window.addEventListener('afterprint', clear)
    const frame = requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (!cancelled) window.print()
      })
    })
    // Browsers that never fire afterprint (rare); keep the report mounted while
    // the dialog is open — a short timeout blanked the page mid-print.
    const fallback = setTimeout(clear, 60_000)
    return () => {
      cancelled = true
      cancelAnimationFrame(frame)
      window.removeEventListener('afterprint', clear)
      clearTimeout(fallback)
    }
  }, [printMode])

  /* Blind mode is a server-side re-render: pseudonyms come from pool position,
     and the resume text has to be masked for display. Scores are untouched. */
  const setBlindMode = useCallback((next) => {
    setBlind(next)
    if (!payload) return
    fetch(`/api/rank?alpha=${alpha}&gate=${gate}&blind_mode=${next}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && setPayload(d))
      .catch(() => {})
  }, [payload, alpha, gate])

  const toggleCompare = useCallback((docId) => {
    setCompare((prev) => (prev.includes(docId)
      ? prev.filter((d) => d !== docId)
      : [...prev, docId].slice(-2)))
  }, [])

  const comparePair = compare
    .map((id) => candidates.find((c) => c.doc_id === id))
    .filter(Boolean)

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') setSelected(null) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  /* ── Intake ──────────────────────────────────────────────────────────── */
  if (!payload && !loading) {
    return (
      <div className="app">
        <header className="topbar topbar--bare">
          <div className="brand"><span className="brand__mark">SH</span> SmartHire</div>
          <div className="topbar__spacer" />
          <button className="btn btn--ghost btn--icon" onClick={toggleTheme}
                  aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
                  title="Toggle theme">
            {theme === 'dark' ? '☀' : '☾'}
          </button>
        </header>
        <Intake
          jd={jdFile} setJd={setJdFile}
          resumes={resumeFiles} setResumes={setResumeFiles}
          onAnalyse={analyseStaged} onSample={loadSample}
          error={error}
          enrichment={enrichment} setEnrichment={setEnrichment}
          blind={blind} setBlind={setBlind}
          Toggle={Toggle}
        />
      </div>
    )
  }

  const meta = payload?.meta
  const job = payload?.job
  const pool = meta?.pool_integrity

  return (
    <>
    <div className="app">
      <header className="topbar">
        <div className="brand"><span className="brand__mark">SH</span> SmartHire</div>

        {job && (
          <div className="topbar__role">
            <strong title={job.title}>{job.title}</strong>
            <span>{meta.pool_size} candidates</span>
          </div>
        )}

        <div className="topbar__spacer" />

        <div className="topbar__stats">
          <div className="stat">
            <div className="stat__v num">{stats.spread.toFixed(1)}</div>
            <div className="stat__l">spread</div>
          </div>
          <div className="stat">
            <div className="stat__v num">{stats.max.toFixed(1)}</div>
            <div className="stat__l">top score</div>
          </div>

          <Toggle checked={blind} onChange={setBlindMode} label="Blind"
                  title="Identity never reached the engine. This only controls what you can see — the scores do not change." />

          <button className="btn btn--ghost btn--icon" onClick={toggleTheme}
                  aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
                  title="Toggle theme">
            {theme === 'dark' ? '☀' : '☾'}
          </button>

          <button className="btn" onClick={() => print('summary')}
                  title="One-page shortlist report — print, or save as PDF">
            Print summary
          </button>

          <button className="btn" onClick={() => { setPayload(null); setError(null) }}
                  title="Return to the intake screen with this batch still staged">
            New batch
          </button>
        </div>
      </header>

      <nav className="tabs" role="tablist">
        {TABS.map(([id, label]) => (
          <button key={id} role="tab" className="tab" aria-selected={tab === id}
                  onClick={() => setTab(id)}>
            {label}
            {id === 'board' && <span className="tab__count">{candidates.length}</span>}
            {id === 'signals' && (
              <span className="tab__count">
                {candidates.filter((c) => c.flag !== 'CONSENSUS').length}
              </span>
            )}
            {id === 'audit' && job?.bias && <span className="tab__count">{job.bias.findings.length}</span>}
          </button>
        ))}
      </nav>

      <div className={`workspace ${liveSelected ? 'workspace--detail' : ''}`}>
        <aside className="col rail">
          {/* Editing the batch is a live operation: the resumes stay parsed and
              embedded, so swapping the JD or adding someone re-scores in well
              under a second rather than re-ingesting the pool. */}
          <div>
            <div className="eyebrow" style={{ marginBottom: 6 }}>This batch</div>
            <div className="railbtns">
              <button className="btn railbtn" onClick={() => jdSwapRef.current?.click()}
                      title="Score this same pool against a different job description">
                Change JD
              </button>
              <input ref={jdSwapRef} type="file" accept="application/pdf" hidden
                     onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; swapJd(f) }} />

              <button className="btn railbtn" onClick={() => addRef.current?.click()}
                      title="Add more resumes to the live pool">
                Add candidates
              </button>
              <input ref={addRef} type="file" accept="application/pdf" multiple hidden
                     onChange={(e) => { const f = e.target.files; e.target.value = ''; addCandidates(f) }} />
            </div>
            <p className="note" style={{ marginTop: 6 }}>
              Everyone is re-scored: the normalisation is pool-relative, so who is
              in the room changes where people stand.
            </p>
          </div>

          <div>
            <div className="eyebrow" style={{ marginBottom: 6 }}>Matching weight</div>
            <div className="slider">
              <input type="range" min="0" max="1" step="0.01" value={alpha}
                     onChange={(e) => setAlpha(parseFloat(e.target.value))}
                     aria-label="Keyword to semantic weighting" />
              <div className="slider__ends">
                <span>semantic</span>
                <span className="mono">α {alpha.toFixed(2)}</span>
                <span>keyword</span>
              </div>
            </div>
            <p className="note" style={{ marginTop: 6 }}>
              Re-ranks in the browser — no network call.
            </p>
          </div>

          <div>
            <Toggle checked={gate} onChange={setGate} label="Must-have gate"
                    title="Scale scores by how much of the required set a candidate covers. Floored, so it re-ranks rather than eliminates." />
            <p className="note" style={{ marginTop: 6 }}>
              Scales by required coverage, floored at {meta?.gate_floor} so a strong
              near-miss stays visible.
            </p>
          </div>

          {pool && (
            <div>
              <div className="eyebrow" style={{ marginBottom: 6 }}>Pool integrity</div>
              <div className="kv"><span className="kv__k">Unsupported claims</span>
                <span className="kv__v">{pool.stuffing_flagged}</span></div>
              <div className="kv"><span className="kv__k">Invisible text</span>
                <span className="kv__v">{pool.hidden_text_flagged}</span></div>
              <div className="kv"><span className="kv__k">Profiles found</span>
                <span className="kv__v">{pool.profiles_found}</span></div>
              <div className="kv"><span className="kv__k">Code-verified</span>
                <span className="kv__v">{pool.fully_corroborated}/{pool.checked}</span></div>
              <div className="kv"><span className="kv__k">README-only claims</span>
                <span className="kv__v">{pool.readme_only_claims}</span></div>
            </div>
          )}

          <div>
            <div className="eyebrow" style={{ marginBottom: 6 }}>Run</div>
            <div className="kv"><span className="kv__k">Engine</span>
              <span className="kv__v">{meta?.semantic_backend}</span></div>
            <div className="kv"><span className="kv__k">Elapsed</span>
              <span className="kv__v">{meta?.elapsed_ms} ms</span></div>
            <div className="kv"><span className="kv__k">PII removed</span>
              <span className="kv__v">{meta?.redactions}</span></div>
            <div className="kv"><span className="kv__k">Parse warnings</span>
              <span className="kv__v">{meta?.parse_warnings}</span></div>
            <div className="kv"><span className="kv__k">External evidence</span>
              <span className="kv__v">{meta?.enrichment ? 'on' : 'off'}</span></div>
          </div>
        </aside>

        <main className="col main">
          {error && <div className="banner banner--error" style={{ marginBottom: 12 }}>{error}</div>}

          {tab === 'board' && (
            <>
              {comparePair.length === 2 && (
                <DiffPanel a={comparePair[0]} b={comparePair[1]}
                           onClose={() => setCompare([])} />
              )}
              <Board candidates={candidates} selected={liveSelected}
                     onSelect={setSelected} loading={loading}
                     compare={compare} onCompare={toggleCompare}
                     onRemove={removeCandidate} />
            </>
          )}
          {tab === 'signals' && (
            <SignalsView candidates={candidates} selected={liveSelected} onSelect={setSelected} />
          )}
          {tab === 'fusion' && <FusionInspector candidates={candidates} meta={meta} />}
          {tab === 'taxonomy' && <TaxonomyExplorer job={job} candidates={candidates} />}
          {tab === 'audit' && <JobAudit job={job} />}
          {tab === 'feedback' && (
            <FeedbackView alpha={alpha} gate={gate} shortlist={3} ready={!!payload} />
          )}
        </main>

        {/* The inspector is one candidate; the dock underneath is the whole pool.
            Both are answers about the same ranking, so they share a column —
            and the dock stays reachable whether or not a row is open. */}
        <aside className="col inspector">
          <div className="inspector__body">
            <Detail candidate={liveSelected} alpha={alpha}
                    onClose={() => setSelected(null)}
                    onPrint={() => print('candidate')}
                    onRemove={removeCandidate} />
          </div>
          {candidates.length > 0 && (
            <ChatDock candidates={candidates} alpha={alpha} gate={gate}
                      onSelect={setSelected} />
          )}
        </aside>
      </div>

    </div>
    <Report mode={printMode} candidate={liveSelected} candidates={candidates}
            meta={meta} job={job} />
    </>
  )
}
