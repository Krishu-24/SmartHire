import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { motion, AnimatePresence, LayoutGroup } from 'framer-motion'
import { rescore, poolStats } from './lib/rescore'
import { StatusBar } from './components/Charts'
import EvidenceDrawer from './components/EvidenceDrawer'
import { WeightRail, InsightPanel, ChatDock, DiffPanel, LoadingBoard } from './components/Panels'

export default function App() {
  const [payload, setPayload] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const [alpha, setAlpha] = useState(0.5)
  const [gate, setGate] = useState(false)

  const [selected, setSelected] = useState(null)
  const [compare, setCompare] = useState([])

  const fileRef = useRef(null)

  /* ── Ranking is recomputed here, in the browser, from sub-scores the backend
        already sent. Dragging the slider never touches the network. ───────── */
  const candidates = useMemo(() => {
    if (!payload) return []
    return rescore(payload.candidates, alpha, gate, payload.meta)
  }, [payload, alpha, gate])

  const stats = useMemo(() => poolStats(candidates), [candidates])

  // Keep the open drawer pointed at fresh numbers as the slider moves.
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
      setSelected(null)
      setCompare([])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  const loadSample = () => run(() => fetch('/api/analyze/sample', { method: 'POST' }))

  const upload = (files) => {
    const list = [...files]
    const jd = list.find((f) => /jd|job|description/i.test(f.name)) ?? list[0]
    const resumes = list.filter((f) => f !== jd)
    if (!resumes.length) {
      setError('Select a job description plus at least one resume.')
      return
    }
    const form = new FormData()
    form.append('jd', jd)
    for (const r of resumes) form.append('resumes', r)
    run(() => fetch('/api/analyze', { method: 'POST', body: form }))
  }

  const toggleCompare = (cand, e) => {
    e.stopPropagation()
    setCompare((prev) => {
      if (prev.includes(cand.doc_id)) return prev.filter((d) => d !== cand.doc_id)
      return [...prev, cand.doc_id].slice(-2)
    })
  }

  const comparePair = compare
    .map((id) => candidates.find((c) => c.doc_id === id))
    .filter(Boolean)

  /* ── Empty state ───────────────────────────────────────────────────────── */
  if (!payload && !loading) {
    return (
      <div className="app">
        <div className="empty">
          <div>
            <h1>Rank a batch of resumes<br />against one job description.</h1>
            <p>
              Hybrid matching: BM25 and per-skill lexical coverage on one side, sentence
              embeddings and per-skill semantic inference on the other. Every score traces
              back to a line of text. No language model scores anything.
            </p>
            {error && (
              <p style={{ color: 'var(--missing)', fontFamily: 'var(--mono)', fontSize: 12 }}>
                {error}
              </p>
            )}
            <div style={{ display: 'flex', gap: 9, justifyContent: 'center' }}>
              <button className="btn primary" onClick={loadSample}>
                Analyse the sample corpus
              </button>
              <button className="btn" onClick={() => fileRef.current?.click()}>
                Upload JD + resumes
              </button>
              <input
                ref={fileRef} type="file" accept="application/pdf" multiple hidden
                onChange={(e) => e.target.files?.length && upload(e.target.files)}
              />
            </div>
            <p className="mono" style={{ fontSize: 10.5, color: 'var(--ink-4)', marginTop: 18 }}>
              Name the job description file with “jd” or “job” so it is picked out of the batch.
            </p>
          </div>
        </div>
      </div>
    )
  }

  const meta = payload?.meta
  const job = payload?.job

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="mark">◆</span>
          InterLoom
        </div>
        {job && (
          <div className="role-title">
            <strong>{job.title}</strong> · {meta.pool_size} candidates
          </div>
        )}
        <div className="topbar-stats">
          <div className="stat">
            <div className="v num">{stats.spread.toFixed(1)}</div>
            <div className="l">spread</div>
          </div>
          <div className="stat">
            <div className="v num">{stats.max.toFixed(1)}</div>
            <div className="l">top score</div>
          </div>
          <button className="btn" onClick={() => fileRef.current?.click()}>New batch</button>
          <input
            ref={fileRef} type="file" accept="application/pdf" multiple hidden
            onChange={(e) => e.target.files?.length && upload(e.target.files)}
          />
        </div>
      </header>

      <div className="workspace">
        <aside className="col rail">
          {meta && job && (
            <WeightRail alpha={alpha} setAlpha={setAlpha} gate={gate} setGate={setGate}
                        meta={meta} skills={job.skills} />
          )}
        </aside>

        <main className="col">
          {loading ? (
            <LoadingBoard />
          ) : (
            <>
              {comparePair.length === 2 && (
                <DiffPanel a={comparePair[0]} b={comparePair[1]} onClose={() => setCompare([])} />
              )}
              <LayoutGroup>
                <div className="board">
                  <AnimatePresence initial={false}>
                    {candidates.map((c) => (
                      <motion.article
                        key={c.doc_id}
                        layout
                        layoutId={c.doc_id}
                        transition={{ type: 'spring', stiffness: 520, damping: 42 }}
                        className={`card glass ${c.flag} ${c.rank <= 3 ? 'top3' : ''} ${
                          selected?.doc_id === c.doc_id ? 'selected' : ''}`}
                        onClick={() => setSelected(c)}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ')
                          && (e.preventDefault(), setSelected(c))}
                        aria-label={`${c.name}, rank ${c.rank}, score ${c.score.toFixed(1)}`}
                      >
                        <div className="rank num">{String(c.rank).padStart(2, '0')}</div>

                        <div style={{ minWidth: 0 }}>
                          <div className="name">{c.name}</div>
                          <div className="meta">
                            {c.flag !== 'CONSENSUS' && (
                              <span className={`flagtag ${c.flag}`}>
                                {c.flag === 'HIDDEN_GEM' ? 'HIDDEN GEM' : 'SURFACE'}
                              </span>
                            )}
                            <span className="mono" style={{ fontSize: 10, color: 'var(--ink-3)' }}>
                              {Math.round(c.primitives.req_coverage * 100)}% required
                            </span>
                            {c.primitives.quality < 0.5 && (
                              <span className="mono" style={{ fontSize: 10, color: 'var(--weak)' }}>
                                ⚠ parse {c.primitives.quality.toFixed(2)}
                              </span>
                            )}
                            <button
                              className="mono"
                              onClick={(e) => toggleCompare(c, e)}
                              style={{
                                font: 'inherit', fontSize: 9.5, cursor: 'pointer',
                                background: compare.includes(c.doc_id) ? 'var(--accent-d)' : 'transparent',
                                color: compare.includes(c.doc_id) ? 'var(--accent)' : 'var(--ink-4)',
                                border: '1px solid var(--glass-line)', borderRadius: 4,
                                padding: '1px 5px',
                              }}
                            >
                              compare
                            </button>
                          </div>
                          <StatusBar candidate={c} />
                        </div>

                        <div className="score">
                          <div className="v num">{c.score.toFixed(1)}</div>
                          <div className="sub">
                            K {c.k_score.toFixed(2)} · M {c.m_score.toFixed(2)}
                          </div>
                        </div>
                      </motion.article>
                    ))}
                  </AnimatePresence>
                </div>
              </LayoutGroup>
            </>
          )}
        </main>

        <aside className="col insight">
          {meta && candidates.length > 0 && (
            <>
              <InsightPanel candidates={candidates} selected={liveSelected}
                            onSelect={setSelected} bias={job?.bias} meta={meta} />
              <ChatDock candidates={candidates} alpha={alpha} gate={gate} />
            </>
          )}
        </aside>
      </div>

      <EvidenceDrawer
        candidate={liveSelected}
        alpha={alpha}
        poolSize={meta?.pool_size ?? 0}
        onClose={() => setSelected(null)}
      />
    </div>
  )
}
