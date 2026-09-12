/**
 * The staging screen: assemble a batch before spending a minute analysing it.
 *
 * The job description and the candidates are picked separately and shown
 * separately, because they are not the same kind of thing. Guessing which of a
 * dropped pile of PDFs was the JD — by looking for "jd" in the filename — works
 * until it doesn't, and when it doesn't the whole run is wrong in a way that
 * takes a while to notice.
 *
 * Files can be removed here, before anything is read. Candidates can also be
 * added and removed *after* analysis from the board, which is a different code
 * path (the pool is live on the server by then); this screen only builds the
 * initial batch.
 */

import { useRef, useState } from 'react'

const MAX_NAME = 42

function shortName(name) {
  if (name.length <= MAX_NAME) return name
  const dot = name.lastIndexOf('.')
  const ext = dot > 0 ? name.slice(dot) : ''
  return `${name.slice(0, MAX_NAME - ext.length - 1)}…${ext}`
}

function kb(size) {
  return size > 1024 * 1024
    ? `${(size / 1024 / 1024).toFixed(1)} MB`
    : `${Math.max(1, Math.round(size / 1024))} KB`
}

/** A dashed drop target that also opens a file picker when clicked. */
function DropZone({ label, hint, multiple, onFiles, compact }) {
  const ref = useRef(null)
  const [over, setOver] = useState(false)

  const take = (list) => {
    const pdfs = [...list].filter((f) => /\.pdf$/i.test(f.name))
    if (pdfs.length) onFiles(pdfs)
  }

  return (
    <button
      type="button"
      className={`drop ${over ? 'drop--over' : ''} ${compact ? 'drop--compact' : ''}`}
      onClick={() => ref.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setOver(true) }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); take(e.dataTransfer.files) }}
    >
      <span className="drop__label">{label}</span>
      {hint && <span className="drop__hint">{hint}</span>}
      <input
        ref={ref} type="file" accept="application/pdf" multiple={multiple} hidden
        onChange={(e) => { take(e.target.files); e.target.value = '' }}
      />
    </button>
  )
}

function FileRow({ file, onRemove }) {
  return (
    <li className="filerow">
      <span className="filerow__name" title={file.name}>{shortName(file.name)}</span>
      <span className="filerow__size mono">{kb(file.size)}</span>
      <button className="filerow__x" onClick={onRemove}
              aria-label={`Remove ${file.name}`} title="Remove">×</button>
    </li>
  )
}

export default function Intake({
  jd, setJd, resumes, setResumes,
  onAnalyse, onSample, error, enrichment, setEnrichment, blind, setBlind, Toggle,
}) {
  const addResumes = (files) => {
    setResumes((prev) => {
      // Same filename twice is a re-pick, not a second candidate.
      const byName = new Map(prev.map((f) => [f.name, f]))
      for (const f of files) byName.set(f.name, f)
      return [...byName.values()]
    })
  }

  const ready = Boolean(jd) && resumes.length > 0

  return (
    <div className="intake">
      <div className="intake__inner">
        <h1>Rank a batch of resumes against one job description.</h1>
        <p className="intake__lede">
          Two independent channels — BM25 with per-skill lexical coverage, and
          sentence embeddings with per-skill semantic inference — fused into one
          ranking. Every score traces back to a line of text, weighted by where on
          the resume that line appears and whether any public code backs it up.
          No language model scores anything.
        </p>

        {error && <div className="banner banner--error intake__error">{error}</div>}

        <div className="intake__grid">
          {/* ── Job description ─────────────────────────────────────────── */}
          <section className="intake__panel">
            <header className="intake__head">
              <span className="eyebrow">Job description</span>
              <span className="intake__count">{jd ? '1 file' : 'required'}</span>
            </header>

            {jd ? (
              <ul className="filelist">
                <FileRow file={jd} onRemove={() => setJd(null)} />
              </ul>
            ) : (
              <DropZone label="Choose the job description"
                        hint="One PDF. Drag it here, or click to browse."
                        onFiles={(files) => setJd(files[0])} />
            )}

            {jd && (
              <DropZone compact label="Replace" hint="pick a different JD"
                        onFiles={(files) => setJd(files[0])} />
            )}
          </section>

          {/* ── Candidates ──────────────────────────────────────────────── */}
          <section className="intake__panel">
            <header className="intake__head">
              <span className="eyebrow">Candidates</span>
              <span className="intake__count">
                {resumes.length ? `${resumes.length} file${resumes.length === 1 ? '' : 's'}`
                                : 'at least one'}
              </span>
              {resumes.length > 0 && (
                <button className="btn btn--ghost intake__clear"
                        onClick={() => setResumes([])}>Clear all</button>
              )}
            </header>

            {resumes.length > 0 && (
              <ul className="filelist filelist--scroll">
                {resumes.map((f) => (
                  <FileRow key={f.name} file={f}
                           onRemove={() => setResumes((p) => p.filter((x) => x !== f))} />
                ))}
              </ul>
            )}

            <DropZone
              multiple compact={resumes.length > 0}
              label={resumes.length ? 'Add more candidates' : 'Choose candidate resumes'}
              hint={resumes.length ? 'drag or click' : 'One PDF each. Drag them here, or click to browse.'}
              onFiles={addResumes}
            />
          </section>
        </div>

        <div className="intake__actions">
          <button className="btn btn--primary" disabled={!ready} onClick={onAnalyse}>
            {ready
              ? `Analyse ${resumes.length} candidate${resumes.length === 1 ? '' : 's'}`
              : 'Analyse'}
          </button>
          <button className="btn" onClick={onSample}>Use the sample corpus</button>

          <span className="intake__spacer" />

          <Toggle checked={enrichment} onChange={setEnrichment}
                  label="External evidence"
                  title="Fetch public GitHub repositories to verify claims. Cached to disk; degrades silently when offline." />
          <Toggle checked={blind} onChange={setBlind} label="Blind screening"
                  title="Hide identity. Scoring is already blind — this controls what you can see." />
        </div>

        {!ready && (
          <p className="note intake__hint">
            {jd ? 'Add at least one candidate resume to begin.'
                : 'Start by choosing the job description.'}
          </p>
        )}
      </div>
    </div>
  )
}
