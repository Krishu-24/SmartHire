/**
 * The board: one row per candidate, ranked.
 *
 * Each row carries the four numbers a recruiter actually scans for — position,
 * score, how much of the JD is covered, and what kind of evidence that coverage
 * is made of. The evidence bar is the important one: two candidates on 71 points
 * can be completely different people, and the bar shows that at a glance without
 * anyone opening a drawer.
 */

import { motion, AnimatePresence, LayoutGroup } from 'framer-motion'
import { STATUSES, STATUS_LABEL, cls, pct, statusCounts } from '../lib/ui'

function EvidenceBar({ candidate }) {
  const counts = statusCounts(candidate)
  const total = STATUSES.reduce((a, s) => a + counts[s], 0) || 1

  return (
    <div>
      <div className="evbar" role="img"
           aria-label={STATUSES.map((s) => `${counts[s]} ${STATUS_LABEL[s]}`).join(', ')}>
        {STATUSES.map((s) => counts[s] > 0 && (
          <div key={s} className={`evbar__seg evbar__seg--${cls(s)}`}
               style={{ width: `${(counts[s] / total) * 100}%` }} />
        ))}
      </div>
      <div className="evbar__legend">
        {STATUSES.map((s) => counts[s] > 0 && (
          <span key={s}>{counts[s]} {STATUS_LABEL[s].toLowerCase()}</span>
        ))}
      </div>
    </div>
  )
}

function Flags({ candidate }) {
  const p = candidate.primitives
  const out = []

  if (candidate.flag === 'HIDDEN_GEM') {
    out.push(<span key="gem" className="chip chip--inferred" title="Required skills demonstrated but never named — a keyword filter would miss this person.">Hidden gem</span>)
  }
  if (candidate.flag === 'SURFACE_MATCH') {
    out.push(<span key="surf" className="chip chip--weak" title="Names the skills, shows little work behind them.">Surface match</span>)
  }
  if (candidate.integrity?.hidden_flag) {
    out.push(<span key="hid" className="chip chip--missing" title="Invisible text found in the PDF.">Invisible text</span>)
  }
  if (candidate.integrity?.stuffing_flag) {
    out.push(<span key="stuff" className="chip chip--missing" title={candidate.integrity.headline}>Unsupported claims</span>)
  }
  if (p.external_proven > 0) {
    out.push(<span key="gh" className="chip chip--matched" title="Skills proven by public code.">{p.external_proven} proven by code</span>)
  }
  if (p.external_contradicted > 0) {
    out.push(<span key="bad" className="chip chip--missing" title="Claimed but absent from every public repository.">{p.external_contradicted} unbacked</span>)
  }
  if (p.quality < 0.5) {
    out.push(<span key="q" className="chip chip--weak" title="This PDF was hard to read; review manually.">Parse {p.quality.toFixed(2)}</span>)
  }
  return out
}

export default function Board({ candidates, selected, onSelect, loading }) {
  if (loading) {
    return (
      <div className="board">
        {Array.from({ length: 8 }, (_, i) => <div key={i} className="skeleton" />)}
      </div>
    )
  }

  return (
    <LayoutGroup>
      <div className="board">
        <AnimatePresence initial={false}>
          {candidates.map((c) => (
            <motion.button
              key={c.doc_id}
              layout
              transition={{ type: 'spring', stiffness: 520, damping: 42 }}
              className={`row ${c.rank <= 3 ? 'row--top' : ''} ${
                c.primitives.doc_multiplier < 1 ? 'row--penalised' : ''}`}
              aria-selected={selected?.doc_id === c.doc_id}
              onClick={() => onSelect(c)}
            >
              <div className="row__rank num">{String(c.rank).padStart(2, '0')}</div>

              <div style={{ minWidth: 0 }}>
                <div className="row__name">{c.name}</div>
                <div className="row__meta">
                  <span className="chip chip--mono">{pct(c.primitives.req_coverage)} required</span>
                  <Flags candidate={c} />
                </div>
              </div>

              <EvidenceBar candidate={c} />

              <div className="row__score">
                <div className="row__score-v">{c.score.toFixed(1)}</div>
                <div className="row__score-sub">K {c.k_score.toFixed(2)} · M {c.m_score.toFixed(2)}</div>
              </div>
            </motion.button>
          ))}
        </AnimatePresence>
      </div>
    </LayoutGroup>
  )
}
