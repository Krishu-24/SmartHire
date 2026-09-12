/**
 * The printable report — one page, for a candidate or for the whole pool.
 *
 * Rendered into the normal document rather than a popup, hidden on screen and
 * revealed by the print stylesheet. That means it inherits every design token,
 * so what prints is the same typography as what the recruiter has been reading,
 * and it works with "Save as PDF" in every browser without a PDF library.
 *
 * The constraint that shapes both layouts is one page. That is not a formatting
 * preference — a one-page summary gets read in a meeting and a three-page one
 * gets skimmed. So each section is capped at the few rows that carry the
 * decision, and the caps are stated in the code rather than left to overflow.
 */

import { STATUS_LABEL, cls, pct } from '../lib/ui'

const MAX_MATCHED = 10
const MAX_GAPS = 4
const MAX_QUESTIONS = 3
const MAX_POOL_ROWS = 14

function Stamp({ meta, job }) {
  return (
    <div className="rep__stamp">
      <span>{job?.title ?? 'Role'}</span>
      <span>·</span>
      <span>{meta?.pool_size ?? 0} candidates</span>
      <span>·</span>
      <span>α {meta?.alpha?.toFixed?.(2) ?? '—'}</span>
      {meta?.blind && <><span>·</span><span>blind screening on</span></>}
      <span className="rep__stamp-right">
        {new Date().toLocaleDateString(undefined,
          { year: 'numeric', month: 'short', day: 'numeric' })}
      </span>
    </div>
  )
}

/* ── One candidate ─────────────────────────────────────────────────────── */

function CandidateReport({ candidate: c, meta, job }) {
  const p = c.primitives
  const cells = p.cells
  const matched = cells.filter((x) => x.status === 'MATCHED')
  const inferred = cells.filter((x) => x.status === 'INFERRED')
  const missingReq = cells.filter(
    (x) => x.tier === 'REQUIRED' && (x.status === 'MISSING' || x.status === 'WEAK'))

  return (
    <article className="rep">
      <header className="rep__head">
        <div>
          <h1 className="rep__name">{c.name}</h1>
          <div className="rep__sub">
            Rank {c.rank} of {meta?.pool_size} · {pct(p.req_coverage)} of required skills
          </div>
        </div>
        <div className="rep__score">
          <div className="rep__score-v">{c.score.toFixed(1)}</div>
          <div className="rep__score-l">match score</div>
        </div>
      </header>

      <Stamp meta={meta} job={job} />

      {c.explanation?.headline && (
        <p className="rep__lede">{c.explanation.headline}</p>
      )}

      <div className="rep__cols">
        <section className="rep__sec">
          <h2>Evidence</h2>
          <table className="rep__t">
            <tbody>
              <tr><td>Keyword channel</td><td className="mono">{c.k_score.toFixed(3)}</td></tr>
              <tr><td>Semantic channel</td><td className="mono">{c.m_score.toFixed(3)}</td></tr>
              <tr><td>Rank by keyword / semantic</td>
                  <td className="mono">{c.rank_lexical} / {c.rank_semantic}</td></tr>
              <tr><td>Rank by RRF</td><td className="mono">{c.rank_rrf}</td></tr>
              <tr><td>Claims discounted to</td>
                  <td className="mono">{Math.round((p.context_discount ?? 1) * 100)}%</td></tr>
              {p.external_proven > 0 && (
                <tr><td>Skills proven by code</td><td className="mono">{p.external_proven}</td></tr>
              )}
              {p.external_contradicted > 0 && (
                <tr><td>Claims absent from code</td>
                    <td className="mono">{p.external_contradicted}</td></tr>
              )}
              <tr><td>Parse quality</td><td className="mono">{p.quality.toFixed(2)}</td></tr>
            </tbody>
          </table>

          {c.flag !== 'CONSENSUS' && (
            <p className="rep__flag">
              {c.flag === 'HIDDEN_GEM'
                ? 'Hidden gem — required skills are demonstrated but never named, so a keyword filter would miss this candidate.'
                : 'Surface match — the resume names the skills but shows little work behind them.'}
            </p>
          )}
        </section>

        <section className="rep__sec">
          <h2>Skills</h2>
          <div className="rep__chips">
            {matched.slice(0, MAX_MATCHED).map((x) => (
              <span key={x.skill_id} className={`rep__chip rep__chip--${cls(x.status)}`}>
                {x.label}
              </span>
            ))}
            {inferred.map((x) => (
              <span key={x.skill_id} className={`rep__chip rep__chip--${cls(x.status)}`}>
                {x.label} *
              </span>
            ))}
          </div>
          {inferred.length > 0 && (
            <p className="rep__foot">* demonstrated in the work described, never named outright.</p>
          )}

          {missingReq.length > 0 && (
            <>
              <h3>Required, not evidenced</h3>
              <div className="rep__chips">
                {missingReq.map((x) => (
                  <span key={x.skill_id} className={`rep__chip rep__chip--${cls(x.status)}`}>
                    {x.label} <em>{STATUS_LABEL[x.status].toLowerCase()}</em>
                  </span>
                ))}
              </div>
            </>
          )}
        </section>
      </div>

      {c.ramp_up?.gaps?.length > 0 && (
        <section className="rep__sec">
          <h2>Time to close the gaps — about {c.ramp_up.total_human}</h2>
          <table className="rep__t rep__t--rule">
            <thead><tr><th>Gap</th><th>Builds on</th><th>Estimate</th></tr></thead>
            <tbody>
              {c.ramp_up.gaps.slice(0, MAX_GAPS).map((g) => (
                <tr key={g.skill_id}>
                  <td>{g.label}</td>
                  <td>{g.springboard}</td>
                  <td className="mono">{g.human}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {c.interview?.questions?.length > 0 && (
        <section className="rep__sec">
          <h2>Interview</h2>
          <ol className="rep__ol">
            {c.interview.questions.slice(0, MAX_QUESTIONS).map((q, i) => (
              <li key={i}>{q.question}</li>
            ))}
          </ol>
        </section>
      )}

      {(c.integrity?.stuffing_flag || c.integrity?.hidden_flag
        || c.verification?.contradicted > 0) && (
        <section className="rep__sec">
          <h2>Integrity</h2>
          {c.integrity?.headline && <p>{c.integrity.headline}.</p>}
          {c.verification?.headline && <p>{c.verification.headline}.</p>}
        </section>
      )}

      <footer className="rep__footer">
        Scored locally by SmartHire. No language model produced any part of this
        assessment; every claim traces to a line in the source document.
      </footer>
    </article>
  )
}

/* ── The whole pool ────────────────────────────────────────────────────── */

function SummaryReport({ candidates, meta, job }) {
  const pool = meta?.pool_integrity
  const gems = candidates.filter((c) => c.flag === 'HIDDEN_GEM')
  const surface = candidates.filter((c) => c.flag === 'SURFACE_MATCH')

  return (
    <article className="rep">
      <header className="rep__head">
        <div>
          <h1 className="rep__name">{job?.title ?? 'Shortlist'}</h1>
          <div className="rep__sub">Ranked shortlist · {candidates.length} candidates</div>
        </div>
        <div className="rep__score">
          <div className="rep__score-v">{candidates[0]?.score.toFixed(1) ?? '—'}</div>
          <div className="rep__score-l">top score</div>
        </div>
      </header>

      <Stamp meta={meta} job={job} />

      <section className="rep__sec">
        <table className="rep__t rep__t--rule rep__t--full">
          <thead>
            <tr>
              <th>#</th><th>Candidate</th><th>Score</th><th>Required</th>
              <th>Evidence</th><th>Note</th>
            </tr>
          </thead>
          <tbody>
            {candidates.slice(0, MAX_POOL_ROWS).map((c) => (
              <tr key={c.doc_id}>
                <td className="mono">{c.rank}</td>
                <td><strong>{c.name}</strong></td>
                <td className="mono">{c.score.toFixed(1)}</td>
                <td className="mono">{pct(c.primitives.req_coverage)}</td>
                <td className="mono">
                  {c.primitives.cells.filter((x) => x.status === 'MATCHED').length}S
                  {' '}
                  {c.primitives.cells.filter((x) => x.status === 'INFERRED').length}D
                </td>
                <td>
                  {c.flag === 'HIDDEN_GEM' ? 'hidden gem'
                    : c.flag === 'SURFACE_MATCH' ? 'surface match'
                    : c.primitives.external_proven > 0
                      ? `${c.primitives.external_proven} proven by code` : ''}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {candidates.length > MAX_POOL_ROWS && (
          <p className="rep__foot">
            Showing the top {MAX_POOL_ROWS} of {candidates.length}. S = stated, D = demonstrated.
          </p>
        )}
      </section>

      <div className="rep__cols">
        <section className="rep__sec">
          <h2>Worth a second look</h2>
          {gems.length > 0 && (
            <p><strong>Hidden gems:</strong> {gems.map((c) => c.name).join(', ')} — required
              skills demonstrated but never named, so a keyword filter would miss them.</p>
          )}
          {surface.length > 0 && (
            <p><strong>Surface matches:</strong> {surface.map((c) => c.name).join(', ')} — the
              resume names the skills but shows little work behind them.</p>
          )}
          {gems.length === 0 && surface.length === 0 && (
            <p>Both channels agree on every candidate in this pool.</p>
          )}
        </section>

        <section className="rep__sec">
          <h2>Pool integrity</h2>
          <table className="rep__t">
            <tbody>
              <tr><td>Unsupported-claim flags</td>
                  <td className="mono">{pool?.stuffing_flagged ?? 0}</td></tr>
              <tr><td>Invisible text found</td>
                  <td className="mono">{pool?.hidden_text_flagged ?? 0}</td></tr>
              <tr><td>Public profiles found</td>
                  <td className="mono">{pool?.profiles_found ?? 0}</td></tr>
              <tr><td>Fully code-verified</td>
                  <td className="mono">{pool?.fully_corroborated ?? 0}/{pool?.checked ?? 0}</td></tr>
              <tr><td>Personal details removed</td>
                  <td className="mono">{meta?.redactions ?? 0}</td></tr>
            </tbody>
          </table>
        </section>
      </div>

      {job?.bias && (
        <section className="rep__sec">
          <h2>Job description audit — {job.bias.score}/100 inclusivity</h2>
          <p>{job.bias.summary}</p>
        </section>
      )}

      <footer className="rep__footer">
        Scored locally by SmartHire. Identity is removed before scoring, so this
        ranking is blind by construction. No language model produced any part of it.
      </footer>
    </article>
  )
}

/* ── Shell ─────────────────────────────────────────────────────────────── */

export default function Report({ mode, candidate, candidates, meta, job }) {
  if (!mode) return null
  return (
    <div className="printable" aria-hidden="true">
      {mode === 'candidate' && candidate
        ? <CandidateReport candidate={candidate} meta={meta} job={job} />
        : <SummaryReport candidates={candidates} meta={meta} job={job} />}
    </div>
  )
}
