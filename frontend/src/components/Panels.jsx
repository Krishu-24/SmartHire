/**
 * Control rail, bias panel, chat dock, diff view and loading states.
 */
import { useEffect, useRef, useState } from 'react'
import { GapScatter } from './Charts'

/* ── Weight rail — the control the whole demo turns on ─────────────────────── */

export function WeightRail({ alpha, setAlpha, gate, setGate, meta, skills }) {
  const req = skills.filter((s) => s.tier === 'REQUIRED')
  const pref = skills.filter((s) => s.tier === 'PREFERRED')

  return (
    <>
      <div className="panel glass">
        <h3>Ranking weights</h3>
        <div className="slider-head">
          <span className={`side ${alpha >= 0.5 ? 'on' : ''}`}>Keyword</span>
          <span className={`side ${alpha <= 0.5 ? 'on' : ''}`}>Semantic</span>
        </div>
        <input
          type="range" min="0" max="1" step="0.01"
          value={1 - alpha}
          onChange={(e) => setAlpha(1 - parseFloat(e.target.value))}
          aria-label="Balance keyword matching against semantic matching"
        />
        <div className="alpha-readout">
          <span>α = {alpha.toFixed(2)}</span>
          <span>{(alpha * 100).toFixed(0)}% / {((1 - alpha) * 100).toFixed(0)}%</span>
        </div>

        <div className="toggle-row" role="button" tabIndex={0}
             onClick={() => setGate(!gate)}
             onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), setGate(!gate))}
             aria-pressed={gate}>
          <span className={`toggle ${gate ? 'on' : ''}`} />
          <span className="label">
            Must-have gate
            <small>Penalise missing required skills</small>
          </span>
        </div>
      </div>

      <div className="panel glass">
        <h3>Job requirements</h3>
        <div className="mono" style={{ fontSize: 10, color: 'var(--ink-4)', marginBottom: 6 }}>
          REQUIRED ({req.length})
        </div>
        <div className="chips-wrap" style={{ marginBottom: 11 }}>
          {req.map((s) => (
            <span key={s.id} className="chip MATCHED" style={{ cursor: 'default' }} title={s.evidence}>
              {s.label}
            </span>
          ))}
        </div>
        <div className="mono" style={{ fontSize: 10, color: 'var(--ink-4)', marginBottom: 6 }}>
          PREFERRED ({pref.length})
        </div>
        <div className="chips-wrap">
          {pref.map((s) => (
            <span key={s.id} className="chip WEAK" style={{ cursor: 'default' }} title={s.evidence}>
              {s.label}
            </span>
          ))}
        </div>
      </div>

      <div className="panel glass">
        <h3>Engine</h3>
        <dl style={{ margin: 0, display: 'grid', gridTemplateColumns: 'auto 1fr',
                     gap: '5px 10px', fontSize: 11 }}>
          {[
            ['semantic', meta.semantic_backend],
            ['device', meta.device],
            ['pool', `${meta.pool_size} resumes`],
            ['analysed in', `${(meta.elapsed_ms / 1000).toFixed(1)}s`],
            ['τ band', `${meta.tau_lo} – ${meta.tau_hi}`],
          ].map(([k, v]) => (
            <div key={k} style={{ display: 'contents' }}>
              <dt style={{ color: 'var(--ink-4)' }}>{k}</dt>
              <dd className="mono" style={{ margin: 0, color: 'var(--ink-2)', textAlign: 'right' }}>{v}</dd>
            </div>
          ))}
        </dl>
        <div className="mono" style={{ fontSize: 9.5, color: 'var(--ink-4)', marginTop: 9,
             paddingTop: 9, borderTop: '1px solid var(--glass-line)' }}>
          Scoring is computed locally. No LLM is used anywhere in this pipeline.
        </div>
      </div>
    </>
  )
}

/* ── Insight column ────────────────────────────────────────────────────────── */

export function InsightPanel({ candidates, selected, onSelect, bias, meta }) {
  const gems = candidates.filter((c) => c.flag === 'HIDDEN_GEM')
  const surface = candidates.filter((c) => c.flag === 'SURFACE_MATCH')

  return (
    <>
      <div className="panel glass">
        <h3>Skill-gap map</h3>
        <GapScatter candidates={candidates} selectedId={selected?.doc_id}
                    onSelect={onSelect} />
        <div style={{ display: 'flex', gap: 11, flexWrap: 'wrap', marginTop: 8, fontSize: 10 }}>
          {[['Hidden gem', 'var(--inferred)'], ['Surface match', 'var(--weak)'],
            ['Consensus', 'var(--ink-3)']].map(([l, c]) => (
            <span key={l} style={{ display: 'flex', alignItems: 'center', gap: 5, color: 'var(--ink-3)' }}>
              <i style={{ width: 7, height: 7, borderRadius: 99, background: c, display: 'block' }} />
              {l}
            </span>
          ))}
        </div>
      </div>

      {(gems.length > 0 || surface.length > 0) && (
        <div className="panel glass">
          <h3>Cross-channel signals</h3>
          {gems.map((c) => (
            <button key={c.doc_id} className="finding medium"
                    onClick={() => onSelect(c)}
                    style={{ display: 'block', width: '100%', textAlign: 'left',
                             background: 'none', border: 0, borderLeft: '2px solid var(--inferred)',
                             cursor: 'pointer', font: 'inherit' }}>
              <span className="sev">Hidden gem</span>
              <div className="txt">{c.name} — #{c.rank}</div>
              <div className="why">
                Semantic rank #{c.rank_semantic} against lexical rank #{c.rank_lexical}.{' '}
                {Math.round(c.primitives.inferred_req_ratio * 100)}% of required skills are
                demonstrated without being named.
              </div>
            </button>
          ))}
          {surface.map((c) => (
            <button key={c.doc_id} className="finding high"
                    onClick={() => onSelect(c)}
                    style={{ display: 'block', width: '100%', textAlign: 'left',
                             background: 'none', border: 0, borderLeft: '2px solid var(--weak)',
                             cursor: 'pointer', font: 'inherit' }}>
              <span className="sev">Surface match</span>
              <div className="txt">{c.name} — #{c.rank}</div>
              <div className="why">
                Names the skills but shows little supporting work. Lexical coverage
                runs {((c.primitives.lex_cov - c.primitives.sem_cov) * 100).toFixed(0)} points
                ahead of semantic.
              </div>
            </button>
          ))}
        </div>
      )}

      {bias && <BiasPanel bias={bias} />}
    </>
  )
}

/* ── Bias panel ────────────────────────────────────────────────────────────── */

export function BiasPanel({ bias }) {
  const [open, setOpen] = useState(true)
  const tone = bias.score >= 70 ? 'var(--matched)' : bias.score >= 40 ? 'var(--weak)' : 'var(--missing)'

  return (
    <div className="panel glass">
      <h3 style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>Job description review</span>
        <span className="mono" style={{ color: tone, fontSize: 12 }}>{bias.score}/100</span>
      </h3>
      <p style={{ fontSize: 11.5, color: 'var(--ink-2)', margin: '0 0 10px', lineHeight: 1.55 }}>
        {bias.summary}
      </p>
      <button className="btn" style={{ width: '100%', marginBottom: 10 }}
              onClick={() => setOpen(!open)}>
        {open ? 'Hide' : 'Show'} {bias.findings.length} findings
      </button>
      {open && bias.findings.map((f, i) => (
        <div key={i} className={`finding ${f.severity}`}>
          <span className="sev">{f.severity} · {f.label}</span>
          <div className="txt">“{f.matched_text}”</div>
          <div className="why">{f.why}</div>
          {f.impact && <span className="impact">▸ {f.impact}</span>}
          <div className="why" style={{ marginTop: 4, color: 'var(--ink-2)' }}>
            <strong style={{ color: 'var(--matched)' }}>Fix:</strong> {f.suggestion}
          </div>
        </div>
      ))}
    </div>
  )
}

/* ── Chat dock ─────────────────────────────────────────────────────────────── */

export function ChatDock({ candidates, alpha, gate }) {
  const [log, setLog] = useState([])
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const endRef = useRef(null)

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [log])

  const suggestions = candidates.length >= 2
    ? [
        `Why is ${candidates[0].name.split(' ')[0]} above ${candidates[1].name.split(' ')[0]}?`,
        `What is ${candidates[1].name.split(' ')[0]} missing?`,
        'Who knows Docker?',
        'Show me the top 5',
      ]
    : []

  const send = async (text) => {
    const query = (text ?? q).trim()
    if (!query || busy) return
    setQ('')
    setLog((l) => [...l, { who: 'you', text: query }])
    setBusy(true)
    try {
      const res = await fetch(`/api/chat?alpha=${alpha}&gate=${gate}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
      })
      const data = await res.json()
      setLog((l) => [...l, {
        who: 'bot',
        text: data.answer ?? data.detail ?? 'Something went wrong.',
        intent: data.intent,
      }])
    } catch {
      setLog((l) => [...l, { who: 'bot', text: 'Could not reach the engine.' }])
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="panel glass">
      <h3>Ask about this shortlist</h3>
      {log.length > 0 && (
        <div className="chat-log">
          {log.map((m, i) => (
            <div key={i} className={`msg ${m.who}`}>
              {m.intent && <span className="intent">{m.intent}</span>}
              {m.text}
            </div>
          ))}
          <div ref={endRef} />
        </div>
      )}
      {log.length === 0 && (
        <div className="suggestions">
          {suggestions.map((s) => (
            <button key={s} onClick={() => send(s)}>{s}</button>
          ))}
        </div>
      )}
      <form className="chat-input" onSubmit={(e) => { e.preventDefault(); send() }}>
        <input value={q} onChange={(e) => setQ(e.target.value)}
               placeholder="Why is X above Y?" aria-label="Ask a question" />
        <button className="btn" type="submit" disabled={busy || !q.trim()}>
          {busy ? '…' : 'Ask'}
        </button>
      </form>
      <div className="mono" style={{ fontSize: 9, color: 'var(--ink-4)', marginTop: 7 }}>
        Answers are templated from the score matrix — no language model involved.
      </div>
    </div>
  )
}

/* ── Diff ──────────────────────────────────────────────────────────────────── */

export function DiffPanel({ a, b, onClose }) {
  const cellsOf = (c) => Object.fromEntries(c.primitives.cells.map((x) => [x.skill_id, x]))
  const ca = cellsOf(a)
  const cb = cellsOf(b)
  const held = (s) => s === 'MATCHED' || s === 'INFERRED'
  const ids = [...new Set([...Object.keys(ca), ...Object.keys(cb)])]
    .sort((x, y) => (cb[y]?.weight ?? 0) - (cb[x]?.weight ?? 0) || x.localeCompare(y))

  const lead = a.score >= b.score ? a : b
  const trail = a.score >= b.score ? b : a

  return (
    <div className="panel glass">
      <h3 style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span>Side by side</span>
        <button className="btn" style={{ padding: '2px 8px' }} onClick={onClose}>✕</button>
      </h3>
      <p style={{ fontSize: 12, color: 'var(--ink)', margin: '0 0 12px', lineHeight: 1.55 }}>
        <strong>{lead.name}</strong> leads by {(lead.score - trail.score).toFixed(1)} points.
        Keyword {lead.k_score.toFixed(2)} vs {trail.k_score.toFixed(2)}, semantic{' '}
        {lead.m_score.toFixed(2)} vs {trail.m_score.toFixed(2)}.
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 88px 1fr', gap: 6,
                    fontSize: 11, alignItems: 'center' }}>
        <div className="mono" style={{ color: 'var(--ink-3)', fontSize: 10 }}>{a.name}</div>
        <div />
        <div className="mono" style={{ color: 'var(--ink-3)', fontSize: 10, textAlign: 'right' }}>{b.name}</div>

        {ids.map((id) => {
          const x = ca[id]
          const y = cb[id]
          const only = held(x?.status) !== held(y?.status)
          return (
            <div key={id} style={{ display: 'contents' }}>
              <div style={{ textAlign: 'right' }}>
                <span className={`chip ${x?.status ?? 'MISSING'}`}
                      style={{ cursor: 'default', opacity: only && held(x?.status) ? 1 : 0.42 }}>
                  {x?.status === 'MATCHED' ? '●' : x?.status === 'INFERRED' ? '◐' : '○'}
                </span>
              </div>
              <div style={{ textAlign: 'center', color: only ? 'var(--ink)' : 'var(--ink-4)',
                            fontSize: 10 }}>
                {x?.label ?? y?.label}
              </div>
              <div>
                <span className={`chip ${y?.status ?? 'MISSING'}`}
                      style={{ cursor: 'default', opacity: only && held(y?.status) ? 1 : 0.42 }}>
                  {y?.status === 'MATCHED' ? '●' : y?.status === 'INFERRED' ? '◐' : '○'}
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ── Loading ───────────────────────────────────────────────────────────────── */

const STAGES = [
  'Parsing PDFs',
  'Extracting job requirements',
  'Embedding resume chunks',
  'Scoring both channels',
  'Fusing and explaining',
]

export function LoadingBoard() {
  const [stage, setStage] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setStage((s) => Math.min(s + 1, STAGES.length - 1)), 1700)
    return () => clearInterval(t)
  }, [])

  return (
    <div className="board">
      <div className="panel glass">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
          {STAGES.map((s, i) => (
            <div key={s} className="stage-line"
                 style={{ opacity: i <= stage ? 1 : 0.32 }}>
              <span className="tick">{i < stage ? '✓' : i === stage ? '▸' : '·'}</span>
              {s}{i === stage ? '…' : ''}
            </div>
          ))}
        </div>
      </div>
      {Array.from({ length: 7 }).map((_, i) => (
        <div key={i} className="skel" style={{ height: 62, opacity: 1 - i * 0.12 }} />
      ))}
    </div>
  )
}
