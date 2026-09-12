"""
Fusion: turn two channels into one ranked, explainable shortlist.

The split in this module matters and is not cosmetic:

    prepare()  expensive, alpha-INDEPENDENT. Normalises across the pool, builds
               the evidence matrix. Runs once per session.

    score()    cheap, alpha-DEPENDENT, and a PURE function of prepare()'s output.
               Mirrored line-for-line by frontend/src/lib/rescore.js so the
               recruiter's weight slider recomputes in the browser with no
               network call. scripts/check_parity.py proves the two agree.

If anything stateful ever creeps into score(), the slider silently disagrees with
the backend and nothing raises. Keep it pure.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

import numpy as np

from backend import config
from backend.core.engine import SubScores
from backend.core.skills import Skill, REQUIRED

# Per-skill evidence labels
MATCHED = "MATCHED"
INFERRED = "INFERRED"
WEAK = "WEAK"
MISSING = "MISSING"

# Cross-channel agreement flags
HIDDEN_GEM = "HIDDEN_GEM"
SURFACE_MATCH = "SURFACE_MATCH"
CONSENSUS = "CONSENSUS"


# ─────────────────────────────────────────────────────────────────────────────
# Primitives
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(slots=True)
class SkillCell:
    """One cell of the evidence matrix. Drives score, explanation and UI alike."""
    skill_id: str
    label: str
    tier: str
    weight: float
    cluster: str
    lex: float
    lex_kind: str
    sem_raw: float
    sem_cal: float          # g(sem_raw)
    coverage: float         # max(lex, sem_cal)
    status: str
    evidence: str = ""      # the resume sentence supporting this
    start: int = -1         # char span into the candidate's display text
    end: int = -1


@dataclass(slots=True)
class Primitives:
    """Everything score() needs, and nothing it doesn't. This is what ships to the client."""
    doc_id: str
    name: str
    filename: str

    bm25_raw: float
    bm25_norm: float
    docsim_raw: float
    docsim_norm: float
    lex_cov: float
    sem_cov: float
    req_coverage: float
    gap_density: float        # weighted fraction of REQUIRED skills not covered
    inferred_req_ratio: float # weighted share of REQUIRED skills found ONLY semantically

    quality: float
    n_chunks: int
    warnings: list[str] = field(default_factory=list)
    cells: list[SkillCell] = field(default_factory=list)


@dataclass(slots=True)
class Candidate:
    """A scored, ranked candidate."""
    doc_id: str
    name: str
    filename: str
    score: float
    rank: int
    k_score: float
    m_score: float
    gate: float
    rank_lexical: int
    rank_semantic: int
    rank_delta: int
    rrf: float
    flag: str
    primitives: Primitives


# ─────────────────────────────────────────────────────────────────────────────
# Normalisation
# ─────────────────────────────────────────────────────────────────────────────

def robust_norm(values: np.ndarray) -> np.ndarray:
    """Percentile-anchored pool-relative min-max.

    P5/P95 rather than true min/max is deliberate. One pathological resume — a
    scanned image yielding forty characters — would otherwise define the floor
    and compress every real candidate into the top sliver of the range, which is
    exactly the "all-similar scores" failure the brief penalises.
    """
    values = np.asarray(values, dtype=np.float64)
    if values.size == 0:
        return values
    lo = float(np.percentile(values, config.NORM_LO_PCT))
    hi = float(np.percentile(values, config.NORM_HI_PCT))
    if hi - lo < 1e-9:
        # Degenerate pool (every candidate identical). Mid-scale is the only
        # honest answer; pretending to rank them would be noise.
        return np.full_like(values, 0.5)
    return np.clip((values - lo) / (hi - lo), 0.0, 1.0)


def calibrate(x: float) -> float:
    """g(x): rescale raw cosine from the discriminative band into [0,1]."""
    span = config.TAU_HI - config.TAU_LO
    if span <= 0:
        return 0.0
    return float(min(max((x - config.TAU_LO) / span, 0.0), 1.0))


def classify(lex: float, sem_cal: float) -> str:
    """Label one evidence cell.

    Literal presence and semantic inference are ALTERNATIVE forms of evidence,
    not additive ones, which is why coverage is a soft-OR rather than a sum.
    """
    if lex >= config.LEX_FUZZY_SCORE:
        return MATCHED
    if sem_cal > config.STATUS_INFERRED_MIN:
        return INFERRED
    if sem_cal > config.STATUS_WEAK_MIN:
        return WEAK
    return MISSING


# ─────────────────────────────────────────────────────────────────────────────
# prepare() — expensive, alpha-independent
# ─────────────────────────────────────────────────────────────────────────────

def prepare(subs: list[SubScores], skills: list[Skill]) -> list[Primitives]:
    """Build the evidence matrix and normalise both channels across the pool."""
    if not subs:
        return []

    bm25_norm = robust_norm(np.array([s.bm25_raw for s in subs]))
    docsim_norm = robust_norm(np.array([s.docsim_raw for s in subs]))

    total_w = sum(s.weight for s in skills) or 1.0
    req_w = sum(s.weight for s in skills if s.tier == REQUIRED) or 1.0

    out: list[Primitives] = []
    for i, sub in enumerate(subs):
        cells: list[SkillCell] = []
        lex_acc = sem_acc = req_acc = inferred_acc = 0.0

        for skill in skills:
            ev = sub.evidence.get(skill.id)
            lex = ev.lex if ev else 0.0
            sem_raw = ev.sem_raw if ev else 0.0
            sem_cal = calibrate(sem_raw)
            coverage = max(lex, sem_cal)

            status = classify(lex, sem_cal)

            lex_acc += skill.weight * lex
            sem_acc += skill.weight * sem_cal
            if skill.tier == REQUIRED:
                req_acc += skill.weight * coverage
                if status == INFERRED:
                    inferred_acc += skill.weight

            cells.append(SkillCell(
                skill_id=skill.id, label=skill.label, tier=skill.tier,
                weight=skill.weight, cluster=skill.cluster,
                lex=lex, lex_kind=ev.lex_kind if ev else "none",
                sem_raw=sem_raw, sem_cal=sem_cal,
                coverage=coverage, status=status,
                evidence=ev.chunk_text if ev else "",
                start=ev.chunk_start if ev else -1,
                end=ev.chunk_end if ev else -1,
            ))

        req_coverage = req_acc / req_w
        out.append(Primitives(
            doc_id=sub.doc_id, name=sub.name, filename=sub.filename,
            bm25_raw=sub.bm25_raw, bm25_norm=float(bm25_norm[i]),
            docsim_raw=sub.docsim_raw, docsim_norm=float(docsim_norm[i]),
            lex_cov=lex_acc / total_w,
            sem_cov=sem_acc / total_w,
            req_coverage=req_coverage,
            gap_density=1.0 - req_coverage,
            inferred_req_ratio=inferred_acc / req_w,
            quality=sub.quality, n_chunks=sub.n_chunks, warnings=list(sub.warnings),
            cells=cells,
        ))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# score() — cheap, pure, mirrored in JavaScript
# ─────────────────────────────────────────────────────────────────────────────

def channel_k(p: Primitives) -> float:
    """Keyword channel. BM25 supplies corpus-aware term rarity; coverage supplies
    requirement awareness. Each covers the other's blind spot."""
    w = config.K_WEIGHT_BM25
    return w * p.bm25_norm + (1.0 - w) * p.lex_cov


def channel_m(p: Primitives) -> float:
    """Semantic channel. Document-level fit plus per-skill inference."""
    w = config.M_WEIGHT_DOCSIM
    return w * p.docsim_norm + (1.0 - w) * p.sem_cov


def gate_multiplier(p: Primitives, enabled: bool) -> float:
    """Expresses 'a role that explicitly asks for certain skills shouldn't be
    satisfied by only loosely related experience'.

    Floored so the gate re-ranks rather than annihilates — a recruiter should
    still be able to see a strong near-miss.
    """
    if not enabled:
        return 1.0
    return config.GATE_FLOOR + config.GATE_SPAN * p.req_coverage


def score(
    primitives: list[Primitives],
    alpha: float = config.DEFAULT_ALPHA,
    gate: bool = config.GATE_ENABLED_DEFAULT,
) -> list[Candidate]:
    """Rank the pool. Pure function of `primitives`, `alpha` and `gate`.

    alpha = 1.0 -> pure keyword.  alpha = 0.0 -> pure semantic.
    """
    if not primitives:
        return []

    alpha = float(min(max(alpha, 0.0), 1.0))

    ks = [channel_k(p) for p in primitives]
    ms = [channel_m(p) for p in primitives]
    gates = [gate_multiplier(p, gate) for p in primitives]
    finals = [100.0 * (alpha * k + (1.0 - alpha) * m) * g for k, m, g in zip(ks, ms, gates)]

    rank_lex = _ranks(ks)
    rank_sem = _ranks(ms)

    cands: list[Candidate] = []
    for i, p in enumerate(primitives):
        delta = rank_lex[i] - rank_sem[i]
        cands.append(Candidate(
            doc_id=p.doc_id, name=p.name, filename=p.filename,
            score=round(finals[i], 2), rank=0,
            k_score=round(ks[i], 4), m_score=round(ms[i], 4), gate=round(gates[i], 4),
            rank_lexical=rank_lex[i], rank_semantic=rank_sem[i], rank_delta=delta,
            rrf=round(1.0 / (config.RRF_K + rank_lex[i]) + 1.0 / (config.RRF_K + rank_sem[i]), 6),
            flag=_flag(delta, p.inferred_req_ratio, p.lex_cov - p.sem_cov, p.req_coverage),
            primitives=p,
        ))

    cands.sort(key=lambda c: (-c.score, c.name))
    for idx, c in enumerate(cands, start=1):
        c.rank = idx
    return cands


def _ranks(values: list[float]) -> list[int]:
    """1-based dense ranking, highest value first. Ties broken by original order."""
    order = sorted(range(len(values)), key=lambda i: (-values[i], i))
    ranks = [0] * len(values)
    for position, idx in enumerate(order, start=1):
        ranks[idx] = position
    return ranks


def _flag(delta: int, inferred_req_ratio: float, lex_sem_gap: float, req_coverage: float) -> str:
    """Cross-channel disagreement, read from the evidence matrix first.

    HIDDEN GEM is the "Express and MongoDB" candidate from the problem statement:
    required skills that are demonstrably practised but never named. That shows up
    directly as INFERRED cells on REQUIRED rows, which is a far steadier signal
    than pool position — a candidate can be mid-ranked in BOTH channels and still
    be a genuine hidden gem, which rank delta alone can never see.

    SURFACE MATCH is the inverse: the resume names the skills but shows no work
    behind them, so lexical coverage far outruns semantic coverage.

    Rank delta stays as a corroborating trigger at a wider threshold, which is
    where the RRF sidecar earns its place without driving the displayed score.
    """
    gem_evidence = (
        inferred_req_ratio >= config.HIDDEN_GEM_INFERRED_RATIO
        or delta >= config.RRF_FLAG_DELTA
    )
    if gem_evidence and req_coverage >= config.HIDDEN_GEM_MIN_COVERAGE:
        return HIDDEN_GEM
    if lex_sem_gap >= config.SURFACE_LEX_SEM_GAP or delta <= -config.RRF_FLAG_DELTA:
        return SURFACE_MATCH
    return CONSENSUS


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def without_skills(primitives: list[Primitives], drop: set[str]) -> list[Primitives]:
    """Re-derive the pool as if the given requirements had never been asked for.

    Powers the bias detector's impact simulation: "how many candidates does this
    single requirement actually cost you?" Only the coverage terms change —
    BM25 and document similarity are document-level and do not depend on the
    skill set — so this is pure arithmetic over cells already computed, with no
    re-parsing and no re-embedding.
    """
    out: list[Primitives] = []
    for p in primitives:
        kept = [c for c in p.cells if c.skill_id not in drop]
        total_w = sum(c.weight for c in kept) or 1.0
        req_cells = [c for c in kept if c.tier == REQUIRED]
        req_w = sum(c.weight for c in req_cells) or 1.0

        req_acc = sum(c.weight * c.coverage for c in req_cells)
        inferred_acc = sum(c.weight for c in req_cells if c.status == INFERRED)
        req_coverage = req_acc / req_w

        out.append(Primitives(
            doc_id=p.doc_id, name=p.name, filename=p.filename,
            bm25_raw=p.bm25_raw, bm25_norm=p.bm25_norm,
            docsim_raw=p.docsim_raw, docsim_norm=p.docsim_norm,
            lex_cov=sum(c.weight * c.lex for c in kept) / total_w,
            sem_cov=sum(c.weight * c.sem_cal for c in kept) / total_w,
            req_coverage=req_coverage,
            gap_density=1.0 - req_coverage,
            inferred_req_ratio=inferred_acc / req_w,
            quality=p.quality, n_chunks=p.n_chunks, warnings=list(p.warnings),
            cells=kept,
        ))
    return out


def cells_by_status(p: Primitives, *statuses: str) -> list[SkillCell]:
    """Evidence cells filtered by label, strongest first."""
    picked = [c for c in p.cells if c.status in statuses]
    return sorted(picked, key=lambda c: (-c.weight, -c.coverage, c.label.lower()))


def primitives_to_dict(p: Primitives) -> dict:
    return asdict(p)
