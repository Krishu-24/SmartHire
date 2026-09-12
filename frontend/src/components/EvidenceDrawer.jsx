/**
 * The evidence drawer — where a score becomes a claim you can check.
 *
 * Clicking a skill chip scrolls the resume to the exact sentence that produced
 * that cell and pulses it. The spans come from the backend, which took them from
 * the same chunks the scorer used, so a highlight can never point at the wrong text.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ScoreRadar, ContribBar } from './Charts'

const ORDER = ['MATCHED', 'INFERRED', 'WEAK', 'MISSING']
const HEADINGS = {
  MATCHED: 'Stated explicitly',
  INFERRED: 'Demonstrated without being named',
  WEAK: 'Adjacent experience only',
  MISSING: 'No evidence',
}

export default function EvidenceDrawer({ candidate, alpha, poolSize, onClose }) {
  const [active, setActive] = useState(null)
  const resumeRef = useRef(null)

  // Escape closes. Expected of any overlay; its absence is always noticed.
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => { setActive(null) }, [candidate?.doc_id])

  const grouped = useMemo(() => {
    const g = { MATCHED: [], INFERRED: [], WEAK: [], MISSING: [] }
    for (const cell of candidate?.primitives.cells ?? []) g[cell.status].push(cell)
    for (const k of ORDER) {
      g[k].sort((a, b) => b.weight - a.weight || b.coverage - a.coverage
        || a.label.localeCompare(b.label))
    }
    return g
  }, [candidate])

  // Build the resume as segments so matched sentences can be marked in place.
  const segments = useMemo(() => {
    if (!candidate) return []
    const text = candidate.resume_text || ''
    const spans = candidate.primitives.cells
      .filter((c) => c.start >= 0 && c.end > c.start)
      .map((c) => ({ start: c.start, end: c.end, id: c.skill_id }))

    // Merge overlapping spans; several skills often cite the same sentence.
    const merged = []
    for (const s of spans.sort((a, b) => a.start - b.start)) {
      const last = merged[merged.length - 1]
      if (last && s.start <= last.end) {
        last.end = Math.max(last.end, s.end)
        last.ids.push(s.id)
      } else {
        merged.push({ start: s.start, end: s.end, ids: [s.id] })
      }
    }

    const out = []
    let cursor = 0
    for (const m of merged) {
      if (m.start > cursor) out.push({ text: text.slice(cursor, m.start), ids: null })
      out.push({ text: text.slice(m.start, m.end), ids: m.ids })
      cursor = m.end
    }
    if (cursor < text.length) out.push({ text: text.slice(cursor), ids: null })
    return out
  }, [candidate])

  const jumpTo = (skillId) => {
    setActive(skillId)
    const el = resumeRef.current?.querySelector(`[data-skills~="${CSS.escape(skillId)}"]`)
    if (el) el.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }

  return (
    <AnimatePresence>
      {candidate && (
        <>
          <motion.div
            className="drawer-scrim"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            onClick={onClose}
          />
          <motion.aside
            className="drawer"
            initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 380, damping: 40 }}
            aria-label={`Evidence for ${candidate.name}`}
          >
            <header className="drawer-head">
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <span className="eyebrow">Rank #{candidate.rank} of {poolSize}</span>
                  <h2>{candidate.name}</h2>
                  {candidate.flag !== 'CONSENSUS' && (
                    <span className={`flagtag ${candidate.flag}`} style={{ marginTop: 6, display: 'inline-block' }}>
                      {candidate.flag.replace('_', ' ')}
                    </span>
                  )}
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div className="mono" style={{ fontSize: 28, fontWeight: 600, letterSpacing: '-0.03em' }}>
                    {candidate.score.toFixed(1)}
                  </div>
                  <div className="eyebrow">match score</div>
                </div>
                <button className="btn" onClick={onClose} aria-label="Close">✕</button>
              </div>
            </header>

            <div className="drawer-body">
              <section className="section">
                <h4>Why this ranking</h4>
                <p className="headline">{candidate.explanation?.headline}</p>
                <ul className="bullets">
                  {candidate.explanation?.bullets.map((b, i) => <li key={i}>{b}</li>)}
                </ul>
              </section>

              <section className="section">
                <h4>Channel contribution at α = {alpha.toFixed(2)}</h4>
                <ContribBar candidate={candidate} alpha={alpha} />
                <div className="mono" style={{ fontSize: 10.5, color: 'var(--ink-3)', marginTop: 7,
                     display: 'flex', justifyContent: 'space-between' }}>
                  <span>K {candidate.k_score.toFixed(3)} · lexical rank #{candidate.rank_lexical}</span>
                  <span>M {candidate.m_score.toFixed(3)} · semantic rank #{candidate.rank_semantic}</span>
                </div>
              </section>

              <section className="section">
                <h4>Skill evidence — click any skill to find it in the resume</h4>
                {ORDER.map((status) =>
                  grouped[status].length ? (
                    <div key={status} style={{ marginBottom: 11 }}>
                      <div className="mono" style={{ fontSize: 9.5, color: 'var(--ink-4)', marginBottom: 5 }}>
                        {HEADINGS[status]} ({grouped[status].length})
                      </div>
                      <div className="chips-wrap">
                        {grouped[status].map((cell) => (
                          <button
                            key={cell.skill_id}
                            className={`chip ${cell.status}`}
                            onClick={() => jumpTo(cell.skill_id)}
                            disabled={cell.start < 0}
                            title={`lexical ${cell.lex.toFixed(2)} · semantic ${cell.sem_raw.toFixed(3)}${
                              cell.tier === 'REQUIRED' ? ' · required' : ' · preferred'}`}
                          >
                            <span className="dot" />
                            {cell.label}
                            {cell.tier === 'REQUIRED' && <span style={{ opacity: 0.55 }}>*</span>}
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : null,
                )}
                <div className="mono" style={{ fontSize: 9.5, color: 'var(--ink-4)', marginTop: 8 }}>
                  * required by the job description
                </div>
              </section>

              <section className="section">
                <h4>Coverage by area</h4>
                <ScoreRadar candidate={candidate} />
              </section>

              <section className="section">
                <h4>
                  Resume as parsed
                  <span style={{ float: 'right', color: 'var(--ink-4)', letterSpacing: 0 }}>
                    {candidate.primitives.quality < 0.5 ? '⚠ ' : ''}
                    parse quality {candidate.primitives.quality.toFixed(2)}
                  </span>
                </h4>
                {candidate.primitives.warnings.length > 0 && (
                  <ul className="bullets" style={{ marginBottom: 9 }}>
                    {candidate.primitives.warnings.map((w, i) => (
                      <li key={i} style={{ color: 'var(--weak)' }}>{w}</li>
                    ))}
                  </ul>
                )}
                <div className="resume" ref={resumeRef}>
                  {segments.map((seg, i) =>
                    seg.ids ? (
                      <mark
                        key={i}
                        data-skills={seg.ids.join(' ')}
                        className={seg.ids.includes(active) ? 'pulse' : ''}
                      >
                        {seg.text}
                      </mark>
                    ) : (
                      <span key={i}>{seg.text}</span>
                    ),
                  )}
                </div>
              </section>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}
