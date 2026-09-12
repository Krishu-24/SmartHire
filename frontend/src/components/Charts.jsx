/**
 * Hand-drawn SVG charts. No charting library — these are simple shapes and
 * writing them directly keeps every colour on the same theme tokens as the rest
 * of the app, which a library would fight.
 */
import { useMemo } from 'react'

const STATUS_HELD = new Set(['MATCHED', 'INFERRED'])

/* ── Skill radar, one axis per gazetteer cluster ───────────────────────────── */

export function ScoreRadar({ candidate, size = 250 }) {
  const data = useMemo(() => {
    const byCluster = new Map()
    for (const cell of candidate.primitives.cells) {
      const c = byCluster.get(cell.cluster) || { w: 0, cov: 0 }
      c.w += cell.weight
      c.cov += cell.weight * cell.coverage
      byCluster.set(cell.cluster, c)
    }
    return [...byCluster.entries()]
      .map(([label, v]) => ({ label, value: v.w ? v.cov / v.w : 0 }))
      .sort((a, b) => a.label.localeCompare(b.label))
  }, [candidate])

  if (data.length < 3) return null

  const cx = size / 2
  const cy = size / 2
  const r = size / 2 - 40
  const step = (Math.PI * 2) / data.length

  const pt = (i, frac) => {
    const a = i * step - Math.PI / 2
    return [cx + Math.cos(a) * r * frac, cy + Math.sin(a) * r * frac]
  }

  const poly = data.map((d, i) => pt(i, Math.max(d.value, 0.02)).join(',')).join(' ')

  return (
    <svg className="chart" viewBox={`0 0 ${size} ${size}`} role="img"
         aria-label="Skill coverage by cluster">
      {[0.25, 0.5, 0.75, 1].map((f) => (
        <polygon key={f} className="grid" fill="none"
                 points={data.map((_, i) => pt(i, f).join(',')).join(' ')} />
      ))}
      {data.map((_, i) => {
        const [x, y] = pt(i, 1)
        return <line key={i} className="grid" x1={cx} y1={cy} x2={x} y2={y} />
      })}

      <polygon points={poly} fill="var(--inferred)" fillOpacity="0.16"
               stroke="var(--inferred)" strokeWidth="1.5" strokeLinejoin="round" />
      {data.map((d, i) => {
        const [x, y] = pt(i, Math.max(d.value, 0.02))
        return <circle key={d.label} cx={x} cy={y} r="2.5" fill="var(--inferred)" />
      })}

      {data.map((d, i) => {
        const [x, y] = pt(i, 1.24)
        return (
          <text key={d.label} x={x} y={y} textAnchor="middle" dominantBaseline="middle">
            {d.label}
          </text>
        )
      })}
    </svg>
  )
}

/* ── Skill-gap density map ─────────────────────────────────────────────────── */

const FLAG_COLOR = {
  HIDDEN_GEM: 'var(--inferred)',
  SURFACE_MATCH: 'var(--weak)',
  CONSENSUS: 'var(--ink-3)',
}

export function GapScatter({ candidates, selectedId, onSelect, width = 300, height = 210 }) {
  const pad = { t: 14, r: 14, b: 30, l: 34 }
  const w = width - pad.l - pad.r
  const h = height - pad.t - pad.b

  const maxScore = Math.max(100, ...candidates.map((c) => c.score))
  const x = (s) => pad.l + (s / maxScore) * w
  const y = (g) => pad.t + g * h

  return (
    <svg className="chart" viewBox={`0 0 ${width} ${height}`} role="img"
         aria-label="Match score against required-skill gap density">
      {/* Quadrant guide: the vertical line marks a healthy match, the horizontal
          line marks half the required skills missing. */}
      <line className="grid" x1={x(maxScore * 0.6)} y1={pad.t}
            x2={x(maxScore * 0.6)} y2={pad.t + h} strokeDasharray="3 4" />
      <line className="grid" x1={pad.l} y1={y(0.5)} x2={pad.l + w} y2={y(0.5)}
            strokeDasharray="3 4" />

      <line className="axis" x1={pad.l} y1={pad.t + h} x2={pad.l + w} y2={pad.t + h} />
      <line className="axis" x1={pad.l} y1={pad.t} x2={pad.l} y2={pad.t + h} />

      <text x={pad.l + w} y={height - 8} textAnchor="end">match score →</text>
      <text x={pad.l - 8} y={pad.t + 4} textAnchor="end">100%</text>
      <text x={pad.l - 8} y={pad.t + h} textAnchor="end">0%</text>
      <text x={4} y={pad.t + h / 2} textAnchor="start" transform={`rotate(-90 10 ${pad.t + h / 2})`}>
        skill gap
      </text>

      {candidates.map((c) => {
        const sel = c.doc_id === selectedId
        const evidence = Math.min(c.primitives.n_chunks / 16, 1)
        return (
          <circle
            key={c.doc_id}
            className="scatter-pt"
            cx={x(c.score)}
            cy={y(c.primitives.gap_density)}
            r={sel ? 7 : 3.5 + evidence * 3}
            fill={FLAG_COLOR[c.flag] || 'var(--ink-3)'}
            fillOpacity={sel ? 1 : 0.62}
            stroke={sel ? 'var(--ink)' : 'none'}
            strokeWidth="1.5"
            onClick={() => onSelect(c)}
          >
            <title>{`${c.name} — ${c.score.toFixed(1)}, ${Math.round(c.primitives.gap_density * 100)}% gap`}</title>
          </circle>
        )
      })}
    </svg>
  )
}

/* ── Channel contribution bar ──────────────────────────────────────────────── */

export function ContribBar({ candidate, alpha }) {
  const k = alpha * candidate.k_score
  const m = (1 - alpha) * candidate.m_score
  const total = k + m || 1
  const kPct = (k / total) * 100

  return (
    <div className="contrib" role="img"
         aria-label={`Keyword contributes ${kPct.toFixed(0)} percent, semantic ${(100 - kPct).toFixed(0)} percent`}>
      <i className="k" style={{ flexGrow: Math.max(k, 0.001) }}>
        {kPct > 22 ? `KEYWORD ${kPct.toFixed(0)}%` : ''}
      </i>
      <i className="m" style={{ flexGrow: Math.max(m, 0.001) }}>
        {100 - kPct > 22 ? `SEMANTIC ${(100 - kPct).toFixed(0)}%` : ''}
      </i>
    </div>
  )
}

/* ── Per-candidate status distribution strip ───────────────────────────────── */

export function StatusBar({ candidate }) {
  const counts = { MATCHED: 0, INFERRED: 0, WEAK: 0, MISSING: 0 }
  for (const c of candidate.primitives.cells) counts[c.status] += c.weight
  const total = Object.values(counts).reduce((a, b) => a + b, 0) || 1

  return (
    <div className="minibar" role="img" aria-label="Skill evidence distribution">
      {['MATCHED', 'INFERRED', 'WEAK', 'MISSING'].map((s) =>
        counts[s] > 0 ? (
          <i key={s} className={s} style={{ width: `${(counts[s] / total) * 100}%` }} />
        ) : null,
      )}
    </div>
  )
}

export { STATUS_HELD }
